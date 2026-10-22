"""Pure full-set bootstrap, reviewed admission and fail-fast bookkeeping."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import image_recovery_remaining_matrix as matrix


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fake_plan(root):
    jobs=[]
    for i in range(42):
        jobs.append({'name':'case-'+str(i),'argv':['mocked-child',str(i)],'report':str(root/'results'/('case-'+str(i)+'.json')),
            'cleanup_report':str(root/'results'/('case-'+str(i)+'-cleanup.json')),'outer_timeout_seconds':900})
    plan={'execution_ready':True,'known38_ownership_gap':False,'driver_sha256':'a'*64,'image_config_identity':'sha256:'+'b'*64,
        'artifact_sha256':'c'*64,'jobs':jobs,'env':{},'runtime_cwd':str(root/'results')}
    (root/'results').mkdir();matrix.dump(root/'plan.json',plan);return plan


def execute_case(root,mode):
    plan=fake_plan(root);calls=[]
    def popen(argv,**kwargs):
        calls.append(argv)
        assert 'PYTHONPATH' not in kwargs['env'] and 'LD_PRELOAD' not in kwargs['env'] and 'GCC_EXEC_PREFIX' not in kwargs['env']
        if mode=='creation':raise OSError('synthetic creation failure')
        i=int(argv[-1]);job=plan['jobs'][i]
        matrix.dump(job['report'],{'passed':mode!='report-false','artifact_sha256':plan['artifact_sha256']})
        matrix.dump(job['cleanup_report'],{'passed':True,'images':[{'closed':mode!='open-image'}],'owned_native_processes_absent':True})
        if mode=='parent-interrupt':
            live=[True]
            def wait(**kwargs):
                if not kwargs:raise KeyboardInterrupt('parent interrupted')
                live[0]=False;return 0
            return SimpleNamespace(pid=123,wait=wait,poll=lambda:None if live[0] else 0,send_signal=lambda value:None)
        return SimpleNamespace(pid=123,wait=lambda:0,poll=lambda:0)
    caught=None
    with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'claim_execution') as claim,patch.object(matrix.subprocess,'Popen',side_effect=popen):
        try:matrix.execute(root,sha(root/'plan.json'))
        except BaseException as error:caught=error
    result=json.loads((root/'matrix.json').read_text());assert claim.call_count==1
    if mode=='success':assert caught is None and result['passed'] and len(calls)==42 and not result['unrun']
    else:
        assert caught is not None and not result['passed'] and len(calls)==1
        assert result['rows'][0]['started']==(mode!='creation') and len(result['unrun'])==(42 if mode=='creation' else 41)
        assert result['rows'][0]['exit_code']==(None if mode=='creation' else 0)
    return result


def full_app_resume_case():
    names=['admission','rejections','private','agent-admission','uninitialized-move','mixed','federation-errors','learned','crash-damaged-after-install-snapshot','crash-no-default-after-install-snapshot']+['crash-later-'+str(n)for n in range(13)]+['rebind','rebind-hostile']
    image='sha256:'+'a'*64;artifact='b'*64
    basis={'jobs':[{'name':n}for n in names],'full_app_only':True,'compiled_binding':{'bound':True},'image_config_identity':image,'artifact_sha256':artifact}
    matrix_value={'passed':False,'artifact_sha256':artifact,'image_config_identity':image,'planned':25,
        'rows':[{'name':n,'passed':i<9,'exit_code':0 if i<9 else 1,'started':True}for i,n in enumerate(names[:10])],
        'executed':names[:10],'attempted':names[:10],'unrun':names[10:]}
    assert matrix.remainder_names(basis,matrix_value,artifact,image)==names[9:]
    for mode in ['not-full-app','missing-cache','wrong-parent-artifact','wrong-parent-image','prefix-false','wrong-failed-name','wrong-unrun','partial-executed']:
        b=copy.deepcopy(basis);m=copy.deepcopy(matrix_value)
        if mode=='not-full-app':b['full_app_only']=False
        elif mode=='missing-cache':b['compiled_binding']=None
        elif mode=='wrong-parent-artifact':b['artifact_sha256']='c'*64
        elif mode=='wrong-parent-image':b['image_config_identity']='sha256:'+'d'*64
        elif mode=='prefix-false':m['rows'][8]['passed']=False
        elif mode=='wrong-failed-name':m['rows'][9]['name']='unrelated'
        elif mode=='wrong-unrun':m['unrun']=m['unrun'][:-1]
        else:m['executed']=m['executed'][:-1]
        try:matrix.remainder_names(b,m,artifact,image)
        except AssertionError:pass
        else:raise AssertionError('Full-app25 continuation scope bypass: '+mode)


def main():
    full_app_resume_case()
    names=['admission','rejections','private','agent-admission','uninitialized-move','mixed','federation-errors','learned']+['crash-'+str(n)for n in range(15)]+['rebind','rebind-hostile']
    rows=[{'name':n,'family':'crash'if n.startswith('crash-')else'http'}for n in names]
    descriptor={'selected_rows':rows[:8]+[{'name':'primitive-'+str(n),'family':'component'}for n in range(17)]+rows[8:]}
    assert [r['name']for r in matrix.full_app_rows(descriptor)]==names
    bad=copy.deepcopy(descriptor);bad['selected_rows'].pop()
    try:matrix.full_app_rows(bad)
    except AssertionError:pass
    else:raise AssertionError('Incomplete25 accepted')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve();work=root/'bootstrap';frozen=work/'frozen';(frozen/'tests').mkdir(parents=True)
        helper=frozen/'tests/helper.py';helper.write_text('raise RuntimeError("never imported")\n')
        driver=work/'driver.py';driver.write_text('pure fake driver\n')
        plan={'driver_sha256':sha(driver),'frozen_inputs':{'tests/helper.py':sha(helper)}};matrix.dump(work/'plan.json',plan)
        assert matrix.bootstrap(driver,sha(work/'plan.json'))==str(frozen/'tests')
        for mode in ['changed','extra','symlink','redirect']:
            if mode=='changed':helper.write_text('changed')
            elif mode=='extra':(frozen/'tests/shadow.py').write_text('shadow')
            elif mode=='symlink':(frozen/'tests/shadow.py').symlink_to(helper)
            else:
                frozen.rename(work/'real');frozen.symlink_to(work/'real',target_is_directory=True)
            try:matrix.bootstrap(driver,sha(work/'plan.json'))
            except AssertionError:pass
            else:raise AssertionError('Frozen custody bypass: '+mode)
            if mode=='changed':helper.write_text('raise RuntimeError("never imported")\n')
            elif mode in ('extra','symlink'):(frozen/'tests/shadow.py').unlink()
            else:frozen.unlink();(work/'real').rename(frozen)
        original=root/'old';(original/'tests').mkdir(parents=True);f=original/'tests/vector.exs';f.write_text('exact vector')
        inventory={'trees':['tests'],'files':{'tests/vector.exs':{'sha256':sha(f)}}}
        (original/'_build').mkdir();(original/'_build/actual-old-output').write_text('unselected original output')
        assert matrix.verify_original(original,inventory)==[Path('tests')]
        (original/'tests/shadow.exs').write_text('unlisted input')
        try:matrix.verify_original(original,inventory)
        except AssertionError:pass
        else:raise AssertionError('Unknown input inside declared tree accepted')
        (original/'tests/shadow.exs').unlink()
        cache=root/'empty-cache';cache.mkdir(mode=0o700);matrix.verify_empty_cache(cache,required=True)
        (cache/'stale.pyc').write_bytes(b'cache')
        try:matrix.verify_empty_cache(cache,required=True)
        except AssertionError:pass
        else:raise AssertionError('Stale cache accepted')
        (cache/'stale.pyc').unlink();redirected=root/'redirected-cache';redirected.symlink_to(cache,target_is_directory=True)
        try:matrix.verify_empty_cache(redirected,required=True)
        except AssertionError:pass
        else:raise AssertionError('Redirected cache accepted')
        for mode in ['success','creation','report-false','open-image','parent-interrupt']:
            case=root/mode;case.mkdir()
            with patch.dict(matrix.os.environ,{'PYTHONPATH':'unreviewed','LD_PRELOAD':'unreviewed','GCC_EXEC_PREFIX':'unreviewed'}):execute_case(case,mode)
        bad=root/'diagnostic';bad.mkdir();p=fake_plan(bad);p['known38_ownership_gap']=True;matrix.dump(bad/'plan.json',p)
        with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'claim_execution') as claim,patch.object(matrix.subprocess,'Popen') as child:
            try:matrix.execute(bad,sha(bad/'plan.json'))
            except AssertionError:pass
            else:raise AssertionError('Diagnostic image executed')
            assert not claim.called and not child.called
        actions=[]
        def interrupted_wait(**kwargs):
            actions.append(('wait',kwargs))
            if not kwargs:raise KeyboardInterrupt('original parent interruption')
            return 0
        process=SimpleNamespace(wait=interrupted_wait,poll=lambda:None,send_signal=lambda value:actions.append(('signal',value)))
        try:matrix.wait_owned_child(process)
        except KeyboardInterrupt as error:assert str(error)=='original parent interruption'
        else:raise AssertionError('Parent interruption masked')
        assert actions==[('wait',{}),('signal',matrix.signal.SIGINT),('wait',{'timeout':90})]
        for value in [['${UNKNOWN}'],{'x':'${UNKNOWN}'}]:
            try:matrix.resolve(value,{'KNOWN':'x'})
            except AssertionError:pass
            else:raise AssertionError('Unresolved command admitted')
    print('PASS remaining matrix pure20 (plus eight full-app25 continuation negative guards) (including full-app25 exact order/incomplete rejection): staged fullSET/hash/symlink/root custody, exact42 success, creationfail attempted-vs-executed, reportfalse failfast, openimage closure denial, diagnostic38 beforeclaim denial, unresolved templates, exact declared-origin trees with excluded old outputs/inside-shadow denial, parent interruption signals owned child cleanup/preserves primary+known terminal exit, stale/redirected caches rejected, ambient injection not inherited; actual subprocess/runtime calls0')


if __name__=='__main__':main()
