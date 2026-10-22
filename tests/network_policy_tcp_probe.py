#!/usr/bin/env python3
"""Bounded standalone protocol witness. Preparation never executes host/image code."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time

IMAGE = 'sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21'
ADMISSION_SHA = 'a78519154311d105ed84ed2e0887490b47d22807141eb2371163fc2c1a0b0f03'
BANNER = b'adhd-policy-v1\n'
STARTUP_READY_SECONDS = 30
PROBE_EXEC_SECONDS = 40
SERVER_LIFETIME_SECONDS = 180
# Fixed no-app fault fixture. Each connection gets the same declared bytes.
FAULT_SERVER = r'''
for {port, parts, delay} <- [
  {10001, ["adhd-", "policy-", "v1\n"], 10},
  {10002, ["wrong-policy-v1\n"], 0},
  {10003, ["adhd-policy"], 0},
  {10004, ["adhd-policy-v1\nEXTRA"], 0},
  {10005, [], 1500}
] do
  spawn_link(fn ->
    {:ok, socket} = :gen_tcp.listen(port, [:binary, active: false, reuseaddr: true])
    Stream.repeatedly(fn ->
      {:ok, client} = :gen_tcp.accept(socket)
      spawn(fn ->
        if parts == [], do: Process.sleep(delay)
        Enum.each(parts, fn part -> :gen_tcp.send(client, part); Process.sleep(delay) end)
        :gen_tcp.close(client)
      end)
    end) |> Stream.run()
  end)
end
IO.puts("fault-fixture-ready")
Process.sleep(:infinity)
'''
CASES = [('fragmented',10001,0,'REACHABLE\n'),('wrong',10002,2,''),
         ('short',10003,2,''),('extra-suffix-prefix-semantics',10004,0,'REACHABLE\n'),
         ('receive-timeout',10005,2,''),('refused',10006,0,'DENIED\n'),
         ('unroutable',9092,0,'DENIED\n')]

def sha(b): return hashlib.sha256(b).hexdigest()
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def read(path,cap=16*1024*1024):
 p=Path(path).absolute();assert p.resolve(strict=True)==p and not p.is_symlink()
 s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=cap
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  key=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
  assert key(os.fstat(fd))==key(s);b=bytearray()
  while True:
   chunk=os.read(fd,min(65536,cap+1-len(b)))
   if not chunk:break
   b.extend(chunk);assert len(b)<=cap
  assert key(os.fstat(fd))==key(s)==key(p.lstat());return bytes(b)
 finally:os.close(fd)
def inventory(root):
 root=Path(root).absolute();assert root.resolve(strict=True)==root and not root.is_symlink()
 files={};dirs=[]
 for x in sorted(root.rglob('*')):
  assert not x.is_symlink()
  if x.is_dir():dirs.append(x.relative_to(root).as_posix());continue
  assert x.is_file() and x.stat().st_uid==os.getuid();files[x.relative_to(root).as_posix()]=sha(read(x,256*1024*1024))
 return {'files':files,'directories':dirs}
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def probe_literal(raw):
 values=[]
 for node in ast.parse(raw).body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROBE' for t in node.targets):values.append(ast.literal_eval(node.value))
 assert len(values)==1 and isinstance(values[0],str)
 probe=values[0];assert ':gen_tcp.recv(socket, byte_size("adhd-policy-v1\\n"), 1000)' in probe
 assert '[:timeout, :ehostunreach, :enetunreach, :econnrefused]' in probe
 return probe

def remaining_seconds(deadline,cap=PROBE_EXEC_SECONDS):
 left=deadline-time.monotonic();assert left>0,'standalone witness lifetime exceeded'
 return min(cap,left)

def compile_binding(elf,proof,source,compiler_plan):
 data=read(elf,1048576);record=json.loads(read(proof)); assert record['passed'] is True
 # Explicit named compile product prevents binding an unrelated successful build.
 assert record['source_sha256']==sha(source) and record['elf_sha256']==sha(data)
 assert record['schema']=='adhd/cni-static-helper-compile@1' and record['plan_sha256']==sha(compiler_plan)
 assert record['exit_code']==0 and record['complete_input_closure_unchanged'] is True
 assert record['native_executions']==0 and record['container_starts']==0 and record['elf_bytes']==len(data)
 assert record['elf']=={'interpreter':None,'needed':[],'search':[]}
 assert record['stdout_sha256']==sha(b'') and record['stderr_sha256']==sha(b'')
 return data

def prepare(args):
 w=Path(args.prepare).absolute();assert not w.exists() and w.parent.resolve(strict=True)==w.parent
 root=Path('/home/horde/src/adhd');own=Path(__file__).parent
 admission=read(root/'verification/project-recovery/development40/admission/manifest.json');assert sha(admission)==ADMISSION_SHA
 adm=json.loads(admission);assert adm['passed'] and adm['image_config_identity']==IMAGE
 context=read(root/'_build/roadmap/final/container-context-40/manifest.json');assert sha(context)==adm['canonical_manifest_sha256']
 source=read(args.source);compiler_plan=read(args.compiler_plan);assert json.loads(compiler_plan)['source_sha256']==sha(source)
 ready=args.elf is not None;assert ready==(args.compile_proof is not None)
 inp=w/'inputs';inp.mkdir(parents=True,mode=0o700)
 originals={'driver.py':Path(__file__),'runner.py':own/'policy_kind_counter_run3.py','prepare.py':own/'policy_kind_counter_prepare.py',
            'policy.py':root/'tests/kafka_network_policy.py'}
 for name,path in originals.items():(inp/name).write_bytes(read(path))
 predecessor=own.parent/'_build/network-policy-static-protocol-e2-01'
 previous_plan=read(predecessor/'plan.json');previous_result=read(predecessor/'result.json');previous=json.loads(previous_plan);failed=json.loads(previous_result)
 assert sha(previous_plan)=='c3109a9dbab108cfdca813e09a8d6166c37c3349ca28163e59899ca2c3078c35'
 assert failed['passed'] is False and failed['inputs_unchanged'] and failed['all_issued_containers_absent']
 assert previous['cases']==json.loads(canon(CASES)) and previous['image']==IMAGE
 assert sha(source)==previous['inputs']['files']['tcp.c']
 assert sha(FAULT_SERVER.encode())==previous['inputs']['files']['fault-server.exs']
 assert sha(probe_literal(read(root/'tests/kafka_network_policy.py')).encode())==previous['inputs']['files']['original-probe.exs']
 for name,raw in {'previous-plan.json':previous_plan,'previous-result.json':previous_result,'previous-once.json':read(predecessor/'EXECUTION_STARTED')}.items():(inp/name).write_bytes(raw)
 for name,raw in {'admission.json':admission,'context-manifest.json':context,'tcp.c':source,'compiler-plan.json':compiler_plan,
                  'fault-server.exs':FAULT_SERVER.encode(),'original-probe.exs':probe_literal(read(root/'tests/kafka_network_policy.py')).encode()}.items():(inp/name).write_bytes(raw)
 helper=module(inp/'prepare.py','tcp_prepare')
 if ready:
  elf=compile_binding(args.elf,args.compile_proof,source,compiler_plan);assert helper.elf_dependencies(elf)==([],[])
  assert sha(elf)==previous['inputs']['files']['tcp'] and sha(read(args.compile_proof))==previous['inputs']['files']['compile-proof.json']
  (inp/'tcp').write_bytes(elf);(inp/'compile-proof.json').write_bytes(read(args.compile_proof));os.chmod(inp/'tcp',0o555)
 for p in inp.iterdir():
  if p.name!='tcp':os.chmod(p,0o444 if p.name=='fault-server.exs' else 0o400)
 base=module(inp/'runner.py','tcp_base');config=w/'docker-config';config.mkdir(mode=0o700);(config/'config.json').write_bytes(b'{}');os.chmod(config/'config.json',0o600)
 socket=Path('/run/docker.sock').stat();assert stat.S_ISSOCK(socket.st_mode)
 plan={'schema':'adhd/network-policy-static-protocol-probe@1','execution_ready':ready,'GO_required':True,'image':IMAGE,'nonce':os.urandom(16).hex(),
       'driver_sha256':sha(read(Path(__file__))),'inputs':inventory(inp),'admission_sha256':ADMISSION_SHA,
       'tools':{'docker':base.bind('/usr/bin/docker'),'python':base.bind('/home/horde/src/adhd/.venv/bin/python')},
       'socket':{'path':'/run/docker.sock','identity':[socket.st_dev,socket.st_ino]},'Python_stdlib':helper.tree('/usr/lib/python3.12'),
       'host_clock_proof':base.host_clock(),'bounds':{'containers':2,'server_lifetime_seconds':SERVER_LIFETIME_SECONDS,'startup_ready_seconds':STARTUP_READY_SECONDS,'probe_exec_seconds':PROBE_EXEC_SECONDS,'connect_timeout_ms':1000,'receive_timeout_ms':1000,'CPU':1,'memory':201326592,'pids':64,'output_each':65536,'output_total':1048576,'parallelism':1,'retries':0},
       'predecessor':{'plan_sha256':sha(previous_plan),'result_sha256':sha(previous_result),'false_preserved':True},'cases':CASES,'standalone_lifetime_reason':'Separate cold original Elixir CLI cross-checks need original exec40; lifetime180 bounds this no-app witness only. Original CNI Ready30/exec40/convergence60 unchanged; no retries/socket timeout extension.', 'scope':'No-app TCP fixture protocol only. Prefix15 LF semantics; extra suffix accepted. Four-source errno mappings retained, actual network-none refused/unroutable observations only; no inference of all four errno execution. No routes/Kafka/hub/CNI/application qualification.'}
 (w/'plan.json').write_bytes(canon(plan));return {'plan':str(w/'plan.json'),'sha256':sha(canon(plan)),'execution_ready':ready,'starts':0}

def verify(work,expected):
 w=Path(work).absolute();assert not w.is_symlink() and w.resolve(strict=True)==w
 raw=read(w/'plan.json');assert sha(raw)==expected;p=json.loads(raw)
 assert inventory(w/'inputs')==p['inputs'] and Path(__file__).absolute()==w/'inputs/driver.py' and sha(read(Path(__file__)))==p['driver_sha256']
 assert p['image']==IMAGE and sha(read(w/'inputs/admission.json'))==ADMISSION_SHA
 a=json.loads(read(w/'inputs/admission.json'));assert a['image_config_identity']==IMAGE and a['canonical_manifest_sha256']==sha(read(w/'inputs/context-manifest.json'))
 b=module(w/'inputs/runner.py','verified_tcp_base');helper=module(w/'inputs/prepare.py','verified_tcp_prepare')
 for tool in p['tools'].values():assert b.bind(tool['path'])==tool
 assert helper.tree('/usr/lib/python3.12')==p['Python_stdlib'] and b.host_clock()==p['host_clock_proof']
 s=Path(p['socket']['path']).stat();assert stat.S_ISSOCK(s.st_mode) and [s.st_dev,s.st_ino]==p['socket']['identity']
 assert read(w/'docker-config/config.json')==b'{}' and stat.S_IMODE((w/'docker-config/config.json').stat().st_mode)==0o600 and stat.S_IMODE((w/'docker-config').stat().st_mode)==0o700
 if p['execution_ready']:
  compile_binding(w/'inputs/tcp',w/'inputs/compile-proof.json',read(w/'inputs/tcp.c'),read(w/'inputs/compiler-plan.json'))
  assert helper.elf_dependencies(read(w/'inputs/tcp',1048576))==([],[])
 assert probe_literal(read(w/'inputs/policy.py')).encode()==read(w/'inputs/original-probe.exs')
 return p,b

def expected_probe(row,code,stdout):
 assert row['error'] is None and row['exit_code']==code and row['stdout']==stdout
 assert row['stderr']==''
 # Any Docker/exec infrastructure failure is never a network DENIED.
 assert row['exit_code'] not in (125,126,127,137)

class TCPRunner:
 def __init__(self,w,p,base):
  self.base=base;self.r=base.Runner(w,p);self.w=w;self.p=p;self.ledger=self.r.ledger
 def owned(self,v,item):
  assert (item['id'] is None or v['Id']==item['id']) and v['Name']=='/'+item['name'] and v['Image']==self.p['image']
  c=v['Config'];h=v['HostConfig'];assert c['Labels']['adhd-counter19-owner']==self.p['nonce'] and c['User']=='1000:1000'
  assert c['Entrypoint']==item['entrypoint'] and c['Cmd']==item['command'] and c['Healthcheck']['Test']==['NONE']
  assert h['ReadonlyRootfs'] and h['NetworkMode']=='none' and h['Memory']==201326592 and h['NanoCpus']==1000000000 and h['PidsLimit']==64
  assert h['CapDrop']==['ALL'] and not h['CapAdd'] and h['SecurityOpt']==['no-new-privileges'] and not h['Privileged'] and h['PidMode']=='' and h['IpcMode']=='private' and h['UsernsMode']==''
  assert not h.get('Devices') and not h.get('DeviceRequests') and not h.get('PortBindings')
  assert {m['Destination']:(m['Source'],m['RW'],m['Type']) for m in v['Mounts']}=={t:(s,False,'bind') for s,t in item['mounts']}
  return v
 def probe(self,item,label,host,port,code,out,crosscheck=True):
  assert time.monotonic()<item['deadline'];self.owned(self.r.inspect(item['id']),item)
  commands=[('native',['/probe/tcp','probe',host,str(port)])]
  if crosscheck:commands.append(('original-Elixir',['/usr/local/bin/elixir','-e',read(self.w/'inputs/original-probe.exs').decode(),'--',host,str(port)]))
  for kind,cmd in commands:
   row=self.r.docker(['exec','--user','1000:1000','--env','ERL_FLAGS=+S 1:1',item['id']]+cmd,seconds=remaining_seconds(item['deadline']))
   expected_probe(row,code,out);item['cases'].append({'case':label,'probe':kind,'passed':True,'exit_code':code,'stdout':out})
  assert time.monotonic()<item['deadline']
 def cleanup(self,item):
  primary=None
  try:
   v=self.r.inspect(item['id'] or item['name'],cleanup=True)
   if v is not None:
    self.owned(v,item)
    if item['id'] is None:item['id']=v['Id']
    if v['State']['Running']:
     kill=self.r.docker(['kill','--signal','KILL',item['id']],cleanup=True);assert kill['exit_code']==0
     waited=self.r.docker(['wait',item['id']],seconds=5,cleanup=True);assert waited['exit_code']==0 and waited['stdout'].strip()=='137'
     stopped=self.owned(self.r.inspect(item['id'],cleanup=True),item);assert not stopped['State']['Running'] and stopped['State']['ExitCode']==137
     item['requested_kill_exit_code']=137
  except BaseException as exc:primary=exc
  self.r.owned=self.owned
  try:self.r.cleanup(item)
  except BaseException as exc:
   if primary:primary.add_note('Independent removal/absence: '+repr(exc))
   else:primary=exc
  if primary:raise primary
 def container(self,kind):
  name='adhd-tcp-probe-'+self.p['nonce']+'-'+kind;assert self.r.inspect(name) is None
  image=self.r.docker(['image','inspect',self.p['image']]);assert image['exit_code']==0
  iv=json.loads(image['stdout']);assert len(iv)==1 and iv[0]['Id']==self.p['image'] and not iv[0]['Config'].get('Volumes')
  mounts=[(str(self.w/'inputs/tcp'),'/probe/tcp')]
  if kind=='static':entry=['/probe/tcp'];command=['serve']
  else:entry=['/usr/local/bin/elixir'];command=['/probe/fault-server.exs'];mounts.append((str(self.w/'inputs/fault-server.exs'),'/probe/fault-server.exs'))
  item={'name':name,'id':None,'mounts':mounts,'entrypoint':entry,'command':command,'observed_absent':False,'cases':[]};self.ledger.append(item)
  args=['create','--name',name,'--label','adhd-counter19-owner='+self.p['nonce'],'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--no-healthcheck','--cpus','1','--memory','192m','--pids-limit','64','--user','1000:1000','--env','ERL_FLAGS=+S 1:1','--entrypoint',entry[0]]
  for src,dst in mounts:args+=['--mount',f'type=bind,source={src},target={dst},readonly']
  args+=[self.p['image']]+command;error=None
  try:
   created=self.r.docker(args);assert created['exit_code']==0 and re.fullmatch('[a-f0-9]{64}',created['stdout'].strip());item['id']=created['stdout'].strip()
   self.owned(self.r.inspect(item['id']),item);begin=time.monotonic();item['deadline']=begin+SERVER_LIFETIME_SECONDS;ready_deadline=begin+STARTUP_READY_SECONDS
   start=self.r.docker(['start',item['id']]);assert start['exit_code']==0
   # Poll exact native probe until startup completes; never repeat a qualification case.
   while True:
    assert time.monotonic()<ready_deadline
    row=self.r.docker(['exec','--user','1000:1000',item['id'],'/probe/tcp','probe','127.0.0.1',str(8082 if kind=='static' else 10001)],seconds=remaining_seconds(ready_deadline))
    assert time.monotonic()<ready_deadline
    assert row['error'] is None and row['exit_code']==0 and row['stdout'] in ('REACHABLE\n','DENIED\n') and row['stderr']==''
    if row['stdout']=='REACHABLE\n':break
    assert time.monotonic()<ready_deadline;time.sleep(.05)
   item['startup_elapsed_seconds']=time.monotonic()-begin;assert item['startup_elapsed_seconds']<STARTUP_READY_SECONDS
   initial=self.owned(self.r.inspect(item['id']),item);assert initial['State']['Running'];item['started_at']=initial['State']['StartedAt']
   if kind=='static':
    for port in (8082,9092,9093):self.probe(item,'static-port-'+str(port),'127.0.0.1',port,0,'REACHABLE\n')
    for command in ([],['probe','bad-address','8082'],['probe','127.0.0.1','0'],['probe','127.0.0.1','65536'],['probe','127.0.0.1','abc']):
     row=self.r.docker(['exec','--user','1000:1000',item['id'],'/probe/tcp']+command,seconds=remaining_seconds(item['deadline']))
     expected_probe(row,3,'');item['cases'].append({'case':'invalid-input','argv':command,'passed':True,'exit_code':3})
   else:
    for label,port,code,out in CASES:self.probe(item,label,'192.0.2.1' if label=='unroutable' else '127.0.0.1',port,code,out)
   final=self.owned(self.r.inspect(item['id']),item);assert final['State']['Running'] and final['State']['StartedAt']==item['started_at']
   assert time.monotonic()<item['deadline'];item['passed']=True
  except BaseException as exc:error=exc
  finally:
   # Reuse reviewed independent removal/strict-absence logic with this exact custody predicate.
   try:self.cleanup(item)
   except BaseException as cleanup:
    if error:error.add_note('Cleanup: '+repr(cleanup))
    else:error=cleanup
   item.pop('deadline',None)
  if error:raise error

def execute(w,p,base):
 assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
 assert p['execution_ready'],'Actual ELF and compile proof required'
 fd=os.open(w/'EXECUTION_STARTED',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:os.write(fd,canon({'plan_sha256':sha(read(w/'plan.json'))}));os.fsync(fd)
 finally:os.close(fd)
 fd=os.open(w,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 (w/'run').mkdir(mode=0o700);(w/'raw').mkdir(mode=0o700);r=TCPRunner(w,p,base);result={'schema':'adhd/network-policy-static-protocol-result@1','passed':False,'image_config_identity':p['image'],'helper_sha256':p['inputs']['files']['tcp'],'source_sha256':p['inputs']['files']['tcp.c'],'compile_proof_sha256':p['inputs']['files']['compile-proof.json'],'plan_sha256':sha(read(w/'plan.json')),'containers':r.ledger,'scope':p['scope']};error=None
 try:r.container('static');r.container('faults');result['passed']=True
 except BaseException as exc:error=exc;result['error']=repr(exc);result['notes']=getattr(exc,'__notes__',[])
 finally:
  result['inputs_unchanged']=inventory(w/'inputs')==p['inputs'];result['all_issued_containers_absent']=all(x['observed_absent'] for x in r.ledger);result['output_bytes']=r.r.used
  result['passed']=result['passed'] and result['inputs_unchanged'] and result['all_issued_containers_absent'];(w/'result.json').write_bytes(canon(result))
 if error:raise error
 return result

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--prepare');parser.add_argument('--source');parser.add_argument('--compiler-plan');parser.add_argument('--elf');parser.add_argument('--compile-proof');parser.add_argument('--work');parser.add_argument('--plan-sha256');parser.add_argument('--verify-only',action='store_true');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 if args.prepare:
  assert args.source and args.compiler_plan and not args.execute and not args.verify_only;print(json.dumps(prepare(args),sort_keys=True))
 else:
  assert args.work and args.plan_sha256 and args.execute!=args.verify_only
  w=Path(args.work).absolute();p,b=verify(w,args.plan_sha256);print(json.dumps(execute(w,p,b) if args.execute else {'verified':True,'execution_ready':p['execution_ready'],'runtime_starts':0},sort_keys=True))
