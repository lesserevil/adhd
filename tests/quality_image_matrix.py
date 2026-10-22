#!/usr/bin/env python3
"""Prepare/review the four unchanged real-provider quality suites on an explicit admitted image.

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
CASES={'history_quality':22,'retrieval_quality':21,'archive_quality':23,'feedback_quality':3}
CAPS={'history_quality':64,'retrieval_quality':32,'archive_quality':128,'feedback_quality':64}
WINDOWS={'history_quality':6000,'retrieval_quality':1800,'archive_quality':3000,'feedback_quality':1200}
BUDGET_BASIS={
 'history_quality':{'cold_starts':22,'startup_seconds_each':45,'queries':22,'query_seconds_each':35,'public_init_seconds_each':60,'control_allowance_seconds_each':120,'subtotal_seconds':5720,'margin_seconds':280},
 'retrieval_quality':{'cold_starts':1,'startup_seconds':60,'public_init_seconds':60,'index_waits':21,'index_seconds_each':25,'queries':21,'query_seconds_each':25,'control_allowance_seconds':330,'subtotal_seconds':1500,'margin_seconds':300},
 'archive_quality':{'cold_starts':1,'startup_seconds':60,'public_init_seconds':60,'index_waits':23,'index_seconds_each':45,'queries':23,'query_seconds_each':45,'control_allowance_seconds':510,'subtotal_seconds':2700,'margin_seconds':300},
 'feedback_quality':{'cold_starts':1,'startup_seconds':45,'public_init_seconds':60,'strata':3,'original_60s_waits_per_stratum':4,'control_allowance_seconds':375,'subtotal_seconds':1200,'margin_seconds':0}}


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
 for name in ['quality_image_matrix.py','quality_image_runtime.py','quality_image_static.py']:
  shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
 bindings={'image-manifest.json':a.context/'manifest.json','staged-Dockerfile':a.context/'Dockerfile','admission.json':a.admission,
  'receipt.json':a.admission.parent/'receipt.json','rebuild.json':a.admission.parent/'rebuild.json'}
 for name,path in bindings.items():assert path.resolve()==path.absolute() and not path.is_symlink();shutil.copyfile(path,work/name)
 assert all(sha(work/name)==admission['files'][name] for name in ['receipt.json','rebuild.json'])
 envelope=json.loads((work/'rebuild.json').read_text());result=envelope['result'];artifact=Path(result['artifact'])
 assert result['passed'] and result['receipt_committed'] and sha(artifact)==artifact_hash
 prior=json.loads(a.prior.read_text());assert prior['passed'] and len(prior['reports'])==4
 externals={str(a.prior.absolute()):sha(a.prior),str(artifact):artifact_hash};jobs=[];runtime=work/'runtime'
 for name,count in CASES.items():
  old=next(v for v in prior['reports'] if v['suite']==name);entry=frozen/'tests'/(name+'.py')
  assert sha(entry)==old['harness_sha256'] and len(old['result']['cases'])==count
  flag='--model-url' if name=='feedback_quality' else '--matcher-url'
  argv=[str(entry),'--image',image,flag,'@OWNED_RELAY_URL@','--report',str(work/(name+'.json'))]
  jobs.append({'name':name,'expected_groups':count,'test_argv':argv,'custody_report':str(work/(name+'-custody.json')),
   'launch_ledger':str(work/(name+'-launches.json')),'provider_log':str(work/(name+'-provider.jsonl')),'provider_post_cap':CAPS[name],'provider_window_seconds':WINDOWS[name],'experiment_budget_basis':BUDGET_BASIS[name],'expected_image_starts':22 if name=='history_quality' else 1})
 for path in [Path(sys.executable).resolve(),Path(shutil.which('docker')).resolve()]:externals[str(path)]=sha(path)
 tools={label:{'path':str(path.absolute()),'resolved':str(path.resolve()),'sha256':sha(path.resolve())} for label,path in [('python',Path(sys.executable)),('docker',Path(shutil.which('docker')))]}
 shutil.copyfile(__file__,work/'run.py')
 plan={'schema':'adhd/live-quality-image-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','image_config_identity':image,'artifact_sha256':artifact_hash,
  'canonical_manifest_sha256':sha(work/'image-manifest.json'),'admission_sha256':a.admission_sha256,'actual_formal_native_export':str(artifact),
  'frozen':str(frozen),'frozen_tree':tree(frozen),'frozen_inputs':tree(frozen)['files'],'externals':externals,
  'bound_inputs':{name:sha(work/name) for name in bindings},'driver_sha256':sha(work/'run.py'),'root_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
  'admitted_specification_drift':drift,'manifest':str(work/'image-manifest.json'),'staged_dockerfile':str(work/'staged-Dockerfile'),
  'expected_app_files':selected['audit']['actual_app_files'],'specifications':len(selected['specifications']),
  'native_artifact_sha256':[],'jobs':jobs,'planned_suites':list(CASES),'expected_groups':69,
  'tools':tools,'python':sys.executable,'runtime_cwd':str(runtime),'fence_library':str(work/'unused-no-native-fence'),'fence_audit':str(work/'unused-no-native-audit'),
  'runs_per_suite':1,'automatic_retries':0,'parallelism':1,'maximum_owned_hubs':1,'stop_first_failure':True,
  'original_readiness_seconds':{'foundation_Runtime':45,'federation_Hub':60},'original_query_seconds':{'history':35,'retrieval':25,'archive':45,'feedback':60},
  'provider_upstream':'http://127.0.0.1:18770/v1/systemone','provider_model':'Nemotron-Deciffusion-8B-v2.1','maximum_provider_posts':288,'provider_window_seconds_per_suite':WINDOWS,'maximum_provider_window_seconds':sum(WINDOWS.values()),'relay_retries':0,
  'assessment_profile':{'feedback_history_request_bytes':8192,'min_confidence_ppm':500000},'exclusive_model_lease_required':True,'extra_provider_health_or_warmup_calls':0,'provider_window_origin':'Relay creation before original suite startup; includes intervening cold startups; deadline is never extended',
  'scope':'Exactimage40 original live quality69 only. Single fixed original corpus/labels/gates; optimizer172 and deployed Compose/Kind filter/search remain separate. No execution before root review/GO.'}
 write(work/'plan.json',plan);load(work/'run.py','copied_quality_driver').verify(plan,work)
 print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen_inputs']),'externals':len(externals),'bound_inputs':len(bindings)}))


def verify(plan,work):
 driver=Path(__file__);assert driver.absolute()==work/'run.py' and driver.resolve()==driver.absolute()
 info=driver.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and sha(driver)==plan['driver_sha256']
 assert tree(work/'frozen')==plan['frozen_tree'] and plan['frozen_inputs']==plan['frozen_tree']['files']
 for path,digest in plan['externals'].items():assert not Path(path).is_symlink() and sha(path)==digest
 for path,digest in plan['bound_inputs'].items():assert not (work/path).is_symlink() and sha(work/path)==digest
 assert plan['planned_suites']==list(CASES) and [v['name'] for v in plan['jobs']]==list(CASES)
 assert [v['expected_groups'] for v in plan['jobs']]==list(CASES.values()) and plan['original_readiness_seconds']=={'foundation_Runtime':45,'federation_Hub':60}
 for row in plan['tools'].values():assert str(Path(row['path']).resolve())==row['resolved'] and sha(row['resolved'])==row['sha256']
 assert plan['expected_groups']==69 and plan['automatic_retries']==0 and plan['parallelism']==1
 return True


def execute(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
 helper=load(work/'frozen/tests/controlled_image_matrix.py','reviewed_sdk_execution_helpers')
 assert not Path(plan['runtime_cwd']).exists();helper.durable_once_marker(work/'started.json',{'plan_sha256':expected,'started_at':time.time()})
 Path(plan['runtime_cwd']).mkdir(mode=0o700);env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1';env['ERL_FLAGS']='+S 2:2'
 rows=[];failure=None
 try:
  for job in plan['jobs']:
   verify(plan,work);name=job['name'];report=work/(name+'.json');log=work/(name+'.log')
   assert all(not path.exists() for path in [report,log,Path(job['custody_report']),Path(job['launch_ledger'])])
   argv=[plan['python'],'-B',str(work/'frozen/tests/quality_image_runtime.py'),'--plan',str(work/'plan.json'),'--job',name,'--reviewed-plan-sha256',expected]
   print('START',name,flush=True);began=time.monotonic();cleanup=[];code=None;child_error=None;cleanup_error=None
   try:
    with log.open('x') as output:child=subprocess.run(argv,cwd=plan['runtime_cwd'],env=env,stdout=output,stderr=subprocess.STDOUT)
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
   assert custody['passed'] and not custody['cleanup_failure_types']
   starts=custody['runtime_events'];assert len(starts)==job['expected_image_starts']
   assert all(e['kind']=='docker' and e['completed'] and e['observed_absent'] and e['full_payload_files_verified']==59 and e['namespace_vm_pid']==1 for e in starts)
   provider=custody['provider'];assert provider['closed'] and provider['inflight']==provider['handlers']==0 and not provider['violations'] and not provider['provider_error_types']
   assert 0<provider['upstream_http_posts']<=job['provider_post_cap'];row['provider']=provider
   row['passed']=True;write(work/'matrix.json',{'passed':False,'status':'RUNNING','rows':rows});print('PASS',name,flush=True)
 except BaseException as error:failure=type(error).__name__
 finally:
  try:verify(plan,work);unchanged=True
  except BaseException:unchanged=False
  unrun=[name for name in CASES if name not in {row['suite'] for row in rows}];passed=not failure and unchanged and not unrun and all(row['passed'] for row in rows)
  write(work/'matrix.json',{'schema':'adhd/live-quality-image-result@1','passed':passed,'plan_sha256':expected,'driver_sha256':plan['driver_sha256'],'frozen_inputs_unchanged':unchanged,'failure_type':failure,
   'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'unrun_suites':unrun,'rows':rows,'scope':plan['scope']})
 return 0 if passed else 1


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--reviewed-plan-sha256')
 for name in ['repo','context','admission','prior']:parser.add_argument('--'+name,type=Path)
 parser.add_argument('--admission-sha256');args=parser.parse_args();work=args.work.absolute()
 if args.prepare:prepare(args)
 else:sys.exit(execute(work,args.reviewed_plan_sha256))
