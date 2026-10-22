#!/usr/bin/env python3
"""Freeze the unchanged four-check stale-owner gate for one admitted image."""
import sys
sys.dont_write_bytecode=True
_STAGED=__file__.rsplit('/',1)[-1]=='driver.py'
if __name__=='__main__' and '--execute' in sys.argv:
 assert _STAGED and sys.flags.isolated,'Execute frozen driver.py with python -I only'
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

NAMES=['stale-owner']


def sha(path):
 value=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(1048576),b''):value.update(block)
 return value.hexdigest()


def plain(path):
 path=Path(path).absolute();info=path.lstat()
 assert path.resolve(strict=True)==path and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and not path.is_symlink(),str(path)
 return path


def save(path,value):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.chmod(0o600);tmp.replace(path)


def inventory(root):
 assert root.is_absolute() and root.resolve(strict=True)==root and root.is_dir() and not root.is_symlink()
 files={};dirs=[]
 for path in sorted(root.rglob('*')):
  info=path.lstat();assert not stat.S_ISLNK(info.st_mode),str(path)
  name=str(path.relative_to(root))
  if stat.S_ISDIR(info.st_mode):dirs.append(name)
  else:assert stat.S_ISREG(info.st_mode) and info.st_nlink==1;files[name]=sha(path)
 return {'files':files,'directories':dirs}


def check_tree(root,expected):
 actual=inventory(root);assert actual==expected,'Frozen complete file/directory set or bytes changed: '+str(root)


def external(path):
 path=Path(path).absolute();real=path.resolve(strict=True);assert real.is_file()
 return {'path':str(path),'realpath':str(real),'sha256':sha(real),'symlink':os.readlink(path) if path.is_symlink() else None}


def tool_tree(root):
 root=Path(root).absolute();assert root.resolve(strict=True)==root and root.is_dir()
 rows={};directories=[]
 for path in sorted(root.rglob('*')):
  if '__pycache__' in path.parts or path.suffix in ('.pyc','.pyo'):continue
  relative=str(path.relative_to(root));info=path.lstat()
  if stat.S_ISDIR(info.st_mode):directories.append(relative)
  elif stat.S_ISLNK(info.st_mode) and path.resolve(strict=True).is_dir():
   target=path.resolve(strict=True);assert target.is_relative_to(root)
   rows[relative]={'directory_symlink':os.readlink(path),'realpath':str(target)}
  else:
   assert stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
   rows[relative]=external(path)
 return {'root':str(root),'files':rows,'directories':directories}



def target_bindings(plan):
 image,artifact,admission=plan['image_config_identity'],plan['artifact_sha256'],plan['admission_sha256']
 assert all(isinstance(v,str) for v in (image,artifact,admission))
 assert re.fullmatch('sha256:[a-f0-9]{64}',image)
 assert re.fullmatch('[a-f0-9]{64}',artifact) and re.fullmatch('[a-f0-9]{64}',admission)
 return image,artifact,admission



def verify(work,plan):
 assert work.resolve(strict=True)==work and not work.is_symlink()
 actual=plain(Path(__file__));assert sha(actual)==sha(work/'driver.py')==plan['driver_sha256']
 image,artifact,admission=target_bindings(plan)
 assert sha(work/'bound/admission.json')==admission
 admitted=json.loads((work/'bound/admission.json').read_text());assert admitted['passed'] and admitted['image_config_identity']==image and admitted['artifact_sha256']==artifact
 manifest=json.loads((work/'bound/image-manifest.json').read_text());assert manifest['files']['hub.exs']==artifact
 assert sha(work/'bound/source-target.exs')==artifact and sha(work/'bound/image-manifest.json')==plan['canonical_manifest_sha256']
 assert sha(work/'frozen/tests/image_stale_owner_matrix.py')==plan['driver_sha256']
 assert [r['name'] for r in plan['jobs']]==NAMES and plan['parallelism']==1 and plan['automatic_retries']==0
 check_tree(work/'frozen',plan['frozen']);check_tree(work/'bound',plan['bound'])
 for tree in plan['tool_trees']:assert tool_tree(tree['root'])==tree,'Native/Python tool closure drift'
 for row in plan['external_inputs']:
  path=Path(row['path']);assert path.resolve(strict=True)==Path(row['realpath']) and sha(row['realpath'])==row['sha256']
  assert (os.readlink(path) if path.is_symlink() else None)==row['symlink']
 socket=Path(plan['docker_socket']['path']);info=socket.stat()
 assert socket.resolve(strict=True)==socket and stat.S_ISSOCK(info.st_mode) and [info.st_dev,info.st_ino]==plan['docker_socket']['identity']
 assert plan['tools']['python']['path']==str(Path(sys.executable).absolute())
 assert Path('/proc/self/exe').resolve()==Path(plan['tools']['python']['realpath'])
 return True


def prepare(args):
 root=Path(args.repo_root).absolute();assert root.resolve(strict=True)==root
 image,artifact,admission_hash=target_bindings({'image_config_identity':args.image,'artifact_sha256':args.artifact_sha256,'admission_sha256':args.admission_sha256})
 work=Path(args.work).absolute();assert work.resolve()==work and not work.exists();work.mkdir(parents=True,mode=0o700)
 source=plain(root/'tests/image_qualification_inputs.py');spec=importlib.util.spec_from_file_location('_reviewed_image_inputs',source);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
 context=Path(args.context).absolute();admission=plain(args.admission_manifest)
 selected=reader.reviewed_payload(context/'manifest.json',admission,admission_hash,image,artifact)
 assert len(selected['specifications'])==selected['audit']['canonical_specifications']
 frozen=work/'frozen';frozen.mkdir(mode=0o700)
 for tree in ('tests','scripts','deploy'):
  for path in sorted((root/tree).rglob('*')):
   assert not path.is_symlink(),str(path)
   if path.is_dir() or '__pycache__' in path.parts:continue
   assert path.is_file();target=frozen/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
 shutil.copyfile(plain(Path(__file__)),frozen/'tests/image_stale_owner_matrix.py')
 for name,body in selected['specifications'].items():
  target=frozen/'components/hub'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
 bound=work/'bound';bound.mkdir(mode=0o700)
 for source,name in [(context/'manifest.json','image-manifest.json'),(admission,'admission.json')]:shutil.copyfile(plain(source),bound/name)
 (bound/'source-target.exs').write_bytes(selected['artifact_bytes']);assert sha(bound/'source-target.exs')==artifact
 (bound/'payload.tar.sha256').write_text(selected['payload_sha256']+'\n')
 tools={name:external(path) for name,path in [('python',sys.executable),('docker','/usr/bin/docker'),('elixir',root/'_build/federation/native/elixir/bin/elixir'),('erl',root/'_build/federation/native/erlang/bin/erl')]}
 arguments=['--image',image,'--image-manifest',str(bound/'image-manifest.json'),'--work',str(work/'fixtures/stale-owner')]
 jobs=[{'name':'stale-owner','script':'federation_stale_owner.py','arguments':arguments,'expected_check_count':4,'argv':[tools['python']['path'],str(frozen/'tests/federation_stale_owner.py')]+arguments+['--report',str(work/'stale-owner.json')]}]
 docker_config=bound/'docker-config';docker_config.mkdir(mode=0o700);(docker_config/'config.json').write_text('{}')
 socket=Path('/var/run/docker.sock').resolve(strict=True);info=socket.stat();assert stat.S_ISSOCK(info.st_mode)
 runtime=work/'runtime';runtime.mkdir(mode=0o700);shutil.copyfile(plain(Path(__file__)),work/'driver.py')
 plan={'schema':'adhd/image-stale-owner-plan@1','scope':'Exactly four unchanged stale-canonical-owner checks, controlled local model, eventing disabled. Separate from federation14/Kafka; no live provider or release claim.',
  'image_config_identity':image,'artifact_sha256':artifact,'admission_sha256':admission_hash,'canonical_manifest_sha256':sha(bound/'image-manifest.json'),
  'payload_sha256':selected['payload_sha256'],'payload_audit':selected['audit'],'target_specifications':len(selected['specifications']),
  'frozen':inventory(frozen),'bound':inventory(bound),'driver_sha256':sha(work/'driver.py'),'unchanged_harness_sha256':sha(root/'tests/federation_stale_owner.py'),
  'docker_socket':{'path':str(socket),'identity':[info.st_dev,info.st_ino]},
  'external_inputs':[external(context/'manifest.json'),external(context/'payload.tar'),external(admission)]+list(tools.values()),
  'tools':tools,'tool_trees':[tool_tree(root/'.venv'),tool_tree(root/'_build/federation/native/elixir'),tool_tree(root/'_build/federation/native/erlang')],
  'jobs':jobs,'parallelism':1,'runs_per_case':1,'automatic_retries':0,'first_failure_stops':True,'runtime_cwd':str(runtime),
  'outer_timeout_seconds':None,'timeout_policy':'Original unchanged harness wait12/query3000ms/catalogTTL10000ms and all existing assertions; no invented outer timeout',
  'lane_lock':str(root/'_build/roadmap/image-stale-owner.lane.lock'),'provider_calls_authorized':0,'preparation_app_compiler_or_service_starts':0,'execution_status':'UNSTARTED_REVIEW_REQUIRED'}
 save(work/'plan.json',plan);verify(work,plan);print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json'),'work':str(work),'jobs':1}))


def absent(result,identifier):
 return result.returncode==1 and result.stdout.strip() in (b'',b'[]') and re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier),result.stderr.decode(errors='replace').strip()) is not None


def qualify(value,job,plan):
 image,artifact,_=target_bindings(plan)
 assert value['passed'] is True and value['artifact_sha256']==artifact
 assert value['schema']=='adhd/federation-v2-stale-canonical-owner@1'
 rows=value['checks'];assert len(rows)==4 and all(row['passed'] for row in rows)
 runtime=value['runtime'];assert runtime['kind']=='docker' and runtime['image_config_identity']==image and runtime['artifact_sha256']==artifact
 assert runtime['canonical_manifest_sha256']==plan['canonical_manifest_sha256']
 events=runtime['container_lifecycle'];started={e['container_id'] for e in events if e['action']=='started'}
 closed={e['container_id'] for e in events if e['action'] in ('hard-killed','stopped') and e.get('observed_absent') and e.get('wait_observed')}
 assert len(started)==4 and started<=closed
 assert any(e['action']=='stopped' for e in events)
 assert value['harness_sha256']==plan['unchanged_harness_sha256']
 return sorted(started),[]


def execute(work,digest):
 assert digest and sha(work/'plan.json')==digest
 plan=json.loads((work/'plan.json').read_text());verify(work,plan)
 image,artifact,_=target_bindings(plan)
 lock=Path(plan['lane_lock']);lock.parent.mkdir(parents=True,exist_ok=True)
 with lock.open('a') as lane:
  fcntl.flock(lane,fcntl.LOCK_EX|fcntl.LOCK_NB)
  marker=os.open(work/'execution.started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(marker,'w') as stream:json.dump({'plan_sha256':digest,'driver_sha256':plan['driver_sha256']},stream);stream.flush();os.fsync(stream.fileno())
  fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  env=os.environ.copy();env.update(PYTHONPATH=str(work/'frozen/tests'),PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(work/'runtime/pycache'),ERL_FLAGS='+S 2:2',
    PATH=str(Path(plan['tools']['python']['path']).parent)+':'+str(Path(plan['tools']['elixir']['path']).parent)+':'+str(Path(plan['tools']['erl']['path']).parent)+':/usr/bin:/bin')
  for key in list(env):
   if key.startswith(('DOCKER_','LD_','ERL_','ELIXIR_','PYTHON')) or key.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy'):env.pop(key)
  env.update(PYTHONPATH=str(work/'frozen/tests'),PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(work/'runtime/pycache'),ERL_FLAGS='+S 2:2')
  env.update(DOCKER_HOST='unix://'+plan['docker_socket']['path'],DOCKER_CONFIG=str(work/'bound/docker-config'),NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
  results=[];failure=None
  try:
   for job in plan['jobs']:
    verify(work,plan);report=work/(job['name']+'.json');log=work/(job['name']+'.log');assert not report.exists() and not log.exists()
    row={'name':job['name'],'attempted':True,'started':False,'passed':False,'process_exit_code':None};results.append(row);print('START',job['name'],flush=True)
    with log.open('x') as output:child=subprocess.run(job['argv'],cwd=plan['runtime_cwd'],env=env,stdout=output,stderr=subprocess.STDOUT)
    row.update(started=True,process_exit_code=child.returncode)
    assert child.returncode==0 and report.is_file(),'Actual child failed or no report; no retry'
    ids,names=qualify(json.loads(report.read_text()),job,plan)
    for identifier in ids+names:
     assert re.fullmatch('[a-f0-9]{64}|adhd-(?:fs-codec|accept-probe)-[a-f0-9]{16}',identifier)
     result=subprocess.run([plan['tools']['docker']['path'],'inspect',identifier],capture_output=True,timeout=30,env=env)
     assert absent(result,identifier),'Independent actual owned container absence unconfirmed'
    row.update(passed=True,independently_absent_ids=ids,independently_absent_codec_names=names);print('DONE',job['name'],True,flush=True)
  except BaseException as error:failure=type(error).__name__;raise
  finally:
   try:verify(work,plan);unchanged=True
   except BaseException:unchanged=False
   for row in results:
    for suffix,key in [('.json','report_sha256'),('.log','log_sha256')]:
     path=work/(row['name']+suffix)
     if path.is_file():row[key]=sha(path)
   executed=[r['name'] for r in results if r['started']];unrun=[j['name'] for j in plan['jobs'] if j['name'] not in executed]
   save(work/'matrix.json',{'schema':'adhd/image-stale-owner-result@1','passed':not failure and unchanged and not unrun and all(r['passed'] for r in results),
     'plan_sha256':digest,'image_config_identity':image,'artifact_sha256':artifact,'scope':plan['scope'],'input_closure_unchanged':unchanged,
     'failure_type':failure,'cleanup_confirmed':all(r['passed'] for r in results) and bool(results),'attempted':[r['name'] for r in results],'executed':executed,'unrun':unrun,'results':results})
 return 0 if unchanged and not unrun and all(r['passed'] for r in results) else 1


def main():
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--plan-sha256')
 for name in ('repo-root','context','admission-manifest'):parser.add_argument('--'+name,type=Path)
 for name in ('image','artifact-sha256','admission-sha256'):parser.add_argument('--'+name)
 args=parser.parse_args()
 if args.prepare:prepare(args)
 else:assert _STAGED;sys.exit(execute(args.work.absolute(),args.plan_sha256))


if __name__=='__main__':main()
