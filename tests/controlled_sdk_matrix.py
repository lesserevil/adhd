#!/usr/bin/env python3
"""Prepare/review the four unchanged SDK ladders on an explicit admitted image.

No preparation branch starts a compiler, runtime, model or Docker probe. The
original image38 false aggregate/prefix is historical evidence, never relabeled.
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
CASES={'feedback_sdk':5,'archive_sdk':4,'history_sdk':4,'retrieval_sdk':4}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def tree(root):
 assert root.is_absolute() and root.resolve()==root and root.is_dir() and not root.is_symlink()
 files={};directories=[]
 for path in sorted(root.rglob('*')):
  info=path.lstat();assert not stat.S_ISLNK(info.st_mode)
  if stat.S_ISDIR(info.st_mode):directories.append(str(path.relative_to(root)))
  else:
   assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
   files[str(path.relative_to(root))]=sha(path)
 return {'files':files,'directories':directories}


def prepare(a):
 repo=a.repo.absolute();work=a.work.absolute();assert repo.resolve()==repo and not work.exists()
 assert sha(a.admission)==a.admission_sha256
 admission=json.loads(a.admission.read_text());image=admission['image_config_identity'];artifact_hash=admission['artifact_sha256']
 reader=load(repo/'tests/image_qualification_inputs.py','reviewed_sdk_inputs')
 selected=reader.reviewed_payload(a.context/'manifest.json',a.admission,a.admission_sha256,image,artifact_hash)
 work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
 for part in ['tests','scripts']:
  for path in (repo/part).rglob('*'):
   if '__pycache__' not in path.parts:assert not path.is_symlink()
 inputs,drift=reader.freeze_inputs(repo,frozen,selected['specifications'])
 for name in ['controlled_sdk_matrix.py','controlled_sdk_runtime.py','controlled_sdk_static.py']:
  shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
 bindings={'image-manifest.json':a.context/'manifest.json','staged-Dockerfile':a.context/'Dockerfile','admission.json':a.admission,
  'receipt.json':a.admission.parent/'receipt.json','rebuild.json':a.admission.parent/'rebuild.json'}
 for name,path in bindings.items():assert path.resolve()==path.absolute() and not path.is_symlink();shutil.copyfile(path,work/name)
 assert all(sha(work/name)==admission['files'][name] for name in ['receipt.json','rebuild.json'])
 envelope=json.loads((work/'rebuild.json').read_text());result=envelope['result'];artifact=Path(result['artifact'])
 assert result['passed'] and result['receipt_committed'] and sha(artifact)==artifact_hash
 parent=json.loads(a.parent_plan.read_text());parent_matrix=json.loads(a.parent_matrix.read_text())
 assert parent_matrix['passed'] is False and [row['suite'] for row in parent_matrix['rows'][:11]]==parent['planned_suites'][:11]
 assert all(row['passed'] for row in parent_matrix['rows'][:11]) and parent_matrix['rows'][11]['suite']=='feedback_sdk' and not parent_matrix['rows'][11]['passed']
 assert [name for name in parent['planned_suites'] if name in CASES]==list(CASES)
 externals={str(a.parent_plan.absolute()):sha(a.parent_plan),str(a.parent_matrix.absolute()):sha(a.parent_matrix),str(artifact):artifact_hash}
 jobs=[];producers=set();runtime=work/'runtime'
 for name,count in CASES.items():
  original=next(v for v in parent['jobs'] if v['name']==name)
  assert original['expected_groups']==count and sha(frozen/'tests'/f'{name}.py')==parent['frozen_inputs']['tests/'+name+'.py']
  native=json.loads(original['test_argv'][original['test_argv'].index('--command')+1]);elixir=Path(native[0])
  argv=[str(frozen/'tests'/f'{name}.py'),'--image',image,'--report',str(work/(name+'.json')),'--command',json.dumps([str(elixir),str(artifact)])]
  historical=[]
  for index,value in enumerate(original['test_argv']):
   if value=='--legacy-command':
    command=json.loads(original['test_argv'][index+1]);assert Path(command[0])==elixir
    path=Path(command[-1]);assert sha(path)==parent['externals'][str(path)];producers.add(path);historical.append(sha(path));argv+=['--legacy-command',json.dumps(command)]
  assert len(historical)==(4 if name=='feedback_sdk' else 3)
  jobs.append({'name':name,'expected_groups':count,'test_argv':argv,'custody_report':str(work/(name+'-custody.json')),
    'launch_ledger':str(work/(name+'-launches.json')),'timeout_seconds':original['timeout_seconds'],'historical_producer_sha256':historical})
 for path in producers:externals[str(path)]=sha(path)
 for path in [Path(sys.executable).resolve(),elixir.resolve(),Path(shutil.which('cc')).resolve(),*list((repo/'_build/federation/native/erlang').glob('erts-*/bin/beam.smp'))]:externals[str(path)]=sha(path)
 tools={label:{'path':str(path.absolute()),'resolved':str(path.resolve()),'sha256':sha(path.resolve())} for label,path in [('python',Path(sys.executable)),('elixir',elixir),('compiler',Path(shutil.which('cc')))]}
 shutil.copyfile(__file__,work/'run.py')
 plan={'schema':'adhd/controlled-sdk-image-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','image_config_identity':image,'artifact_sha256':artifact_hash,
  'canonical_manifest_sha256':sha(work/'image-manifest.json'),'admission_sha256':a.admission_sha256,'actual_formal_native_export':str(artifact),
  'frozen':str(frozen),'frozen_tree':tree(frozen),'frozen_inputs':tree(frozen)['files'],'externals':externals,
  'bound_inputs':{name:sha(work/name) for name in bindings},'driver_sha256':sha(work/'run.py'),'root_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
  'admitted_specification_drift':drift,'manifest':str(work/'image-manifest.json'),'staged_dockerfile':str(work/'staged-Dockerfile'),
  'expected_app_files':selected['audit']['actual_app_files'],'specifications':len(selected['specifications']),
  'native_artifact_sha256':[artifact_hash]+sorted(sha(path) for path in producers),'jobs':jobs,'planned_suites':list(CASES),'expected_groups':17,
  'tools':tools,'python':sys.executable,'compiler':str(Path(shutil.which('cc')).resolve()),'runtime_cwd':str(runtime),'fence_library':str(work/'provider-fence.so'),'fence_audit':str(work/'provider-fence.audit'),
  'path_prefix':parent['path_prefix'],'runs_per_suite':1,'automatic_retries':0,'parallelism':1,'maximum_owned_hubs':2,'stop_first_failure':True,
  'original_readiness_seconds':30,'health_observation':{'calls':'Only unchanged original Hub.start direct health calls','maximum_rows':512,'maximum_body_prefix_bytes':1024,'extra_health_requests':0,'request_timeout_seconds':1,'original_sleep_seconds':0.1},'startup_failure_diagnostic_collection_seconds':15,'startup_failure_diagnostic_reap_grace_seconds':3,'maximum_startup_failure_diagnostic_seconds':18,'parent_false_matrix_sha256':sha(a.parent_matrix),'historical_whole_prefix_groups':100,
  'provider_scope':parent['provider_scope'],'scope':'Explicit current admitted image SDK17 only. Original11-suite image38 prefix100 remains historical, source38 aggregate remains false. No single-artifact117, native full matrix or release claim.'}
 write(work/'plan.json',plan);load(work/'run.py','copied_sdk_driver').verify(plan,work)
 print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen_inputs']),'externals':len(externals),'bound_inputs':len(bindings)}))


def verify(plan,work):
 driver=Path(__file__);assert driver.absolute()==work/'run.py' and driver.resolve()==driver.absolute()
 info=driver.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and sha(driver)==plan['driver_sha256']
 assert tree(work/'frozen')==plan['frozen_tree'] and plan['frozen_inputs']==plan['frozen_tree']['files']
 for path,digest in plan['externals'].items():assert not Path(path).is_symlink() and sha(path)==digest
 for path,digest in plan['bound_inputs'].items():assert not (work/path).is_symlink() and sha(work/path)==digest
 assert plan['planned_suites']==list(CASES) and [v['name'] for v in plan['jobs']]==list(CASES)
 assert [v['expected_groups'] for v in plan['jobs']]==list(CASES.values()) and plan['original_readiness_seconds']==30
 for row in plan['tools'].values():assert str(Path(row['path']).resolve())==row['resolved'] and sha(row['resolved'])==row['sha256']
 assert plan['expected_groups']==17 and plan['automatic_retries']==0 and plan['parallelism']==1
 return True


def execute(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
 helper=load(work/'frozen/tests/controlled_image_matrix.py','reviewed_sdk_execution_helpers')
 assert not Path(plan['runtime_cwd']).exists();helper.durable_once_marker(work/'started.json',{'plan_sha256':expected,'started_at':time.time()})
 Path(plan['runtime_cwd']).mkdir(mode=0o700);env=dict(os.environ);env['PATH']=plan['path_prefix']+':'+env['PATH'];env['PYTHONDONTWRITEBYTECODE']='1'
 env['LD_PRELOAD']=plan['fence_library'];env['ADHD_RECOVERY_DENY_PROVIDER_PORT']='18770';env['ADHD_RECOVERY_PROVIDER_FENCE_AUDIT']=plan['fence_audit'];env['ERL_FLAGS']='+S 2:2'
 rows=[];failure=None
 try:
  subprocess.run([plan['compiler'],'-shared','-fPIC','-O2','-o',plan['fence_library'],str(work/'frozen/tests/project_recovery_no_provider.c'),'-ldl'],check=True,timeout=30)
  for job in plan['jobs']:
   verify(plan,work);name=job['name'];report=work/(name+'.json');log=work/(name+'.log')
   assert all(not path.exists() for path in [report,log,Path(job['custody_report']),Path(job['launch_ledger'])])
   argv=[plan['python'],'-B',str(work/'frozen/tests/controlled_sdk_runtime.py'),'--plan',str(work/'plan.json'),'--job',name,'--reviewed-plan-sha256',expected]
   print('START',name,flush=True);began=time.monotonic();cleanup=[];code=None;child_error=None;cleanup_error=None
   try:
    with log.open('x') as output:child=subprocess.run(argv,cwd=plan['runtime_cwd'],env=env,stdout=output,stderr=subprocess.STDOUT,timeout=job['timeout_seconds'])
    code=child.returncode
   except BaseException as error:child_error=type(error).__name__
   finally:
    try:cleanup=helper.cleanup_ledger(job,plan)
    except BaseException as error:cleanup_error=type(error).__name__
   row={'suite':name,'argv':argv,'exit_code':code,'failure_type':child_error,'cleanup_failure_type':cleanup_error,'cleanup':cleanup,'passed':False,'elapsed_seconds':time.monotonic()-began,
    'log_sha256':sha(log),'report_sha256':sha(report) if report.exists() else None,'custody_report_sha256':sha(job['custody_report']) if Path(job['custody_report']).exists() else None};rows.append(row)
   if code!=0 or child_error or cleanup_error:break
   value=json.loads(report.read_text());custody=json.loads(Path(job['custody_report']).read_text())
   assert value['passed'] and len(value['cases'])==job['expected_groups']
   assert custody['passed'] and not custody['blocked_provider_connects'] and not custody['cleanup_failure_types']
   row['passed']=True;write(work/'matrix.json',{'passed':False,'status':'RUNNING','rows':rows});print('PASS',name,flush=True)
 except BaseException as error:failure=type(error).__name__
 finally:
  try:verify(plan,work);unchanged=True
  except BaseException:unchanged=False
  unrun=[name for name in CASES if name not in {row['suite'] for row in rows}];passed=not failure and unchanged and not unrun and all(row['passed'] for row in rows)
  write(work/'matrix.json',{'schema':'adhd/controlled-sdk-image-result@1','passed':passed,'plan_sha256':expected,'driver_sha256':plan['driver_sha256'],'frozen_inputs_unchanged':unchanged,'failure_type':failure,
   'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'unrun_suites':unrun,'rows':rows,'scope':plan['scope']})
 return 0 if passed else 1


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--reviewed-plan-sha256')
 for name in ['repo','context','admission','parent-plan','parent-matrix']:parser.add_argument('--'+name,type=Path)
 parser.add_argument('--admission-sha256');args=parser.parse_args();work=args.work.absolute()
 if args.prepare:prepare(args)
 else:sys.exit(execute(work,args.reviewed_plan_sha256))
