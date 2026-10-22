#!/usr/bin/env python3
"""Restore actual pending v2 incoming source/discovery jobs and model callbacks.

Public origin submits and authenticated peer status establish acceptance. Only
complete stopped actual files are backed up; snapshot inspection is read-only.
The local typed model is controlled, not a provider or semantic quality test.
"""
from __future__ import annotations
import asyncio
import copy
from datetime import datetime,timezone
import http.client
import json
import os
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from multi_support import Evidence,arguments,scoped
from project_recovery_acceptance import Recovery,RED,BLUE
from project_recovery_allocators import require
from project_recovery_queries import NativeFixture,PeerModel,until,patch
from project_recovery_restore import offline_bundle
from project_recovery_state import digest,exact,route,snapshot


class ModelGate:
    """Forward actual local typed model replies, holding selected successes."""
    def __init__(self,destination):
        self.destination=urlsplit(destination);self.phase='old';self.target=None
        self.rows=[];self.errors=[];self.lock=threading.Lock()
        self.slots=threading.BoundedSemaphore(8)
        self.release={'old':threading.Event(),'new':threading.Event()};outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                if not outer.slots.acquire(blocking=False):self.send_error(429);return
                try:
                    n=int(self.headers['Content-Length']);assert 0<n<=262144
                    raw=self.rfile.read(n);payload=json.loads(raw)
                    instructions=payload.get('questions',{}).get('relevance',{}).get('instructions','')
                    with outer.lock:phase=outer.phase
                    conn=http.client.HTTPConnection(outer.destination.hostname,outer.destination.port,timeout=3)
                    try:
                        conn.request('POST',outer.destination.path,body=raw,headers={'Content-Type':'application/json'})
                        response=conn.getresponse();status=response.status;body=response.read(262145)
                        assert len(body)<=262144
                    finally:conn.close()
                    held=status==200 and outer.target is not None and outer.target in instructions
                    row={'phase':phase,'instructions':instructions,'request_sha256':digest(raw),
                         'status':status,'response_sha256':digest(body),'held':held,'released':False,'sent':False,'write_succeeded':False}
                    with outer.lock:
                        assert len(outer.rows)<1024,'Declared local model relay inventory exhausted'
                        outer.rows.append(row)
                    if held:
                        assert outer.release[phase].wait(30),'Declared30s local model response hold exhausted'
                        row['released']=True
                    self.send_response(status);self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(body)));self.end_headers()
                    try:self.wfile.write(body);row['write_succeeded']=True
                    except (BrokenPipeError,ConnectionResetError):pass
                    row['sent']=True
                except BaseException as error:
                    outer.errors.append(type(error).__name__)
                    try:self.send_error(502)
                    except (BrokenPipeError,ConnectionResetError):pass
                finally:outer.slots.release()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def close(self):
        for event in self.release.values():event.set()
        self.server.shutdown();self.server.server_close();self.thread.join(3)


async def wire(a,b,token,kind,qid,scope):
    command={'protocol_version':2,'op':'source_status' if kind=='source' else 'status',
             'origin_server_id':a.config['server_id'],'origin_project_id':RED,'destination_project_id':RED,'query_id':qid}
    if kind=='source':command['scope']=scope
    async with httpx.AsyncClient(trust_env=False) as http:
        response=await http.post(b.base+'/federation/v2',json=command,headers={'Authorization':'Bearer '+token},timeout=5)
        return response.status_code,response.json()


def jobs(state,queries):
    found={}
    for kind,key in [('source','source_incoming'),('discovery','incoming')]:
        rows=[value for value in state[key].values() if value['command']['query_id']==queries[kind]['id']]
        assert len(rows)==1,'An actual accepted incoming query was lost or duplicated'
        found[kind]=rows[0]
    return found


def compare_accepted(actual,original):
    for kind in original:
        for field in ('command','evidence','federation_v2'):
            assert exact(actual[kind][field])==exact(original[kind][field]),'Incoming accepted '+field+' changed for '+kind
        if 'deadline' in original[kind]:assert actual[kind]['deadline']==original[kind]['deadline']


async def lose_and_restore(args,b,r,backup_id,backup_sha,label,gate):
    _,anchor=route(b.file,RED);nonce=uuid4().hex
    witness=Path(str(b.file)+'.target-down');witness.unlink(missing_ok=True)
    Path(str(b.file)+'.kill-target').write_text(json.dumps({'project_id':RED,'nonce':nonce}))
    await until(witness.exists,'Actual incoming target Store DOWN absent',5)
    observed=json.loads(witness.read_text());assert observed['nonce']==nonce and observed['reason']=='killed' and int(observed['vm_pid'])==b.process.pid
    held=b.root/('lost-incoming-'+label);held.mkdir(mode=0o700)
    for p in [anchor,Path(str(anchor)+'.snapshot')]:assert p.is_file();os.replace(p,held/p.name)
    assert r.status(RED)['availability']=='recovery_required'
    revision=r.revision();receipt=r.call(RED,'project_restore_plan',backup_id=backup_id,manifest_sha256=backup_sha,
        expected_revision=revision,allow_missing=True,message_id='incoming-plan-'+label)
    plan=(await r.settle(RED,receipt,{'ready'}))['plan'];r.assert_plan(plan,RED,'restore')
    gate.phase='new'
    accepted=r.call(RED,'project_restore_apply',plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],
        expected_revision=revision,confirm=True,message_id='incoming-apply-'+label)
    await r.settle(RED,accepted,{'complete'})
    return observed,plan


async def scenario(args,a,b,ar,br,token,scope,model,gate,e,label):
    actor=await a.agent('bridge');remote=await b.agent('bridge');blue=await b.agent('blue-b')
    gate.phase='old';gate.target=None
    for event in gate.release.values():event.clear()
    questions={'source':'incoming-'+label+' Which source maintains image decoders?',
               'discovery':'incoming-'+label+' Which project maintains image decoders?'}
    model.blocked=frozenset(questions.values())
    queries={}
    for kind,op in [('source','source_query'),('discovery','federated_query')]:
        fields={'question':questions[kind],'deadline_ms':120000}
        if kind=='source':fields['sources']=[scope]
        queries[kind]=(await actor.call(scoped(RED,op,**fields),'incoming-'+label+'-'+kind))['query']
    async def accepted():
        for kind,q in queries.items():
            status,value=await wire(a,b,token,kind,q['id'],scope)
            if status!=200 or value['status']!='pending':return False
        return True
    await until(accepted,'Actual remote incoming jobs were not both accepted pending',15)
    b.hard_stop();backup_id='incoming-backup-'+label
    _,backup_sha,backup_state=offline_bundle(b,br,backup_id)
    original=jobs(backup_state,queries);assert all(j['status']=='pending' and j['response'] is None for j in original.values())
    await b.start();remote=await b.agent('bridge');blue=await b.agent('blue-b')
    for kind,q in queries.items():
        remaining=(datetime.fromisoformat(q['deadline_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds()
        assert remaining>0,'Original incoming query deadline expired during cold backup precondition'
        status,value=await wire(a,b,token,kind,q['id'],scope)
        assert status==200 and value['status']=='pending' and value['query_id']==q['id']
    gate.target=questions[label];model.blocked=frozenset(v for k,v in questions.items() if k!=label)
    await until(lambda:any(v['held'] and v['phase']=='old' and gate.target in v['instructions'] for v in gate.rows),
                'Actual selected incoming model success was not held',15)
    tail=(await remote.call(scoped(RED,'publish_record',text='Postbackup peer tail '+label),'incoming-tail-'+label))['record']['publication']
    blue_message=(await remote.call(scoped(BLUE,'send',recipient_id='blue-b',text='Blue incoming restore '+label)))['delivery']
    blue_route=br.status(BLUE)['route'];origin_routes={p:ar.status(p)['route'] for p in [RED,BLUE]}
    config_before=b.admin().call({'op':'config_get'})['config']
    e.record('actual-source-and-discovery-incoming-jobs-backed-up-with-original-bindings-and-deadlines',scenario=label,
             incoming_query_ids={k:v['id'] for k,v in queries.items()},backup_manifest_sha256=backup_sha,provider_posts=0)
    loss,plan=await lose_and_restore(args,b,br,backup_id,backup_sha,label,gate)
    gate.release['old'].set()
    await until(lambda:all(v['sent'] for v in gate.rows if v['held'] and v['phase']=='old'),'Actual old model body was not released',3)
    await asyncio.sleep(.5)
    for kind,q in queries.items():
        status,value=await wire(a,b,token,kind,q['id'],scope)
        assert status==200 and value['status']=='pending','Old incoming model callback populated the restored same-ID job'
    _,path=route(b.file,RED);restored=snapshot(str(path)+'.snapshot');compare_accepted(jobs(restored,queries),original)
    assert tail['id'] not in restored['publications']
    assert b.admin().call({'op':'config_get'})['config']==config_before and br.status(BLUE)['route']==blue_route
    assert {p:ar.status(p)['route'] for p in [RED,BLUE]}==origin_routes
    assert blue_message['id'] in {d['id'] for d in (await blue.call(scoped(BLUE,'poll')))['deliveries']}
    e.record('old-incoming-model-success-cannot-cross-peer-project-recovery-epoch',scenario=label,loss_witness=loss,
             accepted_command_evidence_and_binding_preserved=True,original_deadlines_unchanged=True)
    await until(lambda:any(v['held'] and v['phase']=='new' and gate.target in v['instructions'] for v in gate.rows),
                'Fresh incoming same-ID model evaluation was not observed',15)
    model.blocked=frozenset();gate.release['new'].set()
    completed={}
    for kind,q in queries.items():
        async def done(kind=kind,q=q):
            status,value=await wire(a,b,token,kind,q['id'],scope)
            return value if status==200 and value['status']=='completed' else None
        completed[kind]=await until(done,'Restored incoming job did not complete within its original deadline',15)
        assert completed[kind]['query_id']==q['id'] and completed[kind]['response']['matched'] is True
        getter='get_source_query' if kind=='source' else 'get_federated_query'
        async def origin_done(kind=kind,q=q,getter=getter):
            value=(await actor.call(scoped(RED,getter,query_id=q['id'])))['query']
            return value if value['status']!='pending' else None
        value=await until(origin_done,'Origin did not observe its original restored remote query',15)
        assert value['status']=='completed' and value['deadline_at']==q['deadline_at']
    fresh=(await remote.call(scoped(RED,'publish_record',text='Postbackup peer tail '+label),'incoming-tail-'+label))['record']['publication']
    require(fresh['id'],plan['selected']['allocation_epoch']);assert fresh['id']!=tail['id']
    b.hard_stop();await b.start();remote=await b.agent('bridge')
    for kind,q in queries.items():
        status,value=await wire(a,b,token,kind,q['id'],scope);assert status==200 and value==completed[kind]
    _,path=route(b.file,RED);compare_accepted(jobs(snapshot(str(path)+'.snapshot'),queries),original)
    e.record('fresh-incoming-evaluation-keeps-original-wire-identities-and-survives-peer-cold-restart',scenario=label,
             fresh_publication_id=fresh['id'],allocation_epoch=plan['selected']['allocation_epoch'],provider_posts=0)
    return {'backup_id':backup_id,'backup_sha':backup_sha,'queries':queries,'original':original,'questions':questions}


async def main():
    parser=arguments(__doc__);parser.add_argument('--recovery-schema',type=Path,required=True)
    parser.add_argument('--loss-runner',type=Path,required=True);parser.add_argument('--peer-eventing-rest-url',default='http://127.0.0.1:18085')
    args=parser.parse_args();assert args.hub and not args.image and not args.rest_url and not args.with_model
    aa,ba=copy.copy(args),copy.copy(args);aa.keep_work=args.keep_work/'origin';ba.keep_work=args.keep_work/'peer'
    for target in [aa,ba]:target.command=json.dumps(['elixir',str(args.loss_runner.resolve()),str(args.hub.resolve())])
    ba.eventing_rest_url=args.peer_eventing_rest_url
    a,b=NativeFixture(aa,initialize_projects=False),NativeFixture(ba,initialize_projects=False)
    model=PeerModel();gate=ModelGate(model.url);e=Evidence(args.report,'project-recovery-incoming-peer-jobs')
    e.value.update(artifact_sha256=digest(args.hub.read_bytes()),harness_sha256=digest(Path(__file__).read_bytes()),
        scope='Native incoming accepted source/discovery snapshot preservation, actual model callback epochs and current peer authorization; local controlled typed model only, not provider quality, Docker or release admission.',
        limits={'native_startup_seconds':150,'original_query_deadline_ms':120000,'model_hold_seconds':30,'model_slots':8,'model_inventory':1024},
        dependency_sha256={str(p):digest(p.read_bytes()) for p in [args.loss_runner,args.recovery_schema,Path(__file__).with_name('project_recovery_queries.py'),Path(__file__).with_name('project_recovery_restore.py'),Path(__file__).with_name('multi_support.py')]})
    ab,ba_token=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    scope={'provider':'github','host':'github.com','tenant':'incoming-recovery','resource':'canonical'}
    for f in [a,b]:
        f.config.update(server_id=uuid4().hex,project_id=BLUE,matcher={'url':gate.url if f is b else model.url,'model':'controlled-incoming','timeout_ms':10000,'retry_ms':100},
            federation={'description':'We maintain image decoders.','peers':[],'timeout_ms':10000,'retry_ms':100,'catalog':{'visible':True,'entries':[]}},
            recovery={'backup_root':str(f.root/'offline-backups')})
        Path(f.config['recovery']['backup_root']).mkdir(mode=0o700)
    failure=None
    try:
        async with httpx.AsyncClient(trust_env=False) as http:
            clusters=[]
            for url in [args.eventing_rest_url,args.peer_eventing_rest_url]:
                response=await http.get(url+'/v3/clusters');response.raise_for_status();clusters.append(response.json()['data'][0]['cluster_id'])
            assert len(set(clusters))==2;e.value['broker_cluster_ids']=clusters
        await asyncio.gather(a.start(),b.start());ar,br=Recovery(a,args.recovery_schema),Recovery(b,args.recovery_schema)
        for f,r in [(a,ar),(b,br)]:
            await r.initialize(RED);await r.initialize(BLUE)
        remote=await b.agent('bridge');pub=(await remote.call(scoped(RED,'publish_record',text='Approved incoming image decoder evidence')))['record']['publication']
        projects=copy.deepcopy(b.config['projects']);next(p for p in projects if p['id']==RED)['settings']={'federation':{'description':'We maintain image decoders.',
            'export_publication_ids':[pub['id']],'catalog':{'visible':True,'entries':[{'scope':scope,'aliases':['incoming-codecs'],'description':'Canonical incoming source evidence','relationship':'contained','canonical':True,'export_publication_ids':[pub['id']]}]}}}
        patch(b,{'projects':projects})
        def peer(other,outbound,inbound):return {'server_id':other.config['server_id'],'url':other.base,'token':outbound,'inbound_token':inbound,'project_pairs':[{'local_project_id':RED,'remote_project_id':RED}]}
        patch(b,{'federation':{'peers':[peer(a,ba_token,ab)]}});patch(a,{'federation':{'peers':[peer(b,ab,ba_token)]}})
        actor=await a.agent('bridge')
        async def ready():
            peers=(await actor.call(scoped(RED,'federation_directory')))['peers']
            return peers if len(peers)==1 and peers[0]['status']=='ready' and peers[0]['catalog'] else None
        await until(ready,'Actual canonical incoming target directory did not become ready')
        last=None
        for label in ['source','discovery']:last=await scenario(args,a,b,ar,br,ab,scope,model,gate,e,label)
        # A current grant removal must survive a later restore of the actual
        # earlier bundle containing the old grant. It is policy, not ownership.
        gate.target=None;gate.phase='revoked';gate.release['old'].set();gate.release['new'].set()
        no_pairs=peer(a,ba_token,ab);no_pairs['project_pairs']=[{'local_project_id':BLUE,'remote_project_id':BLUE}]
        patch(b,{'federation':{'peers':[no_pairs]}})
        config_before=b.admin().call({'op':'config_get'})['config'];count=len(gate.rows)
        _,plan=await lose_and_restore(args,b,br,last['backup_id'],last['backup_sha'],'current-grants',gate)
        for kind,q in last['queries'].items():
            remaining=(datetime.fromisoformat(q['deadline_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds()
            assert remaining>0,'Authorization witness original query expired before restored grant check'
            status,value=await wire(a,b,ab,kind,q['id'],scope)
            assert status==403 and value['error']['code']=='FORBIDDEN'
        await asyncio.sleep(.5)
        assert not any(any(question in row['instructions'] for question in last['questions'].values()) for row in gate.rows[count:]),'Unauthorized restored incoming job invoked a model'
        assert b.admin().call({'op':'config_get'})['config']==config_before
        _,path=route(b.file,RED);compare_accepted(jobs(snapshot(str(path)+'.snapshot'),last['queries']),last['original'])
        e.record('restore-does-not-import-backup-peer-grants-or-authorize-incoming-model-work',peer_status=403,
                 original_deadlines_still_live=True,configuration_unchanged=True,provider_posts=0)
        assert not gate.errors,gate.errors
    except BaseException as error:failure=error;raise
    finally:
        cleanup=[]
        for close in [gate.close,model.close,a.close,b.close]:
            try:
                result=close()
                if asyncio.iscoroutine(result):await result
            except BaseException as error:cleanup.append(error)
        e.value.update(model_observations=gate.rows,model_relay_errors=gate.errors,controlled_model_requests=model.calls,provider_posts=0)
        if cleanup:e.value['cleanup_failure_types']=[type(error).__name__ for error in cleanup]
        a.bind_evidence(e);e.finish(failure or (cleanup[0] if cleanup else None))
        if cleanup and failure is None:raise cleanup[0]


if __name__=='__main__':asyncio.run(main())
