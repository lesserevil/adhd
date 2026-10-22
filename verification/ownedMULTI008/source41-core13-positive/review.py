import concurrent.futures,hashlib,importlib.util,json,pathlib,subprocess,sys
sys.dont_write_bytecode=True
R=pathlib.Path('/home/horde/src/adhd');D=R/'.worktrees/deployment';C=R/'_build/core41-compiled03';G=R/'_build/core41-compiled-guard03'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=module('core_guard_actual_readonly',G/'guard.py');gp=load(G/'plan.json');assert v.verify(G,gp);p=load(C/'plan.json');matrix=load(C/'matrix.json');guard=load(G/'result.json')
assert guard['passed'] and guard['exit_code']==0 and guard['core_matrix_sha256']==sha(C/'matrix.json') and guard['plan_sha256']==sha(G/'plan.json');assert matrix['passed'] and matrix['frozen_inputs_unchanged'] and not matrix['unrun_suites'] and matrix['plan_sha256']==sha(C/'plan.json');assert len(matrix['results'])==13
sys.path.insert(0,str(C/'frozen/tests'));core=module('core_actual_driver_pure',C/'driver.py');assert core.reviewed_plan(C,sha(C/'plan.json'),C/'driver.py')==p
from image_qualification_inputs import verify_frozen_inputs
verify_frozen_inputs(C/'frozen',p['frozen_inputs'])
for name,digest in p['bound_inputs'].items():assert sha(C/name)==digest
for name,digest in p['locked_specifications'].items():assert sha(C/'frozen/components/hub'/name)==digest
assert len(p['locked_specifications'])==33 and sha(pathlib.Path(p['legacy_hub']))==p['legacy_sha256']
ids=set();names=set();hostpids=set();reports=[];runtime_count=0;probe_count=0

def inspect_runtime(runtime):
 global runtime_count,probe_count
 runtime_count+=1;assert runtime['kind']=='docker' and runtime['image_config_identity']==p['image_config_identity'] and runtime['artifact_sha256']==p['artifact_sha256'] and runtime['canonical_manifest_sha256']==p['canonical_manifest_sha256'];assert runtime['payload_verified'] is True and not runtime.get('probe_cleanup_blocked',False) and not runtime.get('cleanup_blocked',False)
 events=runtime.get('container_lifecycle',[]);started={x['container_id'] for x in events if x['action']=='started'};closed={x['container_id'] for x in events if x['action'] in ('hard-killed','stopped') and x.get('observed_absent')};assert started<=closed;ids.update(started)
 for probe in runtime.get('payload_probe_lifecycle',[]):
  probe_count+=1;assert probe['image_config_identity']==p['image_config_identity'] and probe['run_exit_code']==0 and probe['observed_absent'] and not probe['cleanup_failure_types'] and not probe['run_failure_type'] and not probe['foreign_object_not_removed'];names.add(probe['owned_name'])
  if probe.get('container_id'):ids.add(probe['container_id'])
 for obs in runtime.get('model_export_isolation',[]):
  assert obs['image_config_identity']==p['image_config_identity'] and obs['network_mode']=='bridge' and obs['provider_exports']==0 and obs['model_endpoints_refused_inside_namespace']==obs['effective_current_model_endpoints'];hostpids.add(obs['host_vm_pid'])

def find_runtimes(value):
 if isinstance(value,dict):
  if value.get('kind')=='docker' and 'container_lifecycle' in value:inspect_runtime(value)
  else:
   for x in value.values():find_runtimes(x)
 elif isinstance(value,list):
  for x in value:find_runtimes(x)

for job,row in zip(p['jobs'],matrix['results']):
 name=job['name'];assert row['name']==name and row['exit_code']==row['process_exit_code']==0 and row['report_passed'] is True
 path=C/row['report'];log=C/(name+'.log');report=load(path);assert core.report_passed(path);assert sha(path)==row['report_sha256'] and sha(log)==row['log_sha256']
 key='cases' if name in ('foundation','wire','auth') else 'checks';checks=report[key];assert checks and all(x['passed'] for x in checks)
 if 'artifact_sha256' in report:assert report['artifact_sha256']==p['artifact_sha256']
 for k in ['image_id','image']:
  if k in report:assert report[k]==p['image_config_identity']
 find_runtimes(report)
 reports.append({'suite':name,'reported_check_key':key,'checks':len(checks),'report_sha256':sha(path),'log_sha256':sha(log),'process_exit_code':0})
 if name=='workflow-upgrade':
  fence=report['provider_export_fence'];assert fence['denied_port']==18770 and fence['blocked_connects_including_probe']>=1 and fence['provider_exports']==0 and all(x['fence_loaded'] for x in fence['observations']);hostpids.update(x['vm_pid'] for x in fence['observations']);assert report['producer_report_sha256']==sha(C/'producer-report.json')
assert sum(x['checks'] for x in reports)==94
from container_fixture import OwnedImage

def absent(key):
 cp=subprocess.run(['/usr/bin/docker','inspect',key],capture_output=True,timeout=30);assert OwnedImage.probe_absence(cp,key);return {'key':key,'strict_current_absence':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:absence=list(pool.map(absent,sorted(ids|names)))
for pid in hostpids|{guard['host_child_pid']}:assert not pathlib.Path('/proc/'+str(pid)).exists()
# Current exact-work census includes older harnesses that do not serialize all launches.
cp=subprocess.run(['/usr/bin/docker','ps','-aq','--filter','ancestor='+p['image_config_identity']],capture_output=True,check=True,timeout=30);otherids=cp.stdout.decode().split();census=0
if otherids:
 cp=subprocess.run(['/usr/bin/docker','inspect',*otherids],capture_output=True,check=True,timeout=30)
 for c in json.loads(cp.stdout):
  census+=1;assert not any(x.get('Source','').startswith(str(C)+'/') for x in c['Mounts']);assert not any(str(C) in x for x in c.get('Args',[]))
# No live exact-work client/provider/legacy-producer process remains; auditor ancestors excluded.
import os
ancestors={os.getpid()};pid=os.getppid()
while pid>1:
 ancestors.add(pid)
 try:pid=int(pathlib.Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[1])
 except OSError:break
for proc in pathlib.Path('/proc').iterdir():
 if not proc.name.isdigit() or int(proc.name) in ancestors:continue
 try:cmd=(proc/'cmdline').read_bytes()
 except OSError:continue
 assert str(C).encode() not in cmd and str(G).encode() not in cmd,'Owned core work-path process remains'
assert v.verify(G,gp);verify_frozen_inputs(C/'frozen',p['frozen_inputs'])
out=D/'verification/ownedMULTI008/source41-core13-positive';out.mkdir(exist_ok=False)
for n in ['matrix.json','execution-started.json']+[j['name']+'.json' for j in p['jobs']]:(out/n).write_bytes((C/n).read_bytes())
(out/'guard-result.json').write_bytes((G/'result.json').read_bytes())
a={'schema':'adhd/source41-core13-independent-audit@1','passed':True,'scope':'One complete current13-suite core invocation against exact source41compiledimage, including original foundation/wire/multi/hot/relocation/aliases/retirement/registry/auth/learned-workflow programs; no prefix composition or broader platform/recovery/semantic-quality/release claim.','image_config_identity':p['image_config_identity'],'artifact_sha256':p['artifact_sha256'],'admission_sha256':p['admission_manifest_sha256'],'canonical_manifest_sha256':p['canonical_manifest_sha256'],'core_plan_sha256':sha(C/'plan.json'),'core_driver_sha256':sha(C/'driver.py'),'guard_plan_sha256':sha(G/'plan.json'),'guard_driver_sha256':sha(G/'guard.py'),'guard_result_sha256':sha(G/'result.json'),'matrix_sha256':sha(C/'matrix.json'),'authoritative_root_exit':{'handle':'39582','exit_code':0,'tool_chunk':'55c405'},'full_guard_frozen_bound_context_tool_external_closure_verified_before_after':True,'actual_core_reviewed_plan_and_report_passed_qualifiers_invoked':True,'locked_specifications_verified':33,'whole_suites':13,'actual_serialized_checks':94,'reports':reports,'runtime_records':runtime_count,'recorded_payload_probes':probe_count,'recorded_container_ids':len(ids),'recorded_issued_probe_names':len(names),'independent_current_strict_absence':absence,'recorded_workflow_vm_producer_host_pids_absent':sorted(hostpids),'guard_child_and_exactwork_process_census_clear':True,'current_sameimage_containers_inspected_for_owned_mounts':census,'provider_isolation':'Original learned producer LD_PRELOAD fence records blocked18770connects includingprobe; target private image namespace proves all effective model endpoints refused. No provider calls or inference by reviewer. Other model fixtures remain controlled-local.','historical_ledger_limit':'Foundation/wire and expected failed-start auth paths do not serialize a complete per-launch CID/name ledger. Exact recorded handles are checked; successful original cleanup plus current exact-work image mount/argv and process census are independently corroborated. No fabricated totalVMcount or missing historical handle names.','prior_core01_core02_aggregates':'Remain false, retained separately; no prefix borrowing into this full invocation.','runtime_compiler_provider_or_cleanup_starts_by_reviewer':0}
(out/'audit.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({'audit_sha256':sha(out/'audit.json'),'checks':94,'suites':13,'ids':len(ids),'names':len(names),'runtimes':runtime_count,'probes':probe_count}))
