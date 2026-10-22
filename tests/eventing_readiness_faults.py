#!/usr/bin/env python3
"""Independent real-broker topic-readiness and one-budget recovery acceptance.

Declared HTTP visibility faults surround actual Kafka creation/configuration;
positive cases require genuine broker delivery, never mocked broker success.
No model, shared broker stop, application patch or private state write is used.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from eventing_readiness_proxy import (ReadinessProxy,queue_premise,QUEUE_EVENTING_TIMEOUT_MS,
    QUEUE_RECOVERY_TIMEOUT_MS,QUEUE_OBSERVATION_MAX_SECONDS)
from multi_support import Fixture,Evidence,arguments,scoped,poll_until
from project_recovery_acceptance import Recovery,RED,BLUE
from project_recovery_state import route

CASES=('lag','queue-control','duplicate','duplicate-bad-topology','never','queue','forbidden','server-error','malformed','bad-cleanup','partitions-float','retention-missing','retention-float','retention-negative','retention-duplicate','existing-retention',
       'offset-nonzero','offset-negative','offset-missing','offset-float','offset-string')


async def until(predicate,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        await asyncio.sleep(.02)
    raise AssertionError('Declared bounded observation was not reached')


async def run_case(args,case,e):
    proxy=ReadinessProxy(args.eventing_rest_url)
    local=copy.copy(args);local.keep_work=(args.keep_work/case)if args.keep_work else None
    f=Fixture(local,initialize_projects=False);r=Recovery(f,args.recovery_schema)
    f.config['eventing'].update(rest_url=proxy.url,timeout_ms=1000,retry_ms=100)
    if case in ('queue','queue-control'):
        f.config['eventing']['timeout_ms']=QUEUE_EVENTING_TIMEOUT_MS
        f.config['recovery']={'timeout_ms':QUEUE_RECOVERY_TIMEOUT_MS}
        f.config['resources']={'eventing_concurrency':1,'project_eventing_concurrency':1}
    original=None;native_identity=None;primary=None
    try:
        await f.start()
        if not f.image_runtime:
            pid=f.process.pid
            native_identity={'pid':pid,'start_ticks':int(Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1].split()[19]),
                'command_sha256':hashlib.sha256(Path('/proc/'+str(pid)+'/cmdline').read_bytes()).hexdigest()}
        blue_initialized=await r.initialize(BLUE)
        blue=await f.agent('blue-b');actor=await f.agent('bridge')
        await blue.call(scoped(BLUE,'subscribe',mode='raw'))
        original=(await actor.call(scoped(BLUE,'publish_record',text='Unrelated readiness witness')))['record']['publication']
        rows=await poll_until(blue,BLUE,{original['id']},args.deadline)
        delivery=next(d for d in rows if d['publication_id']==original['id'])
        await blue.call(scoped(BLUE,'ack',delivery_ids=[delivery['id']]))
        before=f.admin().call({'op':'config_get'});blue_route,_=route(f.file,BLUE);red_route,_=route(f.file,RED)
        if case=='existing-retention':
            proxy.arm(blue_initialized[-1]['result']['topic'],case)
            proxy.transaction=Path(str(f.file)+'.transaction')
            desired=before['config']['eventing']['retention_ms']//2
            f.admin().call({'op':'config_update','patch':{'eventing':{**f.config['eventing'],'retention_ms':desired}},
                'expected_revision':before['config_revision'],'message_id':uuid4().hex,'confirm':True},mutation=True)
            alters=[v for v in proxy.events if v['category']=='alter']
            assert alters and all(v['durable_transaction_present']for v in alters)
            assert any(v['category']=='configs'and v['at']>alters[-1]['at']for v in proxy.events)
            assert f.admin().call({'op':'config_get'})['config']['eventing']['retention_ms']==desired
            after_route=route(f.file,BLUE)[0]
            for field in ['server_id','project_id','generation','project_epoch','allocation_epoch','storage_anchor','aliases']:
                assert after_route[field]==blue_route[field]
            assert (await actor.call(scoped(BLUE,'get_record',publication_id=original['id'])))['record']['publication']==original
            assert all(d['id']!=delivery['id']for d in (await blue.call(scoped(BLUE,'poll')))['deliveries'])
            e.record(case,actual_postdecision_alters=alters,readback_observed=True,original_and_ack_preserved=True)
            return
        planned=r.call(RED,'project_restore_plan',mode='initialize',confirm=True,expected_revision=r.revision(),message_id=uuid4().hex)
        plan=(await r.settle(RED,planned,{'ready'}))['plan'];r.assert_plan(plan,RED,'initialize')
        proxy.arm(plan['selected']['topic'],case)
        if case=='queue':
            proxy.hold=True
            await until(proxy.held.is_set,args.deadline)
        started=time.monotonic()
        receipt=r.call(RED,'project_restore_apply',plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],
            expected_revision=r.revision(),confirm=True,message_id=uuid4().hex)
        if case=='queue':
            def queued():
                status=f.admin().call({'op':'resource_status'})
                lane=status['lanes']['eventing']
                if lane['projects'].get(RED,{}).get('queued',0)>=1:return status
            try:
                resources=await until(queued,QUEUE_OBSERVATION_MAX_SECONDS)
            except AssertionError as error:
                raise AssertionError('Fixture premise failed: no timely actual Red queued observation')from error
            premise=queue_premise(proxy.held_at,time.monotonic())
            assert resources['limits']['eventing_concurrency']==1
            assert resources['lanes']['eventing']['projects'][BLUE]['active']==1
            assert resources['limits']['project_eventing_concurrency']==1
            assert resources['lanes']['eventing']['active']==1
            e.value.setdefault('queue_observations',[]).append({'resources':resources,'premise':premise})
        operation=await r.settle(RED,receipt,{'complete','failed'})
        elapsed=time.monotonic()-started
        proxy.release.set()
        events=list(proxy.events);selected=[v for v in events if v['category']is not None or v['selected_create']]
        creates=[v for v in selected if v['selected_create']]
        assert len(creates)<=1,'Visibility retries repeated creation'
        after=f.admin().call({'op':'config_get'});assert after==before
        current_blue,_=route(f.file,BLUE);assert current_blue==blue_route
        assert (await actor.call(scoped(BLUE,'get_record',publication_id=original['id'])))['record']['publication']==original
        assert all(d['id']!=delivery['id']for d in (await blue.call(scoped(BLUE,'poll')))['deliveries'])
        if case in ('lag','queue-control','duplicate'):
            assert operation['state']=='complete'and len(creates)==1
            if case in ('lag','queue-control'):assert sum(v['injected']for v in selected)==(2 if case=='lag'else 20)
            if case=='duplicate':assert creates[0]['status']==400 and any(v['category']=='metadata'and v['at']>creates[0]['at']for v in selected)
            red=await f.agent('red-b');await red.call(scoped(RED,'subscribe',mode='raw'))
            item=(await actor.call(scoped(RED,'publish_record',text='Real broker readiness accepted')))['record']['publication']
            await poll_until(red,RED,{item['id']},args.deadline)
        else:
            assert operation['state']=='failed',operation
            assert operation['failure']['code']in {'RESTORE_IO_ERROR','RESTORE_TIMEOUT'}
            assert not Path(str(f.file)+'.transaction').exists()
            current_red,_=route(f.file,RED);assert current_red==red_route
            assert r.status(RED)['availability']=='uninitialized'
            if case in ('never','queue'):
                # This is an experiment observation margin, not a widened app
                # deadline: queue+retries share the declared1000/3000ms budget.
                budget=f.config['eventing']['timeout_ms']
                assert elapsed<=budget/1000+1.0,('Single Eventing budget reset/overrun with longer owning recovery budget',elapsed,budget)
            if case in ('forbidden','server-error','malformed','bad-cleanup','partitions-float','retention-missing','retention-float','retention-negative','retention-duplicate','existing-retention','duplicate-bad-topology'):
                injected=[v for v in selected if v['injected']]
                assert len(injected)==1,'Nontransient failure was retried'
        assert not proxy.failures
        e.record(case,operation_state=operation['state'],elapsed_seconds=elapsed,eventing_timeout_ms=f.config['eventing']['timeout_ms'],
                 recovery_timeout_ms=f.config.get('recovery',{}).get('timeout_ms'),statuses=selected,created_requests=len(creates),real_blue_record_and_ack_preserved=True)
    except BaseException as error:
        primary=error
        raise
    finally:
        failures=[]
        for close in [f.close,proxy.close]:
            try:
                value=close()
                if asyncio.iscoroutine(value):await value
            except BaseException as error:failures.append(type(error).__name__)
        try:
            f.bind_evidence(e,key='runtime_'+case)
            if native_identity is not None:
                native_identity['reaped']=f.process.poll() is not None
                assert native_identity['reaped']
                e.value.setdefault('native_runtime_cases',{})[case]=native_identity
            e.value.setdefault('proxy_cleanup',[]).append({'case':case,'handlers':proxy.handlers,'thread_alive':proxy.thread.is_alive(),'failures':proxy.failures,'cleanup_failure_types':failures})
            e.write()
        except BaseException as error:failures.append(type(error).__name__)
        if failures:
            if primary is not None:primary.add_note('Owned cleanup/evidence failures: '+','.join(failures))
            else:raise AssertionError('Owned cleanup/evidence failures: '+','.join(failures))


async def main(args):
    if args.rest_url or args.command or args.with_model:raise ValueError('Requires owned --hub/--image, no model')
    if args.keep_work:args.keep_work.mkdir(mode=0o700,parents=True,exist_ok=False)
    e=Evidence(args.report,'adhd/eventing-readiness-faults@1');e.value.update(provider_calls=0,
        artifact_sha256=json.loads(args.image_manifest.read_text())['files']['hub.exs']if args.image else hashlib.sha256(args.hub.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        proxy_sha256=hashlib.sha256(Path(__file__).with_name('eventing_readiness_proxy.py').read_bytes()).hexdigest(),
        scope='Real Kafka creation/metadata/delivery plus declared selected-topic faults; no replicated durability or inference claim')
    try:
        for case in args.cases.split(','):
            assert case in CASES
            await run_case(args,case,e)
    except BaseException as error:e.finish(error);raise
    else:e.finish()
    finally:e.write()


if __name__=='__main__':
    p=arguments(__doc__);p.add_argument('--cases',default=','.join(CASES));p.add_argument('--recovery-schema',type=Path,default=Path(__file__).resolve().parent.parent/'components/hub/project-recovery/interface.schema.json')
    asyncio.run(main(p.parse_args()))
