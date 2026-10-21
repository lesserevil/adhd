#!/usr/bin/env python3
"""Mixed Archive/replay analysis shares one rate limit while matching remains responsive."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--report',default='verification/feedback-mixed-fairness.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-fairness').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();latencies=[]
    cfg={'project_id':'feedback-fairness','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{a:secrets.token_urlsafe(32) for a in ['alice','bob']},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(c,actor='alice'):
        start=time.monotonic();v=Client(h).rpc(c,h.config['agents'][actor]);latencies.append(time.monotonic()-start);return v
    def wait(fn):
        end=time.monotonic()+45
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Mixed lane deadline '+str(root))
    try:
        h.start();rpc({'op':'publish_record','text':'Sample lane fixture result λ.','information_type':'evidence'});wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        q=rpc({'op':'query_archive','question':'Which replay lane fixture result was recorded?','scope':{'information_type':'evidence'}})['query'];wait(lambda:rpc({'op':'get_archive_query','query_id':q['id']})['query']['status']=='completed');a=wait(lambda:rpc({'op':'list_retrieval_attempts'})['items'])[0]
        rpc({'op':'subscribe','description':'Independent slow matching workload'},'bob');model.mode='slow';model.delay=.35
        for i in range(16):rpc({'op':'publish_record','text':'Matching workload '+str(i),'information_type':'load'})
        replays=[rpc({'op':'replay_retrieval','attempt_id':a['id'],'candidate_recipe':{'context_depth':2}})['query'] for _ in range(4)]
        archives=[rpc({'op':'query_archive','question':'Which archive lane fixture result was recorded for observation '+str(i)+'?','scope':{'information_type':'evidence'}})['query'] for i in range(6)]
        delivered=wait(lambda:v if len(v:=rpc({'op':'poll'},'bob')['deliveries'])==16 else None);rpc({'op':'ack','delivery_ids':[v['id'] for v in delivered]},'bob')
        for op,rows in [('get_retrieval_replay',replays),('get_archive_query',archives)]:
            for q in rows:
                result=wait(lambda:v if (v:=rpc({'op':op,'query_id':q['id']})['query'])['status']!='pending' else None);assert result['status']=='completed',result['error']
        with model.lock:requests=list(model.requests)
        matching=[v['at'] for v in requests if 'relevance' in v['request']['questions']];assert len(matching)==16
        analysis=[];kinds=set()
        for v in requests:
            body=v['request'];question=body['state'].get('question','');questions=body['questions']
            archive=question.startswith('Which archive lane') and any(k in questions for k in ['intent','assessment'])
            replay=question.startswith('Which replay lane') and any(k in questions for k in ['useful','assessment'])
            if matching[0]<=v['at']<=matching[-1] and (archive or replay):analysis.append(v['at']);kinds.add('archive' if archive else 'replay')
        intervals=[b-a for a,b in zip(analysis,analysis[1:])];assert len(analysis)>=3 and kinds=={'archive','replay'} and all(v>=.95 for v in intervals),(kinds,analysis,intervals)
        assert matching[-1]-matching[0]<12 and max(latencies)<1,(matching[-1]-matching[0],max(latencies));assert rpc({'op':'poll'},'bob')['deliveries']==[]
        result={'schema':'adhd/feedback-fairness@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'matching_calls':16,'completed_archive':6,'completed_replay':4,'analysis_kinds':sorted(kinds),'analysis_starts_while_matching_due':len(analysis),'analysis_intervals_seconds':intervals,'matching_start_span_seconds':matching[-1]-matching[0],'maximum_api_seconds':max(latencies),'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n');print('PASS mixed Archive/replay shared rate and independent matching/publish/poll/ACK',flush=True)
    finally:h.stop();model.close()

if __name__=='__main__':main()
