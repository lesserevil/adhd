#!/usr/bin/env python3
"""Independent real-model filtering smoke; credentials are always supplied privately."""
import asyncio,hashlib,json,time
from pathlib import Path
from uuid import uuid4
from kafka_model_audit import verify_audit
from multi_support import Fixture,arguments,scoped,poll_until,reject

async def main():
 p=arguments('Diagnostic real short-response optional filtering');p.add_argument('--model-url',required=True);p.add_argument('--gateway-report',type=Path,required=True);p.add_argument('--with-backend-queries',action='store_true',help='Qualify actual semantic history and a second raw project with the same live endpoint')
 p.add_argument('--privacy-canaries',type=Path,help='Qualification-only synthetic BLUE/private strings scanned by the owned relay')
 args=p.parse_args();f=Fixture(args)
 canaries=json.loads(args.privacy_canaries.read_text()) if args.privacy_canaries else None
 if canaries:assert set(canaries)=={'blue','private'} and all(isinstance(v,str) and v for v in canaries.values())
 try:
  await f.start()
  a,b=await f.agent('red-a'),await f.agent('red-b');admin=f.admin()
  for s in (await b.call(scoped('project-red','list_subscriptions')))['subscriptions']:
   await b.call(scoped('project-red','unsubscribe',subscription_id=s['id']))
  raw=(await a.call(scoped('project-red','subscribe',mode='raw')))['subscription']
  initial=len(json.loads(args.gateway_report.read_text())) if args.gateway_report.exists() else 0
  blue_a,blue_b=await f.agent('blue-a'),await f.agent('blue-b')
  await blue_b.call(scoped('project-blue','subscribe',mode='raw'))
  warm=(await blue_a.call(scoped('project-blue','publish',text=canaries['blue'] if canaries else 'Model-free project BLUE before optional model activation.')))['publication']
  await poll_until(blue_b,'project-blue',{warm['id']},20)
  if canaries:
   private=(await a.call(scoped('project-red','send',recipient_id='red-b',text=canaries['private'])))['delivery']
   assert private['text']==canaries['private']
   assert not (await b.call(scoped('project-red','search',query=canaries['private'])))['publications']
   await b.call(scoped('project-red','ack',delivery_ids=[private['id']]))
  initial_after=len(json.loads(args.gateway_report.read_text())) if args.gateway_report.exists() else 0
  assert initial_after==initial
  adapter={'url':args.model_url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':10000,'retry_ms':1000}
  admin.call({'op':'config_update','patch':{'matcher':adapter}},mutation=True)
  filtered=(await b.call(scoped('project-red','subscribe',mode='filtered',filter='Only breaking API compatibility changes that remove or rename a public API endpoint.')))['subscription']
  fixture=uuid4().hex
  texts=['Breaking API compatibility change: removed the public /v1/create endpoint. All API clients must migrate to /v2/create.',
         'Office lunch menu for Friday: vegetable soup and sandwiches. No software changes are announced.']
  texts=[text+f' [fixture-{i}-{fixture}]' for i,text in enumerate(texts)]
  publications=[]
  for i,text in enumerate(texts):publications.append((await a.call(scoped('project-red','publish',text=text,information_type='live-filter-proof',source={'kind':'live-proof','id':fixture,'item_id':str(i)})))['publication'])
  rawrows=await poll_until(a,'project-red',{p['id'] for p in publications},20)
  filteredrows=await poll_until(b,'project-red',{publications[0]['id']},30)
  deadline=time.monotonic()+35
  while time.monotonic()<deadline:
   events=json.loads(args.gateway_report.read_text()) if args.gateway_report.exists() else []
   relevant=[e for e in events[initial:] if e.get('publication_id') in {p['id'] for p in publications} and e.get('phase','responded')=='responded']
   if {e['publication_id'] for e in relevant}=={p['id'] for p in publications}:break
   await asyncio.sleep(.1)
  scores={e['publication_id']:e['typed_response']['answers']['relevance'] for e in relevant}
  assert set(scores)=={p['id'] for p in publications}
  assert all(s['type']=='noul' and 0<=s['noul']<=1 for s in scores.values())
  assert scores[publications[0]['id']]['noul']>=.9,scores
  assert scores[publications[1]['id']]['noul']<.9,scores
  await asyncio.sleep(.5)
  filteredrows=(await b.call(scoped('project-red','poll')))['deliveries']
  assert any(d.get('publication_id')==publications[0]['id'] for d in filteredrows)
  assert not any(d.get('publication_id')==publications[1]['id'] for d in filteredrows)
  backend=None
  if args.with_backend_queries:
   # Same server, independent project: it has no filtered subscription, and must
   # remain raw even while RED's semantic workflows are configured and active.
   blue=(await blue_a.call(scoped('project-blue','publish',text='Independent BLUE raw fact while RED filters are enabled.')))['publication']
   await poll_until(blue_b,'project-blue',{blue['id']},20)
   q=(await a.call(scoped('project-red','query_history',question='Which public API endpoint was explicitly removed?',scope={'source_kind':'live-proof','source_id':fixture})))['query']
   deadline=time.monotonic()+60
   while time.monotonic()<deadline:
    q=(await a.call(scoped('project-red','get_history_query',query_id=q['id'])))['query']
    if q['status']!='pending':break
    await asyncio.sleep(.1)
   assert q['status']=='completed' and q['outcome']=='direct', (q['status'],q.get('error'),q.get('outcome'))
   assert publications[0]['id'] in q['answer']['support_ids']
   assert blue['id'] not in json.dumps(q)
   if canaries:assert all(value not in json.dumps(q,ensure_ascii=False) for value in canaries.values())
   reject(await f.raw('bridge',scoped('project-blue','get_history_query',query_id=q['id'])),code='NOT_FOUND')
   backend={'project_id':'project-red','status':q['status'],'outcome':q['outcome'],'positive_original_cited':True,'foreign_project_original_absent':True,'foreign_query_lookup_denied':True}
   for agent,project in ((a,'project-red'),(b,'project-red'),(blue_b,'project-blue')):
    rows=(await agent.call(scoped(project,'poll')))['deliveries']
    if rows:await agent.call(scoped(project,'ack',delivery_ids=[d['id'] for d in rows]))
  # Restore model-free state and prove the same live raw subscriber still progresses.
  outstanding=(await b.call(scoped('project-red','poll')))['deliveries']
  if outstanding:await b.call(scoped('project-red','ack',delivery_ids=[d['id'] for d in outstanding]))
  admin.call({'op':'config_update','patch':{'matcher':None}},mutation=True)
  before=len(json.loads(args.gateway_report.read_text()))
  absent=(await a.call(scoped('project-red','publish',text='Breaking API compatibility change: removed the public /v1/offline endpoint while optional model filtering was paused.')))['publication']
  await poll_until(a,'project-red',{absent['id']},20)
  await asyncio.sleep(.5)
  after=len(json.loads(args.gateway_report.read_text()))
  assert before==after,(before,after)
  assert not any(d.get('publication_id')==absent['id'] for d in (await b.call(scoped('project-red','poll')))['deliveries'])
  # Existing filtered subscriptions retain their policy while the model is off;
  # accepting the original then reenabling must not strand that accepted work.
  admin.call({'op':'config_update','patch':{'matcher':adapter}},mutation=True)
  resumed=await poll_until(b,'project-red',{absent['id']},40)
  pending=[d for d in resumed if d.get('publication_id')==absent['id']]
  assert len(pending)==1 and pending[0]['matches'][0]['subscription_id']==filtered['id']
  await b.call(scoped('project-red','ack',delivery_ids=[pending[0]['id']]))
  end=time.monotonic()+5
  while True:
   all_events=json.loads(args.gateway_report.read_text())
   resumed_events=[e for e in all_events[initial:] if e.get('publication_id')==absent['id'] and e.get('phase','responded')=='responded']
   if resumed_events:break
   assert time.monotonic()<end,'Resumed provider response was not captured by the bounded relay'
   await asyncio.sleep(.05)
  await b.call(scoped('project-red','unsubscribe',subscription_id=filtered['id']))
  admin.call({'op':'config_update','patch':{'matcher':None}},mutation=True)
  proof={'passed':True,'scope':'diagnostic-real-model-optional-pubsub-filter','lifecycle_qualified':False,
         'model':'Nemotron-Deciffusion-8B-v2.1','synthetic_decisions':[{'case':'breaking-public-api-removal','type':'noul','noul':scores[publications[0]['id']]['noul']},{'case':'office-lunch-no-software-change','type':'noul','noul':scores[publications[1]['id']]['noul']}],
         'actual_processing_calls':len(all_events)-initial,'initial_filter_fixture_processing_calls':len(relevant),'resumed_filter_processing_calls':len(resumed_events),'raw_received_both':True,'filtered_received_only_positive':True,
         'hot_model_enable_and_disable':True,'raw_progress_after_model_disable':True,'additional_inference_calls_after_disable':after-before,
         'literal_search_preserved':(await a.call(scoped('project-red','search',query=f'fixture-1-{fixture}')))['publications']==[publications[1]]}
  proof['model_free_second_project_zero_inference']=initial_after==initial
  proof['backend_query']=backend
  proof['accepted_while_model_disabled_delivered_once_after_reenable']=True
  proof['artifact_sha256']=hashlib.sha256(args.hub.read_bytes()).hexdigest() if args.hub else None
  proof['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  if canaries:
   assert not args.gateway_report.with_name(args.gateway_report.name+'.denied').exists()
   proof['relay_audit']=verify_audit(all_events,[p['id'] for p in publications]+[absent['id']])
   proof['foreign_and_private_canaries_absent_from_red_requests_and_answer']=True
  proof['gateway_report_sha256']=hashlib.sha256(args.gateway_report.read_bytes()).hexdigest()
  proof['decision_latency_ms']=[e['elapsed_ms'] for e in relevant]
  assert proof['literal_search_preserved'];args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
 finally:await f.close()
if __name__=='__main__':asyncio.run(main())
