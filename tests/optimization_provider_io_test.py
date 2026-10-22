#!/usr/bin/env python3
"""Transport faults against owned loopback upstreams; never the real provider."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import socketserver
import tempfile
import threading
import time
import unittest

import httpx
from optimization_provider_io import exchange,MAX_BODY
from optimization_neutral_witness import ProviderBudget


class Upstream:
    def __init__(self,script):
        self.script=script;self.requests=[];self.stop=threading.Event();self.active=0;self.lock=threading.Condition();outer=self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                with outer.lock:outer.active+=1
                try:
                    self.request.settimeout(2);raw=bytearray()
                    while b'\r\n\r\n' not in raw:
                        assert len(raw)<65536;part=self.request.recv(4096)
                        if not part:return
                        raw.extend(part)
                    headers,body=bytes(raw).split(b'\r\n\r\n',1)
                    length=int(next(x.split(b':',1)[1] for x in headers.split(b'\r\n')[1:] if x.lower().startswith(b'content-length:')))
                    assert length<=65536
                    while len(body)<length:body+=self.request.recv(min(4096,length-len(body)))
                    outer.requests.append(body);outer.script(self.request,outer.stop)
                except (BrokenPipeError,ConnectionResetError,OSError):pass
                finally:
                    with outer.lock:outer.active-=1;outer.lock.notify_all()
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address=True;daemon_threads=True
            def handle_error(self,*_):pass
        self.server=Server(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.02),daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])+'/v1/systemone'
    def close(self):
        self.stop.set();self.server.shutdown();self.server.server_close();self.thread.join(1)
        with self.lock:assert self.lock.wait_for(lambda:self.active==0,timeout=2)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def response(conn,body=b'{}',status=200):
    conn.sendall(f'HTTP/1.1 {status} Owned\r\nContent-Length: {len(body)}\r\n\r\n'.encode()+body)


class IOTests(unittest.TestCase):
    def run_exchange(self,script,**kwargs):
        with Upstream(script) as upstream:
            result=exchange(upstream.url,b'{"exact":1.0,"x":"\\u03bb"}',time.monotonic()+1,**kwargs)
            self.assertEqual(upstream.requests,[b'{"exact":1.0,"x":"\\u03bb"}']);return result
    def test_exact_request_and_maximum_body(self):
        status,body=self.run_exchange(lambda conn,_:response(conn,b'x'*MAX_BODY));self.assertEqual(status,200);self.assertEqual(len(body),MAX_BODY)
    def test_error_response_does_not_retry(self):
        self.assertEqual(self.run_exchange(lambda conn,_:response(conn,b'{"error":true}',503)),(503,b'{"error":true}'))
    def test_header_bound(self):
        with self.assertRaises(ValueError):self.run_exchange(lambda conn,_:conn.sendall(b'HTTP/1.1 200 Owned\r\nX: '+b'x'*17000+b'\r\n\r\n'))
    def test_declared_body_bound_before_read(self):
        with self.assertRaises(ValueError):self.run_exchange(lambda conn,_:conn.sendall(b'HTTP/1.1 200 Owned\r\nContent-Length: 262145\r\n\r\n'))
    def test_eof_body_bound(self):
        with self.assertRaises(ValueError):self.run_exchange(lambda conn,_:conn.sendall(b'HTTP/1.0 200 Owned\r\n\r\n'+b'x'*(MAX_BODY+1)))
    def test_chunked_body_and_trailer(self):
        self.assertEqual(self.run_exchange(lambda conn,_:conn.sendall(b'HTTP/1.1 200 Owned\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\nX-Test: yes\r\n\r\n')),(200,b'{}'))
    def test_chunk_bound_before_read(self):
        with self.assertRaises(ValueError):self.run_exchange(lambda conn,_:conn.sendall(b'HTTP/1.1 200 Owned\r\nTransfer-Encoding: chunked\r\n\r\n40001\r\n'))
    def test_header_dribble_absolute_deadline(self):
        def dribble(conn,stop):
            for value in b'HTTP/1.1 200 Owned\r\nContent-Length: 2\r\n\r\n{}':
                if stop.wait(.02):return
                conn.sendall(bytes([value]))
        started=time.monotonic()
        with Upstream(dribble) as upstream:
            with self.assertRaises(TimeoutError):exchange(upstream.url,b'{}',time.monotonic()+.15)
        self.assertLess(time.monotonic()-started,.8)
    def test_body_dribble_absolute_deadline(self):
        def dribble(conn,stop):
            conn.sendall(b'HTTP/1.1 200 Owned\r\nContent-Length: 1000\r\n\r\n')
            while not stop.wait(.02):conn.sendall(b'x')
        started=time.monotonic()
        with Upstream(dribble) as upstream:
            with self.assertRaises(TimeoutError):exchange(upstream.url,b'{}',time.monotonic()+.15)
        self.assertLess(time.monotonic()-started,.8)
    def test_close_cancels_inflight_io_without_waiting_for_exchange_timeout(self):
        def dribble(conn,stop):
            conn.sendall(b'HTTP/1.1 200 Owned\r\nContent-Length: 1000\r\n\r\n')
            while not stop.wait(.02):conn.sendall(b'x')
        with tempfile.TemporaryDirectory() as directory,Upstream(dribble) as upstream:
            manifest={'provider':{'url':upstream.url,'model':'owned-transport-fixture'},'provider_budget':{'maximum_upstream_http_posts':106,'maximum_wall_clock_seconds':900},'preregistration':{'cases':[{'question':'owned question'}]}}
            budget=ProviderBudget(manifest,Path(directory)/'exchanges.jsonl');budget.closed=False
            def request():
                try:httpx.post(budget.url,json={'model':'owned-transport-fixture','state':{'question':'owned question'},'questions':{'intent':{}}},timeout=2,trust_env=False)
                except httpx.HTTPError:pass
            client=threading.Thread(target=request);client.start();end=time.monotonic()+1
            try:
                while not upstream.requests and time.monotonic()<end:time.sleep(.005)
                self.assertEqual(len(upstream.requests),1);started=time.monotonic();budget.close();client.join(1)
                self.assertLess(time.monotonic()-started,.8);self.assertFalse(client.is_alive())
                self.assertEqual(budget.count,1);self.assertEqual(budget.inflight,0);self.assertEqual(budget.handlers,0);self.assertFalse(budget.timer.is_alive())
            finally:
                if budget.thread.is_alive():budget.close()
                client.join(2)
    def test_global_budget_cancels_dribbling_provider_io_and_handlers(self):
        def dribble(conn,stop):
            conn.sendall(b'HTTP/1.1 200 Owned\r\nContent-Length: 1000\r\n\r\n')
            while not stop.wait(.02):conn.sendall(b'x')
        with tempfile.TemporaryDirectory() as directory,Upstream(dribble) as upstream:
            # Only a local fault-fixture timeout changes; real manifest remains106/900.
            manifest={'provider':{'url':upstream.url,'model':'owned-transport-fixture'},'provider_budget':{'maximum_upstream_http_posts':106,'maximum_wall_clock_seconds':.25},'preregistration':{'cases':[{'question':'owned question'}]}}
            budget=ProviderBudget(manifest,Path(directory)/'exchanges.jsonl');budget.closed=False;started=time.monotonic()
            try:
                try:httpx.post(budget.url,json={'model':'owned-transport-fixture','state':{'question':'owned question'},'questions':{'intent':{}}},timeout=1,trust_env=False)
                except httpx.HTTPError:pass
                budget.close();self.assertLess(time.monotonic()-started,.9)
                self.assertEqual(budget.count,1);self.assertEqual(len(upstream.requests),1);self.assertEqual(budget.inflight,0);self.assertEqual(budget.handlers,0)
                self.assertIn('absolute-wall-deadline',budget.violations);self.assertFalse(budget.thread.is_alive());self.assertFalse(budget.timer.is_alive())
            finally:
                if budget.thread.is_alive():budget.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IOTests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    files=[Path(__file__),Path(__file__).with_name('optimization_provider_io.py'),Path(__file__).with_name('optimization_neutral_witness.py')]
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_provider_posts':0,'scope':'Owned loopback transport fixtures only; no hub, original cohort, semantic model or real provider.','sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
