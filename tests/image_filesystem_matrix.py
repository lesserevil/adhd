#!/usr/bin/env python3
"""Freeze, review, then run the unchanged native38 filesystem ladder in an explicitly admitted image."""
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

BASIS_ARTIFACT='1741225b1a276770ec9f6631e63fe8646ee5f22808fad8a5acfe67a8aed11bd7'
LEGACY='1d3459aab65c295b8edb988dbf7bf716ecece78e9e7e7062ec19312984ee7d48'
SOURCES=('multi_fault.c','store_move_fault.c','storage_write_fault.c','project_recovery_fault.c','rebind_fault.c')
MOVE=('before-decision','after-decision','after-first-snapshot','after-first-checkpoint','before-config','after-config','before-cleanup')
MIGRATE=('before-prepared','before-decided','before-config','after-snapshot','before-completed')
NAMES=['storage-crash']+['movefault-'+n for n in MOVE]+['migration-ordinary']+['migration-'+n for n in MIGRATE]+['migration-damage-'+n for n in ('config','backend','snapshot')]


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
 assert sha(work/'frozen/tests/image_filesystem_matrix.py')==plan['driver_sha256']
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


def selected_native_jobs(native):
 jobs={row['name']:row for row in native['jobs']};assert all(n in jobs for n in NAMES)
 rows=[jobs[n] for n in NAMES]
 assert rows[0]['script']=='storage_recovery.py' and rows[0]['arguments']==['--command',json.dumps(['elixir',next(r['arguments'][1] for r in rows if r['script']=='multi_migration.py')])]
 for row in rows[1:]:
  assert row['arguments'][0]=='--hub' and '--eventing-rest-url' in row['arguments'] and '--with-model' in row['arguments']
 for row in rows[1:]:
  expected_script='multi_store_move_fault.py' if row['name'].startswith('movefault-') else 'multi_migration.py'
  assert row['script']==expected_script
  if row['name'].startswith('movefault-'):
   assert row['arguments'][row['arguments'].index('--crash-at')+1]==row['name'].removeprefix('movefault-')
  elif row['name'].startswith('migration-') and row['name'].removeprefix('migration-') in MIGRATE:
   assert row['arguments'][row['arguments'].index('--crash-at')+1]==row['name'].removeprefix('migration-')
 for target,stage in [('config','before-decided'),('backend','before-config'),('snapshot','after-snapshot')]:
  args=jobs['migration-damage-'+target]['arguments'];assert args[args.index('--damage-backup')+1]==target and args[args.index('--crash-at')+1]==stage
 return rows


def prepare(args):
 root=Path(args.repo_root).absolute();assert root.resolve(strict=True)==root
 work=Path(args.work).absolute();assert work.resolve()==work and not work.exists();work.mkdir(parents=True,mode=0o700)
 # Read only the current-root pure payload reader; no runtime or compiler entry.
 source=plain(root/'tests/image_qualification_inputs.py');spec=importlib.util.spec_from_file_location('_reviewed_image_inputs',source);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
 image,artifact,admission_hash=target_bindings({'image_config_identity':args.image,'artifact_sha256':args.artifact_sha256,'admission_sha256':args.admission_sha256})
 context=Path(args.context).absolute();admission=plain(args.admission_manifest)
 selected=reader.reviewed_payload(context/'manifest.json',admission,admission_hash,image,artifact)
 assert len(selected['specifications'])==33
 native=plain(args.native_plan);nv=json.loads(native.read_text());assert nv['artifact_sha256']==BASIS_ARTIFACT and nv['legacy_sha256']==LEGACY
 basis=selected_native_jobs(nv)
 frozen=work/'frozen';frozen.mkdir(mode=0o700)
 for tree in ('tests','scripts','deploy'):
  for path in sorted((root/tree).rglob('*')):
   assert not path.is_symlink(),str(path)
   if path.is_dir() or '__pycache__' in path.parts:continue
   assert path.is_file();target=frozen/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
 # Bind this reviewed driver as both executable and frozen helper, never an older root copy.
 shutil.copyfile(plain(Path(__file__)),frozen/'tests/image_filesystem_matrix.py')
 drift={}
 for name,body in selected['specifications'].items():
  target=frozen/'components/hub'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
  current=root/'components/hub'/name
  if not current.is_file() or sha(current)!=hashlib.sha256(body).hexdigest():drift[name]=sha(current) if current.is_file() else None
 bound=work/'bound';bound.mkdir(mode=0o700)
 for source,name in [(context/'manifest.json','image-manifest.json'),(admission,'admission.json'),(native,'native-plan.json')]:shutil.copyfile(plain(source),bound/name)
 (bound/'source-target.exs').write_bytes(selected['artifact_bytes']);assert sha(bound/'source-target.exs')==artifact
 (bound/'payload.tar.sha256').write_text(selected['payload_sha256']+'\n')
 abi=Path(args.abi_root).absolute();assert abi.resolve(strict=True)==abi
 proofbindings={}
 for name in SOURCES:
  destination=bound/'observers'/name.removesuffix('.c');destination.mkdir(parents=True,mode=0o700)
  source_library=plain(abi/'build'/name.removesuffix('.c')/'observer.so');source_proof=plain(abi/(name+'.proof.json'))
  shutil.copyfile(source_library,destination/'observer.so');shutil.copyfile(source_proof,destination/'proof.json')
  report=json.loads(source_proof.read_text());assert report['passed'] and report['image_config_identity']==image and report['artifact_sha256']==artifact
  assert report['canonical_manifest_sha256']==sha(bound/'image-manifest.json') and report['observer']['source_sha256']==sha(frozen/'tests'/name)
  assert report['observer']['library_sha256']==sha(destination/'observer.so') and report['owned_container_absent'] and report['exit_code']==137
  assert report['successful_abi_cases']==sorted(report['observer']['exported_symbols'])
  proofbindings[name]={'library':str(destination/'observer.so'),'proof':str(destination/'proof.json'),'source_library':external(source_library),'source_proof':external(source_proof)}
 original_artifact=plain(basis[1]['arguments'][1]);assert sha(original_artifact)==BASIS_ARTIFACT
 legacy=plain(next(row['arguments'][row['arguments'].index('--legacy-hub')+1] for row in basis if '--legacy-hub' in row['arguments']));assert sha(legacy)==LEGACY
 tools={name:external(path) for name,path in [('python',sys.executable),('docker','/usr/bin/docker'),('elixir',root/'_build/federation/native/elixir/bin/elixir'),('erl',root/'_build/federation/native/erlang/bin/erl')]}
 jobs=[]
 for row in basis:
  original=list(row['arguments']);script=row['script'];arguments=list(original)
  source_name={'storage_recovery.py':'storage_write_fault.c','multi_store_move_fault.py':'store_move_fault.c','multi_migration.py':'multi_fault.c'}[script]
  if script=='storage_recovery.py':arguments=[]
  else:
   assert sha(plain(arguments[1]))==BASIS_ARTIFACT;arguments=arguments[2:]
  arguments=['--image',image,'--image-manifest',str(bound/'image-manifest.json')]+arguments
  if script!='storage_recovery.py':arguments+=['--keep-work',str(work/'fixtures'/row['name'])]
  if script=='multi_migration.py':arguments+=['--image-artifact',str(bound/'source-target.exs')]
  if script!='multi_migration.py' or '--crash-at' in original:
   arguments+=['--image-fault-library',proofbindings[source_name]['library'],'--image-fault-proof',proofbindings[source_name]['proof']]
  count=10 if script=='storage_recovery.py' else 4 if script=='multi_store_move_fault.py' else 6 if '--damage-backup' in original else 5 if '--crash-at' in original else 4
  jobs.append({'name':row['name'],'script':script,'native_basis_arguments':original,'arguments':arguments,'expected_check_count':count,
   'observer_source':source_name if '--image-fault-library' in arguments else None,'argv':[tools['python']['path'],str(frozen/'tests'/script)]+arguments+['--report',str(work/(row['name']+'.json'))]})
 docker_config=bound/'docker-config';docker_config.mkdir(mode=0o700);(docker_config/'config.json').write_text('{}')
 socket=Path('/var/run/docker.sock').resolve(strict=True);socket_info=socket.stat();assert stat.S_ISSOCK(socket_info.st_mode)
 runtime=work/'runtime';runtime.mkdir(mode=0o700)
 shutil.copyfile(plain(Path(__file__)),work/'driver.py')
 plan={'schema':'adhd/image-filesystem-ladder@2','scope':'Only the explicitly bound admitted target image; original native38/legacy producer are test provenance, not target qualification. No UI or release claim.',
  'image_config_identity':image,'artifact_sha256':artifact,'admission_sha256':admission_hash,'basis_artifact_sha256':BASIS_ARTIFACT,'legacy_sha256':LEGACY,'canonical_manifest_sha256':sha(bound/'image-manifest.json'),
  'payload_sha256':selected['payload_sha256'],'payload_audit':selected['audit'],'target_specifications':33,'live_specification_drift':drift,
  'frozen':inventory(frozen),'bound':inventory(bound),'driver_sha256':sha(work/'driver.py'),'native_plan_sha256':sha(native),
  'docker_socket':{'path':str(socket),'identity':[socket_info.st_dev,socket_info.st_ino]},
  'external_inputs':[external(original_artifact),external(legacy),external(native),external(context/'manifest.json'),external(context/'payload.tar'),external(admission)]+[v for r in proofbindings.values() for v in (r['source_library'],r['source_proof'])]+list(tools.values()),
  'tools':tools,'tool_trees':[tool_tree(root/'.venv'),tool_tree(root/'_build/federation/native/elixir'),tool_tree(root/'_build/federation/native/erlang')],'observer_bindings':proofbindings,'jobs':jobs,'parallelism':1,'runs_per_case':1,'automatic_retries':0,'first_failure_stops':True,
  'runtime_cwd':str(runtime),'outer_timeout_seconds':None,'timeout_policy':'Original unchanged harness deadlines only; no invented driver timeout that skips finally cleanup',
  'lane_lock':str(root/'_build/roadmap/image-filesystem.lane.lock'),'historical_basis_scope':'Original native38 job arguments and legacy producer remain fixed; all85 checks execute against selected target independently',
  'provider_calls_authorized':0,'preparation_app_compiler_or_service_starts':0,'execution_status':'UNSTARTED_REVIEW_REQUIRED'}
 save(work/'plan.json',plan);verify(work,plan);print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json'),'work':str(work),'jobs':len(jobs)}))


def absent(result,identifier):
 return result.returncode==1 and result.stdout.strip() in (b'',b'[]') and re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier),result.stderr.decode(errors='replace').strip()) is not None


def qualify(value,job,plan):
 image,artifact,_=target_bindings(plan)
 assert value['passed'] is True and value['artifact_sha256']==artifact
 rows=value['cases'] if job['script']=='storage_recovery.py' else value['checks']
 assert len(rows)==job['expected_check_count'] and all(row['passed'] for row in rows)
 runtimes=value['runtime'] if isinstance(value['runtime'],list) else [value['runtime']]
 ids=[];names=[]
 for runtime in runtimes:
  assert runtime['kind']=='docker' and runtime['image_config_identity']==image and runtime['artifact_sha256']==artifact
  assert runtime['canonical_manifest_sha256']==plan['canonical_manifest_sha256'] and not runtime.get('cleanup_blocked',False)
  assert runtime['payload_verified'] is True and not runtime['probe_cleanup_blocked']
  probes=runtime['payload_probe_lifecycle'];assert len(probes)==2 and [r['entrypoint'] for r in probes]==['cat','sha256sum']
  for probe in probes:
   assert probe['image_config_identity']==image and probe['observed_absent'] and probe['run_exit_code']==0
   assert not probe['run_failure_type'] and not probe['cleanup_failure_types'] and not probe['foreign_object_not_removed']
   names.append(probe['owned_name'])
   if probe['container_id'] is not None:ids.append(probe['container_id'])
  events=runtime['container_lifecycle'];started={e['container_id'] for e in events if e['action']=='started'}
  closed={e['container_id'] for e in events if e['action'] in ('hard-killed','stopped') and e.get('observed_absent') and e.get('wait_observed')}
  assert started and started<=closed,'Started target container lacks actual wait/remove/absence closure'
  for event in events:
   if event['action']=='hard-killed':assert event['exit_code']==137
  ids+=sorted(started)
  for codec in runtime.get('offline_helpers',[]):
   assert codec['observed_absent'] and not codec['cleanup_failure_types'] and codec['exit_code']==0
   names.append(codec['owned_name'])
  if runtime.get('observer_source'):
   assert runtime['observer_source']==job['observer_source']
   assert runtime['observer_disarmed_after_kill'] and runtime['actual_beam_kernel_custody']
   for observed in runtime['actual_beam_kernel_custody']:assert observed['kernel_state']=='stopped' and observed['signal_method']=='ancestor-pidfd-SIGSTOP'
 return sorted(set(ids)),sorted(set(names))


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
   save(work/'matrix.json',{'schema':'adhd/image-filesystem-matrix@2','passed':not failure and unchanged and not unrun and all(r['passed'] for r in results),
     'plan_sha256':digest,'image_config_identity':image,'artifact_sha256':artifact,'scope':plan['scope'],'input_closure_unchanged':unchanged,
     'failure_type':failure,'cleanup_confirmed':all(r['passed'] for r in results) and bool(results),'attempted':[r['name'] for r in results],'executed':executed,'unrun':unrun,'results':results})
 return 0 if unchanged and not unrun and all(r['passed'] for r in results) else 1


def main():
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--plan-sha256')
 for name in ('repo-root','native-plan','abi-root','context','admission-manifest'):parser.add_argument('--'+name,type=Path)
 for name in ('image','artifact-sha256','admission-sha256'):parser.add_argument('--'+name)
 args=parser.parse_args()
 if args.prepare:prepare(args)
 else:assert _STAGED;sys.exit(execute(args.work.absolute(),args.plan_sha256))


if __name__=='__main__':main()
