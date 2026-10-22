#!/usr/bin/env python3
"""Real source/discovery query identities and callbacks across target recovery.

Two native hubs and distinct real brokers; a transparent bounded relay holds
actual successful peer responses. The model is a local typed fixture, never a
provider. Live writer loss uses the existing test-only Store DOWN observer.
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from multi_support import Evidence, Fixture, arguments, scoped
from project_recovery_acceptance import Recovery, RED, BLUE
from project_recovery_allocators import require
from project_recovery_restore import offline_bundle
from project_recovery_state import digest, route



class NativeFixture(Fixture):
    async def start(self):
        if not self.file.exists():
            self.file.write_text(json.dumps(self.config));self.file.chmod(0o600)
        command=json.loads(self.args.command) if self.args.command else ['elixir',str(self.args.hub.resolve())]
        import subprocess
        self.logs=[(self.root/name).open('ab') for name in ('stdout.log','stderr.log')]
        self.process=subprocess.Popen(command+[json.dumps(['serve',str(self.file)])],stdout=self.logs[0],stderr=self.logs[1],start_new_session=True)
        deadline=time.monotonic()+150
        async with httpx.AsyncClient(trust_env=False) as http:
            while time.monotonic()<deadline:
                assert self.process.poll() is None,'Owned native hub exited before readiness'
                try:
                    if (await http.get(self.base+'/health',timeout=1)).status_code==200:return
                except httpx.HTTPError:pass
                await asyncio.sleep(.1)
        raise AssertionError('Declared150s native compilation/readiness bound exhausted')


class PeerModel:
    def __init__(self):
        self.blocked=frozenset();self.calls=0;outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                size=int(self.headers['Content-Length']);assert 0<size<=262144
                payload=json.loads(self.rfile.read(size));outer.calls+=1
                if any(question in json.dumps(payload) for question in outer.blocked):
                    self.send_response(503);self.end_headers();return
                body=json.dumps({'model':payload['model'],'answers':{'relevance':{'type':'noul','noul':.99}}}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)


class QueryRelay:
    def __init__(self, destination):
        self.destination=urlsplit(destination)
        self.phase='old';self.targets=set();self.rows=[];self.errors=[]
        self.lock=threading.Lock();self.slots=threading.BoundedSemaphore(12)
        self.release={'old':threading.Event(),'new':threading.Event()}
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                if not outer.slots.acquire(blocking=False):self.send_error(429);return
                try:
                    size=int(self.headers.get('Content-Length','0'));assert 0<size<=262144
                    raw=self.rfile.read(size);command=json.loads(raw)
                    assert self.path=='/federation/v2'
                    with outer.lock:phase=outer.phase
                    connection=http.client.HTTPConnection(outer.destination.hostname,outer.destination.port,timeout=3)
                    try:
                        connection.request('POST',self.path,body=raw,headers={'Content-Type':'application/json','Authorization':self.headers.get('Authorization','')})
                        reply=connection.getresponse();status=reply.status;body=reply.read(262145)
                        assert len(body)<=262144
                    finally:connection.close()
                    response=json.loads(body)
                    held=(command.get('query_id') in outer.targets and status in (200,202)
                        and response.get('status')=='completed')
                    row={'request':command,'status':status,'response':response,
                         'response_sha256':digest(body),'phase':phase,'held':held,'released':False,'write_succeeded':False}
                    with outer.lock:
                        assert len(outer.rows)<512,'Bounded real-peer relay inventory exhausted'
                        outer.rows.append(row)
                    if held:
                        assert outer.release[phase].wait(30),'Bounded peer reply hold expired'
                        row['released']=True
                    self.send_response(status);self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(body)));self.end_headers()
                    try:self.wfile.write(body);row['write_succeeded']=True
                    except (BrokenPipeError,ConnectionResetError):pass
                except BaseException as error:
                    outer.errors.append(type(error).__name__)
                    try:self.send_error(502)
                    except (BrokenPipeError,ConnectionResetError):pass
                finally:outer.slots.release()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def close(self):
        for event in self.release.values():event.set()
        self.server.shutdown();self.server.server_close();self.thread.join(3)


async def until(fn, message, seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=fn()
        if asyncio.iscoroutine(value):value=await value
        if value:return value
        await asyncio.sleep(.03)
    raise AssertionError(message)


def patch(f, value):return f.admin().call({'op':'config_update','patch':value},mutation=True)


async def checks(args,a,b,relay,model,e):
    ar,br=Recovery(a,args.recovery_schema),Recovery(b,args.recovery_schema)
    await asyncio.gather(a.start(),b.start())
    for f,r in [(a,ar),(b,br)]:
        await r.initialize(RED);await r.initialize(BLUE)
    actor=await a.agent('bridge');blue=await a.agent('blue-b');remote=await b.agent('bridge')
    publication=(await remote.call(scoped(RED,'publish_record',text='Public image decoder evidence')) )['record']['publication']
    private=(await remote.call(scoped(RED,'send',recipient_id='red-b',text='PRIVATE_QUERY_RECOVERY_SENTINEL')))['delivery']
    scope={'provider':'github','host':'github.com','tenant':'query-recovery','resource':'canonical'}
    projects=copy.deepcopy(b.config['projects'])
    next(p for p in projects if p['id']==RED)['settings']={'federation':{
        'description':'We maintain image decoders.', 'export_publication_ids':[publication['id']],
        'catalog':{'visible':True,'entries':[{'scope':scope,'aliases':['image-codecs'],'description':'Canonical image decoder project',
        'relationship':'contained','canonical':True,'export_publication_ids':[publication['id']]}]}}}
    patch(b,{'projects':projects})
    ab,ba=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    def peer(other,url,outbound,inbound):
        return {'server_id':other.config['server_id'],'url':url,'token':outbound,'inbound_token':inbound,
                'project_pairs':[{'local_project_id':RED,'remote_project_id':RED}]}
    patch(b,{'federation':{'peers':[peer(a,a.base,ba,ab)]}})
    patch(a,{'federation':{'peers':[peer(b,relay.url,ab,ba)]}})
    async def ready():
        peers=(await actor.call(scoped(RED,'federation_directory')))['peers']
        return peers if len(peers)==1 and peers[0]['status']=='ready' and peers[0]['catalog'] else None
    await until(ready,'Actual authenticated canonical directory did not become ready')
    for label in ('source','discovery'):
        await scenario(args,a,b,ar,relay,model,e,scope,private,label)


async def scenario(args,a,b,ar,relay,model,e,scope,private,label):
    actor=await a.agent('bridge');blue=await a.agent('blue-b')
    relay.phase='old';relay.targets=set()
    for event in relay.release.values():event.clear()
    async def ready():
        peers=(await actor.call(scoped(RED,'federation_directory')))['peers']
        return peers if len(peers)==1 and peers[0]['status']=='ready' and peers[0]['catalog'] else None
    await until(ready,'Canonical peer not ready before fixed query scenario')
    commands={'source':scoped(RED,'source_query',question='Which source maintains image decoders?',sources=[scope],deadline_ms=120000),
              'discovery':scoped(RED,'federated_query',question='Which project maintains image decoders?',deadline_ms=120000)}
    getters={'source':'get_source_query','discovery':'get_federated_query'}
    model.blocked=frozenset('retained-'+label+' '+command['question'] for command in commands.values())
    async def create(tag):
        return {kind:(await actor.call({**command,'question':tag+' '+command['question']},tag+'-'+kind))['query'] for kind,command in commands.items()}
    async def read(kind,q):return (await actor.call(scoped(RED,getters[kind],query_id=q['id'])))['query']
    def submitted(queries):
        wanted={q['id'] for q in queries.values()}
        return wanted<={r['request'].get('query_id') for r in relay.rows if r['request']['op'] in ('submit','source_submit') and r['status'] in (200,202)}
    retained=await create('retained-'+label);await until(lambda:submitted(retained),'Retained remote jobs were not actually accepted')
    for kind,q in retained.items():assert (await read(kind,q))['status']=='pending'
    a.hard_stop();_,backup_sha,_=offline_bundle(a,ar,'pending-query-backup-'+label);await a.start()
    actor=await a.agent('bridge');blue=await a.agent('blue-b')
    await until(ready,'Directory did not recover after actual offline backup')
    model.blocked=model.blocked|frozenset('lost-'+label+' '+command['question'] for command in commands.values())
    lost=await create('lost-'+label);await until(lambda:submitted(lost),'Postbackup remote jobs were not actually accepted')
    relay.targets={lost[label]['id']}
    model.blocked=frozenset(q['question'] for q in retained.values())
    await until(lambda:relay.targets<={r['request'].get('query_id') for r in relay.rows if r['held'] and r['phase']=='old'},
                'Actual successful old-epoch '+label+' peer response was not held',20)
    for kind,q in retained.items():assert (await read(kind,q))['status']=='pending'
    before=ar.status(RED)['route'];blue_route=ar.status(BLUE)['route']
    blue_message=(await actor.call(scoped(BLUE,'send',recipient_id='blue-b',text='Blue pending-query recovery sentinel')))['delivery']
    e.record('accepted-pending-source-and-discovery-queries-backed-up-with-real-pinned-remote-jobs',
             scenario=label,retained_ids={k:v['id'] for k,v in retained.items()},lost_ids={k:v['id'] for k,v in lost.items()},provider_posts=0)
    _,anchor=route(a.file,RED);nonce=uuid4().hex
    Path(str(a.file)+'.target-down').unlink(missing_ok=True)
    Path(str(a.file)+'.kill-target').write_text(json.dumps({'project_id':RED,'nonce':nonce}))
    witness_path=Path(str(a.file)+'.target-down');await until(witness_path.exists,'Actual target Store DOWN was not witnessed',5)
    witness=json.loads(witness_path.read_text());assert witness['nonce']==nonce and witness['reason']=='killed' and int(witness['vm_pid'])==a.process.pid
    lost_pair=a.root/('lost-query-pair-'+label);lost_pair.mkdir(mode=0o700)
    for path in [anchor,Path(str(anchor)+'.snapshot')]:assert path.is_file();os.replace(path,lost_pair/path.name)
    assert ar.status(RED)['availability']=='recovery_required'
    config_before=a.admin().call({'op':'config_get'})['config'];revision=ar.revision()
    receipt=ar.call(RED,'project_restore_plan',backup_id='pending-query-backup-'+label,manifest_sha256=backup_sha,
                    expected_revision=revision,allow_missing=True,message_id='query-plan-'+label)
    plan=(await ar.settle(RED,receipt,{'ready'}))['plan'];ar.assert_plan(plan,RED,'restore')
    relay.phase='new'
    accepted=ar.call(RED,'project_restore_apply',plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],
                    expected_revision=revision,confirm=True,message_id='query-apply-'+label)
    await ar.settle(RED,accepted,{'complete'})
    assert ar.status(RED)['route']['allocation_epoch']!=before['allocation_epoch']
    relay.release['old'].set();await asyncio.sleep(.5)
    for kind,q in retained.items():
        current=await read(kind,q);assert current['status']=='pending','An old callback populated restored pending work before a fresh response'
        for field in ('id','project_id','owner_id','question','created_at','deadline_at'):assert current[field]==q[field],field
    for kind,q in lost.items():
        denied=await a.raw('bridge',scoped(RED,getters[kind],query_id=q['id']))
        assert denied.status_code==200 and denied.json()['error']['data'][0]['reason']=='NOT_FOUND'
    assert ar.status(BLUE)['route']==blue_route and a.admin().call({'op':'config_get'})['config']==config_before
    assert blue_message['id'] in {d['id'] for d in (await blue.call(scoped(BLUE,'poll')))['deliveries']}
    e.record('released-old-source-and-discovery-success-cannot-cross-live-target-epoch',scenario=label,loss_witness=witness,
             allocation_epoch=plan['selected']['allocation_epoch'],same_vm=True)
    await until(lambda:{q['id'] for q in retained.values()}<={r['request'].get('query_id') for r in relay.rows if r['phase']=='new'},
                'Restored pending queries did not recheck original remote jobs',15)
    model.blocked=frozenset();relay.release['new'].set()
    completed={}
    for kind,q in retained.items():
        async def finished(kind=kind,q=q):
            value=await read(kind,q);return value if value['status']!='pending' else None
        completed[kind]=await until(finished,'Restored accepted query did not complete under its original deadline',15)
        assert completed[kind]['status']=='completed',completed[kind]['status']
        assert completed[kind]['deadline_at']==q['deadline_at']
    fresh=await create('lost-'+label)
    for kind,q in fresh.items():
        require(q['id'],plan['selected']['allocation_epoch']);assert q['id']!=lost[kind]['id']
        async def done(kind=kind,q=q):
            value=await read(kind,q);return value if value['status']!='pending' else None
        q=await until(done,'Fresh postrestore query did not complete',15);assert q['status']=='completed'
    # Matching request identities, including destination and source scope, are
    # the actual remote side-effect namespace. No replacement retained query ID
    # may be silently allocated to resume the backed-up logical query.
    for q in retained.values():
        rows=[r for r in relay.rows if r['request'].get('query_id')==q['id']]
        old={json.dumps({k:v for k,v in r['request'].items() if k not in ('op','question','deadline_at','owner_server_id','catalog_revision')},sort_keys=True) for r in rows if r['phase']=='old'}
        new={json.dumps({k:v for k,v in r['request'].items() if k not in ('op','question','deadline_at','owner_server_id','catalog_revision')},sort_keys=True) for r in rows if r['phase']=='new'}
        assert new and new<=old,'Recovery changed a retained query remote identity/pin'
    source=completed['source']['results'][0]
    assert source['owner_server_id']==b.config['server_id'] and source['owner_project_id']==RED
    assert source['scope']==scope and source['response']['server_id']==b.config['server_id']
    assert len(completed['discovery']['responses'])==1 and completed['discovery']['responses'][0]['server_id']==b.config['server_id']
    assert 'PRIVATE_QUERY_RECOVERY_SENTINEL' not in json.dumps([completed,relay.rows])
    assert private['id'] not in json.dumps(completed)
    e.record('fresh-source-and-discovery-identities-use-new-epoch-while-retained-jobs-keep-original-remote-pins',scenario=label,fresh_ids={k:v['id'] for k,v in fresh.items()},provider_posts=0)
    a.hard_stop();await a.start();actor=await a.agent('bridge')
    for kind,q in retained.items():assert await read(kind,q)==completed[kind]
    assert ar.status(BLUE)['route']==blue_route
    assert not relay.errors,relay.errors
    e.value['relay_observations']=relay.rows
    e.record('cold-start-preserves-completed-original-query-identities-and-unrelated-project',scenario=label)


async def main():
    parser=arguments(__doc__);parser.add_argument('--recovery-schema',type=Path,required=True)
    parser.add_argument('--loss-runner',type=Path,required=True)
    parser.add_argument('--peer-eventing-rest-url',default='http://127.0.0.1:18085')
    args=parser.parse_args();assert args.hub and not args.rest_url and not args.image and not args.with_model
    args.keep_work.mkdir(parents=True,mode=0o700,exist_ok=True)
    aa,ba=copy.copy(args),copy.copy(args);aa.keep_work=args.keep_work/'origin';ba.keep_work=args.keep_work/'peer'
    aa.command=json.dumps(['elixir',str(args.loss_runner.resolve()),str(args.hub.resolve())]);ba.command=None
    ba.eventing_rest_url=args.peer_eventing_rest_url
    a,b=NativeFixture(aa,initialize_projects=False),NativeFixture(ba,initialize_projects=False)
    model=PeerModel();relay=QueryRelay(b.base);e=Evidence(args.report,'project-recovery-source-discovery-queries')
    e.value.update(artifact_sha256=digest(args.hub.read_bytes()),harness_sha256=digest(Path(__file__).read_bytes()),
        dependency_sha256={str(p):digest(p.read_bytes()) for p in [args.loss_runner,args.recovery_schema,Path(__file__).with_name('project_recovery_restore.py'),Path(__file__).with_name('multi_support.py')]},
        limits={'relay_slots':12,'relay_requests':512,'held_response_seconds':30,'query_deadline_ms':120000},
        scope='Native actual two-hub/two-broker pending source/discovery and callback fencing; local controlled model only, not semantic quality or release admission.')
    for f in (a,b):
        f.config.update(server_id=uuid4().hex,project_id=BLUE,matcher={'url':model.url,'model':'controlled-peer','timeout_ms':1000,'retry_ms':100},
            federation={'description':'We maintain image decoders.','peers':[],'timeout_ms':10000,'retry_ms':100,'catalog':{'visible':True,'entries':[]}},
            recovery={'backup_root':str(f.root/'offline-backups')})
        Path(f.config['recovery']['backup_root']).mkdir(mode=0o700)
    failure=None
    try:
        async with httpx.AsyncClient(trust_env=False) as http:
            clusters=[]
            for url in [args.eventing_rest_url,args.peer_eventing_rest_url]:
                response=await http.get(url+'/v3/clusters');response.raise_for_status();clusters.append(response.json()['data'][0]['cluster_id'])
            assert len(set(clusters))==2,'Each actual server requires its own Kafka cluster';e.value['broker_cluster_ids']=clusters
        await checks(args,a,b,relay,model,e)
    except BaseException as error:
        failure=error;raise
    finally:
        cleanup_errors=[]
        for close in (relay.close,model.close,a.close,b.close):
            try:
                result=close()
                if asyncio.iscoroutine(result):await result
            except BaseException as error:cleanup_errors.append(error)
        e.value.update(relay_errors=relay.errors,relay_observations=relay.rows,controlled_model_requests=model.calls,provider_posts=0)
        if cleanup_errors:e.value['cleanup_failure_types']=[type(error).__name__ for error in cleanup_errors]
        a.bind_evidence(e);e.finish(failure or (cleanup_errors[0] if cleanup_errors else None))
        if cleanup_errors and failure is None:raise cleanup_errors[0]


if __name__=='__main__':asyncio.run(main())
