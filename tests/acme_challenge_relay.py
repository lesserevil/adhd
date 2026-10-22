"""Owned HTTP-01 validation relay; never substitutes for a CA or ACME client.

Only a real successful upstream proof may be held/corrupted. Tokens and proof
bodies remain in memory; the public evidence view contains hashes and lengths.
Construction is inert. start() explicitly owns a loopback listener.
"""
import hashlib
import http.client
import re
import socket
import socketserver
import threading
import time


TARGET = re.compile(rb'/\.well-known/acme-challenge/[A-Za-z0-9_-]{22,256}\Z')


def parse_request(raw):
    assert len(raw) <= 8192 and raw.endswith(b'\r\n\r\n'), 'Bounded complete request required'
    lines = raw[:-4].split(b'\r\n')
    assert len(lines) <= 32
    method, target, protocol = lines[0].split(b' ')
    assert method == b'GET' and TARGET.fullmatch(target) and protocol in (b'HTTP/1.0', b'HTTP/1.1')
    headers = []
    for line in lines[1:]:
        key, value = line.split(b':', 1)
        assert re.fullmatch(rb'[A-Za-z0-9-]+', key)
        value = value.strip(b' \t')
        assert value and all(32 <= char < 127 for char in value)
        headers.append((key.lower(), value))
    hosts = [v for k, v in headers if k == b'host']
    assert len(hosts) == 1 and not any(k in (b'transfer-encoding', b'content-length') for k, _ in headers)
    return target.decode('ascii'), hosts[0].decode('ascii')


def public_event(path, host, status, body, mode):
    return {'at_monotonic': time.monotonic(), 'target_sha256': hashlib.sha256(path.encode()).hexdigest(),
            'host_sha256': hashlib.sha256(host.encode()).hexdigest(), 'upstream_status': status,
            'proof_sha256': hashlib.sha256(body).hexdigest(), 'proof_bytes': len(body), 'mode': mode}


class ChallengeRelay:
    def __init__(self, port=8080, upstream_port=18080, *, bind='127.0.0.1', max_requests=128, hold_seconds=20, upstreams=None):
        assert bind in ('127.0.0.1', '127.0.0.2') and 0 < port < 65536 and 0 < upstream_port < 65536
        assert 1 <= max_requests <= 256 and 0 < hold_seconds <= 30 and port != upstream_port
        self.bind, self.port, self.upstream_port = bind, port, upstream_port
        self.upstreams = dict(upstreams or {'one.acme.test': upstream_port})
        assert 1 <= len(self.upstreams) <= 2
        assert all(name in ('one.acme.test', 'two.acme.test') and type(value) is int and 0 < value < 65536
                   and value != port for name, value in self.upstreams.items())
        self.max_requests, self.hold_seconds = max_requests, hold_seconds
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.held = threading.Event()
        self.closing = threading.Event()
        self.mode = 'pass'
        self.events, self.errors = [], []
        self.requests = self.active = 0
        self.held_proof = None
        self.server = self.thread = None

    def set_mode(self, mode):
        assert mode in ('pass', 'hold', 'corrupt', '404')
        with self.lock:
            assert self.active == 0, 'Change relay mode only between exchanges'
            self.mode = mode
            self.release.clear()
            self.held.clear()
            self.held_proof = None

    def start(self):
        assert self.server is None and not self.closing.is_set()
        owner = self

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = False
            daemon_threads = False
            block_on_close = True

            def process_request(self, request, address):
                with owner.lock:
                    if owner.active >= 8 or owner.requests >= owner.max_requests or owner.closing.is_set():
                        request.close()
                        owner.errors.append('request-cap-or-concurrency')
                        return
                    owner.active += 1
                    owner.requests += 1
                try:
                    super().process_request(request, address)
                except BaseException:
                    with owner.lock:
                        owner.active -= 1
                    request.close()
                    raise

            def process_request_thread(self, request, address):
                try:
                    super().process_request_thread(request, address)
                finally:
                    with owner.lock:
                        owner.active -= 1

            def handle_error(self, request, address):
                # No raw request, token or exception text in logs.
                with owner.lock:
                    owner.errors.append('handler-error')

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                raw = bytearray()
                try:
                    while b'\r\n\r\n' not in raw:
                        block = self.request.recv(min(1024, 8193 - len(raw)))
                        assert block and len(raw) + len(block) <= 8192
                        raw.extend(block)
                    assert raw.find(b'\r\n\r\n') == len(raw) - 4
                    path, host = parse_request(bytes(raw))
                    hostname = host.split(':', 1)[0]
                    assert hostname in owner.upstreams, 'Relay never forwards an unregistered domain'
                    conn = http.client.HTTPConnection(owner.bind, owner.upstreams[hostname], timeout=3)
                    try:
                        conn.request('GET', path, headers={'Host': host, 'Connection': 'close'})
                        response = conn.getresponse()
                        body = response.read(1025)
                        assert len(body) <= 1024
                        status = response.status
                    finally:
                        conn.close()
                    with owner.lock:
                        mode = owner.mode
                        event = public_event(path, host, status, body, mode)
                        owner.events.append(event)
                    if status == 200:
                        assert body and all(32 <= byte < 127 for byte in body)
                        if mode == 'hold':
                            with owner.lock:
                                owner.held_proof = (path, host, body)
                            owner.held.set()
                            released = owner.release.wait(owner.hold_seconds)
                            event['hold_released'] = released
                            if not released or owner.closing.is_set():
                                status, body = 503, b''
                        elif mode == 'corrupt':
                            body = b'independent-invalid-key-authorization'
                        elif mode == '404':
                            status, body = 404, b''
                    event['downstream_status'] = status
                    event['completed_monotonic'] = time.monotonic()
                    wire = (f'HTTP/1.1 {status} Result\r\nContent-Type: text/plain\r\n'
                            f'Cache-Control: no-store\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode() + body
                    self.request.sendall(wire)
                except (AssertionError, ValueError, OSError, http.client.HTTPException) as exc:
                    with owner.lock:
                        owner.errors.append(type(exc).__name__)
                    try:
                        self.request.sendall(b'HTTP/1.1 502 Result\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                    except OSError:
                        pass

        self.server = Server((self.bind, self.port), Handler)
        try:
            self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1})
            self.thread.start()
        except BaseException:
            self.server.server_close()
            self.server = None
            raise
        return self

    def snapshot(self):
        with self.lock:
            return {'requests': self.requests, 'active': self.active, 'events': [dict(v) for v in self.events],
                    'errors': list(self.errors), 'closed': self.closing.is_set() and self.active == 0 and
                    (self.thread is None or not self.thread.is_alive())}

    def close(self):
        self.closing.set()
        self.release.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=5)
            assert not self.thread.is_alive(), 'Owned relay accept thread remained'
        assert self.active == 0, 'Owned relay handler remained'
