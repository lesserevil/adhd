import hashlib,json,os,pathlib,re,runpy,subprocess,sys
W=pathlib.Path('/home/horde/src/adhd/.worktrees/deployment/_build/baseline41-compiled01');R=pathlib.Path('/home/horde/src/adhd');D=R/'.worktrees/deployment'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=load(W/'plan.json');digest=sha(W/'plan.json');sys.argv=[str(W/'driver.py'),'--execute','--work',str(W),'--plan-sha256',digest]
g=runpy.run_path(str(W/'driver.py'),run_name='baseline_independent_readonly_audit');assert g['verify'](W,p,preflight=True)
m=load(W/'matrix.json');assert m['passed'] is True and m['plan_sha256']==digest and m['inputs_unchanged'] and not m['cleanup_failures'] and not m['unrun_platforms'];assert m['model_before'] is m['model_after'] is None and not m['lease_acquired'] and p['maximum_upstream_posts_total']==0
assert len(m['rows'])==2;known_ids=set();hostpids=[];nodepids=[];names=set();children=[]
for job,row,count in zip(p['jobs'],m['rows'],[11,10]):
 assert job['name']==row['name'];report=W/(job['name']+'.json');log=W/(job['name']+'.log');assert sha(report)==row['report_sha256'] and sha(log)==row['log_sha256'];assert row['passed'] and row['exit_code']==0 and row['started'];assert not pathlib.Path('/proc/'+str(row['child_pid'])).exists()
 c=load(report);assert g['qualified'](c,p) and len(c['checks'])==count and all(x['passed'] for x in c['checks']);assert c['platform']==job['name'];assert c['replaced_resources']==['hub','kafka','kafka-rest']
 assert c['acceptance_sha256']==sha(W/'bound/admission.json') and c['staging_sha256']=={name:sha(W/'context'/name) for name in ['manifest.json','payload.tar','Dockerfile']}
 for path,h in c['input_sha256'].items():assert sha(W/'frozen'/path)==h
 for name,h in c['harness_dependencies_sha256'].items():assert sha(W/'frozen/tests'/name)==h
 root=W/(job['name']+'-work');mode=root/'helper-mode-probe.json';assert sha(mode)==c['offline_helper_mode_probe']['report_sha256'] and load(mode)['passed'] and load(mode)['image_config_digest']==p['image']
 assert len(c['compiled_vm_custody'])==2
 for vm in c['compiled_vm_custody']:
  assert vm['image']==p['image'] and vm['process']['actual_compiled_boot_and_app_arguments'] and vm['restart_count']==0
  if job['name']=='compose':known_ids.add(vm['container_id']);hostpids.append(vm['process']);assert vm['entrypoint']==['elixir','/runtime/adhd/boot.exs','/app/hub.exs']
  else:nodepids.append(vm['process']);assert vm['container_id'].startswith('containerd://') and vm['pod_uid']
 if job['name']=='k8s':assert c['namespace_lease']['name']==job['owned_name'] and c['namespace_lease']['uid'] and c['namespace_lease']['delete_uid_precondition_required']
 children.append({'platform':job['name'],'checks':count,'report_sha256':sha(report),'log_sha256':sha(log),'process_exit_code':row['exit_code'],'compiled_vm_custody':c['compiled_vm_custody'],'namespace_lease':c.get('namespace_lease'),'cleanup':c['cleanup'],'operations_log_sha256':sha(root/'operations.log'),'helper_mode_report_sha256':sha(mode),'recovery_set_sha256':sha(root/'recovery-set.json'),'hub_archive_sha256':sha(root/'hub-state.tgz'),'kafka_archive_sha256':sha(root/'kafka-state.tgz')})
# Strict known Docker IDs, and a mount/project-scoped census for short-lived helpers lacking a retained ID ledger.
from container_fixture import OwnedImage
def cmd(a):return subprocess.run(a,capture_output=True,timeout=30)
for cid in sorted(known_ids):cp=cmd(['/usr/bin/docker','inspect',cid]);assert OwnedImage.probe_absence(cp,cid)
for proc in hostpids:assert not pathlib.Path('/proc/'+str(proc['pid'])).exists()
node=p['facts']['node']['name']
for proc in nodepids:
 cp=cmd(['/usr/bin/docker','exec',node,'sh','-c','test ! -e /proc/'+str(proc['pid'])]);assert cp.returncode==0,'Recorded node process remains'
cp=cmd(['/usr/bin/docker','ps','-aq','--filter','ancestor='+p['image']]);assert cp.returncode==0
ids=cp.stdout.decode().split();checked=0
if ids:
 cp=cmd(['/usr/bin/docker','inspect',*ids]);assert cp.returncode==0
 for row in json.loads(cp.stdout):
  checked+=1
  assert row['Config'].get('Labels',{}).get('com.docker.compose.project')!=p['jobs'][0]['owned_name']
  assert not any(x.get('Source','').startswith(str(W)+'/') for x in row['Mounts']),'Owned source-root mounted container remains'
# Same namespace/PV checks as original cleanup, performed again read-only.
kub=p['tools']['kubectl']['path'];kube=W/'bound/kubeconfig';ns=p['jobs'][1]['owned_name']
cp=cmd([kub,'--kubeconfig',str(kube),'get','namespace',ns,'--ignore-not-found=true','-o','json']);assert cp.returncode==0 and not cp.stdout.strip()
cp=cmd([kub,'--kubeconfig',str(kube),'get','pv','-o','json']);assert cp.returncode==0;assert all(x.get('spec',{}).get('claimRef',{}).get('namespace')!=ns for x in json.loads(cp.stdout)['items'])
assert g['verify'](W,p,preflight=True)
out=D/'verification/ownedMULTI008/source41-baseline-platform-positive';out.mkdir(exist_ok=False)
for n in ['matrix.json','compose.json','k8s.json']:(out/n).write_bytes((W/n).read_bytes())
a={'schema':'adhd/source41-baseline-platform-independent-audit@1','passed':True,'scope':'Exactsource41 compiledimage model-free Compose11/Kind10 full original platform programs; no TLS/OAuth, CNI, live-model, HA or whole-roadmap claim.','image_config_identity':p['image'],'artifact_sha256':p['artifact_sha256'],'plan_sha256':digest,'driver_sha256':sha(W/'driver.py'),'matrix_sha256':sha(W/'matrix.json'),'admission_sha256':p['admission_sha256'],'canonical_manifest_sha256':p['canonical_manifest_sha256'],'full_frozen_bound_context_host_tool_external_closure_verified_before_after':True,'isolated_real_staged_premain':True,'actual_frozen_child_qualifier_invoked':True,'frozen_files':len(p['frozen_inputs']),'bound_files':len(p['bound_inputs']),'context_files':len(p['context_inputs']),'whole_platforms':2,'whole_checks':21,'children':children,'actual_compiled_vm_observations':4,'strict_current_known_docker_ids_absent':sorted(known_ids),'recorded_host_and_node_pids_currently_absent':True,'actual_child_pids_absent':True,'current_namespace_and_claimref_pv_absent':True,'source_mount_and_project_scoped_image_census_clear':True,'other_sameimage_containers_inspected_for_owned_mounts':checked,'historical_helper_ledger_limit':'Short-lived tar and payload helpers do not all retain issued names/IDs. Original --rm/checked completion and current exact work-mount/project census are checked; no invented individual historical names.','model_free_configuration_and_parent_budget':True,'provider_contact_scope':'Original programs use matcher:null and no model-only/relay path. Parent records no lease/model observations and budget0; no packet-level network egress claim.','no_runtime_or_cleanup_mutations_by_audit':True,'authoritative_root_process_exit':'Parent root owns handle29923; actual childexit0/matrixtrue retained, root terminal confirmation recorded separately.'}
(out/'audit.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({'audit_sha256':sha(out/'audit.json'),'whole_checks':21,'known_docker_ids':len(known_ids),'hostpids':len(hostpids),'nodepids':len(nodepids),'inspected_sameimage':checked}))
