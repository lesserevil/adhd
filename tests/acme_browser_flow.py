#!/usr/bin/env python3
"""Once-only actual image/browser gate; no execution without an admitted target."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    if str(driver.parent) not in sys.path:
        sys.path.insert(0, str(driver.parent))
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
        result = {'schema': 'adhd/acme-image-browser-flow-result@1',
            'passed': primary is None and report is not None and report['passed'] and not cleanup,
            'plan_sha256': args.plan_sha256, 'target': target.evidence(),
            'runtime_sessions': target.runtime_evidence(),
            'primary_failure_type': type(primary).__name__ if primary else None,
            'cleanup_errors': cleanup, 'manual_visual_review': 'pending',
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
