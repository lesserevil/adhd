"""Frozen complementary native eventing regression, controlled providers only."""
import argparse,concurrent.futures,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('hub','legacy-hub','repo-root','work','report'):p.add_argument('--'+key,type=Path,required=True)
 for key in ('artifact-sha256','eventing-rest-url','federation-rest-url','private-rest-url','owned-broker-container','owned-compose-project'):p.add_argument('--'+key,required=True)
 p.add_argument('--phase',choices=('healthy','private'),required=True)
 a=p.parse_args();root=a.repo_root.resolve();hub=a.hub.resolve();legacy=a.legacy_hub.resolve();work=a.work.resolve();frozen=work/'frozen'
 assert sha(hub)==a.artifact_sha256
 if a.phase=='healthy':
  assert not work.exists(),'Fresh work required';work.mkdir(parents=True,mode=0o700);frozen.mkdir(mode=0o700);inputs={}
  for subtree in ('tests','scripts','components'):
   for source in sorted((root/subtree).rglob('*')):
    if not source.is_file() or '__pycache__'in source.parts or source.suffix not in('.py','.c','.exs','.json','.md','.yaml','.yml','.sh'):continue
    relative=source.relative_to(root);target=frozen/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);inputs[str(relative)]=sha(target)
  shutil.copyfile(Path(__file__),work/'matrix-driver.py')
 else:
  previous=json.loads((work/'healthy-matrix.json').read_text());assert previous['passed'],'Healthy phase must pass before private faults'
  inputs=json.loads((work/'plan.json').read_text())['frozen_inputs']
 assert all(sha(frozen/n)==h for n,h in inputs.items()),'Frozen input changed'
 command=json.dumps(['elixir',str(hub)]);old=json.dumps(['elixir',str(legacy)]);rest=a.eventing_rest_url;private=a.private_rest_url
 jobs=[]
 for name,file,extra in [('controls','eventing_controls.py',['--legacy-command',old]),('caps','eventing_filter_budget.py',[]),('dormant','eventing_dormant_policy.py',[]),('admin','eventing_admin_edit.py',[]),('policy','eventing_project_policy.py',[])]:
  jobs.append((name,file,['--command',command,'--work',str(work/(name+'-work')),'--eventing-rest-url',rest]+extra))
 for name,file,extra in [('lostreply','eventing_faults.py',[]),('fairness','multi_fairness.py',[]),('cutover','eventing_cutover.py',[]),('cutover-decision','eventing_cutover.py',['--crash-at','transition-decision']),('cutover-project','eventing_cutover.py',['--crash-at','transition-project'])]:
  jobs.append((name,file,['--hub',str(hub),'--eventing-rest-url',rest,'--deadline','90']+extra))
 serial=[('retention','eventing_retention.py',['--command',command,'--eventing-rest-url',private,'--owned-broker-container',a.owned_broker_container,'--work',str(work/'retention-work')]),('outage','eventing_acceptance.py',['--hub',str(hub),'--eventing-rest-url',private,'--broker-container',a.owned_broker_container,'--deadline','90']),('federation','federation_multi.py',['--command',command,'--legacy-command',old,'--eventing-rest-urls',json.dumps([rest,a.federation_rest_url,private]),'--work',str(work/'federation-work')])]
 if a.phase=='healthy':
  plan={'schema':'adhd/native-eventing-plan@1','artifact_sha256':sha(hub),'legacy_sha256':sha(legacy),'runner_sha256':sha(Path(__file__)),'parallelism':2,'runs_per_suite':1,'no_live_provider':True,'frozen_inputs':inputs,'jobs':[{'name':n,'script':f,'arguments':v}for n,f,v in jobs+serial]};(work/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 else:
  plan=json.loads((work/'plan.json').read_text());assert plan['artifact_sha256']==sha(hub) and plan['legacy_sha256']==sha(legacy)
  assert plan['jobs']==[{'name':n,'script':f,'arguments':v}for n,f,v in jobs+serial]
  owned=subprocess.check_output(['docker','inspect','--format','{{index .Config.Labels "com.docker.compose.project"}}',a.owned_broker_container],text=True).strip();assert owned==a.owned_compose_project,'Disposable broker ownership mismatch'
 env=os.environ.copy();env['PYTHONPATH']=str(frozen/'tests')
 def run(job):
  name,file,args=job;report=work/(name+'.json');print('START',name,flush=True)
  with(work/(name+'.log')).open('w')as log:r=subprocess.run([sys.executable,str(frozen/'tests'/file),*args,'--report',str(report)],cwd=frozen,env=env,stdout=log,stderr=subprocess.STDOUT)
  print('DONE',name,r.returncode,flush=True)
  return {'name':name,'exit_code':r.returncode,'report':report.name,'report_sha256':sha(report)if report.exists()else None,'log_sha256':sha(work/(name+'.log'))}
 if a.phase=='healthy':
  with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:results=list(pool.map(run,jobs))
 else:results=[run(job)for job in serial]
 unchanged=all(sha(frozen/n)==h for n,h in inputs.items());value={'schema':'adhd/native-eventing-matrix@1','passed':unchanged and all(r['exit_code']==0 for r in results),'lifecycle_admitted':False,'artifact_sha256':sha(hub),'plan_sha256':sha(work/'plan.json'),'frozen_inputs_unchanged':unchanged,'phase':a.phase,'results':results}
 (work/(a.phase+'-matrix.json')).write_text(json.dumps(value,indent=2)+'\n');a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(value,indent=2)+'\n');sys.exit(0 if value['passed']else 1)

if __name__=='__main__':main()
