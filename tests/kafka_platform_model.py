#!/usr/bin/env python3
"""Independent real-model filtering smoke; credentials are always supplied privately."""
import asyncio,json,time
from pathlib import Path
from uuid import uuid4
from multi_support import Fixture,arguments,scoped,poll_until,reject

async def main():
 p=arguments('Diagnostic real short-response optional filtering');p.add_argument('--model-url',required=True);p.add_argument('--gateway-report',type=Path,required=True)
 args=p.parse_args();f=Fixture(args);await f.start()
 try:
  a,b=await f.agent('red-a'),await f.agent('red-b');admin=f.admin()
  for s in (await b.call(scoped('project-red','list_subscriptions')))['subscriptions']:
   await b.call(scoped('project-red','unsubscribe',subscription_id=s['id']))
  raw=(await a.call(scoped('project-red','subscribe',mode='raw')))['subscription']
  initial=len(json.loads(args.gateway_report.read_text())) if args.gateway_report.exists() else 0
  admin.call({'op':'config_update','patch':{'matcher':{'url':args.model_url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':10000,'retry_ms':1000}}},mutation=True)
  filtered=(await b.call(scoped('project-red','subscribe',mode='filtered',filter='Only breaking API compatibility changes that remove or rename a public API endpoint.')))['subscription']
  fixture=uuid4().hex
  texts=['Breaking API compatibility change: removed the public /v1/create endpoint. All API clients must migrate to /v2/create.',
         'Office lunch menu for Friday: vegetable soup and sandwiches. No software changes are announced.']
  texts=[text+f' [fixture-{i}-{fixture}]' for i,text in enumerate(texts)]
  publications=[]
  for text in texts:publications.append((await a.call(scoped('project-red','publish',text=text)))['publication'])
  rawrows=await poll_until(a,'project-red',{p['id'] for p in publications},20)
  filteredrows=await poll_until(b,'project-red',{publications[0]['id']},30)
  deadline=time.monotonic()+35
  while time.monotonic()<deadline:
   events=json.loads(args.gateway_report.read_text()) if args.gateway_report.exists() else []
   relevant=[e for e in events[initial:] if e.get('publication_id') in {p['id'] for p in publications}]
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
  # Restore model-free state and prove the same live raw subscriber still progresses.
  await b.call(scoped('project-red','unsubscribe',subscription_id=filtered['id']))
  admin.call({'op':'config_update','patch':{'matcher':None}},mutation=True)
  before=len(json.loads(args.gateway_report.read_text()))
  absent=(await a.call(scoped('project-red','publish',text='Raw stream continues after hot model disable.')))['publication']
  await poll_until(a,'project-red',{absent['id']},20)
  await asyncio.sleep(.5)
  after=len(json.loads(args.gateway_report.read_text()))
  assert before==after,(before,after)
  proof={'passed':True,'scope':'diagnostic-real-model-optional-pubsub-filter','lifecycle_qualified':False,
         'model':'Nemotron-Deciffusion-8B-v2.1','synthetic_decisions':[{'case':'breaking-public-api-removal','type':'noul','noul':scores[publications[0]['id']]['noul']},{'case':'office-lunch-no-software-change','type':'noul','noul':scores[publications[1]['id']]['noul']}],
         'actual_processing_calls':len(relevant),'raw_received_both':True,'filtered_received_only_positive':True,
         'hot_model_enable_and_disable':True,'raw_progress_after_model_disable':True,'additional_inference_calls_after_disable':after-before,
         'literal_search_preserved':(await a.call(scoped('project-red','search',query=f'fixture-1-{fixture}')))['publications']==[publications[1]]}
  assert proof['literal_search_preserved'];args.report.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
 finally:await f.close()
asyncio.run(main())
