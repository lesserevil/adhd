#!/usr/bin/env python3
"""Hold actual Kafka observation to prove atomic last-adapter binding without a worker tick."""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from federation_acceptance import Hub, Model, request
from federation_multi import wait
from eventing_controls import ControlledGateway


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--eventing-rest-url',default='http://127.0.0.1:18082');a=p.parse_args()
    a.work=a.work.resolve();a.work.mkdir(parents=True,exist_ok=True)
    models=[Model() for _ in range(3)];gate=ControlledGateway(a.eventing_rest_url)
    h=Hub(json.loads(a.command),a.work/'hub','p',models[0].url)
    def adapter(i,name):return {'url':models[i].url,'model':name,'timeout_ms':1000,'retry_ms':100}
    h.config.update(server_id=uuid4().hex,threshold_ppm=5000,projects=[{'id':'p','name':'P'},
        {'id':'q','name':'Q','settings':{'matcher':adapter(0,'project-Q')}}],
        agent_projects={x:['p','q'] for x in ('alice','bob')},
        eventing={'enabled':True,'rest_url':gate.url,'retry_ms':100})
    report={'schema':'adhd/dormant-policy@1','passed':False,'checks':[],
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def admin(op,project=None,**kw):
        code,v=request(h.base,'/admin/api',{'op':op,**({'project_id':project} if project else {}),**kw},h.config['admin_token'])
        assert code==200,(code,v)
        return v
    def patch(change):
        admin('config_update',expected_revision=admin('config_get')['config_revision'],
              patch=change,confirm=True,message_id=uuid4().hex)
        h.config=json.loads((h.root/'config.json').read_text())
    def call(op,agent='alice',project='p',**kw):return h.call({'op':op,'project_id':project,**kw},agent=agent)
    def receive(ids,agent='alice',project='p'):
        return wait(lambda:ids<={r['publication_id'] for r in call('poll',agent,project)['deliveries']},'Dormant policy delivery missing',45)
    def record(name):report['checks'].append({'name':name,'passed':True});print('PASS',name,flush=True)
    try:
        h.start()
        for project in ('p','q'):
            call('subscribe',project=project,mode='raw')
            call('subscribe','bob',project,mode='filtered',filter='Accept the retained fact')
        gate.hold_topic=admin('eventing_status','p')['topic'];gate.holding.clear();gate.release.clear()
        initial=call('publish',text='Hold this fetched record')['publication']['id']
        assert gate.holding.wait(15),'No held actual Kafka response'
        # The event worker cannot remember B while its HTTP response is held.
        patch({'matcher':adapter(1,'atomic-B')});patch({'matcher':None})
        off=call('publish',text='Off-state original')['publication']['id']
        gate.release.set();receive({initial,off})
        # Q retains its explicit adapter while P is disabled; root B must never
        # overwrite Q's last-effective project policy.
        qid=call('publish',project='q',text='Project-specific adapter')['publication']['id']
        receive({qid},'bob','q')
        wait(lambda:admin('eventing_status','p')['deferred_filter_targets']==2,'Disabled targets not deferred',30)
        assert not call('poll','bob')['deliveries']
        h.stop(hard=True);h.start()
        patch({'matcher':adapter(2,'replacement-C'),'threshold_ppm':900000})
        receive({initial,off},'bob')
        row=next(r for r in call('poll','bob')['deliveries'] if r['publication_id']==off)
        assert row['matches'][0]['model']=='atomic-B' and row['matches'][0]['threshold_ppm']==5000,row
        assert any(v['model']=='atomic-B' for v in models[1].states)
        assert not models[2].states
        assert any(v['model']=='project-Q' for v in models[0].states)
        record('held-worker-rapid-adapter-change-and-disable-persists-B-before-ack-and-hard-restart')
        record('project-effective-adapter-provenance-is-independent-of-root-changes')
        report['passed']=True
    finally:
        gate.release.set();h.stop();gate.close()
        for m in models:m.close()
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
