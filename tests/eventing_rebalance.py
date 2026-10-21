#!/usr/bin/env python3
"""Actual managed observer rebalances beside ADHD's manually assigned bridge.

The observer members never commit offsets or serve ADHD deliveries. This is a
coordinator-interference/recovery qualification, not managed bridge ownership/HA.
Every Kafka HTTP success and assignment comes from the supplied real service.
"""
import asyncio,copy,hashlib,json,os,re,subprocess,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
import httpx
from multi_support import Fixture,Evidence,arguments,poll_until,scoped
P='project-red';V2='application/vnd.kafka.v2+json';JSON_V2='application/vnd.kafka.json.v2+json'
LIMITS={'observers':2,'publications':12,'hub_hard_restarts':1,'phase_seconds':45,'overall_seconds':360,'cli_calls':40,'http_observations':400}

class Relay:
 def __init__(self,url):
  self.url=url.rstrip('/');self.entries=[];self.instances=set();self.lock=threading.Lock();self.overflow=False
  relay=self
  class Handler(BaseHTTPRequestHandler):
   protocol_version='HTTP/1.1'
   def log_message(self,*_):pass
   def do_GET(self):self.forward()
   def do_POST(self):self.forward()
   def do_DELETE(self):self.forward()
   def forward(self):
    body=self.rfile.read(int(self.headers.get('Content-Length','0')))
    headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','content-length','connection','accept-encoding'}}
    try:
     with httpx.Client(trust_env=False,timeout=6) as http:r=http.request(self.command,relay.url+self.path,headers=headers,content=body)
    except httpx.HTTPError:self.send_error(502);return
    entry={'method':self.command,'path':self.path,'status':r.status_code}
    if self.command=='POST' and '/consumers/' in self.path:
     value=json.loads(body) if body else None;entry['request']=value
     if r.is_success and '/instances/' not in self.path:
      response=r.json();path=self.path.rstrip('/')+'/instances/'+response['instance_id'];relay.instances.add(path);entry['instance_path']=path
    if self.command=='POST' and self.path.startswith('/topics/'):
     value=json.loads(body);entry['publication_ids']=[row['value']['publication_id'] for row in value.get('records',[])];entry['topic']=self.path.split('/')[2]
    if not r.is_success:
     try:entry['error']=r.json()
     except ValueError:entry['error_body_sha256']=hashlib.sha256(r.content).hexdigest()
    with relay.lock:
     if len(relay.entries)<LIMITS['http_observations']:relay.entries.append(entry)
     else:relay.overflow=True
    self.send_response(r.status_code)
    if 'content-type' in r.headers:self.send_header('Content-Type',r.headers['content-type'])
    self.send_header('Content-Length',str(len(r.content)));self.end_headers()
    try:self.wfile.write(r.content)
    except (BrokenPipeError,ConnectionResetError):pass
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
 def close(self):self.server.shutdown();self.server.server_close();self.thread.join(3)

class Observer:
 def __init__(self,http,base,group,name,topic):self.http=http;self.path=base+'/consumers/'+group+'/instances/'+name;self.group=group;self.name=name;self.topic=topic;self.task=None;self.running=True;self.statuses=[];self.offsets=[]
 async def start(self,base):
  r=await self.http.post(base+'/consumers/'+self.group,headers={'Accept':V2,'Content-Type':V2},json={'name':self.name,'format':'json','auto.offset.reset':'earliest','auto.commit.enable':'false'});assert r.status_code==200 and r.json()['instance_id']==self.name
  r=await self.http.post(self.path+'/subscription',headers={'Accept':V2,'Content-Type':V2},json={'topics':[self.topic]});assert r.status_code==204
  self.task=asyncio.create_task(self.poll())
 async def poll(self):
  while self.running:
   r=await self.http.get(self.path+'/records?timeout=1000&max_bytes=262144',headers={'Accept':JSON_V2});self.statuses.append(r.status_code)
   if r.is_success:
    for row in r.json():self.offsets.append(row['offset'])
   await asyncio.sleep(.05)
 async def assignment(self):
  r=await self.http.get(self.path+'/assignments',headers={'Accept':V2});assert r.status_code==200;return r.json()['partitions']
 async def close(self):
  self.running=False
  if self.task:await asyncio.wait_for(self.task,8)
  r=await self.http.delete(self.path,headers={'Accept':V2});assert r.status_code in (204,404)

async def until(fn,seconds=45):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  value=await fn()
  if value:return value
  await asyncio.sleep(.1)
 raise AssertionError('Managed coordinator phase deadline exceeded')

async def main(args):
 if not args.hub or args.rest_url or args.image:raise ValueError('First qualification is exact native --hub only')
 assert args.eventing_rest_url.rstrip('/')=='http://127.0.0.1:18087','Only the owned18087 service is authorized'
 relay=Relay(args.eventing_rest_url);local=copy.copy(args);local.eventing_rest_url=relay.base;local.keep_work=None
 f=Fixture(local);e=Evidence(args.report,'adhd/real-coordinator-interference@1');e.value.update(artifact_sha256=hashlib.sha256(args.hub.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),predeclared_limits=LIMITS,scope='Actual managed observer membership/assignment changes alongside manually assigned bridge; no bridge-managed ownership transfer or HA claim',coordinator_snapshots=[],publications=0,hub_hard_restarts=0)
 cli_calls=0;observers=[];http=httpx.AsyncClient(trust_env=False,timeout=8);expected={};receipts=[];all_pubs=[];group=None;topic=None
 def persist():e.write()
 async def cli_snapshot(expected_members):
  nonlocal cli_calls
  outputs={}
  for mode in ['state','members']:
   cli_calls+=1;assert cli_calls<=LIMITS['cli_calls']
   argv=['docker','exec','-e','KAFKA_HEAP_OPTS=-Xmx256m -Xms128m',args.owned_broker_container,'kafka-consumer-groups','--bootstrap-server','localhost:9092','--describe','--group',group,'--'+mode,'--timeout','5000']
   if mode=='members':argv+=['--verbose']
   r=await asyncio.to_thread(subprocess.run,argv,capture_output=True,text=True,timeout=12);assert len(r.stdout.encode())<=16384 and len(r.stderr.encode())<=16384
   outputs[mode]={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  raw={'expected_members':expected_members,'cli':outputs};e.value.setdefault('raw_cli_snapshots',[]).append(raw);persist()
  state=None;members=[]
  for line in outputs['state']['stdout'].splitlines():
   m=re.search(r'\b(Empty|Stable|PreparingRebalance|CompletingRebalance|Assigning|Reconciling|Dead)\s+(\d+)\s*$',line)
   if m:state={'name':m[1],'members':int(m[2])}
  lines=outputs['members']['stdout'].splitlines();header=None
  for line in lines:
   cols=line.split()
   if 'CONSUMER-ID' in cols and '#PARTITIONS' in cols:header=cols
   elif header and cols and cols[0]==group:
    try:members.append({'id':cols[header.index('CONSUMER-ID')],'partitions':int(cols[header.index('#PARTITIONS')]),'assignment':' '.join(cols[header.index('ASSIGNMENT' if 'ASSIGNMENT' in header else 'CURRENT-ASSIGNMENT'):])})
    except (ValueError,IndexError):raise AssertionError('Unrecognized actual broker member table')
  snap={'expected_members':expected_members,'observed_state':state,'members':members,'cli':outputs};e.value['coordinator_snapshots'].append(snap);persist()
  if any(v['returncode']!=0 for v in outputs.values()):return None
  wanted='Empty' if expected_members==0 else 'Stable'
  return snap if state and state['name']==wanted and state['members']==expected_members and len(members)==expected_members else None
 async def state(n):return await until(lambda:cli_snapshot(n))
 async def status():return f.admin().call({'op':'eventing_status','project_id':P})
 async def publish(publisher,text,ack=True):
  e.value['publications']+=1;assert e.value['publications']<=LIMITS['publications']
  cmd=scoped(P,'publish',text=text,source={'kind':'fixture','id':'real-coordinator','item_id':uuid4().hex});mid=uuid4().hex;r=await publisher.call(cmd,mid);pub=r['publication'];receipts.append((cmd,mid,r));all_pubs.append(pub)
  for index,subscriber in enumerate(subscribers):
   rows=await poll_until(subscriber,P,{pub['id']},args.deadline);rows=[x for x in rows if x.get('publication_id')==pub['id']];assert len(rows)==1
   expected[index,pub['id']]=rows[0]['id']
   if ack:await subscriber.call(scoped(P,'ack',delivery_ids=[rows[0]['id']]))
  return pub
 async def broker_offset():
  paths=[x['path'] for x in relay.entries if x['method']=='POST' and x['path'].endswith('/offsets') and x.get('request',{}).get('offsets',[{}])[0].get('topic')==topic]
  assert paths
  r=await http.request('GET',relay.url+paths[-1],headers={'Accept':V2,'Content-Type':V2},json={'partitions':[{'topic':topic,'partition':0}]})
  assert r.status_code==200;return r.json()['offsets'][0]['offset']
 try:
  async with asyncio.timeout(LIMITS['overall_seconds']):
   await f.start();publisher=await f.agent('red-a');subscribers=[await f.agent('red-b'),await f.agent('bridge')]
   for b in subscribers:await b.call(scoped(P,'subscribe',mode='raw'))
   first=await publish(publisher,'Baseline pending first',False);second=await publish(publisher,'Baseline pending second',False)
   await subscribers[0].call(scoped(P,'ack',delivery_ids=[expected[0,second['id']]]));await subscribers[1].call(scoped(P,'ack',delivery_ids=[expected[1,first['id']]]))
   wanted_pending=[{expected[0,first['id']]},{expected[1,second['id']]}]
   produced=next(x for x in relay.entries if first['id'] in x.get('publication_ids',[]));topic=produced['topic']
   assignment=next(x for x in relay.entries if x['path'].endswith('/assignments') and x.get('request',{}).get('partitions',[{}])[0].get('topic')==topic);group=assignment['path'].split('/')[2]
   e.value.update(topic=topic,group=group,broker_container=args.owned_broker_container);persist()
   baseline=await state(0);assert await broker_offset()<=(await status())['next_offset']
   e.record('actual-manual-bridge-has-zero-managed-members-and-independent-out-of-order-acks')
   a=Observer(http,relay.url,group,'observer-a-'+uuid4().hex[:8],topic);observers.append(a);await a.start(relay.url);await state(1)
   await publish(publisher,'Publication during one managed member')
   b=Observer(http,relay.url,group,'observer-b-'+uuid4().hex[:8],topic);observers.append(b);await b.start(relay.url);two=await state(2)
   assert sorted(x['partitions'] for x in two['members'])==[0,1]
   old_owner=next(x['id'] for x in two['members'] if x['partitions']==1);old_idle=next(x['id'] for x in two['members'] if x['partitions']==0)
   await publish(publisher,'Publication during two managed members')
   blue=await f.agent('blue-a');blue_pub=(await blue.call(scoped('project-blue','publish',text='Independent blue while red coordinator changes')))['publication'];e.value['publications']+=1
   assert (await blue.call(scoped('project-blue','search',query=blue_pub['text'])))['publications']==[blue_pub]
   e.record('real-coordinator-membership-one-to-two-with-single-partition-and-a2a-progress')
   before=await status();assert await broker_offset()<=before['next_offset']
   f.hard_stop();e.value['hub_hard_restarts']+=1;await f.start();await state(2)
   for index,sub in enumerate(subscribers):assert {d['id'] for d in (await sub.call(scoped(P,'poll')))['deliveries']}==wanted_pending[index]
   for cmd,mid,r in receipts:
    assert await publisher.call(cmd,mid)==r;assert (await publisher.call(cmd,uuid4().hex))['publication']==r['publication']
   positions=[x for x in relay.entries if x['path'].endswith('/positions') and x.get('request',{}).get('offsets',[{}])[0].get('topic')==topic]
   assert len(positions)>=2 and positions[-1]['request']['offsets'][0]['offset']>=before['next_offset']
   await publish(publisher,'Publication after bridge restart with two managed members')
   e.record('actual-hub-kill-recreates-manual-consumer-at-durable-position-without-observer-takeover')
   assignments=[await x.assignment() for x in observers]
   owner_index=next(i for i,rows in enumerate(assignments) if any(x['topic']==topic and x['partition']==0 for x in rows));removed=observers.pop(owner_index);await removed.close()
   one=await state(1);assert one['members'][0]['id']==old_idle and one['members'][0]['id']!=old_owner and one['members'][0]['partitions']==1
   assert any(x['topic']==topic and x['partition']==0 for x in await observers[0].assignment())
   await publish(publisher,'Publication after actual observer partition transfer')
   e.record('real-broker-assignment-moves-from-removed-owner-to-previously-idle-observer')
   await observers.pop().close();await state(0)
   await publish(publisher,'Publication after managed members leave')
   async def converged():
    s=await status();o=await broker_offset();assert o<=s['next_offset'];return {'durable_next_offset':s['next_offset'],'broker_committed_next_offset':o} if o==s['next_offset'] and s['pending_events']==0 else None
   convergence=await until(converged)
   for index,sub in enumerate(subscribers):
    rows=(await sub.call(scoped(P,'poll')))['deliveries'];assert {x['id'] for x in rows}==wanted_pending[index]
    await sub.call(scoped(P,'ack',delivery_ids=[x['id'] for x in rows]));assert not (await sub.call(scoped(P,'poll')))['deliveries']
   for pub in all_pubs:assert (await subscribers[1].call(scoped(P,'get',publication_id=pub['id'])))['publication']==pub
   failures=[x for x in relay.entries if x['method']=='POST' and x['path'].endswith('/offsets') and x['status']>=400]
   e.value.update(commit_failures=failures,convergence=convergence,manual_bridge_consumer_recreations=len(positions),cli_calls=cli_calls,observer_auto_commit=False,model=None,inference_calls=0)
   assert not relay.overflow
   e.record('empty-group-restores-real-commit-convergence-preserving-originals-and-acks')
 except BaseException as error:e.finish(error);raise
 else:e.finish()
 finally:
  for x in observers:
   try:await x.close()
   except BaseException:pass
  await f.close()
  for path in relay.instances:
   try:await http.delete(relay.url+path,headers={'Accept':V2})
   except httpx.HTTPError:pass
  await http.aclose();relay.close()
  e.value.update(http_observations=relay.entries,http_observation_overflow=relay.overflow,cli_calls=cli_calls);e.write()

if __name__=='__main__':
 parser=arguments(__doc__);parser.add_argument('--owned-broker-container',required=True)
 asyncio.run(main(parser.parse_args()))
