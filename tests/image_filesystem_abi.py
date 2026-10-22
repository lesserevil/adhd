#!/usr/bin/env python3
"""Prepare source-bound non-app ABI probes; --execute requires a reviewed plan.

Preparation runs only host cc/readelf. Execution is a separate explicit action;
no generated app, provider, broker, framework receipt or shared service is run.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
from uuid import uuid4

OBSERVER='/adhd-test/observer.so'
CALLER='/adhd-test/caller.so'
PAYLOAD=b'actual scalar ABI bytes\n'
BIG_OFFSET=(1<<32)+17
HELPERS=('container_fixture.py','image_eventing_fault.py','image_eventing_runtime.py','image_filesystem_fault.py')
FAMILIES={
 'multi_fault.c':('rename','renameat','renameat2','link','linkat'),
 'store_move_fault.c':('rename','link','unlink'),
 'storage_write_fault.c':('fsync','rename','pwrite','pwrite64'),
 'project_recovery_fault.c':('rename','fsync','link','unlink'),
 'rebind_fault.c':('rename','fsync'),
}
OPTIONAL_FAMILIES={'config_rename_fault.c':('rename',)}
CALLER_ABI={'_exit','access','close','dlopen','dlsym','fsync','getenv','getpid','lseek','memcmp','open','pread','read','setenv','snprintf','strcmp','strlen','unsetenv','write'}


def selected_families(names=None):
 names=list(FAMILIES) if names is None else names
 available={**FAMILIES,**OPTIONAL_FAMILIES}
 assert isinstance(names,list) and names and len(names)==len(set(names))
 assert all(name in available for name in names)
 return {name:available[name] for name in names}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(path):
 path=Path(path).absolute();info=path.lstat()
 assert path.resolve(strict=True)==path and not path.is_symlink(), 'Redirected input: '+str(path)
 assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid(),str(path)
 return path


def save(path,value):
 path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)


def load_helpers(directory):
 directory=Path(directory);sys.dont_write_bytecode=True;sys.path.insert(0,str(directory))
 # This driver is standalone: never reuse an ambient module from another tree.
 for key in ('container_fixture','image_eventing_fault','image_eventing_runtime','image_filesystem_fault'):
  prior=sys.modules.get(key)
  if prior:assert Path(prior.__file__).resolve()==directory/(key+'.py'), 'Ambient helper collision'
 import image_filesystem_fault as helper
 import image_eventing_fault as custody
 return helper,custody


def compile_caller(source,target):
 argv=['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-nostdlib','-fno-builtin',
       '-fno-stack-protector','-U_FORTIFY_SOURCE','-D_FORTIFY_SOURCE=0','-O2',str(source),'-o',str(target)]
 subprocess.run(argv,check=True)
 sections={k:subprocess.check_output(['readelf','-W',flag,str(target)],text=True)
           for k,flag in [('dynamic','-d'),('versions','-V'),('header','-h'),('symbols','--dyn-syms')]}
 assert 'NEEDED' not in sections['dynamic'] and 'GLIBC_' not in sections['versions'] and 'GLIBC_' not in sections['symbols']
 assert re.search(r'Machine:\s+Advanced Micro Devices X86-64',sections['header']) and re.search(r'Class:\s+ELF64',sections['header'])
 undefined=set()
 for line in sections['symbols'].splitlines():
  parts=line.split()
  if len(parts)>=8 and parts[6]=='UND':undefined.add(parts[7])
 assert undefined and undefined<=CALLER_ABI and not any('__' in x for x in undefined),undefined
 return {'source_sha256':sha(source),'library_sha256':sha(target),'undefined_scalar_symbols':sorted(undefined),
         'needed_libraries':[],'glibc_symbol_versions':[],'compile_argv':argv,'elf_machine':'x86_64',
         'sections_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sections.items()},'compiler_version':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],'actual_image_loaded':False}


def prepare(args):
 families=selected_families(getattr(args,'family',None))
 assert re.fullmatch('sha256:[a-f0-9]{64}',args.image)
 manifest=plain(args.image_manifest);raw=manifest.read_bytes();meta=json.loads(raw)
 assert meta['schema']=='adhd/container-inputs@1' and re.fullmatch('[a-f0-9]{64}',meta['files']['hub.exs'])
 work=Path(args.work).absolute();assert work.resolve()==work and not work.exists()
 assert len(os.fsencode(work))<1024 and not any(c in str(work) for c in ',:\n\0'), 'Unsupported mount/control path'
 work.mkdir(parents=True,mode=0o700)
 inputs=work/'inputs';inputs.mkdir(mode=0o700)
 source_root=Path(args.helpers_root).absolute();assert source_root.resolve(strict=True)==source_root and source_root.is_dir() and not source_root.is_symlink()
 for name in HELPERS+tuple(families):
  # Only this reviewed test observer changes for musl's missing dlsym alias;
  # the other four observers come byte-for-byte from the helper authority.
  origin=Path(__file__).with_name(name) if name=='storage_write_fault.c' else source_root/name
  shutil.copyfile(plain(origin),inputs/name)
 shutil.copyfile(plain(Path(__file__).with_name('image_filesystem_abi_caller.c')),inputs/'image_filesystem_abi_caller.c')
 shutil.copyfile(plain(Path(__file__)),work/'run.py');shutil.copyfile(manifest,inputs/'manifest.json')
 helper,_=load_helpers(inputs)
 builds={}
 for source in families:
  library,audit=helper.compile_observer(source,work/'build'/source.removesuffix('.c'));builds[source]={'library':str(library),'audit':audit}
 caller=work/'build/caller.so';caller_audit=compile_caller(inputs/'image_filesystem_abi_caller.c',caller)
 inventory={str(f.relative_to(work)):{'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(work.rglob('*')) if f.is_file()}
 plan={'schema':'adhd/image-filesystem-abi-plan@1','scope':'Standalone compatibility probes only; no ADHD app or runtime durability claim',
       'execution_authorized':False,'image_config_identity':args.image,'canonical_manifest_sha256':hashlib.sha256(raw).hexdigest(),
       'artifact_sha256':meta['files']['hub.exs'],'work':str(work),'driver_sha256':sha(work/'run.py'),'inventory':inventory,
       'directories':sorted(str(f.relative_to(work)) for f in work.rglob('*') if f.is_dir()),
       'observer_builds':builds,'caller':{'library':str(caller),'audit':caller_audit},
       'selected_families':list(families),
       'cases':[{'source':s,'op':op} for s,ops in families.items() for op in ops],
       'limits':{'cases':sum(map(len,families.values())),'serial_containers':1,'boundary_seconds':10,'kernel_stop_seconds':2,'docker_seconds':30,
                 'network':'none','memory':'128m','cpus':1,'pids':32,'case_seconds':120,'cleanup_seconds':45,'provider_calls':0,'app_starts':0,'broker_calls':0},
       'required_review':'Explicit root GO of this exact plan hash before --execute; first failure preserved, no retries',
       'sparse_write':{'offset':BIG_OFFSET,'payload_hex':PAYLOAD.hex(),'maximum_allocated_bytes_per_file':65536}}
 save(work/'plan.json',plan);print(json.dumps({'prepared':True,'executed':False,'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json')}))


def verify(plan):
 families=selected_families(plan.get('selected_families'))
 work=Path(plan['work']);assert work.resolve(strict=True)==work and not work.is_symlink()
 driver=plain(Path(__file__));assert sha(driver)==plan['driver_sha256'],'Executing driver changed'
 assert plan['cases']==[{'source':s,'op':op} for s,ops in families.items() for op in ops]
 assert len(plan['cases'])==plan['limits']['cases']==sum(map(len,families.values()))
 observed=set();directories=set()
 for root in (work/'inputs',work/'build'):
  assert root.resolve(strict=True)==root and not root.is_symlink();directories.add(str(root.relative_to(work)))
  for p in root.rglob('*'):
   assert not p.is_symlink(),str(p)
   if p.is_dir():directories.add(str(p.relative_to(work)));continue
   plain(p);observed.add(str(p.relative_to(work)))
 assert directories==set(plan['directories']),'Build/input directory set changed'
 expected={n for n in plan['inventory'] if n!='run.py'};assert observed==expected,'Build/input file set changed'
 for name,record in plan['inventory'].items():
  p=plain(work/name);assert sha(p)==record['sha256'] and p.stat().st_size==record['bytes'],name
 assert sha(work/'inputs/manifest.json')==plan['canonical_manifest_sha256']


def write(path,body):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())


def fixture(root,source,op):
 """Only fresh private ordinary control files; never generated app state."""
 root.mkdir(parents=True,mode=0o700);config=root/'control.json';store=root/'state.dets';sentinel=root/'observer.json'
 src=root/'armed-source';dst=root/'armed-target';stage='';extra={};before=False;effect='target-bytes'
 if source=='multi_fault.c':
  prefix='ADHD_CRASH_';stage='after-snapshot'
  write(Path(str(config)+'.project-upgrade'),b'{"phase":"decided"}')
  if op in ('link','linkat'):
   src=root/'state.dets.projects/.stage/state.dets.snapshot';dst=root/'state.dets.projects/target/state.dets.snapshot'
   write(Path(str(config)+'.transaction'),json.dumps({'kind':'registry_adoption','stage':str(src).removesuffix('.snapshot'),'target':str(dst).removesuffix('.snapshot')},separators=(',',':')).encode())
  else:dst=Path(str(store)+'.snapshot')
  extra={prefix+'CONFIG':str(config),prefix+'STORE':str(store)}
 elif source=='store_move_fault.c':
  prefix='ADHD_MOVE_';stage={'rename':'after-decision','link':'after-first-snapshot','unlink':'before-cleanup'}[op]
  extra={prefix+'CONFIG':str(config),prefix+'TARGET':str(store),prefix+'ARM':str(root/'armed')};write(root/'armed',b'armed')
  if op=='rename':dst=Path(str(config)+'.transaction')
  else:
   write(Path(str(config)+'.transaction'),b'actual decision control')
   if op=='link':src=root/'.move-probe/state.dets.snapshot';dst=Path(str(store)+'.snapshot')
   else:dst=Path(str(config)+'.transaction');before=True;effect='before-unlink'
 elif source=='storage_write_fault.c':
  prefix='ADHD_WRITE_';stage={'fsync':'snapshot-data-sync','rename':'snapshot-install','pwrite':'checkpoint-write','pwrite64':'checkpoint-write'}[op]
  extra={prefix+'ARM':str(root/'armed'),prefix+'TARGET':str(root/'target-path')};write(root/'armed',b'armed');write(root/'target-path',str(store).encode())
  if op=='fsync':src=Path(str(store)+'.snapshot.tmp-probe');dst=src;extra['ADHD_ABI_SYNC']=str(src);effect='synced-bytes'
  elif op=='rename':dst=Path(str(store)+'.snapshot')
  else:dst=store;write(Path(str(store)+'.snapshot'),b'crash-request');effect='sparse-write'
 elif source=='project_recovery_fault.c':
  prefix='ADHD_RECOVERY_FAULT_';stage={'rename':'after-stage-snapshot','fsync':'after-decision-sync','link':'after-install-snapshot','unlink':'before-cleanup'}[op]
  extra={prefix+'CONFIG':str(config),prefix+'ROOT':str(root),prefix+'ARM':str(root/'armed')};write(root/'armed',b'armed')
  if op=='rename':dst=root/'.restore-probe/state.dets.snapshot'
  elif op=='fsync':dst=Path(str(config)+'.transaction');extra['ADHD_ABI_PREPARE_RENAME']=str(src);extra['ADHD_ABI_SYNC']=str(root);effect='directory-synced-rename'
  else:
   write(Path(str(config)+'.transaction'),b'actual decision control')
   if op=='link':src=root/'.restore-probe/state.dets.snapshot';dst=Path(str(store)+'.snapshot')
   else:dst=Path(str(config)+'.transaction');before=True;effect='before-unlink'
 elif source=='config_rename_fault.c':
  assert op=='rename';prefix='ADHD_CONFIG_FAULT_';stage='journal'
  dst=Path(str(config)+'.journal');write(root/'armed',b'armed')
  extra={prefix+'CONFIG':str(config),prefix+'ARM':str(root/'armed')}
 else:
  assert source=='rebind_fault.c';prefix='ADHD_REBIND_';stage='decision-durable';dst=Path(str(config)+'.transaction');extra={prefix+'CONFIG':str(config)}
  if op=='fsync':extra['ADHD_ABI_PREPARE_RENAME']=str(src);extra['ADHD_ABI_SYNC']=str(root);effect='directory-synced-rename'
  else:effect='rename-then-directory-sync'
 if source=='rebind_fault.c' and op=='rename':
  # This observer only stops on directory fsync after rename: caller selects the
  # rename wrapper but must also explicitly flush its actual parent directory.
  extra['ADHD_ABI_AFTER_RENAME_SYNC']=str(root)
 if not before:
  if effect=='sparse-write':write(dst,b'')
  elif src==dst:write(src,PAYLOAD+b'crash-request')
  else:write(src,PAYLOAD+b'crash-request' if source=='storage_write_fault.c' else PAYLOAD)
 dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 environment={prefix+'STAGE':stage,prefix+'SENTINEL':str(sentinel),**extra,
  'ADHD_ABI_OP':op,'ADHD_ABI_ROOT':str(root),'ADHD_ABI_OBSERVER':OBSERVER,'ADHD_ABI_PREFIX':prefix,'ADHD_ABI_STAGE':stage,
  'ADHD_ABI_SOURCE':str(src),'ADHD_ABI_TARGET':str(dst)}
 return {'environment':environment,'stage':stage,'source':src,'target':dst,'sentinel':sentinel,'effect':effect,
         'source_before':src.read_bytes() if src.exists() else None,'target_before':dst.read_bytes() if dst.exists() else None}


def effects(control,op):
 src,dst=control['source'],control['target'];effect=control['effect']
 if effect=='before-unlink':assert dst.read_bytes()==control['target_before']
 elif effect=='sparse-write':
  info=dst.stat();assert info.st_size==BIG_OFFSET+len(PAYLOAD) and info.st_blocks*512<=65536
  with dst.open('rb') as stream:stream.seek(BIG_OFFSET);assert stream.read(len(PAYLOAD)+1)==PAYLOAD
 elif effect=='synced-bytes':assert dst.read_bytes()==control['source_before']
 else:
  assert dst.read_bytes()==control['source_before']
  if op in ('link','linkat'):assert src.stat().st_ino==dst.stat().st_ino and src.read_bytes()==dst.read_bytes()
  else:assert not src.exists()
 # Independent high-offset unarmed check, before any kill/cleanup.
 return {'effect':effect,'verified':True,'target_bytes':dst.stat().st_size,'target_allocated_bytes':dst.stat().st_blocks*512}


def command(plan,case,library,caller,control,name,root):
 assert re.fullmatch('sha256:[a-f0-9]{64}',plan['image_config_identity'])
 return ['docker','run','--detach','--name',name,'--network','none','--read-only','--user',f'{os.getuid()}:{os.getgid()}',
  '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','128m','--cpus','1','--pids-limit','32',
  '--mount',f'type=bind,src={root},dst={root}',
  '--mount',f'type=bind,src={library},dst={OBSERVER},readonly',
  '--mount',f'type=bind,src={caller},dst={CALLER},readonly',
  '--env',f'LD_PRELOAD={OBSERVER}:{CALLER}']+[
  part for key,value in sorted(control['environment'].items()) for part in ('--env',key+'='+value)]+[
  '--entrypoint','/bin/true',plan['image_config_identity']]


def validate_call(call,op):
 assert call['op']==op and call['namespace_pid']==1 and call['unarmed_success'] and call['wrapper_resolved']
 assert call['direct_syscall']==(op=='renameat2') and call['next_resolved_distinct']==(op!='renameat2')
 assert call['off_t_bytes']==call['off64_t_bytes']==8
 if op=='pwrite64':assert call['real_forwarding_symbol'] in ('pwrite64','pwrite')
 else:assert call['real_forwarding_symbol']==('syscall:renameat2' if op=='renameat2' else op)
 if op in ('pwrite','pwrite64'):assert call['sparse_offset']==BIG_OFFSET


def cleanup_owned(docker,key,image,known_identifier,absent_check):
 """Independent known-ID cleanup; failed inspect never implies absence."""
 notes=[];foreign=False;confirmed=False;gone=False
 try:
  initial=docker('inspect',key,check=False)
  if absent_check(initial,key):return {'owned_container_absent':True,'cleanup_notes':[]}
  if initial.returncode==0:
   rows=json.loads(initial.stdout);assert len(rows)==1
   row=rows[0]
   foreign=(row['Image']!=image or (known_identifier is not None and row['Id']!=known_identifier))
   confirmed=not foreign
   if foreign:notes.append('ForeignObjectNotRemoved')
  else:notes.append('InitialInspectUnconfirmed')
 except BaseException as error:notes.append('InitialInspect:'+type(error).__name__)
 # A successful detached run bound a full immutable ID. A transient inspect
 # failure must not skip an independent removal attempt of that exact own ID.
 if not foreign and (known_identifier is not None or confirmed):
  try:
   removed=docker('rm','--force',known_identifier or key,check=False)
   if removed.returncode!=0:notes.append('RemoveUnconfirmed')
  except BaseException as error:notes.append('Remove:'+type(error).__name__)
 try:
  final=docker('inspect',key,check=False);gone=absent_check(final,key)
  if not gone:notes.append('AbsenceUnconfirmed')
 except BaseException as error:notes.append('FinalInspect:'+type(error).__name__)
 return {'owned_container_absent':gone,'cleanup_notes':notes}


def run_case(plan,case,index,helpers,custody):
 work=Path(plan['work']);root=work/'cases'/('%02d-'%index+case['source'].removesuffix('.c')+'-'+case['op']);control=fixture(root,case['source'],case['op'])
 library=plain(plan['observer_builds'][case['source']]['library']);caller=plain(plan['caller']['library']);name='adhd-abi-'+uuid4().hex[:20];identifier=None;row=None;result={'case':case,'passed':False};failure=None;gone=False
 original_docker=custody.docker
 call_deadline=time.monotonic()+plan['limits']['case_seconds']
 def docker(*args,check=True,timeout=30):
  remaining=call_deadline-time.monotonic();assert remaining>0,'Case/cleanup absolute deadline'
  return original_docker(*args,check=check,timeout=min(timeout,remaining))
 # The reviewed custody helper uses its own module-level Docker function.
 # Bind it to the same absolute deadline for this isolated serial case only.
 custody.docker=docker
 try:
  started=docker(*command(plan,case,library,caller,control,name,root)[1:]);identifier=started.stdout.decode().strip();assert re.fullmatch('[a-f0-9]{64}',identifier)
  deadline=time.monotonic()+plan['limits']['boundary_seconds']
  while time.monotonic()<deadline:
   row=json.loads(docker('inspect',identifier).stdout)[0];assert row['Image']==plan['image_config_identity'] and row['Id']==identifier
   if control['sentinel'].exists():break
   assert row['State']['Running'],'Actual image exited without armed observer boundary'
   time.sleep(.01)
  else:raise AssertionError('Actual image ABI boundary deadline')
  trace=json.loads(control['sentinel'].read_text());assert trace['stage']==control['stage'] and trace['pid']==1
  call=json.loads((root/'caller.json').read_text());validate_call(call,case['op'])
  owned=custody.stop_owned_process(identifier,plan['image_config_identity'],trace,OBSERVER,'busybox',['/bin/true'],sha(library))
  assert row['HostConfig']['NetworkMode']=='none' and row['HostConfig']['ReadonlyRootfs']
  mounts={v['Destination']:v for v in row['Mounts']}
  for destination,actual in [(OBSERVER,library),(CALLER,caller)]:
   assert mounts[destination]['Type']=='bind' and not mounts[destination]['RW'] and mounts[destination]['Source']==str(actual)
  maps=docker('exec',identifier,'cat','/proc/1/maps').stdout;assert CALLER.encode() in maps and OBSERVER.encode() in maps
  assert docker('exec',identifier,'cat','/app/manifest.json').stdout==(work/'inputs/manifest.json').read_bytes()
  assert docker('exec',identifier,'sha256sum','/app/hub.exs').stdout.decode().split()[0]==plan['artifact_sha256']
  physical=effects(control,case['op'])
  if case['op'] in ('pwrite','pwrite64'):
   unarmed=root/'unarmed-source';assert unarmed.stat().st_size==BIG_OFFSET+len(PAYLOAD) and unarmed.stat().st_blocks*512<=65536
   with unarmed.open('rb') as stream:stream.seek(BIG_OFFSET);assert stream.read(len(PAYLOAD)+1)==PAYLOAD
  docker('kill','--signal','KILL',identifier);exit_code=int(docker('wait',identifier).stdout);assert exit_code==137
  final=json.loads(docker('inspect',identifier).stdout)[0];assert not final['State']['Running'] and final['State']['ExitCode']==137
  docker('rm',identifier);gone=helpers.EventingFaultImage.authoritative_absence(docker('inspect',identifier,check=False),identifier);assert gone
  result.update(passed=True,container_id=identifier,exit_code=exit_code,caller=call,observer_trace=trace,physical=physical,
   process_custody=owned,observer_library_sha256=sha(library),caller_library_sha256=sha(caller),owned_container_absent=True)
 except BaseException as error:
  failure=error;result.update(failure_type=type(error).__name__,failure=str(error),container_id=identifier,observed_state=row.get('State') if row else None)
  if identifier:
   try:
    logs=docker('logs',identifier,check=False);result['container_stdout']=logs.stdout.decode(errors='replace')[:8192];result['container_stderr']=logs.stderr.decode(errors='replace')[:8192]
   except BaseException as log_error:result['container_log_error']=type(log_error).__name__
 finally:
  call_deadline=time.monotonic()+plan['limits']['cleanup_seconds']
  if not gone:
   cleanup=cleanup_owned(docker,identifier or name,plan['image_config_identity'],identifier,helpers.EventingFaultImage.authoritative_absence)
   gone=cleanup['owned_container_absent'];result.update(cleanup)
   if cleanup['cleanup_notes'] and failure is not None:failure.add_note('Owned cleanup: '+','.join(cleanup['cleanup_notes']))
   if not gone:failure=failure or RuntimeError('Owned cleanup absence unconfirmed')
  result['owned_container_absent']=gone
  try:save(root/'result.json',result)
  finally:custody.docker=original_docker
 if failure:raise RuntimeError('ABI case failed; no retries or later cases; see '+str(root/'result.json')) from failure
 return result


def execute(args):
 plan_path=plain(args.plan);assert sha(plan_path)==args.reviewed_plan_sha256,'Exact reviewed plan required';plan=json.loads(plan_path.read_text());verify(plan)
 work=Path(plan['work']);assert not (work/'cases').exists() and not (work/'result.json').exists(),'Fresh run only'
 # Persist the once-only admission before importing runtime helpers or issuing
 # any case/Docker operation. A partial/lost result never permits a retry.
 write(work/'execution.started',json.dumps({'schema':'adhd/abi-execution-once@1','plan_sha256':sha(plan_path)},separators=(',',':')).encode())
 directory=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
 try:os.fsync(directory)
 finally:os.close(directory)
 helper,custody=load_helpers(work/'inputs');report={'schema':'adhd/image-filesystem-abi-run@1','passed':False,'plan_sha256':sha(plan_path),'rows':[],
  'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'application_started':False,'provider_calls':0,'broker_calls':0}
 try:
  for index,case in enumerate(plan['cases']):
   verify(plan);row=run_case(plan,case,index,helper,custody);report['rows'].append(row);save(work/'result.json',report)
  # Each source proof carries all successful export cases and their physical
  # witnesses. No historical rename-only proof is promoted to full closure.
  for source,ops in selected_families(plan.get('selected_families')).items():
   rows=[r for r in report['rows'] if r['case']['source']==source];assert {r['case']['op'] for r in rows}==set(ops)
   proof={'schema':'adhd/image-filesystem-observer-probe@1','passed':True,'application_started':False,'owned_container_absent':all(r['owned_container_absent'] for r in rows),
    'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'canonical_manifest_sha256':plan['canonical_manifest_sha256'],
    'exit_code':137,'actual_musl_loader':'/lib/ld-musl-x86_64.so.1','observer':plan['observer_builds'][source]['audit'],
    'successful_abi_cases':sorted(ops),'process_custody':rows[0]['process_custody'],'cases':rows,'caller':plan['caller']['audit'],'scope':'Standalone real forwarding/boundary/custody only; no application qualification'}
   save(work/(source+'.proof.json'),proof)
  report['passed']=True
 except BaseException as error:report.update(failure_type=type(error).__name__,failure=str(error));raise
 finally:save(work/'result.json',report)


def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='op',required=True)
 a=sub.add_parser('prepare');a.add_argument('--helpers-root',type=Path,required=True);a.add_argument('--work',type=Path,required=True);a.add_argument('--image',required=True);a.add_argument('--image-manifest',type=Path,required=True)
 a.add_argument('--family',action='append',choices=list(FAMILIES)+list(OPTIONAL_FAMILIES),help='Explicit source ABI closure; default preserves the original18 cases')
 a=sub.add_parser('execute');a.add_argument('--plan',type=Path,required=True);a.add_argument('--reviewed-plan-sha256',required=True)
 args=p.parse_args();prepare(args) if args.op=='prepare' else execute(args)


if __name__=='__main__':main()
