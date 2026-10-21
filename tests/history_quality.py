#!/usr/bin/env python3
"""Independently labeled source-backed history questions against the real evaluator."""
import argparse,hashlib,json,secrets,subprocess,tempfile,time
from pathlib import Path
import jsonschema
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator

# Development fixtures include the published bird requirements. Held-out cases
# use different statements/domains and were authored before their first app run.
DEVELOPMENT=[('contextual-yes', 'Was a bird observed in the courtyard?', [{'id': 'a', 'text': 'Yes', 'context': {'question': 'Was a bird observed in the courtyard?', 'subject': 'courtyard'}}], 'direct', 'quote_0'), ('explicit-negative', 'Was a bird observed in the courtyard?', [{'id': 'a', 'text': 'No bird was observed in the courtyard.'}], 'direct', 'quote_0'), ('species', 'What species was explicitly reported?', [{'id': 'a', 'text': 'I observed a sparrow beside the fountain.'}], 'direct', 'quote_0'), ('no-count', 'How many distinct cameras were installed?', [{'id': 'a', 'text': 'A camera was installed at the gate.', 'context': {'subject': 'gate'}}, {'id': 'b', 'text': 'The gate camera was visible this afternoon.', 'context': {'subject': 'gate'}}], 'insufficient', 'unknown'), ('correction', 'Was a bird or a leaf reported at location A?', [{'id': 'a', 'text': 'A bird was present at location A.', 'context': {'subject': 'location-A'}}, {'id': 'b', 'text': 'Correction: it was a leaf, not a bird.', 'context': {'subject': 'location-A', 'links': [{'relation': 'corrects', 'publication_id': 'a'}]}}], 'conflicting', 'conflict'), ('joint-build', 'Which test ran on the deployed build?', [{'id': 'a', 'text': 'Build zeta passed integration test J.', 'context': {'conversation': 'deployment-zeta'}}, {'id': 'b', 'text': 'Build zeta is the build deployed in production.', 'context': {'conversation': 'deployment-zeta'}}], 'direct', None), ('absent-detail', 'What temperature was explicitly measured?', [{'id': 'a', 'text': 'The room felt warm.'}], 'insufficient', 'unknown'), ('different-referents', 'Was the warehouse gate open?', [{'id': 'a', 'text': 'The office gate was open.', 'context': {'subject': 'office-gate'}}], 'insufficient', 'unknown'), ('ambiguous-count', 'How many distinct birds were observed in tree-1?', [{'id': 'a', 'text': 'Yes', 'context': {'question': 'Is there a bird in tree-1?', 'subject': 'tree-1'}}, {'id': 'b', 'text': 'I see a cardinal in that tree.', 'context': {'subject': 'tree-1'}}, {'id': 'c', 'text': 'There is a red bird on the branch.', 'context': {'subject': 'tree-1'}}], 'insufficient', 'unknown'), ('explicit-count', 'How many distinct birds were observed in tree-1?', [{'id': 'a', 'text': 'There were two distinct birds in tree-1, tagged A and B.'}], 'direct', 'quote_0'), ('explicit-color', 'What color was explicitly reported for the bird?', [{'id': 'a', 'text': 'I see a cardinal in that tree.', 'context': {'subject': 'tree-1'}}, {'id': 'b', 'text': 'There is a red bird on the branch.', 'context': {'subject': 'tree-1'}}], 'direct', 'quote_1'), ('implicit-color', 'What color was explicitly reported for the bird?', [{'id': 'a', 'text': 'I see a cardinal in that tree.', 'context': {'subject': 'tree-1'}}], 'insufficient', 'unknown'), ('arbitrary-data', 'Which artifact was explicitly marked ready?', [{'id': 'a', 'data': {'artifact': {'name': 'gamma-7', 'state': 'ready'}}}], 'direct', 'quote_0')]

HELD_OUT=[('held-no', 'Were errors reported during the monitoring window?', [{'id': 'a', 'text': 'No', 'context': {'question': 'Did the monitoring window contain errors?', 'subject': 'window-A'}}], 'direct', 'quote_0'), ('held-count', 'How many distinct parcels arrived at dock D?', [{'id': 'a', 'text': 'Exactly three distinct parcels, barcodes A1, A2 and A3, arrived at dock D.'}], 'direct', 'quote_0'), ('held-numeric-detail', 'What numeric temperature was explicitly measured for the coolant?', [{'id': 'a', 'text': 'The coolant felt cool.'}], 'insufficient', 'unknown'), ('held-mutual-claims', 'What state was reported for the gate at observation T?', [{'id': 'a', 'text': 'At observation T, the gate was open.', 'context': {'subject': 'gate-at-T'}}, {'id': 'b', 'text': 'At observation T, the gate was closed.', 'context': {'subject': 'gate-at-T'}}], 'conflicting', 'conflict'), ('held-joint', 'Which ticket belongs to the approved milestone?', [{'id': 'a', 'text': 'Ticket Q belongs to milestone M.', 'context': {'conversation': 'milestone-review'}}, {'id': 'b', 'text': 'Milestone M was approved.', 'context': {'conversation': 'milestone-review', 'links': [{'relation': 'related', 'publication_id': 'a'}]}}], 'direct', None), ('held-data', 'Which experiment was explicitly reported as passed?', [{'id': 'a', 'data': {'experiment': {'id': 'run-kappa', 'outcome': 'passed'}}}], 'direct', 'quote_0'), ('held-absent-referent', 'What color was reported for the west gate?', [{'id': 'a', 'text': 'The north gate was closed.'}], 'insufficient', 'unknown'), ('held-compatible-detail', 'What color was explicitly reported for a vehicle beside the crate?', [{'id': 'a', 'text': 'A rover is beside the crate.', 'context': {'subject': 'crate-area'}}, {'id': 'b', 'text': 'A blue vehicle is beside the crate.', 'context': {'subject': 'crate-area'}}], 'direct', 'quote_1'), ('held-uncertain-count', 'How many distinct vehicles were observed near the barrier?', [{'id': 'a', 'text': 'I saw a vehicle near the barrier.', 'context': {'subject': 'barrier'}}, {'id': 'b', 'text': 'A green vehicle appeared near the barrier.', 'context': {'subject': 'barrier'}}], 'insufficient', 'unknown')]

def main():
    p=argparse.ArgumentParser(description=__doc__);r=p.add_mutually_exclusive_group(required=True);r.add_argument('--command');r.add_argument('--image')
    p.add_argument('--matcher-url',default='http://127.0.0.1:18770/v1/systemone');p.add_argument('--model',default='Nemotron-Deciffusion-8B-v2.1');p.add_argument('--cohort',choices=['all','development','held-out'],default='all');p.add_argument('--report',default='verification/history-quality.json');args=p.parse_args()
    command=json.loads(args.command) if args.command else [];parent=Path('_build/roadmap/history-quality').resolve();parent.mkdir(parents=True,exist_ok=True);results=[]
    selected=([('development',case) for case in DEVELOPMENT] if args.cohort!='held-out' else [])+([('held-out',case) for case in HELD_OUT] if args.cohort!='development' else [])
    for cohort,(name,question,records,expected,answer_expected) in selected:
        root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image)
        h.file.write_text(json.dumps({'project_id':'quality-fixture','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':args.matcher_url,'model':args.model}}));h.file.chmod(0o600)
        try:
            h.start();client=Client(h);schema=client.get('/protocol/schema')[1]
            def valid(key,value):ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+key},format_checker=jsonschema.FormatChecker()).validate(value)
            def rpc(value):return client.rpc(value,h.config['agents']['alice'])
            ids={}
            for record in records:
                body={'op':'publish_record',**{k:v for k,v in record.items() if k in ['text','data','context','occurred_at','source']}}
                if 'context' in body:
                    body['context']=json.loads(json.dumps(body['context']))
                    for link in body['context'].get('links',[]):link['publication_id']=ids[link['publication_id']]
                reply=rpc(body);ids[record['id']]=reply['record']['publication']['id']
            q=rpc({'op':'query_history','question':question})['query'];end=time.monotonic()+35
            while time.monotonic()<end:
                q=rpc({'op':'get_history_query','query_id':q['id']})['query'];valid('HistoryQuery',q)
                if q['status']!='pending':break
                time.sleep(.1)
            assert q['status']=='completed',(name,q['error'],q['coverage'])
            target={'insufficient','no_evidence'} if answer_expected=='unknown' else {expected}
            assert q['outcome'] in target,(name,q['outcome'],q['answer'])
            assert q['coverage']['primary_complete'] and q['coverage']['final_complete'] and q['coverage']['remaining']==0
            if answer_expected is not None:assert q['answer']['selection']==answer_expected,(name,q['answer'])
            if answer_expected=='unknown':assert not q['answer']['support_ids'] and not q['answer']['excerpts']
            else:
                assert set(q['answer']['support_ids'])==set(ids.values()),(name,q['answer'])
                for excerpt in q['answer']['excerpts']:
                    original=next(x for x in records if ids[x['id']]==excerpt['publication_id'])
                    if excerpt['field']=='text':assert excerpt['value']==original['text']
                    else:assert json.loads(excerpt['value'])==original['data']
            for evaluation in q['evaluations']:
                valid('HistoryEvaluation',evaluation)
                valid('HistoryModelExchange',{'request':evaluation['request'],'response':{'model':evaluation['request']['model'],'answers':evaluation['answers']}})
                assert hashlib.sha256(evaluation['request_json'].encode()).hexdigest()==evaluation['request_sha256']
            result={'case':name,'cohort':cohort,'passed':True,'outcome':q['outcome'],'selection':q['answer']['selection'],'calls':q['usage']['calls'],'bytes':q['usage']['bytes'],'time_ms':q['usage']['time_ms'],'citations':q['answer']['support_ids']}
            results.append(result);print('PASS',json.dumps(result),flush=True)
        finally:h.stop()
    binding=({'image_id':subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()} if args.image else {'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()})
    Path(args.report).write_text(json.dumps({'schema':'adhd/history-quality@1','passed':True,'model':args.model,'cohort':args.cohort,'cases':results,**binding},indent=2)+'\n')

if __name__=='__main__':main()
