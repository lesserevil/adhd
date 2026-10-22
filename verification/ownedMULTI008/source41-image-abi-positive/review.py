import concurrent.futures,hashlib,importlib.util,json,os,pathlib,subprocess,sys
sys.dont_write_bytecode=True
W=pathlib.Path('/home/horde/src/adhd/_build/abi41-compiled01');OUT=pathlib.Path('/home/horde/src/adhd/.worktrees/deployment/verification/ownedMULTI008/source41-image-abi-positive')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=module('abi_audited_frozen',W/'run.py');p=load(W/'plan.json');r=load(W/'result.json');m.verify(p)
assert sha(W/'plan.json')==r['plan_sha256'];assert r['passed'] is True and len(r['rows'])==19
assert r['image_config_identity']==p['image_config_identity'] and r['artifact_sha256']==p['artifact_sha256']
assert not r['application_started'] and r['provider_calls']==r['broker_calls']==0
h,_=m.load_helpers(W/'inputs');from container_fixture import OwnedImage
rows=r['rows'];assert [v['case'] for v in rows]==p['cases'];assert len({v['container_id'] for v in rows})==19
sources={};physical=[]
for source,ops in m.selected_families(p['selected_families']).items():
 proof=W/(source+'.proof.json');library=p['observer_builds'][source]['library'];_,q=h.validate_observer(p['image_config_identity'],library,proof,source)
 assert q['artifact_sha256']==p['artifact_sha256'] and q['canonical_manifest_sha256']==p['canonical_manifest_sha256']
 assert q['cases']==[x for x in rows if x['case']['source']==source]
 assert sha(W/'inputs'/source)==q['observer']['source_sha256']
 sources[source]={'proof_sha256':sha(proof),'source_sha256':sha(W/'inputs'/source),'library_sha256':sha(library),'exports':sorted(ops)}
for i,row in enumerate(rows):
 source,op=row['case']['source'],row['case']['op'];root=W/'cases'/('%02d-'%i+source.removesuffix('.c')+'-'+op)
 assert load(root/'result.json')==row;assert load(root/'caller.json')==row['caller'];assert load(root/'observer.json')==row['observer_trace']
 m.validate_call(row['caller'],op);c=row['process_custody'];assert c['namespace_pid']==1 and c['kernel_state']=='stopped' and c['signal_method']=='ancestor-pidfd-SIGSTOP' and c['executable_basename']=='busybox' and c['process_maps_witness_phase']=='kernel-stopped'
 assert c['observer_library_sha256']==row['observer_library_sha256']==sources[source]['library_sha256'];assert row['caller_library_sha256']==sha(p['caller']['library'])
 assert row['passed'] is True and row['exit_code']==137 and row['owned_container_absent'] is True and row['physical']['verified'] is True
 assert not pathlib.Path('/proc/'+str(c['host_process_pid'])).exists(),'Recorded process PID currently present'
 # Exact retained target effects, bounded even for sparse >4GiB cases.
 if source=='multi_fault.c': target=root/('state.dets.projects/target/state.dets.snapshot' if op in ('link','linkat') else 'state.dets.snapshot')
 elif source=='store_move_fault.c':target=root/('state.dets.snapshot' if op=='link' else 'control.json.transaction')
 elif source=='storage_write_fault.c':target=root/('state.dets' if op in ('pwrite','pwrite64') else 'state.dets.snapshot.tmp-probe' if op=='fsync' else 'state.dets.snapshot')
 elif source=='project_recovery_fault.c':target=root/('.restore-probe/state.dets.snapshot' if op=='rename' else 'state.dets.snapshot' if op=='link' else 'control.json.transaction')
 else:target=root/('control.json.journal' if source=='config_rename_fault.c' else 'control.json.transaction')
 assert target.stat().st_size==row['physical']['target_bytes']
 if op in ('pwrite','pwrite64'):
  assert target.stat().st_blocks*512<=65536
  for path in (target,root/'unarmed-source'):
   assert path.stat().st_size==m.BIG_OFFSET+len(m.PAYLOAD)
   with path.open('rb') as f:f.seek(m.BIG_OFFSET);assert f.read(len(m.PAYLOAD)+1)==m.PAYLOAD
 else:
  assert target.stat().st_size<1024;data=target.read_bytes();assert data==b'actual decision control' if row['physical']['effect']=='before-unlink' else data.startswith(m.PAYLOAD)
 physical.append({'case':row['case'],'target_sha256':sha(target) if target.stat().st_size<1024 else None,'sparse_high_offset_verified':op in ('pwrite','pwrite64')})
def absent(row):
 cid=row['container_id'];cp=subprocess.run(['docker','inspect',cid],capture_output=True,timeout=20);assert OwnedImage.probe_absence(cp,cid)
 return {'container_id':cid,'strict_current_absence':True,'stdout_sha256':hashlib.sha256(cp.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(cp.stderr).hexdigest(),'returncode':cp.returncode}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:absence=list(pool.map(absent,rows))
cp=subprocess.run(['docker','ps','-a','--filter','name=^/adhd-abi-','--format','{{.ID}} {{.Names}}'],capture_output=True,timeout=20);assert cp.returncode==0 and cp.stdout==b''
m.verify(p)
OUT.mkdir(parents=True,exist_ok=False)
for name in ['result.json']+[s+'.proof.json' for s in sources]:(OUT/name).write_bytes((W/name).read_bytes())
a={'schema':'adhd/source41-image-abi-independent-audit@1','passed':True,'scope':'Standalone source-specific observer ABI forwarding, physical effects, musl loading and process custody; no application/recovery durability qualification.','image_config_identity':p['image_config_identity'],'artifact_sha256':p['artifact_sha256'],'plan_sha256':sha(W/'plan.json'),'driver_sha256':sha(W/'run.py'),'result_sha256':sha(W/'result.json'),'frozen_inventory_files':len(p['inventory']),'frozen_inventory_directories':len(p['directories']),'full_inventory_verified_before_after':True,'compiled_admission':p['compiled_admission'],'source_proofs':sources,'cases':19,'rows_exact_original_order':True,'case_json_caller_trace_equal':True,'all_case_exit_codes':137,'all_recorded_host_pids_currently_absent':True,'actual_known_cid_absence':absence,'abi_name_prefix_census_empty':True,'issued_name_limitation':'Issued random names were not persisted by the original runner. Exact historical name-by-name reconstruction is unavailable; 19 exact CIDs, recorded removal/absence and current scoped name-prefix census are independently checked.','physical_rechecks':physical,'application_started':False,'provider_calls':0,'broker_calls':0,'inspection_only':True}
(OUT/'audit.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({'passed':True,'cases':19,'audit':str(OUT/'audit.json'),'sha256':sha(OUT/'audit.json')}))
