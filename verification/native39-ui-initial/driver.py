#!/usr/bin/env python3
"""Prepared serial native39 development UI prequalification lane. No app starts without explicit --execute."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def verify(plan):
    driver=Path(__file__)
    assert not driver.is_symlink() and driver.resolve(strict=True)==driver.absolute(), 'Runner redirected'
    assert sha(driver)==plan['driver_sha256'], 'Running driver changed'
    source=Path(plan['inputs_manifest'])
    assert sha(source)==plan['inputs_manifest_sha256'],'Input inventory changed'
    inputs=json.loads(source.read_bytes());base=Path(inputs['frozen_root'])
    assert base.is_absolute() and not base.is_symlink() and base.is_dir(), 'Frozen root redirected/missing'
    assert base.resolve(strict=True)==base, 'Frozen root has redirected ancestor'
    observed=set()
    for tree in inputs['trees']:
        tree_root=base/tree
        assert not tree_root.is_symlink() and tree_root.is_dir(),str(tree_root)
        assert tree_root.resolve(strict=True)==tree_root, 'Input tree root redirected'
        for path in tree_root.rglob('*'):
            assert not path.is_symlink(),str(path)
            if path.is_dir():continue
            assert path.is_file(),str(path)
            observed.add(str(path.relative_to(base)))
    assert observed==set(inputs['files']),'Frozen file set changed'
    for name,value in inputs['files'].items():
        path=base/name
        assert path.stat().st_size==value['bytes'] and sha(path)==value['sha256'],name
    for name,value in inputs['external'].items():
        path=Path(name)
        if 'symlink' in value:
            assert path.is_symlink() and os.readlink(path)==value['symlink'],name
        else:
            assert path.is_file() and sha(path)==value['sha256'],name
            if 'resolved' in value:assert str(path.resolve())==value['resolved'],name
    for root_name, closure in inputs.get('critical_tooling', {}).items():
        root=Path(root_name)
        assert not root.is_symlink() and root.is_dir() and root.resolve(strict=True)==root, 'Tool root redirected'
        observed_tools=set()
        for path in root.rglob('*'):
            assert not path.is_symlink(), 'Tool member redirected: '+str(path)
            if path.is_dir():continue
            assert path.is_file(),str(path)
            observed_tools.add(str(path.relative_to(root)))
        assert observed_tools==set(closure['files']), 'Tool file set changed: '+root_name
        for name, value in closure['files'].items():
            path=root/name
            assert path.stat().st_size==value['bytes'] and sha(path)==value['sha256'],str(path)
    assert sha(plan['artifact']['path'])==plan['artifact']['sha256'],'Artifact changed'


def write(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=Path(__file__).with_name('plan.json'))
    parser.add_argument('--execute',action='store_true',help='Only after explicit root GO and native18 review; DEVELOPMENT ONLY')
    parser.add_argument('--reviewed-plan-sha256',help='Required exact reviewed immutable plan bytes')
    args=parser.parse_args();digest=sha(args.plan);plan=json.loads(args.plan.read_bytes())
    if not args.execute:
        print(json.dumps({'execution':False,'plan_sha256':digest,'suites':[row['name'] for row in plan['serial_lane']]}));return
    assert args.reviewed_plan_sha256==digest,'Explicit reviewed plan hash required'
    verify(plan)
    root=Path(plan['results_root']);root.parent.mkdir(parents=True,exist_ok=True)
    lock=Path(plan['lane_lock']);lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Never reuse a partial or previously completed lane/installation.
        assert not root.exists(),'Results root must be fresh'
        for row in plan['serial_lane']:
            if '--keep-work' in row['argv']:
                assert not Path(row['argv'][row['argv'].index('--keep-work')+1]).exists(),'Fixture root must be fresh'
        root.mkdir(mode=0o700)
        report={'schema':'adhd/native39-development-ui-serial-driver@1','plan_sha256':digest,
            'artifact_sha256':plan['artifact']['sha256'],'passed':False,'rows':[],
            'execution_scope':'DEVELOPMENT PREQUALIFICATION ONLY. No lifecycle admission, image, release or semantic model-quality claim.'}
        environment=dict(os.environ);environment.update(plan['env'])
        for row in plan['serial_lane']:
            verify(plan)
            log=root/(row['name']+'.log');start=time.monotonic();process=None
            result={'suite':row['name'],'argv':row['argv'],'passed':False}
            try:
                with log.open('xb') as output:
                    process=subprocess.Popen(row['argv'],cwd=plan['cwd'],env=environment,
                        stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                    try:code=process.wait(timeout=row['outer_timeout_seconds'])
                    except subprocess.TimeoutExpired:
                        result['outer_timeout']=True
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
                        # Application fixtures have their own sessions: never
                        # claim recursive cleanup merely because runner exited.
                        result['fixture_cleanup_proven']=False
                        raise RuntimeError('Runner timeout; owned fixture cleanup requires inspection')
                result['exit_code']=code
                report_path=Path(row['argv'][row['argv'].index('--report')+1])
                if report_path.exists():
                    result['report_sha256']=sha(report_path)
                    result['report_passed']=json.loads(report_path.read_bytes()).get('passed') is True
                else:result['report_passed']=False
                result['passed']=code==0 and result['report_passed']
                if not result['passed']:raise RuntimeError('Suite failed; no retry or later suite')
            except BaseException as error:
                result['error_type']=type(error).__name__;result['error']=str(error)
                if process is not None and process.poll() is None:
                    result['fixture_cleanup_proven']=False
                    try:
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
                    except BaseException as cleanup:
                        result['runner_cleanup_error_type']=type(cleanup).__name__
            finally:
                result['elapsed_seconds']=time.monotonic()-start
                if log.exists():result['log_sha256']=sha(log)
                report['rows'].append(result);write(root/'driver.json',report)
            if not result['passed']:return 1
        report['passed']=True;write(root/'driver.json',report);return 0


if __name__=='__main__':raise SystemExit(main())
