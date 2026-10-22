#!/usr/bin/env python3
"""One owned original Pod utility startup; no app, CNI or route qualification."""
import argparse,ast,hashlib,json,os,re,selectors,stat,subprocess,sys,time
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plain(p):
 p=Path(p).absolute();s=p.lstat();assert p.resolve(strict=True)==p and stat.S_ISREG(s.st_mode)and s.st_nlink==1;return p

def save(p,v):
 with Path(p).open('x')as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 Path(p).chmod(0o600)

def original(raw):
 tree=ast.parse(raw);serve=next(ast.literal_eval(n.value)for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SERVE'for t in n.targets))
 pod=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='pod');scope={'SERVE':serve};exec(compile(ast.Module(body=[pod],type_ignores=[]),'original-pod','exec'),scope)
 value=scope['pod']('broker','kafka','diagnostic','pinned')['spec'];c=value['containers'][0]
 assert c['command']==['elixir','-e',serve]and c['env']==[{'name':'ERL_FLAGS','value':'+S 1:1'}]
 assert c['resources']['limits']=={'cpu':'1','memory':'192Mi'}and value['restartPolicy']=='Never'
 assert value['securityContext']=={'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000}
 assert c['securityContext']=={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
 return {'command':c['command'],'env':c['env'],'resources':c['resources'],'security':value['securityContext'],'container_security':c['securityContext']}

def absence(r,identifier):
 return r['code']==1 and r['stdout'].strip()in(b'',b'[]')and re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier),r['stderr'].decode(errors='replace').strip())is not None

def env(plan,work):
 v={k:x for k,x in os.environ.items()if not k.startswith(('DOCKER_','PYTHON','LD_','DYLD_'))}
 v.update(DOCKER_HOST='unix://'+plan['socket']['path'],DOCKER_CONFIG=str(work/'docker-config'),PATH='/usr/bin:/bin');return v

def argv(plan):
 return ['create','--name',plan['name'],'--label','adhd-utility-owner='+plan['nonce'],'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000','--memory','192m','--memory-swap','192m','--cpus','1','--no-healthcheck','--env','ERL_FLAGS=+S 1:1','--entrypoint','elixir',plan['image']]+plan['pod']['command'][1:]

def verify(work,p):
 assert work.resolve(strict=True)==work and not work.is_symlink();assert sha(plain(work/'driver.py'))==p['driver_sha256']==sha(plain(__file__))
 expected={'driver.py','plan.json','original.py','admission.json','docker-config/config.json'}
 actual=set();dirs=set()
 for f in work.rglob('*'):
  assert not f.is_symlink()
  s=f.lstat();assert stat.S_ISREG(s.st_mode)or stat.S_ISDIR(s.st_mode)
  if f.is_dir():dirs.add(str(f.relative_to(work)))
  elif not f.relative_to(work).parts[0]=='runtime'and f.name!='execution.started':actual.add(str(f.relative_to(work)))
 assert actual==expected and dirs=={'docker-config','runtime'}
 for k,v in p['inputs'].items():assert sha(plain(work/k))==v
 assert original((work/'original.py').read_bytes())==p['pod']
 for t in p['tools'].values():assert str(Path(t['path']).resolve(strict=True))==t['realpath']and sha(t['realpath'])==t['sha256']
 assert str(Path(sys.executable).absolute())==p['tools']['python']['path']and Path('/proc/self/exe').resolve()==Path(p['tools']['python']['realpath'])
 s=Path(p['socket']['path']).stat();assert stat.S_ISSOCK(s.st_mode)and [s.st_dev,s.st_ino]==p['socket']['identity']
 assert p['image']=='sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21'
 assert json.loads((work/'admission.json').read_bytes())['image_config_identity']==p['image']
 return True

class Runner:
 def __init__(self,work,p):self.work=work;self.p=p;self.rows=[];self.cid=None;self.issued=False;self.cleanup=[];self.cleaning=False;self.usage={'normal':{'calls':0,'bytes':0},'cleanup':{'calls':0,'bytes':0}}
 def run(self,args,seconds=10):
  budget=self.usage['cleanup'if self.cleaning else 'normal'];assert budget['calls']<(10 if self.cleaning else 40)and budget['bytes']<524288
  cap=min(65536,524288-budget['bytes']);budget['calls']+=1
  process=subprocess.Popen([self.p['tools']['docker']['path']]+args,env=env(self.p,self.work),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  sel=selectors.DefaultSelector();data={'stdout':bytearray(),'stderr':bytearray()};deadline=time.monotonic()+seconds;error=None
  for name in data:sel.register(getattr(process,name),selectors.EVENT_READ,name)
  try:
   while sel.get_map():
    left=deadline-time.monotonic();assert left>0,'Diagnostic Docker command deadline'
    for key,_ in sel.select(min(left,.1)):
     block=os.read(key.fileobj.fileno(),8192)
     if not block:sel.unregister(key.fileobj)
     else:
      room=cap-sum(map(len,data.values()));data[key.data]+=block[:room];assert len(block)<=room,'Diagnostic output cap'
   code=process.wait(timeout=max(.01,deadline-time.monotonic()))
  except BaseException as e:
   error=e;process.kill();process.wait(timeout=5);raise
  finally:
   sel.close();process.stdout.close();process.stderr.close()
   row={'args':args,'code':process.returncode,'failure':type(error).__name__ if error else None,'stdout':bytes(data['stdout']),'stderr':bytes(data['stderr'])}
   budget['bytes']+=sum(map(len,data.values()))
   number=len(self.rows);self.rows.append({k:v for k,v in row.items()if k not in ('stdout','stderr')})
   for stream in ('stdout','stderr'):
    f=self.work/'runtime'/(str(number)+'-'+stream);f.write_bytes(row[stream]);f.chmod(0o600);self.rows[-1][stream]={'bytes':len(row[stream]),'sha256':sha(f)}
  return row
 def inspect(self,identifier):
  r=self.run(['inspect',identifier])
  if absence(r,identifier):return None
  assert r['code']==0;rows=json.loads(r['stdout']);assert len(rows)==1;return rows[0]
 def owned(self,x):
  assert x['Id']==self.cid and x['Name']=='/'+self.p['name']and x['Image']==self.p['image']and x['Config']['Labels']['adhd-utility-owner']==self.p['nonce'];return x
 def perform(self):
  assert self.inspect(self.p['name'])is None
  image=self.run(['image','inspect',self.p['image']]);assert image['code']==0 and json.loads(image['stdout'])[0]['Id']==self.p['image']
  self.issued=True;r=self.run(argv(self.p),30);assert r['code']==0;self.cid=r['stdout'].decode().strip();assert re.fullmatch('[a-f0-9]{64}',self.cid)
  x=self.owned(self.inspect(self.cid));cfg=x['Config'];host=x['HostConfig'];assert cfg['Healthcheck']['Test']==['NONE']and cfg['User']=='1000:1000'and cfg['Entrypoint']==['elixir']and cfg['Cmd']==self.p['pod']['command'][1:]
  assert 'ERL_FLAGS=+S 1:1'in cfg['Env']and host['NetworkMode']=='none'and host['ReadonlyRootfs']and host['Memory']==192*1024*1024 and host['MemorySwap']==192*1024*1024 and host['NanoCpus']==1000000000 and not x['Mounts']and not host['Privileged']and host['PidMode']==''and host['IpcMode']=='private'and host['CapDrop']==['ALL']and host['SecurityOpt']==['no-new-privileges']and not host.get('PortBindings')
  r=self.run(['start',self.cid]);assert r['code']==0;deadline=time.monotonic()+30;observations=[]
  for i in range(6):
   x=self.owned(self.inspect(self.cid));observations.append({'elapsed':30-max(0,deadline-time.monotonic()),'state':x['State']})
   if not x['State']['Running']:break
   remaining=deadline-time.monotonic()
   if remaining<=0:break
   command=['exec',self.cid,'sh','-eu','-c','cat /proc/net/tcp; for f in memory.events memory.current memory.max; do printf "\\n%s\\n" "$f"; cat "/sys/fs/cgroup/$f"; done']
   self.run(command,min(10,remaining));time.sleep(max(0,min(5,deadline-time.monotonic())))
  terminal=self.owned(self.inspect(self.cid));self.run(['logs',self.cid]);return {'observations':observations,'pre_cleanup_state':terminal['State'],'cause':'Only OOMKilled or scoped memory.events can support OOM; exit137 alone cannot. Docker scope does not retrospectively prove deleted Kind Pod cause.'}
 def finish(self):
  self.cleaning=True
  if not self.issued:return []
  identifier=self.cid or self.p['name'];errors=[];foreign=False;x=None
  try:
   x=self.inspect(identifier)
   if x is not None:
    if self.cid:self.owned(x)
    else:assert x['Name']=='/'+self.p['name']and x['Config']['Labels']['adhd-utility-owner']==self.p['nonce']and x['Image']==self.p['image'];self.cid=x['Id'];identifier=self.cid
  except BaseException as e:
   errors.append(type(e).__name__);foreign=x is not None
  try:
   if not foreign:
    if x is not None and x['State']['Running']:
     r=self.run(['kill','--signal','KILL',identifier]);assert r['code']==0
     r=self.run(['wait',identifier]);assert r['code']==0 and r['stdout'].strip()==b'137'
    r=self.run(['rm','--force',identifier]);assert r['code']==0 or absence(r,identifier)
    assert self.inspect(identifier)is None and self.inspect(self.p['name'])is None
    self.cleanup.append({'identifier':identifier,'name':self.p['name'],'observed_absent':True})
  except BaseException as e:errors.append(type(e).__name__)
  if foreign:self.cleanup.append({'identifier':identifier,'foreign_not_removed':True,'observed_absent':False})
  return errors

def execute(work,digest):
 assert sys.flags.isolated and sha(work/'plan.json')==digest;p=json.loads((work/'plan.json').read_bytes());verify(work,p)
 fd=os.open(work/'execution.started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w')as f:f.write(digest);f.flush();os.fsync(f.fileno())
 fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 runner=Runner(work,p);error=None;observation=None
 try:observation=runner.perform()
 except BaseException as e:error=type(e).__name__
 finally:
  cleanup=runner.finish()
  try:verify(work,p);unchanged=True
  except BaseException:unchanged=False
  save(work/'runtime/result.json',{'schema':'adhd/policy-utility-startup-diagnostic@1','diagnostic_completed':error is None and not cleanup and unchanged,'scope':p['scope'],'failure_type':error,'cleanup_errors':cleanup,'cleanup':runner.cleanup,'observations':observation,'rows':runner.rows,'output_budget_usage':runner.usage,'inputs_unchanged':unchanged,'plan_sha256':digest,'resource_owner':{'name':p['name'],'cid':runner.cid},'routes_qualified':0})
 return 0 if error is None and not cleanup and unchanged else 1

def prepare(work,root):
 assert not work.exists();work.mkdir(parents=True,mode=0o700);(work/'runtime').mkdir(mode=0o700);(work/'docker-config').mkdir(mode=0o700)
 for src,dst in [(Path(__file__),'driver.py'),(root/'tests/kafka_network_policy.py','original.py'),(root/'verification/project-recovery/development40/admission/manifest.json','admission.json')]: (work/dst).write_bytes(plain(src).read_bytes())
 (work/'docker-config/config.json').write_text('{}');nonce=os.urandom(16).hex();socket=Path('/var/run/docker.sock');s=socket.stat()
 p={'schema':'adhd/policy-utility-startup-plan@1','executed':False,'root_GO_required':True,'name':'adhd-policy-utility-'+nonce[:16],'nonce':nonce,'image':'sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21','pod':original((work/'original.py').read_bytes()),'limits':{'startup_seconds':30,'per_command_bytes':65536,'normal_bytes':524288,'cleanup_reserved_bytes':524288,'total_bytes':1048576,'normal_commands':40,'cleanup_commands':10},'driver_sha256':sha(work/'driver.py'),'inputs':{n:sha(work/n)for n in ['original.py','admission.json','docker-config/config.json']},'tools':{n:{'path':str(Path(v).absolute()),'realpath':str(Path(v).resolve()),'sha256':sha(Path(v).resolve())}for n,v in [('python',sys.executable),('docker','/usr/bin/docker')]},'socket':{'path':str(socket),'identity':[s.st_dev,s.st_ino]},'scope':'One original192Mi/CPU1/+S1:1 utility on exact image; Docker HEALTHCHECK disabled. No hubapp/Kafka/CNI/routes/provider qualification. No automatic cap change or retry.'}
 save(work/'plan.json',p);verify(work,p);print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json')}))

if __name__=='__main__':
 a=argparse.ArgumentParser();g=a.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--execute',action='store_true');g.add_argument('--verify-only',action='store_true');a.add_argument('--work',type=Path,required=True);a.add_argument('--root',type=Path);a.add_argument('--plan-sha256');v=a.parse_args();w=v.work.absolute()
 if v.prepare:prepare(w,v.root.absolute())
 elif v.verify_only:assert sha(w/'plan.json')==v.plan_sha256;verify(w,json.loads((w/'plan.json').read_bytes()));print('{"verified":true,"executed":false}')
 else:sys.exit(execute(w,v.plan_sha256))
