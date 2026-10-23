#!/usr/bin/env python3
"""Once-only independently selected real-CA image fault phase. Inert on import.

Every run uses a fresh owned hub and a real trusted issued baseline. It is a
separate gate, not a substitute for full foundation/rebind/account qualification.
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


def verify(path,expected,*,profile='fault',driver_path=None):
    path=Path(path).absolute();assert path==path.resolve(strict=True)and digest(path)==expected
    plan=json.loads(path.read_text());driver=Path(driver_path or __file__).absolute()
    assert profile in ('fault','browser')
    if profile=='fault':assert driver==Path(__file__).absolute()
    else:assert driver.name=='acme_browser_flow.py'
    assert driver==driver.resolve(strict=True)
    assert plan['schema']==('adhd/acme-image-fault-flow@1'if profile=='fault'else'adhd/acme-image-browser-flow@1')
    assert plan['driver']==str(driver)and plan['driver_sha256']==digest(driver)
    assert isinstance(plan.get('target'),dict),'Actual accepted image target required'
    for name,value in plan['files'].items():
        item=Path(name);entry=item.lstat()
        assert item.is_absolute()and item==item.resolve(strict=True)
        assert stat.S_ISREG(entry.st_mode)and entry.st_nlink==1 and digest(item)==value
    required=['acme_image_fault_flow.py','acme_image_flow.py','acme_image_target.py','acme_image_session.py',
      'acme_image_runtime.py','acme_image_provision.py','acme_image_faults.py','acme_runtime.py','acme_account_continuation.py',
      'acme_acceptance.py','acme_acceptance_fixtures.py','acme_challenge_relay.py','acme_issuer_fault_relay.py',
      'acme_fault_cases.py','acme_continuity.py','acme_rebind_acceptance.py','acme_process_observer.py','container_fixture.py',
      'image_compiled_inputs.py','image_compiled_admission.py','image_payload_audit.py']
    assert str(driver)in plan['files']
    if profile=='browser':required+=['acme_browser.py','acme_browser_flow.py','acme_image_browser.py']
    assert all(str(driver.with_name(name))in plan['files']for name in required)
    assert plan['python']==str(Path(sys.executable).resolve())
    for name,value in plan['tool_files'].items():
        item=Path(name);assert item.is_absolute()and item==item.resolve(strict=True)and digest(item)==value
    assert plan['python']in plan['tool_files']
    for key in ['ca_manifest','schema_file','configure']:
        assert plan[key]in plan['files']
    work=Path(plan['work']);marker=path.with_name('started.json')
    assert work.is_absolute()and work==work.resolve()and not work.exists()
    assert not marker.exists()and not path.with_name('result.json').exists()
    assert plan['budget_seconds']==600
    # Imports happen only after the complete declared frozen helper set matches.
    if str(driver.parent)not in sys.path:sys.path.insert(0,str(driver.parent))
    from acme_image_faults import CASES
    from acme_image_target import AcceptedImageTarget
    if profile=='fault':assert plan['case']in CASES
    else:assert 'case'not in plan and isinstance(plan['browser'],dict)
    fixture=plan['issuer_relay']
    assert set(fixture)=={'cert_file','key_file','root_file','cert_sha256','key_sha256','root_sha256'}
    for name in ['cert','key','root']:
        assert fixture[name+'_file']in plan['files']and digest(fixture[name+'_file'])==fixture[name+'_sha256']
    target=AcceptedImageTarget(plan)
    return plan,target,work,marker


def run(plan,target,work):
    from acme_image_provision import OwnedProvision
    from acme_image_faults import FLOOR_CASES,POLICY_CASES,LOSS_CASES,BASIC_CASES,floor_phase,policy_phase,loss_phase,basic_phase,expiry_phase
    primary=None;session=OwnedProvision(plan,target,work)
    report={'passed':False,'case':plan['case'],'checks':[],'scope':'Separate real-CA fault gate; does not qualify the full foundation or other fault selections',
      'target':target.evidence(),'ca_manifest_sha256':digest(plan['ca_manifest']),'public_ca_calls':0}
    try:
        session.start()
        runtime,admin,secure,hub=session.runtime,session.admin,session.secure,session.hub
        issuer,challenge,ca,password=session.issuer,session.challenge,session.ca,session.password
        facts=session.certificate
        report['checks'].append({'name':'genuine real-CA baseline and independently trusted active key','passed':True,'certificate':facts})
        runtime.checkpoint('real-fault-baseline')
        case=plan['case'];common={'admin':admin,'secure':secure,'runtime':runtime,'hub':hub}
        if case in FLOOR_CASES:
            result=floor_phase(case,**common,issuer=issuer,issuer_root=ca['issuer_root'],password=password)
        elif case in POLICY_CASES:
            result=policy_phase(case,**common,challenge=challenge,issuer_root=ca['issuer_root'])
        elif case in LOSS_CASES:
            result=loss_phase(case,**common,challenge=challenge,issuer_root=ca['issuer_root'],password=password,target=target)
        elif case in BASIC_CASES:
            result=basic_phase(case,admin=admin,secure=secure,hub=hub,challenge=challenge,issuer_root=ca['issuer_root'])
        else:result=expiry_phase(admin=admin,secure=secure,hub=hub,issuer=issuer)
        assert result['passed']is True
        report['checks'].append(result);report['passed']=True
    except BaseException as error:primary=error;raise
    finally:
        cleanup=[]
        try:session.close()
        except BaseException as error:cleanup.append(type(error).__name__)
        report.update(primary_failure_type=type(primary).__name__ if primary else None,cleanup_errors=cleanup,
          provision=session.evidence())
        if cleanup:report['passed']=False
        try:
            output=work/'report.json'
            with output.open('x')as stream:json.dump(report,stream,indent=2);stream.write('\n')
            output.chmod(0o600)
        except BaseException as error:
            if primary:primary.add_note('Fault evidence: '+type(error).__name__)
            else:raise
        if cleanup:
            if primary:primary.add_note('Fault cleanup: '+','.join(cleanup))
            else:raise AssertionError('Owned real fault cleanup failed')


def execute(plan,target,work,marker,expected):
    from acme_image_flow import claim_once
    claim_once(marker,expected)
    primary=None
    def expired(signum,frame):raise TimeoutError('Fixed separate fault phase budget600s')
    old=signal.signal(signal.SIGALRM,expired);term=signal.signal(signal.SIGTERM,expired);signal.alarm(600)
    try:run(plan,target,work)
    except BaseException as error:primary=error;raise
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,old);signal.signal(signal.SIGTERM,term)
        cleanup=[]
        for image in target.instances:
            try:image.stop()
            except BaseException as error:cleanup.append(type(error).__name__)
        result={'passed':primary is None and not cleanup,'case':plan['case'],'plan_sha256':expected,
          'primary_failure_type':type(primary).__name__ if primary else None,'cleanup_errors':cleanup,
          'target':target.evidence(),'runtime_sessions':target.runtime_evidence(),
          'report_sha256':digest(work/'report.json')if(work/'report.json').exists()else None}
        try:
            with marker.with_name('result.json').open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
            marker.with_name('result.json').chmod(0o600)
        except BaseException as error:
            if primary:primary.add_note('Fault final result: '+type(error).__name__)
            else:raise
        if cleanup:
            if primary:primary.add_note('Image fault cleanup: '+','.join(cleanup))
            else:raise AssertionError('Image fault cleanup failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--verify-only',action='store_true');mode.add_argument('--execute',action='store_true')
    args=parser.parse_args();plan,target,work,marker=verify(args.plan,args.plan_sha256)
    if args.execute:execute(plan,target,work,marker,args.plan_sha256)
    else:print(json.dumps({'verified':True,'executed':False,'target':target.evidence(),'case':plan['case']}))


if __name__=='__main__':main()
