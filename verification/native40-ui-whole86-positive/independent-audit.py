from pathlib import Path
import json,hashlib,importlib.util,os
w=Path('/home/horde/src/adhd/.worktrees/config-acceptance/_build/nu40-final02');s=importlib.util.spec_from_file_location('frozen_native_ui_terminal',w/'run.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);p=json.load(open(w/'plan.json'));assert m.verify(p,w);v=json.load(open(w/'matrix.json'));assert v['passed'] and not v['unrun_suites'] and len(v['rows'])==9 and v['frozen_inputs_unchanged']
sha=lambda q:hashlib.sha256(Path(q).read_bytes()).hexdigest();assert sha(p['artifact'])==v['artifact_sha256']==p['artifact_sha256'];capture_rows={};processes={};vms={};rows=[];rigs=[]
def record(x):
 if isinstance(x,dict):
  if isinstance(x.get('pid'),int) and x.get('starttime') is not None:processes[(x['pid'],str(x['starttime']))]=True
  for z in x.values():record(z)
 elif isinstance(x,list):
  for z in x:record(z)
for job,row in zip(p['jobs'],v['rows']):
 name=job['name'];assert name==row['suite'] and row['passed'] and row['exit_code']==0 and row['owned_nonce_absent'] and not row['unexpected_live_nonce_processes'];report=json.load(open(w/(name+'.json')));cust=json.load(open(job['custody_report']));launch=json.load(open(job['launch_ledger']));procs=json.load(open(job['process_ledger']));assert report['passed'] and m.unit_count(report,name)==job['expected_units']==row['units'];assert cust['passed'] and not cust['original_exception'] and not cust['cleanup_exception'] and not cust['cleanup_errors'] and not cust['unexpected_live_Popen_handles'];assert sha(w/(name+'.json'))==row['report_sha256'] and sha(job['custody_report'])==row['custody_sha256'] and sha(w/(name+'.log'))==row['log_sha256'];assert not launch['cleanup_errors'];record(cust);record(procs);record(launch)
 for vm in cust['native_vm_observations']:
  assert vm['artifact_sha256']==p['artifact_sha256'] and vm['artifact_path']==p['artifact'] and vm['fence_mapped'] and vm['executable_sha256']==p['native_beam_sha256'];vms[(vm['pid'],vm['starttime'])]=vm
 rigs.extend(cust['rigs'])
 for text,h in row['new_screenshots_and_ARIA'].items():
  q=Path(text);assert q.is_file() and not q.is_symlink() and q.with_suffix('.txt').is_file();assert sha(q)==h['png_sha256'] and sha(q.with_suffix('.txt'))==h['aria_sha256'];capture_rows[text]=h
 rows.append({'suite':name,'units':row['units'],'report_sha256':row['report_sha256'],'custody_sha256':row['custody_sha256'],'launches_sha256':sha(job['launch_ledger']),'processes_sha256':sha(job['process_ledger']),'log_sha256':row['log_sha256']})
assert sum(x['units'] for x in rows)==86
f=Path(p['fence_audit']);assert not f.exists() or f.read_bytes()==b''
absent=[]
for pid,start in sorted(processes):
 try:
  t=(Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1].split();current=t[19];assert current!=start,('Original process identity remains',pid,start,t[0]);status={'pid':pid,'starttime':start,'current_starttime':current,'original_identity_absent':True}
 except FileNotFoundError:status={'pid':pid,'starttime':start,'proc_absent':True}
 absent.append(status)
core=m.load(w/'frozen/tests/native_core_remaining.py','read_only_native_ui_nonce')
for job in p['jobs']:assert not core.owned_nonce_processes(sha(w/'plan.json')+':'+job['name'])
from image_ui_runtime import rig_processes
assert len(rigs)==1 and rigs[0]['terminal_seat_count']==2 and not rigs[0]['after_original_close'];assert not rig_processes(rigs[0]['home'],rigs[0]['mux'])
manual=Path('/home/horde/src/adhd/verification/native40-ui-manual-prefix-review/review.json');review=json.load(open(manual));assert review['artifact_sha256']==p['artifact_sha256'] and review['plan_sha256']==sha(w/'plan.json')
for row in review['reviewed']:
 q=Path('/home/horde/src/adhd')/row['capture_project_relative'];assert str(q) in capture_rows;assert sha(q)==row['png_sha256'] and sha(q.with_suffix('.txt'))==row['accessibility_sha256']
# Read-only complete current owned-path scan, excluding the audit ancestors.
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
  if any(str(root).encode() in cmd or cwd.startswith(str(root)) for root in [w,Path(p['openrig_root'])]):remaining.append({'pid':int(q.name),'cmdline_sha256':hashlib.sha256(cmd).hexdigest()})
 except(FileNotFoundError,ProcessLookupError,PermissionError):pass
assert not remaining
result={'plan_sha256':sha(w/'plan.json'),'driver_sha256':sha(w/'run.py'),'matrix_sha256':sha(w/'matrix.json'),'closure':{'frozen_files':len(p['frozen_inputs']),'bound_files':len(p['bound_inputs']),'externals':len(p['externals']),'tool_roots':len(p['tool_roots'])},'rows':rows,'actual_unique_native_VMs':list(vms.values()),'actual_unique_native_VM_count':len(vms),'strict_process_start_identity_absence':absent,'unique_process_identity_count':len(absent),'all9_owned_nonces_absent':True,'exact_private_rig_environment_processes_remaining':[],'current_owned_path_process_scan_remaining':remaining,'audit_ancestors_excluded':sorted(anc),'private_keep_work_rig_files_intentionally_retained':True,'provider_fence_mapped_on_every_VM':True,'provider_fence_audit_absent_or_empty':True,'captures':capture_rows,'capture_count':len(capture_rows),'manual_review_path':str(manual),'manual_review_sha256':sha(manual),'manual_actual_capture_count':len(review['reviewed']),'no_runtime_cleanup_or_provider_calls':True};Path('/home/horde/src/adhd/.worktrees/config-acceptance/_build/native-ui-terminal-audit/audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'closure':result['closure'],'VMs':len(vms),'processes':len(absent),'captures':len(capture_rows),'manual_viewed':len(review['reviewed'])}))
