#!/usr/bin/env python3
"""Independent Admin subscription editing against actual Kafka/A2A state."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4
import httpx
from federation_acceptance import Hub, Model, request
from eventing_target import RuntimeTarget, add_target_arguments
from federation_multi import wait
from protocol_acceptance import ByteValidator


def main():
    p=argparse.ArgumentParser(description=__doc__)
    add_target_arguments(p);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--eventing-rest-url',default='http://127.0.0.1:18082')
    args=p.parse_args();args.work=args.work.resolve();args.work.mkdir(parents=True,exist_ok=True)
    target=RuntimeTarget(args)
    model=Model();model.mode='error'
    hub=target.hub(args.work/'hub','p',model.url)
    hub.config.update(server_id=uuid4().hex,projects=[{'id':'p','name':'P'}],agent_projects={'alice':['p'],'bob':['p']},eventing={'enabled':True,'rest_url':args.eventing_rest_url,'retry_ms':100})
    report={'schema':'adhd/admin-subscription-edit@1','passed':False,'checks':[],
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    report.update(target.report())
    def record(name):report['checks'].append({'name':name,'passed':True});print('PASS',name,flush=True)
    schema=None
    def validate(name,value):ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name}).validate(value)
    def admin(op,error=None,**fields):
        command={'op':op,**({} if op in {'config_get','config_update','save_user'} else {'project_id':'p'}),**fields};validate('admin_'+op,command)
        status,result=request(hub.base,'/admin/api',command,hub.config['admin_token'])
        if error:assert status=={'CONFIG_CONFLICT':409,'NOT_FOUND':404,'PROJECT_ARCHIVED':403}[error] and result['error']['code']==error,(status,result)
        else:assert status==200,(status,result);validate('admin_result_'+op,result)
        return result
    def mutation(op,**fields):return admin(op,message_id=uuid4().hex,confirm=True,**fields)
    def patch(change):
        revision=admin('config_get')['config_revision']
        mutation('config_update',expected_revision=revision,patch=change)
        hub.config=json.loads((hub.root/'config.json').read_text())
    def call(op,agent='alice',**fields):return hub.call({'op':op,'project_id':'p',**fields},agent=agent)
    def rows(agent):return call('poll',agent=agent)['deliveries']
    try:
        hub.start();schema=request(hub.base,'/protocol/schema')[1]
        call('subscribe',mode='raw')
        sub=call('subscribe',agent='bob',mode='filtered',filter='Accepted frozen policy')['subscription']
        original=call('publish',text='Pending filtered original')['publication']
        raw=wait(lambda:rows('alice'),'Raw stream stalled behind failing filtered decision',45)
        call('ack',delivery_ids=[d['id'] for d in raw])
        jobs=wait(lambda:admin('jobs',status='pending')['items'],'No pending filtered work')
        pending={job['job_id'] for job in jobs}
        edit={'subscription_id':sub['id'],'expected_revision':sub['revision'],'mode':'filtered',
              'filter':'Replacement future filter','selectors':{},'paused':True,
              'message_id':uuid4().hex,'confirm':True}
        result=admin('update_subscription',**edit);sub=result['subscription']
        assert sub['paused'] and sub['revision']==2
        assert admin('update_subscription',**edit)==result
        admin('update_subscription',error='CONFIG_CONFLICT',**{**edit,'message_id':uuid4().hex})
        assert pending<={job['job_id'] for job in admin('jobs',status='pending')['items']}
        record('revisioned-admin-edit-is-idempotent-and-preserves-pending-filter-work')
        sub=mutation('update_subscription',subscription_id=sub['id'],expected_revision=2,
                     mode='raw',selectors={'information_type':['status']})['subscription']
        call('publish',text='Excluded by future deterministic selector')
        accepted=call('publish',text='Included future raw status',information_type='status')['publication']
        got=wait(lambda:rows('bob'),'Admin raw conversion did not deliver selected future event',45)
        assert [d['publication_id'] for d in got]==[accepted['id']],got
        call('ack',agent='bob',delivery_ids=[d['id'] for d in got])
        sub=mutation('update_subscription',subscription_id=sub['id'],expected_revision=sub['revision'],mode='raw',selectors={},paused=True)['subscription']
        paused=call('publish',text='No new subscription snapshot while paused')['publication']
        wait(lambda:admin('eventing_status')['pending_events']==0,'Paused event did not materialize')
        assert not rows('bob')
        sub=mutation('update_subscription',subscription_id=sub['id'],expected_revision=sub['revision'],mode='raw',selectors={})['subscription']
        resumed=call('publish',text='Raw after Admin resume')['publication']
        got=wait(lambda:rows('bob'),'Resumed raw subscription did not progress',45)
        assert [d['publication_id'] for d in got]==[resumed['id']],got
        assert original['id'] not in [d['publication_id'] for d in got] and paused['id'] not in [d['publication_id'] for d in got]
        record('mode-selectors-pause-and-resume-affect-future-events-without-resurrecting-acks')
        patch({'auth':{'mode':'local','allow_admin_token':True}})
        for role in ('Developer','Viewer'):
            username=role.lower();password='independent-local-password-'+username
            revision=admin('config_get')['config_revision']
            mutation('save_user',expected_revision=revision,user={'username':username,'name':role,
                'email':username+'@example.invalid','role':role,'project_ids':['p'],'password':password})
            hub.config=json.loads((hub.root/'config.json').read_text())
            with httpx.Client(trust_env=False) as client:
                assert client.post(hub.base+'/admin/login',json={'username':username,'password':password},headers={'Origin':hub.base}).status_code==200
                session=client.get(hub.base+'/admin/session').json()
                response=client.post(hub.base+'/admin/api',json={'op':'update_subscription',**edit},
                    headers={'Origin':hub.base,'X-CSRF-Token':session['csrf']})
                assert response.status_code==403,response.text
        patch({'agent_projects':{'bob':[]}})
        admin('update_subscription',error='NOT_FOUND',subscription_id=sub['id'],expected_revision=sub['revision'],mode='raw',selectors={},message_id=uuid4().hex,confirm=True)
        patch({'agent_projects':{'bob':['p']}})
        created=[admin('create_subscription',agent_id='alice',mode='raw',message_id=uuid4().hex)['subscription']['id'] for _ in range(105)]
        pages=[admin('subscriptions',agent_id='alice',offset=offset,limit=100) for offset in (0,100)]
        ids=[row['id'] for page in pages for row in page['items']]
        assert len(ids)==106 and len(set(ids))==106 and set(created)<=set(ids)
        assert pages[0]['truncated'] is True and pages[1]['truncated'] is False
        assert admin('subscriptions',agent_id='alice',offset=9007199254740991,limit=100)=={'items':[],'truncated':False}
        record('admin-subscription-pagination-enumerates-more-than-one-hundred-without-gaps-or-repeats')
        projects=json.loads(json.dumps(hub.config['projects']));projects[0]['status']='archived';patch({'projects':projects})
        admin('update_subscription',error='PROJECT_ARCHIVED',subscription_id=sub['id'],expected_revision=sub['revision'],mode='raw',selectors={},message_id=uuid4().hex,confirm=True)
        assert pending<={job['job_id'] for job in admin('jobs',status='pending')['items']}
        record('only-admin-edits-currently-admitted-owner-and-archive-fences-new-edits')
        report['passed']=True;report['artifact_sha256']=target.artifact
    finally:
        hub.stop();model.close();args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
