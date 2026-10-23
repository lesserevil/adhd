"""Closed-tool child custody for future reviewed ACME platform execution.

No subprocess starts until run/start is called. Parent plan verification supplies
exact tool, socket, private Docker configuration and closed inline kubeconfig.
"""
import hashlib
import os
from pathlib import Path
import signal
import selectors
import subprocess
import time


def ticks(pid):
 try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:return None


def group_members(group):
 result={}
 for path in Path('/proc').iterdir():
  if not path.name.isdigit():continue
  try:fields=(path/'stat').read_text().rsplit(')',1)[1].split()
  except (FileNotFoundError,ProcessLookupError):continue
  if int(fields[2])==group:result[int(path.name)]=fields[19]
 return result


def exited_without_reaping(pid):
 return os.waitid(os.P_PID,pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)


def exit_code(observation):
 return observation.si_status if observation.si_code==os.CLD_EXITED else -observation.si_status


class Commands:
 def __init__(self,tools,environment,work):
  assert set(tools)=={'docker','kind','kubectl'}
  assert set(environment)=={'PATH','HOME','DOCKER_HOST','DOCKER_CONFIG','KUBECONFIG','LANG'}
  assert environment['DOCKER_HOST'].startswith('unix://')
  assert environment['PATH']=='/usr/bin:/bin'
  self.tools={k:str(Path(v).absolute()) for k,v in tools.items()}
  self.environment=dict(environment);self.work=Path(work);self.children=[];self.operations=[];self.phase_deadline=None
 def prepare(self,argv,env):
  assert isinstance(argv,list) and argv and argv[0] in self.tools
  assert all(isinstance(v,str) and '\0' not in v for v in argv)
  admitted={'ADHD_HUB_IMAGE','ADHD_UID','ADHD_GID','ADHD_PORT','ADHD_CONFIG_DIR','ADHD_DATA_DIR','KIND_EXPERIMENTAL_DOCKER_NETWORK'}
  assert not set(env or {})-admitted
  return [self.tools[argv[0]],*argv[1:]],{**self.environment,**(env or {})}
 def issue(self,argv,env=None,*,persistent=False):
  actual,environment=self.prepare(argv,env)
  process=subprocess.Popen(actual,stdin=subprocess.DEVNULL if persistent else subprocess.PIPE,stdout=subprocess.DEVNULL if persistent else subprocess.PIPE,stderr=subprocess.DEVNULL if persistent else subprocess.PIPE,
                           env=environment,start_new_session=True)
  record={'pid':process.pid,'start_ticks':None,'argv_sha256':hashlib.sha256('\0'.join(actual).encode()).hexdigest(),
          'process':process,'closed':False,'exit_code':None,'long_lived_cli_output_discarded':persistent}
  try:
   record['start_ticks']=ticks(process.pid);self.children.append(record)
   assert record['start_ticks'] is not None,'Owned CLI start identity unavailable'
   return record
  except BaseException:
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   process.wait(timeout=5);raise
 def stop(self,record):
  process=record['process']
  if record['closed']:return
  # Hold the leader unreaped, including when already a zombie, until groupkill.
  # Its reserved PID/PGID prevents signalling a later unrelated process group.
  assert ticks(process.pid)==record['start_ticks'],'Owned CLI PID reused or prematurely reaped'
  observed={}
  for sig in [signal.SIGTERM,signal.SIGKILL]:
   assert ticks(process.pid)==record['start_ticks']
   observed.update(group_members(process.pid))
   try:os.killpg(process.pid,sig)
   except ProcessLookupError:pass
   if sig==signal.SIGTERM:time.sleep(.1)
  deadline=time.monotonic()+5
  while exited_without_reaping(process.pid) is None:
   assert time.monotonic()<deadline,'Owned CLI leader did not exit';time.sleep(.01)
  # No more signals after waitpid releases the original reserved PID/PGID.
  process.wait(timeout=max(.001,deadline-time.monotonic()))
  record['exit_code']=process.returncode
  while time.monotonic()<deadline:
   if all(ticks(pid)!=start for pid,start in observed.items()):break
   time.sleep(.01)
  else:raise AssertionError('Observed owned CLI group member remains')
  assert not group_members(process.pid),'Owned CLI process group remains'
  record['observed_group_members']=[{'pid':pid,'start_ticks':start,'observed_absent':True} for pid,start in sorted(observed.items())]
  for handle in [process.stdin,process.stdout,process.stderr]:
   if handle:handle.close()
  record['closed']=True
 def __call__(self,argv,*,env=None,input=None,capture=False,check=True,timeout=30,sensitive=False):
  assert 0<timeout<=180
  if self.phase_deadline is not None:
   remaining=self.phase_deadline-time.monotonic();assert remaining>0,'Shared platform phase deadline'
   timeout=min(timeout,remaining)
  record=self.issue(argv,env);process=record['process'];primary=None
  operation={'argv_sha256':record['argv_sha256'],'exit_code':None,'sensitive':sensitive,'raw_output_retained':False}
  index=len(self.operations);self.operations.append(operation);buffers={}
  try:
   assert input is None or isinstance(input,bytes) and len(input)<=2*1024*1024
   pending=memoryview(input or b'');buffers={process.stdout:bytearray(),process.stderr:bytearray()}
   deadline=time.monotonic()+timeout
   with selectors.DefaultSelector() as selector:
    for handle in buffers:
     os.set_blocking(handle.fileno(),False);selector.register(handle,selectors.EVENT_READ)
    if pending:
     os.set_blocking(process.stdin.fileno(),False);selector.register(process.stdin,selectors.EVENT_WRITE)
    else:process.stdin.close()
    while selector.get_map():
     remaining=deadline-time.monotonic()
     if remaining<=0:raise subprocess.TimeoutExpired(argv,timeout)
     for key,events in selector.select(min(.1,remaining)):
      handle=key.fileobj
      if events & selectors.EVENT_WRITE:
       try:n=os.write(handle.fileno(),pending[:16384])
       except BlockingIOError:continue
       pending=pending[n:]
       if not pending:selector.unregister(handle);handle.close()
      else:
       try:block=os.read(handle.fileno(),16384)
       except BlockingIOError:continue
       if not block:selector.unregister(handle)
       else:
        buffers[handle].extend(block)
        assert len(buffers[handle])<=4*1024*1024,'Owned CLI output bound'
   remaining=deadline-time.monotonic()
   if remaining<=0:raise subprocess.TimeoutExpired(argv,timeout)
   while (completion:=exited_without_reaping(process.pid)) is None:
    if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
    time.sleep(.01)
   code=exit_code(completion)
   output,error=bytes(buffers[process.stdout]),bytes(buffers[process.stderr])
   result=subprocess.CompletedProcess(argv,code,output,error)
   operation.update(exit_code=code,stdout_sha256=hashlib.sha256(output).hexdigest(),stderr_sha256=hashlib.sha256(error).hexdigest())
   if check:assert result.returncode==0,'Owned CLI failed: '+argv[0]
   return result
  except BaseException as error:
   primary=error;operation['failure_type']=type(error).__name__;raise
  finally:
   if not sensitive and buffers:
    try:
     body=bytes(buffers.get(process.stdout,b''))+b'\nSTDERR\n'+bytes(buffers.get(process.stderr,b''))
     path=self.work/('cli-'+str(index)+'.log')
     with path.open('xb') as log:log.write(body)
     path.chmod(0o600);operation.update(raw_output_retained=True,private_log=str(path),private_log_sha256=hashlib.sha256(body).hexdigest())
    except BaseException as capture_error:
     operation['log_error']=type(capture_error).__name__
     if primary:primary.add_note('CLI log capture failed: '+type(capture_error).__name__)
     else:primary=capture_error
   try:self.stop(record)
   except BaseException as cleanup:
    if primary:primary.add_note('CLI cleanup failed: '+type(cleanup).__name__)
    else:raise
   if primary is not None and 'log_error' in operation and operation.get('failure_type') is None:raise primary
 def start(self,argv):
  # The sole long-lived CLI is private loopback kubectl port-forward.
  assert argv[0]=='kubectl' and 'port-forward' in argv and '--address=127.0.0.1' in argv
  return self.issue(argv,persistent=True)
 def close(self):
  errors=[]
  for record in reversed(self.children):
   try:self.stop(record)
   except BaseException as error:errors.append(error)
  if errors:raise BaseExceptionGroup('Owned CLI closure failed',errors)
 def evidence(self):
  return {'children':[{k:v for k,v in row.items() if k!='process'} for row in self.children],
          'operations':self.operations,'all_closed':all(row['closed'] for row in self.children)}
