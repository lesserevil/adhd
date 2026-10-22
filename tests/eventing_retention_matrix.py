#!/usr/bin/env python3
"""Closed retention companion; prepare/verify metadata-only, execute needs GO.

Native official lifecycle binding first. The scenario also supports an owned
image directly; a compiled-image wrapper must separately bind image admission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import stat
sys.dont_write_bytecode=True
def bootstrap():
    here=Path(__file__).absolute()
    if here.name=='driver.py':
        def owned(path):
            info=path.lstat()
            assert path.resolve()==path and stat.S_ISREG(info.st_mode)and info.st_nlink==1 and info.st_uid==os.getuid()
            return path
        plan=json.loads(owned(here.parent/'plan.json').read_text())
        assert plan['schema']=='adhd/eventing-retention-native-plan@1'
        assert hashlib.sha256(owned(here).read_bytes()).hexdigest()==plan['driver_sha256']
        selected=here.parent/'frozen/tests/eventing_readiness_matrix.py'
        assert hashlib.sha256(owned(selected).read_bytes()).hexdigest()==plan['frozen']['files']['tests/eventing_readiness_matrix.py']
        sys.path.insert(0,str(selected.parent))
    else:sys.path.insert(0,str(here.parent))
bootstrap()
import eventing_readiness_matrix as base

SCHEMA='adhd/eventing-retention-native-plan@1'
CHECKS=['actual-postdecision-retention-failure-keeps-desired-policy-and-decision',
        'unchanged-files-cold-start-replays-desired-retention-before-readiness',
        'second-cold-start-does-not-repeat-alter-reset-offset-or-replay-ack']


def prepare(a):
    official=base.validate_official(a.export,a.rebuild,a.receipt)
    rest=base.endpoint(a.eventing_rest_url);repo=a.repo.absolute();assert repo.resolve()==repo
    work=a.work.absolute();assert not work.exists();work.mkdir(parents=True,mode=0o700)
    frozen=work/'frozen';bound=work/'bound';frozen.mkdir(mode=0o700);bound.mkdir(mode=0o700)
    for top in ['tests','scripts','components']:
        for source in sorted((repo/top).rglob('*')):
            if '__pycache__'in source.parts:continue
            if source.is_dir():assert not source.is_symlink();continue
            if source.suffix not in {'.py','.json','.md','.exs','.c'}:continue
            base.regular(source);dest=frozen/source.relative_to(repo);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    for source,name in [(a.export,'hub.exs'),(a.rebuild,'rebuild.json'),(a.receipt,'receipt.json')]:shutil.copyfile(source,bound/name)
    shutil.copyfile(__file__,work/'driver.py')
    tools={'python':base.tool(a.python),'elixir':base.tool(a.elixir),'erl':base.tool(a.erl)}
    roots=[base.tool_root(p)for p in a.tool_root];assert roots
    env={'HOME':os.environ['HOME'],'LANG':'C.UTF-8','PATH':':'.join(a.path),'ERL_FLAGS':'+S 2:2'}
    for directory in a.path:
        selected=Path(directory);assert selected.is_absolute()and selected.is_dir()and selected.resolve()==selected
    for name in ('elixir','erl'):
        assert shutil.which(name,path=env['PATH'])==tools[name]['path']
        assert any(Path(tools[name]['resolved']).is_relative_to(root['path'])for root in roots)
    code="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    argv=[tools['python']['path'],'-I','-B','-c',code,str(frozen/'tests'),str(frozen/'tests/eventing_retention_recovery.py'),
          '--hub',str(bound/'hub.exs'),'--eventing-rest-url',rest,'--recovery-schema',str(frozen/'components/hub/project-recovery/interface.schema.json'),
          '--keep-work',str(work/'results/fixture'),'--report',str(work/'results/report.json')]
    plan={'schema':SCHEMA,'status':'UNSTARTED_ROOT_REVIEW_REQUIRED','official':official,'frozen':base.inventory(frozen),'bound':base.inventory(bound),
          'driver_sha256':base.sha(work/'driver.py'),'tools':tools,'tool_roots':roots,'environment':env,'argv':argv,'checks':CHECKS,
          'automatic_retries':0,'parallelism':1,'provider_calls_authorized':0,'outer_timeout':None,
          'scope':'Separate native postdecision-retention negative/recovery; no main23 or compiled-image qualification claim'}
    base.save(work/'plan.json',plan)
    print(json.dumps({'plan':str(work/'plan.json'),'sha256':base.sha(work/'plan.json'),'driver_sha256':plan['driver_sha256']}))


def verify(work):
    work=Path(work).absolute();assert work.resolve()==work
    p=base.read(work/'plan.json');assert p['schema']==SCHEMA and base.regular(__file__)==work/'driver.py'
    assert base.sha(__file__)==p['driver_sha256']and base.inventory(work/'frozen')==p['frozen']and base.inventory(work/'bound')==p['bound']
    o=p['official'];assert base.validate_official(o['artifact_path'],o['rebuild_path'],o['receipt_path'])==o
    for name,key in [('hub.exs','artifact_sha256'),('rebuild.json','rebuild_sha256'),('receipt.json','receipt_sha256')]:assert base.sha(work/'bound'/name)==o[key]
    assert p['checks']==CHECKS and p['automatic_retries']==0 and p['parallelism']==1 and p['provider_calls_authorized']==0 and p['outer_timeout']is None
    for t in p['tools'].values():assert base.tool(t['path'])==t
    for t in p['tool_roots']:assert base.tool_root(t['path'])==t
    code="import sys;sys.path.insert(0,sys.argv[1]);import eventing_retention_recovery"
    child=subprocess.run([p['tools']['python']['path'],'-I','-B','-c',code,str(work/'frozen/tests')],cwd=work/'frozen',env=p['environment'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    assert child.returncode==0 and not child.stdout and not child.stderr,'Frozen import-only preflight failed'
    assert base.inventory(work/'frozen')==p['frozen']
    return p


def observations(path):
    report_path=Path(path)
    report=base.read(path);assert report['suite']=='adhd/eventing-retention-recovery@1'
    assert all(row.get('passed')is True for row in report['checks'])
    whole=[row['name']for row in report['checks']];assert whole==CHECKS[:len(whole)]
    retired=[]
    for row in report.get('native_runtime_cases',[]):
        path=Path('/proc',str(row['pid']),'stat')
        try:current=int(path.read_text().split(') ',1)[1].split()[19])
        except FileNotFoundError:current=None
        retired.append({**row,'same_identity_absent':current!=row['start_ticks']})
    proxy=report.get('proxy_cleanup',{})
    cleanup=all(row.get('reaped')and row['same_identity_absent']for row in retired)and not report.get('cleanup_failure_types')and proxy.get('handlers')==0 and proxy.get('thread_alive')is False and not proxy.get('failures')
    return report,{'whole_passed':whole,'unrun':CHECKS[len(whole):],'report_sha256':base.sha(report_path),'native_identity_absence':retired,'reported_cleanup_verified':cleanup}


def execute(work):
    p=verify(work);work=Path(work).absolute();assert not(work/'results').exists()
    base.claim(work/'started.json');(work/'results').mkdir(mode=0o700)
    result={'schema':'adhd/eventing-retention-native-result@1','passed':False,'plan_sha256':base.sha(work/'plan.json'),'official':p['official'],'runtime_started':False}
    child=None;failure=None
    try:
        with(work/'results/stdout.log').open('xb')as out,(work/'results/stderr.log').open('xb')as err:
            child=subprocess.Popen(p['argv'],cwd=work/'frozen',env=p['environment'],stdout=out,stderr=err,start_new_session=True)
            result['runtime_started']=True;result['child']={'pid':child.pid,'start_ticks':int(Path('/proc',str(child.pid),'stat').read_text().split(') ',1)[1].split()[19])};result['exit_code']=child.wait()
        report,observed=observations(work/'results/report.json');result.update(observed)
        assert result['exit_code']==0 and report['passed']is True and observed['whole_passed']==CHECKS
        assert report['artifact_sha256']==p['official']['artifact_sha256']and report['provider_calls']==0
        assert len(report['native_runtime_cases'])==3 and observed['reported_cleanup_verified'];result['passed']=True
    except BaseException as error:failure=error;result['failure_type']=type(error).__name__
    finally:
        if child is not None and child.poll()is None:
            os.killpg(child.pid,signal.SIGINT)
            try:child.wait(15)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait();result['forced_cleanup']=True
        if(work/'results/report.json').exists():
            try:_,observed=observations(work/'results/report.json');result.update(observed)
            except BaseException as error:result['report_audit_failure_type']=type(error).__name__;result['passed']=False
        result['scoped_processes']=base.scoped_processes(work/'results')
        try:verify(work);result['post_input_closure_verified']=True
        except BaseException as error:result['post_input_closure_verified']=False;result['closure_failure_type']=type(error).__name__
        result['passed']=bool(result['passed']and result['post_input_closure_verified']and not result['scoped_processes']and not result.get('forced_cleanup'))
        base.save(work/'result.json',result)
    if failure is not None:raise failure
    assert result['passed']


def main():
    p=argparse.ArgumentParser(__doc__);sub=p.add_subparsers(dest='phase',required=True);a=sub.add_parser('prepare')
    for name in ('repo','work','export','rebuild','receipt','python','elixir','erl'):a.add_argument('--'+name,type=Path,required=True)
    a.add_argument('--tool-root',type=Path,action='append',required=True);a.add_argument('--path',action='append',required=True);a.add_argument('--eventing-rest-url',required=True)
    for name in ('verify','execute'):sub.add_parser(name).add_argument('--work',type=Path,required=True)
    args=p.parse_args()
    if args.phase=='prepare':prepare(args)
    elif args.phase=='verify':verify(args.work);print(json.dumps({'verified':True,'runtime_started':False}))
    else:execute(args.work)
if __name__=='__main__':main()
