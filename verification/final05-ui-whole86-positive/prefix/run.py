#!/usr/bin/env python3
"""Prepare/review the original nine UI/OpenRig suites on one admitted image.

Preparation only reads/copies inputs. Explicit reviewed execution is serial,
once-gated and fail-first; screenshots remain subject to actual visual review.
"""
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import time
sys.dont_write_bytecode=True
CASES={'admin':18,'evidence':11,'eventing':12,'roles':22,'recovery':2,'index-epoch':6,'openrig':11,'accounts-oidc':2,'session-fence':2}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def tree(root,links=False,external_links=None):
 assert root.is_absolute() and root.resolve()==root and root.is_dir() and not root.is_symlink()
 files={};directories=[];aliases={};outside={}
 for path in sorted(root.rglob('*')):
  info=path.lstat();name=str(path.relative_to(root))
  if stat.S_ISLNK(info.st_mode):
   assert links and path.resolve().is_file();aliases[name]=os.readlink(path)
   if not path.resolve().is_relative_to(root):
    rule=(external_links or {}).get(name);assert rule and rule['link']==os.readlink(path)
    assert rule['resolved']==str(path.resolve()) and rule['sha256']==sha(path.resolve());outside[name]=rule
  elif stat.S_ISDIR(info.st_mode):directories.append(name)
  else:
   assert stat.S_ISREG(info.st_mode) and info.st_nlink==1
   files[name]={'sha256':sha(path),'bytes':info.st_size}
 return {'files':files,'directories':directories,'links':aliases,'external_links':outside}



def approved_entrypoint(key,current,original,amendments):
 if current==original:
  assert key not in amendments,'Unused entrypoint amendment'
  return False
 assert key=='tests/openrig_acceptance.py','Unapproved original UI entrypoint change'
 row=amendments[key]
 assert row['original_sha256']==original and row['approved_sha256']==current
 assert isinstance(row['scope'],str) and 1<=len(row['scope'])<=1024
 return True


def prepare(a):
 repo=a.repo.absolute();work=a.work.absolute();assert repo.resolve()==repo and not work.exists()
 assert sha(a.admission)==a.admission_sha256;admission=json.loads(a.admission.read_text());image=admission['image_config_identity'];artifact=admission['artifact_sha256']
 reader=load(repo/'tests/image_qualification_inputs.py','reviewed_ui_inputs');selected=reader.reviewed_payload(a.context/'manifest.json',a.admission,a.admission_sha256,image,artifact)
 compiled=None
 if a.compiled_cache_manifest:
  validator=load(repo/'tests/controlled_sdk_matrix.py','reviewed_ui_cache_binding')
  compiled=validator.compiled_cache_binding(a.compiled_cache_manifest,admission,image,artifact,sha(a.context/'manifest.json'))
 assert compiled is not None or 'compiled_runtime_audit' not in admission,'Compiled UI target requires cache manifest binding'
 amendments={}
 if a.entrypoint_amendments:
  amendment=json.loads(a.entrypoint_amendments.read_text());assert amendment['schema']=='adhd/ui-entrypoint-amendments@1';amendments=amendment['entries']
  assert set(amendments)<= {'tests/openrig_acceptance.py'}
 used_amendments=set()
 initial=json.loads((repo/'verification/native39-ui-initial/plan.json').read_text());remainder=json.loads((repo/'verification/native39-ui-remainder/plan.json').read_text())
 historical=json.loads((repo/'verification/native39-ui-remainder/manifest.json').read_text());assert historical['passed'] and historical['complete_suites']==9 and historical['complete_check_or_viewport_units']==86
 old_inputs=json.loads(Path(remainder['inputs_manifest']).read_text());assert sha(remainder['inputs_manifest'])==remainder['inputs_manifest_sha256']
 work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
 for part in ['tests','scripts']:
  for path in (repo/part).rglob('*'):
   if '__pycache__' not in path.parts:assert not path.is_symlink()
 _,drift=reader.freeze_inputs(repo,frozen,selected['specifications'])
 for name in ['image_ui_matrix.py','image_ui_runtime.py','image_ui_static.py']:shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
 bound={'image-manifest.json':a.context/'manifest.json','staged-Dockerfile':a.context/'Dockerfile','admission.json':a.admission,
  'receipt.json':a.admission.parent/'receipt.json','rebuild.json':a.admission.parent/'rebuild.json','openrig.tgz':Path(initial['frozen_tarball'])}
 if compiled:bound.update({'cache-manifest.json':a.compiled_cache_manifest,'cache-metadata.json':a.compiled_cache_manifest.with_name('cache-metadata.json')})
 if a.entrypoint_amendments:bound['entrypoint-amendments.json']=a.entrypoint_amendments
 for name,path in bound.items():assert path.is_file() and not path.is_symlink();shutil.copyfile(path,work/name)
 assert all(sha(work/name)==admission['files'][name] for name in ['receipt.json','rebuild.json'])
 pin=json.loads((frozen/'tests/openrig_pin.json').read_text());assert 'sha512-'+base64.b64encode(hashlib.sha512((work/'openrig.tgz').read_bytes()).digest()).decode()==pin['integrity']
 # Existing installed tools are read-only inputs, never installed or invoked.
 externals=dict(old_inputs['external'])
 for path in ['verification/native39-ui-initial/manifest.json','verification/native39-ui-initial/plan.json','verification/native39-ui-remainder/manifest.json','verification/native39-ui-remainder/plan.json']:
  source=repo/path;externals[str(source)]={'sha256':sha(source)}
 actual=json.loads((work/'rebuild.json').read_text())['result'];formal=Path(actual['artifact']);assert actual['passed'] and actual['receipt_committed'] and sha(formal)==artifact;externals[str(formal)]={'sha256':artifact}
 tool_roots={str(Path(root).absolute()):tree(Path(root).absolute()) for root in old_inputs['critical_tooling']}
 openrig=Path(initial['serial_lane'][6]['argv'][initial['serial_lane'][6]['argv'].index('--rig')+1]);modules=openrig.parent.parent.parent.parent
 assert modules.name=='node_modules'
 external_links={}
 for path in modules.rglob('*'):
  if path.is_symlink() and not path.resolve().is_relative_to(modules):
   original=old_inputs['external'].get(str(path));assert original and original.get('symlink')==os.readlink(path)
   external_links[str(path.relative_to(modules))]={'link':os.readlink(path),'resolved':str(path.resolve()),'sha256':sha(path.resolve())}
 tool_roots[str(modules)]=tree(modules,links=True,external_links=external_links)
 node=Path(initial['env']['PATH'].split(':')[0])/'node';externals[str(node)]={'sha256':sha(node),'resolved':str(node.resolve())}
 docker=Path('/usr/bin/docker');assert docker.resolve()==docker;externals[str(docker)]={'sha256':sha(docker)}
 qualified_path=':'.join([str(node.parent),str(repo/'_build/federation/native/erlang/bin'),str(repo/'_build/federation/native/elixir/bin'),'/usr/bin','/bin'])
 assert shutil.which('docker',path=qualified_path)==str(docker)
 jobs=[];runtime=work/'runtime';openrig_root=a.openrig_root.absolute();assert not openrig_root.exists() and len(str(openrig_root/'rigs/mux/tmux-999999/default'))<105
 for row in initial['serial_lane']:
  name=row['name'];assert name in CASES
  old=row['argv'];entry=next(Path(value) for value in old if value.endswith('.py'))
  entry=frozen/'tests'/entry.name;key='tests/'+entry.name
  if approved_entrypoint(key,sha(entry),old_inputs['files'][key]['sha256'],amendments):used_amendments.add(key)
  common=[str(entry),'--image',image,'--image-manifest',str(work/'image-manifest.json'),'--report',str(work/(name+'.json'))]
  if name not in ['accounts-oidc','session-fence']:
   keep=openrig_root if name=='openrig' else runtime/name
   common+=['--eventing-rest-url','http://127.0.0.1:18082','--keep-work',str(keep)]
   if '--with-model' in old:common+=['--with-model']
  if name=='openrig':common+=['--rig',str(openrig),'--openrig-tarball',str(work/'openrig.tgz'),'--peer-eventing-rest-url','http://127.0.0.1:18085']
  if name=='session-fence':common+=['--port-lock',initial['serial_lane'][8]['argv'][-1]]
  jobs.append({'name':name,'expected_units':CASES[name],'test_argv':common,'outer_timeout_seconds':row['outer_timeout_seconds'],'scope':row['scope'],
   'custody_report':str(work/(name+'-custody.json')),'launch_ledger':str(work/(name+'-launches.json')),'foundation_lock':initial['serial_lane'][7]['argv'][1] if name=='accounts-oidc' else None})
 assert [v['name'] for v in jobs]==list(CASES) and used_amendments==set(amendments)
 shutil.copyfile(__file__,work/'run.py')
 env={key:value for key,value in initial['env'].items() if key not in ['PYTHONPYCACHEPREFIX']};env.update(PYTHONDONTWRITEBYTECODE='1',NODE_DISABLE_COMPILE_CACHE='1',PATH=qualified_path)
 plan={'schema':'adhd/image-ui-nine-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','image_config_identity':image,'artifact_sha256':artifact,'admission_sha256':a.admission_sha256,
  'compiled_cache':compiled,'entrypoint_amendments':amendments,'canonical_manifest_sha256':sha(work/'image-manifest.json'),'manifest':str(work/'image-manifest.json'),'frozen':str(frozen),'frozen_tree':tree(frozen),'frozen_inputs':{key:value['sha256'] for key,value in tree(frozen)['files'].items()},
  'externals':externals,'tool_roots':tool_roots,'bound_inputs':{name:sha(work/name) for name in bound},'driver_sha256':sha(work/'run.py'),'python':sys.executable,
  'root_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'admitted_specification_drift':drift,'actual_formal_export':str(formal),'specifications':33,'actual_app_files':59,
  'runtime_cwd':str(runtime),'openrig_root':str(openrig_root),'lane_lock':initial['lane_lock'],'env':env,'jobs':jobs,'planned_suites':list(CASES),'expected_units':86,
  'docker':{'path':str(docker),'sha256':sha(docker)},'qualified_path':qualified_path,'tool_closure_scope':'Existing declared tool roots and exact top executables; no additional recursive library closure claim','parallelism':1,'maximum_owned_hubs':2,'automatic_retries':0,'runs_per_suite':1,'stop_first_failure':True,'provider_calls_authorized':0,
  'native39_historical_only':{'artifact_sha256':historical['artifact_sha256'],'completed_units':86,'original_false_aggregate_preserved':True},
  'prior_image40_prefix':'Six whole71 remain historical source-only-image40 scopes; old false aggregate and10 partial OpenRig excluded, not counted into new full9 execution','diagnostic_capture_storage':'Actual PNG/ARIA remain ignored under runtime/OpenRig private roots; retain hashes and paths only in durable proof, then require root visual review','capture_and_manual_review':initial['capture_and_manual_review'],'openrig_scope':'Actual two builtin:terminal rigs via pinned CLI0.6.14. No LLM coding-provider workload; no image egress firewall claim.',
  'scope':'Exact admitted image40 UI/OpenRig nine suites86units only after actual execution. Native39 evidence remains historical; captures require root visual inspection; no backend semantic quality/platform/release claim.'}
 write(work/'plan.json',plan);load(work/'run.py','copied_image_ui_driver').verify(plan,work)
 print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen_inputs']),'external_entries':len(externals),'tool_roots':len(tool_roots),'bound_inputs':len(bound)}))


def verify(plan,work):
 driver=Path(__file__);assert driver.absolute()==work/'run.py' and driver.resolve()==driver.absolute() and not driver.is_symlink() and sha(driver)==plan['driver_sha256']
 assert tree(work/'frozen')==plan['frozen_tree'] and {k:v['sha256'] for k,v in plan['frozen_tree']['files'].items()}==plan['frozen_inputs']
 for key,value in plan['externals'].items():
  path=Path(key)
  if 'symlink' in value:assert path.is_symlink() and os.readlink(path)==value['symlink']
  else:
   assert path.is_file() and sha(path)==value['sha256']
   if 'resolved' in value:assert str(path.resolve())==value['resolved']
 for root,value in plan['tool_roots'].items():assert tree(Path(root),links=bool(value['links']),external_links=value['external_links'])==value
 for name,digest in plan['bound_inputs'].items():assert not(work/name).is_symlink() and sha(work/name)==digest
 if plan.get('compiled_cache'):
  validator=load(work/'frozen/tests/controlled_sdk_matrix.py','frozen_ui_cache_binding')
  assert validator.compiled_cache_binding(work/'cache-manifest.json',json.loads((work/'admission.json').read_text()),plan['image_config_identity'],plan['artifact_sha256'],plan['canonical_manifest_sha256'])==plan['compiled_cache']
 if plan.get('entrypoint_amendments'):
  assert json.loads((work/'entrypoint-amendments.json').read_text())['entries']==plan['entrypoint_amendments']
 assert plan['planned_suites']==list(CASES) and [v['name'] for v in plan['jobs']]==list(CASES) and [v['expected_units'] for v in plan['jobs']]==list(CASES.values())
 assert plan['docker']['path']=='/usr/bin/docker' and sha(plan['docker']['path'])==plan['docker']['sha256']
 assert plan['env']['PATH']==plan['qualified_path'] and shutil.which('docker',path=plan['qualified_path'])==plan['docker']['path']
 assert plan['parallelism']==1 and plan['automatic_retries']==0 and plan['expected_units']==86
 return True


def unit_count(value,name):
 if name=='accounts-oidc':return len(value['viewports'])
 if name=='session-fence':return len(value['observations'])
 return len(value['checks'])


def captures(root):
 result={}
 if root.exists():
  for png in root.rglob('*.png'):
   assert not png.is_symlink();structure=png.with_suffix('.txt')
   assert structure.is_file() and not structure.is_symlink(),'Missing screenshot ARIA companion'
   result[str(png)]={'png_sha256':sha(png),'aria_sha256':sha(structure),'bytes':png.stat().st_size}
 return result


def cleanup_ledger(work,job,plan):
 helper=load(work/'frozen/tests/controlled_image_matrix.py','strict_ui_absence');runtime=load(work/'frozen/tests/image_ui_runtime.py','owned_ui_processes')
 path=Path(job['launch_ledger']);rows=[];errors=[]
 if not path.exists():return {'observations':[],'errors':[],'fallback_mutation':False}
 ledger=json.loads(path.read_text());mutated=False
 for launch in ledger['launches']:
  identifier=launch.get('container_id') or launch['name'];result={'name':launch['name'],'identifier':identifier,'observed_absent':False,'fallback_mutation':False}
  try:
   inspected=subprocess.run([plan['docker']['path'],'inspect',identifier],capture_output=True,timeout=30)
   if not helper.authoritative_absence(inspected,identifier):
    assert inspected.returncode==0;objects=json.loads(inspected.stdout);assert len(objects)==1;obj=objects[0]
    assert obj['Image']==plan['image_config_identity'] and obj['Name']=='/'+launch['name']
    if launch.get('container_id'):assert obj['Id']==launch['container_id']
    if launch['kind']=='app':assert any(m['Type']=='bind' and m['Source']==launch['private_root'] and m['Destination']==launch['private_root'] for m in obj['Mounts'])
    removed=subprocess.run([plan['docker']['path'],'rm','--force',obj['Id']],capture_output=True,timeout=30);assert removed.returncode==0
    mutated=True;result['fallback_mutation']=True;identifier=obj['Id']
   for key in dict.fromkeys([identifier,launch['name']]):
    final=subprocess.run([plan['docker']['path'],'inspect',key],capture_output=True,timeout=30);assert helper.authoritative_absence(final,key)
   result['identifier']=identifier;result['observed_absent']=True
  except BaseException as error:result['failure_type']=type(error).__name__;errors.append(type(error).__name__)
  rows.append(result)
 processes=[row['identity'] for row in ledger['clients'] if row['identity']]+ledger['chromium']
 for rig in ledger['rigs']:
  processes+=rig['processes']+runtime.rig_processes(rig['home'],rig['mux'])
 seen=set();observed_processes=[]
 for row in processes:
  key=(row['pid'],row['starttime'])
  if key in seen:continue
  seen.add(key);result={'pid':row['pid'],'starttime':row['starttime'],'same_owned_process_not_live':False}
  try:
   if runtime.same(row):
    if runtime.kill_known(row):mutated=True;result['fallback_mutation']=True
    deadline=time.monotonic()+3
    while runtime.same(row) and time.monotonic()<deadline:time.sleep(.02)
   assert not runtime.same(row);result['same_owned_process_not_live']=True
  except BaseException as error:result['failure_type']=type(error).__name__;errors.append(type(error).__name__)
  observed_processes.append(result)
 return {'observations':rows,'processes':observed_processes,'errors':errors,'fallback_mutation':mutated}


def execute(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
 helper=load(work/'frozen/tests/controlled_image_matrix.py','durable_ui_helpers');root=Path(plan['runtime_cwd']);rig=Path(plan['openrig_root']);assert not root.exists() and not rig.exists()
 lock=Path(plan['lane_lock']);lock.parent.mkdir(parents=True,exist_ok=True)
 with lock.open('a') as guard:
  fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB);helper.durable_once_marker(work/'started.json',{'plan_sha256':expected,'started_at':time.time()});root.mkdir(mode=0o700)
  env=dict(os.environ);env.update(plan['env']);rows=[];failure=None
  try:
   for job in plan['jobs']:
    verify(plan,work);name=job['name'];log=work/(name+'.log');report=work/(name+'.json');assert not log.exists() and not report.exists()
    argv=[plan['python'],'-B',str(work/'frozen/tests/image_ui_runtime.py'),'--plan',str(work/'plan.json'),'--job',name,'--reviewed-plan-sha256',expected]
    if job['foundation_lock']:argv=['/usr/bin/flock',job['foundation_lock'],*argv]
    before=captures(root);row={'suite':name,'passed':False,'argv':argv};began=time.monotonic();child=None
    try:
     with log.open('xb') as output:
      child=subprocess.Popen(argv,cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
      try:code=child.wait(timeout=job['outer_timeout_seconds'])
      except subprocess.TimeoutExpired:
       os.killpg(child.pid,signal.SIGTERM)
       try:child.wait(timeout=15)
       except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
       row['fixture_cleanup_proven']=False;raise RuntimeError('Original outer timeout; inspect owned fixture cleanup')
     row['exit_code']=code;assert code==0 and report.exists()
     value=json.loads(report.read_text());custody=json.loads(Path(job['custody_report']).read_text())
     assert value['passed'] and unit_count(value,name)==job['expected_units'] and custody['passed']
     after=captures(root);new={k:v for k,v in after.items() if k not in before}
     if name not in ['evidence','openrig']:
      assert new and any('desktop' in k for k in new) and any('mobile' in k for k in new)
     row['new_screenshots_and_ARIA']=new
     row.update(passed=True,units=job['expected_units'],report_sha256=sha(report),custody_sha256=sha(job['custody_report']))
    except BaseException as error:row.update(failure_type=type(error).__name__,failure=str(error))
    finally:
     if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15);row['fixture_cleanup_proven']=False
     try:
      row['independent_cleanup']=cleanup_ledger(work,job,plan)
      if row['independent_cleanup']['errors'] or row['independent_cleanup']['fallback_mutation']:row['passed']=False
     except BaseException as error:row['cleanup_failure_type']=type(error).__name__;row['passed']=False
     row['elapsed_seconds']=time.monotonic()-began;row['log_sha256']=sha(log);rows.append(row);write(work/'matrix.json',{'passed':False,'status':'RUNNING','rows':rows})
    if not row['passed']:break
  except BaseException as error:failure=type(error).__name__
  finally:
   try:verify(plan,work);unchanged=True
   except BaseException:unchanged=False
   unrun=[name for name in CASES if name not in {row['suite'] for row in rows}];passed=not failure and unchanged and not unrun and all(row['passed'] for row in rows)
   write(work/'matrix.json',{'schema':'adhd/image-ui-nine-result@1','passed':passed,'plan_sha256':expected,'driver_sha256':plan['driver_sha256'],'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'frozen_inputs_unchanged':unchanged,'failure_type':failure,'rows':rows,'unrun_suites':unrun,'manual_visual_review_required':True,'scope':plan['scope']})
 return 0 if passed else 1


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--reviewed-plan-sha256')
 for name in ['repo','context','admission','openrig-root','compiled-cache-manifest','entrypoint-amendments']:parser.add_argument('--'+name,type=Path)
 parser.add_argument('--admission-sha256');a=parser.parse_args();work=a.work.absolute()
 if a.prepare:prepare(a)
 else:sys.exit(execute(work,a.reviewed_plan_sha256))
