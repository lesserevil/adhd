#!/usr/bin/env python3
"""Independent archive-lane rate and matching/publish/poll responsiveness witness."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture

def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');parser.add_argument('--report',default='verification/archive-fairness.json');args=parser.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/archive-fairness').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture()
    cfg={'project_id':'archive-fairness','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{a:secrets.token_urlsafe(32) for a in ('alice','bob')},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600);latencies=[]
    def rpc(cmd,actor='alice'):
        start=time.monotonic();result=Client(h).rpc(cmd,h.config['agents'][actor]);latencies.append(time.monotonic()-start);return result
    def wait(fn):
        end=time.monotonic()+35
        while time.monotonic()<end:
            if value:=fn():return value
            time.sleep(.05)
        raise AssertionError('Fairness deadline; inspect '+str(root))
    try:
        h.start();rpc({'op':'publish_record','text':'The sample fixture result was λ.','information_type':'evidence'})
        wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready');rpc({'op':'subscribe','description':'Matching load fixture'},'bob')
        model.mode='slow';model.delay=.35
        for i in range(16):rpc({'op':'publish_record','text':'Matching load record '+str(i),'information_type':'load'})
        submitted=[]
        for i in range(6):submitted.append(rpc({'op':'query_archive','question':'Which sample result was recorded for fixture '+str(i)+'?','scope':{'information_type':'evidence'}})['query'])
        queued=wait(lambda:v if len(v:=rpc({'op':'poll'},'bob')['deliveries'])==16 else None)
        rpc({'op':'ack','delivery_ids':[v['id'] for v in queued]},'bob')
        done=[]
        for q in submitted:
            value=wait(lambda:v if (v:=rpc({'op':'get_archive_query','query_id':q['id']})['query'])['status']!='pending' else None);assert value['status']=='completed',value['error'];done.append(value)
        with model.lock:requests=list(model.requests)
        matching=[v['at'] for v in requests if 'relevance' in v['request']['questions']];assert len(matching)==16
        analysis=[v['at'] for v in requests if any(k in v['request']['questions'] for k in ('intent','assessment')) and matching[0]<=v['at']<=matching[-1]]
        intervals=[b-a for a,b in zip(analysis,analysis[1:])];assert len(analysis)>=3 and all(v>=.95 for v in intervals),(analysis,intervals)
        assert matching[-1]-matching[0]<12 and max(latencies)<1.0,(matching[-1]-matching[0],max(latencies))
        assert rpc({'op':'poll'},'bob')['deliveries']==[]
        result={'schema':'adhd/archive-fairness@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'matching_calls':len(matching),'analysis_starts_while_matching_due':len(analysis),'analysis_intervals_seconds':intervals,'matching_start_span_seconds':matching[-1]-matching[0],'maximum_api_seconds':max(latencies),'completed_archive_questions':len(done),'workdir':str(root.relative_to(Path.cwd()))}
        Path(args.report).write_text(json.dumps(result,indent=2)+'\n');print('PASS independent analysis lane rate, matching, publish, poll and ACK')
    finally:h.stop();model.close()

if __name__=='__main__':main()
