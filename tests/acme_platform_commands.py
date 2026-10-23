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
   assert record['start_ticks'] is not None or process.poll() is not None
   return record
  except BaseException:
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   process.wait(timeout=5);raise
 def stop(self,record):
  process=record['process']
  if record['closed']:return
  if process.poll() is None:
   assert ticks(process.pid)==record['start_ticks'],'Owned CLI PID reused'
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=1)
   except subprocess.TimeoutExpired:
    assert ticks(process.pid)==record['start_ticks']
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    process.wait(timeout=5)
  else:process.wait(timeout=5)
  record['exit_code']=process.returncode
  assert ticks(process.pid)!=record['start_ticks'] or record['start_ticks'] is None,'Owned CLI remains'
  for handle in [process.stdin,process.stdout,process.stderr]:
   if handle:handle.close()
  record['closed']=True
 def __call__(self,argv,*,env=None,input=None,capture=False,check=True,timeout=30,sensitive=False):
  assert 0<timeout<=180
  if self.phase_deadline is not None:
   remaining=self.phase_deadline-time.monotonic();assert remaining>0,'Shared platform phase deadline'
   timeout=min(timeout,remaining)
  record=self.issue(argv,env);process=record['process'];primary=None
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
   process.wait(timeout=remaining)
   output,error=bytes(buffers[process.stdout]),bytes(buffers[process.stderr])
   result=subprocess.CompletedProcess(argv,process.returncode,output,error)
   self.operations.append({'argv_sha256':record['argv_sha256'],'exit_code':process.returncode,
                          'stdout_sha256':hashlib.sha256(output).hexdigest(),'stderr_sha256':hashlib.sha256(error).hexdigest(),
                          'sensitive':sensitive,'raw_output_retained':False})
   if check:assert result.returncode==0,'Owned CLI failed: '+argv[0]
   return result
  except BaseException as error:
   primary=error;raise
  finally:
   try:self.stop(record)
   except BaseException as cleanup:
    if primary:primary.add_note('CLI cleanup failed: '+type(cleanup).__name__)
    else:raise
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
