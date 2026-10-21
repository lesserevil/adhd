#!/usr/bin/env python3
"""Independent before/after platform recovery assertions using the public SDK."""
import argparse,asyncio,hashlib,json
from pathlib import Path
from multi_support import Fixture,arguments,scoped,poll_until,reject

async def main():
 p=arguments('Diagnostic platform replacement recovery');p.add_argument('--phase',choices=['before','after'],required=True);p.add_argument('--snapshot',type=Path,required=True)
 args=p.parse_args();f=Fixture(args);await f.start()
 try:
  a,b=await f.agent('red-a'),await f.agent('red-b')
  if args.phase=='before':
   text='Durable platform replacement fixture publication'
   sub=(await b.call(scoped('project-red','subscribe',mode='raw')))['subscription']
   original=(await a.call(scoped('project-red','publish',text=text)))['publication']
   deliveries=await poll_until(b,'project-red',{original['id']},20)
   selected=[d for d in deliveries if d.get('publication_id')==original['id']]
   assert len(selected)==1
   snap={'original':original,'delivery':selected[0]};args.snapshot.write_text(json.dumps(snap));args.snapshot.chmod(0o600)
   proof={'passed':True,'phase':'before','unacknowledged_originals':1,'unacknowledged_deliveries':1}
  else:
   snap=json.loads(args.snapshot.read_text());original=snap['original'];delivery=snap['delivery']
   assert (await a.call(scoped('project-red','get',publication_id=original['id'])))['publication']==original
   found=(await a.call(scoped('project-red','search',query='Durable platform replacement fixture')))['publications'];assert original in found
   deliveries=await poll_until(b,'project-red',{original['id']},20)
   selected=[d for d in deliveries if d.get('publication_id')==original['id']];assert selected==[delivery]
   await b.call(scoped('project-red','ack',delivery_ids=[delivery['id']]))
   assert not any(d.get('publication_id')==original['id'] for d in (await b.call(scoped('project-red','poll')))['deliveries'])
   reject(await f.raw('blue-a',scoped('project-red','get',publication_id=original['id'])))
   proof={'passed':True,'phase':'after','original_identity_preserved':True,'unacknowledged_delivery_identity_preserved':True,'literal_search_preserved':True,'acknowledgement_survives_polls':True,'cross_project_access_rejected':True,'event_digest':hashlib.sha256(json.dumps(snap,sort_keys=True).encode()).hexdigest(),'lifecycle_qualified':False}
  args.report.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
 finally:await f.close()
asyncio.run(main())
