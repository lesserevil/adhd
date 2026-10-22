#!/usr/bin/env python3
"""Prepare/review one original three-boundary configuration image scenario.

Preparation is read-only metadata/copying only. The child preserves the original
45s/25s/16s deadlines, records issued app/probe identities, and lets finally run.
"""
import argparse
import ast
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
IMAGE='sha256:b12e75c09ccd213f06739f7fdd998d675670491c31677143fecaceab7823e0f0'
ARTIFACT='1741225b1a276770ec9f6631e63fe8646ee5f22808fad8a5acfe67a8aed11bd7'
ADMISSION='2526ad178e88239704f62b9d7437b98c3f4baca71ee9a82b84e635b242896d58'
BOUNDARIES=('transaction','config','journal')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def save(path,value):
 raw=(json.dumps(value,indent=2)+'\n').encode();temp=path.with_suffix('.tmp')
 with temp.open('wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
 temp.replace(path)

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
 repo=a.repo_root.absolute();work=a.work.absolute();assert repo.resolve()==repo and not work.exists()
 work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700);bound=work/'bound';bound.mkdir(mode=0o700)
 reader=load(repo/'tests/image_qualification_inputs.py','selected_payload')
 selected=reader.reviewed_payload(a.context/'manifest.json',repo/'verification/project-recovery/development38/admission/manifest.json',ADMISSION,IMAGE,ARTIFACT)
 assert len(selected['specifications'])==33 and selected['audit']['actual_app_files']==59
 for part in ['tests','scripts']:
  for source in (repo/part).rglob('*'):
   if '__pycache__' not in source.parts:assert not source.is_symlink()
 inputs,drift=reader.freeze_inputs(repo,frozen,selected['specifications'])
 for name in ['config_image_matrix.py','config_recovery.py','config_image_runtime_unit.py','config_image_matrix_unit.py']:
  shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
 original=ast.parse((repo/'tests/config_recovery.py').read_text());actual=ast.parse((frozen/'tests/config_recovery.py').read_text())
 asserts=lambda value:[ast.dump(node) for node in ast.walk(value) if isinstance(node,ast.Assert)]
 assert asserts(original)==asserts(actual),'Original assertions changed'
 for source,name in [(a.context/'manifest.json','image-manifest.json'),(a.context/'Dockerfile','staged-Dockerfile'),
    (repo/'verification/project-recovery/development38/admission/manifest.json','admission.json'),
    (a.abi_root/'build/config_rename_fault/observer.so','observer.so'),(a.abi_root/'config_rename_fault.c.proof.json','observer-proof.json')]:
  assert source.resolve()==source.absolute() and source.is_file() and not source.is_symlink();shutil.copyfile(source,bound/name)
 for name in ['receipt.json','rebuild.json']:
  assert (a.receipt_bindings/name).is_file();shutil.copyfile(a.receipt_bindings/name,bound/name)
 admission=json.loads((bound/'admission.json').read_text());proof=json.loads((bound/'observer-proof.json').read_text());manifest=json.loads((bound/'image-manifest.json').read_text())
 assert sha(bound/'receipt.json')==admission['receipt_file_sha256'] and sha(bound/'rebuild.json')==admission['official_rebuild_envelope']['sha256']
 assert sha(bound/'staged-Dockerfile')==manifest['files']['Dockerfile']
 assert proof['passed'] and proof['application_started'] is False and proof['owned_container_absent'] and proof['exit_code']==137
 assert proof['image_config_identity']==IMAGE and proof['artifact_sha256']==ARTIFACT and proof['canonical_manifest_sha256']==sha(bound/'image-manifest.json')
 assert proof['observer']['source_sha256']==sha(frozen/'tests/config_rename_fault.c') and proof['observer']['library_sha256']==sha(bound/'observer.so')
 assert proof['successful_abi_cases']==proof['observer']['exported_symbols']==['rename']
 (bound/'source38.exs').write_bytes(selected['artifact_bytes']);assert sha(bound/'source38.exs')==ARTIFACT
 shutil.copyfile(__file__,work/'driver.py');runtime=work/'runtime'
 argv=[str(frozen/'tests/config_recovery.py'),'--image',IMAGE,'--image-manifest',str(bound/'image-manifest.json'),
       '--image-artifact',str(bound/'source38.exs'),'--image-fault-library',str(bound/'observer.so'),
       '--image-fault-proof',str(bound/'observer-proof.json'),'--protocol-version','2','--report',str(work/'result.json')]
 tools={}
 for label,path in [('python',Path(sys.executable)),('docker',Path('/usr/bin/docker'))]:
  tools[label]={'path':str(path.absolute()),'resolved':str(path.resolve()),'sha256':sha(path.resolve())}
 sock=Path('/var/run/docker.sock').resolve();info=sock.stat();assert stat.S_ISSOCK(info.st_mode)
 plan={'schema':'adhd/config-image-three-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','image_config_identity':IMAGE,'artifact_sha256':ARTIFACT,
  'admission_sha256':ADMISSION,'canonical_manifest_sha256':sha(bound/'image-manifest.json'),'payload_sha256':selected['payload_sha256'],
  'driver_sha256':sha(work/'driver.py'),'frozen':tree(frozen),'bound':tree(bound),'specification_count':33,'admitted_specification_drift':drift,
  'source_observer_proof_sha256':sha(a.abi_root/'config_rename_fault.c.proof.json'),'root_original_entrypoint_sha256':sha(repo/'tests/config_recovery.py'),'root_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'original_assertions_count':len(asserts(original)),
  'runtime_cwd':str(runtime),'tools':tools,'docker_socket':{'path':str(sock),'identity':[info.st_dev,info.st_ino]},
  'test_argv':argv,'boundaries':list(BOUNDARIES),'parallelism':1,'runs_per_script':1,'automatic_retries':0,'fail_first':True,
  'outer_timeout':None,'original_deadlines':{'readiness_seconds':45,'mutation_seconds':25,'client_join_seconds':16},
  'provider_calls_authorized':0,'broker_calls_authorized':0,'scope':'Admitted38 configuration crash3 only; separate from recovery42/native strace3/latest40/UI/release. Controlled unreachable model URL127:1; no physical image egress firewall claim.',
  'preparation_app_or_compiler_starts':0}
 save(work/'plan.json',plan);load(work/'driver.py','copied_config_driver').verify(work,plan);print(json.dumps({'plan':str(work/'plan.json'),'sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen':len(plan['frozen']['files']),'bound':len(plan['bound']['files'])}))

def verify(work,plan):
 assert work.resolve()==work and Path(__file__).absolute()==work/'driver.py' and Path(__file__).resolve()==work/'driver.py'
 info=Path(__file__).lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and sha(__file__)==plan['driver_sha256']
 assert tree(work/'frozen')==plan['frozen'] and tree(work/'bound')==plan['bound']
 assert plan['image_config_identity']==IMAGE and plan['artifact_sha256']==ARTIFACT and plan['admission_sha256']==ADMISSION
 assert plan['boundaries']==list(BOUNDARIES) and plan['outer_timeout'] is None
 for row in plan['tools'].values():assert str(Path(row['path']).resolve())==row['resolved'] and sha(row['resolved'])==row['sha256']
 info=Path(plan['docker_socket']['path']).stat();assert stat.S_ISSOCK(info.st_mode) and [info.st_dev,info.st_ino]==plan['docker_socket']['identity']
 return True


def snapshot(runtime):
 image=getattr(runtime,'image_runtime',None)
 if image is None:return {'boundary':getattr(runtime,'boundary',None),'constructed':False}
 return {'boundary':runtime.boundary,'constructed':True,'verified':image.verified,'image_config_identity':image.image_id,
  'artifact_sha256':image.manifest['files']['hub.exs'],'canonical_manifest_sha256':hashlib.sha256(image.manifest_bytes).hexdigest(),
  'name':image.name,'container_id':image.container_id,'container_lifecycle':image.events,'probe_lifecycle':image.probe_events,
  'actual_beam_kernel_custody':image.custody,'observer_disarmed':not image.armed,'cleanup_blocked':getattr(image,'cleanup_blocked',False),
  'probe_cleanup_blocked':image.probe_cleanup_blocked,'probe_active_name':image.probe_active_name,
  'docker_client_exited':runtime.process is None or runtime.process.poll() is not None,
  'running_payload_custody':getattr(runtime,'reviewed_payload_custody',[])}


def audit_configuration(config,initial):
 # These are the original unreachable matcher selection and no-model transports.
 assert config['matcher']['url']=='http://127.0.0.1:1/v1/systemone'
 assert not config.get('peers')
 assert not (config.get('eventing') or {}).get('rest_url')
 if not initial:assert (config.get('eventing') or {}).get('enabled') is False
 for project in config.get('projects',[]):
  settings=project.get('settings') or {}
  for family in ['matcher','history','retrieval','archive','feedback','optimization']:
   assert not settings.get(family),'Original fixture must not add effective model overrides'
 def model_urls(value):
  if isinstance(value,dict):
   for child in value.values():model_urls(child)
  elif isinstance(value,list):
   for child in value:model_urls(child)
  elif isinstance(value,str) and re.match(r'https?://',value):
   assert value=='http://127.0.0.1:1/v1/systemone','Unexpected effective model endpoint'
 for family in ['matcher','history','retrieval','archive','feedback','optimization']:
  model_urls(config.get(family))
 return True


def child(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
 assert json.loads((work/'started.json').read_text())['plan_sha256']==expected
 sys.path.insert(0,str(work/'frozen/tests'))
 from config_image_runtime import ConfigurationFaultRuntime
 import runpy
 original_init=ConfigurationFaultRuntime.__init__;original_start=ConfigurationFaultRuntime.start;original_stop=ConfigurationFaultRuntime.stop
 original_popen=subprocess.Popen;instances=[];launches=[];primary=None;errors=[]
 def progress():
  for runtime in instances:
   image=runtime.image_runtime
   if image.name and image.container_id:
    for launch in launches:
     if launch['name']==image.name:
      assert launch.get('container_id',image.container_id)==image.container_id
      launch['container_id']=image.container_id
  save(work/'custody-progress.json',{'runtimes':[snapshot(r) for r in instances],'launches':launches})
 def init(obj,*args,**kwargs):
  original_init(obj,*args,**kwargs);instances.append(obj);progress()
 def start(obj,*args,**kwargs):
  try:
   # No actual external provider/broker is selected by these original cases.
   audit_configuration(obj.config,initial=not obj.image_runtime.verified)
   result=original_start(obj,*args,**kwargs)
   audit_configuration(obj.config,initial=False)
   image=obj.image_runtime;image.observe()
   row=json.loads(image.docker('inspect',image.container_id).stdout)[0]
   assert row['Id']==image.container_id and row['Image']==IMAGE and row['State']['Running']
   assert row['HostConfig']['PidMode']!='host' and row['State']['Pid']>0
   exe=image.docker('exec',image.container_id,'readlink','/proc/1/exe').stdout.decode().strip()
   assert exe.endswith('/beam.smp')
   manifest=image.docker('exec',image.container_id,'cat','/app/manifest.json').stdout
   assert manifest==image.manifest_bytes
   files={name:digest for name,digest in image.manifest['files'].items() if name!='Dockerfile'}
   assert len(files)==59
   raw=image.docker('exec',image.container_id,'sha256sum',*['/app/'+name for name in files]).stdout.decode()
   observed={path.removeprefix('/app/'):digest for digest,path in (line.split() for line in raw.splitlines())}
   assert observed==files
   if not hasattr(obj,'reviewed_payload_custody'):obj.reviewed_payload_custody=[]
   obj.reviewed_payload_custody.append({'container_id':row['Id'],'host_vm_pid':row['State']['Pid'],
    'namespace_vm_pid':1,'vm_executable':exe,'pid_mode':row['HostConfig']['PidMode'],
    'image_config_identity':row['Image'],'actual_app_files':len(observed),
    'canonical_manifest_sha256':hashlib.sha256(manifest).hexdigest(),'all_manifest_app_hashes_matched':True})
   return result
  finally:progress()
 def stop(obj,*args,**kwargs):
  try:return original_stop(obj,*args,**kwargs)
  finally:progress()
 def popen(argv,*args,**kwargs):
  launch=None
  if isinstance(argv,(list,tuple)) and argv[:2]==['docker','run']:
   assert '--name' in argv and IMAGE in argv and '--pid' not in argv and not any(v.startswith('--pid=') for v in argv)
   name=argv[argv.index('--name')+1];assert re.fullmatch(r'adhd-(?:multi-accept|accept-probe)-[a-f0-9]{16}',name)
   kind='probe' if name.startswith('adhd-accept-probe-') else 'app'
   assert argv[argv.index('--network')+1]==('none' if kind=='probe' else 'host')
   launch={'name':name,'kind':kind,'image_config_identity':IMAGE};launches.append(launch);progress()
  result=original_popen(argv,*args,**kwargs)
  if launch:launch['client_pid']=result.pid;progress()
  return result
 ConfigurationFaultRuntime.__init__=init;ConfigurationFaultRuntime.start=start;ConfigurationFaultRuntime.stop=stop;subprocess.Popen=popen
 try:sys.argv=plan['test_argv'];runpy.run_path(sys.argv[0],run_name='__main__')
 except BaseException as error:primary=error
 finally:
  for runtime in reversed(instances):
   try:runtime.stop()
   except BaseException as error:errors.append(type(error).__name__)
  progress();save(work/'custody.json',{'schema':'adhd/config-image-custody@1','passed':primary is None and not errors,
   'primary_failure_type':type(primary).__name__ if primary else None,'cleanup_failure_types':errors,
   'runtimes':[snapshot(r) for r in instances],'launches':launches})
 if primary:raise primary
 assert not errors,errors


def independent_absence(work,plan):
 helper=load(work/'frozen/tests/controlled_image_matrix.py','strict_docker_absence')
 progress=json.loads((work/'custody-progress.json').read_text()) if (work/'custody-progress.json').exists() else {'launches':[],'runtimes':[]}
 expected={v['name']:v.get('container_id') for v in progress['launches']}
 for runtime in progress['runtimes']:
  for key in ['container_lifecycle','probe_lifecycle']:
   for event in runtime.get(key,[]):
    identifier=event.get('container_id');name=event.get('owned_name')
    if identifier:expected[identifier]=identifier
    if name:expected[name]=identifier
 # Every issued random name is still inspected after known-ID cleanup.
 observations=[]
 for identifier,known in sorted(expected.items(),key=lambda row:(row[1] is None,row[0])):
  row={'identifier':identifier,'known_container_id':known,'observed_absent':False,'fallback_removal':False}
  try:
   actual=subprocess.run([plan['tools']['docker']['path'],'inspect',identifier],capture_output=True,timeout=30)
   if not helper.authoritative_absence(actual,identifier):
    assert actual.returncode==0,'Absence unconfirmed by Docker'
    objects=json.loads(actual.stdout);assert len(objects)==1;obj=objects[0]
    assert obj['Image']==IMAGE and re.fullmatch('[a-f0-9]{64}',obj['Id'])
    assert obj['Name'].lstrip('/') in {v['name'] for v in progress['launches']}
    if known:assert obj['Id']==known
    else:assert obj['Name']=='/'+identifier
    row['fallback_removal']=True;row['removed_container_id']=obj['Id']
    removed=subprocess.run([plan['tools']['docker']['path'],'rm','--force',obj['Id']],capture_output=True,timeout=30)
    assert removed.returncode==0,'Owned fallback removal failed'
    by_id=subprocess.run([plan['tools']['docker']['path'],'inspect',obj['Id']],capture_output=True,timeout=30)
    assert helper.authoritative_absence(by_id,obj['Id'])
    actual=subprocess.run([plan['tools']['docker']['path'],'inspect',identifier],capture_output=True,timeout=30)
   assert helper.authoritative_absence(actual,identifier),'Owned absence remains unconfirmed'
   row['observed_absent']=True
  except BaseException as error:row['failure_type']=type(error).__name__
  observations.append(row)
 save(work/'independent-absence.json',observations)
 return observations


def qualify(value,custody,plan):
 assert value['passed'] is True and value['artifact_sha256']==ARTIFACT
 assert [v['case'] for v in value['cases']]==['kill-at-'+stage+'-rename' for stage in BOUNDARIES] and all(v['passed'] for v in value['cases'])
 assert custody['passed'] and not custody['cleanup_failure_types'] and len(value['runtime'])==len(custody['runtimes'])==3
 for runtime,reported,stage in zip(custody['runtimes'],value['runtime'],BOUNDARIES):
  assert runtime['boundary']==stage and runtime['verified'] and runtime['image_config_identity']==IMAGE
  assert runtime['artifact_sha256']==ARTIFACT and runtime['canonical_manifest_sha256']==plan['canonical_manifest_sha256']
  assert runtime['observer_disarmed'] and not runtime['cleanup_blocked'] and not runtime['probe_cleanup_blocked'] and runtime['probe_active_name'] is None
  assert runtime['name'] is None and runtime['container_id'] is None and runtime['docker_client_exited']
  started={v['container_id'] for v in runtime['container_lifecycle'] if v['action']=='started'}
  stopped={v['container_id'] for v in runtime['container_lifecycle'] if v.get('observed_absent')}
  assert len(started)==2 and started<=stopped
  payload=runtime['running_payload_custody'];assert len(payload)==2 and {row['container_id'] for row in payload}==started
  assert all(row['actual_app_files']==59 and row['all_manifest_app_hashes_matched'] and row['host_vm_pid']>0
    and row['namespace_vm_pid']==1 and row['pid_mode']!='host' and row['image_config_identity']==IMAGE
    and row['canonical_manifest_sha256']==plan['canonical_manifest_sha256'] for row in payload)
  assert reported['image_config_identity']==IMAGE and reported['payload_verified']
  assert reported['canonical_manifest_sha256']==runtime['canonical_manifest_sha256']
  assert reported['artifact_sha256']==ARTIFACT and reported['container_lifecycle']==runtime['container_lifecycle']
  assert reported['actual_beam_kernel_custody']==runtime['actual_beam_kernel_custody']
  assert reported['payload_probe_lifecycle']==runtime['probe_lifecycle']
  hard=[v for v in runtime['container_lifecycle'] if v['action']=='hard-killed'];assert len(hard)==1 and hard[0]['exit_code']==137 and hard[0]['wait_observed']
  proof=runtime['actual_beam_kernel_custody'];assert len(proof)==1 and proof[0]['stage']==stage
  assert len(runtime['probe_lifecycle'])==2 and all(v['observed_absent'] and not v['cleanup_failure_types'] for v in runtime['probe_lifecycle'])


def execute(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
 helper=load(work/'frozen/tests/controlled_image_matrix.py','reviewed_pure_helpers')
 assert not Path(plan['runtime_cwd']).exists();helper.durable_once_marker(work/'started.json',{'plan_sha256':expected})
 Path(plan['runtime_cwd']).mkdir(mode=0o700);env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1';env['ERL_FLAGS']='+S 2:2'
 argv=[plan['tools']['python']['path'],'-I',str(work/'driver.py'),'--child','--work',str(work),'--plan-sha256',expected]
 process=None;failure=None;observations=[];code=None;passed=False
 try:
  with (work/'run.log').open('xb') as output:
   process=subprocess.Popen(argv,cwd=plan['runtime_cwd'],env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
   code=process.wait()  # Original authored deadlines; never bypass child finally.
  observations=independent_absence(work,plan)
  assert all(row['observed_absent'] and not row['fallback_removal'] for row in observations)
  assert code==0 and (work/'result.json').exists() and (work/'custody.json').exists()
  qualify(json.loads((work/'result.json').read_text()),json.loads((work/'custody.json').read_text()),plan);passed=True
 except BaseException as error:failure=type(error).__name__
 finally:
  if process and process.poll() is None:
   os.killpg(process.pid,signal.SIGINT);process.wait()  # Allow original finally, no hard timeout.
  try:
   final=independent_absence(work,plan)
   if any(not row['observed_absent'] or row['fallback_removal'] for row in final):passed=False
   if not observations:observations=final
  except BaseException as error:failure=failure or type(error).__name__;passed=False
  try:verify(work,plan);unchanged=True
  except BaseException:unchanged=False;passed=False
  save(work/'matrix.json',{'schema':'adhd/config-image-three-result@1','passed':passed and unchanged,'plan_sha256':expected,
   'image_config_identity':IMAGE,'artifact_sha256':ARTIFACT,'child_exit_code':code,'failure_type':failure,
   'frozen_and_bound_unchanged':unchanged,'independent_absence':observations,'whole_script_executions':1 if process else 0,
   'native_strace3_qualified':False,'scope':plan['scope']})
 return 0 if passed and unchanged else 1


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
 mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true');mode.add_argument('--child',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--plan-sha256')
 for name in ['repo-root','context','abi-root','receipt-bindings']:parser.add_argument('--'+name,type=Path)
 args=parser.parse_args();work=args.work.absolute()
 if args.prepare:prepare(args)
 elif args.child:child(work,args.plan_sha256)
 else:sys.exit(execute(work,args.plan_sha256))
