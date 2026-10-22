#!/usr/bin/env python3
"""Freeze, then explicitly execute one serial five-suite recovery image plan."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime,timezone

IMAGE='sha256:b12e75c09ccd213f06739f7fdd998d675670491c31677143fecaceab7823e0f0'
ARTIFACT='1741225b1a276770ec9f6631e63fe8646ee5f22808fad8a5acfe67a8aed11bd7'
MANIFEST='dce8d0923d530c01cd38d9ce7c6700e838fd79f2f7bb5e50989b311118aadac4'
ADMISSION='2526ad178e88239704f62b9d7437b98c3f4baca71ee9a82b84e635b242896d58'
NAMES=['pending_model','pending_kafka','queries','incoming','peer_epoch']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n');path.chmod(0o600)


def prepare(repo,work):
    assert not work.exists(),'Fresh plan directory required'
    work.mkdir(parents=True,mode=0o700);work.chmod(0o700)
    frozen=work/'frozen';frozen.mkdir(mode=0o700);inputs={}
    for subtree in ['tests','components','scripts']:
        for source in sorted((repo/subtree).rglob('*')):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix not in ['.py','.c','.exs','.json','.md','.sh']:continue
            assert not source.is_symlink()
            relative=source.relative_to(repo);target=frozen/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);inputs[str(relative)]=sha(target)
    for source,name,expected in [
        (repo/'_build/roadmap/final/container-context-38/manifest.json','image-manifest.json',MANIFEST),
        (repo/'verification/project-recovery/development38/admission/manifest.json','admission.json',ADMISSION)]:
        assert sha(source)==expected;shutil.copyfile(source,work/name)
    adm=json.loads((work/'admission.json').read_text())
    assert adm['passed'] and adm['receipt_committed'] and adm['artifact_sha256']==ARTIFACT
    assert adm['image_config_identity']==IMAGE and adm['canonical_manifest_sha256']==MANIFEST
    assert adm['payload_audit']['passed'] and adm['payload_audit']['actual_app_files']==59
    assert adm['payload_audit']['canonical_specifications']==33
    for source,name,expected in [
        (repo/adm['official_rebuild_envelope']['path'],'rebuild.json',adm['official_rebuild_envelope']['sha256']),
        (repo/'verification/current.json','receipt.json',adm['receipt_file_sha256'])]:
        assert sha(source)==expected;shutil.copyfile(source,work/name)
    manifest=json.loads((work/'image-manifest.json').read_text())
    assert manifest['files']['hub.exs']==ARTIFACT
    specification_drift={}
    for path,digest in manifest['files'].items():
        if path.startswith('specification/'):
            relative=Path('components/hub')/path.removeprefix('specification/')
            original=sha(frozen/relative)
            if original!=digest:specification_drift[str(relative)]={'current_root_sha256':original,'admitted38_sha256':digest}
            with tarfile.open(repo/'_build/roadmap/final/container-context-38/payload.tar') as archive:
                member=archive.getmember('app/'+path)
                assert member.isfile()
                raw=archive.extractfile(member).read()
            assert hashlib.sha256(raw).hexdigest()==digest,path
            (frozen/relative).write_bytes(raw);inputs[str(relative)]=digest
    shutil.copyfile(Path(__file__),work/'driver.py')
    jobs=[]
    for name in NAMES:
        script=frozen/'tests'/('project_recovery_'+name+'.py')
        argv=[sys.executable,str(script),'--image',IMAGE,'--image-manifest',str(work/'image-manifest.json'),
            '--eventing-rest-url','http://127.0.0.1:18082','--keep-work',str(work/('fixture-'+name)),
            '--report',str(work/(name+'.json')),'--recovery-schema',str(frozen/'components/hub/project-recovery/interface.schema.json')]
        if name in ['queries','incoming','peer_epoch']:
            argv+=['--loss-runner',str(frozen/'tests/project_recovery_live_loss.exs')]
        if name in ['queries','incoming']:argv+=['--peer-eventing-rest-url','http://127.0.0.1:18085']
        jobs.append({'name':name,'argv':argv})
    plan={'schema':'adhd/recovery-image-five-plan@1','prepared_at':now(),'status':'REVIEW_REQUIRED_NOT_STARTED',
        'image_config_identity':IMAGE,'artifact_sha256':ARTIFACT,'canonical_manifest_sha256':MANIFEST,'admission_sha256':ADMISSION,
        'driver_sha256':sha(work/'driver.py'),'python':sys.executable,'frozen_inputs':inputs,
        'specification_source':'Exact manifest-verified admitted38 staging specification/ bytes; current root test helpers unchanged.',
        'current_root_specification_drift':specification_drift,
        'bound_inputs':{name:sha(work/name) for name in ['image-manifest.json','admission.json','rebuild.json','receipt.json']},
        'order':NAMES,'parallelism':1,'maximum_owned_hubs':2,'runs_per_suite':1,'stop_first_failure':True,'automatic_retries':0,
        'external_provider_calls':0,'budgets':'All existing default deadlines, relay holds, query TTLs,150s peer/45s callback readiness unchanged; no --deadline override.',
        'scope':'Full existing image callback/outgoing/incoming(including revocation)/catalog scenarios; controlled local HTTP only, distinct existing brokers, no provider/model-service mutation.',
        'jobs':jobs}
    write(work/'plan.json',plan)
    print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':sha(work/'driver.py'),'jobs':jobs},indent=2))


def verify(plan,work):
    assert all(sha(work/'frozen'/p)==digest for p,digest in plan['frozen_inputs'].items())
    assert all(sha(work/p)==digest for p,digest in plan['bound_inputs'].items())


def runtime_proof(report,plan):
    runtimes=[v for k,v in report.items() if k=='runtime' or k.startswith('runtime_')]
    assert runtimes
    for runtime in runtimes:
        assert runtime['kind']=='docker' and runtime['image_config_identity']==IMAGE
        assert runtime['artifact_sha256']==ARTIFACT and runtime['canonical_manifest_sha256']==MANIFEST
        assert runtime['owned_container_absent'] is True and runtime['owned_docker_client_exited'] is True
        assert not runtime['cleanup_failure_types'] and runtime['watched_vm_observations']
        events=runtime['container_lifecycle'];started={v['container_id'] for v in events if v['action']=='started'}
        stopped={v['container_id'] for v in events if v.get('observed_absent') is True}
        assert started and started<=stopped
        assert runtime['payload_probe_lifecycle'] and all(v['observed_absent'] for v in runtime['payload_probe_lifecycle'])


def execute(work,expected_plan,expected_driver):
    assert sha(work/'plan.json')==expected_plan and sha(Path(__file__))==expected_driver
    plan=json.loads((work/'plan.json').read_text());assert plan['driver_sha256']==expected_driver
    verify(plan,work)
    with (work/'execution-started.json').open('x') as marker:json.dump({'started_at':now(),'plan_sha256':expected_plan},marker)
    results=[];failure=None
    env=os.environ.copy();env['PYTHONPATH']=str(work/'frozen/tests');env['PYTHONDONTWRITEBYTECODE']='1'
    try:
        for job in plan['jobs']:
            verify(plan,work);name=job['name'];log=work/(name+'.log');report=work/(name+'.json')
            assert not log.exists() and not report.exists() and not (work/('fixture-'+name)).exists()
            print('START',name,flush=True)
            with log.open('x') as output:
                child=subprocess.run(job['argv'],cwd=work/'frozen',env=env,stdout=output,stderr=subprocess.STDOUT)
            row={'name':name,'exit_code':child.returncode,'report':str(report),'report_sha256':sha(report) if report.exists() else None,'log_sha256':sha(log),'passed':False}
            results.append(row)
            if child.returncode:break
            value=json.loads(report.read_text());assert value['passed'] is True
            runtime_proof(value,plan);row['passed']=True
            print('DONE',name,child.returncode,flush=True)
    except BaseException as error:failure=type(error).__name__
    finally:
        try:verify(plan,work);unchanged=True
        except BaseException:unchanged=False
        unrun=[name for name in NAMES if name not in {v['name'] for v in results}]
        passed=not failure and unchanged and not unrun and all(v['passed'] for v in results)
        write(work/'matrix.json',{'schema':'adhd/recovery-image-five-matrix@1','passed':passed,'finished_at':now(),
            'plan_sha256':expected_plan,'driver_sha256':expected_driver,'image_config_identity':IMAGE,'artifact_sha256':ARTIFACT,
            'admission_sha256':ADMISSION,'frozen_inputs_unchanged':unchanged,'planned_suites':NAMES,
            'executed_suites':[v['name'] for v in results],'unrun_suites':unrun,'failure_type':failure,'results':results})
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--repo',type=Path);parser.add_argument('--expected-plan-sha256');parser.add_argument('--expected-driver-sha256')
    args=parser.parse_args();work=args.work.resolve()
    if args.prepare:prepare(args.repo.resolve(),work)
    else:sys.exit(execute(work,args.expected_plan_sha256,args.expected_driver_sha256))
