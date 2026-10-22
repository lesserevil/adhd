#!/usr/bin/env python3
"""Cooperative model-service lease around one exact reviewed quality driver.

This lock only coordinates callers which honor it. It is not a network firewall
or proof that unrelated callers cannot contact the service. Root separately owns
the all-agent handoff and current-connection check before execution.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

MODEL='190996d1327f998b8f6a50510421800b7cf16f1cba8484baeba0ecd4b94e8cdd'
IMAGE='sha256:3d8ebe07d1b64ceab33030e09a9076e77754d3ed70a19fb0c36b0168d6b94d6f'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def regular(path,private=False):
 path=Path(path);info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
 assert not path.is_symlink() and path.absolute()==path.resolve()
 if private:assert info.st_mode&0o077==0
 return info

def private_write(path,value):
 raw=(json.dumps(value,indent=2)+'\n').encode();assert len(raw)<=16384
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
 directory=os.open(Path(path).parent,os.O_DIRECTORY|os.O_RDONLY|os.O_CLOEXEC)
 try:os.fsync(directory)
 finally:os.close(directory)


def acquire(path):
 path=Path(path);assert path.is_absolute() and path.resolve()==path
 for parent in path.parents:assert not parent.is_symlink()
 try:before=regular(path,True)
 except FileNotFoundError:before=None
 fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 try:
  opened=os.fstat(fd);after=regular(path,True);assert (opened.st_dev,opened.st_ino)==(after.st_dev,after.st_ino)
  if before:assert (opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino)
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return fd,(opened.st_dev,opened.st_ino)
 except BaseException:os.close(fd);raise


def validate_identity(raw,expected):
 assert isinstance(raw,list) and len(raw)==1;row=raw[0]
 assert row['Id']==expected['container_id']==MODEL and row['Image']==expected['image_config_identity']==IMAGE
 assert row['Name']==expected['name'] and re.fullmatch(r'/[A-Za-z0-9][A-Za-z0-9_.-]*',row['Name'])
 assert isinstance(row['State']['StartedAt'],str) and 0<len(row['State']['StartedAt'])<=80 and type(row['RestartCount']) is int and row['RestartCount']>=0
 assert row['State']['Running'] is True and row['State']['Pid']>0 and row['State']['Health']['Status']=='healthy'
 binding=[{'HostIp':'127.0.0.1','HostPort':'18770'}]
 assert row['NetworkSettings']['Ports']['8770/tcp']==binding and row['HostConfig']['PortBindings']['8770/tcp']==binding
 return {'container_id':row['Id'],'image_config_identity':row['Image'],'name':row['Name'],'running':True,'healthy':True,'host_vm_pid':row['State']['Pid'],'started_at':row['State']['StartedAt'],'restart_count':row['RestartCount'],'published_port':{'host_ip':'127.0.0.1','host_port':18770,'container_port':8770}}


def inspect_model(expected,docker):
 # Read-only Docker metadata; no GET/POST, healthcheck command or warmup.
 started=time.monotonic();deadline=started+5;process=None;selector=selectors.DefaultSelector();streams={};client={}
 try:
  process=subprocess.Popen([docker,'inspect',expected['container_id']],stdout=subprocess.PIPE,stderr=subprocess.PIPE);client['pid']=process.pid
  for stream in [process.stdout,process.stderr]:os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ);streams[stream]=bytearray()
  while selector.get_map():
   remaining=deadline-time.monotonic()
   if remaining<=0:raise TimeoutError('Model inspect metadata deadline')
   for key,_ in selector.select(min(.1,remaining)):
    data=os.read(key.fileobj.fileno(),min(8192,131073-sum(map(len,streams.values()))))
    if not data:selector.unregister(key.fileobj)
    else:streams[key.fileobj].extend(data);assert sum(map(len,streams.values()))<=131072
  assert process.wait(timeout=max(.001,deadline-time.monotonic()))==0
  result=validate_identity(json.loads(bytes(streams[process.stdout])),expected)
 except BaseException as error:
  error.owned_metadata_client=client;raise
 finally:
  selector.close()
  if process:
   if process.poll() is None:process.kill();process.wait(timeout=3)
   client['reaped']=process.poll() is not None
   for stream in [process.stdout,process.stderr]:stream.close()
 result['metadata_client']=client;return result


def validate_request(request):
 assert request['launcher_path']==str(Path(__file__).absolute()) and sha(__file__)==request['launcher_sha256']
 driver=Path(request['driver']);plan=Path(request['plan']);regular(driver);regular(plan)
 assert driver.name=='run.py' and plan.name=='plan.json' and driver.parent==plan.parent
 assert sha(driver)==request['driver_sha256'] and sha(plan)==request['plan_sha256']
 payload=json.loads(plan.read_text());assert payload['driver_sha256']==request['driver_sha256'] and payload['schema']=='adhd/live-quality-image-plan@1'
 python=Path(request['python']);assert str(python.resolve())==request['python_resolved'] and sha(python.resolve())==request['python_sha256']
 assert str(Path(sys.executable).resolve())==request['python_resolved'] and sha(Path(sys.executable).resolve())==request['python_sha256']
 docker=Path(request['docker']);assert docker.is_absolute() and str(docker.resolve())==request['docker_resolved'] and sha(docker.resolve())==request['docker_sha256']
 assert request['expected_model']['container_id']==MODEL and request['expected_model']['image_config_identity']==IMAGE
 return [str(python),'-B',str(driver),'--execute','--work',str(plan.parent),'--reviewed-plan-sha256',request['plan_sha256']]


def execute(path,digest):
 regular(path,True);assert sha(path)==digest;request=json.loads(path.read_text());argv=validate_request(request);work=path.parent
 assert not(work/'result.json').exists() and not(work/'driver.log').exists()
 fd=None;identity=None;before=None;after=None;child=None;failure=None;cleanup_failure=None;code=None;metadata_errors=[]
 try:
  fd,identity=acquire(Path(request['lease_path']));before=inspect_model(request['expected_model'],request['docker']);raw=(json.dumps({'request_sha256':digest,'parent_pid':os.getpid(),'driver_sha256':request['driver_sha256'],'plan_sha256':request['plan_sha256']})+'\n').encode();assert len(raw)<=4096
  os.ftruncate(fd,0);assert os.write(fd,raw)==len(raw);os.fsync(fd)
  # Recheck exact reviewed bytes after the metadata gate and before any child.
  assert validate_request(request)==argv
  logfd=os.open(work/'driver.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
  with os.fdopen(logfd,'wb') as output:
   child=subprocess.Popen(argv,stdout=output,stderr=subprocess.STDOUT,start_new_session=True);code=child.wait()
 except BaseException as error:
  failure=type(error).__name__
  if hasattr(error,'owned_metadata_client'):metadata_errors.append(error.owned_metadata_client)
 finally:
  if child is not None and child.poll() is None:
   try:
    os.killpg(child.pid,signal.SIGINT)
    try:child.wait(timeout=30)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
   except BaseException as error:cleanup_failure=type(error).__name__
  if before:
   try:
    after=inspect_model(request['expected_model'],request['docker']);assert {k:v for k,v in before.items() if k!='metadata_client'}=={k:v for k,v in after.items() if k!='metadata_client'}
   except BaseException as error:
    cleanup_failure=type(error).__name__
    if hasattr(error,'owned_metadata_client'):metadata_errors.append(error.owned_metadata_client)
  if fd is not None:
   try:
    info=regular(Path(request['lease_path']),True);assert (info.st_dev,info.st_ino)==identity
   except BaseException as error:cleanup_failure=type(error).__name__
   finally:os.close(fd)
  private_write(work/'result.json',{'schema':'adhd/cooperative-model-service-lease-result@1','passed':code==0 and not failure and not cleanup_failure,'request_sha256':digest,'driver_sha256':request['driver_sha256'],'plan_sha256':request['plan_sha256'],'child_argv':argv,'child_pid':child.pid if child else None,'child_returncode':code,'child_reaped':child is None or child.poll() is not None,'failure_type':failure,'cleanup_failure_type':cleanup_failure,'model_before':before,'model_after':after,'failed_metadata_clients':metadata_errors,'lease_acquired':identity is not None,'lease_released':fd is not None,'scope':'Cooperative lock held by parent throughout exact driver child. No model GET/POST/warmup preflight, service mutation or physical egress isolation. Root separately gates all-agent handoff/current connections; lease does not exclude unrelated callers.'})
 return 0 if code==0 and not failure and not cleanup_failure else 1


def prepare(a):
 work=a.work.absolute();assert not work.exists();plan=a.plan.absolute();driver=plan.parent/'run.py';regular(plan);regular(driver);p=json.loads(plan.read_text());assert sha(driver)==p['driver_sha256'];assert a.model_name.startswith('/')
 work.mkdir(mode=0o700);launcher=work/'launch.py';shutil_copy=Path(__file__).read_bytes();launcher.write_bytes(shutil_copy);launcher.chmod(0o600)
 request={'schema':'adhd/cooperative-model-service-lease-request@1','launcher_path':str(launcher),'launcher_sha256':sha(launcher),'driver':str(driver),'driver_sha256':sha(driver),'plan':str(plan),'plan_sha256':sha(plan),'python':sys.executable,'python_resolved':str(Path(sys.executable).resolve()),'python_sha256':sha(Path(sys.executable).resolve()),'docker':p['tools']['docker']['path'],'docker_resolved':p['tools']['docker']['resolved'],'docker_sha256':p['tools']['docker']['sha256'],'lease_path':str(a.lease_path.absolute()),'expected_model':{'container_id':MODEL,'image_config_identity':IMAGE,'name':a.model_name},'cooperative_all_agent_handoff_and_current_connection_gate_required':True,'status':'UNSTARTED_ROOT_REVIEW_REQUIRED'}
 private_write(work/'request.json',request);print(json.dumps({'request':str(work/'request.json'),'request_sha256':sha(work/'request.json'),'launcher_sha256':sha(launcher)}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--prepare',action='store_true');m.add_argument('--execute',action='store_true');p.add_argument('--work',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--model-name');p.add_argument('--lease-path',type=Path);p.add_argument('--request',type=Path);p.add_argument('--request-sha256');a=p.parse_args()
 if a.prepare:prepare(a)
 else:sys.exit(execute(a.request.absolute(),a.request_sha256))
