#!/usr/bin/env python3
"""Freeze the historical Kafka ladder against one explicitly admitted image target."""
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
NAMES=['controls','caps','dormant','admin','policy','lostreply','fairness','cutover','cutover-decision','cutover-project','retention','outage','federation']
COUNTS=dict(zip(NAMES,[8,5,2,4,4,2,4,4,5,5,2,9,14]))
BASIS='2237066a598ba7a2136c4517e9f0da3901e05688e426a7a7512e72844242005a'


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
 rows=native['jobs'];assert [r['name'] for r in rows]==NAMES
 assert all(r['arguments'][:2]==['--image',native['runtime']['image_config_identity']] for r in rows)
 for row in rows:
  args=row['arguments']
  if row['name'] in ('lostreply','fairness','cutover','cutover-decision','cutover-project','outage'):assert args[args.index('--deadline')+1]=='90'
 for name,stage in [('cutover-decision','transition-decision'),('cutover-project','transition-project')]:
  args=next(r['arguments'] for r in rows if r['name']==name);assert args[args.index('--crash-at')+1]==stage
 return rows


def prepare(args):
 root=Path(args.repo_root).absolute();assert root.resolve(strict=True)==root
 image,artifact,admission_sha=target_bindings({'image_config_identity':args.image,'artifact_sha256':args.artifact_sha256,'admission_sha256':args.admission_sha256})
 project=args.owned_compose_project;assert isinstance(project,str) and re.fullmatch('[a-z0-9][a-z0-9-]{0,62}',project)
 work=Path(args.work).absolute();assert work.resolve()==work and not work.exists();work.mkdir(parents=True,mode=0o700)
 # Read only the current-root pure payload reader; no runtime or compiler entry.
 source=plain(root/'tests/image_qualification_inputs.py');spec=importlib.util.spec_from_file_location('_reviewed_image_inputs',source);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
 context=Path(args.context).absolute();admission=plain(args.admission_manifest)
 selected=reader.reviewed_payload(context/'manifest.json',admission,admission_sha,image,artifact)
 assert len(selected['specifications'])==selected['audit']['canonical_specifications'] and len(selected['specifications'])>0
 native=plain(args.native_plan);assert sha(native)==BASIS;nv=json.loads(native.read_text());assert nv['artifact_sha256']==BASIS_ARTIFACT and nv['legacy_sha256']==LEGACY
 basis=selected_native_jobs(nv)
 frozen=work/'frozen';frozen.mkdir(mode=0o700)
 for tree in ('tests','scripts','deploy'):
  for path in sorted((root/tree).rglob('*')):
   assert not path.is_symlink(),str(path)
   if path.is_dir() or '__pycache__' in path.parts:continue
   assert path.is_file();target=frozen/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
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
 original_artifact=plain(args.basis_artifact);assert sha(original_artifact)==BASIS_ARTIFACT
 legacy=plain(json.loads(basis[0]['arguments'][basis[0]['arguments'].index('--legacy-command')+1])[1]);assert sha(legacy)==LEGACY
 tools={name:external(path) for name,path in [('python',sys.executable),('docker','/usr/bin/docker'),('elixir',root/'_build/federation/native/elixir/bin/elixir'),('erl',root/'_build/federation/native/erlang/bin/erl')]}
 jobs=[]
 for row in basis:
  original=list(row['arguments']);script=row['script'];arguments=[str(work)+v[len(str(native.parent)):] if v.startswith(str(native.parent)) else v for v in original]
  for flag,value in [('--image',image),('--owned-broker-container',project+'-kafka-1'),('--broker-container',project+'-kafka-1'),('--image-manifest',str(bound/'image-manifest.json')),('--image-fault-library',proofbindings['multi_fault.c']['library']),('--image-fault-proof',proofbindings['multi_fault.c']['proof'])]:
   if flag in arguments:arguments[arguments.index(flag)+1]=value
  jobs.append({'name':row['name'],'script':script,'native_basis_arguments':original,'arguments':arguments,'expected_check_count':COUNTS[row['name']],
   'observer_source':'multi_fault.c' if '--crash-at' in arguments else None,'argv':[tools['python']['path'],str(frozen/'tests'/script)]+arguments+['--report',str(work/(row['name']+'.json'))]})
 docker_config=bound/'docker-config';docker_config.mkdir(mode=0o700);(docker_config/'config.json').write_text('{}')
 socket=Path('/var/run/docker.sock').resolve(strict=True);socket_info=socket.stat();assert stat.S_ISSOCK(socket_info.st_mode)
 runtime=work/'runtime';runtime.mkdir(mode=0o700)
 shutil.copyfile(plain(Path(__file__)),work/'driver.py')
 plan={'schema':'adhd/image-kafka-ladder@2','scope':'Only the explicitly selected admitted image/artifact; no historical result relabeling, UI, live-model or release claim',
  'image_config_identity':image,'artifact_sha256':artifact,'admission_sha256':admission_sha,'canonical_manifest_sha256':sha(bound/'image-manifest.json'),
  'payload_sha256':selected['payload_sha256'],'payload_audit':selected['audit'],'target_specifications':len(selected['specifications']),'payload_custody':'Fixture-based lostreply/fairness/cutover/outage require strict2probe ledger; Hub-based controls/caps/dormant/Admin/policy/retention/federation validate exact manifest+artifact by exec in each actual app container and have no extra standalone payload probes','live_specification_drift':drift,
  'frozen':inventory(frozen),'bound':inventory(bound),'driver_sha256':sha(work/'driver.py'),'native_plan_sha256':sha(native),
  'docker_socket':{'path':str(socket),'identity':[socket_info.st_dev,socket_info.st_ino]},
  'external_inputs':[external(original_artifact),external(legacy),external(native),external(context/'manifest.json'),external(context/'payload.tar'),external(admission)]+[v for r in proofbindings.values() for v in (r['source_library'],r['source_proof'])]+list(tools.values()),
  'tools':tools,'tool_trees':[tool_tree(root/'.venv'),tool_tree(root/'_build/federation/native/elixir'),tool_tree(root/'_build/federation/native/erlang')],'observer_bindings':proofbindings,'jobs':jobs,'parallelism':1,'runs_per_case':1,'automatic_retries':0,'first_failure_stops':True,
  'runtime_cwd':str(runtime),'outer_timeout_seconds':None,'timeout_policy':'Original unchanged harness deadlines only; no invented driver timeout that skips finally cleanup',
  'lane_lock':str(root/'_build/roadmap/image-kafka.lane.lock'),'historical_basis':{'native_plan_sha256':BASIS,'artifact_sha256':BASIS_ARTIFACT,'legacy_producer_sha256':LEGACY},
  'provider_calls_authorized':0,'preparation_app_compiler_or_service_starts':0,'execution_status':'UNSTARTED_REVIEW_REQUIRED','private_service':{'project':project,'broker':project+'-kafka-1','rest':project+'-kafka-rest-1','port':'18088','urls':['http://127.0.0.1:18082','http://127.0.0.1:18085','http://127.0.0.1:18088']}}
 save(work/'plan.json',plan);verify(work,plan);print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json'),'work':str(work),'jobs':len(jobs)}))


def absent(result,identifier):
 return result.returncode==1 and result.stdout.strip() in (b'',b'[]') and re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier),result.stderr.decode(errors='replace').strip()) is not None


def qualify(value,job,plan):
 image,artifact,_=target_bindings(plan)
 assert value['passed'] is True and value['artifact_sha256']==artifact
 rows=value['checks']
 assert len(rows)==job['expected_check_count'] and all(row['passed'] for row in rows)
 runtimes=value['runtime'] if isinstance(value['runtime'],list) else [value['runtime']]
 ids=[];names=[]
 for runtime in runtimes:
  assert runtime['kind']=='docker' and runtime['image_config_identity']==image and runtime['artifact_sha256']==artifact
  assert runtime['canonical_manifest_sha256']==plan['canonical_manifest_sha256'] and not runtime.get('cleanup_blocked',False)
  if job['script'] in ('eventing_faults.py','multi_fairness.py','eventing_cutover.py','eventing_acceptance.py'):
   assert runtime['payload_verified'] is True and not runtime['probe_cleanup_blocked']
   probes=runtime['payload_probe_lifecycle'];assert len(probes)==2 and [r['entrypoint'] for r in probes]==['cat','sha256sum']
   for probe in probes:
    assert probe['image_config_identity']==image and probe['observed_absent'] and probe['run_exit_code']==0
    assert not probe['run_failure_type'] and not probe['cleanup_failure_types'] and not probe['foreign_object_not_removed']
    names.append(probe['owned_name'])
    if probe['container_id'] is not None:ids.append(probe['container_id'])
  events=runtime['container_lifecycle'];started={e['container_id'] for e in events if e['action']=='started'}
  closed={e['container_id'] for e in events if e['action'] in ('hard-killed','stopped') and e.get('observed_absent') }
  assert started and started<=closed,'Started target container lacks actual wait/remove/absence closure'
  for event in events:
   if event['action']=='hard-killed' and job['observer_source']:assert event['exit_code']==137 and event['wait_observed']
  ids+=sorted(started)
  for codec in runtime.get('offline_helpers',[]):
   assert codec['observed_absent'] and not codec['cleanup_failure_types'] and codec['exit_code']==0
   names.append(codec['owned_name'])
  if job['observer_source']:
   assert runtime['observer_disarmed_after_kill'] and runtime['actual_beam_kernel_custody']
   for observed in runtime['actual_beam_kernel_custody']:assert observed['kernel_state']=='stopped' and observed['signal_method']=='ancestor-pidfd-SIGSTOP'
 return sorted(set(ids)),sorted(set(names))


def preflight(plan,env):
 import urllib.request
 service=plan['private_service'];observed={}
 for name,kind in [(service['broker'],'kafka'),(service['rest'],'kafka-rest')]:
  result=subprocess.run([plan['tools']['docker']['path'],'inspect',name],env=env,capture_output=True,check=True,timeout=30)
  rows=json.loads(result.stdout);assert len(rows)==1;row=rows[0]
  labels=row['Config']['Labels'];assert labels['com.docker.compose.project']==service['project'] and labels['com.docker.compose.service']==kind and row['State']['Running']
  if kind=='kafka-rest':assert any(p['HostPort']==service['port'] and p['HostIp'] in ('127.0.0.1','::1') for p in row['NetworkSettings']['Ports']['8082/tcp'])
  observed[kind]={'container_id':row['Id'],'image_config_identity':row['Image'],'labels':labels}
 clusters=[]
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for url in service['urls']:
  with opener.open(url+'/v3/clusters',timeout=10) as response:
   assert response.status==200;body=response.read(1048577);assert len(body)<=1048576
  data=json.loads(body)['data'];assert len(data)==1 and isinstance(data[0]['cluster_id'],str) and data[0]['cluster_id']
  clusters.append({'url':url,'cluster_id':data[0]['cluster_id']})
 assert len({r['cluster_id'] for r in clusters})==3,'Require three actual distinct Kafka clusters'
 return {'owned_services':observed,'clusters':clusters}


def execute(work,digest):
 assert digest and sha(work/'plan.json')==digest
 plan=json.loads((work/'plan.json').read_text());image,artifact,_=target_bindings(plan);verify(work,plan)
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
   save(work/'cluster-preflight.json',preflight(plan,env))
   for job in plan['jobs']:
    if job['name'] in ('retention','outage','federation'):save(work/('cluster-preflight-'+job['name']+'.json'),preflight(plan,env))
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
    row.update(passed=True,independently_absent_ids=ids,independently_absent_helper_names=names);print('DONE',job['name'],True,flush=True)
  except BaseException as error:failure=type(error).__name__;raise
  finally:
   try:verify(work,plan);unchanged=True
   except BaseException:unchanged=False
   for row in results:
    for suffix,key in [('.json','report_sha256'),('.log','log_sha256')]:
     path=work/(row['name']+suffix)
     if path.is_file():row[key]=sha(path)
   executed=[r['name'] for r in results if r['started']];unrun=[j['name'] for j in plan['jobs'] if j['name'] not in executed]
   save(work/'matrix.json',{'schema':'adhd/image-kafka-matrix@2','passed':not failure and unchanged and not unrun and all(r['passed'] for r in results),
     'plan_sha256':digest,'image_config_identity':image,'artifact_sha256':artifact,'scope':plan['scope'],'input_closure_unchanged':unchanged,
     'failure_type':failure,'cleanup_confirmed':all(r['passed'] for r in results) and bool(results),'attempted':[r['name'] for r in results],'executed':executed,'unrun':unrun,'results':results})
 return 0 if unchanged and not unrun and all(r['passed'] for r in results) else 1


def main():
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--plan-sha256')
 for name in ('repo-root','native-plan','abi-root','context','admission-manifest','basis-artifact'):parser.add_argument('--'+name,type=Path)
 for name in ('image','artifact-sha256','admission-sha256','owned-compose-project'):parser.add_argument('--'+name)
 args=parser.parse_args()
 if args.prepare:prepare(args)
 else:assert _STAGED;sys.exit(execute(args.work.absolute(),args.plan_sha256))


if __name__=='__main__':main()
