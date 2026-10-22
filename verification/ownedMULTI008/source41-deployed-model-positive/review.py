import hashlib,json,os,pathlib,runpy,stat,subprocess,sys
D=pathlib.Path('/home/horde/src/adhd/.worktrees/deployment');R=D.parents[1];W=D/'_build/deployed-model41-compiled01'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def command(a):return subprocess.run(a,capture_output=True,check=True,timeout=30).stdout
p=load(W/'plan.json');m=load(W/'matrix.json');sys.argv=[str(W/'driver.py'),'--execute','--work',str(W),'--plan-sha256',sha(W/'plan.json')];g=runpy.run_path(str(W/'driver.py'),run_name='readonly_actual_model_audit');assert g['verify'](W,p)
assert m['passed'] and m['inputs_unchanged'] and not m['unrun_platforms'] and not m['cleanup_failures'] and not m['failure_type'] and m['lease_acquired'];assert m['plan_sha256']==sha(W/'plan.json');assert len(m['rows'])==2
before=m['model_before'];after=m['model_after'];assert {k:v for k,v in before.items() if k!='metadata_client'}=={k:v for k,v in after.items() if k!='metadata_client'}
model=json.loads(command(['/usr/bin/docker','inspect',before['container_id']]))[0];assert model['Id']==before['container_id'] and model['Image']==before['image_config_identity'] and model['State']['Pid']==before['host_vm_pid'] and model['State']['StartedAt']==before['started_at'] and model['RestartCount']==before['restart_count'] and model['State']['Running'] and model['State']['Health']['Status']=='healthy'
assert model['NetworkSettings']['Ports']['8770/tcp']==[{'HostIp':'127.0.0.1','HostPort':'18770'}]
from container_fixture import OwnedImage
known_ids=set();relaypids=[];vmpids=[];children=[];requests=0;gateways=[]
for job,row in zip(p['jobs'],m['rows']):
 name=job['name'];root=W/(name+'-work');c=load(W/(name+'.json'));report=root/'optional-model.json';relay=root/'model-relay.json';inner=load(report);calls=load(relay);opt=c['optional_model'];budget=opt['budget']
 assert row['passed'] and row['exit_code']==0 and row['started'];assert not pathlib.Path('/proc/'+str(row['child_pid'])).exists();assert sha(W/(name+'.json'))==row['report_sha256'] and sha(W/(name+'.log'))==row['log_sha256'];assert g['qualified'](c,p)
 assert len(c['checks'])==4 and all(x['passed'] for x in c['checks']);assert c['acceptance_sha256']==p['admission_sha256'] and c['staging_sha256']=={x:sha(W/'context'/x) for x in ['manifest.json','payload.tar','Dockerfile']}
 for f,h in c['input_sha256'].items():assert sha(W/'frozen'/f)==h
 for f,h in c['harness_dependencies_sha256'].items():assert sha(W/'frozen/tests'/f)==h
 assert sha(report)==opt['report_sha256'] and sha(relay)==opt['gateway_report_sha256']==inner['gateway_report_sha256'];assert sha(W/'frozen/tests/kafka_platform_model.py')==opt['harness_sha256']==inner['harness_sha256'];assert sha(W/'frozen/tests/kafka_platform_gateway.py')==opt['gateway_harness_sha256']
 assert inner['passed'] and inner['artifact_sha256'] is None and inner['relay_audit']==budget and inner['actual_processing_calls']==len(calls)==budget['upstream_attempts']==6
 assert budget['filter_attempts']==budget['semantic_attempts']==3 and budget['maximum_upstream_posts']==12 and budget['no_retry_forwards'] and budget['all_requests_privacy_checked'];assert [x['attempt'] for x in calls]==list(range(1,7));assert all(x['phase']=='responded' and x['status']==200 and x['request_privacy_checked'] and x['caller'] in opt['relay_scope']['allowed_callers'] for x in calls)
 assert len({x['request_sha256'] for x in calls})==len(calls);assert sum(x['question_keys']==['relevance'] for x in calls)==3;assert sum(x['question_keys']==['answer','assessment'] for x in calls)==3
 for key in ['raw_received_both','filtered_received_only_positive','hot_model_enable_and_disable','raw_progress_after_model_disable','literal_search_preserved','model_free_second_project_zero_inference','accepted_while_model_disabled_delivered_once_after_reenable','foreign_and_private_canaries_absent_from_red_requests_and_answer']:assert inner[key] is True
 assert inner['additional_inference_calls_after_disable']==0 and inner['initial_filter_fixture_processing_calls']==2 and inner['resumed_filter_processing_calls']==1
 assert inner['backend_query']['positive_original_cited'] and inner['backend_query']['foreign_project_original_absent'] and inner['backend_query']['foreign_query_lookup_denied'] and inner['backend_query']['status']=='completed'
 assert len(inner['synthetic_decisions'])==2
 assert opt['same_packaged_vm_before_after_hot_changes'] and opt['vm_identity']['restart_count']==0 and opt['cleanup']['process_exit_code']==0 and opt['cleanup']['listener_independently_absent'];relaypids.append(opt['relay_process']['pid']);assert not pathlib.Path('/proc/'+str(opt['relay_process']['pid'])).exists()
 v=c['compiled_vm_custody'];assert len(v)==2 and v[0]['container_id']==v[1]['container_id'] and v[0]['process']['pid']==v[1]['process']['pid'] and v[0]['process']['start_ticks']==v[1]['process']['start_ticks'] and v[0]['started_at']==v[1]['started_at']
 for vm in v:
  assert vm['image']==p['image'] and vm['restart_count']==0 and vm['process']['actual_compiled_boot_and_app_arguments'];vmpids.append(vm['process']['pid'])
 if name=='compose':
  known_ids.add(v[0]['container_id']);assert not pathlib.Path('/proc/'+str(v[0]['process']['pid'])).exists()
  nid=opt['relay_scope']['resource_binding']['network_id'];cp=subprocess.run(['/usr/bin/docker','network','inspect',nid],capture_output=True,timeout=30);assert cp.returncode==1 and cp.stdout.strip()==b'[]' and cp.stderr.decode().strip()=='Error response from daemon: network '+nid+' not found'
 else:
  node=p['facts']['node']['name'];assert command(['/usr/bin/docker','exec',node,'sh','-c','test ! -e /proc/'+str(v[0]['process']['pid'])])==b'';assert c['namespace_lease']['delete_uid_precondition_required']
 app=root/'image-app';manifest=load(W/'context/manifest.json');files={str(x.relative_to(app)):sha(x) for x in app.rglob('*') if x.is_file()};expected={k:v for k,v in manifest['files'].items() if k!='Dockerfile'};expected['manifest.json']=sha(W/'context/manifest.json');assert files==expected
 children.append({'platform':name,'outer_reported_checks':4,'outer_report_sha256':sha(W/(name+'.json')),'semantic_report_sha256':sha(report),'relay_report_sha256':sha(relay),'original_semantic_gates':inner,'actual_relay_posts':len(calls),'budget':budget,'same_actual_vm':opt['vm_identity'],'relay_scope':opt['relay_scope'],'relay_process':opt['relay_process'],'namespace_lease':c.get('namespace_lease'),'cleanup':c['cleanup']});requests+=len(calls)
 gateways.append({'platform':name,'entries':[{'attempt':x['attempt'],'phase':x['phase'],'caller':x['caller'],'request_sha256':x['request_sha256'],'question_keys':x['question_keys'],'request_privacy_checked':x['request_privacy_checked'],'status':x['status'],'elapsed_ms':x['elapsed_ms']} for x in calls]})
for cid in known_ids:
 cp=subprocess.run(['/usr/bin/docker','inspect',cid],capture_output=True,timeout=30);assert OwnedImage.probe_absence(cp,cid)
# No mutation/acquisition: observe that the exact cooperative file inode is not locked.
lease=pathlib.Path(p['lease_path']);info=lease.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and not lease.is_symlink();lockkey=f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}';assert not any(lockkey in line for line in pathlib.Path('/proc/locks').read_text().splitlines())
ports={x['relay_port'] for x in p['jobs']}|{x['port'] for x in p['jobs']}
for f in ['/proc/net/tcp','/proc/net/tcp6']:
 for line in pathlib.Path(f).read_text().splitlines()[1:]:
  cells=line.split();assert not(cells[3]=='0A' and int(cells[1].rsplit(':',1)[1],16) in ports)
ns=p['jobs'][1]['owned_name'];kub=p['tools']['kubectl']['path'];base=[kub,'--kubeconfig',str(W/'bound/kubeconfig')];assert not command(base+['get','namespace',ns,'--ignore-not-found=true','-o','json']).strip();assert all(x.get('spec',{}).get('claimRef',{}).get('namespace')!=ns for x in json.loads(command(base+['get','pv','-o','json']))['items']);assert g['verify'](W,p)
assert requests==12 and requests<=p['maximum_upstream_posts_total']==24
out=D/'verification/ownedMULTI008/source41-deployed-model-positive';out.mkdir(exist_ok=False)
for n in ['matrix.json','compose.json','k8s.json']:(out/n).write_bytes((W/n).read_bytes())
for n in ['compose','k8s']:(out/(n+'-semantic-report.json')).write_bytes((W/(n+'-work/optional-model.json')).read_bytes())
a={'schema':'adhd/source41-deployed-model-independent-audit@1','passed':True,'scope':'Complete original model-only Compose+Kind deployed filter/search programs on exact source41compiledimage; no baseline/security/CNI/modelquality69/production/release claim.','image_config_identity':p['image'],'artifact_sha256':p['artifact_sha256'],'plan_sha256':sha(W/'plan.json'),'driver_sha256':sha(W/'driver.py'),'matrix_sha256':sha(W/'matrix.json'),'authoritative_root_exit':{'handle':'37087','exit_code':0},'full_isolated_frozen_bound_context_host_tool_closure_verified_before_after':True,'original_frozen_qualified_invoked_both_platforms':True,'actual_outer_reported_checks':8,'whole_platform_programs':2,'case_count_clarification':'Actualchildren serialize4outerchecks each; semantic reports expose originalboolean/typeddecision gates, not6individuallyserialized cases each. No inherited12case-array claim.','actual_upstream_posts_total':requests,'maximum_upstream_posts_per_platform':12,'maximum_upstream_posts_total':24,'relay_observations':gateways,'children':children,'model_before_after_unchanged':True,'current_readonly_model_identity_matches_before_after':True,'lease_currently_unlocked_inode':{'device':info.st_dev,'inode':info.st_ino},'strict_recorded_compose_cid_absent':sorted(known_ids),'recorded_vm_and_relay_processes_absent':True,'selected_ports_namespace_pvs_and_owned_compose_project_absent':True,'current_actual_model_source_state_unchanged':True,'reviewer_provider_calls_starts_or_cleanup_mutations':0,'inspection_limits':'No packet-level universal egress claim or reconstructed historical unnamed payload-helper IDs. Originalcheckedcompletion plus exactwork/project resource census and qualifiedcleanup retained.'}
(out/'audit.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({'audit_sha256':sha(out/'audit.json'),'outer_checks':8,'platforms':2,'posts_total':requests}))
