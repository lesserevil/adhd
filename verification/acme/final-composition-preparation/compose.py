#!/usr/bin/env python3
"""Stdlib evidence join only. Never runs apps, Docker, CLI or cleanup.

Request pins are explicit. Missing/pending/false requirements prevent --write.
Read-only --check retains a truthful partial readiness report, never a final pass.
"""
import argparse,hashlib,json,os,re,stat
from pathlib import Path
ROOT=Path('/home/horde/src/adhd')
ARTIFACT='ffb14b231c59c44a517e0553d320ffaed7fc2c8ffe1682a19d356f6f82dc6d2a'
IMAGE='sha256:3f82e4c4cefd0ebd539dc7b98f599d12f2d67d71439e9b0c623d44cd6fbd040c'
CONTEXT='c67533217dee5357bf4380fc3d86e9e14b2d1715d4cfd78518a64529859179db'
FAULTS=('issuer-503-timeout','issuer-429-timeout','issuer-floor-manual-edit','issuer-floor-cancel','issuer-floor-cold','issuer-floor-resume','late-domains','hot-disable','parent-loss','client-loss','guardian-loss','bad-challenge','issuer-refusal','untrusted-issuer','real-expiry')
PLATFORM_NAMES=('actual_admitted_runtime_custody','default_disabled_private_http_public_initialization','configured_public_origin_transition_preserves_actual_private_session','real_ca_http01_proof','actual_trusted_hostname_verified_https_and_admin','manual_hot_real_renew_and_exact_receipt_replay_same_vm','scheduled_real_renew_without_manual_submission_same_vm','replacement_new_runtime_same_leaf_account_https','same_private_account_generation_owner_bytes_after_replacement')

def platform_row(row,name):
 assert name in ('compose','kind')and row['platform']==name
 assert row['passed']is True and row['cleanup_errors']==[] and row['scenario']['passed']is True
 checks=row['scenario']['checks']
 assert [item['name']for item in checks]==list(PLATFORM_NAMES),'Exact nine platform predicates/order required'
 assert all(item['passed']is True for item in checks)
 assert re.fullmatch('[0-9a-f]{64}',checks[-1]['private_state_sha256'])
 identities=row['scenario']['runtime_identities'];assert len(identities)==2 and identities[0]!=identities[1]
 for identity in identities:assert identity['image']==IMAGE
 assert row['gateway']['all_threads_closed']is True and row['gateway']['active_sockets']==0
 assert row['relay']['closed']is True

def platform_checks(rows):
 assert [row['platform']for row in rows]==['compose','kind']
 for row in rows:platform_row(row,row['platform'])


def platform_selection(name,plan,result,result_sha):
 assert result['schema']=='adhd/acme-platform-result@1'
 if name=='compose':
  assert result_sha=='4db144cf057c48a222ff098924ed18a88e6a0f6522484a698213211b69838cbf'
  assert result['passed']is False and plan['order']==['compose','kind']
  assert [row['platform']for row in result['platforms']]==['compose','kind']and result['platforms'][1]['passed']is False
  row=result['platforms'][0]
 else:
  assert name=='kind'and result['passed']is True and plan['order']==['kind']and len(result['platforms'])==1
  row=result['platforms'][0]
 platform_row(row,name)
 return row

def body(path):
 p=Path(path).absolute();assert p.resolve(strict=True)==p
 allowed={ROOT/'.worktrees/acme-deploy/_build/acme/platform-image42-12/plan.json',ROOT/'_build/acme/image-build42-01.log',ROOT/'.worktrees/acme-deploy/_build/acme/image42-qualification01/cache22/original-cache.tar'}
 assert p.is_relative_to(ROOT/'verification')or p in allowed
 info=p.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=64*1024*1024
 return p.read_bytes()
def decode(raw):
 def unique(rows):
  out={}
  for key,value in rows:
   assert key not in out,'Duplicate evidence key';out[key]=value
  return out
 return json.loads(raw,object_pairs_hook=unique)
def sha(path):return hashlib.sha256(body(path)).hexdigest()
def read(ref):
 assert isinstance(ref,dict)and set(ref)=={'path','sha256'}
 raw=body(ref['path']);assert hashlib.sha256(raw).hexdigest()==ref['sha256'],'Evidence bytes changed'
 return decode(raw)
def pin(path):return {'path':str(path),'sha256':sha(path)}
def manifest(ref,automatic_browser=False):
 value=read(ref)
 if automatic_browser:
  assert value.get('passed',True)is True and value['automatic_passed']is True,'Browser automatic evidence false'
 else:assert value['passed']is True,'Required positive manifest is false'
 for name,wanted in value.get('files',{}).items():
  assert isinstance(wanted,str)and len(wanted)==64
  path=Path(ref['path']).parent/name
  if not path.exists():
   # These two already-retained binaries/logs remain private, explicitly bound.
   if name=='image-build.log':path=ROOT/'_build/acme/image-build42-01.log'
   elif name=='original-cache.tar':path=ROOT/'.worktrees/acme-deploy/_build/acme/image42-qualification01/cache22/original-cache.tar'
  assert sha(path)==wanted
 return value
def target(value):
 assert value['image_config_identity']==IMAGE and value['artifact_sha256']==ARTIFACT
 assert value['canonical_manifest_sha256']==CONTEXT
 assert value['admission_sha256']=='bde0ac4318642e13d79d1ea65f16a468d97ee74b51037a10934ca8f22d97a4d2'
 assert value['source_admission_sha256']=='e5a577c19bce64c6f1747e31d70fdd76df1cea959670877b739e2d078e1b4c6f'
def phase_ca(plan,report,provenance,kind):
 claimed=plan['ca_manifest_sha256']
 if kind=='foundation':
  argv=plan['program_argv'];assert argv.count('--ca-manifest')==argv.count('--ca-manifest-sha256')==1
  assert argv[argv.index('--ca-manifest-sha256')+1]==claimed
  selected=argv[argv.index('--ca-manifest')+1]
 else:selected=plan['ca_manifest']
 path=Path(selected).absolute()
 assert re.fullmatch(r'/home/horde/src/adhd/_build/acme/image42-plans[0-9]+/inputs/ca-manifest[.]json',str(path))
 assert path.resolve(strict=True)==path and path.stat().st_size<=65536 and not path.is_symlink()
 info=path.lstat();assert stat.S_ISREG(info.st_mode)and info.st_nlink==1
 raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==claimed
 assert plan['files'][str(path)]==claimed
 assert (provenance['actual_ca_manifest_sha256']if kind=='browser'else report['ca_manifest_sha256'])==claimed
 ca=decode(raw);assert ca['ready']is True and ca['real_validation']is True and ca['nonce_validation']is True and ca['public_ca_calls']==0
 for name in ('frontend_root_sha256','issuer_root_sha256'):assert re.fullmatch('[0-9a-f]{64}',ca[name])
 return {'manifest_sha256':claimed,'frontend_root_sha256':ca['frontend_root_sha256'],'issuer_root_sha256':ca['issuer_root_sha256'],'real_http01_validation':True,'nonce_validation':True,'public_ca_calls':0,'scope':'Phase-specific recorded issuer fixture metadata. Historical ready/validation+hash bindings only; no current lease/process liveness inference. Different phase CA generations permitted.'}

def image_case(ref,kind,case=None):
 value=manifest(ref,automatic_browser=kind=='browser');base=Path(ref['path']).parent
 plan=decode(body(base/'plan.json'));result=decode(body(base/'result.json'));report=decode(body(base/'report.json'));audit=decode(body(base/'audit.json'))
 assert result['passed']is True and report['passed']is True
 assert result['cleanup_errors']==[] and report['cleanup_errors']==[]
 assert result['plan_sha256']==sha(base/'plan.json')==audit['plan_sha256']
 assert result['report_sha256']==sha(base/'report.json')==audit['report_sha256']
 assert audit['result_sha256']==sha(base/'result.json') and audit['actual_terminal_exit_code']==0
 assert audit['input_closure_unchanged']is True
 q=audit['qualification'];assert q['structural_passed']is True and q['rejections']==[]
 assert q['resource_audit_performed']is True and q['resource_audit_passed']is True and q['automatic_runtime_qualified']is True
 assert audit['recorded_container_observations'] and all(x['observed_absent']is True for x in audit['recorded_container_observations'])
 assert audit['recorded_pid_start_observations'] and all(x['original_identity_absent']is True for x in audit['recorded_pid_start_observations'])
 target(result['target'])
 checks=report.get('checks',report.get('browser',{}).get('checks',[]))
 assert checks and all(c['passed']is True for c in checks)
 if kind=='fault':
  assert result['case']==report['case']==plan['case']==case
  assert len(checks)==2 and checks[-1]['case']==case
 elif kind=='foundation':assert len(checks)==18
 else:
  assert report['browser']['passed']is True and report['browser_closed']is True and report['playwright_driver_closed']is True
  assert result['host_inputs_unchanged']is True
  assert value['actual_whole_browser_checks']==11 and len(checks)==11
  assert value['check_names']==[row['name']for row in checks]
  assert value['actual_contexts_closed']==['desktop-admin','desktop-developer','desktop-viewer','mobile-admin','mobile-developer','mobile-viewer']
  assert value['private_capture_pairs']==9 and value['browser_input_tree_unchanged']is True
  assert value['actual_image_vms']==1 and value['actual_live_file_checks_per_vm']==76
 return {'manifest':ref,'report_sha256':sha(base/'report.json'),'named_checks':[x.get('name',x.get('case'))for x in checks],
         'scope':kind,'phase_CA':phase_ca(plan,report,value,kind),'baseline_repetitions_count_as_new_contracts':False,'actual_vm_count':q['actual_vm_count']}
def compose_proof(ref,support):
 v=manifest(ref)
 assert v['schema']=='adhd/acme-platform-compose-image42-positive@1'
 assert v['qualified_whole_platforms']==['compose'] and v['actual_parent_exit_code']==1
 assert v['parent_aggregate_passed']is False and v['prior_false_unchanged']is True
 assert v['image']==IMAGE and v['artifact_sha256']==ARTIFACT
 assert v['admission_sha256']=='bde0ac4318642e13d79d1ea65f16a468d97ee74b51037a10934ca8f22d97a4d2'
 assert v['actual_scenario_checks']==9 and v['exact_checks']==list(PLATFORM_NAMES)
 assert v['runtime_identity_count']==2 and v['post_inputs_verified']is True
 assert set(support)=={'negative_review','result','cleanup','plan'}
 negative=read(support['negative_review']);r=read(support['result']);cleanup=read(support['cleanup']);plan=read(support['plan'])
 assert negative['schema']=='adhd/acme-platform-image42-twelfth-negative@1'and negative['passed']is False
 assert negative['authoritative_exit_code']==1 and negative['inputs_unchanged']is True
 assert negative['qualified_whole_platforms']==['compose']and negative['Kind_scenario_unrun']is True
 assert negative['lease_released_and_independently_acquired']is True
 assert v['parent_plan_sha256']==negative['plan_sha256']==support['plan']['sha256']
 assert v['parent_original_result_sha256']==negative['files']['result.json']==support['result']['sha256']
 assert negative['files']['independent-cleanup.json']==support['cleanup']['sha256']
 assert v['strict_cleanup_audit']==str(Path(support['cleanup']['path']).relative_to(ROOT))
 assert r['unrun']==[]and r['cleanup_errors']==[]and r['inputs_unchanged']is True
 assert r['commands']['all_closed']is True and r['relay_lease_released']is True
 t=plan['target'];assert t['image']==IMAGE and t['artifact_sha256']==ARTIFACT
 assert t['admission_sha256']==v['admission_sha256']
 assert t['source_admission_sha256']=='e5a577c19bce64c6f1747e31d70fdd76df1cea959670877b739e2d078e1b4c6f'
 assert plan['bound']['context/manifest.json']==CONTEXT
 assert plan['bound']['admission/source-admission.json']==t['source_admission_sha256']
 assert plan['bound']['admission/manifest.json']==t['admission_sha256']
 row=platform_selection('compose',plan,r,support['result']['sha256'])
 assert decode(body(Path(ref['path']).parent/'compose-row.json'))==row,'Retained whole row differs from original result'
 assert cleanup['passed']is True and cleanup['lease_independently_released']is True
 assert cleanup['CLI_current_absent']==negative['CLI_current_absent']and cleanup['CLI_current_absent']>0
 assert cleanup['checks']and all(x.get('absent')is True or x.get('owned_project_census_empty')is True for x in cleanup['checks'])
 assert {x['kind']for x in cleanup['checks']}=={'container','network','volume'}
 assert len(negative['recorded_app_host_PIDs_absent'])==3
 return {'manifest':ref,'support':support,'platform':'compose','actual_plan_sha256':support['plan']['sha256'],
         'original_aggregate_passed':False,'selected_whole_named_checks':list(PLATFORM_NAMES),
         'scope':'Whole Compose9 only; actual productionUID/default entrypoint, real issuer/manual/scheduled/cold replacement/private-account assertions. Original matrix12 remains false. Independent cleanup and original closed-input/protected-resource audit retained, not rerun here.'}

def collect(request):
 assert request['schema']=='adhd/acme-final-composition-request@1'
 assert list(request['faults'])==list(FAULTS),'Exact unique15 fault order required'
 for ref in request['historical_negatives']:assert read(ref)['passed']is False,'Historical negative changed'
 result={'schema':'adhd/acme-feature-proof-composition@1','passed':False,'pending':[],'evidence':{},'source_artifact_sha256':ARTIFACT,'image':IMAGE,'context_sha256':CONTEXT}
 def checked(name,ref,operation):
  if ref is None:result['pending'].append({'gate':name,'reason':'Missing/pending actual positive binding'});return
  try:result['evidence'][name]=operation(ref)
  except (AssertionError,KeyError,ValueError,TypeError,OSError)as error:result['pending'].append({'gate':name,'reason':'Evidence rejected','type':type(error).__name__})
 def base(name,ref):
  v=manifest(ref)
  if name=='source05':
   assert v['artifact_sha256']==v['raw_assembly_sha256']==ARTIFACT and v['retained_source_file_count']==61
   envelope=decode(body(Path(ref['path']).parent/'rebuild.json'));assert envelope['ok']and envelope['result']['passed']
   assert envelope['result']['test_summary']=={'failed':0,'passed':8,'skipped':0,'total':8}
   oracle=decode(body(Path(ref['path']).parent/'configured-oracle.json'));assert len(oracle['cases'])==114
  elif name=='image':assert v['image_config_identity']==IMAGE and v['artifact_sha256']==ARTIFACT and v['canonical_manifest_sha256']==CONTEXT
  elif name in ('cache22','abi19'):
   assert v['image']==IMAGE and v['artifact_sha256']==ARTIFACT and v['context_sha256']==CONTEXT
   raw=decode(body(Path(ref['path']).parent/'result.json'));assert raw['passed']is True
   rows=raw['results']if name=='cache22'else raw['rows'];assert len(rows)==(22 if name=='cache22'else 19) and all(x['passed']is True for x in rows)
  elif name=='protocol':
   assert v['artifact_sha256']==ARTIFACT and v['wire_execution_exit_code']==0
   w=decode(body(Path(ref['path']).parent/'wire-report.json'));c=decode(body(Path(ref['path']).parent/'conservation26.json'))
   assert w['passed']and len(w['cases'])==8 and all(x['passed']is True for x in w['cases'])
   assert c['passed']and len(c['actual_vectors'])==26 and all(x['passed']is True for x in c['actual_vectors'])and c['unchanged_baseline_definitions']==421
  return {'manifest':ref,'scope':v.get('scope'),'no_other_gate_inferred':True}
 for n in ('source05','image','cache22','abi19','protocol'):checked(n,request['base'][n],lambda ref,n=n:base(n,ref))
 checked('foundation18',request['foundation'],lambda ref:image_case(ref,'foundation'))
 for case,ref in request['faults'].items():checked('fault/'+case,ref,lambda ref,case=case:image_case(ref,'fault',case))
 checked('browser',request['browser'],lambda ref:image_case(ref,'browser'))
 def visual(ref):
  v=manifest(ref);assert v['browser_report_sha256']==result['evidence']['browser']['report_sha256']
  assert v['captures'] and all(x['viewed']is True and x['passed']is True for x in v['captures'])
  browser_path=Path(request['browser']['path']).parent
  browser_audit=decode(body(browser_path/'audit.json'))
  wanted={x['sha256']for x in browser_audit['private_capture_references']if x['kind']=='png'}
  assert len(wanted)==len(v['captures'])==9 and {x['sha256']for x in v['captures']}==wanted
  assert v['hook_report_sha256']==sha(browser_path/'hook-report.json')
  return {'manifest':ref,'scope':'Human/agent actual screenshot inspection only; automatic checks separate'}
 checked('browser_visual',request['browser_visual'],visual)
 def platform(name,ref):
  if name=='compose':return compose_proof(ref,request['compose_support'])
  v=manifest(ref);base=Path(ref['path']).parent;r=decode(body(base/'result.json'));audit=decode(body(base/'audit.json'))
  plan=decode(body(base/'plan.json'));t=plan['target'];assert v['platform']==name
  assert t['image']==IMAGE and t['artifact_sha256']==ARTIFACT and t['admission_sha256']=='bde0ac4318642e13d79d1ea65f16a468d97ee74b51037a10934ca8f22d97a4d2'
  assert t['source_admission_sha256']=='e5a577c19bce64c6f1747e31d70fdd76df1cea959670877b739e2d078e1b4c6f'
  assert r['unrun']==[]and r['cleanup_errors']==[]and r['inputs_unchanged']is True and r['commands']['all_closed']is True and r['relay_lease_released']is True
  row=platform_selection(name,plan,r,sha(base/'result.json'))
  assert audit['passed']is True and audit['input_closure_unchanged']is True and audit['protected_resources_unchanged']is True and audit['owned_resources_absent']is True
  assert audit['plan_sha256']==sha(base/'plan.json')and audit['result_sha256']==sha(base/'result.json')
  return {'manifest':ref,'platform':name,'actual_plan_sha256':sha(base/'plan.json'),'original_aggregate_passed':r['passed'],'selected_whole_named_checks':list(PLATFORM_NAMES),'scope':'Whole selected platform only, all9original predicates+sameprivateaccount/replacement/ownclosure. Compose12 originalaggregate remains false; no singlematrixpassed claim.'}
 assert list(request['platforms'])==['compose','kind']
 for name,ref in request['platforms'].items():checked('platform/'+name,ref,lambda ref,name=name:platform(name,ref))
 if all('platform/'+name in result['evidence']for name in ('compose','kind')):
  assert result['evidence']['platform/compose']['actual_plan_sha256']!=result['evidence']['platform/kind']['actual_plan_sha256']
 result['platform_composition']={'mode':'Two separately observed whole-platform scopes','single_aggregate_matrix_pass_claimed':False,'original_compose12_matrix_remains_false':True,'partial_scenario_prefixes_borrowed':False}
 result['passed']=not result['pending'];result['unique_fault_contracts']=len([n for n in result['evidence']if n.startswith('fault/')])
 result['counting_rule']='15 selected fault predicates only; each repeated baseline is prerequisite evidence, not another distinct fault contract. Local native8/configured114/cache22/ABI19/protocol8/foundation18/platform checks are separate units; no summed aggregate.'
 result['public_CA']={'status':'unrun','qualification_claimed':False,'reason':'No owned public domain/public80/DNS/issuerstaging runtime evidence supplied; isolated realPebble evidence has its ownscope, not publictrust.'}
 result['current_receipt_bridge']={'status':'separate_pending','qualified_here':False,'procedure':'Reviewed final same-source/artifact/context/image bridge; this composition does not issue, update or certify current receipt.'}
 result['historical_negatives_preserved']=request['historical_negatives']
 result['scope']='Feature runtime evidence composition only. No project/roadmap completion, publicCA or finalcurrentreceipt claim. All original false attempts stay false; no disappearance inferred as terminal success.'
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',type=Path,required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--write',type=Path);p.add_argument('--root-go',action='store_true');a=p.parse_args()
 raw=a.request.read_bytes();assert hashlib.sha256(raw).hexdigest()==a.request_sha256
 result=collect(decode(raw));result['request_sha256']=a.request_sha256;result['composition_helper_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 if a.write:
  assert a.root_go and result['passed']is True,'RootGO and all actual required positive evidence mandatory'
  out=a.write.absolute();assert out==ROOT/'verification/acme/final-composition/manifest.json' and not out.exists()and out.parent.resolve(strict=True)==out.parent
  fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'w')as f:json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 print(json.dumps(result,indent=2))
 if not result['passed']:raise SystemExit(3)
if __name__=='__main__':main()
