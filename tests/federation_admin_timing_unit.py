"""No service starts: sanitized observation of the unchanged Admin request."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import federation_multi as target


class AdminTiming(unittest.TestCase):
    def setUp(self):
        self.hub = SimpleNamespace(base='http://private.invalid', config={'admin_token': 'secret-token'})
        self.body = {'op': 'config_update', 'message_id': 'secret-mid', 'patch': {
            'projects': [{'user': 'private-user', 'email': 'private@example.invalid'}],
            'secret-unknown-key': 'secret-body'}}
        self.diag = {'requests': [], 'omitted_requests': 0}

    def test_timeout_rethrows_exact_primary_and_persists_sanitized_report(self):
        error = TimeoutError('secret-response')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'report.json'
            with patch.object(target, 'request', side_effect=error) as request, patch.object(target.time, 'monotonic', side_effect=[10.0, 15.0]):
                with self.assertRaises(TimeoutError) as observed:
                    try:
                        target.timed_admin_request(self.hub, self.body, self.diag, 1)
                    finally:
                        path.write_text(json.dumps({'admin_request_timings': self.diag}))
                self.assertIs(observed.exception, error)
                request.assert_called_once_with(self.hub.base, '/admin/api', self.body, 'secret-token')
                self.assertIs(request.call_args.args[2], self.body)
            raw = path.read_text()
            for secret in ['secret-token', 'secret-mid', 'secret-body', 'secret-response',
                           'private-user', 'private@example.invalid', 'private.invalid', 'secret-unknown-key']:
                self.assertNotIn(secret, raw)
            row = json.loads(raw)['admin_request_timings']['requests'][0]
            self.assertEqual(row, {'monotonic_start': 10.0, 'duration_seconds': 5.0,
                'server_ordinal': 1, 'op': 'config_update', 'message_id_sha256': hashlib.sha256(b'secret-mid').hexdigest(),
                'patch_keys': ['<other>', 'projects'], 'exception_type': 'TimeoutError'})

    def test_success_preserves_response(self):
        response = (409, {'private': 'untouched'})
        with patch.object(target, 'request', return_value=response):
            self.assertEqual(target.timed_admin_request(self.hub, self.body, self.diag, 2), response)
        self.assertEqual(self.diag['requests'][0]['status'], 409)
        self.assertNotIn('private', json.dumps(self.diag))

    def test_bounded_rows(self):
        with patch.object(target, 'request', return_value=(200, {})):
            for _ in range(258):target.timed_admin_request(self.hub, {'op': 'config_get'}, self.diag, 0)
        self.assertEqual(len(self.diag['requests']), 256)
        self.assertEqual(self.diag['omitted_requests'], 2)

    def test_shared_request_still_five_seconds_and_report_finally(self):
        import federation_acceptance
        tree = ast.parse(Path(federation_acceptance.__file__).read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'request')
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'urlopen']
        self.assertEqual([ast.literal_eval(k.value) for k in calls[0].keywords if k.arg == 'timeout'], [5])
        tree = ast.parse(Path(target.__file__).read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        outer = next(n for n in main.body if isinstance(n, ast.Try))
        self.assertIsInstance(outer.finalbody[0], ast.Try)
        self.assertTrue(outer.finalbody[0].finalbody)

if __name__ == '__main__':unittest.main()
