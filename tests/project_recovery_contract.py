#!/usr/bin/env python3
"""Independent future recovery wire contract checks; no running-app claim."""
import argparse,copy,hashlib,json,re
from pathlib import Path
import jsonschema
from jsonschema import validators

ROOT=Path(__file__).resolve().parents[1]

def byte_bound(validator,limit,value,schema):
 if isinstance(value,str) and len(value.encode('utf-8'))>limit:
  yield jsonschema.ValidationError('UTF8 byte bound exceeded')

Strict=validators.extend(jsonschema.Draft202012Validator,{'x-maxBytes':byte_bound},type_checker=jsonschema.Draft202012Validator.TYPE_CHECKER.redefine('integer',lambda checker,value:type(value) is int))

def canonical(value):
 # Fixtures contain only ASCII keys/strings and safe integers: this is JCS's exact
 # subset, not a claim that Python sort order implements arbitrary Unicode JCS.
 return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def digest(plan):return hashlib.sha256(canonical({k:v for k,v in plan.items() if k!='plan_sha256'})).hexdigest()

def duplicates(pairs):
 result={}
 for k,v in pairs:
  if k in result:raise ValueError('duplicate JSON key')
  result[k]=v
 return result

def semantic(definition,value):
 if definition in ('Plan','Operation','Status'):
  plan=value if definition=='Plan' else value.get('plan') if definition=='Operation' else (value.get('operation') or {}).get('plan')
  if plan:
   assert plan['plan_sha256']==digest(plan)
   assert plan['aliases']==sorted(plan['aliases']) and plan['project_id'] not in plan['aliases']
   assert plan['selected']['route_generation']>plan['target']['route_generation']
   assert plan['selected']['project_epoch']!=plan['selected']['allocation_epoch']
   if plan['selected']['transport_enabled']:
    topic=plan['policy']['topic_prefix']+'.'+hashlib.sha256(plan['server_id'].encode()).hexdigest()[:16]+'.'+hashlib.sha256(plan['project_id'].encode()).hexdigest()[:16]+'.r'+plan['selected']['project_epoch']+'.events.v1'
    assert plan['selected']['topic']==topic
 if definition=='Operation':
  if value['plan']:
   assert value['project_id']==value['plan']['project_id']
   if value['kind']=='plan':assert value['operation_id']==value['plan']['plan_id']
  p=value['progress'];assert p['bytes_read']<=p['maximum_bytes'] and p['records_checked']<=p['maximum_records']
  if value['result']:
   result=value['result'];plan=value['plan'];assert result['project_id']==plan['project_id']
   for key in ('route_generation','project_epoch','allocation_epoch','topic'):assert result[key]==plan['selected'][key]
   assert result['initialized']==(plan['mode']=='initialize')
  if value['failure']:
   reasons=[x['reason'] for x in value['failure']['conflicts']];assert len(reasons)==len(set(reasons)) and reasons==sorted(reasons)
 if definition=='Status' and value['operation']:
  assert value['project_id']==value['operation']['project_id'];semantic('Operation',value['operation'])
 if definition in ('RebindRequest','RebindCLI'):
  request=value[1] if definition=='RebindCLI' else value
  ids=[x['project_id'] for x in request['stores']];paths=[x['store_path'] for x in request['stores']]
  assert len(ids)==len(set(ids)) and len(paths)==len(set(paths))
 if definition=='BackupManifest':assert value['aliases']==sorted(value['aliases']) and value['project_id'] not in value['aliases']

def main():
 parser=argparse.ArgumentParser(__doc__);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
 schema_file=ROOT/'components/hub/project-recovery/interface.schema.json';schema=json.loads(schema_file.read_text());jsonschema.Draft202012Validator.check_schema(schema)
 vectors=json.loads((ROOT/'tests/fixtures/project-recovery.json').read_text());out=[]
 for vector in vectors['cases']:
  caught=False
  try:
   value=json.loads(vector['json'],object_pairs_hook=duplicates) if 'json' in vector else vector['value']
   Strict({'$ref':'#/$defs/'+vector['definition'],'$defs':schema['$defs']},format_checker=jsonschema.FormatChecker()).validate(value)
   semantic(vector['definition'],value)
  except (jsonschema.ValidationError,AssertionError,ValueError):caught=True
  assert caught != vector['valid'],vector['id']
  out.append({'id':vector['id'],'expected_valid':vector['valid'],'passed':True})
 examples=re.findall(r'```json\n(.*?)\n```',(schema_file.parent/'interface.md').read_text(),re.S)
 for example in examples:Strict(schema,format_checker=jsonschema.FormatChecker()).validate(json.loads(example,object_pairs_hook=duplicates))
 result={'schema':'adhd/project-recovery-contract-check@1','passed':True,'scope':'Future normative schema/fixtures only, not runtime implementation or authorization qualification','schema_sha256':hashlib.sha256(schema_file.read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256((ROOT/'tests/fixtures/project-recovery.json').read_bytes()).hexdigest(),'checks':out,'examples_validated':len(examples),'definitions':len(schema['$defs'])}
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(out),'vectors;',len(examples),'examples')

if __name__=='__main__':main()
