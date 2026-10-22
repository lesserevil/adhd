"""Prepare then explicitly run the five original callback scenarios on an admitted compiled image.

Preparation never starts Docker, a hub, compiler, model or broker. Execution is
serial, once-only and fail-first; the five original entrypoints stay byte exact.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
sys.dont_write_bytecode=True
CASES={'pending_model':4,'pending_kafka':5,'queries':8,'incoming':7,'peer_epoch':4}
PEERS={'queries','incoming','peer_epoch'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def runtime_proof(value,plan,name):
    runtimes=[v for k,v in value.items() if k=='runtime' or k.startswith('runtime_')]
    assert len(runtimes)==(2 if name in PEERS else 1),'Each actual origin/peer runtime must be bound'
    identities=[]
    for runtime in runtimes:
        assert runtime['kind']=='docker' and runtime['payload_verified'] is True
        assert runtime['image_config_identity']==plan['image_config_identity']
        assert runtime['artifact_sha256']==plan['artifact_sha256'] and runtime['canonical_manifest_sha256']==plan['canonical_manifest_sha256']
        assert runtime['observer_sha256']==plan['bound_inputs']['compiled-observer.exs']
        assert runtime['owned_container_absent'] and runtime['owned_docker_client_exited'] and not runtime['cleanup_failure_types']
        assert runtime['startup_seconds']==(150 if name in PEERS else 45)
        observations=runtime['watched_vm_observations'];assert observations
        started={v['container_id'] for v in runtime['container_lifecycle'] if v['action']=='started'}
        stopped={v['container_id'] for v in runtime['container_lifecycle'] if v.get('observed_absent') is True}
        assert started and started<=stopped
        assert all(v['image_config_identity']==plan['image_config_identity'] and v['namespace_vm_pid']==1 for v in observations)
        identities.append(started)
        assert runtime['payload_probe_lifecycle'] and all(v['observed_absent'] for v in runtime['payload_probe_lifecycle'])
    if name in PEERS:assert identities[0].isdisjoint(identities[1]),'Origin/peer runtime identity alias'


def prepare(args):
    repo=args.repo.absolute();work=args.work.absolute();assert repo.resolve()==repo and not work.exists()
    assert sha(args.admission)==args.admission_sha256
    admission=json.loads(args.admission.read_text());image=admission['image_config_identity'];artifact=admission['artifact_sha256']
    reader=load(repo/'tests/image_qualification_inputs.py','callback_reviewed_inputs')
    selected=reader.reviewed_payload(args.context/'manifest.json',args.admission,args.admission_sha256,image,artifact)
    cache=load(repo/'tests/controlled_sdk_matrix.py','callback_reviewed_cache').compiled_cache_binding(
        args.compiled_cache_manifest,admission,image,artifact,sha(args.context/'manifest.json'))
    original=json.loads(args.original_plan.read_text());original_result=json.loads(args.original_manifest.read_text())
    assert original_result['passed'] and original_result['groups']==CASES and original_result['total_groups']==28
    assert original_result['plan_sha256']==sha(args.original_plan) and original['order']==list(CASES)
    abi=json.loads(args.abi_audit.read_text());assert abi['passed'] and abi['actual_cases']==19
    assert abi['image']==image and abi['artifact_sha256']==artifact and abi['canonical_manifest_sha256']==sha(args.context/'manifest.json')
    work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
    inputs,drift=reader.freeze_inputs(repo,frozen,selected['specifications'])
    for name in ['recovery_callback_matrix.py','recovery_compiled_callbacks.py','recovery_callback_static.py']:
        shutil.copyfile(Path(__file__).with_name(name),frozen/'tests'/name)
    for name in CASES:
        relative='tests/project_recovery_'+name+'.py'
        assert sha(frozen/relative)==original['frozen_inputs'][relative],'Original scenario changed; review required before adaptation'
    bindings={'image-manifest.json':args.context/'manifest.json','staged-Dockerfile':args.context/'Dockerfile',
        'admission.json':args.admission,'receipt.json':args.admission.parent/'receipt.json','rebuild.json':args.admission.parent/'rebuild.json',
        'cache-manifest.json':args.compiled_cache_manifest,'cache-metadata.json':args.compiled_cache_manifest.with_name('cache-metadata.json'),
        'original-plan.json':args.original_plan,'original-manifest.json':args.original_manifest,'abi-audit.json':args.abi_audit}
    for name,path in bindings.items():
        assert path.absolute()==path.resolve() and not path.is_symlink();shutil.copyfile(path,work/name)
    assert all(sha(work/name)==admission['files'][name] for name in ['receipt.json','rebuild.json'])
    envelope=json.loads((work/'rebuild.json').read_text());result=envelope['result'];artifact_path=Path(result['artifact'])
    assert result['passed'] and result['receipt_committed'] and sha(artifact_path)==artifact
    sys.path.insert(0,str(frozen/'tests'))
    adapter=load(frozen/'tests/recovery_compiled_callbacks.py','reviewed_callback_adapter')
    observer=frozen/'tests/project_recovery_live_loss.exs'
    (work/'compiled-observer.exs').write_text(adapter.compiled_observer(observer.read_text()))
    bindings['compiled-observer.exs']=work/'compiled-observer.exs'
    runtime=work/'runtime';jobs=[]
    for name,count in CASES.items():
        argv=[str(frozen/'tests'/('project_recovery_'+name+'.py')),'--image',image,'--image-manifest',str(work/'image-manifest.json'),
            '--eventing-rest-url',args.eventing_rest_url,'--keep-work',str(runtime/('fixture-'+name)),
            '--report',str(work/(name+'.json')),'--recovery-schema',str(frozen/'components/hub/project-recovery/interface.schema.json')]
        if name in PEERS:argv+=['--loss-runner',str(observer)]
        if name in ('queries','incoming'):argv+=['--peer-eventing-rest-url',args.peer_eventing_rest_url]
        old=next(v['argv'] for v in original['jobs'] if v['name']==name)
        assert argv[1::2]==old[2::2],'Original flag order/coverage changed'
        jobs.append({'name':name,'expected_groups':count,'test_argv':argv,'custody_report':str(work/(name+'-custody.json')),
            'launch_ledger':str(work/(name+'-launches.json'))})
    shutil.copyfile(__file__,work/'run.py')
    tree=load(repo/'tests/controlled_sdk_matrix.py','callback_closed_tree').tree
    docker=Path('/usr/bin/docker');assert docker.resolve()==docker
    python=Path(sys.executable);qualified_path='/usr/bin:/bin'
    plan={'schema':'adhd/recovery-compiled-callback-five-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED',
        'image_config_identity':image,'artifact_sha256':artifact,'canonical_manifest_sha256':sha(work/'image-manifest.json'),
        'admission_sha256':args.admission_sha256,'compiled_cache':cache,'manifest':str(work/'image-manifest.json'),
        'frozen':str(frozen),'frozen_tree':tree(frozen),'frozen_inputs':tree(frozen)['files'],
        'bound_inputs':{name:sha(work/name) for name in bindings},
        'externals':{str(path):sha(path) for path in [docker,python.resolve(),artifact_path]},
        'driver_sha256':sha(work/'run.py'),'native_observer_sha256':sha(observer),
        'python':str(python),'docker':{'path':str(docker),'sha256':sha(docker)},'qualified_path':qualified_path,
        'admitted_specification_drift':drift,'jobs':jobs,'planned_suites':list(CASES),'expected_groups':28,
        'runtime_cwd':str(runtime),'parallelism':1,'maximum_owned_hubs':2,'automatic_retries':0,'stop_first_failure':True,
        'external_provider_calls':0,'original_deadlines':'Unchanged45s callbacks/150s peers/20s Kafka settle and accepted TTLs',
        'eventing_profile':{'global_concurrency':16,'project_eventing_concurrency':2},
        'expected_app_files':selected['audit']['actual_app_files'],'specifications':len(selected['specifications']),
        'abi_scope':'Bound actual final-image19 ABI proof; these five scenarios use the original Elixir Store-loss watcher, no C rename library.',
        'provider_scope':'All model URLs audited to registered owned loopback fixtures, excluding18770; no claim of an image network/firewall fence.',
        'scope':'Five unchanged real callback/transport suites on actual admitted image and instrumented real compiled boot, not default OCI startup, native52 or whole-roadmap closure.'}
    write(work/'plan.json',plan);load(work/'run.py','copied_callback_driver').verify(plan,work)
    print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],
        'frozen_files':len(plan['frozen_inputs']),'bound_inputs':len(plan['bound_inputs'])}))


def verify(plan,work):
    driver=Path(__file__).absolute();assert driver==work/'run.py' and driver.resolve()==driver and not driver.is_symlink()
    assert sha(driver)==plan['driver_sha256']
    reader=load(work/'frozen/tests/image_qualification_inputs.py','verify_callback_tree')
    assert reader.verify_frozen_inputs(work/'frozen',plan['frozen_inputs'])
    sys.path.insert(0,str(work/'frozen/tests'))
    assert load(work/'frozen/tests/controlled_sdk_matrix.py','verify_callback_tree_shape').tree(work/'frozen')==plan['frozen_tree']
    for name,digest in plan['bound_inputs'].items():assert not (work/name).is_symlink() and sha(work/name)==digest
    for path,digest in plan['externals'].items():assert Path(path).resolve()==Path(path) and sha(path)==digest
    assert sha(plan['docker']['path'])==plan['docker']['sha256'] and shutil.which('docker',path=plan['qualified_path'])==plan['docker']['path']
    assert Path(sys.executable).resolve()==Path(plan['python']).resolve()
    assert plan['planned_suites']==list(CASES) and [v['name'] for v in plan['jobs']]==list(CASES)
    assert [v['expected_groups'] for v in plan['jobs']]==list(CASES.values()) and plan['expected_groups']==28
    original=json.loads((work/'original-plan.json').read_text())
    for name in CASES:
        relative='tests/project_recovery_'+name+'.py';assert plan['frozen_inputs'][relative]==original['frozen_inputs'][relative]
    module=load(work/'frozen/tests/recovery_compiled_callbacks.py','verify_callback_observer')
    assert (work/'compiled-observer.exs').read_text()==module.compiled_observer((work/'frozen/tests/project_recovery_live_loss.exs').read_text())
    assert plan['automatic_retries']==0 and plan['parallelism']==1 and plan['maximum_owned_hubs']==2
    return True


def execute(work,expected):
    assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
    marker=load(work/'frozen/tests/controlled_image_matrix.py','callback_once')
    cleanup=load(work/'frozen/tests/image_ui_matrix.py','callback_cleanup')
    runtime=Path(plan['runtime_cwd']);assert not runtime.exists()
    marker.durable_once_marker(work/'started.json',{'plan_sha256':expected,'started_at':time.time()});runtime.mkdir(mode=0o700)
    env=dict(os.environ);env.update(PATH=plan['qualified_path'],ERL_FLAGS='+S 2:2',PYTHONDONTWRITEBYTECODE='1')
    rows=[];failure=None
    try:
        for job in plan['jobs']:
            verify(plan,work);name=job['name'];report=work/(name+'.json');log=work/(name+'.log')
            assert all(not p.exists() for p in [report,log,Path(job['custody_report']),Path(job['launch_ledger'])])
            argv=[plan['python'],'-B',str(work/'frozen/tests/recovery_compiled_callbacks.py'),'--plan',str(work/'plan.json'),
                '--job',name,'--reviewed-plan-sha256',expected]
            row={'suite':name,'argv':argv,'passed':False};start=time.monotonic();print('START',name,flush=True)
            try:
                with log.open('xb') as output:child=subprocess.run(argv,cwd=runtime,env=env,stdout=output,stderr=subprocess.STDOUT)
                row['exit_code']=child.returncode
                assert child.returncode==0
                value=json.loads(report.read_text());assert value['passed'] and len(value['checks'])==job['expected_groups']
                runtime_proof(value,plan,name)
                custody=json.loads(Path(job['custody_report']).read_text());assert custody['passed']
                row['passed']=True
            except BaseException as error:row.update(failure_type=type(error).__name__,failure=str(error))
            finally:
                try:
                    row['independent_cleanup']=cleanup.cleanup_ledger(work,job,plan)
                    assert not row['independent_cleanup']['errors'] and not row['independent_cleanup']['fallback_mutation']
                except BaseException as error:row.update(passed=False,cleanup_failure_type=type(error).__name__)
                row.update(elapsed_seconds=time.monotonic()-start,log_sha256=sha(log),report_sha256=sha(report) if report.exists() else None,
                    custody_sha256=sha(job['custody_report']) if Path(job['custody_report']).exists() else None)
                rows.append(row);write(work/'matrix.json',{'passed':False,'status':'RUNNING','rows':rows})
            if not row['passed']:break
            print('PASS',name,flush=True)
    except BaseException as error:failure=type(error).__name__
    finally:
        try:verify(plan,work);unchanged=True
        except BaseException:unchanged=False
        unrun=[name for name in CASES if name not in {v['suite'] for v in rows}]
        passed=not failure and unchanged and not unrun and all(row['passed'] for row in rows)
        write(work/'matrix.json',{'schema':'adhd/recovery-compiled-callback-five-result@1','passed':passed,'plan_sha256':expected,
            'driver_sha256':plan['driver_sha256'],'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],
            'rows':rows,'unrun_suites':unrun,'frozen_inputs_unchanged':unchanged,'failure_type':failure,'scope':plan['scope']})
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--reviewed-plan-sha256')
    for name in ['repo','context','admission','compiled-cache-manifest','original-plan','original-manifest','abi-audit']:
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--admission-sha256');parser.add_argument('--eventing-rest-url',default='http://127.0.0.1:18082')
    parser.add_argument('--peer-eventing-rest-url',default='http://127.0.0.1:18085');args=parser.parse_args()
    if args.prepare:prepare(args)
    else:sys.exit(execute(args.work.absolute(),args.reviewed_plan_sha256))
