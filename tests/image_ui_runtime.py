#!/usr/bin/env python3
"""Image-only custody around unchanged UI/OpenRig qualification entrypoints."""
import argparse
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import runpy
import signal
import stat
import subprocess
import sys
import time
sys.dont_write_bytecode=True


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def proc(pid):
 try:
  raw=Path('/proc',str(pid),'stat').read_text();parts=raw[raw.rfind(')')+2:].split()
  return {'pid':pid,'starttime':parts[19],'state':parts[0]}
 except FileNotFoundError:return None

def same(row):
 current=proc(row['pid']);return current is not None and current['starttime']==row['starttime'] and current['state']!='Z'

def kill_known(row):
 try:descriptor=os.pidfd_open(row['pid'],0)
 except ProcessLookupError:return False
 try:
  if not same(row):return False
  try:signal.pidfd_send_signal(descriptor,signal.SIGKILL)
  except ProcessLookupError:return False
  return True
 finally:os.close(descriptor)


def descendants(pid):
 found=[];pending=[pid];seen={pid}
 while pending:
  parent=pending.pop()
  try:children=Path('/proc',str(parent),'task',str(parent),'children').read_text().split()
  except FileNotFoundError:continue
  for child in map(int,children):
   if child in seen:continue
   seen.add(child);pending.append(child)
   try:
    row=proc(child)
    if row:row['executable']=os.readlink('/proc/'+str(child)+'/exe');found.append(row)
   except FileNotFoundError:pass
 return found


def rig_processes(home,mux):
 markers=[b'OPENRIG_HOME='+os.fsencode(home),b'TMUX_TMPDIR='+os.fsencode(mux)];found=[]
 for path in Path('/proc').iterdir():
  try:
   if not path.name.isdigit() or path.stat().st_uid!=os.getuid():continue
   env=(path/'environ').read_bytes().split(b'\0')
   if not any(marker in env for marker in markers):continue
   row=proc(int(path.name))
   if row:row.update(executable=os.readlink(path/'exe'),exact_private_environment=True);found.append(row)
  except (FileNotFoundError,PermissionError,ProcessLookupError):continue
 return found


class Custody:
 def __init__(self,plan,job,work):
  self.plan,self.job,self.work=plan,job,work;self.images=[];self.launches=[];self.clients=[];self.chromium=[];self.rigs=[];self.vm=[];self.errors=[]
  self.servers=[];self.image=plan['image_config_identity'];self.manifest=json.loads(Path(plan['manifest']).read_text());self.manifest_raw=Path(plan['manifest']).read_bytes()
 def progress(self):
  value={'launches':self.launches,'clients':[{'pid':v.pid,'identity':identity} for v,identity in self.clients],'chromium':self.chromium,'rigs':self.rigs,'vm':self.vm}
  Path(self.job['launch_ledger']).write_text(json.dumps(value,indent=2)+'\n')
 def docker(self,*argv):return subprocess.run(['docker',*argv],capture_output=True,check=True,timeout=30)
 def audit_models(self,config):
  from controlled_image_runtime import audit_models
  allowed=set()
  for server,source in self.servers:
   if server.fileno()>=0 and server.server_address[0]=='127.0.0.1':
    allowed.add('http://127.0.0.1:'+str(server.server_address[1])+'/v1/systemone')
  models={key:config[key] for key in ['matcher','history','retrieval','archive','feedback','optimization'] if key in config}
  models['projects']=[{'settings':{key:value for key,value in (project.get('settings') or {}).items() if key in ['matcher','history','retrieval','archive','feedback','optimization']}} for project in config.get('projects',[])]
  return audit_models(models,allowed)
 def observe_vm(self,image,phase):
  if image.name is None:return
  self.audit_models(json.loads(image.config_file.read_text()) if getattr(image,'config_file',None) else {})
  image.observe();row=json.loads(self.docker('inspect',image.container_id).stdout)[0]
  assert row['Id']==image.container_id and row['Image']==self.image and row['Name']=='/'+image.name
  assert row['State']['Running'] and row['State']['Pid']>0 and row['HostConfig']['PidMode']!='host'
  assert any(m['Type']=='bind' and m['Source']==str(image.root) and m['Destination']==str(image.root) for m in row['Mounts'])
  identifier=row['Id'];previous=next((v for v in self.vm if v['container_id']==identifier),None)
  if previous:assert previous['host_vm_pid']==row['State']['Pid'],'Image VM changed during hot UI operations'
  exe=self.docker('exec',identifier,'readlink','/proc/1/exe').stdout.decode().strip();assert exe.endswith('/beam.smp')
  assert self.docker('exec',identifier,'cat','/app/manifest.json').stdout==self.manifest_raw
  expected={key:value for key,value in self.manifest['files'].items() if key!='Dockerfile'};assert len(expected)==59
  hashes=self.docker('exec',identifier,'sha256sum',*['/app/'+key for key in expected]).stdout.decode()
  actual={path.removeprefix('/app/'):digest for digest,path in (v.split() for v in hashes.splitlines())};assert actual==expected
  self.vm.append({'phase':phase,'container_id':identifier,'owned_name':image.name,'image_config_identity':row['Image'],'host_vm_pid':row['State']['Pid'],
   'namespace_vm_pid':1,'vm_executable':exe,'pid_namespace_mode':row['HostConfig']['PidMode'],'actual_app_files':len(actual),'canonical_manifest_sha256':hashlib.sha256(self.manifest_raw).hexdigest()})
  for launch in self.launches:
   if launch['name']==image.name:launch['container_id']=identifier
  self.progress()
 def install(self):
  from container_fixture import OwnedImage
  from multi_support import Fixture
  from multi_workflow_upgrade import UpgradeRuntime
  from playwright.async_api import BrowserType
  from playwright.sync_api import BrowserType as SyncBrowserType
  from http.server import ThreadingHTTPServer
  custody=self;init=OwnedImage.__init__;popen=subprocess.Popen;image_argv=OwnedImage.argv;server_init=ThreadingHTTPServer.__init__
  def server_construct(obj,address,handler,*a,**kw):
   server_init(obj,address,handler,*a,**kw)
   source=Path(inspect.getsourcefile(handler)).absolute()
   assert source.is_relative_to(Path(custody.plan['frozen'])/'tests')
   assert sha(source)==custody.plan['frozen_inputs'][str(source.relative_to(Path(custody.plan['frozen'])))]
   custody.servers.append((obj,str(source)))
  ThreadingHTTPServer.__init__=server_construct
  def argv(obj,config_file):
   obj.config_file=Path(config_file)
   if obj.config_file.exists():custody.audit_models(json.loads(obj.config_file.read_text()))
   return image_argv(obj,config_file)
  OwnedImage.argv=argv
  def image_init(obj,*a,**kw):init(obj,*a,**kw);custody.images.append(obj)
  OwnedImage.__init__=image_init
  def observed_popen(argv,*a,**kw):
   launch=None
   if isinstance(argv,(list,tuple)) and list(argv[:2])==['docker','run']:
    assert '--name' in argv and custody.image in argv and '--pid' not in argv and not any(v.startswith('--pid=') for v in argv)
    name=argv[argv.index('--name')+1];assert re.fullmatch('adhd-(multi-accept|accept-probe)-[a-f0-9]{16}',name)
    launch={'name':name,'kind':'probe' if 'accept-probe-' in name else 'app','image_config_identity':custody.image}
    if launch['kind']=='app':
     mounts=[argv[i+1] for i,v in enumerate(argv) if v=='--mount'];assert len(mounts)==1
     mount=dict(part.split('=',1) for part in mounts[0].split(','));assert mount['type']=='bind' and mount['src']==mount['dst']
     launch['private_root']=mount['src']
    custody.launches.append(launch);custody.progress()
   process=popen(argv,*a,**kw);identity=proc(process.pid);custody.clients.append((process,identity))
   if launch:launch.update(client_pid=process.pid,client_identity=identity)
   custody.progress();return process
  subprocess.Popen=observed_popen
  original_start,original_close,original_hard=Fixture.start,Fixture.close,Fixture.hard_stop
  async def start(obj,*a,**kw):
   result=await original_start(obj,*a,**kw);assert obj.image_runtime is not None;custody.observe_vm(obj.image_runtime,'after-start');return result
  async def close(obj,*a,**kw):
   primary=None
   try:
    if obj.image_runtime and obj.image_runtime.name:custody.observe_vm(obj.image_runtime,'before-close')
   except BaseException as error:primary=error
   try:result=await original_close(obj,*a,**kw)
   except BaseException:raise
   if primary:raise primary
   return result
  def hard(obj,*a,**kw):
   if obj.image_runtime:custody.observe_vm(obj.image_runtime,'before-hard-stop')
   return original_hard(obj,*a,**kw)
  Fixture.start,Fixture.close,Fixture.hard_stop=start,close,hard
  native_start,native_stop=UpgradeRuntime.start,UpgradeRuntime.stop
  def upgrade_start(obj,*a,**kw):
   result=native_start(obj,*a,**kw);assert obj.owned_image is not None;custody.observe_vm(obj.owned_image,'after-start');return result
  def upgrade_stop(obj,*a,**kw):
   primary=None
   try:
    if obj.owned_image and obj.owned_image.name:custody.observe_vm(obj.owned_image,'before-stop')
   except BaseException as error:primary=error
   result=native_stop(obj,*a,**kw)
   if primary:raise primary
   return result
  UpgradeRuntime.start,UpgradeRuntime.stop=upgrade_start,upgrade_stop
  browser_launch=BrowserType.launch
  async def launch_browser(obj,*a,**kw):
   try:return await browser_launch(obj,*a,**kw)
   finally:
    for row in descendants(os.getpid()):
     if any(part in row['executable'] for part in ['chrome','chromium']):custody.chromium.append(row)
    custody.progress()
  BrowserType.launch=launch_browser
  sync_launch=SyncBrowserType.launch
  def launch_sync_browser(obj,*a,**kw):
   try:return sync_launch(obj,*a,**kw)
   finally:
    for row in descendants(os.getpid()):
     if any(part in row['executable'] for part in ['chrome','chromium']):custody.chromium.append(row)
    custody.progress()
  SyncBrowserType.launch=launch_sync_browser
  if self.job['name']=='openrig':
   import openrig_acceptance
   launch_rigs=openrig_acceptance.Rigs.launch;close_rigs=openrig_acceptance.Rigs.close
   def rigs_launch(obj,*a,**kw):
    obj.env.update(PYTHONDONTWRITEBYTECODE='1',NODE_DISABLE_COMPILE_CACHE='1')
    record={'home':str(obj.home),'mux':str(obj.mux),'processes':[],'terminal_seat_count':0};custody.rigs.append(record);custody.progress()
    try:
     result=launch_rigs(obj,*a,**kw);record['terminal_seat_count']=len(obj.entries)
     assert rig_processes(obj.home,obj.mux);return result
    finally:
     record['processes']=rig_processes(obj.home,obj.mux);custody.progress()
   def rigs_close(obj,*a,**kw):
    try:return close_rigs(obj,*a,**kw)
    finally:
     for row in custody.rigs:
      if row['home']==str(obj.home):row['after_original_close']=rig_processes(obj.home,obj.mux)
     custody.progress()
   openrig_acceptance.Rigs.launch,openrig_acceptance.Rigs.close=rigs_launch,rigs_close
 def finish(self):
  # All cleanup is confined to objects/names/PIDs issued by this exact child.
  from controlled_image_matrix import authoritative_absence
  for image in reversed(self.images):
   if image.name:
    try:image.stop()
    except BaseException as error:self.errors.append(type(error).__name__)
  for row in self.chromium:
   if same(row):
    if kill_known(row):self.errors.append('OwnedBrowserSurvivedOriginalClose')
  for rig in self.rigs:
   alive=rig_processes(rig['home'],rig['mux'])
   for row in alive:
    if same(row) and kill_known(row):self.errors.append('OwnedRigSurvivedOriginalClose')
  for process,identity in self.clients:
   if process.poll() is None:
    process.kill();process.wait(timeout=10);self.errors.append('OwnedClientSurvivedOriginalClose')
  observations=[]
  for launch in self.launches:
   for key in dict.fromkeys([launch.get('container_id'),launch['name']]):
    if key is None:continue
    result=subprocess.run(['docker','inspect',key],capture_output=True,timeout=30);assert authoritative_absence(result,key)
    observations.append({'identifier':key,'observed_absent':True})
  assert self.vm,'No actual image VM custody'
  if self.job['name']=='openrig':assert len(self.images)==2 and len(self.rigs)==1 and self.rigs[0]['terminal_seat_count']==2
  self.progress();assert not self.errors,self.errors
  return observations


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--job',required=True);parser.add_argument('--reviewed-plan-sha256',required=True);a=parser.parse_args()
 assert sha(a.plan)==a.reviewed_plan_sha256;plan=json.loads(a.plan.read_text());assert sha(__file__)==plan['frozen_inputs']['tests/image_ui_runtime.py']
 assert json.loads((a.plan.parent/'started.json').read_text())['plan_sha256']==a.reviewed_plan_sha256
 sys.path.insert(0,str(Path(plan['frozen'])/'tests'));job=next(v for v in plan['jobs'] if v['name']==a.job);custody=Custody(plan,job,a.plan.parent);error=None;cleanup=None;absence=[]
 try:custody.install();sys.argv=job['test_argv'];runpy.run_path(sys.argv[0],run_name='__main__')
 except BaseException as failure:error=failure
 finally:
  try:absence=custody.finish()
  except BaseException as failure:cleanup=failure
  Path(job['custody_report']).write_text(json.dumps({'schema':'adhd/image-ui-runtime-custody@1','passed':error is None and cleanup is None,
   'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'canonical_manifest_sha256':sha(plan['manifest']),
   'original_exception':type(error).__name__ if error else None,'cleanup_failure':type(cleanup).__name__ if cleanup else None,'cleanup_error_types':custody.errors,
   'actual_vm_observations':custody.vm,'browser_processes':custody.chromium,'rigs':custody.rigs,'independent_absence':absence},indent=2)+'\n')
 if error:raise error
 if cleanup:raise cleanup

if __name__=='__main__':main()
