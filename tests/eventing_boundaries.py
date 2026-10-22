#!/usr/bin/env python3
"""Real Kafka fanout-sync and consumer-offset commit crash boundaries.

Native fsync hooks stop actual syscalls, never rewrite state. Docker runs execute
only the two network/actual container-kill cases. Every broker success is real.
"""
import asyncio,copy,hashlib,json,os,signal,subprocess,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
import httpx
from multi_support import Evidence,Fixture,arguments,poll_until,scoped
P='project-red'

class BoundaryGateway:
 def __init__(self,upstream):
  self.upstream=upstream.rstrip('/');self.target=None;self.target_text=None;self.stage=None;self.pause=None
  self.fetched=threading.Event();self.release_records=threading.Event();self.reached=threading.Event();self.release_commit=threading.Event();self.abort=False;self.record=None;self.commit=None
  g=self
  class Handler(BaseHTTPRequestHandler):
   protocol_version='HTTP/1.1'
   def log_message(self,*_):pass
   def do_GET(self):self.forward()
   def do_POST(self):self.forward()
   def do_DELETE(self):self.forward()
   def forward(self):
    body=self.rfile.read(int(self.headers.get('Content-Length','0')))
    headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','content-length','connection','accept-encoding'}}
    commit=self.command=='POST' and self.path.endswith('/offsets') and g.record and json.loads(body)['offsets'][0]['offset']==g.record['offset'] and not g.reached.is_set()
    if commit and g.stage=='offset-before-post':
     g.commit={'path':self.path,'request':json.loads(body),'upstream_called':False};g.pause();g.reached.set();g.release_commit.wait(30)
     if g.abort:self.send_error(503);return
    try:
     with httpx.Client(trust_env=False,timeout=10) as client:r=client.request(self.command,g.upstream+self.path,headers=headers,content=body)
    except httpx.HTTPError:self.send_error(502);return
    if self.command=='GET' and '/records?' in self.path and r.is_success:
     records=r.json()
     chosen=next((row for row in records if (row.get('value',{}).get('publication_id')==g.target or (g.target_text is not None and row.get('value',{}).get('publication',{}).get('text')==g.target_text))),None)
     if chosen and not g.fetched.is_set():g.record=chosen;g.fetched.set();g.release_records.wait(15)
    if commit and g.stage=='offset-after-post':
     assert r.status_code in (200,204)
     g.commit={'path':self.path,'request':json.loads(body),'upstream_called':True,'upstream_status':r.status_code};g.pause();g.reached.set();g.release_commit.wait(30)
    self.send_response(r.status_code)
    if 'content-type' in r.headers:self.send_header('Content-Type',r.headers['content-type'])
    self.send_header('Content-Length',str(len(r.content)));self.end_headers()
    try:self.wfile.write(r.content)
    except (BrokenPipeError,ConnectionResetError):pass
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
 def close(self):
  self.abort=True;self.release_records.set();self.release_commit.set();self.server.shutdown();self.server.server_close();self.thread.join(3)

async def until(fn,deadline=30):
 end=time.monotonic()+deadline
 while time.monotonic()<end:
  value=fn()
  if value:return value
  await asyncio.sleep(.02)
 raise AssertionError('Boundary observation deadline exceeded')

def disk(path,publication):
 code='''[path,id]=System.argv(); <<"ADHDSTATE",1,hash::binary-size(32),body::binary>>=File.read!(path); true=hash==:crypto.hash(:sha256,body); s=:erlang.binary_to_term(body); ds=s.deliveries |> Map.values() |> Enum.map(& &1.value) |> Enum.filter(&(&1["publication_id"]==id)); e=s.eventing.events[id]; IO.puts(JSON.encode!(%{next_offset: s.eventing.next_offset, event_state: if(e,do: Atom.to_string(e.state),else: nil), deliveries: Enum.map(ds,&Map.take(&1,["id","publication_id","acked"]))}))'''
 return json.loads(subprocess.check_output(['elixir','-e',code,str(path),publication],text=True))

async def case(args,stage,evidence):
 g=BoundaryGateway(args.eventing_rest_url);local=copy.copy(args);local.eventing_rest_url=g.url;local.keep_work=None
 f=Fixture(local);arm=f.root/'armed';sentinel=f.root/'boundary.json';original_command=None
 if stage.startswith('fanout'):
  library=f.root/'eventing-sync.so';helper=Path(__file__).with_name('eventing_sync_fault.c')
  subprocess.run(['cc','-shared','-fPIC','-O2','-o',str(library),str(helper),'-ldl'],check=True)
  original_command=json.loads(args.command) if args.command else ['elixir',str(args.hub.resolve())]
  local.command=json.dumps(['env','LD_PRELOAD='+str(library),'ADHD_EVENT_STAGE='+stage,'ADHD_EVENT_STORE='+str(f.root/'hub.dets'),'ADHD_EVENT_ARM='+str(arm),'ADHD_EVENT_SENTINEL='+str(sentinel)]+original_command)
 try:
  await f.start();a,b=await f.agent('red-a'),await f.agent('red-b')
  await b.call(scoped(P,'subscribe',mode='raw'))
  baseline=(await a.call(scoped(P,'publish',text='Previously acknowledged boundary baseline')))['publication']
  previous=await poll_until(b,P,{baseline['id']},args.deadline)
  await b.call(scoped(P,'ack',delivery_ids=[d['id'] for d in previous]))
  # Hold the actual next records response before allowing its fanout transaction.
  cmd=scoped(P,'publish',text='Boundary original '+uuid4().hex,source={'kind':'slack','id':'boundaries','item_id':uuid4().hex});mid=uuid4().hex
  g.target_text=cmd['text']
  result=await a.call(cmd,mid);pub=result['publication'];g.target=pub['id']
  await until(g.fetched.is_set,args.deadline)
  assert g.record['value']['publication_id']==pub['id']
  expected=g.record['offset']+1
  accepted=await asyncio.to_thread(disk,f.root/'hub.dets.snapshot',pub['id'])
  assert accepted['event_state']=='published' and not accepted['deliveries']
  def pause():
   if f.image_runtime:
    x=f.image_runtime.docker('kill','--signal','STOP',f.image_runtime.name);assert x.returncode==0
    row=json.loads(f.image_runtime.docker('inspect',f.image_runtime.name).stdout)[0];assert row['State']['Running']
    evidence.value.setdefault('kernel_stops',[]).append({'container_id':row['Id'],'signal':'SIGSTOP'})
   else:os.kill(f.process.pid,signal.SIGSTOP)
  evidence.value['active_boundary']={'stage':stage,'accepted':accepted,'expected_next_offset':expected};evidence.write()
  if stage.startswith('fanout'):arm.touch()
  else:g.stage=stage;g.pause=pause
  g.release_records.set()
  if stage.startswith('fanout'):await until(sentinel.exists,args.deadline);witness=json.loads(sentinel.read_text());assert witness['pid']==f.process.pid
  else:await until(g.reached.is_set,args.deadline);witness=g.commit
  if not f.image_runtime:
   await until(lambda:'\nState:\tT' in Path('/proc',str(f.process.pid),'status').read_text(),5)
  evidence.value['active_boundary']['witness']=witness;evidence.write()
  installed=await asyncio.to_thread(disk,f.root/'hub.dets.snapshot',pub['id'])
  prospective=None
  if stage=='fanout-before-sync':
   prospective=await asyncio.to_thread(disk,Path(witness['path']),pub['id']);assert prospective['next_offset']==expected and len(prospective['deliveries'])==1
   assert installed['next_offset']<expected and not installed['deliveries']
  else:assert installed['next_offset']==expected and len(installed['deliveries'])==1
  evidence.value['active_boundary'].update(installed=installed,prospective=prospective);evidence.write()
  broker=None
  if stage.startswith('offset'):
   with httpx.Client(trust_env=False) as client:
    r=client.request('GET',g.upstream+g.commit['path'],headers={'Accept':'application/vnd.kafka.v2+json','Content-Type':'application/vnd.kafka.v2+json'},json={'partitions':[{'topic':g.record['topic'],'partition':0}]})
   evidence.value['active_boundary']['broker_query_status']=r.status_code;evidence.write()
   assert r.is_success;broker=r.json()
   evidence.value['active_boundary']['broker_offsets']=broker;evidence.write()
   actual=next(row['offset'] for row in broker['offsets'] if row['topic']==g.record['topic'])
   assert actual==expected if stage=='offset-after-post' else actual<expected
  f.hard_stop();g.abort=True;g.release_commit.set();arm.unlink(missing_ok=True)
  if original_command:local.command=json.dumps(original_command)
  await f.start()
  assert await a.call(cmd,mid)==result
  assert (await a.call(cmd,uuid4().hex))['publication']==pub
  rows=await poll_until(b,P,{pub['id']},args.deadline)
  rows=[d for d in rows if d.get('publication_id')==pub['id']];assert len(rows)==1
  if installed['deliveries']:assert rows[0]['id']==installed['deliveries'][0]['id']
  assert [d['id'] for d in (await b.call(scoped(P,'poll')))['deliveries']]==[rows[0]['id']]
  await b.call(scoped(P,'ack',delivery_ids=[rows[0]['id']]))
  f.hard_stop();await f.start();assert not (await b.call(scoped(P,'poll')))['deliveries']
  assert (await a.call(scoped(P,'get',publication_id=pub['id'])))['publication']==pub
  assert (await a.call(scoped(P,'search',query=cmd['text'])))['publications']==[pub]
  restored=await asyncio.to_thread(disk,f.root/'hub.dets.snapshot',pub['id']);assert restored['next_offset']>=expected
  evidence.record(stage,kind='native-syscall' if stage.startswith('fanout') else 'real-broker-network',boundary=witness,installed=installed,prospective=prospective,broker_offsets=broker,expected_next_offset=expected,committed_delivery_identity_preserved=bool(installed['deliveries']),baseline_ack_retained=True,restored=restored)
  evidence.value.pop('active_boundary',None);evidence.write()
 finally:
  arm.unlink(missing_ok=True);g.abort=True;g.release_records.set();g.release_commit.set()
  await f.close();f.bind_evidence(evidence,key='runtime_'+stage);g.close()

async def main(args):
 if args.rest_url:raise ValueError('An owned hub is required')
 evidence=Evidence(args.report,'adhd/eventing-durable-boundaries@1')
 evidence.value['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 evidence.value['hook_sha256']=hashlib.sha256(Path(__file__).with_name('eventing_sync_fault.c').read_bytes()).hexdigest()
 if args.hub:evidence.value['artifact_sha256']=hashlib.sha256(args.hub.read_bytes()).hexdigest()
 stages=['offset-before-post','offset-after-post'] if args.image else ['fanout-before-sync','fanout-after-sync','offset-before-post','offset-after-post']
 try:
  for stage in stages:await case(args,stage,evidence)
 except BaseException as error:evidence.finish(error);raise
 else:evidence.finish()
if __name__=='__main__':asyncio.run(main(arguments(__doc__).parse_args()))
