#!/usr/bin/env python3
"""Closed native readiness gate: prepare/verify are metadata-only; execute needs GO.

An official successful rebuild plus its matching finalized receipt and actual
export are mandatory. Candidate source is deliberately not an admission input.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit
sys.dont_write_bytecode=True
CASES=('lag','queue-control','duplicate','duplicate-bad-topology','never','queue','forbidden','server-error','malformed','bad-cleanup','partitions-float','retention-missing','retention-float','retention-negative','retention-duplicate','existing-retention','offset-nonzero','offset-negative','offset-missing','offset-float','offset-string')
SCHEMA='adhd/eventing-readiness-native21-plan@1'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def regular(path):
 path=Path(path).absolute();info=path.lstat()
 assert path.resolve()==path and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid(),str(path)
 return path

def read(path):return json.loads(regular(path).read_text())
def save(path,value):
 raw=(json.dumps(value,indent=2)+'\n').encode();temporary=path.with_name(path.name+'.tmp')
 fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 temporary.replace(path);sync_dir(path.parent)

def sync_dir(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)

def inventory(root):
 root=Path(root).absolute();assert root.resolve()==root and root.is_dir()
 files={};directories=[]
 for path in sorted(root.rglob('*')):
  info=path.lstat();assert not stat.S_ISLNK(info.st_mode),str(path)
  if stat.S_ISDIR(info.st_mode):directories.append(str(path.relative_to(root)))
  else:regular(path);files[str(path.relative_to(root))]=sha(path)
 return {'files':files,'directories':directories}

def validate_official(export,rebuild,receipt):
 export=regular(export);r=read(rebuild);f=read(receipt)
 assert r['schema']=='literate-ai/cli-result@1'and r['command']=='rebuild'and r['ok']is True
 b=r['result'];assert b['schema']=='literate-ai/project-rebuild@1'and b['passed']is True and b['receipt_committed']is True
 assert Path(b['artifact'])==export,'Export must be the actual official rebuild artifact, not a candidate or substituted copy'
 assert f['schema']=='urn:literate-ai:schema:v1:project-test-receipt-finalized-candidate'
 canonical=json.dumps(f['receipt'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
 assert f['receipt_identity']=='sha256:'+hashlib.sha256(canonical).hexdigest()
 assert f['receipt_identity']==b['receipt_identity']==b['receipt_update']['identity']
 assert f['lifecycle_request_identity']==b['lifecycle_request_identity']
 assert f['lifecycle_command_identity']==b['lifecycle_invocation_identity']
 assert f['receipt']['result']==b['lifecycle_result_identity']
 assert f['receipt']['project_revision']==b['validated_project_authority_identity']==b['project_revision_identity']
 assert f['component_lock_identities']==b['component_lock_identities']and b['component_lock_identity']in f['component_lock_identities']
 assert b['test_summary']=={'failed':0,'passed':18,'skipped':0,'total':18}and f['receipt']['tests']==18
 assert f['receipt']['project']==b['project_id']=='adhd'
 return {'artifact_path':str(export),'artifact_sha256':sha(export),'rebuild_path':str(regular(rebuild)),'rebuild_sha256':sha(rebuild),
         'receipt_path':str(regular(receipt)),'receipt_sha256':sha(receipt),'receipt_identity':f['receipt_identity'],
         'authority_identity':b['project_revision_identity'],'component_lock_identity':b['component_lock_identity'],
         'lifecycle_request_identity':b['lifecycle_request_identity'],'lifecycle_result_identity':b['lifecycle_result_identity']}

def endpoint(value):
 p=urlsplit(value);assert p.scheme=='http'and p.hostname=='127.0.0.1'and p.port and p.port!=18770
 assert not(p.username or p.password or p.query or p.fragment or p.path.strip('/'))
 return value

def tool(path):
 p=Path(path).absolute();assert p.is_file();resolved=p.resolve()
 return {'path':str(p),'resolved':str(resolved),'sha256':sha(resolved)}

def tool_root(root):
 # External qualified installations may contain intentional symlinks. Record
 # exact paths/targets/content; this is not a recursive OS dependency claim.
 root=Path(root).absolute();assert root.resolve()==root and root.is_dir()
 result={}
 for p in sorted(root.rglob('*')):
  if '__pycache__'in p.parts:continue
  info=p.lstat()
  if stat.S_ISDIR(info.st_mode):continue
  assert p.is_file(),str(p)
  result[str(p.relative_to(root))]={'resolved':str(p.resolve()),'sha256':sha(p.resolve()),'symlink':os.readlink(p)if p.is_symlink()else None}
 return {'path':str(root),'files':result}

def prepare(a):
 official=validate_official(a.export,a.rebuild,a.receipt);rest=endpoint(a.eventing_rest_url)
 repo=a.repo.absolute();assert repo.resolve()==repo
 work=a.work.absolute();assert not work.exists();work.mkdir(parents=True,mode=0o700)
 frozen=work/'frozen';bound=work/'bound';frozen.mkdir(mode=0o700);bound.mkdir(mode=0o700)
 for top in ['tests','scripts','components']:
  for source in sorted((repo/top).rglob('*')):
   if '__pycache__'in source.parts:continue
   if source.is_dir():assert not source.is_symlink();continue
   if source.suffix not in {'.py','.json','.md','.exs','.c'}:continue
   regular(source);dest=frozen/source.relative_to(repo);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
 for source,name in [(a.export,'hub.exs'),(a.rebuild,'rebuild.json'),(a.receipt,'receipt.json')]:shutil.copyfile(source,bound/name)
 shutil.copyfile(__file__,work/'driver.py')
 parsed=ast.parse((frozen/'tests/eventing_readiness_faults.py').read_text())
 cases=next(ast.literal_eval(n.value)for n in parsed.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='CASES'for t in n.targets))
 assert cases==CASES
 tools={'python':tool(a.python),'elixir':tool(a.elixir),'erl':tool(a.erl)}
 roots=[tool_root(p)for p in a.tool_root];assert roots,'Qualified native tool roots must be bound explicitly'
 code="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
 argv=[tools['python']['path'],'-I','-B','-c',code,str(frozen/'tests'),str(frozen/'tests/eventing_readiness_faults.py'),
       '--hub',str(bound/'hub.exs'),'--eventing-rest-url',rest,'--recovery-schema',str(frozen/'components/hub/project-recovery/interface.schema.json'),
       '--keep-work',str(work/'results/fixtures'),'--report',str(work/'results/report.json')]
 env={'HOME':os.environ['HOME'],'LANG':'C.UTF-8','PATH':':'.join(a.path),'ERL_FLAGS':'+S 2:2'}
 for directory in a.path:
  selected=Path(directory);assert selected.is_absolute()and selected.is_dir()and selected.resolve()==selected
 for name in ['elixir','erl']:
  assert shutil.which(name,path=env['PATH'])==tools[name]['path']
  assert any(Path(tools[name]['resolved']).is_relative_to(root['path'])for root in roots)
 plan={'schema':SCHEMA,'status':'UNSTARTED_ROOT_REVIEW_REQUIRED','official':official,'frozen':inventory(frozen),'bound':inventory(bound),
       'driver_sha256':sha(work/'driver.py'),'tools':tools,'tool_roots':roots,'argv':argv,'environment':env,'cases':list(CASES),
       'automatic_retries':0,'parallelism':1,'provider_calls_authorized':0,'outer_timeout':None,
       'scope':'Native real-Kafka21 authored fault cases; no compiled-image, replicated-durability or model-quality claim.'}
 save(work/'plan.json',plan)
 print(json.dumps({'plan':str(work/'plan.json'),'sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],'frozen_files':len(plan['frozen']['files'])}))

def verify(work):
 work=Path(work).absolute();assert work.resolve()==work
 plan=read(work/'plan.json');assert plan['schema']==SCHEMA and regular(__file__)==work/'driver.py'
 assert sha(__file__)==plan['driver_sha256']and inventory(work/'frozen')==plan['frozen']and inventory(work/'bound')==plan['bound']
 o=plan['official'];assert validate_official(o['artifact_path'],o['rebuild_path'],o['receipt_path'])==o
 assert sha(work/'bound/hub.exs')==o['artifact_sha256']and sha(work/'bound/rebuild.json')==o['rebuild_sha256']and sha(work/'bound/receipt.json')==o['receipt_sha256']
 assert plan['cases']==list(CASES)and plan['parallelism']==1 and plan['automatic_retries']==0 and plan['outer_timeout']is None and plan['provider_calls_authorized']==0
 for value in plan['tools'].values():assert tool(value['path'])==value
 for value in plan['tool_roots']:assert tool_root(value['path'])==value
 # Exercise the exact frozen dependency imports before the durable execution
 # claim. Importing this authored module constructs no Fixture/proxy/server.
 code="import sys;sys.path.insert(0,sys.argv[1]);import eventing_readiness_faults"
 imported=subprocess.run([plan['tools']['python']['path'],'-I','-B','-c',code,str(work/'frozen/tests')],
                         cwd=work/'frozen',env=plan['environment'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
 assert imported.returncode==0,'Frozen authored harness dependency imports failed before execution claim'
 assert not imported.stdout and not imported.stderr
 assert inventory(work/'frozen')==plan['frozen']
 return plan

def claim(path):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as stream:stream.write(b'{"claimed":true}\n');stream.flush();os.fsync(stream.fileno())
 sync_dir(path.parent)

def scoped_processes(root):
 marker=str(root).encode();found=[]
 for path in Path('/proc').iterdir():
  if not path.name.isdecimal()or int(path.name)==os.getpid():continue
  try:
   raw=(path/'cmdline').read_bytes()
   if marker in raw:found.append({'pid':int(path.name),'command_sha256':hashlib.sha256(raw).hexdigest(),'start_ticks':int((path/'stat').read_text().split(') ',1)[1].split()[19])})
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 return found

def report_observations(path):
 report=read(path);observed=[r['name']for r in report['checks']]
 attempted=[r['case']for r in report.get('proxy_cleanup',[])]
 assert observed==list(CASES)[:len(observed)]and attempted==list(CASES)[:len(attempted)]
 assert len(observed)<=len(attempted)<=len(observed)+1
 retired=[]
 for name,identity in report.get('native_runtime_cases',{}).items():
  path_stat=Path('/proc',str(identity['pid']),'stat')
  try:current=int(path_stat.read_text().split(') ',1)[1].split()[19])
  except FileNotFoundError:current=None
  retired.append({'case':name,**identity,'same_identity_absent':current!=identity['start_ticks']})
 proxies=report.get('proxy_cleanup',[])
 return report,{'report_sha256':sha(path),'whole_passed':observed,'attempted':attempted,
  'failed_case':attempted[len(observed)]if len(attempted)>len(observed)else None,'unrun':list(CASES[len(attempted):]),
  'native_identity_absence':retired,'proxy_cleanup':proxies,
  'reported_cleanup_verified':all(r['reaped']and r['same_identity_absent']for r in retired)and all(not r['thread_alive']and r['handlers']==0 and not r['failures']and not r['cleanup_failure_types']for r in proxies)}


def execute(work):
 plan=verify(work);work=Path(work).absolute();assert not(work/'results').exists()
 claim(work/'started.json');(work/'results').mkdir(mode=0o700)
 result={'schema':'adhd/eventing-readiness-native21-result@1','passed':False,'plan_sha256':sha(work/'plan.json'),'driver_sha256':sha(__file__),'official':plan['official'],'runtime_started':False,'unrun':list(CASES)}
 child=None;failure=None
 try:
  with (work/'results/stdout.log').open('xb')as out,(work/'results/stderr.log').open('xb')as err:
   child=subprocess.Popen(plan['argv'],cwd=work/'frozen',env=plan['environment'],stdout=out,stderr=err,start_new_session=True)
   result['runtime_started']=True;result['child']={'pid':child.pid,'start_ticks':int(Path('/proc',str(child.pid),'stat').read_text().split(') ',1)[1].split()[19])}
   result['exit_code']=child.wait()
  report,observations=report_observations(work/'results/report.json');result.update(observations)
  assert result['exit_code']==0 and report['passed']is True and result['whole_passed']==list(CASES)
  assert report['artifact_sha256']==plan['official']['artifact_sha256']and report['provider_calls']==0
  assert len(report['native_runtime_cases'])==len(CASES)and len(report['proxy_cleanup'])==len(CASES)
  assert result['reported_cleanup_verified']
  result['passed']=True
 except BaseException as error:failure=error;result['failure_type']=type(error).__name__
 finally:
  if child is not None and child.poll()is None:
   os.killpg(child.pid,signal.SIGINT)
   try:child.wait(15)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait();result['forced_cleanup']=True
  # Capture partial reports and actual identity/cleanup observations even when
  # the child or a whole-case assertion failed; never replace the first error.
  if (work/'results/report.json').exists():
   try:
    _,observations=report_observations(work/'results/report.json');result.update(observations)
   except BaseException as error:result['report_audit_failure_type']=type(error).__name__;result['passed']=False
  result['scoped_processes']=scoped_processes(work/'results')
  try:verify(work);result['post_input_closure_verified']=True
  except BaseException as error:result['post_input_closure_verified']=False;result['closure_failure_type']=type(error).__name__
  result['passed']=bool(result['passed']and result['post_input_closure_verified']and not result['scoped_processes']and not result.get('forced_cleanup'))
  save(work/'result.json',result)
 if failure is not None:raise failure
 assert result['passed']


def main():
 p=argparse.ArgumentParser(__doc__);sub=p.add_subparsers(dest='phase',required=True)
 prep=sub.add_parser('prepare')
 for name in ['repo','work','export','rebuild','receipt','python','elixir','erl']:prep.add_argument('--'+name,type=Path,required=True)
 prep.add_argument('--tool-root',type=Path,action='append',required=True);prep.add_argument('--path',action='append',required=True)
 prep.add_argument('--eventing-rest-url',required=True)
 for name in ['verify','execute']:sub.add_parser(name).add_argument('--work',type=Path,required=True)
 a=p.parse_args()
 if a.phase=='prepare':prepare(a)
 elif a.phase=='verify':verify(a.work);print(json.dumps({'verified':True,'runtime_started':False}))
 else:execute(a.work)
if __name__=='__main__':main()
