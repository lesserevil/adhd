#!/usr/bin/env python3
"""Once-only default-entrypoint image foundation/rebind/account continuation.

A preparation may carry target:null. Verification/execution refuse it. No image
identity or passing admission is synthesized; actual target input is mandatory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify(plan_path,expected):
    plan_path=Path(plan_path).absolute();assert plan_path==plan_path.resolve(strict=True)
    assert digest(plan_path)==expected
    plan=json.loads(plan_path.read_text())
    assert plan['schema']=='adhd/acme-image-flow@1'
    driver=Path(__file__).absolute();assert driver==driver.resolve(strict=True)
    assert plan['driver']==str(driver)and plan['driver_sha256']==digest(driver)
    assert isinstance(plan.get('target'),dict),'No accepted image target has been bound'
    assert isinstance(plan['files'],dict)and str(driver)in plan['files']
    for name,value in plan['files'].items():
        path=Path(name);assert path.is_absolute()and path==path.resolve(strict=True)
        st=path.lstat();assert stat.S_ISREG(st.st_mode)and st.st_nlink==1
        assert digest(path)==value,'Frozen image flow dependency changed'
    tools=plan['tool_files'];assert isinstance(tools,dict)and str(Path(sys.executable).resolve())in tools
    for name,value in tools.items():
        path=Path(name);assert path.is_absolute()and path==path.resolve(strict=True)
        assert path.is_file()and digest(path)==value,'Reviewed tool dependency changed'
    required=['acme_acceptance.py','acme_account_continuation.py','acme_acceptance_fixtures.py',
      'acme_challenge_relay.py','acme_runtime.py','acme_process_observer.py','acme_continuity.py',
      'acme_rebind_acceptance.py','acme_image_runtime.py','acme_image_session.py','acme_image_target.py',
      'container_fixture.py','image_compiled_inputs.py','image_compiled_admission.py','image_payload_audit.py']
    assert all(str(driver.with_name(name))in plan['files']for name in required)
    assert plan['python_executable']==str(Path(sys.executable).resolve())
    argv=plan['program_argv'];assert argv.count('--work')==1
    assert '--execute'in argv and argv[argv.index('--phase')+1]=='full'
    assert '--rebind'in argv and '--account-continuation'in argv
    assert not any(x in argv for x in ['--source','--cache','--elixir','--erlang','--cache-manifest-sha256'])
    work=Path(argv[argv.index('--work')+1]).absolute();assert work==work.resolve()and not work.exists()
    marker=Path(plan['once_marker']).absolute();assert marker.parent==plan_path.parent
    assert not marker.exists()and not marker.with_name('result.json').exists()
    for name in ['--schema','--configure','--ca-manifest']:
        assert argv.count(name)==1 and str(Path(argv[argv.index(name)+1]).absolute())in plan['files']
    # These imports happen only after the actual canonical driver and complete
    # declared helper closure have been authenticated with stdlib operations.
    helpers=str(driver.parent)
    if helpers not in sys.path:sys.path.insert(0,helpers)
    if plan.get('tool_roots')or plan.get('frozen'):
        assert str(driver.with_name('acme_image_plan_prepare.py'))in plan['files']
        from acme_image_plan_prepare import verify_tool_roots
        verify_tool_roots(plan)
    for key,value in plan.get('execution_env',{}).items():assert os.environ.get(key)==value,'Reviewed execution environment changed'
    from acme_image_target import AcceptedImageTarget
    target=AcceptedImageTarget(plan)
    return plan,target,work,marker


def claim_once(marker,plan_sha256):
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w')as stream:
        json.dump({'plan_sha256':plan_sha256,'pid':os.getpid()},stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    fd=os.open(marker.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def execute(plan,target,work,marker,plan_sha256):
    import acme_acceptance
    import acme_rebind_acceptance
    import acme_continuity
    from acme_image_session import runtime_class
    from acme_runtime import ticks,regular,sha
    argv=plan['program_argv']
    ca_path=Path(argv[argv.index('--ca-manifest')+1]);regular(ca_path)
    assert sha(ca_path)==argv[argv.index('--ca-manifest-sha256')+1]
    ca=json.loads(ca_path.read_text())
    assert ca['ready']and ca['real_validation']and ca['nonce_validation']and ca['public_ca_calls']==0
    for row in ca['processes']:assert ticks(row['pid'])==row['start_ticks'],'Reviewed real CA lease identity changed'
    for name in ['frontend_root','issuer_root']:assert sha(ca[name])==ca[name+'_sha256']
    claim_once(marker,plan_sha256)
    cls=runtime_class(target,work)
    originals=[acme_acceptance.NativeDiagnostic,acme_rebind_acceptance.NativeDiagnostic,acme_continuity.NativeDiagnostic]
    old_argv=sys.argv
    primary=None;passed=False
    try:
        acme_acceptance.NativeDiagnostic=acme_rebind_acceptance.NativeDiagnostic=acme_continuity.NativeDiagnostic=cls
        sys.argv=[str(Path(__file__).with_name('acme_acceptance.py')),*argv]
        acme_acceptance.main()
        report=json.loads((work/'report.json').read_text());assert report['passed']is True
        assert len(report['checks'])==(18 if '--continuity'in argv else 16)
        assert all(x['passed']is True for x in report['checks'])
        for image in target.instances:
            assert image.name is None and not image.probe_cleanup_blocked
        passed=True
    except BaseException as error:primary=error;raise
    finally:
        sys.argv=old_argv
        acme_acceptance.NativeDiagnostic,acme_rebind_acceptance.NativeDiagnostic,acme_continuity.NativeDiagnostic=originals
        cleanup=[]
        for image in target.instances:
            try:image.stop()
            except BaseException as error:cleanup.append(type(error).__name__)
        result={'schema':'adhd/acme-image-flow-result@1','passed':passed and not cleanup,
          'plan_sha256':plan_sha256,'target':target.evidence(),'runtime_sessions':target.runtime_evidence(),
          'primary_failure_type':type(primary).__name__ if primary else None,'cleanup_errors':cleanup,
          'report_sha256':digest(work/'report.json')if(work/'report.json').exists()else None,
          'scope':'Actual default-entrypoint image foundation/rebind/account continuation; no native-cache launcher or entrypoint substitution'}
        try:
            output=Path(plan['once_marker']).with_name('result.json')
            with output.open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
            output.chmod(0o600)
        except BaseException as error:
            if primary:primary.add_note('Image flow evidence: '+type(error).__name__)
            else:raise
        if cleanup:
            if primary:primary.add_note('Image flow cleanup: '+','.join(cleanup))
            else:raise AssertionError('Owned image flow cleanup failed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',required=True);p.add_argument('--plan-sha256',required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--verify-only',action='store_true');mode.add_argument('--execute',action='store_true')
    args=p.parse_args();plan,target,work,marker=verify(args.plan,args.plan_sha256)
    if args.execute:execute(plan,target,work,marker,args.plan_sha256)
    else:print(json.dumps({'verified':True,'executed':False,'target':target.evidence()}))


if __name__=='__main__':main()
