"""Public Admin initialization after hot relocation with inaccessible old storage."""
import asyncio,os
from pathlib import Path
from uuid import uuid4
from recovery_image_support import retained_recovery_fixture, close_recovery_fixture
from multi_support import Fixture,Evidence,arguments,scoped
from project_recovery_acceptance import Recovery,RED,BLUE,HIDDEN
from project_recovery_state import route,registry

async def main():
 p=arguments(__doc__);p.add_argument('--recovery-schema',type=Path,required=True);a=p.parse_args()
 assert not a.rest_url and not a.with_model
 f=retained_recovery_fixture(Fixture(a,initialize_projects=False));e=Evidence(a.report,'uninitialized-project-relocation')
 e.value.update(scope='NoKafka/noModel public Admin initialization after accepted hot anchor relocation; inaccessible old directory is actual mode000',lifecycle_admitted=False)
 e.value['limitations']=['No Kafka, model, crash or selective restore qualification; lifecycle admission is independently bound by the parent plan.']
 old=f.root/'old-storage';new=f.root/'new-storage';old.mkdir(mode=0o700);new.mkdir(mode=0o700)
 f.config['store_path']=str(old/'root.dets');f.config['eventing']['enabled']=False
 try:
  await f.start();r=Recovery(f,a.recovery_schema);await r.initialize(RED)
  actor=await f.agent('bridge');original=(await actor.call(scoped(RED,'send',recipient_id='red-b',text='Red survives hot relocation'),'red-before-move'))['delivery']
  config=f.admin().call({'op':'config_get'});before=registry(f.file);destination=new/'root.dets'
  unknown=before['projects'][BLUE];assert not unknown['initialized']
  source=Path(unknown['storage_anchor']);source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(b'foreign source');source.chmod(0o600)
  f.admin().call({'op':'config_update','patch':{'store_path':str(destination)}},mutation=True,expected=409)
  assert f.admin().call({'op':'config_get'})==config and source.read_bytes()==b'foreign source';source.unlink()
  e.record('unexpected-uninitialized-source-file-blocks-hot-rebase-without-config-or-byte-change')
  target=Path(str(destination)+str(source)[len(f.config['store_path']):]+'.snapshot');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'foreign destination');target.chmod(0o600)
  f.admin().call({'op':'config_update','patch':{'store_path':str(destination)}},mutation=True,expected=409)
  assert f.admin().call({'op':'config_get'})==config and target.read_bytes()==b'foreign destination';target.unlink()
  e.record('unexpected-uninitialized-target-file-blocks-hot-rebase-without-config-or-byte-change')
  pid=f.process.pid
  f.admin().call({'op':'config_update','patch':{'store_path':str(destination)}},mutation=True)
  assert f.process.pid==pid and r.status(BLUE)['availability']=='uninitialized'
  changed=registry(f.file)['projects'][BLUE]
  assert changed['storage_anchor'].startswith(str(new)+os.sep)
  assert changed['generation']==0 and changed['project_epoch'] is None and changed['allocation_epoch'] is None
  e.record('accepted-hot-move-rebases-proven-empty-route-without-admitting-or-allocating-namespace')
  old.chmod(0)
  try:os.stat(old/'root.dets.projects')
  except PermissionError:pass
  else:raise AssertionError('Old storage is not actually inaccessible to this test process')
  await r.initialize(BLUE)
  assert str(route(f.file,BLUE)[1]).startswith(str(new)+os.sep)
  later=(await actor.call(scoped(BLUE,'send',recipient_id='blue-b',text='Blue admitted after relocation'),'blue-after-move'))['delivery']
  recipient=await f.agent('red-b');assert original['id'] in {x['id']for x in (await recipient.call(scoped(RED,'poll')))['deliveries']}
  e.record('authenticated-admin-can-initialize-new-project-while-old-storage-is-inaccessible')
  f.hard_stop();await f.start()
  assert r.status(RED)['availability']=='ready' and r.status(BLUE)['availability']=='ready' and r.status(HIDDEN)['availability']=='uninitialized'
  recipient=await f.agent('blue-b');assert later['id'] in {x['id']for x in (await recipient.call(scoped(BLUE,'poll')))['deliveries']}
  e.record('cold-restart-opens-current-routes-and-retains-postmove-accepted-data-with-old-storage-inaccessible')
  e.finish()
 except BaseException as error:e.finish(error);raise
 finally:
  try:old.chmod(0o700)
  finally:await close_recovery_fixture(f,e)

if __name__=='__main__':asyncio.run(main())
