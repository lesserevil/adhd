import concurrent.futures, hashlib, json, os, pathlib, shutil, subprocess
root=pathlib.Path.cwd();out=root/'_build/roadmap/final/recovery-crash16';artifact=root/'_build/roadmap/multi/hub-filter-36-dev16.exs'
shutil.copytree(root/'tests',out/'tests',ignore=shutil.ignore_patterns('__pycache__'))
schema=out/'recovery-schema.json';shutil.copyfile(root/'components/hub/project-recovery/interface.schema.json',schema)
stages=['after-install-snapshot','before-stage-snapshot','after-stage-snapshot','before-decision','after-decision','after-decision-sync','after-install-checkpoint','after-route-selected','after-route-ready','after-completion','before-cleanup','after-cleanup']
cases=[('damaged-after-install-snapshot','after-install-snapshot',['--damage-stage']),('no-default-after-install-snapshot','after-install-snapshot',['--no-default']),('archived-before-cleanup','before-cleanup',['--archived'])]+[(s,s,[]) for s in stages]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan={'schema':'adhd/project-recovery-kill-matrix-plan@1','artifact_sha256':h(artifact),'frozen_tests':{str(p.relative_to(out/'tests')):h(p) for p in sorted((out/'tests').rglob('*')) if p.is_file()},'recovery_schema_sha256':h(schema),'cases':[{'name':n,'stage':s,'flags':flags} for n,s,flags in cases],'parallelism':2,'provider_calls':0,'scope':'Entire authored tests tree and schema copied once before launching any child; actual native16 Linux syscall-boundary SIGSTOP/SIGKILL and real Kafka. Includes complete twelve-boundary matrix and damaged decided target isolation. No admitted image/platform claim.'}
(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
env=dict(os.environ,PATH=str(root/'_build/federation/native/erlang/bin')+':'+str(root/'_build/federation/native/elixir/bin')+':/usr/local/bin:/usr/bin:/bin',ERL_FLAGS='+S 2:2')
def run(case):
 name,stage,flags=case
 argv=[str(root/'.venv/bin/python'),str(out/'tests/project_recovery_crash.py'),'--hub',str(artifact),'--recovery-schema',str(schema),'--crash-at',stage,'--deadline','60','--keep-work',str(root/'_build/kafka'/('recovery-crash16-'+name)),'--report',str(out/(name+'.json'))]+flags
 with (out/(name+'.log')).open('w') as log:r=subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT)
 value={'case':name,'stage':stage,'exit_code':r.returncode};print(json.dumps(value),flush=True);return value
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,cases))
(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(any(x['exit_code'] for x in results))
