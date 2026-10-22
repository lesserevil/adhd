import concurrent.futures,hashlib,importlib.util,json,pathlib,sys
sys.dont_write_bytecode=True
D=pathlib.Path('/home/horde/src/adhd/.worktrees/deployment');W=D/'_build/ui41-focused01'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=module('ui41_actual_frozen_review',W/'run.py');p=load(W/'plan.json');r=load(W/'matrix.json');assert m.verify(p,W);assert r['passed'] and r['frozen_inputs_unchanged'] and not r['failure_type'] and r['unrun_suites']==[]
assert p['planned_suites']==['admin','eventing','recovery'] and p['expected_units']==32 and [x['suite'] for x in r['rows']]==p['planned_suites']
rt=module('ui41_actual_runtime_readonly',W/'frozen/tests/image_ui_runtime.py');assert r['plan_sha256']==sha(W/'plan.json') and r['driver_sha256']==sha(W/'run.py')
ids=set();names=set();processes={};vms={};observation_count=0;screenshots={};suites=[]
for job,row in zip(p['jobs'],r['rows']):
 name=job['name'];c=load(W/(name+'-custody.json'));report=load(W/(name+'.json'));ledger=load(W/(name+'-launches.json'))
 assert row['exit_code']==0 and row['passed'] and report['passed'] and m.unit_count(report,name)==job['expected_units']==row['units'];assert sha(W/(name+'.json'))==row['report_sha256'] and sha(W/(name+'-custody.json'))==row['custody_sha256'] and sha(W/(name+'.log'))==row['log_sha256']
 assert c['passed'] and not c['original_exception'] and not c['cleanup_failure'] and c['cleanup_error_types']==[];assert c['image_config_identity']==p['image_config_identity'] and c['artifact_sha256']==p['artifact_sha256'] and c['canonical_manifest_sha256']==p['canonical_manifest_sha256']
 assert not row['independent_cleanup']['errors'] and not row['independent_cleanup']['fallback_mutation']
 for x in ledger['launches']:
  names.add(x['name'])
  if x.get('container_id'):ids.add(x['container_id'])
 for obs in c['actual_vm_observations']:
  observation_count+=1;assert obs['image_config_identity']==p['image_config_identity'] and obs['canonical_manifest_sha256']==p['canonical_manifest_sha256'] and obs['namespace_vm_pid']==1 and obs['actual_app_files']==59
  cache=obs['compiled_cache'];assert cache['modules']==59 and cache['cache_and_toolchain_files_verified']==67 and cache['same_actual_VM'] and cache['entrypoint']==['elixir','/runtime/adhd/boot.exs','/app/hub.exs']
  assert cache['manifest_sha256']==sha(W/'cache-manifest.json');assert not pathlib.Path('/proc/'+str(obs['host_vm_pid'])).exists();vms[obs['container_id']]=obs;ids.add(obs['container_id']);names.add(obs['owned_name'])
 for proc in row['independent_cleanup']['processes']:
  assert proc['same_owned_process_not_live'] and not rt.same(proc);processes[(proc['pid'],proc['starttime'])]=proc
 current=row['new_screenshots_and_ARIA'];assert current and any('desktop' in x for x in current) and any('mobile' in x for x in current)
 for key,v in current.items():
  image=pathlib.Path(key);assert image.is_relative_to(W/'runtime') and not image.is_symlink() and not image.with_suffix('.txt').is_symlink();assert sha(image)==v['png_sha256'] and sha(image.with_suffix('.txt'))==v['aria_sha256'] and image.stat().st_size==v['bytes'];assert image.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n';screenshots[key]=v
 suites.append({'suite':name,'units':row['units'],'report_sha256':row['report_sha256'],'custody_sha256':row['custody_sha256'],'launches_sha256':sha(W/(name+'-launches.json')),'log_sha256':row['log_sha256'],'exit_code':0,'screenshot_pairs':len(current)})
sys.path.insert(0,str(W/'frozen/tests'));from container_fixture import OwnedImage
import subprocess
def absent(key):
 cp=subprocess.run(['/usr/bin/docker','inspect',key],capture_output=True,timeout=30);assert OwnedImage.probe_absence(cp,key);return {'key':key,'strict_current_absence':True,'returncode':cp.returncode}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:absence=list(pool.map(absent,sorted(ids|names)))
assert m.captures(W/'runtime')==screenshots;assert m.verify(p,W)
out=D/'verification/ownedMULTI008/source41-focused-ui-positive';out.mkdir(exist_ok=False)
for n in ['matrix.json']+[a+b for a in p['planned_suites'] for b in ['.json','-custody.json','-launches.json']]:(out/n).write_bytes((W/n).read_bytes())
a={'schema':'adhd/source41-focused-ui-independent-audit@1','passed':True,'scope':'Complete originalAdmin18/Events12/project-recovery2 against exact admitted source41 compiledimage. No new9/86/OpenRig/unchosenprogram or release claim.','image_config_identity':p['image_config_identity'],'artifact_sha256':p['artifact_sha256'],'plan_sha256':sha(W/'plan.json'),'driver_sha256':sha(W/'run.py'),'matrix_sha256':sha(W/'matrix.json'),'authoritative_root_process_exit':{'handle':'54757','exit_code':0,'source':'Root confirmation; agent did not poll handle.'},'frozen_full_set_hash_aliases_external_tools_bound_verified_before_after':True,'frozen_files':len(p['frozen_inputs']),'externals':len(p['externals']),'tool_roots':len(p['tool_roots']),'bound_inputs':len(p['bound_inputs']),'whole_programs':3,'whole_units':32,'suites':suites,'actual_vms':len(vms),'actual_vm_observations':observation_count,'actual_app_files_per_vm':59,'actual_compiled_cache_toolchain_files_verified_per_observation':67,'strict_current_known_id_count':len(ids),'strict_current_issued_name_count':len(names),'independent_absence':absence,'recorded_process_identities_not_live':len(processes),'recorded_process_identity_method':'PID/starttime comparison, zombie excluded, using unchanged frozen readonly runtime.same; no signals/cleanup from auditor.','png_aria_pairs':len(screenshots),'captures':screenshots,'visual_review':'Parent root performs independent screenshot review; this audit checks actualPNG+ARIA identity and complete selected capture set, not aesthetic approval. Bind root manual review separately.','no_fallback_cleanup_or_mutations_by_audit':True,'provider_calls':0,'tool_closure_scope':p['tool_closure_scope']}
(out/'audit.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({'audit_sha256':sha(out/'audit.json'),'actual_vms':len(vms),'observations':observation_count,'ids':len(ids),'names':len(names),'processes':len(processes),'captures':len(screenshots)}))
