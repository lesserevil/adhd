"""Frozen complementary native eventing regression, controlled providers only."""
import argparse,concurrent.futures,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def bounded_jobs(jobs,run,parallelism,fail_fast):
 if not fail_fast:
  with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism)as pool:return list(pool.map(run,jobs))
 results={};next_index=0;failed=False
 with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism)as pool:
  pending={}
  while pending or (not failed and next_index<len(jobs)):
   while not failed and len(pending)<parallelism and next_index<len(jobs):
    pending[pool.submit(run,jobs[next_index])]=next_index;next_index+=1
   done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
   for future in done:
    index=pending.pop(future);results[index]=future.result()
    if results[index]['exit_code']!=0:failed=True
 return [results[index]for index in sorted(results)]


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('legacy-hub','repo-root','work','report'):p.add_argument('--'+key,type=Path,required=True)
 for key in ('artifact-sha256','eventing-rest-url','federation-rest-url','private-rest-url','owned-broker-container','owned-compose-project'):p.add_argument('--'+key,required=True)
 target=p.add_mutually_exclusive_group(required=True)
 target.add_argument('--hub',type=Path)
 target.add_argument('--image',help='Immutable reviewed Docker image configuration ID')
 p.add_argument('--image-manifest',type=Path)
 p.add_argument('--image-fault-library',type=Path)
 p.add_argument('--image-fault-proof',type=Path)
 p.add_argument('--image-admission-manifest',type=Path)
 p.add_argument('--image-admission-sha256')
 p.add_argument('--prepare-only',action='store_true',help='Image healthy phase: freeze target authority/commands only')
 p.add_argument('--reviewed-plan-sha256',help='Required exact reviewed image plan digest before execution')
 p.add_argument('--phase',choices=('healthy','private'),required=True)
 p.add_argument('--fail-fast',action='store_true',help='Stop admitting suites after an observed failure; already running suites finish')
 p.add_argument('--only',help='Explicit comma-separated healthy-phase subset for fixture-only reruns')
 a=p.parse_args();root=a.repo_root.resolve();hub=a.hub.resolve() if a.hub else None;legacy=a.legacy_hub.resolve();work=a.work.resolve();frozen=work/'frozen'
 assert not a.prepare_only or (a.image and a.phase=='healthy'),'Preparation applies only to image healthy plan'
 reuse_image=bool(a.image and not a.prepare_only)
 if reuse_image:sys.path.insert(0,str(frozen/'tests'))
 bound_inputs={};selected=None;live_spec_drift={}
 if a.image:
  import re
  assert re.fullmatch('sha256:[a-f0-9]{64}',a.image),'Require immutable image configuration ID'
  assert a.image_manifest and a.image_fault_library and a.image_fault_proof,'Full13image suites require reviewed manifest and actual-image fault observer proof/library'
  manifest=json.loads(a.image_manifest.read_text());artifact=manifest['files']['hub.exs']
  assert a.image_admission_manifest and a.image_admission_sha256,'Image qualification requires reviewed admission binding'
  from image_qualification_inputs import reviewed_payload
  selected=reviewed_payload(a.image_manifest,a.image_admission_manifest,a.image_admission_sha256,a.image,artifact)
  from image_eventing_runtime import validate_observer
  validate_observer(a.image,a.image_fault_library,a.image_fault_proof)
  for name,path in [('manifest',a.image_manifest),('fault_library',a.image_fault_library),('fault_proof',a.image_fault_proof),('admission',a.image_admission_manifest),('payload',a.image_manifest.with_name('payload.tar'))]:
   bound_inputs[name]={'path':str(path.resolve()),'sha256':sha(path)}
 else:artifact=sha(hub)
 assert artifact==a.artifact_sha256
 if a.phase=='healthy' and not reuse_image:
  assert not work.exists(),'Fresh work required';work.mkdir(parents=True,mode=0o700);frozen.mkdir(mode=0o700)
  if a.image:
   from image_qualification_inputs import freeze_inputs
   inputs,live_spec_drift=freeze_inputs(root,frozen,selected['specifications'])
  else:
   inputs={}
   for subtree in ('tests','scripts','components'):
    for source in sorted((root/subtree).rglob('*')):
     if not source.is_file() or '__pycache__'in source.parts or source.suffix not in('.py','.c','.exs','.json','.md','.yaml','.yml','.sh'):continue
     relative=source.relative_to(root);target=frozen/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);inputs[str(relative)]=sha(target)
  shutil.copyfile(Path(__file__),work/'matrix-driver.py')
 else:
  if a.phase=='private':
   previous=json.loads((work/'healthy-matrix.json').read_text());assert previous['passed'],'Healthy phase must pass before private faults'
  saved_plan=json.loads((work/'plan.json').read_text());inputs=saved_plan['frozen_inputs'];live_spec_drift=saved_plan.get('live_root_specification_drift',{})
 assert all(sha(frozen/n)==h for n,h in inputs.items()),'Frozen input changed'
 command=json.dumps(['elixir',str(hub)]) if hub else None;old=json.dumps(['elixir',str(legacy)]);rest=a.eventing_rest_url;private=a.private_rest_url
 hub_target=['--image',a.image,'--image-manifest',str(a.image_manifest.resolve())] if a.image else ['--command',command]
 fixture_target=['--image',a.image,'--image-manifest',str(a.image_manifest.resolve())] if a.image else ['--hub',str(hub)]
 fault_target=['--image-fault-library',str(a.image_fault_library.resolve()),'--image-fault-proof',str(a.image_fault_proof.resolve())] if a.image else []
 jobs=[]
 for name,file,extra in [('controls','eventing_controls.py',['--legacy-command',old]),('caps','eventing_filter_budget.py',[]),('dormant','eventing_dormant_policy.py',[]),('admin','eventing_admin_edit.py',[]),('policy','eventing_project_policy.py',[])]:
  jobs.append((name,file,hub_target+['--work',str(work/(name+'-work')),'--eventing-rest-url',rest]+extra))
 for name,file,extra in [('lostreply','eventing_faults.py',[]),('fairness','multi_fairness.py',[]),('cutover','eventing_cutover.py',[]),('cutover-decision','eventing_cutover.py',['--crash-at','transition-decision']),('cutover-project','eventing_cutover.py',['--crash-at','transition-project'])]:
  jobs.append((name,file,fixture_target+['--eventing-rest-url',rest,'--deadline','90']+extra+(fault_target if '--crash-at'in extra else [])))
 serial=[('retention','eventing_retention.py',hub_target+['--eventing-rest-url',private,'--owned-broker-container',a.owned_broker_container,'--work',str(work/'retention-work')]),('outage','eventing_acceptance.py',fixture_target+['--eventing-rest-url',private,'--broker-container',a.owned_broker_container,'--deadline','90']),('federation','federation_multi.py',hub_target+['--legacy-command',old,'--eventing-rest-urls',json.dumps([rest,a.federation_rest_url,private]),'--work',str(work/'federation-work')])]
 if a.phase=='healthy':
  plan={'schema':'adhd/image-eventing-plan@1' if a.image else 'adhd/native-eventing-plan@1','artifact_sha256':artifact,'legacy_sha256':sha(legacy),'runtime':{'kind':'docker','image_config_identity':a.image} if a.image else {'kind':'native'},'bound_inputs':bound_inputs,'live_root_specification_drift':live_spec_drift,'target_payload_audit':selected['audit'] if selected else None,'target_specifications':{name:hashlib.sha256(body).hexdigest()for name,body in selected['specifications'].items()} if selected else None,'scope':'Admitted38 recovery/backend normative payload; live-root presentation changes excluded and unqualified' if a.image else 'Native target declared authority','runner_sha256':sha(Path(__file__)),'parallelism':2,'runs_per_suite':1,'fail_fast':a.fail_fast,'no_live_provider':True,'frozen_inputs':inputs,'jobs':[{'name':n,'script':f,'arguments':v}for n,f,v in jobs+serial]}
  if reuse_image:assert plan==saved_plan,'Prepared image plan differs from current invocation/driver'
  else:(work/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 else:
  plan=json.loads((work/'plan.json').read_text());assert plan['artifact_sha256']==artifact and plan['legacy_sha256']==sha(legacy)
  assert plan.get('bound_inputs',{})==bound_inputs
  assert plan.get('runtime',{'kind':'native'})==({'kind':'docker','image_config_identity':a.image} if a.image else {'kind':'native'})
  assert plan.get('fail_fast',False)==a.fail_fast
  assert plan['jobs']==[{'name':n,'script':f,'arguments':v}for n,f,v in jobs+serial]
 if a.prepare_only:
  print('PREPARED all13 image eventing suites; no runtime execution',flush=True);return
 if a.image:
  assert a.reviewed_plan_sha256 and sha(work/'plan.json')==a.reviewed_plan_sha256,'Require reviewed exact image plan hash'
  assert sha(Path(__file__))==sha(work/'matrix-driver.py')==plan['runner_sha256'],'Running image driver differs from reviewed driver'
  from multi_image_core_matrix import claim_execution
  claim_execution(work,a.reviewed_plan_sha256,plan['runner_sha256'],a.phase+'-execution-started.json')
 if a.phase=='private':
  owned=subprocess.check_output(['docker','inspect','--format','{{index .Config.Labels "com.docker.compose.project"}}',a.owned_broker_container],text=True).strip();assert owned==a.owned_compose_project,'Disposable broker ownership mismatch'
 env=os.environ.copy();env['PYTHONPATH']=str(frozen/'tests')
 def run(job):
  name,file,args=job;report=work/(name+'.json');assert not report.exists(),'Refuse stale report reuse';print('START',name,flush=True)
  with(work/(name+'.log')).open('w')as log:r=subprocess.run([sys.executable,str(frozen/'tests'/file),*args,'--report',str(report)],cwd=frozen,env=env,stdout=log,stderr=subprocess.STDOUT)
  try:report_ok=report.exists() and json.loads(report.read_text()).get('passed') is True
  except (ValueError,TypeError,AttributeError):report_ok=False
  qualified=r.returncode==0 and report_ok
  print('DONE',name,r.returncode,'report_passed',report_ok,flush=True)
  return {'name':name,'exit_code':0 if qualified else 1,'exit_code_kind':'qualification','process_exit_code':r.returncode,'report_passed':report_ok,'report':report.name,'report_sha256':sha(report)if report.exists()else None,'log_sha256':sha(work/(name+'.log'))}
 selected=jobs
 if a.only:
  assert a.phase=='healthy','Subsets only apply to healthy phase'
  names=a.only.split(',');assert len(names)==len(set(names)) and set(names)<={j[0]for j in jobs}
  selected=[j for j in jobs if j[0]in names]
 planned=selected if a.phase=='healthy' else serial
 if a.phase=='healthy':results=bounded_jobs(planned,run,2,a.fail_fast)
 else:
  results=[]
  for job in planned:
   result=run(job);results.append(result)
   if a.fail_fast and result['exit_code']!=0:break
 unrun=[job[0]for job in planned if job[0]not in {row['name']for row in results}]
 unchanged=all(sha(frozen/n)==h for n,h in inputs.items()) and all(sha(Path(row['path']))==row['sha256'] for row in bound_inputs.values()) and sha(legacy)==plan['legacy_sha256'];value={'schema':'adhd/image-eventing-matrix@1' if a.image else 'adhd/native-eventing-matrix@1','passed':unchanged and not unrun and all(r['exit_code']==0 for r in results),'lifecycle_admitted':False,'artifact_sha256':artifact,'plan_sha256':sha(work/'plan.json'),'frozen_inputs_unchanged':unchanged,'runtime':plan['runtime'],'live_root_specification_drift':live_spec_drift,'scope':plan['scope'],'target_specifications':plan['target_specifications'],'bound_inputs':bound_inputs,'phase':a.phase,'selected_suites':[r['name']for r in results],'fail_fast':a.fail_fast,'planned_suites':[j[0]for j in planned],'executed_suites':[r['name']for r in results],'unrun_suites':unrun,'results':results}
 (work/(a.phase+'-matrix.json')).write_text(json.dumps(value,indent=2)+'\n');a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(value,indent=2)+'\n');sys.exit(0 if value['passed']else 1)

if __name__=='__main__':main()
