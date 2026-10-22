#!/usr/bin/env python3
"""Live Nemotron same-snapshot paired context recovery and negative controls."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--model-url',default='http://127.0.0.1:18770/v1/systemone');p.add_argument('--report',default='verification/feedback-quality.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-quality').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);cases=[]
    cfg={'project_id':'feedback-quality','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':args.model_url,'model':'Nemotron-Deciffusion-8B-v2.1'},'history':{'request_bytes':8192},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(c):return Client(h).rpc(c,h.config['agents']['alice'])
    def admin(c,mutation=False):return Client(h,h.config['admin_token']).api(c,mutation=mutation)
    def wait(fn):
        end=time.monotonic()+60
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Real model deadline '+str(root))
    def publish(text,tag,reply=None):return rpc({'op':'publish_record','text':text,'information_type':tag,**({'context':{'links':[{'relation':'reply','publication_id':reply}]}} if reply else {})})['record']['publication']['id']
    def finish(q,op):return wait(lambda:v if (v:=rpc({'op':op,'query_id':q['id']})['query'])['status']!='pending' else None)
    try:
        h.start();schema=Client(h).get('/protocol/schema')[1]
        for tag,record_question,reply,question,expectation in [
            ('context','Did capsule Z reach the collection bay?','Yes','Was capsule Z delivered to the collection bay?','supported'),
            ('negative','Did capsule N reach the collection bay?','No','Was capsule N delivered to the collection bay?','supported'),
            ('control','Did capsule K reach the collection bay?','Yes','Was capsule V delivered to the collection bay?','no_evidence'),
        ]:
            first=publish(record_question,'thread');middle=publish('Message acknowledgement.','thread',first);last=publish(reply,tag,middle);wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
            original=rpc({'op':'query_archive','question':question,'scope':{'information_type':tag}})['query'];original=finish(original,'get_archive_query');assert original['status']=='completed',original['error']
            a=wait(lambda:[v for v in rpc({'op':'list_retrieval_attempts'})['items'] if v['archive_query_id']==original['id']])[0]
            # These authored cases are exposed development/regression evidence;
            # they are deliberately not described as fresh optimizer held-out data.
            label={'expectation':expectation,'support_ids':[] if expectation=='no_evidence' else [first,last],'cohort':'regression' if tag!='context' else 'training','tags':['negation'] if tag=='negative' else [],'note':'Authored independent context/negative development control','confirmed':True}
            admin({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':label},True)
            q=rpc({'op':'replay_retrieval','attempt_id':a['id'],'candidate_recipe':{'context_depth':2}})['query'];q=finish(q,'get_retrieval_replay');ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/ReplayQuery'}).validate(q);assert q['status']=='completed' and q['comparison']['eligible'],q['error']
            assert q['baseline']['metrics']['answer_pass'] and q['candidate']['metrics']['answer_pass'],{b:q[b]['answer'] for b in ['baseline','candidate']}
            if expectation=='supported':
                assert q['comparison']['retrieval_gain_ppm']>0 and q['comparison']['calls_delta']<0 and q['comparison']['bytes_delta']<0
                assert q['baseline']['metrics']['fallback'] and not q['candidate']['metrics']['fallback'];assert reply in [v['value'] for v in q['candidate']['answer']['excerpts']]
            else:assert q['candidate']['metrics']['false_support'] is False and q['candidate']['metrics']['full_scope']
            assert q['policy']['history_evaluator']['policy']['min_confidence_ppm']==500000 and q['policy']['history_evaluator']['policy']['request_bytes']==8192
            (root/(tag+'.json')).write_text(json.dumps(q,indent=2)+'\n');cases.append({'case':tag,'passed':True,'comparison':q['comparison'],'baseline':q['baseline']['metrics'],'candidate':q['candidate']['metrics'],'actual_usage':q['usage'],'evidence':str((root/(tag+'.json')).relative_to(Path.cwd()))});print('PASS live paired',tag,flush=True)
        result={'schema':'adhd/feedback-quality@1','passed':True,'model':cfg['matcher']['model'],'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'assessment_profile':{'history_request_bytes':8192,'min_confidence_ppm':500000},'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
    finally:h.stop()

if __name__=='__main__':main()
