#!/usr/bin/env python3
"""Real configured-model usefulness and bounded retrieval quality; labels are independent."""
import argparse,sys,json,tempfile,time,hashlib,math
from pathlib import Path
sys.path.insert(0,str(Path('tests').resolve()))
from federation_acceptance import Hub,request
from protocol_acceptance import ByteValidator
import jsonschema
p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--command');m.add_argument('--image');p.add_argument('--matcher-url',default='http://127.0.0.1:18770/v1/systemone');p.add_argument('--report',default='verification/retrieval-quality.json');args=p.parse_args();command=json.loads(args.command) if args.command else [];Hub.image=args.image
parent=Path('_build/roadmap/retrieval-quality').resolve();parent.mkdir(parents=True,exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Hub(command,root/'hub','retrieval-quality',args.matcher_url);h.config.pop('federation');rows=[]
def wait(fn):
 end=time.monotonic()+25
 while time.monotonic()<end:
  value=fn()
  if value:return value
  time.sleep(.05)
 raise AssertionError('Quality query deadline')
try:
 h.start();schema=request(h.base,'/protocol/schema')[1];jsonschema.Draft202012Validator.check_schema(schema)
 def valid(name,value):ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker()).validate(value)
 h.call({'op':'send','recipient_id':'bob','text':'PRIVATE_RETRIEVAL_SENTINEL: Replacing the failed switch restored network service.'})
 cases=json.loads('[{"case": "paraphrase", "cohort": "development", "question": "How did the service resume operation?", "record": {"text": "Restarting the daemon restored availability."}, "expected": true}, {"case": "exact-id", "cohort": "development", "question": "Which result was recorded for BUILD-x9?", "record": {"text": "BUILD-x9 passed its integration suite."}, "expected": true}, {"case": "context-yes", "cohort": "development", "question": "Was sample K delivered?", "record": {"text": "Yes", "context": {"question": "Did sample K reach the laboratory?"}}, "expected": true}, {"case": "negation-candidate", "cohort": "development", "question": "Did the north gate open?", "record": {"text": "The north gate did not open."}, "expected": true}, {"case": "joint-fragment", "cohort": "development", "question": "Which ticket belongs to the approved milestone?", "record": {"text": "Ticket Q belongs to milestone M.", "context": {"conversation": "milestone-review"}}, "expected": true}, {"case": "irrelevant", "cohort": "development", "question": "How did the service resume operation?", "record": {"text": "The cafeteria served soup today."}, "expected": false}, {"case": "wrong-identifier", "cohort": "development", "question": "Which result was recorded for BUILD-x9?", "record": {"text": "BUILD-y8 passed its integration suite."}, "expected": false}, {"case": "data", "cohort": "development", "question": "Which experiment succeeded?", "record": {"data": {"experiment": {"id": "run-omega", "outcome": "passed"}}}, "expected": true}, {"case": "held-paraphrase", "cohort": "held-out", "question": "What restored network service?", "record": {"text": "Replacing the failed switch brought connectivity back."}, "expected": true}, {"case": "held-explicit-id", "cohort": "held-out", "question": "Who approved mission LM-42?", "record": {"text": "Mission LM-43 was approved by the duty officer."}, "expected": false}, {"case": "held-context-no", "cohort": "held-out", "question": "Was the launch cancelled?", "record": {"text": "No", "context": {"question": "Was the launch cancelled?", "subject": "launch-L"}}, "expected": true}, {"case": "held-correction", "cohort": "held-out", "question": "Which team owns package K?", "record": {"text": "Correction: package K belongs to team B rather than team A.", "context": {"subject": "package-K"}}, "expected": true}, {"case": "held-repeated-count", "cohort": "held-out", "question": "How many distinct vehicles were observed?", "record": {"text": "A vehicle appeared beside the barrier.", "context": {"subject": "barrier"}}, "expected": true}, {"case": "held-irrelevant", "cohort": "held-out", "question": "What restored network service?", "record": {"text": "The garden received rainfall yesterday."}, "expected": false}, {"case": "held-unicode-id", "cohort": "held-out", "question": "What happened to BUILD-κ7?", "record": {"text": "BUILD-κ7 completed its smoke tests."}, "expected": true}, {"case": "held-structured", "cohort": "held-out", "question": "Which sample was damaged?", "record": {"data": {"inspection": {"sample": "specimen-P", "finding": "fractured"}}}, "expected": true}, {"case": "held-negation", "cohort": "held-out", "question": "Was sample Q approved?", "record": {"text": "Sample Q was not approved."}, "expected": true}]')
 for i,case in enumerate(cases):
  cohort=case['cohort'];source=case['record'];question=case['question'];kind='quality-'+str(i)
  body={'op':'publish_record','information_type':kind,**source}
  publication=h.call(body)['record']['publication'];pid=publication['id']
  wait(lambda:(v if (v:=h.call({'op':'retrieval_index'})['index'])['status']=='ready' else None))
  initial=h.call({'op':'retrieve','question':question,'scope':{'information_type':kind}})['query']
  q=wait(lambda:(v if (v:=h.call({'op':'get_retrieval','query_id':initial['id']})['query'])['status']!='pending' else None))
  valid('RetrievalQuery',q);assert q['status']=='completed',q['error'];assert q['coverage']['total']==1 and q['coverage']['semantic_examined']==1
  assert q['coverage']['exhaustive'] is False and len(q['evaluations'])==1
  evaluation=q['evaluations'][0];valid('RetrievalEvaluation',evaluation)
  assert json.loads(evaluation['request_json'])==evaluation['request'] and hashlib.sha256(evaluation['request_json'].encode()).hexdigest()==evaluation['request_sha256']
  assert evaluation['response']['model']==evaluation['request']['model'] and set(evaluation['response']['answers'])=={'useful'}
  score=evaluation['response']['answers']['useful'];assert score['type']=='noul' and not isinstance(score['noul'],bool) and math.isfinite(score['noul']) and 0<=score['noul']<=1
  assert (score['noul']>=.5)==case['expected'],(case['case'],case['expected'],score)
  assert 'PRIVATE_RETRIEVAL_SENTINEL' not in json.dumps(q)
  assert evaluation['request']['state']['candidate']['fragments']==[{k:f[k] for k in ['origin_publication_id','field','text']} for f in evaluation['fragments']]
  for fragment in evaluation['fragments']:
   valid('RetrievalFragment',fragment);assert fragment['origin_publication_id']==pid
   assert fragment['sha256']==hashlib.sha256(fragment['text'].encode()).hexdigest() and fragment['end']-fragment['start']==len(fragment['text'].encode())
   origin=h.call({'op':'get_record','publication_id':fragment['origin_publication_id']})['record'];p=origin['publication'];ctx=origin['context'] or {};field=fragment['field']
   if field=='data':value=json.dumps(p['data'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
   elif field.startswith('context.'):value=ctx[field.split('.')[1]]
   elif field.startswith('source.'):value=p['source'][field.split('.')[1]]
   else:value=p[field]
   assert value.encode()[fragment['start']:fragment['end']].decode()==fragment['text']
  if case['expected']:assert any(x['publication_id']==pid for x in q['candidates'])
  value={'case':case['case'],'cohort':cohort,'expected_useful':case['expected'],'probability':score['noul'],'passed':True,'candidates':len(q['candidates']),'calls':q['usage']['calls'],'bytes':q['usage']['bytes'],'time_ms':q['usage']['time_ms']};rows.append(value);print('PASS',json.dumps(value),flush=True)
 # Mixed candidate pools are retrieval checks, distinct from single-candidate
 # usefulness classification above. Labels never depend on the hub's scores.
 ranking_cases=[
  ('rank-paraphrase','What restored network service?','Replacing the failed switch brought connectivity back.','Network service maintenance will be discussed at the cafeteria.'),
  ('rank-identifier','Which result was recorded for BUILD-x9?','BUILD-x9 passed its integration suite.','BUILD-y8 passed its integration suite.'),
  ('rank-negation','Did the north gate open?','The north gate did not open.','The south gate did open.')]
 for i,(name,question,target,distractor) in enumerate(ranking_cases):
  kind='rank-'+str(i)
  good=h.call({'op':'publish_record','text':target,'information_type':kind})['record']['publication']['id']
  bad=h.call({'op':'publish_record','text':distractor,'information_type':kind})['record']['publication']['id']
  wait(lambda:(v if (v:=h.call({'op':'retrieval_index'})['index'])['status']=='ready' else None))
  q=h.call({'op':'retrieve','question':question,'scope':{'information_type':kind},'limit':1})['query']
  q=wait(lambda:(v if (v:=h.call({'op':'get_retrieval','query_id':q['id']})['query'])['status']!='pending' else None))
  valid('RetrievalQuery',q);assert q['status']=='completed' and q['coverage']['semantic_examined']==2
  assert [c['publication_id'] for c in q['candidates']]==[good],(name,q['candidates'])
  probabilities={e['publication_id']:e['response']['answers']['useful']['noul'] for e in q['evaluations']}
  assert probabilities[good]>=.5 and probabilities[bad]<.5,(name,probabilities)
  value={'case':name,'cohort':'retrieval-ranking','passed':True,'calls':q['usage']['calls'],'bytes':q['usage']['bytes'],'time_ms':q['usage']['time_ms']};rows.append(value);print('PASS',json.dumps(value),flush=True)
 # Bare Yes must be interpreted with its actual linked public question.
 question='Did probe Z reach the laboratory?'
 parent=h.call({'op':'publish_record','text':question,'information_type':'linked-question'})['record']['publication']['id']
 child=h.call({'op':'publish_record','text':'Yes','information_type':'linked-answer','context':{'links':[{'relation':'reply','publication_id':parent}]}})['record']['publication']['id']
 wait(lambda:(v if (v:=h.call({'op':'retrieval_index'})['index'])['status']=='ready' else None))
 q=h.call({'op':'retrieve','question':'Was probe Z delivered?','scope':{'information_type':'linked-answer'}})['query']
 q=wait(lambda:(v if (v:=h.call({'op':'get_retrieval','query_id':q['id']})['query'])['status']!='pending' else None))
 valid('RetrievalQuery',q);assert q['status']=='completed' and q['candidates'][0]['publication_id']==child and parent in q['coverage']['expanded_ids']
 assert q['evaluations'][0]['response']['answers']['useful']['noul']>=.5
 assert any(f['origin_publication_id']==parent and f['text']==question for f in q['evaluations'][0]['fragments'])
 value={'case':'linked-original-question-with-bare-yes','cohort':'retrieval-context','passed':True,'calls':q['usage']['calls'],'bytes':q['usage']['bytes'],'time_ms':q['usage']['time_ms']};rows.append(value);print('PASS',json.dumps(value),flush=True)
 report={'passed':True,'command':command,'image':args.image,'cases':rows,'scope':'Bounded relevance and candidate ranking; no truth or exhaustiveness claim.'}
 if command and Path(command[-1]).is_file():report['artifact_sha256']=hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()
 Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
finally:h.stop()
