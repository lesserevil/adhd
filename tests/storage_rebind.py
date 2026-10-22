#!/usr/bin/env python3
"""Actual offline CLI rebind/cold-server checks, with isolated native fsync kills."""
import argparse,hashlib,json,os,shutil,signal,socket,subprocess,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,separators=(',',':')));p.chmod(0o600)
def request(base,path,body=None,token=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urlopen(Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=h),timeout=5) as r:return json.load(r)
def call(base,c,agent,cmd,mid):
 b={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':mid,'role':'ROLE_USER','parts':[{'data':cmd}]}}}
 r=request(base,'/a2a',b,c['agents'][agent]);assert 'error' not in r,r
 return r['result']['message']['parts'][0]['data']
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def copied(source,target):
 shutil.copytree(source,target);target.chmod(0o700)
 assert not (target/'hub.json.transaction').exists()
 return target/'hub.json'
def command_for(p,mid):
 r=json.loads(Path(str(p)+'.stores').read_text());stores=[]
 original=Path(r['config_file']).parent
 for project,e in sorted(r['projects'].items()):
  if not e['initialized']:continue
  old=Path(e['storage_anchor']);assert old.is_relative_to(original)
  current=p.parent/old.relative_to(original)
  stores.append({'project_id':project,'store_path':str(current),'expected_route_generation':e['generation'],'snapshot_sha256':sha(str(current)+'.snapshot'),'checkpoint_sha256':sha(current)})
 return {'config_file':str(p),'expected_server_id':r['server_id'],'expected_config_sha256':sha(p),'expected_config_journal_sha256':sha(str(p)+'.journal') if Path(str(p)+'.journal').exists() else None,'expected_registry_sha256':sha(str(p)+'.stores'),'expected_recovery_journal_sha256':sha(str(p)+'.recovery'),'expected_marker_sha256':sha(str(p)+'.stores.marker'),'stores':stores,'message_id':mid,'confirm':True,'confirm_stopped':True}
def product_hashes(cmd):return {m['project_id']:{'checkpoint':sha(m['store_path']),'snapshot':sha(m['store_path']+'.snapshot')} for m in cmd['stores']}
def cli(command,arg,root,name,env=None,error=None):
 r=subprocess.run(command+[json.dumps(arg,separators=(',',':'))],capture_output=True,timeout=150,env=env)
 (root/(name+'.stdout')).write_bytes(r.stdout);(root/(name+'.stderr')).write_bytes(r.stderr);print(name,'exit',r.returncode,flush=True)
 if error:
  assert r.returncode==1 and not r.stdout,(name,r.returncode)
  obj=json.loads(r.stderr);assert set(obj)=={'error'} and set(obj['error'])=={'code','message'} and obj['error']['code']==error,(name,obj)
  return {'exit_code':r.returncode,'code':error,'stderr_json_only':True}
 assert r.returncode==0,(name,r.returncode,r.stderr[-2000:])
 return json.loads(r.stdout)
def start(command,p,root,name):
 out=(root/(name+'.stdout')).open('wb');err=(root/(name+'.stderr')).open('wb')
 process=subprocess.Popen(command+[json.dumps(['serve',str(p)])],stdout=out,stderr=err,start_new_session=True)
 base='http://127.0.0.1:'+str(json.loads(p.read_text())['port']);deadline=time.monotonic()+100
 try:
  while time.monotonic()<deadline:
   assert process.poll() is None,(name,'startup exited')
   try:
    request(base,'/health');print(name,'ready',flush=True);return process,base,[out,err]
   except Exception:time.sleep(.1)
  raise AssertionError('startup timeout')
 except BaseException:
  if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
  out.close();err.close();raise
def stop(process,handles):
 if process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
 for h in handles:h.close()
def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--command',required=True);ap.add_argument('--artifact',type=Path,required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--history-source',type=Path);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
 command=json.loads(a.command);work=a.work.resolve();work.mkdir(parents=True,exist_ok=False);work.chmod(0o700);checks=[];active=None
 try:
  origin=work/'origin';p=copied(a.source,origin);c=json.loads(p.read_text());c['store_path']=str(origin/'unused-old-anchor'/'hub.dets');c['port']=port();c['public_url']='http://127.0.0.1:'+str(c['port']);c['matcher']=None;c['eventing']['enabled']=False;write(p,c)
  cmd=command_for(p,'prepare-own-origin');before=product_hashes(cmd);config=sha(p)
  first=cli(command,['rebind-storage',cmd],work,'origin-rebind');assert first['rebound'] and first['registry_revision']==1
  assert product_hashes(cmd)==before and sha(p)==config;checks.append({'id':'initial-complete-three-project-rebind','passed':True,'projects':first['projects']})
  process,base,handles=start(command,p,work,'origin-hub');active=(process,handles);accepted={}
  for color in ['red','blue']:
   project='project-'+color;pub=color+'-a';recipient=color+'-b'
   sub=call(base,c,recipient,{'op':'subscribe','project_id':project,'mode':'raw'},'portable-sub-'+color)['subscription']
   cmdpub={'op':'publish','project_id':project,'text':'portable '+color+' fact','source':{'kind':'other','id':'portable','item_id':color}}
   r=call(base,c,pub,cmdpub,'portable-pub-'+color);private=call(base,c,pub,{'op':'send','project_id':project,'recipient_id':recipient,'text':'private '+color},'portable-private-'+color)['delivery']
   rows=call(base,c,recipient,{'op':'poll','project_id':project},'poll-before-'+color)['deliveries'];delivery=next(d for d in rows if d.get('publication_id')==r['publication']['id'])
   call(base,c,recipient,{'op':'ack','project_id':project,'delivery_ids':[delivery['id']]},'portable-ack-'+color)
   accepted[color]={'publication':r,'command':cmdpub,'delivery_id':delivery['id'],'private_id':private['id'],'subscription_id':sub['id']}
  stop(*active);active=None;checks.append({'id':'real-two-project-publication-private-delivery-ack-fixture','passed':True})
  moved=work/'moved';mp=copied(origin,moved);shutil.rmtree(origin);assert not origin.exists()
  assert not Path(c['store_path']).parent.exists();backup=work/'pre-rebind';shutil.copytree(moved,backup)
  cmd=command_for(mp,'portable-move');before=product_hashes(cmd);config=sha(mp);rawreg=json.loads(Path(str(mp)+'.stores').read_text())
  result=cli(command,['rebind-storage',cmd],work,'moved-rebind');assert result['registry_revision']==2
  assert product_hashes(cmd)==before and sha(mp)==config
  reg=json.loads(Path(str(mp)+'.stores').read_text())
  for project,e in rawreg['projects'].items():
   now=reg['projects'][project];assert {k:v for k,v in e.items() if k!='storage_anchor'}=={k:v for k,v in now.items() if k!='storage_anchor'}
  assert cli(command,['rebind-storage',cmd],work,'moved-exact-replay')==result
  bad={**cmd,'expected_registry_sha256':'0'*64};cli(command,['rebind-storage',bad],work,'changed-mid',error='IDEMPOTENCY_CONFLICT')
  cli(command,['rebind-storage',None],work,'invalid-shape',error='INVALID_PARAMS')
  checks.append({'id':'portable-bytes-identities-epochs-preserved-exact-receipt','passed':True,'product_hashes_before':before,'product_hashes_after':product_hashes(cmd)})
  process,base,handles=start(command,mp,work,'moved-hub');active=(process,handles)
  for color,item in accepted.items():
   project='project-'+color;pub=color+'-a';recipient=color+'-b'
   assert call(base,c,pub,item['command'],'portable-pub-'+color)==item['publication']
   assert call(base,c,pub,item['command'],'portable-new-mid-'+color)==item['publication']
   rows=call(base,c,recipient,{'op':'poll','project_id':project},'poll-after-'+color)['deliveries']
   assert item['delivery_id'] not in [d['id'] for d in rows] and item['private_id'] in [d['id'] for d in rows]
   facts=call(base,c,pub,{'op':'search','project_id':project,'query':'portable'},'search-after-'+color)['publications'];assert item['publication']['publication']['id'] in [v['id'] for v in facts]
  stop(*active);active=None
  assert cli(command,['rebind-storage',cmd],work,'receipt-after-advanced-writes')==result
  checks.append({'id':'actual-moved-cold-start-facts-source-mid-retries-and-acks','passed':True,'old_anchor_parent_absent':True})
  # Each negative uses a fresh complete set; no accepted mutation may escape.
  for name,mutate,error in [('missing-mapping',lambda r:r.update(stores=r['stores'][:-1]),'RESTORE_CONFLICT'),('wrong-snapshot',lambda r:r['stores'][0].update(snapshot_sha256='0'*64),'RESTORE_CONFLICT'),('foreign-server',lambda r:r.update(expected_server_id='0'*32),'RESTORE_CONFLICT'),('invalid-checkpoint',lambda r:(Path(r['stores'][0]['store_path']).write_bytes(b'not-a-dets-file'),r['stores'][0].update(checkpoint_sha256=sha(r['stores'][0]['store_path']))),'RESTORE_CONFLICT')]:
   np=copied(backup,work/name);req=command_for(np,name);mutate(req)
   files=[np,Path(str(np)+'.stores'),Path(str(np)+'.stores.marker'),Path(str(np)+'.recovery')];hashes=[sha(x) for x in files];products=product_hashes(req)
   cli(command,['rebind-storage',req],work,name+'-error',error=error);assert [sha(x) for x in files]==hashes;assert not Path(str(np)+'.transaction').exists();assert product_hashes(req)==products
   checks.append({'id':name+'-before-decision-unchanged','passed':True})
  if a.history_source:
   hp=copied(a.history_source,work/'retained-history');req=command_for(hp,'retained-history');before=product_hashes(req);previous=json.loads(Path(str(hp)+'.recovery').read_text())
   ready={k for k,v in previous['operations'].items() if v['kind']=='plan' and v['state']=='ready'}
   assert ready,'Expected actual retained reviewed recovery plan'
   cli(command,['rebind-storage',req],work,'retained-history')
   current=json.loads(Path(str(hp)+'.recovery').read_text());assert product_hashes(req)==before and current['receipts']==previous['receipts'] and current['jobs']==previous['jobs']
   assert all(current['operations'][k]['state']=='stale' for k in ready)
   for k,v in previous['operations'].items():
    if k not in ready:assert current['operations'][k]==v
   checks.append({'id':'actual-retained-recovery-history-receipts-preserved-ready-plans-stale','passed':True,'plans_staled':len(ready)})
  library=work/'rebind_fault.so';subprocess.run(['gcc','-shared','-fPIC','-std=c11','-Wall','-Wextra',str(Path(__file__).with_name('rebind_fault.c')),'-ldl','-o',str(library)],check=True,capture_output=True)
  for stage in ['decision-durable','registry-durable','receipt-durable']:
   fp=copied(backup,work/stage);req=command_for(fp,'fault-'+stage);before=product_hashes(req);cfg=sha(fp);sentinel=work/(stage+'.sentinel.json');env={**os.environ,'LD_PRELOAD':str(library),'ADHD_REBIND_CONFIG':str(fp),'ADHD_REBIND_STAGE':stage,'ADHD_REBIND_SENTINEL':str(sentinel)}
   out=(work/(stage+'.stdout')).open('wb');err=(work/(stage+'.stderr')).open('wb');process=subprocess.Popen(command+[json.dumps(['rebind-storage',req])],stdout=out,stderr=err,env=env,start_new_session=True);active=(process,[out,err]);deadline=time.monotonic()+140
   while not sentinel.exists() and time.monotonic()<deadline:
    assert process.poll() is None,(stage,'exited before observed fsync');time.sleep(.05)
   assert sentinel.exists(),stage;witness=json.loads(sentinel.read_text());assert witness['directory_fsync_result']==0
   os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10);out.close();err.close();active=None;assert process.returncode==-signal.SIGKILL
   assert Path(str(fp)+'.transaction').exists();recovered=cli(command,['rebind-storage',req],work,stage+'-retry')
   assert recovered['rebound'] and not Path(str(fp)+'.transaction').exists() and product_hashes(req)==before and sha(fp)==cfg
   assert cli(command,['rebind-storage',req],work,stage+'-replay')==recovered
   checks.append({'id':stage+'-kernel-kill-exact-recovery','passed':True,'witness':witness,'exit_code':process.returncode,'product_bytes_unchanged':True})
  report={'schema':'adhd/storage-rebind-native-check@1','passed':True,'scope':'Actual native CLI/full-server moved restore and real metadata fsync+kernel-kill boundaries; no image claim','artifact_sha256':sha(a.artifact),'harness_sha256':sha(__file__),'fault_hook_sha256':sha(Path(__file__).with_name('rebind_fault.c')),'checks':checks}
  a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print('PASS',len(checks),'native portable/rebind groups',flush=True)
 finally:
  if active:stop(*active)
if __name__=='__main__':main()
