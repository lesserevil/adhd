#!/usr/bin/env python3
"""Prospective two-runtime optimizer qualification. Default phase only reads files.

Old preregistration/provider manifests remain immutable historical inputs. Every
startup phase requires separately reviewed plan AND driver hashes. Model-free
phases never instantiate ProviderBudget; inference additionally requires both
closed seals in one reviewed amendment and explicit provider authorization.
"""
import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import time

import httpx

from multi_support import Evidence, scoped
from optimization_neutral_runtime import (RefusingModel, SealedRuntime, canonical,
    private_seal, python_pins, sha, validate_target, verify_pins, verify_seal)
from optimization_neutral_witness import ProviderBudget, WireAgent, checks
from project_recovery_queries import until

PARENT_SHA='b069fdf8f7bf4ff5e85754850cedc42deb6ef28dd7c5c876b3869df8a1f6724f'
NATIVE_ROOT='/home/horde/src/adhd/.worktrees/acceptance/_build/optimizer-neutral-preflight/run-c'
IMAGE_ROOT='/home/horde/src/adhd/_build/oq37i'
IMAGE_SERVER='1a7bee386af8a0ce3b7e151994796108'
BUDGET={'maximum_upstream_http_posts':106,'maximum_wall_clock_seconds':900,'relay_retries':0}
ENTRIES=['optimization_neutral_pair.py','optimization_neutral_runtime.py','optimization_neutral_witness.py']


def parent_manifest(path):
    raw=path.read_bytes();assert sha(raw)==PARENT_SHA,'Historical prepared manifest changed'
    value=json.loads(raw)
    assert value['provider_budget']==BUDGET and len(value['continuation']['original_records'])==6
    return value


def semantics(parent):
    return {key:copy.deepcopy(parent[key]) for key in ('preregistration','provider_budget','provider','original_attempt','optimization')}


def template(parent):
    return {'schema':'adhd/neutral-optimizer-two-runtime@1','status':'PROSPECTIVE_NO_EXECUTION',
        'execution_hold':'Accepted final targets, zero-model seals, code and separate execution approvals required.',
        'historical_parent_sha256':PARENT_SHA,'semantics_sha256':sha(canonical(semantics(parent))),
        'native_originals_sha256':copy.deepcopy(parent['continuation']['original_records_sha256']),
        'semantic_plan':semantics(parent),'target_release':'final38',
        'targets':{
            'native':{'kind':'native','fixture_root':NATIVE_ROOT,'server_id':parent['preregistration']['target']['server_id'],
                'broker_rest_url':'http://127.0.0.1:18082','broker_cluster_id':None,'artifact_sha256':None,
                'artifact_path':None,'admission_evidence':None},
            'image':{'kind':'image','fixture_root':IMAGE_ROOT,'server_id':IMAGE_SERVER,
                'broker_rest_url':'http://127.0.0.1:18085','broker_cluster_id':None,'artifact_sha256':None,
                'artifact_path':None,'admission_evidence':None,'image_config_identity':None,
                'image_manifest':None,'canonical_manifest_sha256':None}},
        'budgets':{'per_runtime':BUDGET,'aggregate_posts':212,'aggregate_provider_seconds':1800,
            'retries':0,'borrow_unused_allowance':False},
        'order':['native','image'],'one_proposal_per_runtime':True,'adapt_to_other_result':False,
        'sealed_inputs':None,'python_dependency_sha256':python_pins(ENTRIES),
        'assertion_clarification':{'training':'Require actual completed empty search, recorded baseline recipe, confirmed gap and independent current owned groups.',
            'held_out_and_regression':'Original scan-only Archive planning is allowed only with completed expected gold answer, full nontruncated History and unchanged actual paired current-baseline/candidate answer/recall/cost/native gates.',
            'all_seven':'Require model-free empty lexical baseline and exact complete depth2 original gold closure before each original attempt.'}}


def validate_plan(plan,parent,*,bound=False):
    assert plan['schema']=='adhd/neutral-optimizer-two-runtime@1'
    assert plan['historical_parent_sha256']==PARENT_SHA
    assert plan['semantic_plan']==semantics(parent) and plan['semantics_sha256']==sha(canonical(semantics(parent)))
    baseline=template(parent)
    for key in ('budgets','order','one_proposal_per_runtime','adapt_to_other_result','assertion_clarification','native_originals_sha256'):
        assert plan[key]==baseline[key], 'Reviewed experiment/gates/order changed'
    for label in ('native','image'):
        target=plan['targets'][label]
        for key in ('kind','fixture_root','server_id','broker_rest_url'):
            assert target[key]==baseline['targets'][label][key], 'Preregistered runtime identity changed'
        if bound:
            validate_target(target,target['artifact_path'])
            admission=target['admission_evidence']
            assert admission and sha(Path(admission['path']).read_bytes())==admission['sha256']
            assert isinstance(target['broker_cluster_id'],str) and target['broker_cluster_id']
    if bound:
        a,b=[plan['targets'][key] for key in ('native','image')]
        assert a['artifact_sha256']==b['artifact_sha256'] and a['broker_cluster_id']!=b['broker_cluster_id']
    assert plan['python_dependency_sha256']==baseline['python_dependency_sha256'], 'Transitive dependency closure changed or was omitted'
    verify_pins(plan['python_dependency_sha256'])


def fixture_args(target,report):
    return SimpleNamespace(keep_work=Path(target['fixture_root']),hub=Path(target['artifact_path']),
        image=target.get('image_config_identity'),image_manifest=Path(target['image_manifest']) if target.get('image_manifest') else None,
        command=None,rest_url=None,credentials=None,with_model=False,initialize_projects=False,
        eventing_rest_url=target['broker_rest_url'],report=Path(report),deadline=300)


async def broker_identity(target):
    async with httpx.AsyncClient(trust_env=False) as client:
        response=await client.get(target['broker_rest_url']+'/v3/clusters',timeout=5)
        response.raise_for_status();clusters=response.json()['data']
        assert len(clusters)==1 and clusters[0]['cluster_id']==target['broker_cluster_id']
        return clusters[0]['cluster_id']


def once(path,value):
    with path.open('x') as output:output.write(value+'\n')
    path.chmod(0o600)


async def close_owned(f):
    # SealedRuntime.close always attempts actual runtime cleanup even if SDK
    # close fails. Preserve any cleanup failure; never turn it into a pass.
    if f is not None:await f.close()


def config_profile(config,parent):
    p=parent['preregistration']
    assert config['retrieval']['recipe']==p['recipe'] and config['history']==p['history'] and config['archive']==p['archive']
    assert not config.get('optimization',{}).get('enabled',False)
    assert not config.get('federation',{}).get('peers',[])


def original_bindings(parent,target,captures):
    expected={case['id']+':'+record['key'] for case in parent['preregistration']['cases'][:2] for record in case['records']}
    assert set(captures)==expected and len({v['publication']['id'] for v in captures.values()})==6
    for case in parent['preregistration']['cases'][:2]:
        for original in case['records']:
            record=captures[case['id']+':'+original['key']];publication=record['publication']
            for key in ('text','information_type','source','occurred_at'):assert publication[key]==original[key]
            assert publication['author_id']=='bridge' and publication['project_id']=='project-red' and publication['data']=={}
            assert record['identity']=='urn:adhd:record:'+target['server_id']+':'+publication['id']
            if original['reply_to'] is None:
                assert record['context'] is None and record['links']==[]
            else:
                parent_record=captures[case['id']+':'+original['reply_to']]
                link={'relation':'reply','publication_id':parent_record['publication']['id']}
                assert record['context']=={'links':[link]}
                assert record['links']==[{**link,'target_identity':parent_record['identity']}]


async def inspect_training(f,parent,captures,guard,evidence):
    """Same exact public assertions in fresh-image and existing-native preflight."""
    project=parent['preregistration']['target']['project_id'];actor=WireAgent(await f.agent('bridge'))
    async def call(op,**fields):
        assert not guard.posts
        result=await actor.call(scoped(project,op,**fields));assert not guard.posts
        return result
    async def ready():
        v=(await call('retrieval_index'))['index']
        return v if v['status']=='ready' and v['active']['indexed']==6 and v['active']['excluded']==0 else None
    index=await until(ready,'Six-original baseline index not ready',150)
    assert index['active']['recipe']==parent['preregistration']['recipe'] and not index['selection']['applied']
    assert f.admin().call(scoped(project,'overview'))['counts']['publications']==6
    jobs=f.admin().call(scoped(project,'query_jobs',limit=64));assert not jobs['truncated']
    assert all(j['kind']=='retrieval' and j['query']['status']=='completed' for j in jobs['items'])
    assert f.admin().call(scoped(project,'index_proposals',limit=64))['items']==[]
    for key,record in captures.items():
        assert (await call('get_record',publication_id=record['publication']['id']))['record']==record
    for case in parent['preregistration']['cases'][:2]:
        ids={r['key']:captures[case['id']+':'+r['key']]['publication']['id'] for r in case['records']}
        q=(await call('retrieve',question=case['question'],scope=case['scope'],limit=case['limit']))['query']
        async def complete():
            v=(await call('get_retrieval',query_id=q['id']))['query'];return v if v['status']!='pending' else None
        q=await until(complete,'Model-free retrieval not complete',30);coverage=q['coverage']
        assert q['status']=='completed' and q['candidates']==[] and q['usage']['calls']==0 and q['evaluations']==[]
        assert all(coverage[k]==v for k,v in {'total':1,'indexed':1,'semantic_target':0,'semantic_remaining':0,'semantic_examined':0}.items())
        shallow=await call('get_record',publication_id=ids['2'],watermark=q['snapshot']['watermark'],max_depth=1,limit=32)
        full=await call('get_record',publication_id=ids['2'],watermark=q['snapshot']['watermark'],max_depth=2,limit=32)
        records=[full['record']]+full['related'];present={r['publication']['id'] for r in records}
        assert present==set(ids.values()) and not full['truncated']
        assert all(g['reason']=='cycle' and g['target_id'] in present for g in full['gaps'])
        assert ids['0'] not in {r['publication']['id'] for r in [shallow['record']]+shallow['related']}
        for key,pid in ids.items():assert next(r for r in records if r['publication']['id']==pid)==captures[case['id']+':'+key]
        evidence.record('same-original-zero-model-training-gap-and-complete-gold-closure',case=case['id'],query=q,depth1=shallow,depth2=full)
    evidence.value['index']=index
    evidence.value['route']=f.admin().call(scoped(project,'project_restore_status'))['route']
    evidence.value['schema_sha256']=sha(canonical(f.admin().client.get('/protocol/schema')[1]))


async def preflight(plan,parent,label,report,plan_sha):
    target=plan['targets'][label];root=Path(target['fixture_root'])
    # A failure is not permission to retry on the same/new namespace. Review the
    # retained report first. Markers live outside a fresh root to prevent reuse.
    marker=root.parent/(root.name+'.neutral-preflight.once')
    assert not report.exists()
    if label=='native':
        for name,digest in parent['continuation']['required_files_sha256'].items():
            assert sha((root/name).read_bytes())==digest, 'Historical native input changed before final-target revalidation'
        config=json.loads((root/'hub.json').read_bytes());config_profile(config,parent)
        guard=RefusingModel(config['matcher']['url'])
    else:
        assert not root.exists(), 'Image inputs may be created only once in the preregistered new root'
        guard=RefusingModel()
    f=None;error=None;e=Evidence(report,'neutral-optimizer-'+label+'-model-free-seal')
    e.value.update(plan_sha256=plan_sha,semantic_sha256=plan['semantics_sha256'],target=target,
        harness_sha256=sha(Path(__file__).read_bytes()),provider_posts=0,forbidden_model_attempts=[],frozen_originals={})
    try:
        once(marker,plan_sha);await broker_identity(target)
        f=SealedRuntime(fixture_args(target,report),target,adopt=label=='native')
        if label=='image':
            p=parent['preregistration']
            f.config.update(server_id=target['server_id'],matcher={'url':guard.url,'model':'forbidden-preflight-model'},
                retrieval={'recipe':p['recipe']},history=p['history'],archive=p['archive'],
                recovery={'backup_root':str(root/'offline-backups')})
            (root/'offline-backups').mkdir(mode=0o700)
        await f.start();admin=f.admin();current=admin.call({'op':'config_get'})
        e.value['actual_runtime_versions']=f.versions()
        valid=admin.call({'op':'config_validate','patch':{},'expected_revision':current['config_revision']});assert valid['valid']
        project=parent['preregistration']['target']['project_id']
        if label=='image':
            assert admin.call(scoped(project,'project_restore_status'))['availability']=='uninitialized'
            revision=current['config_revision']
            accepted=admin.call(scoped(project,'project_restore_plan',mode='initialize',expected_revision=revision,confirm=True,message_id='neutral-image-init-plan'))
            planned=await f.wait_recovery(project,accepted['operation_id'],{'ready'},300);p=planned['plan']
            applied=admin.call(scoped(project,'project_restore_apply',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],expected_revision=revision,confirm=True,message_id='neutral-image-init-apply'))
            complete=await f.wait_recovery(project,applied['operation_id'],{'complete'},300)
            assert complete['result']['initialized'] is True and admin.call({'op':'config_get'})['config_revision']==revision
            e.value['explicit_initialization']={'plan':planned,'apply':complete}
            captures={};actor=WireAgent(await f.agent('bridge'))
            for case in parent['preregistration']['cases'][:2]:
                ids={}
                for original in case['records']:
                    fields=copy.deepcopy(original);key=fields.pop('key');reply=fields.pop('reply_to')
                    if reply is not None:fields['context']={'links':[{'relation':'reply','publication_id':ids[reply]}]}
                    record=(await actor.call(scoped(project,'publish_record',**fields)))['record']
                    ids[key]=record['publication']['id'];captures[case['id']+':'+key]=record
                    e.value['frozen_originals']=copy.deepcopy(captures);e.write()
        else:
            assert admin.call(scoped(project,'project_restore_status'))['availability']=='ready'
            captures=copy.deepcopy(parent['continuation']['original_records'])
        original_bindings(parent,target,captures)
        await inspect_training(f,parent,captures,guard,e)
        e.value.update(frozen_originals=captures,originals_sha256={key:sha(canonical(v)) for key,v in captures.items()})
        e.value['config_profile']={key:current['config'].get(key) for key in ('retrieval','history','archive','optimization')}
        # Only the original config file must remain identical for native. New
        # verification jobs and derived runtime refresh are disclosed separately.
        if label=='native':assert sha(f.file.read_bytes())==parent['continuation']['required_files_sha256']['hub.json']
        assert not guard.posts
    except BaseException as caught:error=caught
    finally:
        try:await close_owned(f)
        except BaseException as caught:e.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
        finally:
            try:guard.close()
            except BaseException as caught:e.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
        e.value['forbidden_model_attempts']=guard.posts
        if guard.posts:error=error or AssertionError('Forbidden model request during structural preflight')
        if f:f.bind_evidence(e)
        if error is None:
            e.value['closed_private_files']=private_seal(root)
        e.finish(error)
    if error:raise error


def load_seals(plan):
    seals={}
    for label in ('native','image'):
        ref=plan['sealed_inputs'][label];raw=Path(ref['report_path']).read_bytes()
        assert sha(raw)==ref['report_sha256'];report=json.loads(raw)
        assert report['passed'] and report['target']==plan['targets'][label]
        assert report['semantic_sha256']==plan['semantics_sha256']
        assert report['provider_posts']==0 and not report['forbidden_model_attempts'] and len(report['checks'])==2
        assert len(report['frozen_originals'])==6 and report['closed_private_files']==ref['private_files']
        if label=='native':assert report['originals_sha256']==plan['native_originals_sha256'], 'Native originals were replaced'
        original_bindings(plan['semantic_plan'],plan['targets'][label],report['frozen_originals'])
        runtime=report['runtime'];assert runtime['owned_process']['exit_code'] is not None
        assert runtime['artifact_sha256']==plan['targets'][label]['artifact_sha256']
        if label=='image':
            assert runtime['kind']=='docker' and runtime['image_config_identity']==plan['targets'][label]['image_config_identity']
            assert runtime['canonical_manifest_sha256']==plan['targets'][label]['canonical_manifest_sha256']
            events=runtime['container_lifecycle']
            assert any(v['action']=='started' for v in events) and events[-1]['observed_absent'] is True
        else:assert runtime['kind']=='native'
        verify_seal(Path(report['target']['fixture_root']),report['closed_private_files'])
        for key,value in report['frozen_originals'].items():assert sha(canonical(value))==report['originals_sha256'][key]
        seals[label]=report
    assert {r['identity'] for r in seals['native']['frozen_originals'].values()}.isdisjoint(
        {r['identity'] for r in seals['image']['frozen_originals'].values()})
    return seals


def continuation(parent,seal,target):
    m=copy.deepcopy(parent)
    m['execution_target']=target;m.pop('execution_hold',None)
    m['continuation']={'fixture_root':target['fixture_root'],'original_records':seal['frozen_originals'],
        'original_records_sha256':seal['originals_sha256']}
    return m


async def one_leg(plan,parent,label,seal,report):
    target=plan['targets'][label];root=Path(target['fixture_root'])
    verify_seal(root,seal['closed_private_files'])
    once(root/'neutral-provider-phase.once',sha(canonical(plan)))
    e=Evidence(report,'neutral-optimizer-'+label+'-sealed-continuation')
    e.value.update(artifact_sha256=target['artifact_sha256'],plan_sha256=sha(canonical(plan)),
        harness_sha256=sha(Path(__file__).read_bytes()),qualification='none',dependency_sha256=plan['python_dependency_sha256'],
        input_seal_sha256=sha(canonical(seal['closed_private_files'])),semantic_sha256=plan['semantics_sha256'],
        limitations=['Prior30 QUALITY_REGRESSION and34 MIN_EVIDENCE remain failed.','Explicit lexical profile; same seven semantic cases in two runtime profiles, not14 independent semantic cases.'])
    f=None;budget=None;error=None
    try:
        await broker_identity(target)
        f=SealedRuntime(fixture_args(target,report),target,adopt=True)
        m=continuation(parent,seal,target)
        # Startup/compilation is not provider time. Both manifests are already
        # sealed, and no model work is pending; a closed relay remains necessary
        # until all public pre-inference checks complete.
        await f.start()
        e.value['actual_runtime_versions']=f.versions()
        budget=ProviderBudget(m,root/'neutral-provider-exchanges.jsonl')
        provider_started=time.monotonic()
        await asyncio.wait_for(checks(f,e,m,budget),timeout=max(.01,budget.deadline-time.monotonic()))
    except BaseException as caught:error=caught
    finally:
        try:
            if budget:budget.close()
        except BaseException as caught:e.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
        finally:
            try:await close_owned(f)
            except BaseException as caught:e.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
        if f:f.bind_evidence(e)
        if budget:
            e.value['provider_budget_observed']={'upstream_http_posts':budget.count,'violations':budget.violations,
                'inflight':budget.inflight,'exchange_log_sha256':sha(budget.log.read_bytes()),
                'absolute_provider_allowance_seconds':900,'elapsed_including_bounded_cleanup_seconds':time.monotonic()-provider_started}
            if budget.violations:error=error or AssertionError('Provider budget/scope violated')
            assert budget.count<=106
        e.finish(error)
    return e.value,error


async def run_pair(plan,parent,reports):
    seals=load_seals(plan) # BOTH checked before either runtime sees output.
    marker=Path(reports)/'pair.once';once(marker,sha(canonical(plan)))
    results={};errors=[];posts=0
    for label in plan['order']:
        # No branch on a quality result. Image inputs/code are rechecked after
        # native, so neither its winner nor its final failures can tune image.
        verify_pins(plan['python_dependency_sha256'])
        result,error=await one_leg(plan,parent,label,seals[label],Path(reports)/(label+'.json'))
        results[label]=result
        budget=result.get('provider_budget_observed',{})
        posts+=budget.get('upstream_http_posts',0)
        if error:errors.append(label)
        assert posts<=212
        # Cleanup/security/transport errors cannot authorize another live leg.
        if result.get('cleanup_failure_types') or budget.get('violations'):
            break
    output={'schema':'adhd/two-runtime-optimizer-result@1','passed':len(results)==2 and not errors,
        'per_runtime_passed':{key:value['passed'] for key,value in results.items()},'provider_posts':posts,
        'maximum_provider_posts':212,'maximum_provider_seconds':1800,'plan_sha256':sha(canonical(plan)),
        'runtime_reports':{key:{'path':str(Path(reports)/(key+'.json')),'sha256':sha((Path(reports)/(key+'.json')).read_bytes())} for key in results},
        'prior_failures_reclassified':False,'unrun_runtime':[v for v in plan['order'] if v not in results]}
    (Path(reports)/'pair.json').write_text(json.dumps(output,indent=2)+'\n')
    assert output['passed'],'One or both fixed runtime witnesses failed or remain unrun'


def reviewed(args,plan,raw):
    assert args.approved_manifest_sha256==sha(raw),'Exact plan review required before any runtime action'
    assert args.approved_harness_sha256==sha(Path(__file__).read_bytes()),'Exact driver review required'
    validate_plan(plan,parent_manifest(args.parent_manifest),bound=True)


async def main(args):
    parent=parent_manifest(args.parent_manifest)
    if args.phase=='template':
        assert args.output and not args.output.exists()
        args.output.write_text(json.dumps(template(parent),indent=2)+'\n');return
    assert args.manifest, 'A reviewed manifest path is required'
    raw=args.manifest.read_bytes();plan=json.loads(raw)
    bound=all(t.get('artifact_sha256') for t in plan['targets'].values())
    validate_plan(plan,parent,bound=args.phase!='check' or bound)
    if args.phase=='check':
        print(json.dumps({'valid_preparation':True,'bound':all(t['artifact_sha256'] for t in plan['targets'].values()),
            'runtime_started':False,'provider_posts':0,'manifest_sha256':sha(raw),'harness_sha256':sha(Path(__file__).read_bytes())}));return
    if args.phase=='amend':
        assert args.output and not args.output.exists() and args.native_preflight and args.image_preflight
        candidate=copy.deepcopy(plan);candidate['sealed_inputs']={}
        for label,path in [('native',args.native_preflight),('image',args.image_preflight)]:
            report=json.loads(path.read_bytes())
            candidate['sealed_inputs'][label]={'report_path':str(path.resolve()),'report_sha256':sha(path.read_bytes()),'private_files':report['closed_private_files']}
        load_seals(candidate)
        candidate['status']='SEALED_FOR_REVIEW_NOT_EXECUTED';candidate['execution_hold']='Explicit root review of both seals, code and accepted runtime targets still required.'
        candidate['pre_execution_parent_sha256']=sha(raw)
        args.output.write_text(json.dumps(candidate,indent=2)+'\n');return
    reviewed(args,plan,raw)
    if args.phase in ('preflight-native','preflight-image'):
        assert args.authorize_model_free and args.report and not args.authorize_provider
        await preflight(plan,parent,args.phase.split('-')[1],args.report,sha(raw));return
    assert args.phase=='run' and args.authorize_provider and not args.authorize_model_free
    assert plan['status']=='SEALED_EXECUTION_APPROVED' and not plan.get('execution_hold')
    assert args.reports and not args.reports.exists()
    load_seals(plan);args.reports.mkdir(mode=0o700)
    await run_pair(plan,parent,args.reports)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['template','check','preflight-native','preflight-image','amend','run'],default='check')
    p.add_argument('--manifest',type=Path);p.add_argument('--parent-manifest',type=Path,default=Path(__file__).with_name('fixtures')/'optimizer-neutral-provider-prepared.json')
    p.add_argument('--output',type=Path);p.add_argument('--native-preflight',type=Path);p.add_argument('--image-preflight',type=Path)
    p.add_argument('--report',type=Path);p.add_argument('--reports',type=Path)
    p.add_argument('--approved-manifest-sha256');p.add_argument('--approved-harness-sha256')
    p.add_argument('--authorize-model-free',action='store_true');p.add_argument('--authorize-provider',action='store_true')
    asyncio.run(main(p.parse_args()))
