"""Inert framing/fault fixtures, no TLS service/CA/socket or subprocess."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from acme_issuer_fault_relay import IssuerFaultRelay,Wire,headers,fault_bytes,MAX_BODY

class IssuerFaultChecks(unittest.TestCase):
    def test_429_and_503_are_explicit_retry_only_failures(self):
        for status in [429,503]:
            raw=fault_bytes(status,120);head,body=raw.split(b'\r\n\r\n',1)
            actual,h=headers(head+b'\r\n\r\n',response=True)
            self.assertEqual(actual,status);self.assertEqual(h[b'retry-after'],b'120')
            self.assertEqual(int(h[b'content-length']),len(body))
            self.assertNotIn(b'replay-nonce',h);self.assertNotIn(b'certificate',body)
        for status,delay in [(200,120),(503,0),(429,True),(503,601)]:
            with self.assertRaises(AssertionError):fault_bytes(status,delay)

    def test_duplicate_ambiguous_oversize_headers_denied(self):
        for raw in [b'GET /dir HTTP/1.1\r\nHost: localhost:19103\r\nHost: foreign\r\n\r\n',
                    b'POST /order HTTP/1.1\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n',
                    b'GET https://foreign/dir HTTP/1.1\r\nHost: localhost:19103\r\n\r\n',
                    b'GET /dir HTTP/1.1\r\nX: '+b'a'*17000+b'\r\n\r\n']:
            with self.assertRaises(AssertionError):headers(raw)

    def test_bounded_chunk_and_body_parser(self):
        sock=Mock();wire=Wire(sock,10**12)
        wire.buffer=bytearray(b'3\r\nabc\r\n0\r\n\r\n')
        self.assertEqual(wire.body({b'transfer-encoding':b'chunked'}),b'abc');sock.recv.assert_not_called()
        with self.assertRaises(AssertionError):wire.exact(MAX_BODY+1)
        wire=Wire(sock,0)
        with self.assertRaises(TimeoutError):wire.recv(1)
        sock.recv.assert_not_called()

    def test_constructor_never_starts_or_contacts_services(self):
        with tempfile.TemporaryDirectory()as d,patch('acme_issuer_fault_relay.socket.create_connection')as connect,patch('acme_issuer_fault_relay.socketserver.ThreadingTCPServer')as server:
            p=Path(d)/'pinned';p.write_bytes(b'owned fixture placeholder');p.chmod(0o600)
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            relay=IssuerFaultRelay(cert_file=p,key_file=p,root_file=p,cert_sha256=digest,key_sha256=digest,root_sha256=digest)
            relay.set_fault(503,120);self.assertEqual(relay.mode,503)
            relay.set_fault();self.assertEqual(relay.mode,'pass')
            relay.active=1
            with self.assertRaises(AssertionError):relay.set_fault(429)
            self.assertIsNone(relay.server);connect.assert_not_called();server.assert_not_called()
