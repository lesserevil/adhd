#!/usr/bin/env python3
"""Bounded temporary relay to an existing local model, bound only to private IPs.

Never starts or changes the model. Reports record typed decisions, publication
IDs and request digests, excluding raw request/state and credentials. Send SIGTERM
or Ctrl-C for a graceful shutdown after the platform smoke tests.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import signal
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', action='append', required=True,
                        help='An owned private Docker bridge IP; repeat for another bridge')
    parser.add_argument('--port', type=int, default=18771)
    parser.add_argument('--target', default='http://127.0.0.1:18770')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--max-calls', type=int, default=32)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.max_calls <= 256 or not 0 < args.timeout <= 30:
        parser.error('Port, call limit or timeout outside supported bounds')
    for bind in args.bind:
        address = ipaddress.ip_address(bind)
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
            parser.error('--bind must be a specific private IPv4 Docker bridge address')
    target = urlsplit(args.target)
    if (target.scheme != 'http' or target.hostname not in ('127.0.0.1', 'localhost')
            or target.username or target.password or target.path or target.query or target.fragment):
        parser.error('--target must be the existing local HTTP model origin')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    # The platform parent checks this audit file before sending its first call.
    # Refuse an existing report so a new relay cannot inherit another run's data.
    with args.report.open('x') as initial_report:
        initial_report.write('[]\n')
    args.report.chmod(0o600)
    events, lock, limit = [], threading.Lock(), threading.BoundedSemaphore(4)
    post_count = 0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *values):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            nonlocal post_count
            if self.path not in ('/health', '/v1/systemone') or not limit.acquire(blocking=False):
                self.send_error(503)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 1048576:
                    self.send_error(413)
                    return
                if self.command == 'POST':
                    with lock:
                        if post_count >= args.max_calls:
                            self.send_error(429)
                            return
                        post_count += 1
                self.connection.settimeout(args.timeout)
                body = self.rfile.read(size)
                started = time.monotonic()
                request = Request(args.target + self.path, data=body if self.command == 'POST' else None,
                                  method=self.command, headers={'Content-Type': 'application/json'})
                with urlopen(request, timeout=args.timeout) as response:
                    status, result = response.status, response.read(262145)
                if len(result) > 262144:
                    raise ValueError('Model response exceeded relay bound')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(result)))
                self.end_headers()
                self.wfile.write(result)
                if self.command == 'POST':
                    value = json.loads(body)
                    row = {'path': self.path, 'status': status,
                           'elapsed_ms': round((time.monotonic()-started)*1000),
                           'request_sha256': hashlib.sha256(body).hexdigest(),
                           'typed_response': json.loads(result),
                           'publication_id': value.get('state', {}).get('publication', {}).get('id')}
                    with lock:
                        events.append(row)
                        args.report.write_text(json.dumps(events, indent=2)+'\n')
            except Exception as error:
                try:
                    self.send_error(503)
                except OSError:
                    pass
                with lock:
                    events.append({'status': 503, 'error_type': type(error).__name__})
                    args.report.write_text(json.dumps(events, indent=2)+'\n')
            finally:
                limit.release()

    servers = []
    stopped = threading.Event()
    try:
        for bind in args.bind:
            server = ThreadingHTTPServer((bind, args.port), Handler)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        print('Private bridge model relay ready', flush=True)
        stopped.wait()
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
