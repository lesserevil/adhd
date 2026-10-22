#!/usr/bin/env python3
"""Independent archive ownership, fallback, exact sampling, costs and interruption checks."""
import argparse,copy,hashlib,json,secrets,tempfile,time
from pathlib import Path
import jsonschema
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator
from archive_support import ArchiveFixture

def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--command');mode.add_argument('--image');parser.add_argument('--report',default='verification/archive-lifecycle.json')
    args=parser.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/archive-tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'archive-fixture','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{a:secrets.token_urlsafe(32) for a in ('alice','bob')},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def rpc(cmd,actor='alice',mid=None):return Client(h).rpc(cmd,h.config['agents'][actor],mid=mid)
    def wait(fn,seconds=25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if value:=fn():return value
            time.sleep(.025)
        raise AssertionError('Archive deadline; inspect '+str(root))
    def error(cmd,reason,actor='alice',mid=None):
        envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':mid or secrets.token_urlsafe(18),'role':'ROLE_USER','parts':[{'data':cmd}]}}}
        status,value,_=Client(h).request('/a2a',envelope,{'Authorization':'Bearer '+h.config['agents'][actor]})
        assert status==200 and 'error' in value,value
        if reason=='INVALID_PARAMS':assert value['error']['code']==-32602,value
        else:assert value['error']['data'][0]['reason']==reason,value
    def patch(value):return Client(h,h.config['admin_token']).api({'op':'config_update','patch':value},mutation=True)
    def publish(tag,text='The sample Unicode result was λ.',**extra):return rpc({'op':'publish_record','information_type':tag,'text':text,**extra})['record']
    def ready():return wait(lambda:v if (v:=rpc({'op':'retrieval_index'})['index'])['status']=='ready' else None)
    def get(q,**kw):return rpc({'op':'get_archive_query','query_id':q['id'],**kw})['query']
    def submit(tag,**kw):return rpc({'op':'query_archive','question':'Which sample reports the Unicode result?','scope':{'information_type':tag},**kw})['query']
    def finish(q,status='completed'):
        value=wait(lambda:v if (v:=get(q))['status']!='pending' else None)
        valid('ArchiveQuery',value);assert value['status']==status,(value['status'],value['error']);return value
    try:
        h.start();admin=Client(h,h.config['admin_token']);schema=admin.get('/protocol/schema')[1];jsonschema.Draft202012Validator.check_schema(schema)
        def valid(name,value,expected=True):
            errors=list(ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker()).iter_errors(value))
            assert bool(errors)!=expected,(name,[(str(e.path),e.message) for e in errors])
        pid=h.pid;ready();q=finish(submit('empty'));assert q['usage']['total']['calls']==0 and q['coverage']['full_scope_evaluated'] and q['outcome']=='no_evidence'
        record('empty-frozen-scope-completes-with-zero-model-calls')
        original=publish('basic');ready();cmd={'op':'query_archive','question':'Which sample reports the Unicode result?','scope':{'information_type':'basic'}}
        initial=rpc(cmd,mid='stable-archive')['query'];assert rpc(cmd,mid='stable-archive')['query']==initial
        error({**cmd,'question':'Changed question'},'IDEMPOTENCY_CONFLICT',mid='stable-archive')
        for op in ('get_archive_query','cancel_archive_query','continue_archive_query'):error({'op':op,'query_id':initial['id']},'NOT_FOUND','bob')
        q=finish(initial);assert q['path']==['plan','search','assess'] and q['outcome']=='direct' and q['coverage']['answer_scope']=='candidate_only'
        assert q['assessment']['record_ids']==[original['publication']['id']] and q['sample']['eligible'] and not q['sample']['selected']
        stable=get(q);assert stable['usage']==q['usage']
        record('owned-idempotent-asynchronous-search-assesses-full-originals-and-preserves-costs')
        for mutation in ('probability','selected','concealed','usage','provenance','bytes','plan','child-owner','question'):
            bad=copy.deepcopy(q)
            if mutation=='probability':bad['sample']['probability_numerator']='1'
            elif mutation=='selected':bad['sample']['selected']=True
            elif mutation=='concealed':bad['sample']['draw_hex']=None
            elif mutation=='usage':bad['usage']['total']['calls']+=1
            elif mutation=='provenance':bad['evaluations'][-1]['record_ids']=[]
            elif mutation=='bytes':bad['evaluations'][-1]['bytes']+=1
            elif mutation=='plan':bad['sample']['plan_id']='another-plan'
            elif mutation=='child-owner':bad['search']['owner_id']='bob'
            else:bad['question']='A different question'
            valid('ArchiveQuery',bad,False)
        record('independent-semantic-wire-negatives-reject-forged-sampling-costs-bytes-and-child-bindings')
        full=finish(submit('basic',complete=True));assert full['coverage']['full_scope_evaluated'] and full['children']['scan'] and full['usage']['planner']['calls']==0
        guard=rpc({'op':'query_archive','question':'List all sample results.','scope':{'information_type':'basic'}})['query'];guard=finish(guard)
        assert guard['intent']['source']=='guard' and guard['intent']['matched_terms']==['all'] and guard['coverage']['full_scope_evaluated']
        only=finish(submit('basic',mode='search',complete=True),'partial');assert only['error']['code']=='REQUIRES_SCAN' and only['children']['scan'] is None
        record('explicit-completeness-and-language-guards-force-real-full-scope-children')
        model.intent='unknown';unknown=finish(submit('basic'));assert unknown['intent']['decision']=='unknown' and unknown['children']['scan'];model.intent='bounded'
        model.mode='invalid-intent';fallback=finish(submit('basic'));assert 'planner_error' in fallback['fallback_reasons'] and fallback['coverage']['full_scope_evaluated'];model.mode='normal'
        record('ambiguous-and-malformed-intent-escalate-without-fabricated-bounded-decisions')
        model.assessment='insufficient';insufficient=finish(submit('basic'));assert 'evidence_insufficient' in insufficient['fallback_reasons'] and insufficient['children']['scan']
        only=finish(submit('basic',mode='search'),'partial');assert only['error']['code']=='REQUIRES_SCAN' and only['outcome']=='insufficient';model.assessment='direct'
        record('insufficient-original-support-falls-back-or-reports-required-scan')
        patch({'retrieval':{'enabled':False}});disabled=finish(submit('basic'));assert disabled['coverage']['full_scope_evaluated'] and disabled['search'] is None
        patch({'retrieval':{'enabled':True}});ready();patch({'history':{'enabled':False}})
        disabled=finish(submit('basic',mode='scan'),'partial');assert disabled['error']['code']=='SCAN_DISABLED';patch({'history':{'enabled':True}})
        record('disabled-dependencies-remain-explicit-and-supported-fallback-still-works')
        # Two independent originals: candidate limit 1 has bounded evidence while
        # the full audit chooses the second original. This is a controlled miss,
        # not a claim about individual support labels from model input lists.
        publish('audit','Sample Unicode initial report.');publish('audit','Sample Unicode later independent report.');ready();model.select_last=True
        patch({'archive':{'audit_rate_ppm':1000000}});audited=finish(submit('audit',limit=1));model.select_last=False
        assert audited['sample']['selected'] and audited['sample']['probability_numerator']==audited['sample']['probability_denominator']
        assert audited['children']['audit'] and audited['coverage']['audit_final_complete'] and audited['comparison']['answer_changed']
        assert 'audit_changed_answer' in audited['answer']['uncertainty'];record('forced-audit-discovers-controlled-hidden-original-and-records-exact-probability')
        partial_audit=finish(submit('audit',limit=1,budget={'audit':{'records':1}}),'partial')
        assert partial_audit['sample']['selected'] and not partial_audit['comparison']['completed_scope'] and partial_audit['comparison']['answer_changed'] is None
        plan=partial_audit['plan_id'];draw=partial_audit['sample']['draw_hex']
        continued=rpc({'op':'continue_archive_query','query_id':partial_audit['id'],'budget':{'audit':{'records':8}}})['query'];continued=finish(continued)
        assert continued['sample']['selected'] and continued['plan_id']==plan and continued['sample']['draw_hex']==draw and continued['comparison']['completed_scope']
        record('incomplete-audit-never-labels-equivalence-and-continuation-keeps-the-selected-trial')
        patch({'archive':{'audit_rate_ppm':0}})
        # Submission freezes primary records before the worker can collect them.
        frozen=submit('basic',mode='scan');publish('basic','A later result must not join the existing question.')
        frozen=finish(frozen);assert frozen['coverage']['total']==1 and frozen['scan']['coverage']['total']==1
        record('concurrent-publication-does-not-change-parent-or-child-frozen-corpus')
        publish('budget','First budget result.');publish('budget','Second budget result.');ready()
        limited=finish(submit('budget',mode='scan',budget={'scan':{'records':1}}),'partial');assert limited['error']['code']=='BUDGET_RECORDS'
        plan=limited['plan_id'];cost=limited['usage']['total']['cumulative_calls'];draw=limited['sample']['draw_hex']
        resumed=rpc({'op':'continue_archive_query','query_id':limited['id'],'budget':{'scan':{'records':8}}})['query'];resumed=finish(resumed)
        assert resumed['plan_id']==plan and resumed['sample']['draw_hex']==draw and resumed['run']==2 and resumed['usage']['total']['cumulative_calls']>=cost
        prior=get(resumed,run=1);assert prior['status']=='partial' and prior['children']['scan']['run']==1
        record('budget-continuation-keeps-plan-draw-and-fences-child-runs-with-prior-evidence')
        restarted=rpc({'op':'continue_archive_query','query_id':resumed['id'],'restart':True})['query'];restarted=finish(restarted)
        assert restarted['plan_id']!=plan and restarted['snapshot']==resumed['snapshot'];record('explicit-restart-draws-new-plan-on-the-same-frozen-corpus')
        model.mode='slow';model.delay=1.5;patch({'archive':{'timeout_ms':3000}})
        cancelling=submit('basic');wait(lambda: get(cancelling)['usage']['planner']['calls']==1)
        cancelled=rpc({'op':'cancel_archive_query','query_id':cancelling['id']})['query'];assert cancelled['status']=='cancelled' and cancelled['usage']['planner']['uncertain_calls']==1
        time.sleep(1.6);assert get(cancelling)['status']=='cancelled';model.mode='normal';record('cancel-fences-inflight-planner-and-settles-uncertain-reservation')
        model.mode='slow';model.delay=1.5;changing=submit('basic');wait(lambda:get(changing)['usage']['planner']['calls']==1)
        patch({'archive':{'operator_version':'changed-policy'}});invalid=finish(changing,'invalidated');assert invalid['error']['code']=='CONFIG_CHANGED';model.mode='normal'
        record('hot-semantic-policy-change-invalidates-inflight-work-without-hub-restart')
        assert h.pid==pid
        model.mode='slow';model.delay=1.5
        changed=submit('basic',mode='scan');child=wait(lambda:v['children']['scan'] if (v:=get(changed))['children']['scan'] else None)
        rpc({'op':'cancel_history_query','query_id':child['query_id']});changed=finish(changed,'partial');assert changed['error']['code']=='CHILD_CHANGED';model.mode='normal'
        record('independently-cancelled-child-is-rejected-instead-of-adopted')
        model.mode='slow';model.delay=1.5;interrupted=submit('basic',budget={'planner':{'time_ms':6500,'calls':2}});wait(lambda:get(interrupted)['usage']['planner']['calls']==1)
        h.stop(hard=True);model.mode='normal';h.start();restored=finish(interrupted)
        assert restored['usage']['planner']['uncertain_calls']==1 and restored['usage']['planner']['calls']==2 and restored['usage']['planner']['time_ms']>=3000
        assert get(audited)['sample']==audited['sample'];record('hard-kill-preserves-audit-decision-and-settles-abandoned-request-once')
        job=admin.api({'op':'query_job','query_id':audited['id']});valid('ArchiveQuery',job['query']);assert job['kind']=='archive'
        listing=admin.api({'op':'query_jobs','kind':'archive'});assert all(row['kind']=='archive' for row in listing['items'])
        record('explicit-admin-job-inspection-keeps-agent-ownership-and-exact-evidence')
        report={'schema':'adhd/archive-lifecycle@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'cases':cases,'workdir':str(root.relative_to(Path.cwd()))}
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
