#!/usr/bin/env python3
"""Controlled-model optimizer ownership, cancellation, dedupe, limits and recovery."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--command');m.add_argument('--image');p.add_argument('--report',default='verification/optimization-faults.json');a=p.parse_args()
    parent=Path('_build/roadmap/optimization-faults').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',json.loads(a.command) if a.command else [],a.image);model=ArchiveFixture();model.noul=.01;cases=[]
    cfg={'project_id':'optimizer-faults','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'},'archive':{'audit_rate_ppm':0},'optimization':{'enabled':True}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def admin(v,mutation=False):return Client(h,h.config['admin_token']).api(v,mutation=mutation)
    def rpc(v):return Client(h).rpc(v,h.config['agents']['alice'])
    def wait(fn,seconds=45):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Optimizer fault deadline '+str(root))
    def get(id):return admin({'op':'index_proposal','proposal_id':id,'limit':64})['proposal']
    def record(name,**v):cases.append({'case':name,'passed':True,**v});print('PASS',name,flush=True)
    def propose(ids):return admin({'op':'propose_index','training_attempt_ids':ids},True)['proposal']
    try:
        h.start();training=[];publications=[]
        for i in range(2):
            tag='fault'+str(i);pub=rpc({'op':'publish_record','text':'Controlled original evidence '+str(i),'information_type':tag})['record']['publication']['id'];publications.append(pub)
            wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
            q=rpc({'op':'query_archive','question':'Was specimen '+['Alpha','Beta'][i]+' present?','scope':{'information_type':tag}})['query'];qid=q['id'];q=wait(lambda:v if (v:=rpc({'op':'get_archive_query','query_id':qid})['query'])['status']!='pending' else None);assert q['status']=='completed'
            item=wait(lambda:[v for v in rpc({'op':'list_retrieval_attempts'})['items'] if v['archive_query_id']==q['id']])[0]
            admin({'op':'save_retrieval_label','attempt_id':item['id'],'expected_label_revision':0,'label':{'expectation':'supported','support_ids':[pub],'cohort':'training','tags':[],'note':'Controlled-model lifecycle assertion, not live-model quality.','confirmed':True}},True);training.append(item['id'])
        original_count=admin({'op':'overview'})['counts']['publications'];model.mode='slow';model.delay=.4
        q=propose(training);id=q['id'];q=wait(lambda:q if (q:=get(id))['children'] else None)
        first_child=q['children'][0]['replay_id']
        wait(lambda:any(admin({'op':'query_job','query_id':first_child})['query']['children'].values()))
        admin({'op':'config_update','patch':{'optimization':{'enabled':False}}},True)
        time.sleep(1.0);before_pause=len(model.requests);time.sleep(.6);assert len(model.requests)==before_pause
        assert get(id)['status']=='pending'
        admin({'op':'config_update','patch':{'optimization':{'enabled':True}}},True)
        q=admin({'op':'cancel_index_proposal','proposal_id':id},True)['proposal'];assert q['status']=='cancelled'
        stopped=get(id);assert stopped['usage']['cumulative_calls']>=0
        for ref in stopped['children']:
            child=admin({'op':'query_job','query_id':ref['replay_id']})['query'];assert child['status']!='pending'
        again=propose(training);assert again['id']==id and again['status']=='cancelled'
        record('owned-child-cancellation-keeps-costs-and-unchanged-signatures-do-not-retry',usage=stopped['usage'])
        # A new independently confirmed label revision changes the experiment
        # signature. The previous proposal is retained, never silently restarted.
        item=admin({'op':'feedback_attempt','attempt_id':training[0]})['attempt'];label=item['labels'][-1];newlabel={k:label[k] for k in ['expectation','support_ids','cohort','tags','note','confirmed']};newlabel['note']='Explicit revised controlled assertion'
        admin({'op':'save_retrieval_label','attempt_id':training[0],'expected_label_revision':item['label_revision'],'label':newlabel},True)
        q=propose(training);second=q['id'];assert second!=id
        # Current interpretation change invalidates parent and cancels children.
        admin({'op':'config_update','patch':{'retrieval':{'operator_version':'controlled-new-interpretation'}}},True)
        changed=wait(lambda:q if (q:=get(second))['status']!='pending' else None);assert changed['status']=='invalidated' and changed['error']['code']=='POLICY_CHANGED'
        record('current-interpretation-fences-pending-proposals-without-adopting-new-policy')
        admin({'op':'config_update','patch':{'feedback':{'max_replays':1,'max_active_replays':1}}},True)
        q=propose(training);limited=q['id'];limited_q=wait(lambda:q if (q:=get(limited))['status']!='pending' else None)
        assert limited_q['status']=='partial' and limited_q['error']['code']=='RESOURCE_LIMIT',(limited_q['status'],limited_q['error'])
        record('shared-feedback-cap-checkpoints-with-explicit-resource-cause')
        model.mode='normal';admin({'op':'config_update','patch':{'feedback':{'max_replays':256,'max_active_replays':16}}},True)
        admin({'op':'continue_index_proposal','proposal_id':limited},True)
        wait(lambda:len(get(limited)['children'])>0)
        h.stop(hard=True);h.start();restored=get(limited);assert restored['id']==limited and restored['run']==2
        assert restored['usage']['cumulative_calls']>=limited_q['usage']['cumulative_calls']
        admin({'op':'cancel_index_proposal','proposal_id':limited},True)
        before=admin({'op':'feedback_status'})['status'];admin({'op':'retire_index_proposal','proposal_id':limited},True);retired=get(limited);after=admin({'op':'feedback_status'})['status'];assert retired['status']=='retired' and not retired['evidence_available'];assert before['attempts']==after['attempts']
        assert admin({'op':'overview'})['counts']['publications']==original_count
        for pub in publications:assert rpc({'op':'get_record','publication_id':pub})['record']['publication']['id']==pub
        record('crash-continuation-and-derived-retirement-preserve-originals-labels-and-cumulative-costs')
        def revise(note):
            item=admin({'op':'feedback_attempt','attempt_id':training[0]})['attempt'];value={k:item['labels'][-1][k] for k in ['expectation','support_ids','cohort','tags','note','confirmed']};value['note']=note
            admin({'op':'save_retrieval_label','attempt_id':training[0],'expected_label_revision':item['label_revision'],'label':value},True)
        model.mode='slow';model.delay=.4
        revise('Explicit child-fence experiment');child_parent=propose(training)['id'];child=wait(lambda:q['children'][0] if (q:=get(child_parent))['children'] else None)
        rpc({'op':'cancel_retrieval_replay','query_id':child['replay_id']});invalidated=get(child_parent);assert invalidated['status']=='invalidated' and invalidated['error']['code']=='CHILD_CHANGED'
        record('independent-agent-child-cancellation-cannot-qualify-a-parent')
        revise('Explicit label-fence experiment');label_parent=propose(training)['id'];wait(lambda:get(label_parent)['children']);revise('Changed independent assertion while work was pending')
        invalidated=get(label_parent);assert invalidated['status']=='invalidated' and invalidated['error']['code']=='LABEL_CHANGED'
        record('changed-confirmed-label-invalidates-the-captured-experiment')
        owner_parent=propose(training)['id'];token=h.config['agents']['alice'];admin({'op':'config_update','patch':{'agents':{'alice':None}}},True)
        invalidated=get(owner_parent);assert invalidated['status']=='invalidated' and invalidated['error']['code']=='OWNER_REMOVED'
        admin({'op':'config_update','patch':{'agents':{'alice':token}}},True)
        record('removed-current-agent-owner-cancels-owned-work-with-an-explicit-cause')
        revise('Explicit model-failure and paid-retry experiment');model.mode='error';failed=propose(training)['id']
        checkpoint=wait(lambda:q if (q:=get(failed))['status']!='pending' else None)
        assert checkpoint['status']=='partial' and checkpoint['error']['code']=='MODEL_ERROR',(checkpoint['status'],checkpoint['error'])
        paid=checkpoint['usage']['cumulative_calls'];assert paid>0
        admin({'op':'continue_index_proposal','proposal_id':failed},True)
        unchanged=wait(lambda:q if (q:=get(failed))['status']!='pending' else None);assert unchanged['status']=='partial' and unchanged['usage']['cumulative_calls']==paid
        model.mode='normal';admin({'op':'continue_index_proposal','proposal_id':failed,'retry_failed':True},True)
        restarted=wait(lambda:q if (q:=get(failed))['children'] and q['children'][0]['run']>checkpoint['children'][0]['run'] else None)
        assert restarted['usage']['cumulative_calls']>=paid
        pair=admin({'op':'query_job','query_id':restarted['children'][0]['replay_id']})['query'];assert pair['prior_runs'] and pair['usage']['total']['cumulative_calls']>=paid
        admin({'op':'cancel_index_proposal','proposal_id':failed},True)
        record('model-failures-never-become-success-by-continuation-and-explicit-retry-retains-paid-runs')
        password='optimizer-'+secrets.token_urlsafe(24)
        human=admin({'op':'save_user','user':{'username':'optimizer-admin','name':'Optimizer Administrator','email':'optimizer@example.invalid','password':password,'role':'Admin'}},True)['user'];admin({'op':'config_update','patch':{'auth':{'mode':'local','allow_admin_token':True}}},True)
        session=Client(h);session.login('optimizer-admin',password);session.api({'op':'optimization_status'})
        admin({'op':'save_user','user':{'id':human['id'],'name':human['name'],'email':human['email'],'role':'Viewer'}},True)
        for command in [{'op':'optimization_status'},{'op':'index_proposals'},{'op':'index_proposal','proposal_id':id}]:session.api(command,expected=403)
        session.api({'op':'propose_index','training_attempt_ids':training},expected=403,mutation=True)
        assert admin({'op':'overview'})['counts']['publications']==original_count
        index=rpc({'op':'retrieval_index'})['index'];assert 'training_attempt_ids' not in json.dumps(index) and password not in json.dumps(index)
        record('hot-admin-demotion-revokes-proposal-reads-and-mutations-without-agent-metadata-leakage')
        report={'schema':'adhd-optimization-faults-report@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(h.command[-1]).read_bytes()).hexdigest() if h.command else None,'image':a.image};Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
