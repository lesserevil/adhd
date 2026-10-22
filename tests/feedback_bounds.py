#!/usr/bin/env python3
"""Feedback capture backlog, retained-job bounds and empty-scope accounting."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--report',default='verification/feedback-bounds.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-bounds').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'feedback-bounds','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'},'archive':{'audit_rate_ppm':0},'feedback':{'max_attempts':1,'max_replays':1,'max_active_replays':1}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(c):return Client(h).rpc(c,h.config['agents']['alice'])
    def admin(c,mutation=False):return Client(h,h.config['admin_token']).api(c,mutation=mutation)
    def wait(fn):
        end=time.monotonic()+30
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.025)
        raise AssertionError('Bound fixture deadline '+str(root))
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def archive(question):
        q=rpc({'op':'query_archive','question':question,'scope':{'information_type':'empty'}})['query'];return wait(lambda:v if (v:=rpc({'op':'get_archive_query','query_id':q['id']})['query'])['status']=='completed' else None)
    try:
        h.start();pid=h.pid;first=archive('Which empty fixture observation exists?');a=wait(lambda:rpc({'op':'list_retrieval_attempts'})['items'])[0]
        second=archive('Which other empty fixture observation exists?');status=wait(lambda:v if (v:=admin({'op':'feedback_status'})['status'])['unrecorded_runs']==1 and v['last_error'] else None)
        assert status['attempts']==1 and status['last_error']['code']=='RESOURCE_LIMIT';record('capture-count-bound-preserves-terminal-backlog-and-reports-resource-error')
        h.stop(hard=True);h.start();assert admin({'op':'feedback_status'})['status']['unrecorded_runs']==1
        admin({'op':'config_update','patch':{'feedback':{'max_attempts':2}}},True);wait(lambda:len(rpc({'op':'list_retrieval_attempts'})['items'])==2);assert admin({'op':'feedback_status'})['status']['last_error'] is None;record('bounded-backlog-survives-restart-and-hot-cap-increase-resumes-capture')
        label={'expectation':'no_evidence','support_ids':[],'cohort':'training','tags':[],'note':'Explicit empty applicable scope','confirmed':True};admin({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':label},True)
        cmd={'op':'replay_retrieval','attempt_id':a['id'],'baseline':'current','candidate_recipe':{}};q=rpc(cmd)['query'];q=wait(lambda:v if (v:=rpc({'op':'get_retrieval_replay','query_id':q['id']})['query'])['status']!='pending' else None)
        assert q['status']=='completed' and q['usage']['total']['calls']==0 and q['comparison']['eligible'] and q['baseline']['metrics']['answer_pass'] and q['candidate']['metrics']['answer_pass']
        assert model.requests==[];record('empty-replay-performs-no-model-calls-and-records-real-zero-cost-children')
        envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':'retained-bound','role':'ROLE_USER','parts':[{'data':cmd}]}}};_,denied,_=Client(h).request('/a2a',envelope,{'Authorization':'Bearer '+h.config['agents']['alice']});assert denied['error']['data'][0]['reason']=='RESOURCE_EXHAUSTED'
        admin({'op':'retire_replay','query_id':q['id']},True);assert admin({'op':'feedback_status'})['status']['replays']==1;admin({'op':'config_update','patch':{'feedback':{'max_replays':2}}},True);assert rpc(cmd)['query']['id']!=q['id'];record('retained-job-quota-includes-retired-metrics-and-single-field-hot-increase-is-valid')
        result={'schema':'adhd/feedback-bounds@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
