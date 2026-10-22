#!/usr/bin/env python3
"""Closed no-app counter19 probe. Preparation allowed; execution needs root GO.

No host /proc target access. The synthetic ENV-only resume runs as UID1000
inside its already-owned container, fixed PID1, descriptor-only SIGCONT.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

IMAGE='sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21'
ENV=['HOME=/tmp','PATH=/usr/local/bin:/usr/bin:/bin','LANG=C','ERL_FLAGS=+S 2:2','ERL_FLAGS=+S 1:1']
LIMIT=1048576

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def read(path,cap=16*1024*1024):
 p=Path(path);assert p.is_absolute()and not p.is_symlink()and p.resolve(strict=True)==p
 s=p.lstat();assert stat.S_ISREG(s.st_mode)and s.st_size<=cap
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  key=lambda a:(a.st_dev,a.st_ino,a.st_mode,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
  assert key(os.fstat(fd))==key(s);out=bytearray()
  while True:
   b=os.read(fd,min(65536,cap+1-len(out)))
   if not b:break
   out.extend(b);assert len(out)<=cap
  assert key(os.fstat(fd))==key(s)==key(p.lstat());return bytes(out)
 finally:os.close(fd)

def inventory(root):
 root=Path(root);assert root.resolve(strict=True)==root and not root.is_symlink()
 files={};dirs=[]
 for p in sorted(root.rglob('*')):
  assert not p.is_symlink(),'redirected input'
  if p.is_dir():dirs.append(p.relative_to(root).as_posix());continue
  assert p.is_file()and p.stat().st_nlink==1 and p.stat().st_uid==os.getuid();files[p.relative_to(root).as_posix()]=sha(read(p))
 return {'files':files,'directories':dirs}

def bind(path):
 p=Path(path).absolute();real=p.resolve(strict=True);return {'path':str(p),'realpath':str(real),'sha256':sha(read(real,256*1024*1024))}

def missing(result,identifier):
 return result['exit_code']==1 and result['stdout'].strip()in ('','[]')and re.fullmatch(r'(?i:(?:error(?: response from daemon)?:\s*)?no such (?:object|container):\s*)'+re.escape(identifier),result['stderr'].strip())is not None

def prepare(work,probe_elf=None):
 # Authored preparation only; no compiler/Docker calls in this path.
 import importlib.util
 helper=Path(__file__).with_name('policy_kind_counter_prepare.py').absolute()
 spec=importlib.util.spec_from_file_location('counter_prepare',helper);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
 root=Path(__file__).parents[1].absolute();base=root/'_build/policy-kind-counter19-source02'
 work=Path(work).absolute();assert not work.exists()and work.parent.resolve(strict=True)==work.parent
 source=Path(__file__).with_name('policy_kind_counter_probe2.c').absolute()
 frozen=work/'inputs';frozen.mkdir(parents=True,mode=0o700)
 for name,path in {'driver.py':Path(__file__).absolute(),'prepare.py':helper,'probe.c':source,
                   'policy_kind_counter.c':source.with_name('policy_kind_counter.c'),
                   'gate':base/'startup-gate','compile.json':base/'compile.json','source-plan.json':base/'plan.json',
                   'policy.py':source.with_name('kafka_network_policy.py')}.items():
  (frozen/name).write_bytes(read(path));os.chmod(frozen/name,0o555 if name=='gate' else 0o400)
 original=p.serve((frozen/'policy.py').read_text());nonce=os.urandom(16).hex()
 argv=p.gate_argv(nonce,original);config=work/'docker-config';config.mkdir(mode=0o700);(config/'config.json').write_bytes(b'{}');os.chmod(config/'config.json',0o600)
 compile=json.loads((frozen/'source-plan.json').read_bytes());command=compile['future_compile_argv'].copy();command[command.index('-o')+1]=str(work/'counter-probe');command[-1]=str(frozen/'probe.c')
 ready=probe_elf is not None
 if ready:
  data=read(Path(probe_elf).absolute(),1048576);assert p.elf_dependencies(data)==([],[])
  (frozen/'probe').write_bytes(data);os.chmod(frozen/'probe',0o555)
 sock=Path('/run/docker.sock');s=sock.stat();assert stat.S_ISSOCK(s.st_mode)
 cases=[{'mode':'--selftest','exit_code':0}]+[{'mode':mode,'exit_code':70,'stderr':'counter19 rejected: '+reason+'\n'}for mode,reason in [('--reject-leading-zero','decimal'),('--reject-overflow','decimal'),('--reject-number-tail','decimal'),('--reject-environment','ERL_FLAGS'),('--reject-path','unsupported-cgroup-layout')]]+[{'mode':'--clock','exit_code':0}]
 plan={'schema':'adhd/counter19-same-UID-noapp-probe@2','execution_ready':ready,'execution_GO_required':True,'image':IMAGE,'nonce':nonce,'driver_sha256':sha(read(Path(__file__).absolute())),
       'inputs':inventory(frozen),'tools':{'python':bind('/home/horde/src/adhd/.venv/bin/python'),'docker':bind('/usr/bin/docker')},'Python_stdlib':p.tree('/usr/lib/python3.12'),
       'socket':{'path':str(sock),'identity':[s.st_dev,s.st_ino]},'host_time_namespace_inode':os.stat('/proc/self/ns/time').st_ino,
       'config_sha256':sha(b'{}'),'cases':cases,'gate_argv_sha256':p.vector_hash(argv),'ordered_env_sha256':p.environment_hash(ENV),'SERVE_sha256':sha(original.encode()),
       'future_compile_argv':command,'future_compile_environment':compile['future_compile_environment'],'parent_gate_sha256':sha(read(frozen/'gate')),
       'bounds':{'parallelism':1,'retries':0,'container_count':2,'memory_bytes':201326592,'pids':64,'CPU':1,'command_output_bytes':65536,'total_output_bytes':LIMIT,'container_seconds':30,'release_seconds':10,'native_case_seconds':2},
       'scope':'Native SHA/parse; fixed read-only image facts; synthetic native ENV exec witness. No app/shebang/Kind/OOM/routes. Extra tiny resume process INSIDE ENV-only container is not memory-causal evidence.',
       'source_plan':'Original source02 remains unchanged; compiler closure/source dependency review required before future compile. This driver NEVER compiles.'}
 (work/'plan.json').write_bytes(canon(plan));return {'plan':str(work/'plan.json'),'sha256':sha(canon(plan)),'execution_ready':ready,'runtime_starts':0}

def verify(work,expected):
 work=Path(work).absolute();assert not work.is_symlink()and work.resolve(strict=True)==work
 planraw=read(work/'plan.json',8*1024*1024);assert sha(planraw)==expected;plan=json.loads(planraw)
 assert inventory(work/'inputs')==plan['inputs'];assert sha(read(work/'inputs/driver.py'))==plan['driver_sha256']
 assert Path(__file__).absolute()==work/'inputs/driver.py'and sha(read(Path(__file__).absolute()))==plan['driver_sha256'],'use actual frozen driver'
 for tool in plan['tools'].values():assert bind(tool['path'])==tool
 assert read(work/'docker-config/config.json')==b'{}'and sha(b'{}')==plan['config_sha256']
 assert stat.S_IMODE((work/'docker-config').stat().st_mode)==0o700 and stat.S_IMODE((work/'docker-config/config.json').stat().st_mode)==0o600
 s=Path(plan['socket']['path']).stat();assert stat.S_ISSOCK(s.st_mode)and[s.st_dev,s.st_ino]==plan['socket']['identity']
 assert os.stat('/proc/self/ns/time').st_ino==plan['host_time_namespace_inode']
 import importlib.util
 spec=importlib.util.spec_from_file_location('closed_counter_prepare',work/'inputs/prepare.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 assert helper.tree('/usr/lib/python3.12')==plan['Python_stdlib']
 return plan

class Runner:
 def __init__(self,work,plan):
  self.work=work;self.plan=plan;self.used=[0,0];self.index=0;self.ledger=[]
  self.env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','HOME':str(work),
            'DOCKER_HOST':'unix://'+plan['socket']['path'],'DOCKER_CONFIG':str(work/'docker-config')}
 def run(self,args,seconds=5,cleanup=False):
  quota=1 if cleanup else 0;assert self.used[quota]<LIMIT//2
  if not cleanup:assert inventory(self.work/'inputs')==self.plan['inputs']
  for tool in self.plan['tools'].values():assert bind(tool['path'])==tool
  sock=Path(self.plan['socket']['path']).stat();assert stat.S_ISSOCK(sock.st_mode)and[sock.st_dev,sock.st_ino]==self.plan['socket']['identity']
  assert read(self.work/'docker-config/config.json')==b'{}'
  self.index+=1;tag=f'{self.index:03d}';deadline=time.monotonic()+seconds
  proc=subprocess.Popen(args,cwd=self.work/'run',env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  output=[bytearray(),bytearray()];sel=selectors.DefaultSelector()
  for index,pipe in enumerate((proc.stdout,proc.stderr)):os.set_blocking(pipe.fileno(),False);sel.register(pipe,selectors.EVENT_READ,index)
  error=None
  try:
   while sel.get_map():
    remaining=deadline-time.monotonic();assert remaining>0,'command timeout'
    for key,_ in sel.select(min(0.1,remaining)):
     raw=os.read(key.fileobj.fileno(),65536)
     if not raw:sel.unregister(key.fileobj);continue
     output[key.data].extend(raw);self.used[quota]+=len(raw)
     assert sum(map(len,output))<=65536 and self.used[quota]<=LIMIT//2,'output budget'
   code=proc.wait(timeout=max(0.001,deadline-time.monotonic()))
  except BaseException as exc:
   error=exc
   if proc.poll()is None:os.killpg(proc.pid,signal.SIGKILL)
   proc.wait(timeout=3);code=proc.returncode
  finally:
   sel.close();proc.stdout.close();proc.stderr.close()
  row={'argv':list(args),'exit_code':code,'stdout':output[0].decode(errors='replace'),'stderr':output[1].decode(errors='replace'),'error':repr(error)if error else None}
  (self.work/'raw'/f'{tag}.json').write_bytes(canon(row))
  if error:raise error
  return row
 def docker(self,args,seconds=5,cleanup=False):return self.run([self.plan['tools']['docker']['path']]+args,seconds,cleanup)
 def inspect(self,identifier,cleanup=False):
  row=self.docker(['inspect',identifier],cleanup=cleanup)
  if row['exit_code']!=0:
   if missing(row,identifier):return None
   raise AssertionError('non-authoritative inspect failure')
  values=json.loads(row['stdout']);assert len(values)==1;return values[0]
 def owned(self,value,item):
  assert re.fullmatch('[a-f0-9]{64}',value['Id'])and(item['id']is None or value['Id']==item['id'])and value['Name']=='/'+item['name']and value['Image']==self.plan['image']
  assert value['Config']['Labels']['adhd-counter19-owner']==self.plan['nonce']
  host=value['HostConfig'];assert host['ReadonlyRootfs']and host['NetworkMode']=='none'and host['Memory']==201326592 and host['PidsLimit']==64 and host['NanoCpus']==1000000000
  assert host['CapDrop']==['ALL']and not host.get('CapAdd')and host['SecurityOpt']==['no-new-privileges']and value['Config']['User']=='1000:1000'
  assert not host['Privileged']and host['PidMode']==''and host['IpcMode']=='private'and host['UsernsMode']==''
  assert not host.get('Devices')and not host.get('DeviceRequests')and not host.get('PortBindings')
  assert value['Config']['Entrypoint']==['/probe/counter-probe']and value['Config']['Cmd']==item['command']
  assert value['Config']['Healthcheck']['Test']==['NONE']
  expected=item['mounts'];actual=value['Mounts'];assert len(actual)==len(expected)
  assert {m['Destination']:(m['Source'],m['RW'],m['Type'])for m in actual}=={t:(s,False,'bind')for s,t in expected}
  return value
 def cleanup(self,item):
  primary=None;foreign=False
  try:
   value=self.inspect(item['id']or item['name'],cleanup=True)
   if value is not None:
    try:
     self.owned(value,item)
     if item['id']is None:item['id']=value['Id']
    except BaseException:foreign=True;raise
  except BaseException as exc:primary=exc
  # Issued fullID/name is ours after successful create; independent removal even
  # initial inspect failed, but never a positively inspected foreign object.
  if not foreign and item['id']is not None:
   try:
    row=self.docker(['rm','--force','--volumes',item['id']],cleanup=True)
    item['remove_exit_code']=row['exit_code']
    if row['exit_code']!=0 and not missing(row,item['id']):raise AssertionError('remove failed')
   except BaseException as exc:
    if primary is None:primary=exc
    else:primary.add_note('Independent removal: '+repr(exc))
  try:
   assert self.inspect(item['id']or item['name'],cleanup=True)is None
   assert self.inspect(item['name'],cleanup=True)is None
   item['observed_absent']=True
  except BaseException as exc:
   item['observed_absent']=False
   if primary is None:primary=exc
  if primary:raise primary
 def container(self,kind):
  inp=self.work/'inputs';name='adhd-counter19-'+self.plan['nonce']+'-'+kind
  mounts=[(str(inp/'probe'),'/probe/counter-probe')]
  if kind=='env':mounts.extend([(str(inp/'gate'),'/adhd-diagnostic/startup-gate'),(str(inp/'probe'),'/usr/local/bin/elixir')])
  assert self.inspect(name)is None
  image=self.docker(['image','inspect',self.plan['image']]);assert image['exit_code']==0;images=json.loads(image['stdout']);assert len(images)==1 and images[0]['Id']==self.plan['image']and not images[0]['Config'].get('Volumes')
  item={'name':name,'id':None,'mounts':mounts,'command':['--image-fact']if kind=='facts'else['--env-launcher',self.plan['nonce']],'observed_absent':False};self.ledger.append(item)
  args=['create','--name',name,'--label','adhd-counter19-owner='+self.plan['nonce'],'--read-only','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--no-healthcheck','--cpus','1','--memory','192m','--pids-limit','64','--user','1000:1000','--entrypoint','/probe/counter-probe']
  for source,target in mounts:args+=['--mount',f'type=bind,source={source},target={target},readonly']
  args+=[self.plan['image']]+(['--image-fact']if kind=='facts'else['--env-launcher',self.plan['nonce']])
  original=None
  try:
   created=self.docker(args);assert created['exit_code']==0 and re.fullmatch('[a-f0-9]{64}',created['stdout'].strip());item['id']=created['stdout'].strip()
   self.owned(self.inspect(item['id']),item)
   begin=time.monotonic();release_ns=time.monotonic_ns()+10_000_000_000;deadline=begin+30
   started=self.docker(['start',item['id']]);assert started['exit_code']==0
   if kind=='env':
    while True:
     assert time.monotonic()<min(begin+5,deadline)
     logs=self.docker(['logs',item['id']]);assert logs['exit_code']==0
     if '"kind":"gate-ready"'in logs['stdout']:break
     time.sleep(0.05)
    gate_rows=[json.loads(x)for x in logs['stdout'].splitlines()];assert len(gate_rows)==1 and gate_rows[0]['ordered_env_sha256']==self.plan['ordered_env_sha256']and gate_rows[0]['nonce']==self.plan['nonce']
    before=self.owned(self.inspect(item['id']),item);assert before['State']['Running']and before['State']['Pid']>0
    resumed=self.docker(['exec','--user','1000:1000',item['id'],'/probe/counter-probe','--resume-gate',self.plan['nonce'],self.plan['parent_gate_sha256'],self.plan['gate_argv_sha256'],self.plan['ordered_env_sha256'],str(self.plan['host_time_namespace_inode']),str(release_ns)],seconds=min(3,max(0.001,deadline-time.monotonic())))
    assert resumed['exit_code']==0 and time.monotonic_ns()<release_ns
    item['resume']=json.loads(resumed['stdout']);assert item['resume']['signal']=='pidfd-SIGCONT'and item['resume']['pid']==1 and item['resume']['identity_rechecked']
    after=self.owned(self.inspect(item['id']),item);assert after['State']['StartedAt']==before['State']['StartedAt']
   waited=self.docker(['wait',item['id']],seconds=max(0.001,deadline-time.monotonic()));assert waited['exit_code']==0 and waited['stdout'].strip()=='0'
   state=self.owned(self.inspect(item['id']),item);assert not state['State']['Running']and state['State']['ExitCode']==0
   logs=self.docker(['logs',item['id']]);assert logs['exit_code']==0;rows=[json.loads(x)for x in logs['stdout'].splitlines()]
   if kind=='env':
    assert len(rows)==2 and rows[-1]['passed']and rows[-1]['ordered_env_sha256']==self.plan['ordered_env_sha256']and rows[-1]['SERVE_sha256']==self.plan['SERVE_sha256']and rows[-1]['ERL_FLAGS']==['+S 2:2','+S 1:1']
   else:
    assert len(rows)==2 and rows[0]['kind']=='image-executable-fact'and not rows[0]['script_executed']
    assert rows[1]['kind']=='clock-fact'and rows[1]['time_namespace_inode']==self.plan['host_time_namespace_inode']
   item['outputs']=rows;item['natural_exit_code']=0
  except BaseException as exc:original=exc
  finally:
   try:self.cleanup(item)
   except BaseException as cleanup:
    if original:original.add_note('Cleanup: '+repr(cleanup))
    else:original=cleanup
  if original:raise original
  return item

def execute(work,plan):
 assert plan['execution_ready'],'actual probe ELF not admitted'
 assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'use Python -I -S -B'
 marker=work/'EXECUTION_STARTED';fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  payload=canon({'plan_sha256':sha(read(work/'plan.json')),'driver_sha256':plan['driver_sha256']});assert os.write(fd,payload)==len(payload);os.fsync(fd)
 finally:os.close(fd)
 d=os.open(work,os.O_RDONLY|os.O_DIRECTORY);os.fsync(d);os.close(d)
 (work/'run').mkdir(mode=0o700);(work/'raw').mkdir(mode=0o700);runner=Runner(work,plan);result={'passed':False,'native_cases':[],'containers':runner.ledger,'scope':plan['scope']};error=None
 try:
  for case in plan['cases']:
   row=runner.run([str(work/'inputs/probe'),case['mode']],seconds=2);assert row['exit_code']==case['exit_code']
   if 'stderr'in case:assert row['stderr']==case['stderr']and row['stdout']==''
   elif case['mode']=='--selftest':assert json.loads(row['stdout'])=={'kind':'native-selftest','sha_vectors':4,'exact_path_vectors':1,'number_vectors':2,'passed':True}
   else:assert json.loads(row['stdout'])['time_namespace_inode']==plan['host_time_namespace_inode']
   result['native_cases'].append({'mode':case['mode'],'passed':True})
  runner.container('facts');runner.container('env');result['passed']=True
 except BaseException as exc:error=exc;result['error']=repr(exc);result['notes']=getattr(exc,'__notes__',[])
 finally:
  result['inputs_unchanged']=inventory(work/'inputs')==plan['inputs'];result['output_bytes']=runner.used
  result['all_issued_containers_absent']=all(x['observed_absent']for x in runner.ledger)
  if not result['inputs_unchanged']or not result['all_issued_containers_absent']:result['passed']=False
  (work/'result.json').write_bytes(canon(result))
 if error:raise error
 return result

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--prepare');parser.add_argument('--probe-elf');parser.add_argument('--work');parser.add_argument('--plan-sha256');parser.add_argument('--execute',action='store_true');parser.add_argument('--verify-only',action='store_true');args=parser.parse_args()
 if args.prepare:
  assert not args.execute and not args.verify_only;print(json.dumps(prepare(args.prepare,args.probe_elf),sort_keys=True))
 else:
  assert args.work and args.plan_sha256 and(args.execute!=args.verify_only)
  work=Path(args.work).absolute();plan=verify(work,args.plan_sha256)
  print(json.dumps(execute(work,plan)if args.execute else {'verified':True,'execution_ready':plan['execution_ready'],'native_starts':0},sort_keys=True))
