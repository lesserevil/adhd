import json,os,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path('/home/horde/src/adhd')
OUT=ROOT/'_build/acme/finaldocs01'
OUT.mkdir(exist_ok=True)
name=sys.argv[1];args=sys.argv[2:]
assert name and '/' not in name
stdout=OUT/(name+'.json');stderr=OUT/(name+'.stderr');record=OUT/(name+'-execution.json')
assert not any(p.exists()for p in [stdout,stderr,record]),'Never overwrite an actual command result'
cli=[str(ROOT/'_build/federation/litai/bin/python'),str(ROOT/'_build/federation/litai/bin/litai')]
env=os.environ.copy();env.update(PATH=str(ROOT/'_build/federation/native/erlang/bin')+':'+str(ROOT/'_build/federation/native/elixir/bin')+':'+env['PATH'],ERL_FLAGS='+S 2:2',PYTHONDONTWRITEBYTECODE='1',GH_CONFIG_DIR=str(ROOT/'.git/gh-lesserevil'),LITAI_CODING_PROVIDER='coding-cli',CODING_CLI='codex')
start=time.monotonic()
with stdout.open('xb')as o,stderr.open('xb')as e:
 p=subprocess.run(cli+args,cwd=ROOT,env=env,stdout=o,stderr=e)
v={'argv':cli+args,'actual_exit_code':p.returncode,'duration_seconds':time.monotonic()-start,'stdout_sha256':hashlib.sha256(stdout.read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256(stderr.read_bytes()).hexdigest(),'environment_overlay':{k:env[k]for k in ['PATH','ERL_FLAGS','PYTHONDONTWRITEBYTECODE','GH_CONFIG_DIR','LITAI_CODING_PROVIDER','CODING_CLI']}}
record.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v));sys.exit(p.returncode)
