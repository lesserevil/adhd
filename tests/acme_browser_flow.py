#!/usr/bin/env python3
"""Once-only actual image/browser gate; no execution without an admitted target."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import stat
import sys


def digest(path):
    path = Path(path)
    entry = path.lstat()
    assert stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1
    assert entry.st_size <= 128 * 1024 * 1024
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-only', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    path = Path(args.plan).absolute()
    assert path == path.resolve(strict=True) and digest(path) == args.plan_sha256
    value = json.loads(path.read_bytes())
    # Authenticate shared bootstrap code before importing it. The bootstrap
    # authenticates all remaining helpers before evaluating target readers.
    driver = Path(__file__).absolute()
    assert driver == driver.resolve(strict=True)
    for name in ['acme_browser_flow.py', 'acme_image_fault_flow.py']:
        helper = driver.with_name(name)
        assert digest(helper) == value['files'][str(helper)]
    # Use an isolated interpreter with an empty alternative bytecode lookup.
    # Third-party modules are admitted only after the full host tree matches.
    assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
    cache = Path(sys.pycache_prefix or '').absolute()
    assert cache == path.parent / 'python-cache' and cache == cache.resolve(strict=True)
    assert cache.is_dir() and not list(cache.iterdir())
    for name, expected in value['files'].items():
        member = Path(name)
        assert member.is_absolute() and member == member.resolve(strict=True)
        assert digest(member) == expected
    if str(driver.parent) not in sys.path:
        sys.path.insert(0, str(driver.parent))
    host_helper = driver.with_name('image_host_dependencies.py')
    assert str(host_helper) in value['files']
    closure_path = value['host_closure']
    assert closure_path in value['files']
    import image_host_dependencies as host
    closure = json.loads(Path(closure_path).read_bytes())
    host.verify(closure)
    assert Path(closure['python_executable']).resolve(strict=True) == Path(sys.executable).resolve(strict=True)
    assert value['browser']['root'] in closure['roots']
    assert value['browser']['executable'] in closure['elf_inputs']
    sites = list(Path(closure['python_executable']).parent.parent.glob('lib/python*/site-packages'))
    assert len(sites) == 1
    assert any(sites[0].is_relative_to(root) for root in map(Path, closure['roots']))
    sys.path.insert(1, str(sites[0]))
    from acme_image_fault_flow import verify
    plan, target, work, marker = verify(path, args.plan_sha256,
                                       profile='browser', driver_path=driver)
    from acme_image_browser import run, verify_browser
    verify_browser(plan['browser'])
    if args.verify_only:
        print(json.dumps({'verified': True, 'executed': False, 'target': target.evidence()}))
        return
    from acme_image_flow import claim_once
    from acme_browser import safe_write
    claim_once(marker, args.plan_sha256)
    primary = None
    report = None
    def expired(signum, frame):
        raise TimeoutError('Fixed actual image/browser phase budget600s')
    old = signal.signal(signal.SIGALRM, expired)
    old_term = signal.signal(signal.SIGTERM, expired)
    signal.alarm(plan['budget_seconds'])
    try:
        report = run(plan, target, work)
        assert report['passed'] is True
    except BaseException as error:
        primary = error
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        signal.signal(signal.SIGTERM, old_term)
        cleanup = []
        for image in target.instances:
            try:
                image.stop()
            except BaseException as error:
                cleanup.append(type(error).__name__)
        host_unchanged = False
        try:
            host.verify(closure)
            host_unchanged = True
        except BaseException as error:
            cleanup.append('host-inputs:' + type(error).__name__)
        result = {'schema': 'adhd/acme-image-browser-flow-result@1',
            'passed': primary is None and report is not None and report['passed'] and not cleanup,
            'plan_sha256': args.plan_sha256, 'target': target.evidence(),
            'runtime_sessions': target.runtime_evidence(),
            'primary_failure_type': type(primary).__name__ if primary else None,
            'cleanup_errors': cleanup, 'manual_visual_review': 'pending',
            'host_inputs_unchanged': host_unchanged,
            'report_sha256': digest(work / 'browser-result.json') if (work / 'browser-result.json').exists() else None}
        try:
            safe_write(marker.with_name('result.json'), result)
        except BaseException as error:
            if primary:
                primary.add_note('Browser final evidence: ' + type(error).__name__)
            else:
                raise
        if cleanup:
            if primary:
                primary.add_note('Owned browser image cleanup: ' + ','.join(cleanup))
            else:
                raise AssertionError('Owned browser image cleanup failed')


if __name__ == '__main__':
    main()
