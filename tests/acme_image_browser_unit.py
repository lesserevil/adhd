"""Pure browser input custody and independent partial-start cleanup checks."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from acme_image_browser import browser_binding, verify_browser, inspect, run
from acme_browser_flow import digest as flow_digest


class BrowserInputs(unittest.TestCase):
    def test_bootstrap_refuses_fifo_and_redirected_plan_before_read(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fifo = root / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaises(AssertionError): flow_digest(fifo)
            plain = root / 'plan.json'
            plain.write_text('{}')
            alias = root / 'alias'
            alias.symlink_to(plain)
            with self.assertRaises(AssertionError): flow_digest(alias)

    def test_exact_tree_rejects_replaced_added_and_redirected_inputs(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            executable = root / 'browser'
            executable.write_bytes(b'reviewed-tool')
            executable.chmod(0o500)
            baseline = browser_binding(root, executable)
            verify_browser(baseline)
            executable.chmod(0o700)
            executable.write_bytes(b'changed-tool')
            executable.chmod(0o500)
            with self.assertRaises(AssertionError): verify_browser(baseline)
            executable.chmod(0o700)
            executable.write_bytes(b'reviewed-tool')
            executable.chmod(0o500)
            (root / 'new-input').write_bytes(b'added')
            with self.assertRaises(AssertionError): verify_browser(baseline)
            (root / 'new-input').unlink()
            (root / 'alias').symlink_to(executable)
            with self.assertRaises(AssertionError): verify_browser(baseline)

    def test_writable_tool_and_tree_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            executable = root / 'browser'
            executable.write_bytes(b'tool')
            executable.chmod(0o777)
            with self.assertRaises(AssertionError): browser_binding(root, executable)
            executable.chmod(0o500)
            root.chmod(0o777)
            with self.assertRaises(AssertionError): browser_binding(root, executable)
            root.chmod(0o700)

    def test_browser_close_failure_does_not_skip_driver_stop_or_hide_primary(self):
        events = []
        class Browser:
            async def close(self):
                events.append('browser-close')
                raise OSError('owned-close-fault')
        class Driver:
            @property
            def chromium(self): return self
            async def launch(self, **kwargs): return Browser()
            async def stop(self): events.append('driver-stop')
        class Manager:
            async def start(self): return Driver()
        module = ModuleType('playwright.async_api')
        module.async_playwright = Manager
        session = SimpleNamespace(password='private-fixture',
            admin=SimpleNamespace(mutate=lambda *args, **kwargs: None,
                api=lambda command:{'config':{'tls':{'acme':{'ca_cert_file':'/owned/hub/directory-root.pem'}}}}),
            runtime=SimpleNamespace(base='http://127.0.0.1:12345'), hub=Path('/owned/hub'),
            tls={'acme':{'ca_cert_file':'directory-root.pem'}})
        async def fail(*args, **kwargs): raise ValueError('original-browser-fault')
        with tempfile.TemporaryDirectory() as raw:
            report = {}
            with patch.dict(sys.modules, {'playwright.async_api': module}), \
                    patch('acme_browser.run_browser_phase', fail):
                with self.assertRaisesRegex(ValueError, 'original-browser-fault'):
                    asyncio.run(inspect(session, {'browser': {'executable': '/owned/browser'},
                        'target': {'image': 'sha256:' + 'a' * 64}}, Path(raw), report))
            self.assertEqual(events, ['browser-close', 'driver-stop'])
            self.assertTrue(report['playwright_driver_closed'])
            self.assertEqual(report['browser_cleanup_errors'], [{'scope': 'browser', 'type': 'OSError'}])

    def test_evidence_write_failure_preserves_partial_start_error_and_cleanup(self):
        events = []
        class Provision:
            def __init__(self, plan, target, work): self.work = work
            def start(self):
                self.work.mkdir()
                raise ValueError('original-startup-fault')
            def close(self): events.append('provision-close')
            def evidence(self): return {}
        class Observer:
            def __init__(self, *args): pass
            def start(self): return self
            def close(self): events.append('observer-close')
            def evidence(self): return {}
        module = ModuleType('acme_image_provision')
        module.OwnedProvision = Provision
        with tempfile.TemporaryDirectory() as raw:
            with patch.dict(sys.modules, {'acme_image_provision': module}), \
                    patch('acme_image_browser.verify_browser'), \
                    patch('acme_process_observer.Descendants', Observer), \
                    patch('acme_browser.safe_write', side_effect=OSError('private-write-fault')):
                with self.assertRaisesRegex(ValueError, 'original-startup-fault') as caught:
                    run({'browser': {}}, SimpleNamespace(evidence=lambda: {}), Path(raw) / 'work')
            self.assertEqual(events, ['provision-close', 'observer-close'])
            self.assertEqual(caught.exception.__notes__, ['Browser phase evidence: OSError'])


if __name__ == '__main__': unittest.main()
