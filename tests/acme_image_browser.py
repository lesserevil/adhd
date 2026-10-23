"""Owned browser phase for an actual admitted image and real isolated issuer.

Importing this module starts nothing. The once-controller authenticates its plan,
complete helper/tool closure and exclusive CA phase before calling run(). This
phase keeps the original browser assertions and leaves visual approval pending.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import uuid4


def browser_binding(root, executable):
    """Read-only inventory of the explicitly selected installed Chromium tree."""
    root, executable = Path(root).absolute(), Path(executable).absolute()
    assert root == root.resolve(strict=True) and root.is_dir()
    owner = root.lstat()
    assert owner.st_uid in (0, os.getuid()) and not owner.st_mode & 0o022
    assert executable == executable.resolve(strict=True) and executable.is_relative_to(root)
    files, directories = {}, []
    for path in sorted(root.rglob('*')):
        entry = path.lstat()
        assert not path.is_symlink() and entry.st_uid in (0, os.getuid())
        assert not entry.st_mode & 0o022, 'Writable browser dependency'
        relative = str(path.relative_to(root))
        if stat.S_ISDIR(entry.st_mode):
            directories.append(relative)
        else:
            assert stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1
            files[relative] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'mode': stat.S_IMODE(entry.st_mode)}
    assert executable.is_file() and os.access(executable, os.X_OK)
    inventory = {'files': files, 'directories': directories}
    raw = json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode()
    return {'root': str(root), 'executable': str(executable),
            'inventory_sha256': hashlib.sha256(raw).hexdigest(),
            'file_count': len(files)}


def verify_browser(value):
    assert isinstance(value, dict) and set(value) == {
        'root', 'executable', 'inventory_sha256', 'file_count'}
    assert browser_binding(value['root'], value['executable']) == value, 'Browser input changed'



def normalized_tls(session):
    """Observe public normalization; permit only the expected owned CA path."""
    expected=copy.deepcopy(session.tls)
    assert expected['acme']['ca_cert_file']=='directory-root.pem'
    path=Path(session.hub)/'directory-root.pem';assert path.is_absolute()
    expected['acme']['ca_cert_file']=str(path)
    actual=session.admin.api({'op':'config_get'})['config']['tls']
    assert actual==expected,'Unexpected TLS normalization or configuration drift'
    return actual


async def inspect(session, plan, work, report):
    from playwright.async_api import async_playwright
    from acme_browser import run_browser_phase, safe_write

    expected_tls = normalized_tls(session)
    credentials = work / 'browser-credentials'
    credentials.mkdir(mode=0o700)
    paths = {}
    paths['Admin'] = credentials / 'admin.json'
    safe_write(paths['Admin'], {'username': 'admin', 'password': session.password})
    for role in ('Developer', 'Viewer'):
        username, password = role.lower(), uuid4().hex + '-owned-browser-role'
        session.admin.mutate('save_user', user={'username': username, 'name': role,
            'email': username + '@fixture.invalid', 'role': role, 'password': password})
        paths[role] = credentials / (username + '.json')
        safe_write(paths[role], {'username': username, 'password': password})

    async def custody():
        # The VM is the inspected image VM, never the local Docker client PID.
        session.runtime.checkpoint('browser-custody')
        assert session.secure.request('/health')[0] == 200

    driver = browser = None
    primary = None
    try:
        driver = await async_playwright().start()
        browser = await driver.chromium.launch(executable_path=plan['browser']['executable'],
            headless=True, args=['--no-sandbox'], timeout=30000)
        report['browser'] = await asyncio.wait_for(run_browser_phase(browser,
            base=session.runtime.base, credential_files=paths,
            output_dir=work / 'browser-captures', expected_tls=expected_tls,
            serial_id={'image': plan['target']['image'], 'work': str(work)},
            custody_check=custody), timeout=240)
        assert report['browser']['passed'] is True
        assert report['browser']['manual_visual_review'] == 'pending'
        await custody()
        assert session.admin.api({'op': 'config_get'})['config']['tls'] == expected_tls
    except BaseException as error:
        primary = error
        raise
    finally:
        # Driver shutdown remains independent of browser close failure.
        errors = []
        if browser:
            try:
                await asyncio.wait_for(browser.close(), timeout=20)
                report['browser_closed'] = True
            except BaseException as error:
                errors.append(('browser', error))
        if driver:
            try:
                await asyncio.wait_for(driver.stop(), timeout=20)
                report['playwright_driver_closed'] = True
            except BaseException as error:
                errors.append(('playwright', error))
        report['browser_cleanup_errors'] = [{'scope': scope, 'type': type(error).__name__}
                                             for scope, error in errors]
        if errors:
            if primary:
                for scope, error in errors:
                    primary.add_note('Owned browser cleanup ' + scope + ': ' + type(error).__name__)
            else:
                raise AssertionError('Owned browser/driver cleanup failed') from None


def run(plan, target, work):
    """Call only from the reviewed once-controller; all setup is caller-owned."""
    from acme_image_provision import OwnedProvision
    from acme_process_observer import Descendants
    from acme_runtime import ticks
    from acme_browser import safe_write

    work = Path(work).absolute()
    verify_browser(plan['browser'])
    assert not work.exists() and work == work.resolve()
    report = {'schema': 'adhd/acme-image-browser@1', 'passed': False,
        'target': target.evidence(), 'browser_binding': plan['browser'],
        'manual_visual_review': 'pending', 'browser_closed': False,
        'playwright_driver_closed': False, 'failure_type': None, 'cleanup_errors': [],
        'scope': 'Actual admitted default-entrypoint image; real isolated issuance; private HTTP Admin UI plus independently trusted HTTPS custody. No public CA claim.'}
    session = OwnedProvision(plan, target, work)
    observer = Descendants(os.getpid(), ticks(os.getpid())).start()
    primary = None
    try:
        session.start()
        asyncio.run(inspect(session, plan, work, report))
        report['passed'] = True
    except BaseException as error:
        primary = error
        report['failure_type'] = type(error).__name__
        raise
    finally:
        for scope, close in [('provision', session.close), ('descendants', observer.close)]:
            try:
                close()
            except BaseException as error:
                report['passed'] = False
                report['cleanup_errors'].append({'scope': scope, 'type': type(error).__name__})
                if primary:
                    primary.add_note('Owned browser phase cleanup ' + scope + ': ' + type(error).__name__)
        report['session'] = session.evidence()
        report['observed_descendants'] = observer.evidence()
        try:
            verify_browser(plan['browser'])
            report['browser_inputs_unchanged'] = True
        except BaseException:
            report['browser_inputs_unchanged'] = False
            report['passed'] = False
        try:
            safe_write(work / 'browser-result.json', report)
        except BaseException as error:
            if primary:
                primary.add_note('Browser phase evidence: ' + type(error).__name__)
            else:
                raise
        if not primary and not report['passed']:
            raise AssertionError('Owned image browser phase custody/cleanup failed')
    return report
