"""One frozen native core/migration regression ladder; controlled fixtures only."""
import argparse,concurrent.futures,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('hub','legacy-hub','repo-root','work','report'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--artifact-sha256',required=True);p.add_argument('--eventing-rest-url',required=True)
 p.add_argument('--parallelism',type=int,choices=(1,2,3,4),default=2)
 a=p.parse_args();root=a.repo_root.resolve();hub=a.hub.resolve();legacy=a.legacy_hub.resolve();work=a.work.resolve()
 assert sha(hub)==a.artifact_sha256,'Frozen artifact mismatch'
 assert not work.exists(),'Qualification work directory must be fresh'
 work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
 inputs={}
 for subtree in ('tests','scripts','components'):
  for source in sorted((root/subtree).rglob('*')):
   if not source.is_file() or '__pycache__'in source.parts or source.suffix not in('.py','.c','.exs','.json','.md','.yaml','.yml','.sh'):continue
   relative=source.relative_to(root);target=frozen/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
   inputs[str(relative)]=sha(target)
 shutil.copyfile(Path(__file__),work/'matrix-driver.py')
 command=json.dumps(['elixir',str(hub)]);base=['--hub',str(hub),'--eventing-rest-url',a.eventing_rest_url,'--with-model'];old=['--legacy-hub',str(legacy)]
 jobs=[('foundation','foundation_acceptance.py',['--command',command,'--protocol-version','2']),('multi','multi_acceptance.py',base),('store-move','multi_store_move.py',base),('move-no-default','multi_store_move.py',base+['--no-default']),('hot','multi_hot.py',base),('aliases','multi_aliases.py',base+old),('backend-models','multi_model_capabilities.py',base),('auth','auth_lifecycle.py',['--command',command]),('storage-crash','storage_recovery.py',['--command',command])]
 for stage in ('before-decision','after-decision','after-first-snapshot','after-first-checkpoint','before-config','after-config','before-cleanup'):
  jobs.append(('movefault-'+stage,'multi_store_move_fault.py',base+['--crash-at',stage]))
 migrations=[('ordinary',[])]+[(s,['--crash-at',s])for s in ('before-prepared','before-decided','before-config','after-snapshot','before-completed')]+[('damage-'+x,['--damage-backup',x,'--crash-at',s])for x,s in (('config','before-decided'),('backend','before-config'),('snapshot','after-snapshot'))]
 for name,extra in migrations:jobs.append(('migration-'+name,'multi_migration.py',base+old+extra))
 plan={'schema':'adhd/native-core-plan@1','artifact_sha256':sha(hub),'legacy_sha256':sha(legacy),'runner_sha256':sha(Path(__file__)),'parallelism':a.parallelism,'no_live_provider':True,'frozen_inputs':inputs,'jobs':[{'name':n,'script':f,'arguments':args}for n,f,args in jobs]}
 (work/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 env=os.environ.copy();env['PYTHONPATH']=str(frozen/'tests')
 def run(job):
  name,file,args=job;report=work/(name+'.json');cmd=[sys.executable,str(frozen/'tests'/file),*args,'--report',str(report)]
  if '--hub'in args:cmd+=['--keep-work',str(work/name)]
  print('START',name,flush=True)
  with(work/(name+'.log')).open('w')as log:r=subprocess.run(cmd,cwd=frozen,env=env,stdout=log,stderr=subprocess.STDOUT)
  print('DONE',name,r.returncode,flush=True)
  result={'name':name,'exit_code':r.returncode,'report':report.name,'report_sha256':sha(report)if report.exists()else None,'log_sha256':sha(work/(name+'.log'))}
  return result
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.parallelism)as pool:results=list(pool.map(run,jobs))
 native=work/'native.json'
 with native.open('w')as out,(work/'native.stderr').open('w')as err:r=subprocess.run(['elixir',str(hub),'--litai-test'],cwd=frozen,env=env,stdout=out,stderr=err)
 results.append({'name':'native','exit_code':r.returncode,'report':native.name,'report_sha256':sha(native),'stderr_sha256':sha(work/'native.stderr')})
 # Detect mutation of frozen inputs even when source work continued elsewhere.
 unchanged=all(sha(frozen/path)==digest for path,digest in inputs.items())
 value={'schema':'adhd/native-core-matrix@1','passed':unchanged and all(x['exit_code']==0 for x in results),'lifecycle_admitted':False,'artifact_sha256':sha(hub),'plan_sha256':sha(work/'plan.json'),'frozen_inputs_unchanged':unchanged,'results':results}
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(value,indent=2)+'\n')
 sys.exit(0 if value['passed']else 1)

if __name__=='__main__':main()
