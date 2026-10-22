"""Inert, caller-owned Playwright hook for the Admin TLS console.

The caller owns the admitted hub, local CA, browser/tool closure and exclusive
mutation phase. Importing this file starts nothing. run_browser_phase never
launches/stops a hub, CA, browser or provider and never makes direct Admin API
mutations. It creates serial browser contexts only. Run --self-test for pure guards.

Credential files are closed owner-private JSON {username,password}. Supply all
three existing roles; this hook does not provision users. expected_tls must be the
actual normalized current TLS object. It edits/restores only retry_seconds and
requests renewal once, after restore. Accepted renewal is not issuance proof.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from contextlib import asynccontextmanager
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path
import stat
import sys
from urllib.parse import urlsplit

FIELDS = (
    ('Enable native HTTPS', 'enabled', 'checkbox'),
    ('HTTPS bind address', 'host', 'text'),
    ('HTTPS listener port', 'port', 'number'),
    ('Challenge bind address', 'challenge_host', 'text'),
    ('Challenge listener port', 'challenge_port', 'number'),
    ('Enable ACME issuance and renewal', 'acme.enabled', 'checkbox'),
    ('ACME directory URL', 'acme.directory_url', 'text'),
    ('Contact email', 'acme.email', 'email'),
    ('Hostnames (one per line)', 'acme.domains', 'textarea'),
    ('Accept this issuer’s account terms', 'acme.accept_terms', 'checkbox'),
    ('Renew before expiry (days)', 'acme.renew_before_days', 'number'),
    ('Retry delay (seconds)', 'acme.retry_seconds', 'number'),
    ('Order timeout (milliseconds)', 'acme.order_timeout_ms', 'number'),
    ('Private ACME issuer CA certificate file (optional)', 'acme.ca_cert_file', 'text'),
)
SAVE_DIALOG = 'Apply these TLS settings immediately? Listener changes take effect without restarting.'
RENEW_DIALOG = 'Request renewal using the current issuer, account and hostnames? Issuer rate limits still apply.'
API_OPS = {'list_projects', 'project_restore_status', 'overview', 'users',
           'config_get', 'config_update', 'tls_status', 'tls_renew'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _closed(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, 'Duplicate private credential key'
        result[key] = value
    return result


def read_credentials(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        assert not parent.is_symlink(), 'Redirected credential path'
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
    assert before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
    assert before.st_size <= 8192
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        assert identity(opened) == identity(before)
        raw = os.read(fd, 8193)
        assert len(raw) == before.st_size and not os.read(fd, 1)
        assert identity(os.fstat(fd)) == identity(before) == identity(path.lstat())
    finally:
        os.close(fd)
    value = json.loads(raw, object_pairs_hook=_closed)
    assert set(value) == {'username', 'password'}
    assert isinstance(value['username'], str) and 0 < len(value['username']) <= 128
    assert isinstance(value['password'], str) and 0 < len(value['password']) <= 1024
    return value


def private_base(base):
    parsed = urlsplit(base)
    assert parsed.scheme in ('http', 'https') and not parsed.username and not parsed.password
    assert parsed.path in ('', '/') and not parsed.query and not parsed.fragment
    assert parsed.port and ipaddress.ip_address(parsed.hostname).is_loopback
    return base.rstrip('/')


def field_value(tls, key):
    value = tls
    for part in key.split('.'):
        value = value[part]
    return value


def next_retry(original):
    assert type(original) is int and 30 <= original <= 86400
    return original + 1 if original < 86400 else original - 1


def safe_write(path, value):
    data = json.dumps(value, indent=2).encode() + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        raise


def request_op(request, base, op):
    if request.url != base + '/admin/api' or request.method != 'POST':
        return False
    value = request.post_data_json
    return isinstance(value, dict) and value.get('op') == op


@asynccontextmanager
async def owned_context(browser, viewport, report, label):
    context = await browser.new_context(viewport=viewport, ignore_https_errors=False)
    primary = None
    try:
        yield context
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            await context.close()
            report['contexts_closed'].append(label)
        except BaseException as exc:
            report['cleanup_errors'].append({'phase': 'close-context', 'type': type(exc).__name__})
            if primary is None:
                raise AssertionError('Owned browser context cleanup failed') from None


async def run_browser_phase(browser, *, base, credential_files, output_dir,
                            expected_tls, serial_id, custody_check=None):
    """Run only during a caller-authorized exclusive browser/CA mutation phase.

    browser is already launched by its owner. credential_files maps the existing
    Admin/Developer/Viewer roles to private files. custody_check, if supplied, is
    an async read-only assertion before/after UI changes, owned by the caller.
    Captures are private ignored diagnostics; a human must review both viewports.
    """
    from playwright.async_api import expect
    from browser_observation import BrowserObservation

    source_bytes = Path(__file__).read_bytes()
    base = private_base(base)
    assert set(credential_files) == {'Admin', 'Developer', 'Viewer'}
    credentials = {role: read_credentials(path) for role, path in credential_files.items()}
    def credential_identity(path):
        s = Path(path).lstat()
        return (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    credential_ids = {role: credential_identity(path) for role, path in credential_files.items()}
    assert expected_tls['enabled'] and expected_tls['acme']['enabled']
    assert expected_tls['acme']['accept_terms'] and expected_tls['acme']['domains']
    assert set(expected_tls) == {'enabled', 'host', 'port', 'challenge_host', 'challenge_port', 'acme'}
    assert set(expected_tls['acme']) == {key.split('.')[1] for _, key, _ in FIELDS if key.startswith('acme.')}
    original = copy.deepcopy(expected_tls)
    changed = copy.deepcopy(original)
    changed['acme']['retry_seconds'] = next_retry(original['acme']['retry_seconds'])
    output = Path(output_dir).absolute()
    for parent in output.parents:
        assert not parent.is_symlink(), 'Redirected browser output root'
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    assert output.lstat().st_uid == os.getuid() and stat.S_IMODE(output.lstat().st_mode) == 0o700
    safe_write(output / 'once.json', {'schema': 'adhd/acme-browser-once@1', 'serial_sha256': digest(serial_id)})
    root_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    report = {'schema': 'adhd/acme-browser@1', 'passed': False, 'checks': [], 'captures': [],
              'serial_sha256': digest(serial_id), 'expected_tls_sha256': digest(original),
              'application_starts': 0, 'ca_starts': 0, 'browser_launches': 0,
              'contexts_closed': [], 'browser_observations': [], 'failure_type': None, 'cleanup_errors': [],
              'manual_visual_review': 'pending', 'renewal_scope': 'actual UI accepted request, not completed issuance',
              'role_scope': 'actual authenticated session and hidden controls, not a replacement for backend authorization tests',
              'transport_scope': 'caller-owned loopback Admin endpoint; no independent HTTPS certificate-trust claim'}
    secrets = [v for c in credentials.values() for v in c.values()]
    secrets += [original['acme'][k] for k in ('directory_url', 'email', 'ca_cert_file') if original['acme'][k]]
    secrets += original['acme']['domains']
    def redact(value):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, '[redacted]')
        return value
    def check(name, **facts):
        report['checks'].append({'name': name, 'passed': True, **facts})
    async def custody():
        if custody_check:
            await custody_check()
    async def capture(page, label):
        layout = await page.evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})')
        nonfinite = await page.get_by_text(re.compile(r'^(NaN|[+-]?Infinity)$')).count()
        broken = await page.locator('[href="undefined"],[href="null"],[src="undefined"],[src="null"]').count()
        png = output / (label + '.png')
        aria = output / (label + '.txt')
        mask = [page.locator('input[type=password]'), page.locator('[name="directory_url"],[name="email"],[name="ca_cert_file"],[name="domains"]'),
                page.locator('#content p').filter(has_text='Active hostnames:')]
        await page.screenshot(path=str(png), full_page=True, mask=mask)
        png.chmod(0o600)
        text = redact(await page.locator('body').aria_snapshot())
        fd = os.open(aria, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
        report['captures'].append({'label': label, 'png': png.name, 'aria': aria.name,
            'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest(), 'aria_sha256': hashlib.sha256(aria.read_bytes()).hexdigest(),
            'manual_review': 'pending', 'layout': layout, 'nonfinite_text_nodes': nonfinite, 'broken_url_nodes': broken})
        assert layout['document'] <= layout['viewport'], 'Horizontal overflow'
        assert not nonfinite and not broken, 'Nonfinite text or broken URL'
    async def login(page, role):
        await page.goto(base + '/admin')
        await expect(page.get_by_label('Username', exact=True)).to_be_visible()
        await page.get_by_label('Username', exact=True).fill(credentials[role]['username'])
        await page.get_by_label('Password', exact=True).fill(credentials[role]['password'])
        async with page.expect_response(lambda r: r.url == base + '/admin/session' and r.request.method == 'GET') as session:
            await page.get_by_role('button', name='Sign in', exact=True).click()
        current = await (await session.value).json()
        assert current['authenticated'] and current['user']['role'] == role
        await expect(page.locator('#workspace')).to_be_visible()
    async def enter_tls(page):
        async with page.expect_response(lambda r: request_op(r.request, base, 'tls_status')) as response:
            await page.get_by_role('button', name='TLS', exact=True).click()
        response = await response.value
        assert response.status == 200
        status = await response.json()
        assert 'project_id' not in response.request.post_data_json
        await expect(page.get_by_role('heading', name='TLS', exact=True)).to_be_visible()
        await expect(page.get_by_role('button', name='Confirm and save TLS settings', exact=True)).to_be_visible()
        return status
    async def assert_fields(page, target):
        form = page.locator('#content form')
        assert await form.count() == 1
        for label, key, kind in FIELDS:
            item = form.get_by_label(label, exact=True)
            await expect(item).to_be_visible()
            value = field_value(target, key)
            if kind == 'checkbox':
                assert await item.is_checked() == value
            else:
                text = '\n'.join(value) if key == 'acme.domains' else str(value) if value is not None else ''
                await expect(item).to_have_value(text)
        await expect(page.get_by_text('Challenge method: HTTP-01.', exact=False)).to_be_visible()
    async def assert_expiry(page, status):
        assert status['https_state'] == 'ready' and status['certificate'] is not None
        await expect(page.get_by_text('Certificate expires ' + status['certificate']['not_after'], exact=True)).to_be_visible()
        await expect(page.get_by_text('Active hostnames: ' + ', '.join(status['active_domains']), exact=True)).to_be_visible()
    async def save(page, target, label, on_commit=None):
        await custody()
        form = page.locator('#content form')
        for field, key, kind in FIELDS:
            value = field_value(target, key)
            item = form.get_by_label(field, exact=True)
            if kind == 'checkbox':
                await item.set_checked(value)
            else:
                await item.fill('\n'.join(value) if key == 'acme.domains' else str(value) if value is not None else '')
        # Register both actual response identities before clicking. The second
        # response is the UI's own post-save config read, not a test API call.
        async with page.expect_response(lambda r: request_op(r.request, base, 'config_get')) as reloaded:
            async with page.expect_response(lambda r: request_op(r.request, base, 'config_update')) as result:
                await page.get_by_role('button', name='Confirm and save TLS settings', exact=True).click()
            response = await result.value
            body = response.request.post_data_json
            assert set(body) == {'op', 'patch', 'expected_revision', 'confirm', 'message_id'}
            assert body['confirm'] is True and body['patch'] == {'tls': target} and isinstance(body['message_id'], str) and body['message_id']
            assert response.status == 200
            if on_commit:
                on_commit()
            value = await response.json()
            assert value['config_revision'] == body['expected_revision'] + 1
        readback = await reloaded.value
        assert readback.status == 200
        current = await readback.json()
        assert current['config']['tls'] == target and current['config_revision'] == value['config_revision']
        await assert_fields(page, target)
        await expect(page.locator('#error')).to_have_text('')
        await custody()
        check(label, revision_advanced=True, tls_only_patch=True, actual_ui_readback_matches=True,
              message_id_sha256=digest(body['message_id']))
    async def refresh(page):
        async with page.expect_response(lambda r: request_op(r.request, base, 'tls_status')) as result:
            await page.get_by_role('button', name='Refresh certificate status', exact=True).click()
        response = await result.value
        assert response.status == 200
        status = await response.json()
        await expect(page.get_by_role('button', name='Confirm and save TLS settings', exact=True)).to_be_visible()
        await assert_expiry(page, status)
        return status
    primary = None
    try:
        await custody()
        for viewport, size in [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]:
            for role in ('Admin', 'Developer', 'Viewer'):
                async with owned_context(browser, size, report, viewport + '-' + role.lower()) as context:
                    page = await context.new_page()
                    page.set_default_timeout(15000)
                    observer = BrowserObservation(page, base)
                    unexpected = []
                    dialogs = []
                    restore_needed = False
                    restore_attempted = False
                    async def network(route):
                        request = route.request
                        parsed = urlsplit(request.url)
                        allowed = request.url.startswith(base + '/') and not parsed.query and not parsed.fragment
                        if request.url == base + '/admin/api':
                            body = request.post_data_json
                            allowed = request.method == 'POST' and isinstance(body, dict) and body.get('op') in API_OPS
                        else:
                            allowed = allowed and (request.method, parsed.path) in {
                                ('GET', '/admin'), ('GET', '/admin/assets/app.css'), ('GET', '/admin/assets/app.js'),
                                ('GET', '/admin/session'), ('POST', '/admin/login'), ('POST', '/admin/logout')}
                        if allowed:
                            await route.continue_()
                        else:
                            unexpected.append({'method': request.method, 'url_sha256': digest(request.url)})
                            await route.abort()
                    async def dialog(value):
                        dialogs.append(value.message)
                        if value.type == 'confirm' and value.message in (SAVE_DIALOG, RENEW_DIALOG):
                            await value.accept()
                        else:
                            await value.dismiss()
                    await page.route('**/*', network)
                    page.on('dialog', dialog)
                    try:
                        await login(page, role)
                        if role == 'Admin':
                            status = await enter_tls(page)
                            await assert_fields(page, original)
                            await assert_expiry(page, status)
                            check(viewport + '-admin-controls-and-expiry', form_fields=len(FIELDS))
                            await capture(page, viewport + '-tls-ready')
                            if viewport == 'desktop':
                                def mark_changed():
                                    nonlocal restore_needed
                                    restore_needed = True
                                    report['ui_policy_restore_required'] = True
                                await save(page, changed, 'ui-save-normalized-tls-fields', on_commit=mark_changed)
                                await capture(page, 'desktop-tls-saved')
                                restore_attempted = True
                                await save(page, original, 'ui-restore-original-retry-policy')
                                restore_needed = False
                                report['ui_policy_restore_required'] = False
                                await capture(page, 'desktop-tls-restored')
                                await custody()
                                async with page.expect_response(lambda r: request_op(r.request, base, 'tls_renew')) as renewed:
                                    await page.get_by_role('button', name='Request certificate renewal', exact=True).click()
                                response = await renewed.value
                                command = response.request.post_data_json
                                value = await response.json()
                                assert response.status == 200 and set(command) == {'op', 'expected_revision', 'confirm', 'message_id'}
                                assert command['confirm'] is True and value == {'accepted': True, 'config_revision': command['expected_revision']}
                                await expect(page.get_by_role('button', name='Confirm and save TLS settings', exact=True)).to_be_visible()
                                await expect(page.locator('#error')).to_have_text('')
                                check('ui-manual-renewal-actual-accepted-request', message_id_sha256=digest(command['message_id']))
                                await capture(page, 'desktop-renewal-accepted')
                                assert dialogs == [SAVE_DIALOG, SAVE_DIALOG, RENEW_DIALOG]
                            await refresh(page)
                            await assert_fields(page, original)
                            check(viewport + '-refresh-observes-real-status-and-expiry')
                        else:
                            await expect(page.get_by_role('button', name='TLS', exact=True)).to_have_count(0)
                            await expect(page.get_by_role('button', name='Confirm and save TLS settings', exact=True)).to_have_count(0)
                            await expect(page.get_by_role('button', name='Request certificate renewal', exact=True)).to_have_count(0)
                            check(viewport + '-' + role.lower() + '-tls-controls-hidden', actual_session_role_verified=True)
                            await capture(page, viewport + '-' + role.lower() + '-navigation')
                        assert not unexpected, 'Unexpected browser fetch'
                        assert all(message in (SAVE_DIALOG, RENEW_DIALOG) for message in dialogs), 'Unexpected browser dialog'
                        observer.check()
                        await custody()
                    finally:
                        if sys.exc_info()[0] is not None:
                            try:
                                await capture(page, viewport + '-' + role.lower() + '-failure')
                            except BaseException as exc:
                                report['cleanup_errors'].append({'phase':'failure-capture','type':type(exc).__name__})
                        if restore_needed and not restore_attempted:
                            restore_attempted = True
                            try:
                                await save(page, original, 'failure-cleanup-restored-original-policy')
                                report['cleanup_restore_succeeded'] = True
                                report['ui_policy_restore_required'] = False
                            except BaseException as exc:
                                report['cleanup_errors'].append({'phase': 'restore-ui-policy', 'type': type(exc).__name__})
                        observed = {'context': viewport + '-' + role.lower(), 'passed': False,
                            'page_errors': len(observer.errors), 'console_errors': len(observer.console),
                            'http_errors': len(observer.responses), 'failed_requests': len(observer.failed),
                            'unexpected_fetches': len(unexpected)}
                        report['browser_observations'].append(observed)
                        try:
                            observer.check()
                            assert not unexpected
                            observed['passed'] = True
                        except BaseException as exc:
                            report['cleanup_errors'].append({'phase': 'browser-observation', 'type': type(exc).__name__})
                if report['cleanup_errors']:
                    raise AssertionError('Owned browser context or observation cleanup failed')
        assert not report['cleanup_errors'] and len(report['contexts_closed']) == 6
        assert len(report['browser_observations']) == 6 and all(r['passed'] for r in report['browser_observations'])
        report['passed'] = True
    except BaseException as exc:
        primary = exc
        report['failure_type'] = type(exc).__name__
    finally:
        report['script_sha256'] = hashlib.sha256(source_bytes).hexdigest()
        try:
            report['inputs_unchanged'] = Path(__file__).read_bytes() == source_bytes and all(
                credential_identity(path) == credential_ids[role] and read_credentials(path) == credentials[role]
                for role, path in credential_files.items())
        except BaseException:
            report['inputs_unchanged'] = False
        if not report['inputs_unchanged']:
            report['passed'] = False
            if primary is None:
                primary = AssertionError('Browser inputs changed')
                report['failure_type'] = type(primary).__name__
        try:
            safe_write(output / 'report.json', report)
        except BaseException:
            if primary is None:
                raise AssertionError('Could not retain browser evidence') from None
    if primary is not None:
        # Never stringify a browser exception carrying page/request/private values.
        raise AssertionError('ACME browser phase failed; inspect private report') from None
    return report


def self_test():
    """Pure guards only. No Playwright import/browser/service/process launch."""
    import tempfile
    import unittest
    class Guards(unittest.TestCase):
        def test_partial_context_failure_cleanup(self):
            class Context:
                closed = False
                async def close(self): self.closed = True
            class Browser:
                context = Context()
                async def new_context(self, **kwargs):
                    assert kwargs['ignore_https_errors'] is False
                    return self.context
            async def observed():
                browser=Browser();report={'contexts_closed':[],'cleanup_errors':[]}
                try:
                    async with owned_context(browser, {'width':390,'height':844}, report, 'partial'):
                        raise ValueError('fixture startup failure')
                except ValueError:
                    pass
                self.assertTrue(browser.context.closed)
                self.assertEqual(report['contexts_closed'],['partial'])
                self.assertEqual(report['cleanup_errors'],[])
            asyncio.run(observed())
        def test_context_cleanup_preserves_primary(self):
            class Browser:
                async def new_context(self, **kwargs): return self
                async def close(self): raise OSError('fixture cleanup failure')
            async def observed():
                report={'contexts_closed':[],'cleanup_errors':[]}
                with self.assertRaises(ValueError):
                    async with owned_context(Browser(), {}, report, 'partial'):
                        raise ValueError('original fixture failure')
                self.assertEqual(report['cleanup_errors'],[{'phase':'close-context','type':'OSError'}])
                self.assertEqual(report['contexts_closed'],[])
            asyncio.run(observed())
        def test_private_credentials(self):
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                path = root / 'credentials.json'
                safe_write(path, {'username': 'admin', 'password': 'owned-test-secret'})
                self.assertEqual(read_credentials(path)['username'], 'admin')
                path.chmod(0o644)
                with self.assertRaises(AssertionError): read_credentials(path)
                path.chmod(0o600)
                alias = root / 'alias'
                alias.symlink_to(path)
                with self.assertRaises(AssertionError): read_credentials(alias)
                alias.unlink();os.link(path, alias)
                with self.assertRaises(AssertionError): read_credentials(path)
        def test_duplicate_and_open_credentials(self):
            with self.assertRaises(AssertionError): json.loads('{"username":"a","username":"b"}', object_pairs_hook=_closed)
        def test_owned_loopback_only(self):
            self.assertEqual(private_base('http://127.0.0.2:8766/'), 'http://127.0.0.2:8766')
            for value in ('http://example.org:80', 'http://admin:secret@127.0.0.1:80', 'http://127.0.0.1:80/x', 'http://127.0.0.1:80/?secret=x'):
                with self.assertRaises((AssertionError, ValueError)): private_base(value)
        def test_retry_bounds_and_field_closure(self):
            self.assertEqual(next_retry(30),31);self.assertEqual(next_retry(86400),86399)
            with self.assertRaises(AssertionError): next_retry(True)
            self.assertEqual(len(FIELDS),14)
            self.assertEqual(len({key for _,key,_ in FIELDS}),14)
        def test_exclusive_safe_output(self):
            with tempfile.TemporaryDirectory() as raw:
                path=Path(raw)/'report.json';safe_write(path,{'passed':False})
                with self.assertRaises(FileExistsError):safe_write(path,{'passed':True})
                self.assertEqual(json.loads(path.read_text()),{'passed':False})
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Guards))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args=parser.parse_args()
    assert args.self_test, 'Execution is caller-owned: import run_browser_phase only during an authorized exclusive phase'
    raise SystemExit(self_test())
