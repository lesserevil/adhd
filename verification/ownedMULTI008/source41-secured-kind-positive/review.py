import ast,collections,hashlib,json,os,pathlib,re,runpy,subprocess,sys
D=pathlib.Path('/home/horde/src/adhd/.worktrees/deployment');R=pathlib.Path('/home/horde/src/adhd');W=D/'_build/secured-kind41-compiled02'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=load(W/'plan.json');e=load(W/'execution.json');c=load(W/'result.json');sys.argv=[str(W/'driver.py'),'--execute','--work',str(W),'--plan-sha256',sha(W/'plan.json')];g=runpy.run_path(str(W/'driver.py'),run_name='security_independent_readonly');assert g['verify'](W,p)
assert e['passed'] and e['started'] and e['exit_code']==0 and e['plan_sha256']==sha(W/'plan.json') and e['report_sha256']==sha(W/'result.json')
# Original execute() inline qualifier, applied without invoking execution.
assert c['passed'] is True and c['artifact_sha256']==p['artifact_sha256'] and c['runtime_hub_image_config_digest']==p['image'];assert all(x['closed'] for x in c['cleanup']);assert all(x['observed_absent'] and not x['cleanup_failure_types'] for x in c['keytool_probe_custody']+c['payload_probe_custody'])
assert len(c['checks'])==7 and all(x['passed'] for x in c['checks']);assert c['staging_manifest_sha256']==p['canonical_manifest_sha256'] and c['acceptance_report_sha256']==p['admission_sha256'];assert c['image_config_digest']==p['image']
for name,h in c['input_sha256'].items():assert sha(W/'frozen'/name)==h
for name,h in c['harness_dependencies_sha256'].items():assert sha(W/'frozen/tests'/name)==h
body=W/'frozen/tests/kafka_oauth_k8s.py';assert sum(isinstance(x,ast.Assert) for x in ast.walk(ast.parse(body.read_text())))==51
old=load(R/'verification/ownedMULTI008/compiled05-secured-kind-positive/assertions.json');assert old['actual_frozen_test_sha256']==sha(body) and old['all_original_assertion_ASTs_preserved'] and old['original_assertions']==48
manifest=load(W/'context/manifest.json');app=W/'oauth-work/image-app';actual={str(x.relative_to(app)):sha(x) for x in app.rglob('*') if x.is_file()};expected={k:v for k,v in manifest['files'].items() if k!='Dockerfile'};expected['manifest.json']=sha(W/'context/manifest.json');assert actual==expected and len(actual)==60 and sum(x.startswith('specification/') for x in actual)==33
for x in app.rglob('*'):assert not x.is_symlink()
assert (app/'manifest.json').read_bytes()==(W/'oauth-work/running-manifest.json').read_bytes()
from container_fixture import OwnedImage
absences=[]
for event in c['payload_probe_custody']+c['keytool_probe_custody']:
 assert event['run_exit_code']==0 and not event['run_failure_type'] and not event['foreign_object_not_removed'];key=event['owned_name'];cp=subprocess.run(['/usr/bin/docker','inspect',key],capture_output=True,timeout=30);assert OwnedImage.probe_absence(cp,key);absences.append({'owned_name':key,'image':event['image_config_identity'],'strict_current_absence':True,'entrypoint':event['entrypoint']})
lease=c['namespace_lease'];assert lease['name']==p['namespace'] and lease['issued'] and lease['uid'] and lease['delete_uid_precondition_required']
base=[p['tools']['kubectl']['path'],'--kubeconfig',str(W/'bound/kubeconfig'),'get','--raw'];raw={}
for endpoint in ['/api/v1/namespaces','/api/v1/persistentvolumes','/api/v1/pods']:
 cp=subprocess.run(base+[endpoint],capture_output=True,check=True,timeout=30);v=json.loads(cp.stdout);raw[endpoint]=hashlib.sha256(cp.stdout).hexdigest()
 if endpoint.endswith('/namespaces'):assert all(x['metadata']['name']!=p['namespace'] for x in v['items'])
 elif endpoint.endswith('/pods'):assert all(x['metadata']['namespace']!=p['namespace'] for x in v['items'])
 else:assert all(x.get('spec',{}).get('claimRef',{}).get('namespace')!=p['namespace'] for x in v['items'])
assert not pathlib.Path('/proc/'+str(e['child_pid'])).exists()
ports=set(p['ports'].values());properties=(W/'oauth-work/security/kafka-rest.properties').read_text();ports.update(int(x) for x in re.findall(r'https://(?:[^/:\s]+):(\d+)',properties))
for f in ['/proc/net/tcp','/proc/net/tcp6']:
 for line in pathlib.Path(f).read_text().splitlines()[1:]:
  cells=line.split();assert not(cells[3]=='0A' and int(cells[1].rsplit(':',1)[1],16) in ports)
ancestors={os.getpid()};pid=os.getppid()
while pid>1:
 ancestors.add(pid)
 try:pid=int(pathlib.Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[1])
 except OSError:break
for proc in pathlib.Path('/proc').iterdir():
 if not proc.name.isdigit() or int(proc.name) in ancestors:continue
 try:cmd=(proc/'cmdline').read_bytes()
 except OSError:continue
 assert str(W).encode() not in cmd,'Owned work-path process remains'
assert (W/'stdout').stat().st_size==(W/'stderr').stat().st_size==0;assert g['verify'](W,p)
out=D/'verification/ownedMULTI008/source41-secured-kind-positive';out.mkdir(exist_ok=False)
for n in ['result.json','execution.json','execution-started.json']:(out/n).write_bytes((W/n).read_bytes())
a={'schema':'adhd/source41-secured-kind-independent-audit@1','passed':True,'scope':'Actual exactimage207 source41 secured Kind TLS/OAuth, hottrust/token and Secret/keystore/REST+broker replacements; no SASL_SSL, CNI, replicatedHA, entitlement or release claim.','image_config_identity':p['image'],'artifact_sha256':p['artifact_sha256'],'plan_sha256':sha(W/'plan.json'),'driver_sha256':sha(W/'driver.py'),'result_sha256':sha(W/'result.json'),'execution_sha256':sha(W/'execution.json'),'authoritative_root_exit':{'handle':'49298','exit_code':0,'source':'Parent authoritative confirmation; no agent handle polling.'},'original_driver_inline_qualifiers_applied':True,'full_isolated_frozen_bound_context_host_tool_external_verify_before_after':True,'frozen_files':len(p['frozen_inputs']),'bound_files':len(p['bound_inputs']),'context_files':len(p['context_inputs']),'actual_whole_reported_checks':7,'original_assertions_conserved':48,'current_program_assertion_AST_count':51,'assertion_count_scope':'51 source assertion sites, not51 individually serialized cases or an asserted runtime instruction count. Actual report has7whole checks and childexit0.','assertion_conservation_reference_sha256':sha(R/'verification/ownedMULTI008/compiled05-secured-kind-positive/assertions.json'),'test_sha256':sha(body),'actual_extracted_payload_files_including_manifest':60,'actual_canonical_specs':33,'namespace_lease':lease,'strict_probe_absence':absences,'current_namespace_pods_and_claimed_pvs_absent':True,'owned_child_workpath_processes_and_hub_rest_issuer_listeners_absent':True,'verified_absent_listener_ports':sorted(ports),'runtime_continuity_scope':'Successful original assertions compare actual PodUID/containerID/PID1 starttime and restart0 across hottrust/token and podreplacements. Raw tuple values were not separately serialized; no postdeletion fabricated tuple.','actual_jwks_fetches':c['jwks_fetches'],'operations_log_sha256':sha(W/'oauth-work/operations.log'),'namespace_pod_pv_readonly_observation_hashes':raw,'no_runtime_cleanup_or_provider_starts_by_reviewer':True,'source_state_image_model_unmodified':True,'limitations':c['limitations']}
(out/'audit.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({'audit_sha256':sha(out/'audit.json'),'reported_checks':7,'assertion_sites':51,'issued_names_absent':len(absences)}))
