#!/usr/bin/env python3
"""Public hot registry invariants: dry/apply/file reload and actual cold restart."""
import asyncio,copy,hashlib,json,time
from pathlib import Path
from uuid import uuid4
from multi_support import Evidence,Fixture,arguments,poll_until,scoped

async def until(fn,seconds=10):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  v=fn()
  if v:return v
  await asyncio.sleep(.1)
 raise AssertionError('Registry rejection observation timed out')

async def case(args,no_default,e):
 local=copy.copy(args);local.keep_work=None;f=Fixture(local);f.config['eventing']={'enabled':False}
 if no_default:f.config.pop('project_id')
 label='no-default' if no_default else 'legacy-default'
 try:
  await f.start();bridge=await f.agent('bridge');subs={};publications={}
  for p,name in [('project-red','red-b'),('project-blue','blue-b')]:
   b=await f.agent(name);subs[p]=b
   await b.call(scoped(p,'subscribe',mode='raw'))
   publication=(await bridge.call(scoped(p,'publish',text='Retained registry original '+p)))['publication'];publications[p]=publication
   rows=await poll_until(b,p,{publication['id']},args.deadline)
   await b.call(scoped(p,'ack',delivery_ids=[r['id'] for r in rows]))
  admin=f.admin().client;before=admin.api({'op':'config_get'})['config'];revision=before['config_revision']
  ids=[p['id'] for p in before['projects']];pid=f.process.pid
  removal=[p for p in before['projects'] if p['id']=='project-red']
  grants={a:[p for p in ps if p=='project-red'] for a,ps in f.config['agent_projects'].items()}
  patches=[{'projects':None,'agent_projects':None},{'projects':removal,'agent_projects':grants},{'project_id':'project-red' if no_default else 'project-blue'}]
  for patch in patches:
   for op in ['config_validate','config_update']:
    cmd={'op':op,'patch':patch,'expected_revision':revision}
    if op=='config_update':cmd.update(message_id=uuid4().hex,confirm=True)
    status,value,_=admin.request('/admin/api',cmd)
    assert status==409 and value['error']['code']=='CONFIG_APPLY_FAILED',(label,op,status,value)
    now=admin.api({'op':'config_get'})['config'];assert now['config_revision']==revision and [p['id'] for p in now['projects']]==ids
  e.record(label+'-dry-and-apply-reject-downgrade-removal-and-default-rebinding',negative_requests=6)
  raw=f.file.read_bytes();base=json.loads(raw)
  proposals=[{k:v for k,v in base.items() if k not in ('projects','agent_projects')},dict(base,projects=removal,agent_projects=grants),dict(base,server_id=('0'*32 if base['server_id']!='0'*32 else '1'*32)),dict(base,project_id='project-red' if no_default else 'project-blue')]
  for candidate in proposals:
   f.file.write_text(json.dumps(candidate));f.file.chmod(0o600)
   await until(lambda:admin.api({'op':'config_get'})['reload_status']=='error')
   now=admin.api({'op':'config_get'})['config'];assert now['config_revision']==revision and [p['id'] for p in now['projects']]==ids and now['server_id']==before['server_id']
   f.file.write_bytes(raw)
   await until(lambda:admin.api({'op':'config_get'})['reload_status']=='ready')
  assert f.process.pid==pid
  e.record(label+'-file-reload-rejects-downgrade-removal-server-and-default-identity-changes',proposals=4)
  f.hard_stop();await f.start()
  for p,pub in publications.items():
   assert (await bridge.call(scoped(p,'get',publication_id=pub['id'])))['publication']==pub
   assert not (await subs[p].call(scoped(p,'poll')))['deliveries']
  after=f.admin().client.api({'op':'config_get'})['config'];assert after['config_revision']==revision and after['server_id']==before['server_id'] and [p['id'] for p in after['projects']]==ids
  e.record(label+'-cold-restart-preserves-both-project-originals-acks-registry-and-revision')
 finally:
  await f.close();f.bind_evidence(e,key='runtime_'+label)

async def main(args):
 if args.rest_url:raise ValueError('An owned fixture is required')
 e=Evidence(args.report,'adhd/hot-registry-invariants@1');e.value['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 if args.hub:e.value['artifact_sha256']=hashlib.sha256(args.hub.read_bytes()).hexdigest()
 try:
  for mode in [False,True]:await case(args,mode,e)
 except BaseException as error:e.finish(error);raise
 else:e.finish()
if __name__=='__main__':asyncio.run(main(arguments(__doc__).parse_args()))
