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
import os
import signal
import subprocess
from pathlib import Path
import time
from uuid import uuid4

from eventing_readiness_proxy import (ReadinessProxy,queue_premise,QUEUE_EVENTING_TIMEOUT_MS,
    QUEUE_RECOVERY_TIMEOUT_MS,QUEUE_OBSERVATION_MAX_SECONDS)
from multi_support import Fixture,Evidence,arguments,scoped,poll_until
from project_recovery_acceptance import Recovery,RED,BLUE
from project_recovery_state import route

CASES=('lag','queue-control','duplicate','duplicate-bad-topology','never','queue','forbidden','server-error','malformed','bad-cleanup','partitions-float','retention-missing','retention-float','retention-negative','retention-duplicate','existing-retention',
       'offset-nonzero','offset-negative','offset-missing','offset-float','offset-string','metadata-lag','offset-end-float')


async def until(predicate,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        await asyncio.sleep(.02)
    raise AssertionError('Declared bounded observation was not reached')


def owned_native_identity(process):
    pid=process.pid
    return {'pid':pid,'start_ticks':int(Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1].split()[19]),
            'command_sha256':hashlib.sha256(Path('/proc/'+str(pid)+'/cmdline').read_bytes()).hexdigest()}


def reap_owned_native(fixture,identity):
    """Fallback only for this Fixture's still-live native Popen and exact identity."""
    process=fixture.process
    if fixture.image_runtime or process is None or process.poll()is not None:return
    assert identity is not None and owned_native_identity(process)==identity,'Owned native start identity changed; refusing signal'
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        assert owned_native_identity(process)==identity,'Owned native start identity changed before hard stop'
        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
    assert process.poll()is not None


def sanitized_case_diagnostic(case,proxy,operation,elapsed,config,primary,cleanup_types):
    """Bounded public-policy trace only; never retain paths, bodies or identities."""
    states={'queued','verifying','ready','applying','decided','complete','failed'}
    codes={'RESTORE_INVALID_BACKUP','RESTORE_CONFLICT','RESTORE_STALE_PLAN','RESTORE_TIMEOUT','RESTORE_IO_ERROR','RESTORE_UNAVAILABLE','RECOVERY_REQUIRED'}
    reasons={'hash','schema','identity','alias','owner_missing','owner_changed','owner_unprovable','populated','missing_admission','partial_target','path','revision','route','expired','limits','io','transport','timeout','decision_integrity','snapshot_integrity'}
    def number(value,maximum):
        return value if type(value)in(int,float)and 0<=value<=maximum else None
    def typename(value):
        return value if isinstance(value,str)and len(value)<=64 and value.isidentifier()else 'UnknownError'
    def policy(value):
        if not isinstance(value,dict):return None
        if value.get('invalid_data')is True:return {'invalid_data':True}
        result={}
        for key in ('cleanup_policy','retention_ms'):
            rows=value.get(key,[]);rows=rows if isinstance(rows,list)else[];safe=[]
            for row in rows[:8]:
                if key=='cleanup_policy'and row in ('delete','compact'):safe.append(row)
                elif key=='retention_ms'and isinstance(row,str)and len(row)<=19 and (row=='-1'or row=='0'or row.isascii()and row.isdecimal()and row[0]!='0')and -1<=int(row)<=9223372036854775807:safe.append(row)
                elif isinstance(row,dict)and isinstance(row.get('invalid_value_type'),str)and row.get('invalid_value_type')in {'str','int','float','bool','dict','list','NoneType'}:safe.append({'invalid_value_type':row['invalid_value_type']})
                else:safe.append({'invalid_value':True})
            result[key]=safe
            if len(rows)>8:result[key+'_truncated']=True
        return result
    events_available=proxy is not None and hasattr(proxy,'events')
    events=list(proxy.events)if events_available else[];safe_events=[]
    for event in events[:256]:
        if not isinstance(event,dict):continue
        safe_events.append({'at':number(event.get('at'),1e12),
            'method':event.get('method')if event.get('method')in ('GET','POST','DELETE')else None,
            'category':event.get('category')if event.get('category')in ('metadata','configs','alter','offsets')else None,
            'status':event.get('status')if type(event.get('status'))is int and 100<=event['status']<=599 else None,
            'selected_create':event.get('selected_create')is True,'injected':event.get('injected')is True,
            'actual_configuration':policy(event.get('actual_configuration')),
            'durable_transaction_present':event.get('durable_transaction_present')if type(event.get('durable_transaction_present'))is bool else None})
    selected=None
    if isinstance(operation,dict):
        failure=operation.get('failure');safe_failure=None
        if isinstance(failure,dict):
            safe_failure={'code':failure.get('code')if isinstance(failure.get('code'),str)and failure.get('code')in codes else None,
                'reason':failure.get('reason')if isinstance(failure.get('reason'),str)and failure.get('reason')in reasons else None,
                'retryable':failure.get('retryable')if type(failure.get('retryable'))is bool else None}
        selected={'state':operation.get('state')if isinstance(operation.get('state'),str)and operation.get('state')in states else None,'failure':safe_failure}
    eventing=config.get('eventing',{})if isinstance(config,dict)else{}
    recovery=config.get('recovery',{})if isinstance(config,dict)else{}
    return {'case':case,'selected_operation':selected,'elapsed_seconds':number(elapsed,3600),
        'eventing_timeout_ms':number(eventing.get('timeout_ms'),1000000000),
        'recovery_timeout_ms':number(recovery.get('timeout_ms'),1000000000),
        'events':safe_events,'events_available':events_available,'event_count':len(events),'events_truncated':len(events)>256,
        'assertion_or_primary_type':typename(type(primary).__name__)if primary is not None else None,
        'cleanup_failure_types':[typename(v)for v in cleanup_types[:16]],'cleanup_types_truncated':len(cleanup_types)>16}


async def run_case(args,case,e):
    proxy=None;f=None;native_identity=None;primary=None;operation=None;started=None;elapsed=None
    try:
        local=copy.copy(args);local.keep_work=(args.keep_work/case)if args.keep_work else None
        f=Fixture(local,initialize_projects=False)
        proxy=ReadinessProxy(args.eventing_rest_url)
        r=Recovery(f,args.recovery_schema)
        f.config['eventing'].update(rest_url=proxy.url,timeout_ms=1000,retry_ms=100)
        if case in ('queue','queue-control'):
            f.config['eventing']['timeout_ms']=QUEUE_EVENTING_TIMEOUT_MS
            f.config['recovery']={'timeout_ms':QUEUE_RECOVERY_TIMEOUT_MS}
            f.config['resources']={'eventing_concurrency':1,'project_eventing_concurrency':1}
        original=None
        await f.start()
        if not f.image_runtime:
            native_identity=owned_native_identity(f.process)
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
            assert not proxy.transaction.exists(),'Prior transaction must not falsely witness this decision'
            old_retention=before['config']['eventing']['retention_ms']
            desired=old_retention//2
            f.admin().call({'op':'config_update','patch':{'eventing':{**f.config['eventing'],'retention_ms':desired}},
                'expected_revision':before['config_revision'],'message_id':uuid4().hex,'confirm':True},mutation=True)
            alters=[v for v in proxy.events if v['category']=='alter']
            assert alters and all(v['durable_transaction_present']for v in alters)
            assert any(v['category']=='configs'and v['at']>alters[-1]['at']for v in proxy.events)
            expected_old={'cleanup_policy':['delete'],'retention_ms':[str(old_retention)]}
            expected_new={'cleanup_policy':['delete'],'retention_ms':[str(desired)]}
            prior_reads=[v for v in proxy.events if v['category']=='configs'and v['at']<alters[0]['at']and v['actual_configuration']==expected_old]
            verified_reads=[v for v in proxy.events if v['category']=='configs'and v['at']>alters[-1]['at']and v['actual_configuration']==expected_new]
            assert prior_reads,'Actual broker old valid retention must be observed before authorized alter'
            assert verified_reads,'Actual broker desired retention must be read back after authorized alter'
            assert f.admin().call({'op':'config_get'})['config']['eventing']['retention_ms']==desired
            after_route=route(f.file,BLUE)[0]
            for field in ['server_id','project_id','generation','project_epoch','allocation_epoch','storage_anchor','aliases']:
                assert after_route[field]==blue_route[field]
            assert (await actor.call(scoped(BLUE,'get_record',publication_id=original['id'])))['record']['publication']==original
            assert all(d['id']!=delivery['id']for d in (await blue.call(scoped(BLUE,'poll')))['deliveries'])
            e.record(case,actual_postdecision_alters=alters,actual_predecision_old_configuration=prior_reads,actual_postdecision_desired_configuration=verified_reads,readback_observed=True,original_and_ack_preserved=True)
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
        if case in ('lag','queue-control','duplicate','metadata-lag'):
            assert operation['state']=='complete'and len(creates)==1
            if case in ('lag','queue-control'):assert sum(v['injected']for v in selected)==(2 if case=='lag'else 20)
            if case=='metadata-lag':assert sum(v['injected']for v in selected)==1 and any(v['category']=='metadata'and v['status']==200 and not v['injected']for v in selected)
            if case=='duplicate':assert creates[0]['status']==400 and any(v['category']=='metadata'and v['at']>creates[0]['at']for v in selected)
            red=await f.agent('red-b');await red.call(scoped(RED,'subscribe',mode='raw'))
            item=(await actor.call(scoped(RED,'publish_record',text='Real broker readiness accepted')))['record']['publication']
            await poll_until(red,RED,{item['id']},args.deadline)
        else:
            assert operation['state']=='failed',operation
            def red_released():
                status=f.admin().call({'op':'resource_status'})
                counts=status['lanes']['eventing']['projects'].get(RED,{'active':0,'queued':0})
                if counts['active']==0 and counts['queued']==0:return status
            released=await until(red_released,2)
            e.value.setdefault('failed_operation_resource_release',[]).append({'case':case,'resources':released})
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
        diagnostic_elapsed=elapsed if elapsed is not None else(time.monotonic()-started if started is not None else None)
        failures=[]
        if f is not None and not f.image_runtime and f.process is not None and f.process.poll()is None and native_identity is None:
            try:native_identity=owned_native_identity(f.process)
            except BaseException as error:failures.append(type(error).__name__)
        closers=([f.close]if f is not None else[])+([proxy.close]if proxy is not None else[])
        for close in closers:
            try:
                value=close()
                if asyncio.iscoroutine(value):await value
            except BaseException as error:failures.append(type(error).__name__)
        if f is not None:
            try:reap_owned_native(f,native_identity)
            except BaseException as error:failures.append(type(error).__name__)
        try:
            if f is not None:f.bind_evidence(e,key='runtime_'+case)
            if native_identity is not None:
                native_identity['reaped']=f.process.poll() is not None
                assert native_identity['reaped']
                e.value.setdefault('native_runtime_cases',{})[case]=native_identity
            e.value.setdefault('proxy_cleanup',[]).append({'case':case,'constructed':proxy is not None,'handlers':proxy.handlers if proxy else 0,'thread_alive':proxy.thread.is_alive()if proxy else False,'failures':proxy.failures if proxy else[],'cleanup_failure_types':failures})
        except BaseException as error:failures.append(type(error).__name__)
        try:
            e.value.setdefault('case_diagnostics',{})[case]=sanitized_case_diagnostic(case,proxy,operation,diagnostic_elapsed,getattr(f,'config',{}),primary,failures)
            e.write()
        except BaseException as error:failures.append(type(error).__name__)
        if failures:
            if primary is not None:primary.add_note('Owned cleanup/evidence failures: '+','.join(failures))
            else:raise AssertionError('Owned cleanup/evidence failures: '+','.join(failures))


async def main(args):
    if args.rest_url or args.command or args.with_model:raise ValueError('Requires owned --hub/--image, no model')
    if args.keep_work:args.keep_work.mkdir(mode=0o700,parents=True,exist_ok=False)
    e=Evidence(args.report,'adhd/eventing-readiness-faults@2');e.value.update(provider_calls=0,planned_cases=list(CASES),original_case_prefix_count=21,
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
