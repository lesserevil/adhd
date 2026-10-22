#!/usr/bin/env python3
"""Actual committed retention-readback failure and unchanged-file cold recovery.

No provider, broker restart, private state edit, or application patch. This is
separate from the positive readiness matrix and never turns its failure green.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from urllib.error import URLError
from http.client import RemoteDisconnected
import time
from unittest.mock import patch
import multi_support

from multi_support import Fixture,Evidence,arguments,scoped,poll_until
from project_recovery_acceptance import Recovery,BLUE
from project_recovery_state import route
from eventing_readiness_proxy import ReadinessProxy
from eventing_readiness_faults import owned_native_identity,reap_owned_native,sanitized_case_diagnostic,assert_retention_policy_capacity as capacity


class TrackedFixture(Fixture):
    """Capture each native Popen identity at assignment, before health awaits."""
    def __init__(self,args,identities):
        self.retention_identities=identities
        self.retention_process_keys={}
        self.retention_health=[]
        super().__init__(args,initialize_projects=False)
    def __setattr__(self,key,value):
        super().__setattr__(key,value)
        if key=='process'and value is not None:
            identity=owned_native_identity(value)
            self.retention_process_keys[value]=(identity['pid'],identity['start_ticks'])
            if not self.image_runtime:self.retention_identities.append(identity)

    async def start(self):
        original=multi_support.httpx.AsyncClient
        async def observed(response):
            if str(response.request.url)==self.base+'/health'and response.status_code==200:
                self.retention_health.append({'at':time.monotonic(),'process_key':self.retention_process_keys.get(self.process)})
        def client(*args,**kwargs):
            hooks={key:list(value)for key,value in(kwargs.get('event_hooks')or{}).items()}
            hooks['response']=hooks.get('response',[])+[observed]
            return original(*args,**{**kwargs,'event_hooks':hooks})
        # Adds no HTTP calls and preserves the original45s readiness loop. The
        # hook runs when response headers arrive, before the response body read.
        with patch.object(multi_support.httpx,'AsyncClient',client):
            await super().start()



def faulted_update(client,command):
    """Recognize only the concrete failure envelope or socket disconnection."""
    disconnected=(RemoteDisconnected,ConnectionResetError,BrokenPipeError)
    try:status,value,_=client.request('/admin/api',command)
    except URLError as error:
        if not isinstance(error.reason,disconnected):raise
        return {'transport_failure_type':type(error.reason).__name__}
    except disconnected as error:return {'transport_failure_type':type(error).__name__}
    assert status==500 and value=={'error':{'code':'INTERNAL','message':'Request failed'}},'Unexpected fault-update response'
    return {'http_status':500,'domain_code':'INTERNAL'}


def same_route(current,original):
    for key in ('server_id','project_id','generation','project_epoch','allocation_epoch','storage_anchor','storage_generation','topic_generation','initialized','aliases'):
        assert current[key]==original[key]


def next_offset(f):
    status=f.admin().call(scoped(BLUE,'eventing_status'))
    status=status.get('eventing',status)
    return status['next_offset']


async def run(args,e):
    f=None;proxy=None;primary=None;cleanup=[];identities=[];runtimes=[];captured=set();closed=set()
    def capture():
        if f is not None and f.process is not None and f.retention_process_keys[f.process]not in captured:
            if not f.image_runtime:
                assert any(row['pid']==f.process.pid for row in identities),'Native launch must be recorded before readiness'
            captured.add(f.retention_process_keys[f.process])
    async def close_current():
        identity=identities[-1]if identities and f.process and identities[-1]['pid']==f.process.pid else None
        if f.process is None:
            await f.close();return
        if f.retention_process_keys.get(f.process)in closed:return
        failure=None
        try:await f.close()
        except BaseException as error:failure=error
        try:
            # A client.close failure must never bypass actual owned VM cleanup.
            if f.image_runtime:
                f.image_runtime.stop()
                f.process.wait(timeout=15)
            else:reap_owned_native(f,identity)
            assert f.process.poll()is not None
            closed.add(f.retention_process_keys[f.process])
            if identity is not None:identity['reaped']=True
            if f.image_runtime and f.image_runtime.verified:runtimes.append(f.image_runtime.identity())
        except BaseException as error:
            if failure is None:failure=error
            else:failure.add_note('Fallback cleanup failure type: '+type(error).__name__)
        finally:
            for log in f.logs:
                try:log.close()
                except BaseException as error:
                    if failure is None:failure=error
                    else:failure.add_note('Log cleanup failure type: '+type(error).__name__)
        if failure is not None:raise failure
    async def start():
        try:await f.start()
        finally:
            # Capture partial native startup while its exact process still exists.
            if f.process is not None and f.process.poll()is None:capture()
    try:
        f=TrackedFixture(args,identities)
        proxy=ReadinessProxy(args.eventing_rest_url)
        f.config['eventing'].update(rest_url=proxy.url,timeout_ms=1000,retry_ms=100)
        f.config['resources']={'eventing_concurrency':16,'project_eventing_concurrency':2}
        await start();r=Recovery(f,args.recovery_schema);initialized=await r.initialize(BLUE)
        blue=await f.agent('blue-b');actor=await f.agent('bridge')
        await blue.call(scoped(BLUE,'subscribe',mode='raw'))
        original=(await actor.call(scoped(BLUE,'publish_record',text='Committed retention recovery preserves original and acknowledgement')))['record']['publication']
        rows=await poll_until(blue,BLUE,{original['id']},args.deadline)
        delivery=next(row for row in rows if row['publication_id']==original['id'])
        await blue.call(scoped(BLUE,'ack',delivery_ids=[delivery['id']]))
        before=f.admin().call({'op':'config_get'});old=before['config']['eventing']['retention_ms'];desired=old//2
        original_route,_=route(f.file,BLUE);offset=next_offset(f)
        status=f.admin().call({'op':'resource_status'})
        e.value['capacity_premise']={'resources':status,'premise':capacity(status)}
        proxy.arm(initialized[-1]['result']['topic'],'retention-recovery')
        transaction=Path(str(f.file)+'.transaction');proxy.transaction=transaction
        assert not transaction.exists()
        command={'op':'config_update','patch':{'eventing':{**f.config['eventing'],'retention_ms':desired}},
                 'expected_revision':before['config_revision'],'message_id':uuid4().hex,'confirm':True}
        update_failure=faulted_update(f.admin().client,command)
        alters=[v for v in proxy.events if v['category']=='alter']
        assert len(alters)==1 and alters[0]['status']==204 and alters[0]['durable_transaction_present']is True
        expected_old={'cleanup_policy':['delete'],'retention_ms':[str(old)]}
        assert any(v['category']=='configs'and v['actual_configuration']==expected_old and v['at']<alters[0]['at']for v in proxy.events)
        assert not any(v['selected_create']for v in proxy.events),'Existing topic must not be recreated'
        injected=[v for v in proxy.events if v['injected']]
        assert injected and all(v['category']=='configs'and v['status']==503 and v['at']>alters[0]['at']and v['durable_transaction_present']is True for v in injected)
        assert transaction.exists()
        decision=json.loads(transaction.read_text());saved=json.loads(f.file.read_text())
        assert decision['config']['eventing']['retention_ms']==saved['eventing']['retention_ms']==desired
        transition=decision['eventing_transition']['id'];assert isinstance(transition,str)and transition
        # A failed writer is reaped before any recovery start. No private file is
        # rewritten, no desired policy is rolled back, and the same proxy stays.
        await close_current()
        e.record('actual-postdecision-retention-failure-keeps-desired-policy-and-decision',
                 failure_type=update_failure,alters=alters,injected_readbacks=injected)
        config_sha=hashlib.sha256(f.file.read_bytes()).hexdigest();decision_sha=hashlib.sha256(transaction.read_bytes()).hexdigest()
        proxy.disable_fault();restart_event=len(proxy.events);f.admin_client=None
        assert hashlib.sha256(f.file.read_bytes()).hexdigest()==config_sha and hashlib.sha256(transaction.read_bytes()).hexdigest()==decision_sha
        health_count=len(f.retention_health)
        await start()
        ready=f.retention_health[health_count]['at']
        recovery_events=proxy.events[restart_event:]
        expected={'cleanup_policy':['delete'],'retention_ms':[str(desired)]}
        verified=[v for v in recovery_events if v['category']=='configs'and v['status']==200 and v['actual_configuration']==expected and v['durable_transaction_present']is True]
        assert verified,'Desired actual broker policy must be read back while decision exists, before startup readiness'
        assert all(v['at']<=ready for v in verified),'Desired policy readback must precede first observed healthy response headers'
        assert not transaction.exists()
        current=f.admin().call({'op':'config_get'})
        assert current['config']['eventing']['retention_ms']==desired and current['config_revision']==before['config_revision']+1
        replay=f.admin().call(command);assert replay['applied']is True
        assert f.admin().call({'op':'config_get'})['config_revision']==current['config_revision']
        same_route(route(f.file,BLUE)[0],original_route);assert next_offset(f)==offset
        blue=await f.agent('blue-b');actor=await f.agent('bridge')
        assert (await actor.call(scoped(BLUE,'get_record',publication_id=original['id'])))['record']['publication']==original
        assert all(row['id']!=delivery['id']for row in(await blue.call(scoped(BLUE,'poll')))['deliveries'])
        e.record('unchanged-files-cold-start-replays-desired-retention-before-readiness',
                 actual_desired_readbacks=verified,first_healthy_headers_at=ready,stable_route=True,stable_next_offset=offset,original_and_ack_preserved=True,mid_receipt_idempotent=True)
        await close_current();second_event=len(proxy.events);f.admin_client=None
        await start()
        assert not transaction.exists()and next_offset(f)==offset
        assert not any(v['category']=='alter'for v in proxy.events[second_event:])
        same_route(route(f.file,BLUE)[0],original_route)
        blue=await f.agent('blue-b');actor=await f.agent('bridge')
        assert(await actor.call(scoped(BLUE,'get_record',publication_id=original['id'])))['record']['publication']==original
        assert all(row['id']!=delivery['id']for row in(await blue.call(scoped(BLUE,'poll')))['deliveries'])
        assert f.admin().call({'op':'config_get'})['config_revision']==current['config_revision']
        e.record('second-cold-start-does-not-repeat-alter-reset-offset-or-replay-ack')
        assert len(captured)==3,'Exactly three owned starts required'
    except BaseException as error:primary=error;raise
    finally:
        if f is not None:
            if f.process is not None and f.process.poll()is None:
                try:capture()
                except BaseException as error:cleanup.append(type(error).__name__)
            try:await close_current()
            except BaseException as error:cleanup.append(type(error).__name__)
        if proxy is not None:
            try:proxy.close()
            except BaseException as error:cleanup.append(type(error).__name__)
        try:
            e.value.update(native_runtime_cases=identities,image_runtimes=runtimes,
                proxy_cleanup={'handlers':proxy.handlers if proxy else 0,'thread_alive':proxy.thread.is_alive()if proxy else False,'failures':proxy.failures if proxy else[]},cleanup_failure_types=cleanup,
                diagnostic=sanitized_case_diagnostic('retention-recovery',proxy,None,None,getattr(f,'config',{}),primary,cleanup))
            e.write()
        except BaseException as error:
            cleanup.append(type(error).__name__)
            if primary is not None:primary.add_note('Evidence failure type: '+type(error).__name__)
            else:raise
        if cleanup:
            if primary is not None:primary.add_note('Cleanup failure types: '+','.join(cleanup))
            else:raise AssertionError('Owned cleanup failed: '+','.join(cleanup))


async def main(args):
    if args.rest_url or args.command or args.with_model:raise ValueError('Requires owned native/image, zero provider')
    assert args.keep_work is not None,'Retained private fixture required for failed-decision evidence'
    args.keep_work.mkdir(mode=0o700,parents=True,exist_ok=False)
    e=Evidence(args.report,'adhd/eventing-retention-recovery@1');e.value.update(provider_calls=0,
        artifact_sha256=json.loads(args.image_manifest.read_text())['files']['hub.exs']if args.image else hashlib.sha256(args.hub.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),proxy_sha256=hashlib.sha256(Path(__file__).with_name('eventing_readiness_proxy.py').read_bytes()).hexdigest())
    try:await run(args,e)
    except BaseException as error:
        try:e.finish(error)
        except BaseException as failure:error.add_note('Final evidence failure type: '+type(failure).__name__)
        raise
    else:e.finish()


if __name__=='__main__':
    p=arguments(__doc__);p.add_argument('--recovery-schema',type=Path,default=Path(__file__).resolve().parent.parent/'components/hub/project-recovery/interface.schema.json')
    asyncio.run(main(p.parse_args()))
