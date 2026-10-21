#!/usr/bin/env python3
"""Independent human-role fences, frozen label eligibility and private-data exclusion."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--report',default='verification/feedback-privacy.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-privacy').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'feedback-privacy','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{a:secrets.token_urlsafe(32) for a in ['alice','bob']},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(c,actor='alice'):return Client(h).rpc(c,h.config['agents'][actor])
    def admin(c,mutation=False):return Client(h,h.config['admin_token']).api(c,mutation=mutation)
    def wait(fn):
        end=time.monotonic()+30
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.025)
        raise AssertionError('Privacy deadline '+str(root))
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    try:
        h.start();pub=rpc({'op':'publish_record','information_type':'frozen','text':'Public sample result λ.'})['record']['publication']['id'];wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        original=rpc({'op':'query_archive','question':'Which public sample result was recorded?','scope':{'information_type':'frozen'}})['query'];wait(lambda:rpc({'op':'get_archive_query','query_id':original['id']})['query']['status']=='completed');a=wait(lambda:rpc({'op':'list_retrieval_attempts'})['items'])[0]
        future=rpc({'op':'publish_record','information_type':'future','text':'FUTURE_LABEL_SENTINEL'})['record']['publication']['id'];private=rpc({'op':'send','recipient_id':'bob','text':'PRIVATE_FEEDBACK_SENTINEL'})['delivery']['id']
        base={'expectation':'supported','support_ids':[pub],'cohort':'training','tags':[],'note':'Independent source assertion','confirmed':True}
        for source in [future,private]:
            Client(h,h.config['admin_token']).api({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':{**base,'support_ids':[source]}},expected=400,mutation=True)
        assert rpc({'op':'get_retrieval_attempt','attempt_id':a['id']})['attempt']['label_revision']==0;record('future-and-private-original-ids-cannot-enter-a-frozen-confirmed-label')
        password='independent-'+secrets.token_urlsafe(24);human=admin({'op':'save_user','user':{'username':'feedback-admin','name':'Feedback Administrator','email':'feedback-admin@example.invalid','password':password,'role':'Admin'}},True)['user'];admin({'op':'config_update','patch':{'auth':{'mode':'local','allow_admin_token':True}}},True);session=Client(h);assert session.login('feedback-admin',password)['id']==human['id']
        saved=session.api({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':base},mutation=True)['label'];assert saved['actor_kind']=='human_session' and saved['actor_id']==human['id']
        r=session.api({'op':'replay_attempt','attempt_id':a['id'],'candidate_recipe':{}},mutation=True)['query'];assert r['owner_id']=='alice' and r['requester_kind']=='human_session' and r['requester_id']==human['id'];r=wait(lambda:v if (v:=rpc({'op':'get_retrieval_replay','query_id':r['id']})['query'])['status']!='pending' else None)
        assert r['status']=='completed' and r['comparison']['eligible'];record('human-session-label-and-admin-replay-record-real-requester-without-agent-impersonation')
        serialized=json.dumps(r)+json.dumps(rpc({'op':'get_retrieval_attempt','attempt_id':a['id']}))
        assert all(v not in serialized for v in ['PRIVATE_FEEDBACK_SENTINEL','FUTURE_LABEL_SENTINEL',password,h.config['admin_token']])
        with model.lock:model_inputs=json.dumps([v['request'] for v in model.requests])
        assert all(v not in model_inputs for v in ['PRIVATE_FEEDBACK_SENTINEL','FUTURE_LABEL_SENTINEL',password,h.config['admin_token'],'Independent source assertion'])
        assert rpc({'op':'poll'})['deliveries']==[];queued=rpc({'op':'poll'},'bob')['deliveries'];assert len(queued)==1 and queued[0]['id']==private and queued[0]['text']=='PRIVATE_FEEDBACK_SENTINEL';rpc({'op':'ack','delivery_ids':[private]},'bob');record('replay-and-feedback-exclude-private-future-credentials-and-label-notes-from-model-inputs')
        admin({'op':'save_user','user':{'id':human['id'],'name':human['name'],'email':human['email'],'role':'Viewer'}},True)
        for op in ['feedback_status','feedback_attempts','feedback_cohorts','feedback_clusters']:session.api({'op':op},expected=403)
        session.api({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':1,'label':base},expected=403,mutation=True);session.api({'op':'retire_replay','query_id':r['id']},expected=403,mutation=True)
        assert rpc({'op':'get_retrieval_attempt','attempt_id':a['id']})['attempt']['label_revision']==1 and rpc({'op':'get_retrieval_replay','query_id':r['id']})['query']['evidence_available'];record('hot-admin-demotion-immediately-revokes-feedback-read-label-and-retirement-access')
        result={'schema':'adhd/feedback-privacy@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
