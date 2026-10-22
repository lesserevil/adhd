#!/usr/bin/env python3
"""Actual Kafka per-project policy isolation and safe hot transition checks."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import httpx
from federation_acceptance import Hub, Model, request
from eventing_target import RuntimeTarget, add_target_arguments
from federation_multi import wait
from eventing_controls import ControlledGateway


def main():
    p=argparse.ArgumentParser(description=__doc__)
    add_target_arguments(p);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--eventing-rest-url',default='http://127.0.0.1:18082')
    a=p.parse_args();a.work=a.work.resolve();a.work.mkdir(parents=True,exist_ok=True)
    target=RuntimeTarget(a)
    model=Model();gate=ControlledGateway(a.eventing_rest_url)
    h=target.hub(a.work/'hub','p',model.url)
    h.config.update(server_id=uuid4().hex,matcher=None,projects=[{'id':x,'name':x} for x in ('p','q')],
                    agent_projects={x:['p','q'] for x in ('alice','bob')},
                    eventing={'enabled':True,'rest_url':gate.url,'retry_ms':100})
    report={'schema':'adhd/project-event-policy@1','passed':False,'checks':[],
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    report.update(target.report())
    def record(name):report['checks'].append({'name':name,'passed':True});print('PASS',name,flush=True)
    def admin(op,project=None,**fields):
        code,value=request(h.base,'/admin/api',{'op':op,**({'project_id':project} if project else {}),**fields},h.config['admin_token'])
        assert code==200,(code,value)
        return value
    def patch(change,fail=False):
        revision=admin('config_get')['config_revision']
        code,value=request(h.base,'/admin/api',{'op':'config_update','expected_revision':revision,
            'message_id':uuid4().hex,'confirm':True,'patch':change},h.config['admin_token'])
        if fail:assert code==409 and value['error']['code']=='CONFIG_APPLY_FAILED',(code,value)
        else:assert code==200,(code,value)
        h.config=json.loads((h.root/'config.json').read_text())
        return revision
    def call(project,op,**fields):return h.call({'op':op,'project_id':project,**fields})
    def status(project):return admin('eventing_status',project)
    def poll(project):return call(project,'poll')['deliveries']
    def receive(project,ids):
        def observe():
            rows=poll(project)
            return rows if ids<={row['publication_id'] for row in rows} else None
        return wait(observe,'Real Kafka delivery did not progress',45)
    def acknowledge(project):
        rows=poll(project)
        if rows:call(project,'ack',delivery_ids=[row['id'] for row in rows])
    def retained(topic):
        with httpx.Client(trust_env=False,timeout=5) as client:
            cluster=client.get(a.eventing_rest_url+'/v3/clusters').json()['data'][0]['cluster_id']
            configs=client.get(a.eventing_rest_url+'/v3/clusters/'+cluster+'/topics/'+topic+'/configs').json()['data']
            return int(next(row['value'] for row in configs if row['name']=='retention.ms'))
    try:
        h.start()
        for project in ('p','q'):
            call(project,'subscribe',mode='raw')
            original=call(project,'publish',text='Original before project policy edit')['publication']
            receive(project,{original['id']});acknowledge(project)
        before={project:status(project) for project in ('p','q')}
        gate.fail_topic=before['q']['topic']
        revision=patch({'eventing':{'retention_ms':3600000}},fail=True)
        gate.fail_topic=None
        assert admin('config_get')['config_revision']==revision
        assert not gate.alters
        assert retained(before['p']['topic'])==604800000 and retained(before['q']['topic'])==604800000
        record('failed-second-project-preflight-never-shrinks-first-project-broker-retention')

        gate.hold_topic=before['q']['topic'];gate.holding.clear();gate.release.clear()
        held=call('q','publish',text='Fetched under old configuration but not materialized')['publication']
        assert gate.holding.wait(15),'No actual Kafka record was fetched for the fence experiment'
        projects=copy.deepcopy(h.config['projects']);projects[0]['name']='Renamed display label'
        patch({'projects':projects});gate.release.set()
        receive('q',{held['id']});acknowledge('q')
        record('stale-fetched-batch-recreates-consumer-at-durable-position-after-hot-change')

        projects=copy.deepcopy(h.config['projects'])
        projects[0]['settings']={'eventing':{'retention_ms':3600000,'max_pending_events':1,'max_pending_bytes':65536}}
        p_before=status('p');q_before=status('q');patch({'projects':projects})
        assert retained(status('p')['topic'])==3600000
        assert retained(status('q')['topic'])==604800000
        assert status('p')['next_offset']==p_before['next_offset'] and status('q')['next_offset']==q_before['next_offset']
        assert gate.alters
        gate.block_produces=True
        accepted=call('p','publish',text='Accepted under project pending limit')['publication']
        h.call({'op':'publish','project_id':'p','text':'Must fail own project limit'},error='BACKPRESSURE')
        qevents={call('q','publish',text='Independent backlog '+str(i))['publication']['id'] for i in range(2)}
        projects=copy.deepcopy(h.config['projects']);projects[0]['settings']['eventing']['topic_prefix']='project_p'
        q_checkpoint=status('q')['next_offset'];patch({'projects':projects})
        assert status('p')['topic']!=before['p']['topic'] and status('q')['topic']==before['q']['topic']
        assert status('q')['next_offset']==q_checkpoint
        gate.block_produces=False
        receive('p',{accepted['id']});receive('q',qevents);acknowledge('p');acknowledge('q')
        record('project-retention-budget-and-topic-cutover-preserve-independent-project-progress-and-acks')

        projects=copy.deepcopy(h.config['projects']);projects[0]['settings']['eventing']={key:None for key in ('topic_prefix','retention_ms','max_pending_events','max_pending_bytes')}
        patch({'projects':projects})
        assert status('p')['topic']==before['p']['topic'] and retained(status('p')['topic'])==604800000
        assert h.config['projects'][0]['settings']['eventing']=={}
        wait(lambda:status('p')['last_error'] is None,'Reset topic did not reconcile')
        assert not poll('p') and not poll('q')
        projects=copy.deepcopy(h.config['projects']);projects.append({'id':'new','name':'New','settings':{'eventing':{'topic_prefix':'new_project','retention_ms':7200000}}})
        patch({'projects':projects})
        if request(h.base,'/protocol/schema')[1].get('$id')=='urn:adhd:protocol:2.1':
            assert admin('project_restore_status','new')['availability']=='uninitialized'
            h.initialize_unknown_projects()
        assert retained(status('new')['topic'])==7200000
        assert model.states==[]
        record('per-field-null-reset-inherits-root-and-new-project-preflight-needs-no-live-empty-writer')
        report['passed']=True;report['artifact_sha256']=target.artifact
    finally:
        gate.release.set();h.stop();gate.close();model.close();a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
