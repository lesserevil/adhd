#!/usr/bin/env python3
"""Prepared native continuation of one preregistered neutral optimizer cohort.

--check-plan only reads pinned files. Actual execution additionally requires the
reviewed manifest SHA; preparation never authorizes inference. Training originals
MUST be the exact six accepted by the successful model-free preflight.
"""
import asyncio
import copy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time

import httpx

from multi_support import Evidence,arguments,scoped
from optimization_positive_witness import canonical,digest
from project_recovery_queries import NativeFixture
from protocol_acceptance import ByteValidator


class ProviderBudget:
    """One counted provider attempt, no retries, strict question/stage allowlist."""
    def __init__(self,manifest,log):
        self.provider=manifest['provider'];self.budget=manifest['provider_budget'];self.log=log
        self.deadline=time.monotonic()+self.budget['maximum_wall_clock_seconds']
        self.questions={c['question'] for c in manifest['preregistration']['cases'][:2]}
        self.lock=threading.Condition();self.closed=True;self.count=0;self.inflight=0;self.violations=[]
        self.log.write_text('');self.log.chmod(0o600);outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=65536:self.reply(503,b'{}');outer.violate('request-size');return
                raw=self.rfile.read(n)
                try:payload=json.loads(raw)
                except ValueError:self.reply(503,b'{}');outer.violate('request-json');return
                with outer.lock:
                    remaining=outer.deadline-time.monotonic()
                    state=payload.get('state') if isinstance(payload,dict) else None
                    questions=payload.get('questions') if isinstance(payload,dict) else None
                    valid=(isinstance(state,dict) and isinstance(questions,dict) and payload.get('model')==outer.provider['model']
                           and state.get('question') in outer.questions and set(questions) in ({'intent'},{'assessment','answer'})
                           and (set(questions)=={'intent'} or n<=8192))
                    if outer.closed or remaining<=0 or outer.count>=outer.budget['maximum_upstream_http_posts'] or not valid:
                        outer.violations.append('closed-budget-or-out-of-scope');self.reply(503,b'{}');return
                    outer.count+=1;number=outer.count;outer.inflight+=1
                row={'sequence':number,'request_sha256':digest(raw),'request_json':raw.decode()};started=time.monotonic()
                try:
                    with httpx.Client(trust_env=False,follow_redirects=False,timeout=max(.001,min(10,remaining))) as http:
                        response=http.post(outer.provider['url'],content=raw,headers={'Content-Type':'application/json'})
                    body=response.content;assert len(body)<=262144
                    status=response.status_code;row.update(http_status=status,response_sha256=digest(body),response_text=body.decode())
                except Exception as error:
                    body,status=b'{}',502;row['transport_error_type']=type(error).__name__
                finally:
                    row['elapsed_seconds']=time.monotonic()-started
                    with outer.lock:
                        with outer.log.open('a') as output:output.write(json.dumps(row)+'\n')
                        outer.inflight-=1;outer.lock.notify_all()
                self.reply(status,body)
            def reply(self,status,body):
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def violate(self,reason):
        with self.lock:self.violations.append(reason)
    def check(self):
        assert not self.violations and time.monotonic()<self.deadline,'Frozen provider scope/budget exhausted'
    def close(self):
        try:
            with self.lock:
                self.closed=True;assert self.lock.wait_for(lambda:self.inflight==0,timeout=12),'Provider exchange failed to settle'
        finally:self.server.shutdown();self.server.server_close();self.thread.join(2)


class WireAgent:
    """Keep actual JSON tokens after the official SDK validates the same result."""
    def __init__(self,agent):
        self.agent=agent;self.values=[];agent.http.event_hooks.setdefault('response',[]).append(self.receive)
    async def receive(self,response):
        await response.aread()
        try:
            parts=json.loads(response.content)['result']['message']['parts']
            if len(parts)==1 and 'data' in parts[0]:self.values.append(parts[0]['data'])
        except (ValueError,KeyError,TypeError):pass
    async def call(self,command,message_id=None):
        before=len(self.values);await self.agent.call(command,message_id)
        assert len(self.values)==before+1,'SDK and raw HTTP result mismatch'
        return self.values.pop()


def verify(args):
    raw=args.manifest.read_bytes();m=json.loads(raw);p=m['preregistration'];c=m['continuation']
    assert m['status']=='FROZEN_FOR_HARNESS_REVIEW_NOT_EXECUTED'
    assert m['provider_budget']=={'maximum_upstream_http_posts':106,'maximum_wall_clock_seconds':900,'relay_retries':0}
    assert p['limits']['proposed_later_total_posts']==106 and p['recipe']['semantic'] is False
    assert m['original_attempt']=={'mode':'search_then_scan','complete':False,'limit':8}
    assert len(p['cases'])==7 and [v['cohort'] for v in p['cases']]==['training']*2+['held_out']*3+['regression']*2
    assert p['cases'][6]['question']=='What was reported about whether parcel Spruce was delivered to the loading bay?'
    assert p['cases'][6]['gold']['support_keys']==['0','1','2'] and p['cases'][6]['gold']['expectation']=='conflicting'
    old=json.loads(args.parent_manifest.read_bytes());assert digest(args.parent_manifest.read_bytes())==m['preregistration_parent_sha256']
    unchanged=copy.deepcopy(p);unchanged['cases'][6]['question']=old['cases'][6]['question'];unchanged['limits']['proposed_later_total_posts']=256;assert unchanged==old
    assert digest(args.hub.read_bytes())==p['target']['artifact_sha256']
    assert digest(args.preflight_report.read_bytes())==c['preflight_report_sha256']
    pre=json.loads(args.preflight_report.read_bytes());assert pre['passed'] and len(pre['checks'])==2 and pre['provider_posts']==0 and pre['forbidden_model_attempts']==[]
    assert pre['harness_sha256']==c['preflight_harness_sha256'] and pre['manifest_sha256']==c['preflight_manifest_sha256']
    assert pre['frozen_originals']==c['original_records'] and len(c['original_records'])==6
    assert args.keep_work.resolve()==Path(c['fixture_root'])
    for path,sha in c['required_files_sha256'].items():assert digest((args.keep_work/path).read_bytes())==sha,'Preflight installation bytes changed'
    for key,value in c['original_records'].items():assert digest(canonical(value))==c['original_records_sha256'][key]
    for name,sha in m['python_dependency_sha256'].items():assert digest(Path(__file__).with_name(name).read_bytes())==sha,'Reviewed helper bytes changed'
    return m,digest(raw)


async def checks(f,e,m,budget):
    p=m['preregistration'];project=p['target']['project_id'];name=p['target']['agent_id']
    agent=WireAgent(await f.agent(name));admin=f.admin();captures=copy.deepcopy(m['continuation']['original_records'])
    e.value['frozen_originals']=copy.deepcopy(captures);e.write()
    schema=admin.client.get('/protocol/schema')[1];validator=ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/OptimizationProposal'})
    def management(op,mutation=False,**fields):return admin.call(scoped(project,op,**fields),mutation=mutation)
    async def call(op,**fields):budget.check();return await agent.call(scoped(project,op,**fields))
    async def wait(fn):
        while True:
            budget.check();value=fn()
            if asyncio.iscoroutine(value):value=await value
            if value:return value
            await asyncio.sleep(.1)
    async def ready(expected):
        async def observe():
            index=(await call('retrieval_index'))['index']
            return index if index['status']=='ready' and index['active']['indexed']==expected and index['active']['excluded']==0 else None
        return await wait(observe)
    async def resolved(case):return {r['key']:captures[case['id']+':'+r['key']]['publication']['id'] for r in case['records']}
    async def structural(case,ids):
        before=budget.count;q=(await call('retrieve',question=case['question'],scope=case['scope'],limit=case['limit']))['query']
        async def done():
            v=(await call('get_retrieval',query_id=q['id']))['query'];return v if v['status']!='pending' else None
        q=await wait(done);cov=q['coverage'];assert q['status']=='completed' and not q['candidates'] and q['usage']['calls']==0
        assert all(cov[k]==v for k,v in {'total':1,'indexed':1,'semantic_target':0,'semantic_remaining':0,'semantic_examined':0}.items())
        shallow=await call('get_record',publication_id=ids['2'],watermark=q['snapshot']['watermark'],max_depth=1,limit=32)
        full=await call('get_record',publication_id=ids['2'],watermark=q['snapshot']['watermark'],max_depth=2,limit=32)
        records=[full['record']]+full['related'];actual={r['publication']['id'] for r in records}
        assert actual==set(ids.values()) and not full['truncated']
        assert all(g['reason']=='cycle' and g['target_id'] in actual for g in full['gaps'])
        assert ids['0'] not in {v['publication']['id'] for v in [shallow['record']]+shallow['related']}
        for record in records:assert record==captures[case['id']+':'+next(k for k,v in ids.items() if v==record['publication']['id'])]
        assert budget.count==before,'Structural check invoked a model'
        e.value.setdefault('structural_checks',[]).append({'case':case['id'],'query':q,'depth1':shallow,'depth2':full});e.write()
    def answer_pass(query,case,ids):
        answer=query['answer'];expected=case['gold']['expectation'];gold={ids[k] for k in case['gold']['support_keys']}
        if expected=='no_evidence':return answer['assessment'] in ('insufficient','no_evidence') and query['coverage']['full_scope_evaluated']
        return answer['assessment']==('direct' if expected=='supported' else 'conflicting') and gold<=set(answer['support_ids']+answer['contradiction_ids'])
    async def attempt(case,ids):
        await structural(case,ids)
        q=(await call('query_archive',question=case['question'],scope=case['scope'],**m['original_attempt']))['query']
        e.value.setdefault('owned_archive_query_ids',[]).append(q['id']);e.write()
        async def done():
            v=(await call('get_archive_query',query_id=q['id']))['query'];return v if v['status']!='pending' else None
        q=await wait(done)
        e.value.setdefault('actual_archive_queries',[]).append(q);e.write()
        assert q['status']=='completed' and q['error'] is None and answer_pass(q,case,ids),'Original asserted answer/coverage failed'
        assert q['search'] and q['search']['status']=='completed' and q['search']['error'] is None and q['search']['candidates']==[]
        assert q['assessment'] is None and 'no_candidates' in q['fallback_reasons'] and q['scan']['coverage']['final_complete']
        async def captured():
            rows=(await call('list_retrieval_attempts',limit=64))['items'];return next((v for v in rows if v['archive_query_id']==q['id']),None)
        row=await wait(captured);label=copy.deepcopy(case['gold']);label['support_ids']=[ids[k] for k in label.pop('support_keys')]
        label.update(cohort=case['cohort'],note='Independent gold fixed before any model observation; no inferred support.')
        management('save_retrieval_label',True,attempt_id=row['id'],expected_label_revision=0,label=label)
        detail=management('feedback_attempt',attempt_id=row['id'])['attempt']
        assert detail['status']=='completed' and detail['owner_id']==name and detail['labels'][-1]['confirmed']
        if case['cohort']=='training':assert detail['adjudicated_diagnosis'] in ('confirmed_retrieval_gap','confirmed_context_assembly_gap')
        e.value.setdefault('confirmed_attempts',[]).append({'case':case['id'],'detail':detail,'gold':label});e.write()
        return row['id'],detail
    async def settled(pid):
        def observe():
            v=management('index_proposal',proposal_id=pid,limit=64);e.value['latest_proposal']=v['proposal'];e.write()
            return v['proposal'] if v['proposal']['status']!='pending' else None
        value=await wait(observe);validator.validate(value);return value
    # Before arming, verify exactly the existing corpus and terminal old work.
    assert management('overview')['counts']['publications']==6
    jobs=management('query_jobs',limit=64);assert not jobs['truncated']
    assert all(j['kind']=='retrieval' and j['query']['status']=='completed' for j in jobs['items'])
    assert management('index_proposals',limit=64)['items']==[]
    for key,record in captures.items():assert (await call('get_record',publication_id=record['publication']['id']))['record']==record
    base=await ready(6);assert base['selection']['effective_recipe']==p['recipe'] and not base['selection']['applied']
    for case in p['cases'][:2]:await structural(case,await resolved(case))
    patch={'matcher':{'url':budget.url,'model':m['provider']['model']},'history':p['history'],'archive':p['archive'],'optimization':m['optimization']}
    current=admin.call({'op':'config_get'});valid=admin.call({'op':'config_validate','patch':patch,'expected_revision':current['config_revision']});assert valid['valid']
    with budget.lock:assert budget.count==0 and not budget.violations;budget.closed=False
    admin.call({'op':'config_update','patch':patch},mutation=True)
    e.value['resolved_policies_before_inference']=admin.call({'op':'config_get'})['config'];e.write()
    training=[];details=[]
    for case in p['cases'][:2]:
        aid,detail=await attempt(case,await resolved(case));training.append(aid);details.append(detail)
    assert len({v['group_id'] for v in details})==2
    groups=management('feedback_cohorts',limit=64);clusters=management('feedback_clusters',limit=64)
    assert groups['next_offset'] is None and clusters['next_offset'] is None
    for detail in details:
        group=next(v for v in groups['items'] if v['id']==detail['group_id']);assert group['cohort']=='training' and group['owners']==[name] and not group['exposed']
    e.value.update(training_cohorts=groups,training_clusters=clusters);e.record('two-actual-completed-confirmed-independent-training-gaps-and-all-gold-answers-before-one-proposal')
    proposal=management('propose_index',True,training_attempt_ids=training)['proposal'];pid=proposal['id'];e.value['proposal_id']=pid;e.write()
    proposal=await settled(pid);assert proposal['status']=='awaiting_evaluation' and proposal['held_out_attempt_ids']==proposal['regression_attempt_ids']==[]
    assert len(proposal['variants'])==6
    e.value['training_freeze']=copy.deepcopy(proposal);e.record('one-winner-frozen-before-any-final-original-publication')
    final=[]
    for case in p['cases'][2:]:
        with budget.lock:budget.questions.add(case['question'])
        ids={}
        for original in case['records']:
            fields=copy.deepcopy(original);key=fields.pop('key');reply=fields.pop('reply_to')
            if reply is not None:fields['context']={'links':[{'relation':'reply','publication_id':ids[reply]}]}
            record=(await call('publish_record',**fields))['record'];ids[key]=record['publication']['id'];captures[case['id']+':'+key]=record
        e.value['frozen_originals']=copy.deepcopy(captures);e.write();await ready(len(captures))
        aid,_=await attempt(case,ids);final.append(aid)
    management('evaluate_index',True,proposal_id=pid,held_out_attempt_ids=final[:3],regression_attempt_ids=final[3:]);proposal=await settled(pid)
    assert proposal['status']=='qualified','Fixed cohort failed qualification; no retries or replacement proposal'
    ev=proposal['evaluation'];assert ev['passed'] and ev['mean_recall_gain_ppm']>0 and ev['total_calls_delta']<=0 and ev['total_bytes_delta']<=0
    assert ev['answer_failures']==ev['answer_regressions']==ev['false_supports']==0
    rows=[v for v in proposal['cases'] if v['cohort']!='training'];assert len(rows)==5
    assert all(v['baseline']['answer_pass'] and v['candidate']['answer_pass'] and v['comparison']['retrieval_gain_ppm']>=0 for v in rows)
    assert proposal['winner_identity']==e.value['training_freeze']['winner_identity'] and proposal['build']['status']=='ready' and proposal['index_manifest']['excluded']==0
    e.value['qualified_proposal']=copy.deepcopy(proposal)
    e.record('all-fixed-strata-pass-unchanged-gold-confidence-recall-call-byte-and-native-gates')
    # No more provider work is permitted, including during ordinary lifecycle.
    with budget.lock:budget.closed=True;provider_calls=budget.count
    previous=await ready(21);management('promote_index',True,proposal_id=pid,expected_selection_revision=previous['selection']['revision'])
    selected=await ready(21);assert selected['selection']['applied'] and selected['selection']['qualification_current']
    assert selected['active']['recipe']==selected['selection']['effective_recipe'] and selected['previous']['recipe']==p['recipe']
    assert selected['active']['source_watermark']==selected['publication_watermark']
    subscription=(await call('subscribe',mode='raw',selectors={'information_type':[p['cases'][-1]['scope']['information_type']]}))['subscription']
    assert (await call('poll'))['deliveries']==[],'Late raw subscription implicitly replayed history'
    async def drained():
        value=management('eventing_status');return value if value['pending_events']==0 else None
    status=await wait(drained);mark=status['replay_watermark']
    command=scoped(project,'replay_events',from_sequence=mark,to_sequence=mark,expected_watermark=mark,subscriptions=[{'id':subscription['id'],'revision':subscription['revision']}],reason='Frozen optimizer witness existing-record raw replay',confirm=True,message_id='neutral-existing-record-replay')
    replay=admin.client.api(command);assert admin.client.api(command)==replay
    last=captures[p['cases'][-1]['id']+':2']['publication']['id']
    async def delivered():return next((v for v in (await call('poll'))['deliveries'] if v.get('publication_id')==last),None)
    delivery=await wait(delivered);assert any(v['subscription_id']==subscription['id'] for v in delivery['matches'])
    await call('ack',delivery_ids=[delivery['id']])
    async def replay_done():
        value=management('eventing_replay',replay_id=replay['replay']['id']);return value if value['replay']['status']=='materialized' else None
    materialized=await wait(replay_done);e.value['raw_replay']={'command':command,'accepted':replay,'materialized':materialized,'delivery':delivery}
    old=selected['active']['id'];management('rebuild_index',True)
    async def rebuild_ready():
        value=await ready(21);return value if value['active']['id']!=old else None
    rebuilt=await wait(rebuild_ready)
    # Native rebuilding existing records must preserve the protected rollback.
    assert rebuilt['active']['id']!=old and rebuilt['previous']['recipe']==p['recipe']
    assert management('overview')['counts']['publications']==21 and budget.count==provider_calls
    e.record('promotion-native-catchup-and-existing-record-raw-replay-ack-use-zero-additional-provider-posts')
    admin.call({'op':'config_update','patch':{'optimization':{'enabled':False}}},mutation=True)
    rollback=management('rollback_index',True,expected_selection_revision=rebuilt['selection']['revision'])['proposal'];rollback=await settled(rollback['id']);assert rollback['status']=='promoted'
    restored=await ready(21);assert restored['selection']['effective_recipe']==p['recipe']
    management('reset_index_selection',True,expected_selection_revision=restored['selection']['revision']);reset=await ready(21);assert not reset['selection']['applied']
    f.hard_stop();await f.start();agent=WireAgent(await f.agent(name));f.admin_client=None;admin=f.admin()
    restarted=await ready(21);assert restarted['selection']==reset['selection']
    assert not any(v['id']==delivery['id'] for v in (await call('poll'))['deliveries'])
    for record in captures.values():assert (await call('get_record',publication_id=record['publication']['id']))['record']==record
    assert budget.count==provider_calls and not budget.violations
    e.value['qualification']='positive-scoped-lexical-native-witness';e.record('disabled-rollback-reset-and-hard-restart-preserve-same-originals-and-ack-without-provider-work')


async def main(args):
    manifest,sha=verify(args)
    if args.check_plan:
        print(json.dumps({'manifest_sha256':sha,'harness_sha256':digest(Path(__file__).read_bytes()),
                          'valid':True,'runtime_started':False,'provider_posts':0,'training_originals_republished':0}))
        return
    assert args.approved_manifest_sha256==sha,'Separate explicit reviewed manifest digest required before inference'
    assert args.approved_harness_sha256==digest(Path(__file__).read_bytes()),'Separately reviewed exact harness digest required'
    assert not args.with_model and not args.image and not args.rest_url and not args.report.exists()
    marker=args.keep_work/'neutral-provider-phase.once'
    with marker.open('x') as output:output.write(sha+'\n')
    marker.chmod(0o600)
    f=NativeFixture(args,initialize_projects=False)
    # Adopt this installation's current private credentials and bound endpoint;
    # never synthesize another server, namespace or training publication.
    f.config=json.loads(f.file.read_text());f.tokens=f.config['agents'];f.base='http://127.0.0.1:'+str(f.config['port'])
    assert f.config['server_id']==manifest['preregistration']['target']['server_id']
    evidence=Evidence(args.report,'independent-neutral-optimizer-native-continuation')
    evidence.value.update(manifest_sha256=sha,harness_sha256=digest(Path(__file__).read_bytes()),
        artifact_sha256=digest(args.hub.read_bytes()),qualification='none',manifest=manifest,
        limitations=['Original30capsule-R QUALITY_REGRESSION and34MIN_EVIDENCE remain failed.',
                     'Explicit semantic:false native recipe, not default semantic calibration or Docker qualification.',
                     'One fixed cohort and one proposal only; no retries, replacement IDs or labels.'],
        dependency_sha256=manifest['python_dependency_sha256'])
    budget=None;error=None
    try:
        budget=ProviderBudget(manifest,f.root/'neutral-provider-exchanges.jsonl')
        await f.start();f.bind_evidence(evidence)
        await asyncio.wait_for(checks(f,evidence,manifest,budget),timeout=max(.01,budget.deadline-time.monotonic()))
    except BaseException as caught:
        error=caught
        if budget:
            with budget.lock:budget.closed=True
        # Refuse further provider work before cancellation. Accepted evidence and
        # failed outcomes remain retained; cancellation does not authorize retry.
        try:
            admin=f.admin();project=manifest['preregistration']['target']['project_id']
            for qid in evidence.value.get('owned_archive_query_ids',[]):
                try:admin.call(scoped(project,'cancel_query_job',query_id=qid),mutation=True)
                except Exception as cleanup_error:evidence.value.setdefault('cancellation_failure_types',[]).append(type(cleanup_error).__name__)
            pid=evidence.value.get('proposal_id')
            if pid:
                try:admin.call(scoped(project,'cancel_index_proposal',proposal_id=pid),mutation=True)
                except Exception as cleanup_error:evidence.value.setdefault('cancellation_failure_types',[]).append(type(cleanup_error).__name__)
            admin.call({'op':'config_update','patch':{'optimization':{'enabled':False}}},mutation=True)
        except Exception as cleanup_error:evidence.value.setdefault('cancellation_failure_types',[]).append(type(cleanup_error).__name__)
    finally:
        try:
            if budget:budget.close()
        except BaseException as cleanup_error:
            evidence.value.setdefault('cleanup_failure_types',[]).append(type(cleanup_error).__name__);error=error or cleanup_error
        finally:
            try:await f.close()
            except BaseException as cleanup_error:
                evidence.value.setdefault('cleanup_failure_types',[]).append(type(cleanup_error).__name__);error=error or cleanup_error
            finally:
                f.bind_evidence(evidence)
                if budget:
                    evidence.value['provider_budget_observed']={'upstream_http_posts':budget.count,'violations':budget.violations,
                        'inflight':budget.inflight,'exchange_log_sha256':digest(budget.log.read_bytes())}
                    if budget.violations:error=error or AssertionError('Provider scope/budget violation')
                evidence.finish(error)
    if error:raise error


if __name__=='__main__':
    parser=arguments(__doc__);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--parent-manifest',type=Path,required=True)
    parser.add_argument('--preflight-report',type=Path,required=True)
    parser.add_argument('--check-plan',action='store_true');parser.add_argument('--approved-manifest-sha256');parser.add_argument('--approved-harness-sha256')
    asyncio.run(main(parser.parse_args()))
