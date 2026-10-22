from pathlib import Path
import json,hashlib,importlib.util,subprocess,os
w=Path('/home/horde/src/adhd/.worktrees/config-acceptance/_build/core05-remaining02');s=importlib.util.spec_from_file_location('frozen_core10_terminal',w/'run.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);p=json.load(open(w/'plan.json'));assert m.verify(w,p);v=json.load(open(w/'matrix.json'));assert v['passed'] and not v['unrun'] and len(v['results'])==10
sha=lambda q:hashlib.sha256(Path(q).read_bytes()).hexdigest();parent=Path(p['parent_core']);old=json.load(open(parent/'matrix.json'));assert old['passed'] is False;handles=set();runtimes=[];rows=[];clientpids=[];empty_negative=0

def visit(x):
 global empty_negative
 if isinstance(x,dict):
  if isinstance(x.get('container_lifecycle'),list):
   assert x['kind']=='docker' and x['image_config_identity']==p['image_config_identity'] and x['canonical_manifest_sha256']==p['canonical_manifest_sha256'];assert not x.get('cleanup_blocked',False) and not x.get('probe_cleanup_blocked',False)
   ev=x['container_lifecycle'];a={e['container_id'] for e in ev if e['action']=='started'};b={e['container_id'] for e in ev if e['action'] in ['hard-killed','stopped'] and e.get('observed_absent')};assert a<=b
   empty_negative+=not bool(a)
   runtimes.append({k:x.get(k) for k in ['kind','image_config_identity','artifact_sha256','canonical_manifest_sha256']})
  for q in x.get('payload_probe_lifecycle',[]):assert q['observed_absent'] and not q['cleanup_failure_types']
  for z in x.values():visit(z)
 elif isinstance(x,list):
  for z in x:visit(z)
for job,row in zip(p['jobs'],v['results']):
 name=job['name'];assert name==row['name'] and row['passed'] and row['process_exit_code']==0;report=json.load(open(w/(name+'.json')));assert report['passed'];checks=report.get('checks',report.get('cases'));assert checks and all(x['passed'] for x in checks);assert sha(w/(name+'.json'))==row['report_sha256'] and sha(w/(name+'.log'))==row['log_sha256'];visit(report);handles.update(m.runtime_handles(report));clientpids.append(row['host_client_pid']);rows.append({'name':name,'whole_checks':len(checks),'report_sha256':row['report_sha256'],'log_sha256':row['log_sha256']})
for name in p['whole_prefix']:
 report=json.load(open(parent/(name+'.json')));assert report['passed'];checks=report.get('checks',report.get('cases'));assert all(x['passed'] for x in checks);visit(report);handles.update(m.runtime_handles(report));rows.append({'name':name,'whole_checks':len(checks),'report_sha256':sha(parent/(name+'.json')),'log_sha256':sha(parent/(name+'.log')),'original_whole_prefix':True})
assert sum(x['whole_checks'] for x in rows)==94 and len(rows)==13
original_names=[x['name'] for x in json.load(open(parent/'plan.json'))['jobs']];assert set(original_names)=={r['name'] for r in rows};rows.sort(key=lambda row:original_names.index(row['name']))
gp=json.load(open(Path(p['parent_guard'])/'plan.json'));env={k:x for k,x in os.environ.items() if not k.startswith('DOCKER_')};env.update(DOCKER_HOST='unix://'+gp['socket']['path'],DOCKER_CONFIG=str(w/'bound/docker-config'))
observations=[m.absence(i,env) for i in sorted(handles)]
anc=set();x=os.getpid()
while x>1:
 anc.add(x)
 try:x=int((Path('/proc')/str(x)/'stat').read_text().split(') ',1)[1].split()[1])
 except FileNotFoundError:break
remaining=[]
for q in Path('/proc').iterdir():
 if not q.name.isdigit() or int(q.name) in anc:continue
 try:
  cmd=(q/'cmdline').read_bytes();cwd=os.readlink(q/'cwd')
  if any(str(a).encode() in cmd or cwd.startswith(str(a)) for a in [w,parent,Path(p['parent_guard'])]):remaining.append({'pid':int(q.name),'cmdline_sha256':hashlib.sha256(cmd).hexdigest()})
 except(FileNotFoundError,ProcessLookupError,PermissionError):pass
assert not remaining
owned_mounts=[]
for i in subprocess.check_output(['/usr/bin/docker','ps','-aq'],env=env,text=True).split():
 rr=subprocess.run(['/usr/bin/docker','inspect',i],capture_output=True,env=env,timeout=30)
 if rr.returncode:m.absence(i,env);continue
 c=json.loads(rr.stdout)[0]
 if any(any(str(a) in z.get('Source','') for a in [w,parent,Path(p['parent_guard'])]) for z in c.get('Mounts',[])):owned_mounts.append({'id':c['Id'],'name':c['Name']})
assert not owned_mounts
out={'passed':True,'whole_suites':13,'whole_checks':94,'remaining10_checks':59,'whole_prefix3_checks':35,'original_false_matrix_sha256':sha(parent/'matrix.json'),'original_false_preserved':True,'partial_failed8_excluded':True,'whole_rows_original13_order':rows,'full_frozen_parent_bound_context_tool_external_verify':True,'fresh_frozen_files':len(p['frozen']['files']),'fresh_bound_files':len(p['bound']['files']),'fresh_runtime_fixture_bindings':len(p['runtime_fixtures']),'strict_known_container_and_probe_absence':observations,'known_container_ID_count':sum(len(x)==64 for x in handles),'known_probe_name_count':sum(len(x)!=64 for x in handles),'current_owned_path_process_scan_remaining':remaining,'current_owned_mount_containers_remaining':owned_mounts,'recorded_child_pid_numbers':[{'pid':pid,'currently_proc_absent':not Path('/proc',str(pid)).exists(),'start_tick_not_recorded':True} for pid in clientpids],'audit_ancestors_excluded':sorted(anc),'actual_reported_image_runtime_bindings':runtimes,'constructed_negative_startup_runtimes_with_no_started_event':empty_negative,'recording_limit':'No new global issuance ledger. Foundation/wire prefix lack runtime lifecycle issuance. Exact recorded container IDs/probe names and current owned mount/path scans audited; no invented app names or historical PID-start ticks. Two deliberate refused auth starts have no started lifecycle event.','no_runtime_provider_or_cleanup_mutations':True};Path('/home/horde/src/adhd/.worktrees/config-acceptance/_build/core05-terminal-audit/audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'whole':94,'IDs':out['known_container_ID_count'],'probes':out['known_probe_name_count'],'runtime_bindings':len(runtimes),'negative_startups':empty_negative}))
