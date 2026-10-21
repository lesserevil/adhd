#!/usr/bin/env python3
"""Independent real-Kafka bounded filter admission, restart and dormant-policy checks."""
import argparse
import json
import hashlib
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4
from federation_acceptance import Hub, Model, request
from federation_multi import wait


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--command',required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--eventing-rest-url',default='http://127.0.0.1:18082')
    a=p.parse_args();a.work=a.work.resolve();a.work.mkdir(parents=True,exist_ok=True)
    models=[Model() for _ in range(3)]
    for m in models:m.mode='error'
    h=Hub(json.loads(a.command),a.work/'hub','p',models[0].url)
    h.config.update(server_id=uuid4().hex,projects=[{'id':'p','name':'P'},{'id':'q','name':'Q'}],
        agent_projects={x:['p','q'] for x in ('alice','bob')},threshold_ppm=5000,
        eventing={'enabled':True,'rest_url':a.eventing_rest_url,'retry_ms':100,
                  'max_pending_filter_jobs':3,'max_pending_filter_jobs_per_subscription':2})
    report={'schema':'adhd/filter-budget@1','passed':False,'checks':[],
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def record(name):report['checks'].append({'name':name,'passed':True});print('PASS',name,flush=True)
    def admin(op,project=None,**fields):
        code,v=request(h.base,'/admin/api',{'op':op,**({'project_id':project} if project else {}),**fields},h.config['admin_token'])
        assert code==200,(code,v)
        return v
    def patch(change):
        code,v=request(h.base,'/admin/api',{'op':'config_update','expected_revision':admin('config_get')['config_revision'],
            'message_id':uuid4().hex,'confirm':True,'patch':change},h.config['admin_token'])
        assert code==200,(code,v)
        h.config=json.loads((h.root/'config.json').read_text())
    def call(op,agent='alice',project='p',**kw):return h.call({'op':op,'project_id':project,**kw},agent=agent)
    def status(project='p'):return admin('eventing_status',project)
    def settled(n,d,project='p'):
        def check():
            s=status(project)
            return s if s['pending_events']==0 and s['pending_filter_jobs']==n and s['deferred_filter_targets']==d else None
        return wait(check,'Expected filter counts '+str((n,d,project)),120)
    def poll(agent='alice',project='p'):return call('poll',agent,project)['deliveries']
    def receive(ids,agent='alice',project='p'):
        return wait(lambda:ids<={r['publication_id'] for r in poll(agent,project)},'Delivery set did not progress',45)
    def publish(text,project='p'):return call('publish',project=project,text=text)['publication']['id']
    try:
        h.start()
        for project in ('p','q'):call('subscribe',project=project,mode='raw')
        subs=[call('subscribe','bob',mode='filtered',filter='all facts '+str(i))['subscription'] for i in range(2)]
        ids={publish('Budget event '+str(i)) for i in range(18)}
        receive(ids);s=settled(3,33)
        assert s['filter_queue_limits']=={'max_pending_filter_jobs':3,'max_pending_filter_jobs_per_subscription':2}
        counts=Counter(j['subscription_id'] for j in admin('jobs','p',status='pending')['items'])
        assert sum(counts.values())==3 and max(counts.values())<=2,counts
        assert not poll('bob')
        record('real-kafka-raw-stream-progresses-with-ready-project-and-subscription-caps-full')
        patch({'eventing':{'max_pending_filter_jobs':1,'max_pending_filter_jobs_per_subscription':1}})
        more={publish('Additional event '+str(i)) for i in range(3)};ids|=more
        receive(ids);settled(3,39)
        qid=publish('Independent project event','q');receive({qid},project='q');settled(0,0,'q')
        h.stop(hard=True);h.start();settled(3,39);receive(ids)
        record('hot-cap-reduction-retains-overcap-jobs-and-hard-restart-preserves-durable-deferred-intents')
        # All newly accepted off-state publications must freeze the most recent
        # effective adapter B; enabling C later is only a permission gate.
        adapter=dict(h.config['matcher']);adapter.update(url=models[1].url,model='dormant-B')
        patch({'matcher':adapter});patch({'matcher':None})
        count=[len(m.states) for m in models];off=publish('Accepted with dormant B');ids.add(off)
        receive(ids);settled(3,41);time.sleep(.7)
        assert [len(m.states) for m in models]==count
        assert status()['filtering_paused']
        adapter.update(url=models[2].url,model='replacement-C')
        patch({'matcher':adapter,'threshold_ppm':900000})
        for m in models:m.mode='normal'
        settled(0,0);receive(ids,'bob')
        rows=poll('bob');assert len(rows)==len(ids),(len(rows),len(ids))
        offrow=next(r for r in rows if r['publication_id']==off)
        assert all(m['threshold_ppm']==5000 and m['model']=='dormant-B' for m in offrow['matches']),offrow
        assert models[1].states and not models[2].states
        assert all(len(r['matches'])==2 for r in rows),rows
        call('ack','bob',delivery_ids=[r['id'] for r in rows]);h.stop(hard=True);h.start()
        assert not poll('bob');settled(0,0)
        record('off-state-publication-freezes-last-effective-adapter-and-threshold-across-reenable-and-restart')
        # A revised criterion creates a distinct replay intent. A full queue must
        # report deferred, then materialized handoff without resurrecting acked IDs.
        models[2].mode='error'
        patch({'threshold_ppm':5000})
        sub=call('update_subscription','bob',subscription_id=subs[0]['id'],expected_revision=1,
                 mode='filtered',filter='Revised replay criterion')['subscription']
        blocked=publish('Fill single ready slot');receive({blocked});settled(1,1)
        watermark=status()['replay_watermark']
        result=admin('replay_events','p',from_sequence=1,to_sequence=watermark,
            expected_watermark=watermark,subscriptions=[{'id':sub['id'],'revision':sub['revision']}],
            reason='Bounded replay qualification',confirm=True,message_id=uuid4().hex)
        rid=result['replay']['id']
        def deferred():
            r=admin('eventing_replay','p',replay_id=rid)['replay']
            return r if r['status']=='deferred' and r['deferred_filter_targets']>0 else None
        wait(deferred,'Replay never reported actual deferred intents',45)
        assert status()['pending_filter_jobs']==1
        models[2].mode='normal';settled(0,0)
        wait(lambda:admin('eventing_replay','p',replay_id=rid)['replay']['status']=='materialized','Replay handoff incomplete',30)
        assert not ({r['publication_id'] for r in poll('bob')}&ids),'Replay resurrected acknowledgements'
        record('replay-shares-bounded-ready-slots-and-distinguishes-deferred-intents-from-materialized-handoff')
        # Project overrides govern actual ready admission independently of the
        # shared root service; removing a subscription cleans paused intents.
        models[2].mode='error'
        projects=json.loads(json.dumps(h.config['projects']))
        projects[1]['settings']={'eventing':{'max_pending_filter_jobs':2,'max_pending_filter_jobs_per_subscription':2}}
        patch({'projects':projects})
        qsub=call('subscribe','bob',project='q',mode='filtered',filter='Project Q filter')['subscription']
        qids={publish('Q bounded filter '+str(i),'q') for i in range(3)}
        receive(qids,project='q');settled(2,1,'q');settled(0,0)
        patch({'matcher':None})
        paused={publish('Deferred then cancelled '+str(i)) for i in range(2)}
        receive(paused);settled(0,4)
        before=[len(m.states) for m in models]
        for sub_id in (subs[0]['id'],subs[1]['id']):call('unsubscribe','bob',subscription_id=sub_id)
        call('unsubscribe','bob',project='q',subscription_id=qsub['id'])
        settled(0,0);settled(0,0,'q');time.sleep(.3)
        assert [len(m.states) for m in models]==before
        record('project-overrides-bound-real-filter-jobs-and-unsubscribe-cancels-paused-deferred-intents')
        report['passed']=True
    finally:
        h.stop()
        for m in models:m.close()
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
