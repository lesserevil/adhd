"""Inert framing/fault fixtures, no TLS service/CA/socket or subprocess."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from acme_issuer_fault_relay import IssuerFaultRelay,Wire,headers,fault_bytes,MAX_BODY,header_checkpoint,selected_response_fields

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

    def test_response_link_fields_preserve_original_order_and_bytes(self):
        raw=(b'HTTP/1.1 200 OK\r\nLink: </issuer>;rel="up"\r\n'
          b'Content-Type: application/pem-certificate-chain\r\nLink: </alternate>;rel="alternate"\r\n'
          b'Replay-Nonce: public-nonce\r\nContent-Length: 0\r\n\r\n')
        status,h=headers(raw,response=True)
        self.assertEqual(status,200)
        self.assertEqual(selected_response_fields(h),
          b'link: </issuer>;rel="up"\r\ncontent-type: application/pem-certificate-chain\r\n'
          b'link: </alternate>;rel="alternate"\r\nreplay-nonce: public-nonce\r\n')
        self.assertEqual(header_checkpoint(raw,response=True)['name_counts']['link'],2)
        for name in [b'Replay-Nonce',b'Location',b'Content-Length',b'Transfer-Encoding',b'Unknown']:
            with self.assertRaises(AssertionError):headers(b'HTTP/1.1 200 OK\r\n'+name+b': a\r\n'+name+b': b\r\n\r\n',response=True)
        with self.assertRaises(AssertionError):headers(b'GET / HTTP/1.1\r\nLink: a\r\nLink: b\r\n\r\n')

    def test_failure_checkpoint_is_value_free_bounded_and_survives_parse_failure(self):
        raw=b'HTTP/1.1 200 OK\r\nReplay-Nonce: PRIVATEVALUE\r\nReplay-Nonce: SECRETVALUE\r\nsecret-header-name: PRIVATEVALUE\r\n\r\n'
        checkpoint={'stage':'response-headers','response_headers':header_checkpoint(raw,response=True)}
        with self.assertRaises(AssertionError):headers(raw,response=True)
        relay=IssuerFaultRelay.__new__(IssuerFaultRelay);relay.errors=[];relay.error_total=0;relay.failure_checkpoints=[]
        for _ in range(1000):relay._failure_locked(AssertionError('PRIVATEVALUE'),checkpoint)
        self.assertEqual(relay.error_total,1000);self.assertEqual(len(relay.failure_checkpoints),128)
        self.assertEqual(relay.failure_checkpoints[0]['response_headers']['name_counts'],{'replay-nonce':2,'other':1})
        import json
        retained=json.dumps(relay.failure_checkpoints)
        for secret in ['PRIVATEVALUE','SECRETVALUE','secret-header-name']:self.assertNotIn(secret,retained)
        oversized=header_checkpoint(b'PRIVATEVALUE'*2000,response=True)
        self.assertEqual(oversized,{'header_bytes':24000,'name_counts':{}})

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

class FakeThread:
    def __init__(self,alive=True,exits=True):self.alive=alive;self.exits=exits;self.joins=[];self.cancelled=False
    def is_alive(self):return self.alive
    def cancel(self):self.cancelled=True
    def join(self,timeout=None):
        self.joins.append(timeout)
        if self.exits:self.alive=False

class RelayLifecycleChecks(unittest.TestCase):
    def fixture(self,d):
        p=Path(d)/'fixture';p.write_bytes(b'owned fixture bytes');p.chmod(0o600)
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        return IssuerFaultRelay(cert_file=p,key_file=p,root_file=p,cert_sha256=digest,key_sha256=digest,root_sha256=digest)

    def test_rejected_request_flood_has_bounded_retention_and_exact_total(self):
        import time
        with tempfile.TemporaryDirectory()as d:
            relay=self.fixture(d);relay.started=time.monotonic();relay.requests=relay.max_requests
            request=Mock()
            for _ in range(1000):self.assertFalse(relay._claim_request(request))
            self.assertEqual(len(relay.errors),128);self.assertEqual(relay.error_total,1000)
            self.assertEqual(relay.requests,256);self.assertEqual(relay.active,0)
            self.assertEqual(len(relay.workers),0);self.assertEqual(request.close.call_count,1000)

    def test_closed_requires_joined_worker_and_both_timer_kinds(self):
        with tempfile.TemporaryDirectory()as d:
            relay=self.fixture(d);relay.closing.set()
            worker,timer,lifetime=FakeThread(),FakeThread(),FakeThread()
            relay.workers=[worker];relay.exchange_timers=[timer];relay.lifetime_timer=lifetime
            self.assertFalse(relay.snapshot()['closed'])
            relay.close()
            self.assertTrue(relay.snapshot()['closed'])
            for thread in [worker,timer,lifetime]:self.assertEqual(len(thread.joins),1)
            self.assertTrue(timer.cancelled);self.assertTrue(lifetime.cancelled)

    def test_hung_worker_stays_unclosed_after_failed_join(self):
        with tempfile.TemporaryDirectory()as d:
            relay=self.fixture(d);relay.workers=[FakeThread(exits=False)]
            with self.assertRaisesRegex(AssertionError,'thread did not exit'):relay.close()
            self.assertFalse(relay.snapshot()['closed'])

    def test_lifetime_callback_does_not_join_itself_or_prematurely_claim_closed(self):
        with tempfile.TemporaryDirectory()as d:
            relay=self.fixture(d);lifetime=FakeThread();relay.lifetime_timer=lifetime
            with patch('acme_issuer_fault_relay.threading.current_thread',return_value=lifetime):relay.close()
            self.assertEqual(lifetime.joins,[])
            self.assertFalse(relay.snapshot()['closed'])
            lifetime.alive=False
            self.assertTrue(relay.snapshot()['closed'])

    def test_worker_start_failure_releases_claim_and_preserves_original(self):
        with tempfile.TemporaryDirectory()as d:
            relay=self.fixture(d);relay.active=1;request=Mock();relay.sockets.add(request)
            worker=Mock();worker.is_alive.return_value=False
            failure=OSError('original failure');worker.start.side_effect=failure
            with patch('acme_issuer_fault_relay.threading.Thread',return_value=worker):
                with self.assertRaises(OSError)as caught:relay._spawn_worker(Mock(),request,('127.0.0.1',1))
            self.assertIs(caught.exception,failure);self.assertEqual(relay.active,0)
            self.assertFalse(relay.sockets);request.close.assert_called_once()
            worker.join.assert_not_called()
