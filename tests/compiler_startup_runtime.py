#!/usr/bin/env python3
"""Once-only diagnostic child: unchanged first SDK startup, public compiler trace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import controlled_sdk_runtime as sdk
from compiler_startup_observer import diagnostic_image_argv


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
class DiagnosticReadyObserved(Exception):pass


def trace_prefix(path,expected):
 before=path.lstat();assert stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and before.st_mode&0o077==0
 assert [before.st_dev,before.st_ino]==expected and 0<before.st_size<=1048832
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  opened=os.fstat(fd);assert (opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino)
  remaining=before.st_size;parts=[]
  while remaining:
   body=os.read(fd,min(remaining,65536));assert body;parts.append(body);remaining-=len(body)
  after=path.lstat();assert (after.st_dev,after.st_ino)==(before.st_dev,before.st_ino)
  raw=b''.join(parts);assert raw.startswith(b'installed\t');return raw
 finally:os.close(fd)


class CompilerCustody(sdk.base.Custody):
 def __init__(self,*args,**kw):super().__init__(*args,**kw);self.observation=None;self.original_image_failure=None
 def capture(self,obj):
  begin=time.monotonic();deadline=begin+15
  def reader(argv,requested):
   # Shared host network contains other projects' sockets. Observe only our
   # actual PID1 FDs; never request the namespace-wide TCP tables.
   if argv[-1]=='cat /proc/1/net/tcp /proc/1/net/tcp6; ls -l /proc/1/fd':argv=argv[:-3]+['ls','-l','/proc/1/fd']
   return sdk.bounded(argv,min(deadline,requested))
  diag=sdk.startup_diagnostics(self,obj,reader)
  if diag.get('owned_identity_verified'):
   event=obj._controlled_custody_attempt;event.update(container_name=diag['container_name'],container_id=diag['container_id'],host_vm_pid=diag['state']['Pid'])
   for launch in self.launches:
    if launch.get('name')==diag['container_name']:launch['container_id']=diag['container_id']
   self.ledger.write_text(json.dumps(self.launches,indent=2)+'\n')
  result={'diagnostic':diag,'trace_snapshot':None,'snapshot_failure_type':None,'maximum_collection_seconds':15,'maximum_client_reap_grace_seconds':3}
  try:
   assert diag['owned_identity_verified'] and diag['actual_beam_pid1_observed'] and diag['actual_canonical_manifest_matched'] and diag['all59_actual_app_hashes_matched']
   cid=diag['container_id'];path=obj.root/'compiler-events.tsv';fds=diag['observations']['passive_namespace_listeners'];assert fds['returncode']==0
   matches=re.findall(r'\b(\d+) -> '+re.escape(str(path))+r'$',fds['stdout'],re.M);assert len(matches)==1
   target='/proc/1/fd/'+matches[0]
   def identity():
    row=reader(['docker','exec',cid,'stat','-L','-c','%d %i',target],min(deadline,time.monotonic()+3));assert row['returncode']==0
    result.setdefault('fd_identity_clients',[]).append(row.get('client_process'));values=row['stdout'].decode().split();assert len(values)==2 and all(v.isdecimal() for v in values);return list(map(int,values))
   first=identity();raw=trace_prefix(path,first);assert identity()==first
   snapshot=Path(self.job['trace_snapshot']);assert not snapshot.exists();snapshot.write_bytes(raw);snapshot.chmod(0o600)
   result['trace_snapshot']={'path':str(snapshot),'sha256':hashlib.sha256(raw).hexdigest(),'prefix_bytes':len(raw),'complete_line_prefix':raw.endswith(b'\n'),'actual_container_id':cid,'actual_namespace_pid':1,'actual_fd':int(matches[0]),'held_fd_identity':first,'same_owned_fd_open_before_and_after_read':True,'scope':'Captured bounded prefix while actual VM logger owns same open FD; logger may append later. No trace completion or SDK qualification claim.'}
  except BaseException as error:result['snapshot_failure_type']=type(error).__name__
  result['elapsed_seconds']=time.monotonic()-begin;self.observation=result;return result
 def start(self,original,obj,*args,**kw):
  def observed(instance,*a,**k):
   recorder=sdk.OriginalHealthCalls(original,instance)
   try:
    with recorder:result=original(instance,*a,**k)
   except BaseException as error:
    if self.is_image(instance):self.original_image_failure={'type':type(error).__name__,'message':str(error)};self.capture(instance)
    raise
   else:
    if self.is_image(instance):self.capture(instance);raise DiagnosticReadyObserved('Diagnostic stops at first image Ready; no SDK flow after adoption')
    return result
   finally:instance._controlled_custody_attempt['original_health_calls']=recorder.evidence()
  return super().start(observed,obj,*args,**kw)
 def install(self):
  super().install();old=subprocess.Popen;custody=self
  def launch(argv,*args,**kw):
   if isinstance(argv,list) and argv[:2]==['docker','run'] and custody.image in argv:
    command=json.loads(argv[-1]);assert len(command)==2 and command[0]=='serve';root=Path(command[1]).parent
    source=Path(custody.plan['frozen'])/'tests/compiler_startup_trace.exs';assert sha(source)==custody.plan['frozen_inputs']['tests/compiler_startup_trace.exs']
    path=root/'compiler-tracer.exs';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as out:out.write(source.read_bytes());out.flush();os.fsync(out.fileno())
    argv=diagnostic_image_argv(argv,custody.image,root,sha(source))
   return old(argv,*args,**kw)
  subprocess.Popen=launch


def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--reviewed-plan-sha256',required=True);a=p.parse_args();assert sha(a.plan)==a.reviewed_plan_sha256
 plan=json.loads(a.plan.read_text());assert sha(__file__)==plan['frozen_inputs']['tests/compiler_startup_runtime.py'];assert json.loads((a.plan.parent/'started.json').read_text())['plan_sha256']==a.reviewed_plan_sha256
 job=plan['job'];c=CompilerCustody(plan,job,Path(job['custody_report']));primary=None;errors=[]
 try:c.install();sys.argv=job['test_argv'];runpy.run_path(sys.argv[0],run_name='__main__')
 except BaseException as error:primary=error
 finally:
  for obj in reversed(c.instances):
   try:c.cleanup_one(obj)
   except BaseException as error:errors.append(type(error).__name__)
  absence=[]
  for row in c.launches:
   for key in dict.fromkeys([row.get('container_id'),row.get('name')]):
    if key:
     try:assert c.absent(key);absence.append({'identifier':key,'observed_absent':True})
     except BaseException as error:errors.append(type(error).__name__)
  observation_ok=bool(c.observation and c.observation['trace_snapshot'] and not c.observation['snapshot_failure_type'])
  observed=observation_ok and primary is not None and not errors and not c.errors
  Path(job['custody_report']).write_text(json.dumps({'schema':'adhd/public-compiler-startup-diagnostic@1','diagnostic_observation_complete':observed,'sdk_qualified':False,'primary_exception_type':type(primary).__name__ if primary else None,'original_image_start_failure':c.original_image_failure,'image_config_identity':c.image,'artifact_sha256':plan['artifact_sha256'],'runtime_events':c.events,'observation':c.observation,'cleanup_error_types':errors+c.errors,'owned_container_absence':absence,'scope':'Unchanged first native producer/setup and first actual image Hub.start30s only; diagnostic stops even if Ready. No whole SDK case, new provider/model warmup or product performance fix.'},indent=2)+'\n')
 if not observed:
  if primary:raise primary
  raise AssertionError('Diagnostic unavailable; preserve report')

if __name__=='__main__':main()
