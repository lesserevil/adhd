"""Prepare current admitted-source native UI9 without relabeling native39 evidence.

Preparation reads/copies inputs only. Original browser scripts, query/assertion
bounds, viewport/role cases and native argv remain authoritative.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
sys.dont_write_bytecode=True


def bootstrap_frozen(driver):
    """Verify the frozen import tree using only stdlib before importing it."""
    driver=Path(driver).absolute();work=driver.parent
    assert driver.resolve(strict=True)==driver and not driver.is_symlink()
    planfile=work/'plan.json';assert not planfile.is_symlink() and planfile.stat().st_size<=16*1024*1024
    raw=planfile.read_bytes();plan=json.loads(raw)
    assert hashlib.sha256(driver.read_bytes()).hexdigest()==plan['driver_sha256']
    if '--execute'in sys.argv:
        assert sys.argv.count('--reviewed-plan-sha256')==1
        assert hashlib.sha256(raw).hexdigest()==sys.argv[sys.argv.index('--reviewed-plan-sha256')+1]
    frozen=work/'frozen';assert frozen.resolve(strict=True)==frozen and frozen.is_dir() and not frozen.is_symlink()
    expected=plan['frozen_inputs'];observed={};directories=set();wanted_directories=set()
    for name in expected:
        path=Path(name);assert not path.is_absolute() and '..'not in path.parts and str(path)==name
        wanted_directories.update(str(p)for p in path.parents if str(p)!='.')
    for path in frozen.rglob('*'):
        info=path.lstat();assert not stat.S_ISLNK(info.st_mode)
        name=str(path.relative_to(frozen))
        if stat.S_ISDIR(info.st_mode):directories.add(name)
        else:
            assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
            observed[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    assert observed==expected and directories==wanted_directories
    sys.path.insert(0,str(frozen/'tests'))


if Path(__file__).name=='run.py':bootstrap_frozen(__file__)
from image_ui_matrix import CASES, tree, captures, unit_count


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def module_identity(old,current):
    def modules(raw):
        sections=re.split(rb'(?m)(?=^defmodule ADHD\.)',raw)
        return {re.match(rb'defmodule (ADHD\.[A-Za-z0-9]+)',section).group(1).decode():section
            for section in sections if section.startswith(b'defmodule ADHD.')}
    before,after=modules(old),modules(current);assert len(before)==len(after)==59 and set(before)==set(after)
    changed=[name for name in before if before[name]!=after[name]]
    assert changed==['ADHD.Projects'] and before['ADHD.Web']==after['ADHD.Web']
    return {'old_artifact_sha256':hashlib.sha256(old).hexdigest(),'target_artifact_sha256':hashlib.sha256(current).hexdigest(),
        'modules':59,'byte_identical_modules':58,'changed_modules':changed,
        'Web_byte_range_sha256':hashlib.sha256(after['ADHD.Web']).hexdigest(),
        'conclusion':'Identical presentation bytes support visual comparison and avoid another image run. Native39 development execution is not current admitted-source native execution; no86 reuse claim.'}


def native_arguments(original,script,artifact,report,keep,tarball):
    """Retarget only owned paths/current source; preserve every original flag."""
    start=next(i for i,value in enumerate(original) if value.endswith('.py'))
    result=copy.deepcopy(original[start:]);result[0]=str(script)
    for index,value in enumerate(result):
        if value=='--hub':result[index+1]=str(artifact)
        elif value=='--command':
            command=json.loads(result[index+1]);assert len(command)==2
            command[-1]=str(artifact);result[index+1]=json.dumps(command)
        elif value=='--keep-work':result[index+1]=str(keep)
        elif value=='--report':result[index+1]=str(report)
        elif value=='--openrig-tarball':result[index+1]=str(tarball)
    assert not any(value in result for value in ['--image','--rest-url','--deadline'])
    return result


def prepare(args):
    repo=args.repo.absolute();work=args.work.absolute();assert repo.resolve()==repo and not work.exists()
    reference=json.loads(args.reference_plan.read_text());reference_proof=json.loads(args.reference_proof.read_text())
    assert reference_proof['passed'] and reference_proof['whole_suites']==9 and reference_proof['whole_check_or_viewport_units']==86
    assert reference_proof['image_config_identity']==reference['image_config_identity'] and reference_proof['artifact_sha256']==reference['artifact_sha256']
    assert sha(args.admission)==args.admission_sha256
    admission=json.loads(args.admission.read_text());assert admission['passed'] and admission['artifact_sha256']==reference['artifact_sha256']
    reader=load(repo/'tests/image_qualification_inputs.py','native_ui_reviewed_inputs')
    selected=reader.reviewed_payload(args.context/'manifest.json',args.admission,args.admission_sha256,admission['image_config_identity'],admission['artifact_sha256'])
    actual=json.loads((args.admission.parent/'rebuild.json').read_text())['result'];artifact=Path(actual['artifact'])
    assert actual['passed'] and actual['receipt_committed'] and sha(artifact)==admission['artifact_sha256']
    initial=json.loads((repo/'verification/native39-ui-initial/plan.json').read_text())
    remainder=json.loads((repo/'verification/native39-ui-remainder/plan.json').read_text())
    historical=json.loads((repo/'verification/native39-ui-remainder/manifest.json').read_text())
    assert historical['passed'] and historical['complete_suites']==9 and historical['complete_check_or_viewport_units']==86
    assert sha(initial['artifact']['path'])==initial['artifact']['sha256']==historical['artifact_sha256']
    assert admission['image_config_identity']==reference['image_config_identity'] and reference['admission_sha256']==args.admission_sha256
    identity=module_identity(Path(initial['artifact']['path']).read_bytes(),artifact.read_bytes())
    work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
    _,drift=reader.freeze_inputs(repo,frozen,selected['specifications'])
    for name in ['native_ui_matrix.py','native_ui_runtime.py','native_ui_static.py']:
        shutil.copyfile(Path(__file__).with_name(name),frozen/'tests'/name)
    runtime=work/'runtime';openrig=args.openrig_root.absolute()
    assert not openrig.exists() and len(str(openrig/'rigs/mux/tmux-999999/default'))<105
    bound={'admission.json':args.admission,'receipt.json':args.admission.parent/'receipt.json','rebuild.json':args.admission.parent/'rebuild.json',
        'image-manifest.json':args.context/'manifest.json','staged-Dockerfile':args.context/'Dockerfile',
        'native39-initial-plan.json':repo/'verification/native39-ui-initial/plan.json',
        'native39-remainder-plan.json':repo/'verification/native39-ui-remainder/plan.json',
        'native39-manifest.json':repo/'verification/native39-ui-remainder/manifest.json',
        'image05-plan.json':args.reference_plan,'image05-proof.json':args.reference_proof,
        'openrig.tgz':args.reference_plan.parent/'openrig.tgz'}
    for name,path in bound.items():assert path.is_file() and not path.is_symlink();shutil.copyfile(path,work/name)
    for name in ['receipt.json','rebuild.json']:assert sha(work/name)==admission['files'][name]
    write(work/'source-identity-review.json',identity);bound['source-identity-review.json']=work/'source-identity-review.json'
    externals=copy.deepcopy(reference['externals']);tool_roots=copy.deepcopy(reference['tool_roots'])
    compiler=Path(shutil.which('cc')).resolve();elixir=repo/'_build/federation/native/elixir/bin/elixir'
    beams=list((repo/'_build/federation/native/erlang').glob('erts-*/bin/beam.smp'));assert len(beams)==1
    for path in [artifact,compiler,elixir.resolve(),beams[0],Path('/usr/bin/flock'),Path(sys.executable).resolve(),Path(initial['artifact']['path'])]:
        externals[str(path)]={'sha256':sha(path)}
    jobs=[]
    for row in initial['serial_lane']:
        name=row['name'];script=next(Path(value).name for value in row['argv'] if value.endswith('.py'));key='tests/'+script
        assert sha(frozen/key)==reference['frozen_inputs'][key],'Original final UI scenario bytes must remain unchanged'
        argv=native_arguments(row['argv'],frozen/key,artifact,work/(name+'.json'),openrig if name=='openrig' else runtime/name,work/'openrig.tgz')
        jobs.append({'name':name,'test_argv':argv,'expected_units':CASES[name],'outer_timeout_seconds':row['outer_timeout_seconds'],
            'custody_report':str(work/(name+'-custody.json')),'launch_ledger':str(work/(name+'-launches.json')),
            'process_ledger':str(work/(name+'-processes.json')),'foundation_lock':row['argv'][1] if row['argv'][0]=='/usr/bin/flock' else None,
            'scope':row['scope']})
    core=load(repo/'tests/native_core_remaining.py','native_ui_cwd_contract')
    shutil.copyfile(__file__,work/'run.py');frozen_tree=tree(frozen)
    plan={'schema':'adhd/admitted-native-ui-nine-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','runtime_kind':'native',
        'artifact':str(artifact),'artifact_sha256':sha(artifact),'admission_sha256':args.admission_sha256,
        'reference_image_only':reference['image_config_identity'],'reference_image_UI_qualified':True,
        'frozen':str(frozen),'frozen_tree':frozen_tree,'frozen_inputs':{k:v['sha256']for k,v in frozen_tree['files'].items()},
        'bound_inputs':{name:sha(work/name)for name in bound},'externals':externals,'tool_roots':tool_roots,
        'driver_sha256':sha(work/'run.py'),'runtime_cwd':str(runtime),'runtime_fixture':core.runtime_fixture(frozen),
        'openrig_root':str(openrig),'python':sys.executable,'compiler':str(compiler),'native_beam_sha256':sha(beams[0]),
        'fence_library':str(work/'provider-fence.so'),'fence_audit':str(work/'provider-fence.audit'),
        'qualified_path':reference['qualified_path'],'env':reference['env'],'lane_lock':initial['lane_lock'],
        'jobs':jobs,'planned_suites':list(CASES),'expected_units':86,'parallelism':1,'maximum_owned_hubs':2,
        'automatic_retries':0,'runs_per_suite':1,'stop_first_failure':True,'provider_posts_authorized':0,
        'source_identity_review':identity,'admitted_specification_drift':drift,
        'provider_scope':'Original registered owned typed loopback fixtures only; actual native VM must map the scoped18770-deny fence; no model service contact or semantic quality claim.',
        'capture_scope':'All original viewport/role/error/capture assertions unchanged. PNG/ARIA stay ignored/private; retain hashes/paths and require root rendered inspection.',
        'tool_closure_scope':'Reuse seven reviewed UI tool roots/top executables; no additional recursive library closure claim.',
        'scope':'Missing exact admitted source40 native9/86 only. Native39 development and final image05 evidence remain separate; no image rerun, historical relabel or release/roadmap closure.'}
    write(work/'plan.json',plan);assert load(work/'run.py','copied_native_ui_driver').verify(plan,work)
    print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],
        'frozen_files':len(plan['frozen_inputs']),'externals':len(externals),'tool_roots':len(tool_roots),'bound_inputs':len(bound)}))


def verify(plan,work):
    driver=Path(__file__).absolute();assert driver==work/'run.py' and driver.resolve()==driver and not driver.is_symlink() and sha(driver)==plan['driver_sha256']
    assert tree(work/'frozen')==plan['frozen_tree'] and {k:v['sha256']for k,v in plan['frozen_tree']['files'].items()}==plan['frozen_inputs']
    assert Path(sys.executable).resolve()==Path(plan['python']).resolve()
    sys.path.insert(0,str(work/'frozen/tests'))
    for name,digest in plan['bound_inputs'].items():assert not(work/name).is_symlink() and sha(work/name)==digest
    for text,row in plan['externals'].items():
        path=Path(text)
        if 'symlink' in row:assert path.is_symlink() and os.readlink(path)==row['symlink']
        else:
            assert path.is_file() and sha(path)==row['sha256']
            if 'resolved' in row:assert str(path.resolve())==row['resolved']
    for root,row in plan['tool_roots'].items():assert tree(Path(root),links=bool(row['links']),external_links=row['external_links'])==row
    assert sha(plan['artifact'])==plan['artifact_sha256'] and plan['runtime_kind']=='native'
    core=load(work/'frozen/tests/native_core_remaining.py','verify_native_ui_cwd')
    assert core.runtime_fixture(work/'frozen')==plan['runtime_fixture']
    reference=json.loads((work/'image05-plan.json').read_text());initial=json.loads((work/'native39-initial-plan.json').read_text())
    assert plan['planned_suites']==list(CASES) and [r['name']for r in plan['jobs']]==list(CASES)
    for original,job in zip(initial['serial_lane'],plan['jobs']):
        name=job['name'];script=next(Path(value).name for value in original['argv']if value.endswith('.py'))
        assert plan['frozen_inputs']['tests/'+script]==reference['frozen_inputs']['tests/'+script]
        expected=native_arguments(original['argv'],work/'frozen/tests'/script,Path(plan['artifact']),work/(name+'.json'),
            Path(plan['openrig_root']) if name=='openrig' else Path(plan['runtime_cwd'])/name,work/'openrig.tgz')
        assert job['test_argv']==expected and job['expected_units']==CASES[name] and job['outer_timeout_seconds']==original['outer_timeout_seconds']
        assert job['foundation_lock']==(original['argv'][1]if original['argv'][0]=='/usr/bin/flock' else None)
    assert plan['expected_units']==86 and plan['automatic_retries']==0 and plan['parallelism']==1
    assert plan['env']['PATH']==plan['qualified_path']
    return True


def execute(work,expected):
    assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
    once=load(work/'frozen/tests/controlled_image_matrix.py','native_ui_durable_once')
    core=load(work/'frozen/tests/native_core_remaining.py','native_ui_nonce_and_cwd')
    runtime=Path(plan['runtime_cwd']);assert not runtime.exists() and not Path(plan['openrig_root']).exists()
    lock=Path(plan['lane_lock']);lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a')as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        once.durable_once_marker(work/'started.json',{'plan_sha256':expected,'driver_sha256':plan['driver_sha256']})
        runtime.mkdir(mode=0o700);core.materialize_runtime_fixture(runtime,work/'frozen',plan['runtime_fixture'])
        tmp=runtime/'tmp';tmp.mkdir(mode=0o700)
        env=dict(os.environ);env.update(plan['env']);env.update(TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1',ERL_FLAGS='+S 2:2',
            LD_PRELOAD=plan['fence_library'],ADHD_RECOVERY_DENY_PROVIDER_PORT='18770',ADHD_RECOVERY_PROVIDER_FENCE_AUDIT=plan['fence_audit'])
        rows=[];failure=None
        try:
            subprocess.run([plan['compiler'],'-shared','-fPIC','-O2','-o',plan['fence_library'],str(work/'frozen/tests/project_recovery_no_provider.c'),'-ldl'],check=True,timeout=30)
            for job in plan['jobs']:
                verify(plan,work);name=job['name'];before=captures(runtime);report=work/(name+'.json');log=work/(name+'.log')
                assert all(not path.exists()for path in [report,log,Path(job['custody_report']),Path(job['launch_ledger']),Path(job['process_ledger'])])
                nonce=expected+':'+name;childenv=dict(env,ADHD_NATIVE_CORE_RUN_NONCE=nonce)
                argv=[plan['python'],'-B',str(work/'frozen/tests/native_ui_runtime.py'),'--plan',str(work/'plan.json'),'--job',name,'--reviewed-plan-sha256',expected]
                if job['foundation_lock']:argv=['/usr/bin/flock',job['foundation_lock'],*argv]
                row={'suite':name,'passed':False,'argv':argv};start=time.monotonic();child=None;print('START',name,flush=True)
                try:
                    with log.open('xb')as output:
                        child=subprocess.Popen(argv,cwd=runtime,env=childenv,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                        try:code=child.wait(timeout=job['outer_timeout_seconds'])
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid,signal.SIGTERM)
                            try:child.wait(timeout=15)
                            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
                            raise RuntimeError('Original outer deadline exceeded')
                    row['exit_code']=code;assert code==0
                    value=json.loads(report.read_text());custody=json.loads(Path(job['custody_report']).read_text())
                    assert value['passed'] and unit_count(value,name)==job['expected_units'] and custody['passed']
                    after=captures(runtime);new={key:value for key,value in after.items()if key not in before}
                    if name not in ['evidence','openrig']:assert new and any('desktop'in key for key in new) and any('mobile'in key for key in new)
                    row.update(passed=True,units=job['expected_units'],report_sha256=sha(report),custody_sha256=sha(job['custody_report']),new_screenshots_and_ARIA=new)
                except BaseException as error:row.update(failure_type=type(error).__name__,failure=str(error))
                finally:
                    if child is not None and child.poll()is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15);row['passed']=False
                    try:
                        unexpected=core.close_nonce_processes(nonce);row['unexpected_live_nonce_processes']=unexpected
                        assert not unexpected;row['owned_nonce_absent']=True
                        ledger=json.loads(Path(job['process_ledger']).read_text())
                        assert all(not item['identity'] or not core.same(item['identity'])for item in ledger['processes'])
                        fence=Path(plan['fence_audit']);assert not fence.exists()or fence.read_bytes()==b''
                    except BaseException as error:row.update(passed=False,cleanup_failure_type=type(error).__name__)
                    row.update(elapsed_seconds=time.monotonic()-start,log_sha256=sha(log));rows.append(row)
                    write(work/'matrix.json',{'passed':False,'status':'RUNNING','rows':rows})
                if not row['passed']:break
                print('PASS',name,flush=True)
        except BaseException as error:failure=type(error).__name__
        finally:
            try:verify(plan,work);unchanged=True
            except BaseException:unchanged=False
            unrun=[name for name in CASES if name not in {row['suite']for row in rows}]
            passed=not failure and unchanged and not unrun and all(row['passed']for row in rows)
            write(work/'matrix.json',{'schema':'adhd/admitted-native-ui-nine-result@1','passed':passed,'plan_sha256':expected,
                'driver_sha256':plan['driver_sha256'],'artifact_sha256':plan['artifact_sha256'],'rows':rows,'unrun_suites':unrun,
                'failure_type':failure,'frozen_inputs_unchanged':unchanged,'manual_rendered_inspection_required':True,'scope':plan['scope']})
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--reviewed-plan-sha256')
    for name in ['repo','context','admission','reference-plan','reference-proof','openrig-root']:parser.add_argument('--'+name,type=Path)
    parser.add_argument('--admission-sha256');args=parser.parse_args()
    if args.prepare:prepare(args)
    else:sys.exit(execute(args.work.absolute(),args.reviewed_plan_sha256))
