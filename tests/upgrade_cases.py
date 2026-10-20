"""Upgrade a real pre-console store; do not synthesize implementation state."""
import shutil
import hub_acceptance as h
async def schema_two_upgrade_checks(old_command, new_command, root, record):
 f=h.ModelFixture();root=root / 'schema-two-upgrade'; hub=h.Hub(old_command,root,f.url);a=b=None
 try:
  hub.start();a=await hub.agent('agent-a');b=await hub.agent('agent-b')
  await b.call({'op':'subscribe','description':'API updates'})
  command={'op':'publish','text':'API v2 preserved source event','information_type':'status','source':{'kind':'agent','id':'agent-a','item_id':'v2-upgrade-event'},'data':{'progress':21}}
  result=await a.call(command,'original-source-message')
  ds=await h.wait_deliveries(b,lambda ds:bool(ds));await b.call({'op':'ack','delivery_ids':[ds[0]['id']]})
  await a.call({'op':'send','recipient_id':'agent-b','text':'private v2 upgrade pending'})
  f.mode='error';pending=await a.call({'op':'publish','text':'API pending before UI upgrade'})
  hub.stop();shutil.copy2(root/'hub.dets',root/'before-upgrade.dets');hub.command=new_command;hub.start()
  assert await a.call(command,'new-source-message')==result,'Previous source-event deduplication lost during schema-2 upgrade'
  upgraded=(await b.call({'op':'get','publication_id':result['publication']['id']}))['publication']
  assert {key:upgraded[key] for key in result['publication']}==result['publication']
  assert upgraded['context']=={} and len(upgraded['content_identity'])==64
  assert len((await b.call({'op':'poll'}))['deliveries'])==1
  f.mode='match';await h.wait_deliveries(b,lambda ds:any(d.get('publication_id')==pending['publication']['id'] for d in ds))
  record('real-schema-two-upgrade-preserves-source-event-dedup-history-ack-and-pending-jobs')
 finally:
  if a:await a.close()
  if b:await b.close()
  hub.stop();f.close()
