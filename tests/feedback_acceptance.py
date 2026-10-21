#!/usr/bin/env python3
"""Independent ownership, adjudication, cohort leakage, paired replay and recovery checks."""
import argparse,copy,hashlib,json,secrets,tempfile,time
from pathlib import Path
import jsonschema
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator
from archive_support import ArchiveFixture


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');parser.add_argument('--report',default='verification/feedback-lifecycle.json');args=parser.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-tests').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'feedback-fixture','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{a:secrets.token_urlsafe(32) for a in ['alice','bob']},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def rpc(cmd,actor='alice',mid=None):return Client(h).rpc(cmd,h.config['agents'][actor],mid=mid)
    def admin(cmd,mutation=False):return Client(h,h.config['admin_token']).api(cmd,mutation=mutation)
    def patch(v):return admin({'op':'config_update','patch':v},True)
    def wait(fn,seconds=30):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.025)
        raise AssertionError('Feedback deadline; inspect '+str(root))
    def error(cmd,reason,actor='alice',mid=None):
        envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':mid or secrets.token_urlsafe(18),'role':'ROLE_USER','parts':[{'data':cmd}]}}}
        status,value,_=Client(h).request('/a2a',envelope,{'Authorization':'Bearer '+h.config['agents'][actor]});assert status==200 and 'error' in value,value
        if reason=='INVALID_PARAMS':assert value['error']['code']==-32602,value
        else:assert value['error']['data'][0]['reason']==reason,value
    def admin_error(cmd,reason):
        cmd={**cmd,'message_id':secrets.token_urlsafe(18),'confirm':True,'expected_revision':admin({'op':'config_get'})['config_revision']}
        status,v,_=Client(h,h.config['admin_token']).request('/admin/api',cmd);assert status>=400 and v['error']['code']==reason,(status,v)
    def valid(name,v,expected=True):
        errors=list(ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker()).iter_errors(v));assert bool(errors)!=expected,(name,[(str(e.path),e.message) for e in errors])
    def archive(question,tag='basic',actor='alice',**kw):
        q=rpc({'op':'query_archive','question':question,'scope':{'information_type':tag},**kw},actor)['query'];return wait(lambda:v if (v:=rpc({'op':'get_archive_query','query_id':q['id']},actor)['query'])['status']!='pending' else None)
    def attempt(q,actor='alice'):
        rows=wait(lambda:[v for v in rpc({'op':'list_retrieval_attempts'},actor)['items'] if v['archive_query_id']==q['id'] and v['run']==q['run']]);a=rpc({'op':'get_retrieval_attempt','attempt_id':rows[0]['id']},actor)['attempt'];valid('FeedbackAttempt',a);return a
    def label(a,cohort='training',expectation='supported',ids=None):return admin({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':a['label_revision'],'label':{'expectation':expectation,'support_ids':ids if ids is not None else [pub],'cohort':cohort,'tags':[],'note':'Independent fixture assertion','confirmed':True}},True)
    def replay(a,**kw):return rpc({'op':'replay_retrieval','attempt_id':a['id'],'candidate_recipe':{'context_depth':2},**kw})['query']
    def get(q,**kw):return rpc({'op':'get_retrieval_replay','query_id':q['id'],**kw})['query']
    def finish(q,status='completed'):
        v=wait(lambda:v if (v:=get(q))['status']!='pending' else None);valid('ReplayQuery',v);assert v['status']==status,(v['status'],v['error']);return v
    try:
        h.start();schema=admin({'op':'feedback_status'}) # Check routes before schema inspection.
        schema=Client(h).get('/protocol/schema')[1];jsonschema.Draft202012Validator.check_schema(schema)
        pub=rpc({'op':'publish_record','information_type':'basic','text':'Sample Unicode result λ.'})['record']['publication']['id'];wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        q=archive('Which sample result was reported?');a=attempt(q)
        assert a['diagnosis']=='successful_search_unchecked' and a['label_revision']==0 and a['recipe'] is not None
        assert rpc({'op':'list_retrieval_attempts'},'bob')['items']==[]
        error({'op':'get_retrieval_attempt','attempt_id':a['id']},'NOT_FOUND','bob');error({'op':'replay_retrieval','attempt_id':a['id'],'candidate_recipe':{}},'NOT_FOUND','bob')
        record('terminal-capture-is-owned-immutable-and-distinct-from-confirmed-labels')
        saved=label(a);valid('FeedbackLabel',saved['label']);assert saved['label']['actor_kind']=='legacy_token' and saved['label']['actor_id']=='legacy-admin'
        a=attempt(q);assert a['adjudicated_diagnosis']=='confirmed_supported_search' and a['label_revision']==1
        admin_error({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':{k:saved['label'][k] for k in ['expectation','support_ids','cohort','tags','note','confirmed']}},'COHORT_CONFLICT')
        record('admin-only-independent-labels-carry-actor-and-monotonic-revision-fence')
        cmd={'op':'replay_retrieval','attempt_id':a['id'],'candidate_recipe':{'context_depth':2}}
        r=rpc(cmd,mid='stable-replay')['query'];assert rpc(cmd,mid='stable-replay')['query']==r
        for op in ['get_retrieval_replay','cancel_retrieval_replay','continue_retrieval_replay']:error({'op':op,'query_id':r['id']},'NOT_FOUND','bob')
        r=finish(r);assert r['comparison']['eligible'] and r['baseline']['metrics']['answer_pass'] and r['candidate']['metrics']['answer_pass']
        assert all(v['stage'] in ['retrieval','assessment'] for v in r['evaluations']);assert get(r)['usage']==r['usage'];record('owned-idempotent-paired-replay-records-real-model-work-without-publishing')
        for mutation in ['usage','recipe','question','gold','cost','returned','originals']:
            bad=copy.deepcopy(r)
            if mutation=='usage':bad['usage']['total']['calls']+=1
            elif mutation=='recipe':bad['candidate']['recipe_identity']='0'*64
            elif mutation=='question':bad['question']='Different question'
            elif mutation=='gold':bad['label_revision']+=1
            elif mutation=='cost':bad['comparison']['calls_delta']+=1
            elif mutation=='returned':bad['candidate']['coverage']['returned_ids']=[]
            else:bad['evaluations'][-1]['record_ids']=[]
            valid('ReplayQuery',bad,False)
        record('independent-wire-negatives-reject-forged-branch-policy-question-cost-gold-and-originals')
        limited=finish(replay(a,budget={'calls':1}),'partial');assert limited['error']['code']=='BUDGET_CALLS';before=limited['usage']['total']['cumulative_calls']
        continued=rpc({'op':'continue_retrieval_replay','query_id':limited['id'],'budget':{'calls':16}})['query'];continued=finish(continued)
        assert continued['run']==2 and continued['usage']['total']['cumulative_calls']>before and continued['baseline']['comparison_usage']['calls']==2 and continued['candidate']['comparison_usage']['calls']==2
        assert get(continued,run=1)['status']=='partial';record('budget-checkpoint-continuation-keeps-paid-baseline-cost-and-prior-run-evidence')
        current=finish(replay(a,corpus='current'));assert not current['comparison']['eligible'] and current['comparison']['reason']=='changed_corpus'
        record('current-corpus-is-explicit-and-cannot-reuse-old-label-for-quality-credit')
        pending=replay(a,budget={'calls':1});pending=finish(pending,'partial');old_label=pending['label'];a=attempt(q);label(a)
        restarted=rpc({'op':'continue_retrieval_replay','query_id':pending['id'],'restart':True})['query'];restarted=finish(restarted);assert restarted['label_revision']==2 and get(restarted,run=1)['label']==old_label
        record('explicit-restart-adopts-current-label-on-the-same-frozen-corpus')
        scan=archive('Which sample result was reported?',mode='scan');scan_a=attempt(scan);assert scan_a['recipe'] is None
        error({'op':'replay_retrieval','attempt_id':scan_a['id'],'candidate_recipe':{}},'BASELINE_UNAVAILABLE');finish(replay(scan_a,baseline='current'))
        record('scan-only-attempt-requires-explicit-current-baseline-without-guessed-history')
        # A different owner asking the same normalized question belongs to the same
        # independent cohort. Membership stays Admin-only.
        duplicate=attempt(archive('  WHICH sample result was reported?  ',actor='bob'),'bob')
        admin_error({'op':'save_retrieval_label','attempt_id':duplicate['id'],'expected_label_revision':0,'label':{'expectation':'supported','support_ids':[pub],'cohort':'held_out','tags':[],'note':'Conflicting split','confirmed':True}},'COHORT_CONFLICT')
        assert 'owners' not in duplicate and 'attempt_ids' not in duplicate;clusters=admin({'op':'feedback_clusters'})['items'];assert clusters and all(v['groups']<=v['plans']<=v['observations'] for v in clusters);valid('admin_result_feedback_clusters',{'items':clusters,'next_offset':None});record('same-question-cross-owner-and-shared-support-cannot-cross-cohort-splits')
        hp=rpc({'op':'publish_record','information_type':'held','text':'Independent held fixture result μ.'})['record']['publication']['id'];wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        held=attempt(archive('Which independent held fixture result was reported?','held'));label(held,'held_out',ids=[hp]);hr=replay(held);hr=finish(hr)
        error({'op':'replay_retrieval','attempt_id':held['id'],'candidate_recipe':{'context_depth':3}},'HELD_OUT_EXPOSED')
        assert attempt({'id':held['archive_query_id'],'run':held['run']})['exposed'];record('held-out-exposure-is-durable-before-execution-and-another-candidate-is-rejected')
        # Original sources, labels and exposure survive retiring derived replay rows.
        retired=admin({'op':'retire_replay','query_id':hr['id']},True)['query'];valid('ReplayQuery',retired)
        assert not retired['evidence_available'] and retired['evaluations']==[] and retired['evaluation_count']==hr['evaluation_count'] and retired['comparison']['reason']=='retired'
        for key in ['retrieval_gain_ppm','answer_regressions','false_supports','fallback_delta','calls_delta','bytes_delta','time_ms_delta','native_bytes_delta']:assert retired['comparison'][key]==hr['comparison'][key]
        for b in ['baseline','candidate']:
            for key in ['expected_gold','retrieved_gold','retrieval_recall_ppm','answer_pass','false_support']:assert retired[b]['metrics'][key]==hr[b]['metrics'][key]
        assert rpc({'op':'get_record','publication_id':hp})['record']['publication']['id']==hp
        error({'op':'replay_retrieval','attempt_id':held['id'],'candidate_recipe':{}},'HELD_OUT_EXPOSED')
        record('retirement-removes-only-derived-evidence-keeps-originals-labels-and-exposure')
        durable=get(r);h.stop(hard=True);h.start();assert get(r)==durable and not get(hr)['evidence_available'];assert attempt(q)['label_revision']==2
        record('attempts-labels-replays-retirement-and-spent-cohorts-survive-hard-restart')
        assert rpc({'op':'poll'},'bob')['deliveries']==[]
        jobs=admin({'op':'query_jobs','kind':'replay'});assert jobs['items'] and all(v['kind']=='replay' for v in jobs['items']);valid('admin_result_query_jobs',jobs)
        record('admin-activity-includes-replays-and-replay-never-pollutes-deliveries')
        patch({'feedback':{'enabled':False}});empty=archive('Which empty result exists?','not-present');time.sleep(.3)
        assert not any(v['archive_query_id']==empty['id'] for v in rpc({'op':'list_retrieval_attempts'})['items']);patch({'feedback':{'enabled':True}});attempt(empty)
        record('hot-capture-disable-and-enable-records-visible-backlog-without-restart')
        result={'schema':'adhd/feedback-lifecycle@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
