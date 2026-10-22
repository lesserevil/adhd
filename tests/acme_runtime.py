"""Independent native diagnostic custody and ordinary verifying HTTP(S) clients.

No service starts on import. This cache launcher is diagnostic, never a substitute
for the later official exported-artifact and packaged-image acceptance gates.
"""
import hashlib
import http.client
from http.cookiejar import CookieJar
import json
import os
import re
from pathlib import Path
import signal
import socket
import ssl
import stat
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import (Request, build_opener, ProxyHandler, HTTPSHandler,
                            HTTPCookieProcessor, HTTPRedirectHandler)
from uuid import uuid4
from acme_process_observer import Descendants


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path):
    value = Path(path).lstat()
    assert stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_uid == os.getuid()
    return value


def ticks(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except FileNotFoundError:
        return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicClient:
    def __init__(self, base, *, trust=None, connect_ip='127.0.0.1', bearer=None):
        parsed = urlsplit(base)
        assert parsed.scheme in ('http', 'https') and not parsed.username and not parsed.password
        assert not parsed.query and not parsed.fragment and parsed.path in ('', '/')
        self.base, self.bearer, self.csrf = base.rstrip('/'), bearer, None
        self.cookies, self.handshakes = CookieJar(), []
        handlers = [ProxyHandler({}), HTTPCookieProcessor(self.cookies), NoRedirect()]
        if parsed.scheme == 'https':
            assert trust is not None and connect_ip in ('127.0.0.1', '127.0.0.2')
            context = ssl.create_default_context(cafile=str(trust))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            owner = self

            class Connection(http.client.HTTPSConnection):
                def connect(self):
                    assert self.host == parsed.hostname and self.port == parsed.port
                    sock = socket.create_connection((connect_ip, self.port), self.timeout)
                    try:
                        self.sock = context.wrap_socket(sock, server_hostname=self.host)
                    except BaseException:
                        sock.close()
                        raise
                    owner.handshakes.append({'der': self.sock.getpeercert(binary_form=True),
                                             'tls_version': self.sock.version(),
                                             'at_monotonic': time.monotonic(),
                                             'verified_chain_and_hostname': True})

            class Handler(HTTPSHandler):
                def https_open(self, request):
                    return self.do_open(Connection, request)

            handlers.append(Handler(context=context))
        self.opener = build_opener(*handlers)

    def request(self, path, data=None, *, headers=None, timeout=5):
        assert path.startswith('/') and not path.startswith('//') and '\r' not in path and '\n' not in path
        hs = {'Origin': self.base}
        if self.bearer:
            hs['Authorization'] = 'Bearer ' + self.bearer
        if self.csrf:
            hs['X-CSRF-Token'] = self.csrf
        if data is not None:
            hs['Content-Type'] = 'application/json'
        hs.update(headers or {})
        raw = json.dumps(data).encode() if data is not None else None
        try:
            response = self.opener.open(Request(self.base + path, data=raw, headers=hs), timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(262145)
            assert len(body) <= 262144, 'Public response bound'
            value = json.loads(body) if response.headers.get_content_type() == 'application/json' else body.decode()
            return response.status, value, response.headers

    def api(self, command, expected=200):
        status, value, _ = self.request('/admin/api', command)
        assert status == expected, ('Admin API status', command['op'], status, expected)
        return value

    def login(self, username, password):
        status, _, _ = self.request('/admin/login', {'username': username, 'password': password})
        assert status == 200, ('Login status', status)
        status, session, _ = self.request('/admin/session')
        assert status == 200 and session['authenticated'] is True
        self.csrf = session['csrf']
        return session['user']

    def mutate(self, op, *, expected=200, message_id=None, **fields):
        # Observe public effective revision; never infer it from unnormalized disk.
        revision = self.api({'op': 'config_get'})['config_revision']
        command = {'op': op, 'expected_revision': revision, 'confirm': True,
                   'message_id': message_id or uuid4().hex, **fields}
        return self.api(command, expected), command

    def rpc(self, command, token, message_id=None):
        envelope = {'jsonrpc': '2.0', 'id': 1, 'method': 'SendMessage', 'params': {'message': {
            'messageId': message_id or uuid4().hex, 'role': 'ROLE_USER', 'parts': [{'data': command}]}}}
        status, value, _ = self.request('/a2a', envelope, headers={'Authorization': 'Bearer ' + token})
        assert status == 200 and 'error' not in value, 'Authenticated A2A command failed'
        return value['result']['message']['parts'][0]['data']


class NativeDiagnostic:
    def __init__(self, root, source, cache, elixir, cache_manifest_sha256, *, erlang, peer_trust=None, peer_hosts=()):
        self.root, self.source, self.cache = map(lambda p: Path(p).resolve(), (root, source, cache))
        self.elixir = Path(elixir).resolve()
        self.erlang = Path(erlang).resolve()
        self.peer_trust = Path(peer_trust).resolve() if peer_trust else None
        self.peer_hosts = tuple(peer_hosts)
        assert all(host in ('one.acme.test', 'two.acme.test') for host in self.peer_hosts)
        self.manifest_sha = cache_manifest_sha256
        self.file = self.root / 'hub.json'
        self.process, self.logs, self.log_ids = None, [], []
        self.identities = []
        self.observer = None

    def verify(self):
        manifest = self.cache / 'sources.json'
        regular(manifest)
        assert sha(manifest) == self.manifest_sha
        files = json.loads(manifest.read_text())
        assert isinstance(files, dict) and len(files) >= 50
        for relative, digest in files.items():
            path = Path(relative)
            assert not path.is_absolute() and '..' not in path.parts
            regular(self.source / path)
            assert sha(self.source / path) == digest, 'Diagnostic cache source drift'
        beams = sorted(self.cache.glob('*.beam'))
        assert len(beams) >= 59
        for path in beams:
            regular(path)
        return {'scope': 'source-bound diagnostic module cache; not official artifact',
                'source_manifest_sha256': self.manifest_sha, 'sources': files,
                'beams': {path.name: sha(path) for path in beams}, 'elixir_sha256': sha(self.elixir),
                'erlang_sha256': sha(self.erlang)}

    def start(self):
        assert self.process is None
        binding = self.verify()
        regular(self.file)
        self.base = 'http://127.0.0.1:' + str(json.loads(self.file.read_text())['port'])
        try:
            for name in ('stdout.log', 'stderr.log'):
                path = self.root / name
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                handle = os.fdopen(fd, 'ab', buffering=0)
                self.logs.append(handle)
                st = os.fstat(fd)
                assert stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid()
                self.log_ids.append((path, st.st_dev, st.st_ino))
            code = '[payload] = System.argv(); ADHD.CLI.run(JSON.decode!(payload))'
            command = [str(self.elixir), '-pa', str(self.cache), '-e', code, '--', json.dumps(['serve', str(self.file)])]
            env = {'PATH': str(self.elixir.parent) + ':' + str(self.erlang.parent) + ':/usr/bin:/bin', 'HOME': str(self.root),
                   'LANG': 'C.UTF-8', 'ERL_FLAGS': '+S 2:2'}
            def erl_path(path):
                assert re.fullmatch(r'[A-Za-z0-9_./-]+', str(path)), 'Owned runtime path must have an unambiguous Erlang argument'
                return "'" + json.dumps(str(path)) + "'"
            if self.peer_trust:
                regular(self.peer_trust)
                binding['peer_trust_sha256'] = sha(self.peer_trust)
                env['ERL_FLAGS'] += ' -public_key cacerts_path ' + erl_path(self.peer_trust)
            if self.peer_hosts:
                inetrc = self.root/'fixture.inetrc'
                data = '{lookup, [file]}.\n' + ''.join('{host, {127,0,0,1}, ['+json.dumps(host)+']}.\n' for host in self.peer_hosts)
                if inetrc.exists():
                    regular(inetrc)
                    assert inetrc.read_text() == data
                else:
                    fd = os.open(inetrc, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'w') as output:
                        output.write(data)
                binding['peer_inetrc_sha256'] = sha(inetrc)
                env['ERL_FLAGS'] += ' -kernel inetrc ' + erl_path(inetrc)
            self.process = subprocess.Popen(command, stdout=self.logs[0], stderr=self.logs[1],
                                            start_new_session=True, env=env)
            self.pid_ticks = ticks(self.process.pid)
            assert self.pid_ticks is not None
            row = {'pid': self.process.pid, 'start_ticks': self.pid_ticks,
                   'config_path_sha256': hashlib.sha256(str(self.file).encode()).hexdigest(),
                   'binding': binding, 'started_monotonic': time.monotonic(), 'reaped': False}
            self.identities.append(row)
            self.observer = Descendants(self.process.pid,self.pid_ticks).start()
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                assert self.process.poll() is None, 'Owned diagnostic VM exited before readiness'
                try:
                    if PublicClient(self.base).request('/health', timeout=1)[0] == 200:
                        row['first_health_monotonic'] = time.monotonic()
                        return self
                except (OSError, TimeoutError):
                    pass
                time.sleep(.1)
            raise AssertionError('Original 45 second readiness bound')
        except BaseException as original:
            try:
                self.stop()
            except BaseException as cleanup:
                original.add_note('Owned diagnostic startup cleanup failed: ' + type(cleanup).__name__)
            raise

    def stop(self, hard=False):
        try:
            if self.process:
                if self.process.poll() is None:
                    assert ticks(self.process.pid) == self.pid_ticks, 'Owned VM identity changed'
                    os.killpg(self.process.pid, signal.SIGKILL if hard else signal.SIGTERM)
                    try:
                        self.process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        assert ticks(self.process.pid) == self.pid_ticks
                        os.killpg(self.process.pid, signal.SIGKILL)
                        self.process.wait(timeout=5)
                self.process.wait(timeout=1)
                self.identities[-1].update(reaped=True, exit_code=self.process.returncode,
                                           original_identity_absent=ticks(self.process.pid) != self.pid_ticks)
                self.process = None
        finally:
            try:
                if self.observer:
                    try:
                        self.observer.close()
                    finally:
                        self.identities[-1]['observed_descendants'] = self.observer.evidence()
                        self.observer = None
            finally:
                try:
                    for handle in self.logs:
                        handle.close()
                finally:
                    self.logs = []
                    for path, dev, ino in self.log_ids:
                        value = regular(path)
                        assert (value.st_dev, value.st_ino) == (dev, ino), 'Owned log pathname replaced'
                    self.log_ids = []
