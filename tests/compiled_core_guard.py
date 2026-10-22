#!/usr/bin/env python3
"""Closed outer admission for an unchanged prepared core13 executor.

Preparation and verification never start children. Execute requires a reviewed
plan, Python isolated mode, and exclusive durable once. Original max2 child
scheduling/assertions/deadlines are retained and explicitly reported.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

sys.dont_write_bytecode=True

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def regular(path):
 p=Path(path).absolute();s=p.lstat();assert p.resolve(strict=True)==p and stat.S_ISREG(s.st_mode) and s.st_nlink==1;return p

def inventory(root):
 root=Path(root);assert root.resolve(strict=True)==root and not root.is_symlink()
 files={};directories=[]
 for p in sorted(root.rglob('*')):
  assert not p.is_symlink()
  assert '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')
  if p.is_dir():directories.append(str(p.relative_to(root)));continue
  regular(p);files[str(p.relative_to(root))]=sha(p)
 return {'files':files,'directories':directories}

def write(path,body):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
 fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def helper(path):
 spec=importlib.util.spec_from_file_location('closed_filesystem_inputs',regular(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def verify(work,plan):
 assert work.resolve(strict=True)==work and not work.is_symlink()
 assert sha(regular(__file__))==sha(work/'guard.py')==plan['driver_sha256']
 core=Path(plan['core_work']);assert core.resolve(strict=True)==core
 assert sha(regular(core/'plan.json'))==plan['core_plan_sha256']
 assert sha(regular(core/'driver.py'))==plan['core_driver_sha256']
 assert inventory(core/'frozen')==plan['frozen']
 assert inventory(work/'admission')==plan['admission']
 assert inventory(work/'docker-config')==plan['docker_config']
 assert (work/'docker-config/config.json').read_bytes()==b'{}'
 assert inventory(Path(plan['context']))==plan['context_inputs']
 for name,digest in plan['bound_inputs'].items():assert sha(regular(core/name))==digest
 assert str(Path(sys.executable).absolute())==plan['tools']['python']['path']
 assert str(Path('/proc/self/exe').resolve())==plan['tools']['python']['realpath']
 fs=helper(core/'frozen/tests/image_filesystem_matrix.py')
 for item in plan['external_inputs']:assert fs.external(item['path'])==item
 for tree in plan['tool_trees']:assert fs.tool_tree(tree['root'])==tree
 socket=Path(plan['socket']['path']);s=socket.stat()
 assert socket.resolve()==socket and stat.S_ISSOCK(s.st_mode) and [s.st_dev,s.st_ino]==plan['socket']['identity']
 assert plan['programs']==13 and plan['maximum_child_parallelism']==2
 return True

def prepare(args):
 root=regular(args.core_work/'plan.json').parent;core=json.loads((root/'plan.json').read_text());assert not core['started'] and len(core['jobs'])==13
 assert not (root/'execution-started.json').exists() and not (root/'matrix.json').exists()
 assert core['parallelism_after_first_two']==2 and core['first_two_serial']
 work=args.work.absolute();assert work.resolve()==work and not work.exists();work.mkdir(mode=0o700,parents=True)
 fs=helper(root/'frozen/tests/image_filesystem_matrix.py');context=args.context.absolute();admission=regular(args.admission_manifest)
 assert sha(admission)==core['admission_manifest_sha256']
 admitted=json.loads(admission.read_text());assert admitted['image_config_identity']==core['image_config_identity'] and admitted['passed']
 assert admitted['canonical_manifest_sha256']==core['canonical_manifest_sha256']
 (work/'admission').mkdir(mode=0o700)
 for name,digest in {'manifest.json':sha(admission),**admitted['files']}.items():
  assert Path(name).name==name and name not in ('.','..')
  src=regular(admission.parent/name);assert sha(src)==digest;write(work/'admission'/name,src.read_bytes())
 (work/'docker-config').mkdir(mode=0o700);write(work/'docker-config/config.json',b'{}')
 write(work/'guard.py',regular(__file__).read_bytes())
 tools={n:fs.external(p) for n,p in [('python',sys.executable),('docker','/usr/bin/docker'),('flock','/usr/bin/flock')]}
 sock=Path('/var/run/docker.sock').resolve();info=sock.stat();assert stat.S_ISSOCK(info.st_mode)
 plan={'schema':'adhd/compiled-core13-outer-plan@1','prepared':True,'executed':False,'root_GO_required':True,
       'driver_sha256':sha(work/'guard.py'),'core_work':str(root),'core_plan_sha256':sha(root/'plan.json'),
       'core_driver_sha256':sha(root/'driver.py'),'image':core['image_config_identity'],'artifact_sha256':core['artifact_sha256'],
       'canonical_manifest_sha256':core['canonical_manifest_sha256'],'admission_sha256':sha(admission),
       'frozen':inventory(root/'frozen'),'admission':inventory(work/'admission'),'docker_config':inventory(work/'docker-config'),'bound_inputs':core['bound_inputs'],
       'context':str(context),'context_inputs':inventory(context),'tools':tools,
       'tool_trees':[fs.tool_tree(args.repo_root/p) for p in ['.venv','_build/federation/native/elixir','_build/federation/native/erlang']],
       'external_inputs':list(tools.values())+[fs.external(core['legacy_hub'])],
       'socket':{'path':str(sock),'identity':[info.st_dev,info.st_ino]},'programs':13,'maximum_child_parallelism':2,
       'scheduling_scope':'Original first2 serial then bounded max2 unchanged; one outer core family. No new test assertions, concurrency or deadlines.',
       'argv':[tools['python']['path'],str(root/'driver.py'),'--execute','--repo-root',str(args.repo_root),'--work',str(root),'--plan-sha256',sha(root/'plan.json')],
       'timeout_policy':'Original harness bounds only; no new outer timeout','automatic_retries':0,'provider_calls_authorized':0}
 write(work/'plan.json',(json.dumps(plan,indent=2)+'\n').encode());verify(work,plan)
 print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json')}))

def execute(args):
 work=args.work.absolute();assert Path(__file__).name=='guard.py' and sys.flags.isolated
 assert sha(work/'plan.json')==args.plan_sha256;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
 write(work/'execution.started',json.dumps({'plan_sha256':args.plan_sha256}).encode())
 env={k:v for k,v in os.environ.items() if not k.startswith(('LD_','PYTHON','DOCKER_','ERL_','ELIXIR_'))}
 core=Path(plan['core_work']);env.update(DOCKER_HOST='unix://'+plan['socket']['path'],DOCKER_CONFIG=str(work/'docker-config'),PYTHONPATH=str(core/'frozen/tests'),PYTHONDONTWRITEBYTECODE='1',ERL_FLAGS='+S 2:2',PATH=str(Path(plan['tools']['python']['path']).parent)+':'+str(Path(plan['tool_trees'][1]['root'])/'bin')+':'+str(Path(plan['tool_trees'][2]['root'])/'bin')+':/usr/bin:/bin')
 row={'passed':False,'started':False};primary=None
 try:
  with (work/'core.log').open('xb') as log:
   child=subprocess.Popen(plan['argv'],cwd=plan['core_work'],env=env,stdout=log,stderr=subprocess.STDOUT);row.update(started=True,host_child_pid=child.pid)
   row['exit_code']=child.wait()
  result=json.loads((core/'matrix.json').read_text());assert row['exit_code']==0 and result['passed'] is True
  verify(work,plan);row['passed']=True
 except BaseException as error:primary=error;row['failure_type']=type(error).__name__;raise
 finally:
  if 'child' in locals() and child.poll() is None:
   # No process-group kill: the original harness owns Docker cleanup. Join the
   # original child on interruption and retain the primary exception afterwards.
   child.wait()
  row.update(plan_sha256=args.plan_sha256,core_matrix_sha256=sha(core/'matrix.json') if (core/'matrix.json').exists() else None)
  write(work/'result.json',(json.dumps(row,indent=2)+'\n').encode())

def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--execute',action='store_true')
 p.add_argument('--work',type=Path,required=True);p.add_argument('--core-work',type=Path);p.add_argument('--repo-root',type=Path);p.add_argument('--context',type=Path);p.add_argument('--admission-manifest',type=Path);p.add_argument('--plan-sha256');args=p.parse_args()
 prepare(args) if args.prepare else execute(args)
if __name__=='__main__':main()
