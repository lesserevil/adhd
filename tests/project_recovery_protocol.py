#!/usr/bin/env python3
"""Check combined2.1 exports against reviewed recovery authority and profile2.0."""
import argparse,hashlib,json
from pathlib import Path
import jsonschema
from project_recovery_contract import ROOT,Strict,duplicates,semantic

SPECIAL={'RecoveryConfig':'ProjectRecoveryConfig','RecoveryMergePatch':'ProjectRecoveryMergePatch','AdminCommand':'ProjectRecoveryCommand','AdminResult':'ProjectRecoveryResult'}
def name(value):return SPECIAL.get(value,'ProjectRecovery'+value)
def rename(value):
 if isinstance(value,dict):return {k:('#/$defs/'+name(x.removeprefix('#/$defs/')) if k=='$ref' and isinstance(x,str) and x.startswith('#/$defs/') else rename(x)) for k,x in value.items()}
 if isinstance(value,list):return [rename(x) for x in value]
 return value

def walk(value):
 if isinstance(value,dict):
  yield value
  for x in value.values():yield from walk(x)
 elif isinstance(value,list):
  for x in value:yield from walk(x)

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--schema',type=Path,required=True);p.add_argument('--openapi',type=Path,required=True);p.add_argument('--baseline-schema',type=Path,required=True);p.add_argument('--candidate',type=Path);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
 normative=ROOT/'components/hub/project-recovery/interface.schema.json';norm=json.loads(normative.read_text());schema=json.loads(args.schema.read_text());api=json.loads(args.openapi.read_text());baseline=json.loads(args.baseline_schema.read_text());jsonschema.Draft202012Validator.check_schema(schema)
 assert schema['$id']=='urn:adhd:protocol:2.1' and api['info']['version']=='2.1.0'
 for key,value in norm['$defs'].items():assert schema['$defs'][name(key)]==rename(value),key
 changed=sorted(k for k,v in baseline['$defs'].items() if schema['$defs'].get(k)!=v);assert set(changed)=={'AdminCommand','AdminResult','PublicConfig','MergePatch','Error'},changed
 # Every reference in actual exports resolves; CLI operations never enter Admin.
 for node in walk(schema):
  if '$ref' in node:assert node['$ref'].startswith('#/$defs/') and node['$ref'].removeprefix('#/$defs/') in schema['$defs']
 for node in walk(api):
  if '$ref' in node:assert node['$ref'].startswith('#/components/schemas/') and node['$ref'].removeprefix('#/components/schemas/') in api['components']['schemas']
 admin_refs={x['$ref'] for x in schema['$defs']['AdminCommand']['oneOf']}
 assert all('#/$defs/admin_'+op in admin_refs for op in ('project_restore_plan','project_restore_apply','project_restore_status'))
 assert not any('Rebind' in x or 'rebind' in x for x in admin_refs)
 fixtures=ROOT/'tests/fixtures/project-recovery.json';cases=json.loads(fixtures.read_text())['cases'];checks=[]
 for vector in cases:
  rejected=False
  try:
   value=json.loads(vector['json'],object_pairs_hook=duplicates) if 'json' in vector else vector['value'];Strict({'$ref':'#/$defs/'+name(vector['definition']),'$defs':schema['$defs']},format_checker=jsonschema.FormatChecker()).validate(value);semantic(vector['definition'],value)
  except (jsonschema.ValidationError,AssertionError,ValueError):rejected=True
  assert rejected!=vector['valid'],vector['id'];checks.append({'id':vector['id'],'expected_valid':vector['valid'],'passed':True})
 # OpenAPI components must mirror each named combined JSON Schema definition.
 def api_refs(v):
  if isinstance(v,dict):return {k:x.replace('#/$defs/','#/components/schemas/') if k=='$ref' else api_refs(x) for k,x in v.items()}
  if isinstance(v,list):return [api_refs(x) for x in v]
  return v
 for key,value in schema['$defs'].items():assert api['components']['schemas'][key]==api_refs(value),key
 result={'schema':'adhd/project-recovery-combined-schema-check@1','passed':True,'scope':'Combined schema-only candidate qualification; no running recovery service/backend or authorization claim','normative_schema_sha256':hashlib.sha256(normative.read_bytes()).hexdigest(),'combined_schema_sha256':hashlib.sha256(args.schema.read_bytes()).hexdigest(),'openapi_sha256':hashlib.sha256(args.openapi.read_bytes()).hexdigest(),'baseline_schema_sha256':hashlib.sha256(args.baseline_schema.read_bytes()).hexdigest(),'baseline_artifact_sha256':'7cc2f584c73ac869baf08fed763627361488b3e71aecc82911157f083d6234a9','candidate_sha256':hashlib.sha256(args.candidate.read_bytes()).hexdigest() if args.candidate else None,'definitions_matched':len(norm['$defs']),'legacy_definitions_changed':changed,'legacy_definitions_unchanged':len(baseline['$defs'])-len(changed),'checks':checks,'rebind_is_cli_only':True,'references_resolved':True,'openapi_components_exact':True}
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(checks),'vectors;',len(norm['$defs']),'exactdefinitions;',len(changed),'expectedlegacychanges')
if __name__=='__main__':main()
