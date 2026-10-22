#!/usr/bin/env python3
"""Freeze one public compiler-startup diagnostic; preparation starts nothing."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from controlled_sdk_matrix import tree


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def prepare(a):
 repo=a.repo.absolute();work=a.work.absolute();parent=json.loads(a.parent_plan.read_text());assert parent['planned_suites'][0]=='feedback_sdk'
 reader=load(repo/'tests/image_qualification_inputs.py','diagnostic_inputs');selected=reader.reviewed_payload(a.context/'manifest.json',a.admission,a.admission_sha256,parent['image_config_identity'],parent['artifact_sha256'])
 assert not work.exists();work.mkdir(mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700);inputs,drift=reader.freeze_inputs(repo,frozen,selected['specifications'])
 for name in ['compiler_startup_matrix.py','compiler_startup_runtime.py','compiler_startup_trace.exs','compiler_startup_observer.py','compiler_startup_static.py']:shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
 assert sha(frozen/'tests/feedback_sdk.py')==parent['frozen_inputs']['tests/feedback_sdk.py']
 bound={'image-manifest.json':a.context/'manifest.json','staged-Dockerfile':a.context/'Dockerfile','admission.json':a.admission,'receipt.json':a.admission.parent/'receipt.json','rebuild.json':a.admission.parent/'rebuild.json','provider-fence.so':Path(parent['fence_library'])}
 for name,path in bound.items():assert not path.is_symlink();shutil.copyfile(path,work/name)
 admission=json.loads((work/'admission.json').read_text());assert sha(work/'receipt.json')==admission['files']['receipt.json'] and sha(work/'rebuild.json')==admission['files']['rebuild.json']
 env=json.loads((work/'rebuild.json').read_text());assert env['result']['passed'] and env['result']['receipt_committed'];assert sha(Path(env['result']['artifact']))==parent['artifact_sha256']
 original=parent['jobs'][0];job=copy.deepcopy(original);job['name']='first-feedback-startup';job['test_argv'][0]=str(frozen/'tests/feedback_sdk.py');job['test_argv'][job['test_argv'].index('--report')+1]=str(work/'unreached-sdk-report.json');job['custody_report']=str(work/'diagnostic.json');job['launch_ledger']=str(work/'launches.json');job['trace_snapshot']=str(work/'compiler-prefix.tsv')
 shutil.copyfile(__file__,work/'run.py');externals=dict(parent['externals']);externals[str(a.parent_plan.absolute())]=sha(a.parent_plan)
 for path,digest in externals.items():assert sha(path)==digest
 plan={'schema':'adhd/public-compiler-diagnostic-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','image_config_identity':parent['image_config_identity'],'artifact_sha256':parent['artifact_sha256'],'manifest':str(work/'image-manifest.json'),'canonical_manifest_sha256':sha(work/'image-manifest.json'),'admission_sha256':sha(work/'admission.json'),'staged_dockerfile':str(work/'staged-Dockerfile'),'expected_app_files':59,'specifications':33,'specification_drift':drift,'bound_inputs':{n:sha(work/n) for n in bound},'frozen':str(frozen),'frozen_tree':tree(frozen),'frozen_inputs':tree(frozen)['files'],'externals':externals,'driver_sha256':sha(work/'run.py'),'python':sys.executable,'job':job,'runtime_cwd':str(work/'runtime'),'fence_library':str(work/'provider-fence.so'),'fence_audit':str(work/'provider-fence.audit'),'native_artifact_sha256':parent['native_artifact_sha256'],'path_prefix':parent['path_prefix'],'runs':1,'automatic_retries':0,'real_provider_calls_authorized':0,'sdk_qualification':False,'original_health_deadline_seconds':30,'original_request_timeout_seconds':1,'original_sleep_seconds':0.1,'observer_bound_seconds':18,'maximum_compiler_events':4096,'maximum_trace_bytes_with_header':1048832,'capture_requires_same_open_vm_fd':True,'parent_plan_sha256':sha(a.parent_plan),'scope':'Diagnostic first unchanged Feedback SDK native producer/setup and image adoption only. Exact image/source payload unchanged; public compiler tracer via-r. Original30s health calls unchanged; stop at first image observation even if Ready. No SDKcase or performancefix qualification.'}
 write(work/'plan.json',plan);load(work/'run.py','copied_compiler_driver').verify(plan,work);print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen_inputs']),'externals':len(externals),'bound_inputs':len(bound)}))


def verify(plan,work):
 actual=Path(__file__);assert actual.absolute()==work/'run.py' and actual.resolve()==actual.absolute() and not actual.is_symlink() and sha(actual)==plan['driver_sha256']
 assert tree(work/'frozen')==plan['frozen_tree'] and plan['frozen_tree']['files']==plan['frozen_inputs']
 for name,digest in plan['bound_inputs'].items():assert not(work/name).is_symlink() and sha(work/name)==digest
 for name,digest in plan['externals'].items():assert not Path(name).is_symlink() and sha(name)==digest
 assert plan['runs']==1 and plan['automatic_retries']==0 and plan['real_provider_calls_authorized']==0 and plan['sdk_qualification'] is False
 assert plan['original_health_deadline_seconds']==30 and plan['original_request_timeout_seconds']==1 and plan['original_sleep_seconds']==0.1
 return True


def execute(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work);helper=load(work/'frozen/tests/controlled_image_matrix.py','diagnostic_cleanup');root=Path(plan['runtime_cwd']);assert not root.exists()
 helper.durable_once_marker(work/'started.json',{'plan_sha256':expected,'started_at':time.time()});root.mkdir(mode=0o700)
 env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',ERL_FLAGS='+S 2:2',LD_PRELOAD=plan['fence_library'],ADHD_RECOVERY_DENY_PROVIDER_PORT='18770',ADHD_RECOVERY_PROVIDER_FENCE_AUDIT=plan['fence_audit']);env['PATH']=plan['path_prefix']+':'+env['PATH']
 argv=[plan['python'],'-B',str(work/'frozen/tests/compiler_startup_runtime.py'),'--plan',str(work/'plan.json'),'--reviewed-plan-sha256',expected];process=None;code=None;failure=None;cleanup=[];cleanup_failure=None
 try:
  with (work/'diagnostic.log').open('x') as stream:
   process=subprocess.Popen(argv,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
   try:code=process.wait(timeout=plan['job']['timeout_seconds'])
   except subprocess.TimeoutExpired:
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
    raise
 except BaseException as error:failure=type(error).__name__
 finally:
  if process is not None and process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
  try:cleanup=helper.cleanup_ledger(plan['job'],plan)
  except BaseException as error:cleanup_failure=type(error).__name__
  try:verify(plan,work);unchanged=True
  except BaseException:unchanged=False
  diagnostic=Path(plan['job']['custody_report']);value=json.loads(diagnostic.read_text()) if diagnostic.exists() else None
  blocked=Path(plan['fence_audit']);provider_denied=blocked.read_text().splitlines() if blocked.exists() else []
  observed=code==0 and not failure and not cleanup_failure and unchanged and not provider_denied and value and value['diagnostic_observation_complete']
  write(work/'result.json',{'schema':'adhd/public-compiler-diagnostic-result@1','diagnostic_observation_complete':bool(observed),'sdk_qualified':False,'plan_sha256':expected,'driver_sha256':plan['driver_sha256'],'exit_code':code,'failure_type':failure,'cleanup_failure_type':cleanup_failure,'cleanup':cleanup,'full_inputs_unchanged':unchanged,'blocked_real_provider_connects':len(provider_denied),'log_sha256':sha(work/'diagnostic.log'),'diagnostic_sha256':sha(diagnostic) if diagnostic.exists() else None,'scope':plan['scope']})
 return 0 if observed else 1

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true');p.add_argument('--work',type=Path,required=True);p.add_argument('--reviewed-plan-sha256')
 for name in ['repo','context','admission','parent-plan']:p.add_argument('--'+name,type=Path)
 p.add_argument('--admission-sha256');a=p.parse_args()
 if a.prepare:prepare(a)
 else:sys.exit(execute(a.work.absolute(),a.reviewed_plan_sha256))
