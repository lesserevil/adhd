#!/usr/bin/env python3
"""Actual v2 catalog replies cannot cross a selective-project recovery epoch.

Two owned hubs, transparent real-peer relay, no Kafka or model. The
existing test-only live-loss runner kills one actual nondefault Store, without
adding a product API or fabricating accepted state.
"""
import asyncio,copy,hashlib,http.client,json,os,secrets,subprocess,sys,threading,time
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from multi_support import Evidence,Fixture,arguments,scoped
from project_recovery_acceptance import Recovery,RED,BLUE
from project_recovery_restore import offline_bundle
from project_recovery_state import route,registry
from recovery_image_runtime import RecoveryImageRuntime,bind_down,same_vm

class NativeFixture(Fixture):
 async def start(self):
  # The fixed bound includes compilation of the exact one-megabyte native script.
  if not self.file.exists():
   self.file.write_text(json.dumps(self.config));self.file.chmod(0o600)
  command=json.loads(self.args.command) if self.args.command else ['elixir',str(self.args.hub.resolve())]
  self.logs=[(self.root/name).open('ab') for name in ('stdout.log','stderr.log')]
  self.process=subprocess.Popen(command+[json.dumps(['serve',str(self.file)])],stdout=self.logs[0],stderr=self.logs[1],start_new_session=True)
  deadline=time.monotonic()+150
  async with httpx.AsyncClient(trust_env=False) as client:
   while time.monotonic()<deadline:
    assert self.process.poll() is None,'Owned hub exited before readiness'
    try:
     response=await client.get(self.base+'/health',timeout=1)
     if response.status_code==200:return
    except httpx.HTTPError:pass
    await asyncio.sleep(.1)
  raise AssertionError('Declared150s native compile/readiness bound exhausted')

class CatalogRelay:
 def __init__(self,destination):
  self.destination=urlsplit(destination);self.rows=[];self.lock=threading.Lock();self.slots=threading.BoundedSemaphore(4)
  self.held=[threading.Event(),threading.Event()];self.release=[threading.Event(),threading.Event()];self.sent=[threading.Event(),threading.Event()]
  self.catalog_count=0;self.errors=[];outer=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*_):pass
   def do_POST(self):
    if not outer.slots.acquire(blocking=False):self.send_error(429);return
    try:
     n=int(self.headers.get('Content-Length','0'));assert 0<n<=262144
     body=self.rfile.read(n);cmd=json.loads(body);assert self.path=='/federation/v2'
     connection=http.client.HTTPConnection(outer.destination.hostname,outer.destination.port,timeout=2)
     try:
      connection.request('POST',self.path,body=body,headers={'Content-Type':'application/json','Authorization':self.headers.get('Authorization','')})
      reply=connection.getresponse();status=reply.status;raw=reply.read(262145);assert len(raw)<=262144
     finally:connection.close()
     value=json.loads(raw);row={'request':cmd,'status':status,'response':value,'response_sha256':hashlib.sha256(raw).hexdigest(),'held_index':None,'released':False,'write_succeeded':False}
     index=None
     with outer.lock:
      assert len(outer.rows)<128,'Declared relay inventory bound exhausted'
      if cmd.get('op')=='catalog' and status==200:
       index=outer.catalog_count;outer.catalog_count+=1
       if index<2:row['held_index']=index
      outer.rows.append(row)
     if index is not None and index<2:
      outer.held[index].set()
      assert outer.release[index].wait(10),'Declared10s actual response hold expired'
      row['released']=True
     self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
     try:self.wfile.write(raw);row['write_succeeded']=True
     except (BrokenPipeError,ConnectionResetError):pass
     if index is not None and index<2:outer.sent[index].set()
    except BaseException as error:
     outer.errors.append(type(error).__name__)
     try:self.send_error(502)
     except (BrokenPipeError,ConnectionResetError):pass
    finally:outer.slots.release()
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
 def close(self):
  for event in self.release:event.set()
  self.server.shutdown();self.server.server_close();self.thread.join(3)

async def until(fn,message,seconds=8):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  value=fn()
  if value:return value
  await asyncio.sleep(.02)
 raise AssertionError(message)

def patch(f,value):
 return f.admin().call({'op':'config_update','patch':value},mutation=True)

async def main():
 parser=arguments(__doc__);parser.add_argument('--recovery-schema',type=Path,default=Path(__file__).resolve().parents[1]/'components/hub/project-recovery/interface.schema.json');parser.add_argument('--loss-runner',type=Path,required=True)
 args=parser.parse_args();assert (args.hub or args.image) and not args.with_model and not args.rest_url and not args.command,'Exact-artifact/no-provider fixture only'
 work=args.keep_work.resolve();work.mkdir(mode=0o700,parents=True,exist_ok=True)
 aargs=copy.copy(args);aargs.keep_work=work/'origin'
 if not args.image:aargs.command=json.dumps(['elixir',str(args.loss_runner.resolve()),str(args.hub.resolve())])
 bargs=copy.copy(args);bargs.keep_work=work/'peer';bargs.command=None
 if args.image:a,b=(RecoveryImageRuntime(v,args.loss_runner.resolve(),startup_seconds=150) for v in (aargs,bargs))
 else:a,b=NativeFixture(aargs,initialize_projects=False),NativeFixture(bargs,initialize_projects=False)
 relay=CatalogRelay(b.base);e=Evidence(args.report,'project-recovery-peer-catalog-epoch')
 e.value['limitations']=['Model-free/eventing-disabled two-hub cache/epoch case; runtime custody separately bound; no Kafka, semantic provider or release completion claim.']
 e.value['prior_attempts']=[{'report':'recovery-peer13.json','report_sha256':'f10ec12f9c0d2885090c6b82c336f876f083ebf99fc0c3ed5c45c903cd51fdf3','result':'Harness waited for fresh request before releasing old synchronous worker request; failure retained, corrected ordering does not change old-result rejection expectation.'},{'report':'recovery-peer13b.json','report_sha256':'445de0d95b8dbcb822aff25579ed8cc132205bf54c367701a55ec54d1d3885af','result':'Harness fresh-refresh3s deadline shorter than configured10s network timeout; corrected to10s+2s scheduling, immediate old-directory-empty assertion preserved.'}]
 e.value.update(artifact_sha256=a.image_runtime.manifest['files']['hub.exs'] if args.image else hashlib.sha256(args.hub.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='Actual v2 peer HTTP catalog refresh across live target writer loss/restore; runtime custody separately bound; no Kafka/model/provider',limits={'startup_seconds':150,'relay_slots':4,'relay_requests':128,'hold_seconds':10,'epoch_transition_seconds':8,'fresh_refresh_seconds':12},dependency_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.loss_runner,Path(sys.modules['multi_support'].__file__),Path(sys.modules['project_recovery_restore'].__file__),args.recovery_schema]})
 token_ab,token_ba=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
 scope={'provider':'github','host':'github.com','tenant':'fixture','resource':'held-catalog'}
 for f in [a,b]:
  f.config.update(server_id=uuid4().hex,project_id=BLUE,eventing={'enabled':False},matcher=None,federation={'description':'Epoch fixture','peers':[],'timeout_ms':10000,'retry_ms':100,'catalog':{'visible':True,'entries':[]}})
  f.config['recovery']={'backup_root':str(f.root/'offline-backups')};Path(f.config['recovery']['backup_root']).mkdir(mode=0o700)
 b.config['projects']=copy.deepcopy(b.config['projects'])
 next(p for p in b.config['projects'] if p['id']==RED)['settings']={'federation':{'catalog':{'visible':True,'entries':[{'scope':scope,'aliases':['held-catalog'],'description':'Actual peer canonical catalog marker','relationship':'contained','canonical':True,'export_publication_ids':[]}]}}}
 b.config['federation']['peers']=[{'server_id':a.config['server_id'],'url':a.base,'token':token_ba,'inbound_token':token_ab,'project_pairs':[{'local_project_id':RED,'remote_project_id':RED}]}]
 failure=None
 try:
  await asyncio.gather(a.start(),b.start());ar,br=Recovery(a,args.recovery_schema),Recovery(b,args.recovery_schema)
  for f,r in [(a,ar),(b,br)]:
   await r.initialize(RED);await r.initialize(BLUE)
  a.hard_stop();_,backup_sha,backup_state=offline_bundle(a,ar,'empty-directory');assert not backup_state['directory'];await a.start()
  actor=await a.agent('bridge');blue=await a.agent('blue-b')
  prior=(await actor.call(scoped(BLUE,'send',recipient_id='blue-b',text='Blue survives Red catalog restore'),'blue-durable'))['delivery']
  before_blue=ar.status(BLUE)['route'];old_entry,anchor=route(a.file,RED)
  patch(a,{'federation':{'peers':[{'server_id':b.config['server_id'],'url':relay.url,'token':token_ab,'inbound_token':token_ba,'project_pairs':[{'local_project_id':RED,'remote_project_id':RED}]}]}})
  assert await until(relay.held[0].is_set,'No real old-epoch catalog response was held',12)
  old_row=next(row for row in relay.rows if row['held_index']==0);assert old_row['status']==200 and old_row['response']['items'][0]['scope']==scope
  e.record('actual-authenticated-v2-peer-catalog-success-held-before-target-loss',response_sha256=old_row['response_sha256'])
  owner_vm=a.watched_vm() if args.image else None
  cutoff=time.monotonic();nonce=uuid4().hex;Path(str(a.file)+'.kill-target').write_text(json.dumps({'project_id':RED,'nonce':nonce}))
  witness_path=Path(str(a.file)+'.target-down');await until(witness_path.exists,'Live loss hook did not observe actual Store DOWN')
  witness=json.loads(witness_path.read_text())
  if args.image:bind_down(owner_vm,witness,nonce,RED);same_vm(owner_vm,a.watched_vm())
  else:assert witness['nonce']==nonce and witness['reason']=='killed' and int(witness['vm_pid'])==a.process.pid
  held=a.root/'lost-pair';held.mkdir(mode=0o700)
  for p in [anchor,Path(str(anchor)+'.snapshot')]:assert p.is_file();os.replace(p,held/p.name)
  assert a.process.poll() is None and ar.status(RED)['availability']=='recovery_required'
  newer=(await actor.call(scoped(BLUE,'send',recipient_id='blue-b',text='Blue writable while Red is missing'),'blue-while-missing'))['delivery']
  revision=ar.revision();receipt=ar.call(RED,'project_restore_plan',backup_id='empty-directory',manifest_sha256=backup_sha,expected_revision=revision,allow_missing=True,message_id='peer-review')
  plan=(await ar.settle(RED,receipt,{'ready'}))['plan'];ar.assert_plan(plan,RED,'restore')
  accepted=ar.call(RED,'project_restore_apply',plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],expected_revision=revision,confirm=True,message_id='peer-apply')
  await ar.settle(RED,accepted,{'complete'});assert a.process.poll() is None
  if args.image:same_vm(owner_vm,a.watched_vm())
  assert ar.status(RED)['route']['project_epoch']!=old_entry['project_epoch'] and ar.status(BLUE)['route']==before_blue
  assert time.monotonic()-cutoff<8,'Declared live recovery/hold transition bound exhausted'
  e.record('same-vm-target-restored-to-new-epoch-while-blue-remains-current',loss_witness=witness,old_epoch=old_entry['project_epoch'],new_epoch=plan['selected']['project_epoch'])
  old_expiry=datetime.fromisoformat(old_row['response']['generated_at'].replace('Z','+00:00'))+timedelta(milliseconds=old_row['response']['max_age_ms'])
  assert datetime.now(timezone.utc)<old_expiry-timedelta(milliseconds=500),'Old catalog expired before release; would not isolate epoch fencing'
  relay.release[0].set();await until(relay.sent[0].is_set,'Old response was not released')
  await asyncio.sleep(.5)
  view=(await actor.call(scoped(RED,'federation_directory')))['peers'];assert len(view)==1 and view[0]['status']!='ready' and view[0]['catalog']==[],view
  e.record('released-old-real-peer-response-does-not-populate-restored-directory',peer_status=view[0]['status'])
  await until(relay.held[1].is_set,'No current-epoch catalog after configured10s HTTP deadline plus2s scheduling margin',12)
  relay.release[1].set();await until(relay.sent[1].is_set,'Fresh response was not released')
  deadline=time.monotonic()+5;ready=None
  while time.monotonic()<deadline:
   value=(await actor.call(scoped(RED,'federation_directory')))['peers'][0]
   if value['status']=='ready':ready=value;break
   await asyncio.sleep(.05)
  assert ready and ready['catalog'][0]['scope']==scope and ready['server_id']==b.config['server_id'],ready
  fresh=next(row for row in relay.rows if row['held_index']==1)
  expires=datetime.fromisoformat(fresh['response']['generated_at'].replace('Z','+00:00'))+timedelta(milliseconds=fresh['response']['max_age_ms'])
  assert datetime.fromisoformat(ready['expires_at'].replace('Z','+00:00'))==expires
  assert {prior['id'],newer['id']}<={d['id'] for d in (await blue.call(scoped(BLUE,'poll')))['deliveries']}
  assert not relay.errors,relay.errors
  e.value['relay_observations']=[{k:v for k,v in row.items() if k!='request'} for row in relay.rows]
  e.record('fresh-epoch-real-peer-refresh-succeeds-and-blue-originals-remain-usable',fresh_response_sha256=fresh['response_sha256'],peer_catalog_revision=ready['revision'])
 except BaseException as error:
  failure=error
  e.value['relay_errors']=relay.errors;e.value['relay_observations']=relay.rows
 finally:
  cleanup=[]
  for close in [relay.close,a.close,b.close]:
   try:
    result=close()
    if asyncio.iscoroutine(result):await result
   except BaseException as error:cleanup.append(error)
  if args.image:
   for label,f in [('origin',a),('peer',b)]:
    try:f.bind_evidence(e,'runtime_'+label)
    except BaseException as error:cleanup.append(error)
  else:a.bind_evidence(e)
  if cleanup:e.value['cleanup_failure_types']=[type(error).__name__ for error in cleanup]
  e.finish(failure or (cleanup[0] if cleanup else None))
  if failure:raise failure
  if cleanup:raise cleanup[0]
if __name__=='__main__':asyncio.run(main())
