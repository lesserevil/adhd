"""Prepare/execute one explicitly reviewed, source-unchanged R25 phase diagnostic.

No qualification assertions or deadlines are replaced. The old false aggregate
and all of its inputs remain immutable. Execution needs a separately reviewed
fresh plan hash; preparation does not start a VM, broker, compiler or model.
"""
import sys
sys.dont_write_bytecode=True
import asyncio
import time
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import stat
import re
import tarfile
from uuid import uuid4


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def regular(path):
    path=Path(path).absolute();s=path.lstat()
    assert path.resolve(strict=True)==path and stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1
    return path


def render_observer(template,source,artifact_sha256):
    """Select known MFA arities from exact source bytes, never evaluate code."""
    assert hashlib.sha256(source).hexdigest()==artifact_sha256
    match=re.search(r'^defmodule ADHD\.Eventing do\n(.*?)(?=^defmodule |\Z)',source.decode(),re.M|re.S)
    assert match,'Bound Eventing module missing'
    def arities(name):
        result=set()
        for arguments in re.findall(r'^\s+defp? '+re.escape(name)+r'\(([^\n)]*)\)',match.group(1),re.M):
            depth=0;count=1 if arguments.strip()else 0
            for char in arguments:
                if char in '[{(':depth+=1
                elif char in ']})':depth-=1
                elif char==',' and depth==0:count+=1
                assert depth>=0
            assert depth==0
            defaults=arguments.count(chr(92)*2)
            result.update(range(count-defaults,count+1))
        return sorted(result)
    observed={name:arities(name)for name in ('preflight_restore','provision','request','request_until','request_now','response','success')}
    legacy={'preflight_restore':[2],'provision':[2,3],'request':[4,5,6],'request_until':[],'request_now':[7],'response':[4],'success':[1]}
    current={'preflight_restore':[2,3],'provision':[2,3,4],'request':[4,5,6],'request_until':[7],'request_now':[8],'response':[4],'success':[1]}
    assert observed in (legacy,current),'Unsupported Eventing observer signature profile'
    rendered=template.decode()
    assert len(re.findall(r'^\s+\{ADHD\.',rendered,re.M))==16
    for token in ('{ADHD.Eventing, :preflight_restore, 2}', '{ADHD.Eventing, :provision, 3}', '{ADHD.Eventing, :request, 6}', '{ADHD.Eventing, :request_now, 7}'):
        assert rendered.count(token)==1,'Unexpected observer template'
    if observed==current:
        rendered=rendered.replace('{ADHD.Eventing, :preflight_restore, 2},','{ADHD.Eventing, :preflight_restore, 2},\n    {ADHD.Eventing, :preflight_restore, 3},')
        rendered=rendered.replace('{ADHD.Eventing, :provision, 3},','{ADHD.Eventing, :provision, 3},\n    {ADHD.Eventing, :provision, 4},')
        rendered=rendered.replace('{ADHD.Eventing, :request, 6},','{ADHD.Eventing, :request, 6},\n    {ADHD.Eventing, :request_until, 7},')
        rendered=rendered.replace('{ADHD.Eventing, :request_now, 7}', '{ADHD.Eventing, :request_now, 8}')
    profile={'name':'shared-deadline19'if observed==current else 'legacy16','pattern_count':19 if observed==current else 16,
             'source_sha256':artifact_sha256,'observed_arities':observed,'template_sha256':hashlib.sha256(template).hexdigest()}
    assert len(re.findall(r'^\s+\{ADHD\.',rendered,re.M))==profile['pattern_count']
    return rendered.encode(),profile


def bound_observer(original,parent,template):
    """Read only the already context-bound source, without code evaluation."""
    path=regular(Path(original)/'context/payload.tar');assert path.stat().st_size<=32*1024*1024
    with tarfile.open(path,mode='r:')as archive:
        entries=[item for item in archive.getmembers()if item.name=='app/hub.exs']
        assert len(entries)==1 and entries[0].isfile()and entries[0].size<=8*1024*1024
        source=archive.extractfile(entries[0]).read()
    return render_observer(template,source,parent['artifact_sha256'])


def instrument(base,image,observer,root,arm,index,nonce):
    assert base[:2]==['docker','run'] and base[-1]==image
    assert '--entrypoint' not in base and not any(x=='--pid' or x.startswith('--pid=')for x in base)
    assert all(',' not in str(p) for p in [observer,root,arm])
    log=root/('phase-'+str(index)+'.log');assert not log.exists() and not log.is_symlink()
    additions=['--entrypoint','elixir','--mount','type=bind,src='+str(observer)+',dst=/adhd-test/recovery-phase.exs,readonly',
        '--env','ADHD_TEST_PHASE_LOG='+str(log),'--env','ADHD_TEST_PHASE_ARM='+str(arm),'--env','ADHD_TEST_PHASE_NONCE='+nonce]
    return base[:-1]+additions+[image,'-r','/adhd-test/recovery-phase.exs','/runtime/adhd/boot.exs','/app/hub.exs'],log


def inspected(row,target,compiled,original):
    assert row['Config']['Entrypoint']==['elixir']
    assert row['Config']['Cmd']==['-r','/adhd-test/recovery-phase.exs','/runtime/adhd/boot.exs','/app/hub.exs',json.dumps(['serve',str(target.config_file)])]
    mounts=[v for v in row['Mounts']if v['Destination']=='/adhd-test/recovery-phase.exs']
    assert len(mounts)==1 and mounts[0]['Type']=='bind' and mounts[0]['RW']is False and mounts[0]['Source']==target.phase_observer_path
    assert sha(regular(mounts[0]['Source']))==target.phase_observer_sha256
    normalized=copy.deepcopy(row);normalized['Config']['Entrypoint']=compiled['reviewed_runtime_audit']['entrypoint']
    proof=original(normalized,target,compiled)
    proof.update(entrypoint=row['Config']['Entrypoint'],execution_scope='source-unchanged-compiled-boot-with-diagnostic-mfa-observer',
        diagnostic_observer_sha256=target.phase_observer_sha256,diagnostic_trace_path=target.phase_trace_paths[-1],diagnostic_argv_prefix=row['Config']['Cmd'][:-1])
    return proof


def install(observer,pattern_count=16):
    assert pattern_count in (16,19)
    import image_filesystem_fault as faults
    import image_recovery_cache as cache
    from multi_support import Fixture
    start=Fixture.start
    argv=faults.FilesystemFaultImage.argv;inspect=cache.inspected_launch
    digest=sha(regular(observer))
    def command(target,config):
        assert sha(regular(observer))==digest
        base=argv(target,config)
        if not hasattr(target,'phase_trace_paths'):target.phase_trace_paths=[]
        target.phase_observer_path=str(observer);target.phase_observer_sha256=digest
        arm=Path(target.environment['ADHD_RECOVERY_FAULT_ARM'])
        nonce=uuid4().hex
        result,log=instrument(base,target.image_id,observer,target.root,arm,len(target.phase_trace_paths),nonce)
        target.phase_nonce=nonce
        target.phase_readiness_deadline=time.monotonic()+45
        target.phase_trace_paths.append(str(log));return result
    async def ready(fixture):
        await start(fixture)
        target=fixture.image_runtime
        assert isinstance(target,faults.FilesystemFaultImage)
        path=Path(target.phase_trace_paths[-1])
        while time.monotonic()<target.phase_readiness_deadline:
            if path.exists():
                info=regular(path).stat();assert stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=65536
                lines=path.read_text().splitlines()
                assert not any('|observer-failed|'in x or '|limit|'in x or '|expired|'in x for x in lines)
                if any('|header|'+target.phase_nonce+'|'in x for x in lines)and any(x.endswith('|ready|'+target.phase_nonce+'|'+str(pattern_count)+'-mfa-patterns')for x in lines):return
            await asyncio.sleep(.01)
        raise AssertionError('Diagnostic tracing was not verified within the unchanged original startup bound')
    Fixture.start=ready
    faults.FilesystemFaultImage.argv=command
    cache.inspected_launch=lambda row,target,compiled:inspected(row,target,compiled,inspect)
    return lambda:(setattr(faults.FilesystemFaultImage,'argv',argv),setattr(cache,'inspected_launch',inspect),setattr(Fixture,'start',start))


def verify(work,plan):
    assert sha(regular(work/'driver.py'))==plan['driver_sha256']
    assert {p.name for p in work.iterdir()} <= {'driver.py','observer.exs','observer-template.exs','plan.json','started.json','result.json','results','parent-cache'}
    assert sha(regular(work/'observer.exs'))==plan['observer_sha256']
    original=Path(plan['original_work']);assert sha(original/'plan.json')==plan['original_plan_sha256']
    # Import only the original read-only verifier, not its main/execute path.
    oldargv=sys.argv;sys.argv=['audit','--execute','--plan-sha256',plan['original_plan_sha256']]
    try:
        spec=importlib.util.spec_from_file_location('reviewed_original_r25',original/'driver.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        parent=json.loads((original/'plan.json').read_text());assert module.verify(original,parent)
    finally:sys.argv=oldargv
    assert sha(regular(work/'observer-template.exs'))==plan['observer_profile']['template_sha256']
    rendered,profile=bound_observer(original,parent,(work/'observer-template.exs').read_bytes())
    assert profile==plan['observer_profile']and rendered==(work/'observer.exs').read_bytes()
    selected=next(r for r in parent['jobs']if r['name']==plan['case'])
    assert plan['argv']==[v.replace(str(original/'results'),str(work/'results'))for v in selected['argv']]
    assert sha(original/'matrix.json')==plan['original_matrix_sha256']
    assert parent['image_config_identity']==plan['image_config_identity'] and parent['artifact_sha256']==plan['artifact_sha256']
    assert plan['case']=='crash-no-default-after-install-snapshot'
    assert int(plan['argv'][plan['argv'].index('--timeout')+1])==plan['original_outer_timeout_seconds']==900
    return True


def import_preflight(work,plan):
    """Load only the verified venv, without ambient site/.pth processing."""
    original=Path(plan['original_work']);parent=json.loads((original/'plan.json').read_text())
    host=json.loads((original/'bound/host-dependencies.json').read_text())
    root=Path(parent['python']['path']).parent.parent
    trees=[t for t in host['trees']if Path(t['root'])==root];assert len(trees)==1
    candidates=[Path(n).parent.parent for n in trees[0]['files']if n.endswith('/httpx/__init__.py')]
    assert len(candidates)==1
    site=root/candidates[0];assert site.resolve(strict=True)==site and site.is_dir()
    assert sha(site/'httpx/__init__.py')==trees[0]['files'][str(candidates[0]/'httpx/__init__.py')]['sha256']
    if str(site)not in sys.path:sys.path.append(str(site))
    import subprocess
    names=['Popen','run','check_call','check_output','call'];saved={n:getattr(subprocess,n)for n in names}
    def denied(*_,**__):raise AssertionError('Dependency import attempted a subprocess')
    undo=None
    try:
        for name in names:setattr(subprocess,name,denied)
        undo=install(work/'observer.exs',plan['observer_profile']['pattern_count'])
        command=plan['argv'];entry=Path(command[3]);script=Path(command[command.index('--script')+1])
        runpy.run_path(str(entry),run_name='diagnostic_dependency_import_only')
        runpy.run_path(str(script),run_name='diagnostic_dependency_import_only')
    finally:
        if undo:undo()
        for name,value in saved.items():setattr(subprocess,name,value)
    return {'site_packages':str(site),'pth_executed':False,'install_and_original_modules_imported':True,'subprocess_calls_authorized':0}


def prepare(args):
    work=args.work.absolute();assert not work.exists();old=args.original.absolute();parent=json.loads((old/'plan.json').read_text())
    row=next(r for r in parent['jobs']if r['name']=='crash-no-default-after-install-snapshot')
    work.mkdir(mode=0o700);(work/'parent-cache').mkdir(mode=0o700)
    import shutil
    shutil.copyfile(__file__,work/'driver.py')
    template=regular(Path(__file__).with_name('recovery_phase_observer.exs')).read_bytes()
    rendered,profile=bound_observer(old,parent,template)
    (work/'observer-template.exs').write_bytes(template);(work/'observer.exs').write_bytes(rendered)
    plan={'schema':'adhd/recovery-causal-diagnostic@1','scope':'One diagnostic, not qualification. Original no-default crash assertions and deadlines unchanged; no retry.',
        'case':row['name'],'original_work':str(old),'original_plan_sha256':sha(old/'plan.json'),'original_matrix_sha256':sha(old/'matrix.json'),
        'driver_sha256':sha(work/'driver.py'),'observer_sha256':sha(work/'observer.exs'),'observer_profile':profile,'image_config_identity':parent['image_config_identity'],
        'artifact_sha256':parent['artifact_sha256'],'argv':[v.replace(str(old/'results'),str(work/'results'))for v in row['argv']],
        'original_outer_timeout_seconds':row['outer_timeout_seconds'],'provider_calls_authorized':0,'parallelism':1,'runs':1,
        'python_flags':['-I','-S','-B','-X','pycache_prefix='+str(old/'parent-cache')],'expected_original_input_counts':{k:len(parent[k])for k in ['frozen_inputs','component_inputs','context_inputs','bound_inputs','external_inputs']}}
    dump(work/'plan.json',plan);print(json.dumps({'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'work':str(work)}))


def claim(work):
    fd=os.open(work/'started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:os.write(fd,b'{"once":true}\n');os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def execute(args):
    work=args.work.absolute();assert Path(__file__).absolute()==work/'driver.py'
    assert sha(regular(work/'plan.json'))==args.plan_sha256
    plan=json.loads((work/'plan.json').read_text());assert verify(work,plan)
    imports=import_preflight(work,plan)
    claim(work);(work/'results').mkdir(mode=0o700)
    parent=json.loads((Path(plan['original_work'])/'plan.json').read_text())
    os.environ.clear();os.environ.update(parent['env'])
    # The original entry installs exact owned runtime finally cleanup. Instrument
    # its class in-place; executing the entry cannot change the original script.
    undo=None;oldargv=sys.argv;failure=None;primary=None
    try:
        undo=install(work/'observer.exs',plan['observer_profile']['pattern_count'])
        command=plan['argv'];sys.argv=command[3:]
        assert sys.argv[0].endswith('/image_recovery_entry.py')
        runpy.run_path(sys.argv[0],run_name='__main__')
    except BaseException as error:
        primary=error;failure=type(error).__name__;raise
    finally:
        sys.argv=oldargv
        if undo:undo()
        postverify=False
        try:
            assert verify(work,plan);postverify=True
            traces=[]
            for f in (work/'results').rglob('phase-*.log'):
                s=f.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and s.st_size<=65536
                lines=f.read_text().splitlines()
                traces.append({'path':str(f),'sha256':sha(f),'bytes':s.st_size,'ready_observed':any('|ready|'in line for line in lines),
                    'incomplete_observed':any(any('|'+mark+'|'in line for mark in ['expired','limit','observer-failed'])for line in lines)})
            dump(work/'result.json',{'diagnostic_only':True,'dependency_import_preflight':imports,'original_inputs_reverified':postverify,'failure_type':failure,'trace_files':traces,'original_cleanup_report':str(work/'results'/ (plan['case']+'-cleanup.json'))})
        except BaseException as error:
            if primary is not None:primary.add_note('Diagnostic evidence finalization failed: '+type(error).__name__)
            else:raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--verify-only',action='store_true');p.add_argument('--work',type=Path,required=True);p.add_argument('--original',type=Path);p.add_argument('--plan-sha256');a=p.parse_args();assert sum([a.prepare,a.execute,a.verify_only])==1
    if a.prepare:prepare(a)
    elif a.verify_only:
        assert sha(regular(a.work/'plan.json'))==a.plan_sha256
        plan=json.loads((a.work/'plan.json').read_text())
        assert verify(a.work,plan)
        print(json.dumps(import_preflight(a.work,plan)))
        assert not(a.work/'started.json').exists()and not(a.work/'results').exists()
        print('Verified; no execution')
    else:execute(a)
if __name__=='__main__':main()
