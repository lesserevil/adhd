"""Failure injection only: no process, listener, CA or outgoing request starts."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from acme_runtime import NativeDiagnostic, PublicClient


class RuntimeChecks(unittest.TestCase):
    def test_constructor_is_inert_and_failed_spawn_closes_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'hub.json').write_text(json.dumps({'port':19001}))
            runtime = NativeDiagnostic(root, root, root, '/usr/bin/false', '0'*64, erlang='/owned/erlang/bin/erl')
            self.assertIsNone(runtime.process)
            self.assertEqual(runtime.logs, [])
            with patch.object(runtime, 'verify', return_value={}), patch('acme_runtime.subprocess.Popen', side_effect=OSError('injected')) as spawn:
                with self.assertRaisesRegex(OSError, 'injected'):
                    runtime.start()
            self.assertEqual(spawn.call_count, 1)
            self.assertIn('/owned/erlang/bin', spawn.call_args.kwargs['env']['PATH'].split(':'))
            self.assertEqual(runtime.logs, [])
            self.assertEqual(runtime.identities, [])
            for name in ('stdout.log', 'stderr.log'):
                self.assertEqual((root/name).stat().st_mode & 0o777, 0o600)

    def test_symlink_log_rejected_without_spawn_or_foreign_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'hub.json').write_text(json.dumps({'port':19001}))
            foreign = root/'foreign'
            foreign.write_bytes(b'unchanged')
            (root/'stdout.log').symlink_to(foreign)
            runtime = NativeDiagnostic(root, root, root, '/usr/bin/false', '0'*64, erlang='/owned/erlang/bin/erl')
            with patch.object(runtime, 'verify', return_value={}), patch('acme_runtime.subprocess.Popen') as spawn:
                with self.assertRaises(OSError):
                    runtime.start()
            spawn.assert_not_called()
            self.assertEqual(foreign.read_bytes(), b'unchanged')

    def test_mutation_observes_effective_public_revision_once(self):
        client = PublicClient('http://127.0.0.1:19001')
        calls = []
        def api(command, expected=200):
            calls.append(command)
            return {'config_revision':19} if command['op']=='config_get' else {'accepted':True}
        client.api = api
        _, command = client.mutate('tls_renew', message_id='fixed')
        self.assertEqual(len(calls), 2)
        self.assertEqual(command, {'op':'tls_renew','expected_revision':19,'confirm':True,'message_id':'fixed'})

    def test_tls_transport_preserves_sni_and_fixed_connect_address(self):
        context = Mock()
        tls_socket = Mock()
        tls_socket.getpeercert.return_value = b'public-der-placeholder'
        tls_socket.version.return_value = 'TLSv1.3'
        context.wrap_socket.return_value = tls_socket
        with patch('acme_runtime.ssl.create_default_context', return_value=context) as create:
            client = PublicClient('https://one.acme.test:18443', trust='/owned/issuer.pem')
        create.assert_called_once_with(cafile='/owned/issuer.pem')
        handler = next(h for h in client.opener.handlers if type(h).__name__ == 'Handler')
        with patch.object(handler, 'do_open') as dispatch:
            handler.https_open(SimpleNamespace())
        connection_class = dispatch.call_args.args[0]
        connection = connection_class('one.acme.test:18443', timeout=2)
        plain = Mock()
        with patch('acme_runtime.socket.create_connection', return_value=plain) as connect:
            connection.connect()
        connect.assert_called_once_with(('127.0.0.1',18443), 2)
        context.wrap_socket.assert_called_once_with(plain, server_hostname='one.acme.test')
        self.assertEqual(client.handshakes[0]['der'], b'public-der-placeholder')
        with patch('acme_runtime.socket.create_connection') as connect:
            with self.assertRaises(AssertionError):
                connection_class('foreign.acme.test:18443', timeout=2).connect()
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
