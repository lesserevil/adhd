#!/usr/bin/env python3
"""Freeze/review the unqualified native40 core union; preparation starts no runtime."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode=True

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def identity(pid):
 try:
  raw=Path('/proc',str(pid),'stat').read_text();parts=raw[raw.rfind(')')+2:].split()
  return {'pid':pid,'starttime':parts[19],'state':parts[0]}
 except FileNotFoundError:return None

def same(row):
 current=identity(row['pid']);return current is not None and current['starttime']==row['starttime'] and current['state']!='Z'


def owned_nonce_processes(nonce,proc_root=Path('/proc')):
 marker=('ADHD_NATIVE_CORE_RUN_NONCE='+nonce).encode();found=[]
 for path in proc_root.iterdir():
  try:
   if not path.name.isdigit() or path.stat().st_uid!=os.getuid():continue
   with (path/'environ').open('rb')as stream:raw=stream.read(1048577)
   assert len(raw)<=1048576,'Owned process environment exceeds audit bound'
   if marker not in raw.split(b'\0'):continue
   row=identity(int(path.name))
   if row and row['state']!='Z':found.append(row)
  except(FileNotFoundError,ProcessLookupError,PermissionError):continue
 return found

def close_nonce_processes(nonce):
 rows=owned_nonce_processes(nonce)
 for row in rows:
  try:fd=os.pidfd_open(row['pid'],0)
  except ProcessLookupError:continue
  try:
   if not same(row):continue
   assert any(v['pid']==row['pid'] and v['starttime']==row['starttime']for v in owned_nonce_processes(nonce)),'Owned nonce identity changed before cleanup'
   signal.pidfd_send_signal(fd,signal.SIGKILL)
   deadline=time.monotonic()+10
   while same(row) and time.monotonic()<deadline:time.sleep(.01)
   assert not same(row),'Owned nonce process remains live'
  except ProcessLookupError:pass
  finally:os.close(fd)
 assert not owned_nonce_processes(nonce)
 return rows

def owned_tree(root):
 root=Path(root);assert root.absolute()==root.resolve() and root.is_dir() and not root.is_symlink()
 files={};directories=[]
 for p in sorted(root.rglob('*')):
  info=p.lstat();assert not stat.S_ISLNK(info.st_mode)
  if stat.S_ISDIR(info.st_mode):directories.append(str(p.relative_to(root)))
  else:
   assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
   files[str(p.relative_to(root))]=sha(p)
 return {'files':files,'directories':directories}


def coordinator_argv(name,argv,lock):
 # Wire owns its original self-flock. Only foundation needs an outer coordinator.
 return ['/usr/bin/flock',lock,*argv] if name=='foundation' else argv

def replace_workspace(value,old,new):
 if isinstance(value,str):return value.replace(str(old),str(new))
 if isinstance(value,list):return [replace_workspace(v,old,new)for v in value]
 if isinstance(value,dict):return {k:replace_workspace(v,old,new)for k,v in value.items()}
 return value

def prepare_remainder(a):
 work=a.work.absolute();assert not work.exists()
 parent_path=a.parent_plan.absolute();old=parent_path.parent;parent=json.loads(parent_path.read_text())
 original=load(old/'run.py','original_native29_driver');assert original.verify(parent,old)
 result=json.loads(a.parent_result.read_text());assert result['passed']is False and result['inputs_unchanged']
 assert result['plan_sha256']==sha(parent_path) and result['artifact_sha256']==parent['artifact_sha256']
 assert [r['name']for r in result['rows']]==['foundation','wire']
 assert result['rows'][0]['passed'] and result['rows'][1]['returncode']==130 and not result['rows'][1]['passed']
 assert result['unrun']==[r['name']for r in parent['jobs'][2:]]
 work.mkdir(parents=True,mode=0o700);shutil.copytree(old/'frozen',work/'frozen')
 for name in ['native_core_remaining.py','native_core_remaining_unit.py']:shutil.copyfile(Path(__file__).parent/name,work/'frozen/tests'/name)
 shutil.copyfile(__file__,work/'run.py')
 bound={name:old/name for name in parent['bound_inputs']}
 bound.update({'parent-plan.json':parent_path,'parent-result.json':a.parent_result,'parent-driver.py':old/'run.py','prefix-foundation.json':old/'runtime/foundation.json','prefix-foundation-custody.json':old/'foundation-custody.json','prefix-foundation.log':old/'foundation.log','interrupt.json':a.interrupt_receipt})
 for name,path in bound.items():assert not path.is_symlink();shutil.copyfile(path,work/name)
 plan=json.loads(json.dumps(parent));plan.update(frozen=str(work/'frozen'),frozen_inputs=owned_tree(work/'frozen'),driver_sha256=sha(work/'run.py'),runtime=str(work/'runtime'),fence_library=str(work/'provider-fence.so'),fence_audit=str(work/'provider-fence.audit'))
 jobs=replace_workspace(parent['jobs'][1:],old,work);wire=jobs[0]
 assert wire['name']=='wire' and wire['argv'][:2]==['/usr/bin/flock',parent['jobs'][0]['argv'][1]]
 plan['foundation_lock']=wire['argv'][1];wire['argv']=wire['argv'][2:]
 assert '--port-lock'in wire['argv'] and wire['argv'][wire['argv'].index('--port-lock')+1]==plan['foundation_lock']
 plan.update(jobs=jobs,bound_inputs={name:sha(work/name)for name in bound},qualified_prefix={'names':['foundation'],'parent_plan_sha256':sha(parent_path),'parent_result_sha256':sha(a.parent_result),'whole_foundation_cases':len(json.loads((work/'prefix-foundation.json').read_text())['cases'])},scope='Remaining28 of original native29; exact whole foundation20 retained separately, original false aggregate preserved. Current native18 and ownershipfault3 also separate. No source38 equivalence/image/SDK/UI/model/platform/release claim.')
 write(work/'plan.json',plan);load(work/'run.py','native28_frozen_driver').verify(plan,work)
 print(json.dumps({'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen_inputs']['files']),'externals':len(plan['externals']),'bound_inputs':len(bound),'jobs':len(jobs)}))


def prepare(a):
 root=a.repo.absolute();work=a.work.absolute();assert not work.exists()
 proposal=json.loads(a.proposal.read_text());assert proposal['executed'] is False and proposal['remaining_native_rows']==29
 admission=json.loads(a.admission.read_text());assert sha(a.admission)==a.admission_sha256 and admission['passed']
 reader=load(root/'tests/image_qualification_inputs.py','native_inputs')
 selected=reader.reviewed_payload(a.context/'manifest.json',a.admission,a.admission_sha256,admission['image_config_identity'],admission['artifact_sha256'])
 artifact=Path(json.loads((a.admission.parent/'rebuild.json').read_text())['result']['artifact']);assert sha(artifact)==proposal['target_artifact_sha256']==admission['artifact_sha256']
 work.mkdir(mode=0o700,parents=True);frozen=work/'frozen';frozen.mkdir(mode=0o700)
 for subtree in ['tests','scripts']:
  assert all(not p.is_symlink() for p in (root/subtree).rglob('*') if '__pycache__' not in p.parts)
 inputs,drift=reader.freeze_inputs(root,frozen,selected['specifications'])
 for name in ['native_core_remaining.py','native_core_remaining_unit.py']:shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
 shutil.copyfile(__file__,work/'run.py')
 bound={'proposal.json':a.proposal,'admission.json':a.admission,'receipt.json':a.admission.parent/'receipt.json','rebuild.json':a.admission.parent/'rebuild.json','image-manifest.json':a.context/'manifest.json'}
 for name,p in bound.items():assert p.resolve()==p.absolute() and not p.is_symlink();shutil.copyfile(p,work/name)
 for name in ['receipt.json','rebuild.json']:assert sha(work/name)==admission['files'][name]
 # Positive prefix and original native/image row definitions are immutable external evidence.
 external={}
 for text,digest in proposal['bindings'].items():
  p=Path(text) if Path(text).is_absolute() else root/text
  assert sha(p)==digest;external[str(p)]=digest
 old=json.loads((root/'verification/project-recovery/development40/core-preparation/plan.json').read_text())
 producer=Path(next(j for j in old['jobs'] if j['name']=='workflow-upgrade')['arguments'][next(j for j in old['jobs'] if j['name']=='workflow-upgrade')['arguments'].index('--producer-report')+1])
 producer_value=json.loads(producer.read_text());producer_root=root/producer_value['workdir']/'hub'
 assert producer_value['passed'] and producer_root.is_dir()
 producer_state=owned_tree(producer_root)
 elixir=root/'_build/federation/native/elixir/bin/elixir';compiler=Path(shutil.which('cc')).resolve()
 tools={name:{'path':str(p.absolute()),'resolved':str(p.resolve()),'sha256':sha(p.resolve())}for name,p in [('python',Path(sys.executable)),('elixir',elixir),('compiler',compiler),('flock',Path('/usr/bin/flock'))]}
 for value in tools.values():external[value['resolved']]=value['sha256']
 for p in (root/'_build/federation/native/erlang').glob('erts-*/bin/beam.smp'):external[str(p)]=sha(p)
 jobs=[]
 for row in proposal['proposed_rows']:
  if row['qualification_state']!='UNSTARTED_MISSING_CURRENT_NATIVE_PROOF':continue
  name=row['name'];script=frozen/row['entrypoint'];assert sha(script)==row['entrypoint_sha256']
  argv=[]
  for arg in row['argv']:
   if arg=='/home/horde/src/adhd/.venv/bin/python':argv.append(sys.executable)
   elif arg==str(root/row['entrypoint']):argv.append(str(script))
   else:argv.append(arg.replace('FRESH_NATIVE40_RESULTS_ROOT',str(work/'runtime')))
  argv=coordinator_argv(name,argv,str(root/'_build/roadmap/foundation-port.lock'))
  jobs.append({'name':name,'argv':argv,'script':str(script),'report':str(work/'runtime'/(name+'.json')),'custody':str(work/(name+'-custody.json')),'log':str(work/(name+'.log'))})
 assert len(jobs)==29 and [r['name']for r in jobs]==proposal['remaining_native_row_names']
 for job in jobs:
  for value in job['argv']:
   if value.startswith('/'):
    candidate=Path(value)
    if candidate.is_file() and not candidate.is_relative_to(work):
     if candidate.is_symlink():assert str(candidate) in [v['path']for v in tools.values()]
     external[str(candidate.resolve())]=sha(candidate.resolve())
 plan={'schema':'adhd/native-core-remaining-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','artifact_sha256':sha(artifact),'artifact':str(artifact),'source_admission_sha256':a.admission_sha256,'frozen':str(frozen),'frozen_inputs':owned_tree(frozen),'bound_inputs':{n:sha(work/n)for n in bound},'externals':external,'producer_root':str(producer_root),'producer_tree':producer_state,'driver_sha256':sha(work/'run.py'),'tools':tools,'runtime':str(work/'runtime'),'jobs':jobs,'specification_drift':drift,'retained_native_rows':proposal['retained_current_native_rows'],'automatic_retries':0,'parallelism':1,'outer_child_deadline':None,'scope':'Current source40 native29 remaining rows only; original native18 and ownership-fault3 stay separately retained. No image/SDK/model/security/UI/recovery matrix closure.','tool_closure_scope':'Exact inputs and top executable identities, not recursive tool-library closure','foundation_lock':str(root/'_build/roadmap/foundation-port.lock'),'qualified_path':str(elixir.parent)+':'+str(root/'_build/federation/native/erlang/bin')+':/usr/bin:/bin','provider_port_fence':18770,'fence_library':str(work/'provider-fence.so'),'fence_audit':str(work/'provider-fence.audit'),'root_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
 write(work/'plan.json',plan);load(work/'run.py','native_frozen_driver').verify(plan,work)
 print(json.dumps({'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen_inputs']['files']),'external_files':len(external),'bound_inputs':len(bound),'rows':len(jobs)}))

def verify(plan,work):
 assert Path(__file__).absolute()==Path(__file__).resolve()==work/'run.py' and sha(__file__)==plan['driver_sha256']
 assert owned_tree(work/'frozen')==plan['frozen_inputs']
 for name,digest in plan['bound_inputs'].items():assert not(work/name).is_symlink() and sha(work/name)==digest
 for name,digest in plan['externals'].items():assert not Path(name).is_symlink() and sha(name)==digest
 assert owned_tree(plan['producer_root'])==plan['producer_tree']
 for value in plan['tools'].values():assert str(Path(value['path']).resolve())==value['resolved'] and sha(value['resolved'])==value['sha256']
 assert plan['automatic_retries']==0 and plan['parallelism']==1 and plan['outer_child_deadline'] is None
 if plan.get('qualified_prefix'):
  parent=json.loads((work/'parent-plan.json').read_text());result=json.loads((work/'parent-result.json').read_text());old=Path(parent['frozen']).parent
  assert len(plan['jobs'])==28 and plan['qualified_prefix']['names']==['foundation'] and result['passed']is False
  assert result['rows'][0]['name']=='foundation' and result['rows'][0]['passed']
  expected=replace_workspace(parent['jobs'][1:],old,work);assert expected[0]['name']=='wire' and expected[0]['argv'][:2]==['/usr/bin/flock',plan['foundation_lock']]
  expected[0]['argv']=expected[0]['argv'][2:];assert expected==plan['jobs']
  report=json.loads((work/'prefix-foundation.json').read_text());custody=json.loads((work/'prefix-foundation-custody.json').read_text())
  assert report['passed'] and report['artifact_sha256']==plan['artifact_sha256'] and custody['passed']
  assert result['rows'][0]['report_sha256']==sha(work/'prefix-foundation.json') and result['rows'][0]['custody_sha256']==sha(work/'prefix-foundation-custody.json') and result['rows'][0]['log_sha256']==sha(work/'prefix-foundation.log')
  assert plan['qualified_prefix']['parent_plan_sha256']==sha(work/'parent-plan.json') and plan['qualified_prefix']['parent_result_sha256']==sha(work/'parent-result.json')
  before=parent['frozen_inputs']['files'];after=plan['frozen_inputs']['files'];assert set(before)==set(after)
  assert {name for name in before if before[name]!=after[name]}=={'tests/native_core_remaining.py','tests/native_core_remaining_unit.py'}
 else:assert len(plan['jobs'])==29
 return True

class ChildLedger:
 """Transparent owned Popen observations; no changes to request/readiness behavior."""
 def __init__(self,path):self.path=Path(path);self.processes=[];self.rows=[];self.lock=threading.RLock()
 def install(self):
  previous=subprocess.Popen;ledger=self
  def observed(*args,**kwargs):
   process=previous(*args,**kwargs)
   with ledger.lock:
    ledger.processes.append(process);row=identity(process.pid)
    ledger.rows.append({'pid':process.pid,'identity':row,'argv_sha256':hashlib.sha256(repr(args[0] if args else kwargs.get('args')).encode()).hexdigest()})
    ledger.save()
   return process
  subprocess.Popen=observed;self.previous=previous
 def save(self):write(self.path,{'processes':self.rows,'scope':'Owned subprocess creation identities; no global PID or system-wide cleanup claim'})
 def close(self):
  subprocess.Popen=self.previous;orphans=[]
  for process,row in zip(self.processes,self.rows):
   if process.poll() is None:
    orphans.append(row['pid'])
    # Only genuine Popen handles we created, plus stable start identity, may be killed.
    assert row['identity'] and same(row['identity'])
    process.kill();process.wait(timeout=10)
   row['returncode']=process.returncode;row['same_process_absent']=not row['identity'] or not same(row['identity'])
   assert row['same_process_absent']
  self.save();return orphans

def child(work,expected,name):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
 row=next(r for r in plan['jobs']if r['name']==name);ledger=ChildLedger(row['custody']);ledger.install();failure=None;code=0;orphans=[]
 try:
  sys.path.insert(0,str(work/'frozen/tests'));sys.argv=row['argv']
  # flock is already owned by the outer driver; only the unchanged Python test body runs here.
  i=sys.argv.index(row['script']);sys.argv=sys.argv[i:];runpy.run_path(row['script'],run_name='__main__')
 except SystemExit as error:
  code=0 if error.code is None else error.code if isinstance(error.code,int) else 1
  if error.code is not None and not isinstance(error.code,int):print(error.code,file=sys.stderr)
 except BaseException as error:failure=type(error).__name__;raise
 finally:
  try:orphans=ledger.close()
  finally:
   value=json.loads(Path(row['custody']).read_text())if Path(row['custody']).exists()else {'processes':[]}
   value.update(passed=not failure and code==0 and not orphans,failure_type=failure,exit_code=code,unexpected_live_owned_pids=orphans);write(row['custody'],value)
 return 1 if orphans else code

def execute(work,expected):
 assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(plan,work)
 helper=load(work/'frozen/tests/controlled_image_matrix.py','native_once');assert not Path(plan['runtime']).exists()
 helper.durable_once_marker(work/'started.json',{'plan_sha256':expected,'driver_sha256':plan['driver_sha256']})
 Path(plan['runtime']).mkdir(mode=0o700);tmp=Path(plan['runtime'])/'tmp';tmp.mkdir(mode=0o700)
 env=dict(os.environ,PATH=plan['qualified_path'],TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1',ERL_FLAGS='+S 2:2',LD_PRELOAD=plan['fence_library'],ADHD_RECOVERY_DENY_PROVIDER_PORT='18770',ADHD_RECOVERY_PROVIDER_FENCE_AUDIT=plan['fence_audit'])
 rows=[];failure=None
 try:
  subprocess.run([plan['tools']['compiler']['resolved'],'-shared','-fPIC','-O2','-o',plan['fence_library'],str(work/'frozen/tests/project_recovery_no_provider.c'),'-ldl'],check=True,timeout=30)
  for job in plan['jobs']:
   verify(plan,work);argv=[plan['tools']['python']['path'],'-B',str(work/'run.py'),'--child',job['name'],'--work',str(work),'--reviewed-plan-sha256',expected]
   argv=coordinator_argv(job['name'],argv,plan['foundation_lock'])
   print('START',job['name'],flush=True)
   nonce=expected+':'+job['name'];child_env=dict(env,ADHD_NATIVE_CORE_RUN_NONCE=nonce);result=None;child_error=None;cleanup_error=None;unexpected=[]
   try:
    with Path(job['log']).open('x') as log:result=subprocess.run(argv,cwd=plan['runtime'],env=child_env,stdout=log,stderr=subprocess.STDOUT)
   except BaseException as error:child_error=type(error).__name__
   finally:
    try:unexpected=close_nonce_processes(nonce)
    except BaseException as error:cleanup_error=type(error).__name__
   report=Path(job['report']);custody=Path(job['custody']);value=json.loads(report.read_text())if report.exists()else {};c=json.loads(custody.read_text())if custody.exists()else {}
   code=result.returncode if result else None
   row={'name':job['name'],'returncode':code,'child_error':child_error,'cleanup_error':cleanup_error,'unexpected_live_owned_nonce_processes':unexpected,'owned_nonce_processes_absent':cleanup_error is None,'passed':code==0 and not child_error and not cleanup_error and not unexpected and value.get('passed')is True and c.get('passed')is True,'report_sha256':sha(report)if report.exists()else None,'custody_sha256':sha(custody)if custody.exists()else None,'log_sha256':sha(job['log'])if Path(job['log']).exists()else None};rows.append(row)
   print('DONE',job['name'],row['passed'],flush=True);write(work/'matrix.json',{'passed':False,'rows':rows,'status':'RUNNING'})
   if not row['passed']:break
 except BaseException as error:failure=type(error).__name__;raise
 finally:
  try:verify(plan,work);unchanged=True
  except BaseException:unchanged=False
  unrun=[r['name']for r in plan['jobs']if r['name']not in {v['name']for v in rows}]
  value={'schema':'adhd/native-core-remaining-result@1','passed':not failure and unchanged and not unrun and all(r['passed']for r in rows),'plan_sha256':expected,'artifact_sha256':plan['artifact_sha256'],'rows':rows,'unrun':unrun,'failure_type':failure,'inputs_unchanged':unchanged,'scope':plan['scope'],'retained_qualified_prefix':plan.get('qualified_prefix')};write(work/'matrix.json',value)
 return 0 if value['passed']else 1

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--prepare',action='store_true');m.add_argument('--prepare-remainder',action='store_true');m.add_argument('--execute',action='store_true');m.add_argument('--child')
 p.add_argument('--parent-plan',type=Path);p.add_argument('--parent-result',type=Path);p.add_argument('--interrupt-receipt',type=Path);p.add_argument('--repo',type=Path);p.add_argument('--work',type=Path,required=True);p.add_argument('--proposal',type=Path);p.add_argument('--context',type=Path);p.add_argument('--admission',type=Path);p.add_argument('--admission-sha256');p.add_argument('--reviewed-plan-sha256');a=p.parse_args()
 if a.prepare:prepare(a)
 elif a.prepare_remainder:prepare_remainder(a)
 else:sys.exit(child(a.work.absolute(),a.reviewed_plan_sha256,a.child)if a.child else execute(a.work.absolute(),a.reviewed_plan_sha256))
