"""Exercise actual stdlib bind options using only fake sockets; no listeners."""
import errno
import hashlib
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock,patch
from acme_challenge_relay import ChallengeRelay
from acme_issuer_fault_relay import IssuerFaultRelay


class BoundOptionChecks(unittest.TestCase):
    def relay(self,kind,root):
        if kind=='challenge':return ChallengeRelay(upstreams={'one.acme.test':('127.0.0.2',8080)})
        path=root/'fixture';path.write_bytes(b'owned static fixture');path.chmod(0o600)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        return IssuerFaultRelay(cert_file=path,key_file=path,root_file=path,
          cert_sha256=digest,key_sha256=digest,root_sha256=digest)

    def exercise(self,kind,occupied):
        with tempfile.TemporaryDirectory()as directory:
            relay=self.relay(kind,Path(directory));sock=Mock()
            # Leave actual TCPServer.server_bind intact: this checks the actual
            # subclass flags reach the real stdlib setsockopt/bind implementation.
            stop=OSError(errno.EADDRINUSE,'owned listener occupied')if occupied else RuntimeError('pure stop before activation/thread')
            if occupied:sock.bind.side_effect=stop
            def fake_constructor(server,address,handler,bind_and_activate=True):
                server.socket=sock;server.server_address=address
                server.server_bind()
                raise stop
            with patch('socketserver.TCPServer.__init__',fake_constructor),\
                 patch('acme_issuer_fault_relay.ssl.SSLContext',return_value=Mock()),\
                 patch('acme_issuer_fault_relay.ssl.create_default_context',return_value=Mock()),\
                 patch('threading.Thread.start')as threads,patch('threading.Timer.start')as timers:
                with self.assertRaises(type(stop))as caught:relay.start()
            self.assertIs(caught.exception,stop)
            sock.setsockopt.assert_called_once_with(socket.SOL_SOCKET,socket.SO_REUSEADDR,True)
            sock.bind.assert_called_once_with(('127.0.0.1',8080 if kind=='challenge' else 19103))
            threads.assert_not_called();timers.assert_not_called()
            self.assertIsNone(relay.server)

    def test_issuer_reuses_timewait_without_reuseport(self):self.exercise('issuer',False)
    def test_challenge_reuses_timewait_without_reuseport(self):self.exercise('challenge',False)
    def test_issuer_live_listener_collision_remains_exact_failure(self):self.exercise('issuer',True)
    def test_challenge_live_listener_collision_remains_exact_failure(self):self.exercise('challenge',True)
