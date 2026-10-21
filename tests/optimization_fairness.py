#!/usr/bin/env python3
"""Owned optimizer replay and Archive share their lane while matching/poll/ACK progress."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--command');m.add_argument('--image');p.add_argument('--report',default='verification/optimization-fairness.json');a=p.parse_args();command=json.loads(a.command) if a.command else []
    parent=Path('_build/roadmap/optimization-fairness').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,a.image);model=ArchiveFixture();model.retrieval_noul=.01;latencies=[]
    cfg={'project_id':'optimization-fairness','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{x:secrets.token_urlsafe(32) for x in ['alice','bob']},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'resources':{'project_model_concurrency':2},'archive':{'audit_rate_ppm':0},'optimization':{'enabled':True}};h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def admin(c,mutation=False):return Client(h,h.config['admin_token']).api(c,mutation=mutation)
    def rpc(c,actor='alice'):
        start=time.monotonic();v=Client(h).rpc(c,h.config['agents'][actor]);latencies.append(time.monotonic()-start);return v
    def wait(fn):
        end=time.monotonic()+60
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Optimizer lane deadline '+str(root))
    try:
        h.start();training=[]
        for i in range(2):
            tag='training'+str(i);pub=rpc({'op':'publish_record','text':'Controlled background evidence.','information_type':tag})['record']['publication']['id'];wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
            q=rpc({'op':'query_archive','question':'Was specimen '+['Alpha','Beta'][i]+' present?','scope':{'information_type':tag}})['query'];qid=q['id'];wait(lambda:rpc({'op':'get_archive_query','query_id':qid})['query']['status']=='completed')
            attempt=wait(lambda:[r for r in rpc({'op':'list_retrieval_attempts'})['items'] if r['archive_query_id']==qid])[0]
            admin({'op':'save_retrieval_label','attempt_id':attempt['id'],'expected_label_revision':0,'label':{'expectation':'supported','support_ids':[pub],'cohort':'training','tags':[],'note':'Controlled model scheduling assertion; not live-model quality.','confirmed':True}},True);training.append(attempt['id'])
        rpc({'op':'publish_record','text':'Sample lane fixture result λ.','information_type':'evidence'});wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        rpc({'op':'subscribe','description':'Independent slow matching workload'},'bob');model.mode='slow';model.delay=.35
        for i in range(16):rpc({'op':'publish_record','text':'Matching workload '+str(i),'information_type':'load'})
        proposal=admin({'op':'propose_index','training_attempt_ids':training},True)['proposal'];id=proposal['id']
        archives=[rpc({'op':'query_archive','question':'Which archive lane fixture result was recorded for observation '+str(i)+'?','scope':{'information_type':'evidence'}})['query'] for i in range(6)]
        delivered=wait(lambda:v if len(v:=rpc({'op':'poll'},'bob')['deliveries'])==16 else None);rpc({'op':'ack','delivery_ids':[d['id'] for d in delivered]},'bob')
        current=admin({'op':'index_proposal','proposal_id':id})['proposal'];assert current['children'] and current['usage']['cumulative_calls']>0
        admin({'op':'cancel_index_proposal','proposal_id':id},True)
        for q in archives:
            qid=q['id'];result=wait(lambda:v if (v:=rpc({'op':'get_archive_query','query_id':qid})['query'])['status']!='pending' else None);assert result['status']=='completed',result['error']
        with model.lock:requests=list(model.requests)
        matching=[r['at'] for r in requests if 'relevance' in r['request']['questions']];assert len(matching)==16
        direct=[];kinds=set();history=[]
        for r in requests:
            question=r['request']['state'].get('question','');keys=r['request']['questions']
            if not matching[0]<=r['at']<=matching[-1]:continue
            archive=question.startswith('Which archive lane') and any(k in keys for k in ['intent','assessment'])
            optimizer=question.startswith('Was specimen ') and 'useful' in keys
            if archive or optimizer:direct.append(r['at']);kinds.add('archive' if archive else 'optimization')
            if question.startswith('Was specimen ') and 'assessment' in keys:history.append(r['at'])
        intervals=[b-a for a,b in zip(direct,direct[1:])];assert len(direct)>=3 and kinds=={'archive','optimization'} and all(d>=.95 for d in intervals),(kinds,direct,intervals)
        assert matching[-1]-matching[0]<12 and max(latencies)<1,(matching[-1]-matching[0],max(latencies));assert rpc({'op':'poll'},'bob')['deliveries']==[]
        report={'schema':'adhd-optimization-fairness-report@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':a.image,'resource_profile':{'project_model_concurrency':2},'matching_calls':16,'completed_archive':6,'owned_optimizer_children':len(current['children']),'actual_optimizer_usage':current['usage'],'shared_analysis_lane_kinds':sorted(kinds),'shared_analysis_intervals_seconds':intervals,'separately_paced_history_starts_while_matching_due':len(history),'matching_start_span_seconds':matching[-1]-matching[0],'maximum_api_seconds':max(latencies)};Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print('PASS owned optimizer/Archive shared lane, separate History pacing and responsive matching/publish/poll/ACK',flush=True)
    finally:h.stop();model.close()

if __name__=='__main__':main()
