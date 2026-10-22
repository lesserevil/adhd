#!/usr/bin/env python3
"""Hold actual Kafka consumer replies across a live selective restore.

A transparent gateway forwards real broker requests and buffers actual records.
It never invents a successful response, record, offset or acknowledgement.
"""
import asyncio
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from uuid import uuid4
import httpx
from multi_support import Fixture, Evidence, arguments, scoped, poll_until
from project_recovery_acceptance import Recovery, RED, BLUE
from project_recovery_restore import offline_bundle
from project_recovery_state import digest, read_json, route
from recovery_image_runtime import RecoveryImageRuntime, bind_down, same_vm, finish_callback
from project_recovery_pending_model import until


class Gate:
    def __init__(self):
        self.entered=threading.Event();self.release=threading.Event();self.attempted=threading.Event();self.observation=None


class ConsumerGateway:
    def __init__(self,upstream):
        self.upstream=upstream.rstrip('/');self.gates={};self.lock=threading.Lock();self.produces=[];fixture=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_GET(self):self.forward()
            def do_POST(self):self.forward()
            def do_DELETE(self):self.forward()
            def forward(self):
                raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
                headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','content-length','connection','accept-encoding'}}
                with httpx.Client(trust_env=False,follow_redirects=False,timeout=10) as client:
                    try: response=client.request(self.command,fixture.upstream+self.path,content=raw,headers=headers)
                    except httpx.HTTPError:self.send_error(502);return
                gate=None
                if self.command=='GET' and '/records?' in self.path and response.status_code==200:
                    rows=response.json()
                    if rows:
                        topics={r['topic'] for r in rows}
                        with fixture.lock:
                            candidates=[g for topic,g in fixture.gates.items() if topic in topics and not g.entered.is_set()]
                            if candidates:
                                assert len(candidates)==1;gate=candidates[0]
                                gate.observation={'path':self.path,'rows':rows,'status':response.status_code,'received_at':time.monotonic()}
                                gate.entered.set()
                if self.command=='POST' and self.path.startswith('/topics/') and response.is_success:
                    fixture.produces.append({'path':self.path,'body':json.loads(raw),'ack':response.json()})
                if gate:assert gate.release.wait(120),'Held real broker reply never released'
                self.send_response(response.status_code)
                if 'content-type' in response.headers:self.send_header('Content-Type',response.headers['content-type'])
                self.send_header('Content-Length',str(len(response.content)));self.end_headers()
                outcome='written'
                try:self.wfile.write(response.content);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):outcome='retired_connection'
                if gate:gate.observation.update(released_at=time.monotonic(),transport=outcome);gate.attempted.set()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def close(self):
        for gate in self.gates.values():gate.release.set()
        self.server.shutdown();self.server.server_close();self.thread.join(2)


async def main(args):
    assert (args.hub or args.image) and not args.with_model
    assert not args.command and not args.rest_url
    f=None;gateway=None;error=None
    e=Evidence(args.report,'adhd/project-recovery-pending-kafka@1')
    gates=[]
    try:
        gateway=ConsumerGateway(args.eventing_rest_url);local=copy.copy(args);local.eventing_rest_url=gateway.url
        runner=Path(__file__).with_name('project_recovery_live_loss.exs').resolve()
        f=RecoveryImageRuntime(local,runner) if args.image else Fixture(local,initialize_projects=False)
        f.config['project_id']=BLUE;f.config['eventing']['timeout_ms']=30000
        backup=f.root/'backups';backup.mkdir(mode=0o700);f.config['recovery']={'backup_root':str(backup)}
        runner=Path(__file__).with_name('project_recovery_live_loss.exs').resolve()
        if not args.image:
            wrapped=copy.copy(local);wrapped.hub=None;wrapped.command=json.dumps(['elixir',str(runner),str(args.hub.resolve())]);f.args=wrapped
        r=Recovery(f,args.recovery_schema)
        e.value.update(artifact_sha256=f.image_runtime.manifest['files']['hub.exs'] if args.image else digest(args.hub.read_bytes()),harness_sha256=digest(Path(__file__).read_bytes()),runner_sha256=digest(runner.read_bytes()),provider_calls=0,
            scope='Actual real Kafka consumer reply across same-VM target-only restore; runtime custody recorded separately, not full platform qualification')
        await f.start();await r.initialize(RED);await r.initialize(BLUE)
        actor=await f.agent('bridge');reader=await f.agent('red-b')
        await reader.call(scoped(RED,'subscribe',mode='raw'))
        oldtopic=f.admin().call(scoped(RED,'eventing_status'))['topic']
        initial=Gate();gates.append(initial);gateway.gates[oldtopic]=initial
        publication=(await actor.call(scoped(RED,'publish_record',text='One accepted event survives physical transport reset.')))['record']['publication']
        await until(initial.entered.is_set,args.deadline,'Actual pre-backup broker row never reached gateway')
        assert not (await reader.call(scoped(RED,'poll')))['deliveries']
        f.hard_stop();_,manifest_sha,state=offline_bundle(f,r,'pending-event')
        assert state['eventing']['events'][publication['id']]['state']!='materialized'
        initial.release.set();await until(initial.attempted.is_set,5,'Pre-backup held response did not retire')
        old=Gate();gates.append(old);gateway.gates[oldtopic]=old
        await f.start()
        owner_vm=f.watched_vm() if args.image else None
        owner_pid=owner_vm['namespace_vm_pid'] if args.image else f.process.pid
        await until(old.entered.is_set,args.deadline,'Actual old-topic row not observed after restart')
        assert {row['topic'] for row in old.observation['rows']}=={oldtopic}
        assert publication['id'] in json.dumps(old.observation['rows'])
        e.record('actual-accepted-pending-event-backed-up-and-old-topic-consumer-response-held')
        actor=await f.agent('bridge');reader=await f.agent('red-b')
        blue=(await actor.call(scoped(BLUE,'publish_record',text='Blue advances while old Red broker response is held.')))['record']['publication']
        oldentry,checkpoint=route(f.file,RED);nonce=uuid4().hex
        arm=Path(str(f.file)+'.kill-target');ack=Path(str(f.file)+'.target-down')
        arm.write_text(json.dumps({'project_id':RED,'nonce':nonce}));arm.chmod(0o600)
        await until(ack.exists,args.deadline,'Actual Red Store DOWN not observed')
        assert read_json(ack)['nonce']==nonce and f.process.poll() is None
        if args.image:bind_down(owner_vm,read_json(ack),nonce,RED);same_vm(owner_vm,f.watched_vm())
        for p in (checkpoint,Path(str(checkpoint)+'.snapshot')):os.replace(p,Path(str(p)+'.lost'))
        receipt=r.call(RED,'project_restore_plan',mode='restore',backup_id='pending-event',manifest_sha256=manifest_sha,
            allow_missing=True,expected_revision=r.revision(),message_id=uuid4().hex)
        plan=(await r.settle(RED,receipt,{'ready'}))['plan'];r.assert_plan(plan,RED,'restore')
        newtopic=plan['selected']['topic'];assert newtopic!=oldtopic
        fresh=Gate();gates.append(fresh);gateway.gates[newtopic]=fresh
        applied=r.call(RED,'project_restore_apply',plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],expected_revision=r.revision(),confirm=True,message_id=uuid4().hex)
        await r.settle(RED,applied,{'complete'})
        if args.image:same_vm(owner_vm,f.watched_vm());assert f.process.poll() is None
        else:assert f.process.pid==owner_pid and f.process.poll() is None
        await until(fresh.entered.is_set,args.deadline,'Actual fresh-topic consumer response not observed')
        assert publication['id'] in json.dumps(fresh.observation['rows'])
        e.record('same-accepted-event-republished-to-fresh-topic-while-both-real-consumer-replies-are-held',old_topic=oldtopic,new_topic=newtopic)
        old.release.set();await until(old.attempted.is_set,args.deadline,'Old real consumer response not attempted')
        await asyncio.sleep(.3)
        assert not fresh.release.is_set()
        assert not (await reader.call(scoped(RED,'poll')))['deliveries']
        status=f.admin().call(scoped(RED,'eventing_status'));assert status['next_offset']==0 and status['quarantined']==0
        assert (await actor.call(scoped(BLUE,'get',publication_id=blue['id'])))['publication']==blue
        e.record('released-old-topic-response-cannot-materialize-or-attach-offset-to-restored-target',response_transport=old.observation['transport'])
        fresh.release.set();await until(fresh.attempted.is_set,args.deadline,'Fresh real consumer response not attempted')
        rows=await poll_until(reader,RED,{publication['id']},args.deadline)
        deliveries=[d for d in rows if d.get('publication_id')==publication['id']];assert len(deliveries)==1
        await reader.call(scoped(RED,'ack',delivery_ids=[deliveries[0]['id']]))
        assert (await actor.call(scoped(RED,'get',publication_id=publication['id'])))['publication']==publication
        e.record('fresh-topic-response-materializes-original-event-once-with-original-publication-identity')
        f.hard_stop();await f.start();reader=await f.agent('red-b');actor=await f.agent('bridge')
        assert deliveries[0]['id'] not in json.dumps(await reader.call(scoped(RED,'poll')))
        assert (await actor.call(scoped(BLUE,'get',publication_id=blue['id'])))['publication']==blue
        e.record('acknowledgement-and-current-blue-survive-real-cold-restart')
        e.value['actual_old_response']=old.observation;e.value['actual_new_response']=fresh.observation
    except BaseException as exc:error=exc
    finally:
        for gate in gates:gate.release.set()
        await finish_callback(f,e,error,gateway.close if gateway else lambda:None)

if __name__=='__main__':
    parser=arguments(__doc__);parser.add_argument('--recovery-schema',type=Path,default=Path('components/hub/project-recovery/interface.schema.json'))
    asyncio.run(main(parser.parse_args()))
