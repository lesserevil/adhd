#!/usr/bin/env python3
"""Actual pending History HTTP callback across target-only live restore.

The test runner kills only the fixture's nondefault project writer. All accepted
records and recovery operations use public Admin/A2A; complete stopped files
supply the backup. The controlled local evaluator holds an actual POST until
activation. No external model, product fault endpoint or fabricated state.
"""
import asyncio
import copy
import json
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from multi_support import Fixture, Evidence, arguments, scoped
from project_recovery_acceptance import Recovery, RED, BLUE
from project_recovery_restore import offline_bundle
from project_recovery_state import digest, read_json, route, snapshot
from recovery_image_runtime import RecoveryImageRuntime, bind_down, same_vm, finish_callback


class GatedEvaluator:
    def __init__(self):
        self.entered=threading.Event(); self.release=threading.Event(); self.attempted=threading.Event()
        self.requests=[]; self.replies=[]; fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def send(self,value):
                raw=json.dumps(value).encode(); self.send_response(200)
                self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                try: self.wfile.write(raw); self.wfile.flush(); return 'written'
                except (BrokenPipeError,ConnectionResetError): return 'retired_connection'
            def do_GET(self): self.send({'ready':True})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.requests.append({'body':body,'entered_at':time.monotonic()}); fixture.entered.set()
                assert fixture.release.wait(120), 'Fixture never released actual HTTP response'
                answers={}
                for key,q in body['questions'].items():
                    labels=q['criteria']; selected='direct' if key=='assessment' else 'quote_0'
                    if selected not in labels: selected='unknown'
                    answers[key]={'type':'choice','choice':selected,'confidence':1.0,
                        'probabilities':{label:float(label==selected) for label in labels}}
                result={'model':body['model'],'answers':answers}
                outcome=self.send(result)
                fixture.replies.append({'body':result,'at':time.monotonic(),'transport':outcome});fixture.attempted.set()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler); self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def close(self):
        self.release.set();self.server.shutdown();self.server.server_close();self.thread.join(2)


async def until(predicate,deadline,message):
    end=time.monotonic()+deadline
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        await asyncio.sleep(.02)
    raise AssertionError(message)


async def main(args):
    assert (args.hub or args.image) and not args.with_model
    assert not args.command and not args.rest_url
    f=None;model=None;error=None
    e=Evidence(args.report,'adhd/project-recovery-pending-model@1')
    try:
        runner=Path(__file__).with_name('project_recovery_live_loss.exs').resolve()
        f=RecoveryImageRuntime(args,runner) if args.image else Fixture(args,initialize_projects=False)
        model=GatedEvaluator()
        f.config['project_id']=BLUE
        f.config['matcher']={'url':model.url,'model':'controlled-history-epoch','timeout_ms':30000,'retry_ms':100}
        f.config['history']={'timeout_ms':30000,'budget':{'time_ms':120000}}
        backups=f.root/'backups';backups.mkdir(mode=0o700)
        f.config['recovery']={'backup_root':str(backups)}
        runner=Path(__file__).with_name('project_recovery_live_loss.exs').resolve()
        if not args.image:
            wrapped=copy.copy(args);wrapped.hub=None
            wrapped.command=json.dumps(['elixir',str(runner),str(args.hub.resolve())]);f.args=wrapped
        r=Recovery(f,args.recovery_schema)
        e.value.update(artifact_sha256=f.image_runtime.manifest['files']['hub.exs'] if args.image else digest(args.hub.read_bytes()),runner_sha256=digest(runner.read_bytes()),
            harness_sha256=digest(Path(__file__).read_bytes()),scope='Actual controlled History HTTP callback and one live nondefault Store loss; not full service callback qualification',external_provider_calls=0)
        await f.start();await r.initialize(RED);await r.initialize(BLUE)
        f.hard_stop();_,manifest_sha,backup_state=offline_bundle(f,r,'empty-before-pending')
        await f.start()
        owner_vm=f.watched_vm() if args.image else None
        owner_pid=owner_vm['namespace_vm_pid'] if args.image else f.process.pid
        actor=await f.agent('bridge')
        oldpub=(await actor.call(scoped(RED,'publish_record',text='The retained observation was amber.')))['record']['publication']
        query=(await actor.call(scoped(RED,'query_history',question='What was the retained observation?')))['query']
        await until(model.entered.is_set,args.deadline,'Actual History POST never reached controlled evaluator')
        assert model.requests[0]['body']['questions']
        oldentry,checkpoint=route(f.file,RED)
        e.record('actual-post-backup-history-query-is-pending-at-http-evaluator',query_id=query['id'],publication_id=oldpub['id'])
        blue=(await actor.call(scoped(BLUE,'publish_record',text='Blue stays live while Red awaits its evaluator.')))['record']['publication']
        nonce=uuid4().hex;arm=Path(str(f.file)+'.kill-target');ack=Path(str(f.file)+'.target-down')
        arm.write_text(json.dumps({'project_id':RED,'nonce':nonce}));arm.chmod(0o600)
        await until(ack.exists,args.deadline,'Actual nondefault Store DOWN not observed')
        down=read_json(ack);assert down['nonce']==nonce and int(down['vm_pid'])==owner_pid
        if args.image:bind_down(owner_vm,down,nonce,RED);same_vm(owner_vm,f.watched_vm())
        assert f.process.poll() is None
        for p in (checkpoint,Path(str(checkpoint)+'.snapshot')): os.replace(p,Path(str(p)+'.lost'))
        receipt=r.call(RED,'project_restore_plan',mode='restore',backup_id='empty-before-pending',
            manifest_sha256=manifest_sha,allow_missing=True,expected_revision=r.revision(),message_id=uuid4().hex)
        plan=(await r.settle(RED,receipt,{'ready'}))['plan'];r.assert_plan(plan,RED,'restore')
        accepted=r.call(RED,'project_restore_apply',plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],
            expected_revision=r.revision(),confirm=True,message_id=uuid4().hex)
        await r.settle(RED,accepted,{'complete'})
        if args.image:same_vm(owner_vm,f.watched_vm());assert f.process.poll() is None
        else:assert f.process.pid==owner_pid and f.process.poll() is None
        assert not model.release.is_set()
        newentry,newpath=route(f.file,RED);assert newentry['project_epoch']!=oldentry['project_epoch']
        e.record('same-hub-restores-earlier-empty-target-while-real-old-model-post-is-held',old_epoch=oldentry['project_epoch'],new_epoch=newentry['project_epoch'])
        model.release.set();await until(model.attempted.is_set,args.deadline,'Actual held evaluator response never attempted')
        await asyncio.sleep(.5)
        response=await f.raw('bridge',scoped(RED,'get_history_query',query_id=query['id']))
        assert response.status_code==200
        assert response.json()['error']['data'][0]['metadata']['code']=='NOT_FOUND'
        current=snapshot(Path(str(newpath)+'.snapshot'))
        assert query['id'] not in json.dumps(current) and oldpub['id'] not in json.dumps(current)
        blue_records=(await actor.call(scoped(BLUE,'get_record',publication_id=blue['id'])))
        assert blue['id'] in json.dumps(blue_records)
        fresh=(await actor.call(scoped(RED,'publish_record',text='Fresh target epoch remains writable.')))['record']['publication']
        assert fresh['id'] not in {oldpub['id'],query['id']}
        e.record('released-old-response-cannot-recreate-discarded-query-or-publication-and-blue-survives',response_transport=model.replies[0]['transport'])
        f.hard_stop();await f.start()
        actor=await f.agent('bridge')
        assert fresh['id'] in json.dumps(await actor.call(scoped(RED,'get_record',publication_id=fresh['id'])))
        assert blue['id'] in json.dumps(await actor.call(scoped(BLUE,'get_record',publication_id=blue['id'])))
        e.record('fresh-target-and-current-blue-survive-another-real-cold-start')
        e.value['controlled_requests']=model.requests;e.value['controlled_replies']=model.replies
    except BaseException as exc:error=exc
    finally:
        if model:model.release.set()
        await finish_callback(f,e,error,model.close if model else lambda:None)

if __name__=='__main__':
    parser=arguments(__doc__)
    parser.add_argument('--recovery-schema',type=Path,default=Path('components/hub/project-recovery/interface.schema.json'))
    asyncio.run(main(parser.parse_args()))
