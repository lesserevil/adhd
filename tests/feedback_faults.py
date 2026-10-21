#!/usr/bin/env python3
"""Replay hard interruption, stale leases, cancellation, policy fences and real fallback."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--report',default='verification/feedback-faults.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-faults').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'feedback-faults','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(c):return Client(h).rpc(c,h.config['agents']['alice'])
    def admin(c,mutation=False):return Client(h,h.config['admin_token']).api(c,mutation=mutation)
    def patch(v):return admin({'op':'config_update','patch':v},True)
    def wait(fn,seconds=30):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.025)
        raise AssertionError('Fault fixture deadline '+str(root))
    def get(q):return rpc({'op':'get_retrieval_replay','query_id':q['id']})['query']
    def replay(**kw):return rpc({'op':'replay_retrieval','attempt_id':a['id'],'candidate_recipe':{},**kw})['query']
    def finish(q,status='completed'):
        v=wait(lambda:v if (v:=get(q))['status']!='pending' else None);ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/ReplayQuery'}).validate(v);assert v['status']==status,v['error'];return v
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    try:
        h.start();schema=Client(h).get('/protocol/schema')[1];rpc({'op':'publish_record','text':'Sample fault fixture result λ.'});wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        archive=rpc({'op':'query_archive','question':'Which sample fault result was reported?'})['query'];wait(lambda:rpc({'op':'get_archive_query','query_id':archive['id']})['query']['status']=='completed');a=wait(lambda:rpc({'op':'list_retrieval_attempts'})['items'])[0];admin({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':{'expectation':'supported','support_ids':[a['candidates'][0]['publication_id']],'cohort':'training','tags':[],'note':'Independent authored fixture result','confirmed':True}},True)
        # Kill after the provider accepted a reserved call, before it returns.
        model.mode='slow';model.delay=1.5;q=replay();wait(lambda:get(q)['baseline']['usage']['calls']==1)
        with model.lock:accepted=len(model.requests)
        assert accepted>=1;h.stop(hard=True);model.mode='normal';h.start();q=finish(q)
        assert q['baseline']['usage']['uncertain_calls']==1 and q['baseline']['usage']['calls']==3 and q['baseline']['usage']['time_ms']>=3000
        stable=get(q);time.sleep(.15);assert get(q)==stable;record('hard-kill-reserved-http-lease-is-charged-once-and-recovery-retries-with-fresh-nonce')
        model.mode='slow';model.delay=.8;q=replay();wait(lambda:get(q)['baseline']['usage']['calls']==1)
        start=time.monotonic();cancelled=rpc({'op':'cancel_retrieval_replay','query_id':q['id']})['query'];assert time.monotonic()-start<1 and cancelled['status']=='cancelled' and cancelled['baseline']['usage']['uncertain_calls']==1
        time.sleep(1);assert get(q)==cancelled;record('cancellation-settles-uncertain-cost-and-late-response-cannot-commit')
        model.mode='slow';q=replay();wait(lambda:get(q)['baseline']['usage']['calls']==1);patch({'history':{'operator_version':'changed-during-lease'}});invalid=finish(q,'invalidated');assert invalid['error']['code']=='POLICY_CHANGED'
        time.sleep(1);assert get(q)==invalid;model.mode='normal';restarted=rpc({'op':'continue_retrieval_replay','query_id':q['id'],'restart':True})['query'];restarted=finish(restarted);assert restarted['policy']['history_evaluator']['operator_version']=='changed-during-lease' and restarted['snapshot']==q['snapshot'];record('hot-policy-change-fences-inflight-results-and-explicit-restart-keeps-corpus')
        model.mode='fail-retrieval';fallback=finish(replay());assert fallback['baseline']['scan'] and fallback['candidate']['scan'] and fallback['baseline']['answer']['assessment']=='direct' and fallback['baseline']['error']['code']=='MODEL_ERROR';model.mode='normal'
        record('semantic-model-failure-uses-real-full-history-fallback-with-explicit-branch-error')
        model.mode='fail-retrieval';checkpoint=finish(replay(budget={'calls':1}),'partial');assert checkpoint['error']['code']=='BUDGET_CALLS';model.mode='normal'
        checkpoint=rpc({'op':'continue_retrieval_replay','query_id':checkpoint['id'],'budget':{'calls':16}})['query'];checkpoint=finish(checkpoint);assert checkpoint['baseline']['error']['code']=='MODEL_ERROR' and not checkpoint['comparison']['eligible'];record('continuation-cannot-erase-failed-baseline-or-manufacture-quality-credit')
        patch({'retrieval':{'request_bytes':1024,'model':'Nemotron-Deciffusion-8B-v2.1/'+('x'*450)}});bounded=finish(replay());assert bounded['baseline']['scan'] and bounded['baseline']['answer']['assessment']=='direct' and bounded['baseline']['error']['code']=='CONTEXT_LIMIT' and not bounded['comparison']['eligible'];patch({'retrieval':{'request_bytes':6144,'model':None}})
        rpc({'op':'publish_record','text':'Oversized original fixture '+('x'*7000),'information_type':'large'})
        context=finish(replay(corpus='current'),'partial');assert context['error']['code']=='CONTEXT_LIMIT';rpc({'op':'cancel_retrieval_replay','query_id':context['id']});record('retrieval-input-limit-falls-back-and-natural-history-context-limit-keeps-its-real-cause')
        for budget,code in [({'records':1},'BUDGET_RECORDS'),({'calls':1},'BUDGET_CALLS'),({'bytes':1024},'BUDGET_BYTES')]:
            limited=finish(replay(budget=budget),'partial');assert limited['error']['code']==code,limited['error']
        model.mode='slow';model.delay=.4;limited=finish(replay(budget={'time_ms':100}),'partial');assert limited['error']['code']=='BUDGET_TIME';model.mode='normal';record('all-four-per-branch-budget-limits-checkpoint-without-counterfactual-charges')
        # Disablement and owner removal must not leave invisible pending work.
        patch({'retrieval':{'enabled':False}});disabled=finish(replay(),'partial');assert disabled['error']['code']=='RETRIEVAL_DISABLED';patch({'retrieval':{'enabled':True}})
        q=replay(budget={'calls':1});q=finish(q,'partial');owner_token=h.config['agents']['alice'];owner_projects=h.config['agent_projects']['alice'];patch({'agents':{'alice':None},'agent_projects':{'alice':None}})
        # Restart is deliberately not used: this already stopped observation is
        # preserved; a newly pending job below is observed via the Admin API.
        patch({'agents':{'alice':owner_token},'agent_projects':{'alice':owner_projects}});model.mode='slow';q=replay();wait(lambda:get(q)['baseline']['usage']['calls']==1);patch({'agents':{'alice':None},'agent_projects':{'alice':None}})
        removed=wait(lambda:v if (v:=admin({'op':'query_job','query_id':q['id']})['query'])['status']!='pending' else None);assert removed['status']=='partial' and removed['error']['code']=='OWNER_REMOVED';patch({'agents':{'alice':owner_token},'agent_projects':{'alice':owner_projects}});model.mode='normal';record('disabled-dependencies-and-removed-owner-have-visible-terminal-errors')
        # A configured cap reduction keeps every original and permits retirement.
        terminal=finish(replay());patch({'feedback':{'max_replays':1,'max_active_replays':1}});retired=admin({'op':'retire_replay','query_id':terminal['id']},True)['query'];assert not retired['evidence_available'];assert rpc({'op':'get_record','publication_id':a['candidates'][0]['publication_id']})['record'];patch({'feedback':{'max_replays':2}});assert admin({'op':'config_get'})['config']['feedback']['max_active_replays']==1;record('hot-cap-reduction-preserves-source-data-and-allows-bounded-derived-retirement')
        result={'schema':'adhd/feedback-faults@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
