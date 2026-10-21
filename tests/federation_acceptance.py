#!/usr/bin/env python3
"""Independent three-hub federation acceptance; only standard Python libraries.

Fault fixtures test the protocol, not model quality. --matcher-url adds a real
SystemOne relevance check. No generated modules or test manifests are imported.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def request(base, path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body).encode()
    try:
        with urlopen(Request(base + path, data=data, headers=headers), timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        raw = exc.read()
        try:
            value = json.loads(raw)
        except ValueError:
            value = None
        return exc.code, value


class Model:
    def __init__(self):
        self.mode = 'normal'
        self.states = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.states.append(payload)
                if fixture.mode == 'error':
                    self.send_response(503)
                    self.end_headers()
                    return
                if fixture.mode == 'slow':
                    time.sleep(.6)
                project = payload.get('state', {}).get('project', {})
                # An independent deterministic fixture for transport/state checks.
                probability = .99 if 'image decoders' in project.get('description', '') else .01
                if fixture.mode == 'invalid':
                    probability = True
                value = {'model': payload['model'], 'answers': {
                    'relevance': {'type': 'noul', 'noul': probability}}}
                raw = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1/systemone'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class Hub:
    image = None

    def __init__(self, command, root, identity, matcher):
        self.command, self.root = command, root
        root.mkdir()
        self.base = f'http://127.0.0.1:{port()}'
        self.tokens = {name: secrets.token_urlsafe(32) for name in ('alice', 'bob')}
        self.config = {
            'project_id': identity, 'port': int(self.base.rsplit(':', 1)[1]),
            'store_path': str(root / 'hub.dets'), 'agents': self.tokens,
            'admin_token': secrets.token_urlsafe(32),
            'matcher': {'url': matcher, 'model': 'Nemotron-Deciffusion-8B-v2.1',
                        'timeout_ms': 1000, 'retry_ms': 100},
            'federation': {'description': 'We build image decoders.' if identity == 'beta'
                           else 'We build financial reporting tools.',
                           'peers': [], 'retry_ms': 100, 'timeout_ms': 1000}}
        self.process = None
        self.handles = []
        self.container = None

    def start(self):
        path = self.root / 'config.json'
        path.write_text(json.dumps(self.config))
        path.chmod(0o600)
        self.handles = [(self.root / name).open('ab') for name in ('stdout', 'stderr')]
        command = self.command
        if self.image:
            self.container = 'adhd-federation-test-' + uuid4().hex[:12]
            command = ['docker', 'run', '--rm', '--name', self.container,
                       '--network', 'host', '--user', f'{os.getuid()}:{os.getgid()}',
                       '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                       '--pids-limit', '128', '--memory', '512m', '--cpus', '2',
                       '--tmpfs', '/tmp:rw,nosuid,noexec,size=64m',
                       '--mount', f'type=bind,src={self.root},dst={self.root}',
                       '--env', f'ADHD_CONFIG_FILE={path}', self.image]
        self.process = subprocess.Popen(command + [json.dumps(['serve', str(path)])],
                                        stdout=self.handles[0], stderr=self.handles[1],
                                        start_new_session=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError('Hub failed startup; inspect private acceptance work directory')
            try:
                if request(self.base, '/health')[0] == 200:
                    return
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(.1)
        raise AssertionError('Hub readiness timeout')

    def stop(self, hard=False):
        if self.container:
            subprocess.run(['docker', 'kill' if hard else 'stop', self.container],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL if hard else signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        for handle in self.handles:
            handle.close()
        self.handles = []
        if self.container:
            subprocess.run(['docker', 'rm', '-f', self.container],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            self.container = None

    def call(self, command, agent='alice', key=None, error=None):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'SendMessage', 'params': {
            'message': {'messageId': key or uuid4().hex, 'role': 'ROLE_USER',
                        'parts': [{'data': command}]}}}
        status, result = request(self.base, '/a2a', body, self.tokens[agent])
        assert status == 200, (status, result)
        if error:
            assert error in json.dumps(result.get('error', {})), result
            return result
        assert 'error' not in result, result
        return result['result']['message']['parts'][0]['data']

    def query(self, **kwargs):
        return self.call({'op': 'federated_query',
                          'question': 'Which projects build image decoders?', **kwargs})['query']

    def get(self, query_id):
        return self.call({'op': 'get_federated_query', 'query_id': query_id})['query']

    def finish(self, query_id, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            query = self.get(query_id)
            if query['status'] != 'pending':
                return query
            time.sleep(.1)
        raise AssertionError('Federation job did not finish')


class BadPeer:
    """A hostile wire peer; its content must never become an accepted answer."""
    def __init__(self, response):
        self.mode = 'wrong-project'
        self.redirects_followed = 0
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                fixture.redirects_followed += 1
                self.send_response(500)
                self.end_headers()

            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                # This adversary implements only the original discovery protocol.
                # New metadata refreshes must fail explicitly rather than crashing
                # its request handler before a discovery correlation ID exists.
                if value.get('op') in ('catalog', 'identities'):
                    raw = json.dumps({'protocol_version': 1, 'error': {
                        'code': 'NOT_FOUND', 'message': 'Metadata is unsupported'}}).encode()
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fixture.mode == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', '/redirected')
                    self.end_headers()
                    return
                if value['op'] == 'submit':
                    status = 202
                    result = {'query_id': value['query_id'], 'status': 'pending'}
                else:
                    status = 200
                    answer = {**response, 'project_id': 'gamma'}
                    result = {'query_id': value['query_id'], 'status': 'completed', 'response': answer}
                    if fixture.mode == 'wrong-project':
                        answer['project_id'] = 'untrusted-project'
                    elif fixture.mode == 'wrong-query':
                        result['query_id'] = 'different-query'
                    elif fixture.mode == 'bad-probability':
                        answer['probability_ppm'] = True
                    elif fixture.mode == 'oversized':
                        answer['description'] = 'x' * (270 * 1024)
                    elif fixture.mode == 'bad-publication':
                        answer['publications'] = [{'id': 'invented'}]
                raw = json.dumps(result).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    runtime = parser.add_mutually_exclusive_group(required=True)
    runtime.add_argument('--command', help='JSON argv excluding application JSON argument')
    runtime.add_argument('--image', help='Run the same tests in hardened Docker containers')
    parser.add_argument('--work-dir', default='_build/federation/acceptance')
    parser.add_argument('--report', default='verification/federation-acceptance.json')
    parser.add_argument('--matcher-url', help='Optional real SystemOne endpoint')
    args = parser.parse_args()
    parent = Path(args.work_dir).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    command = json.loads(args.command) if args.command else []
    Hub.image = args.image
    model = Model()
    hubs = [Hub(command, root / identity, identity, model.url)
            for identity in ('alpha', 'beta', 'gamma')]
    a, b, c = hubs
    cases = []

    def record(name):
        cases.append({'case': name, 'passed': True})
        print('PASS', name, flush=True)

    try:
        # Fully connected cyclic configuration; incoming queries must never forward.
        for i, hub in enumerate(hubs):
            for j, other in enumerate(hubs):
                if i != j:
                    hub.config['federation']['peers'].append({
                        'project_id': other.config['project_id'], 'url': other.base,
                        'token': f'link-from-{i}-to-{j}-' + 'x' * 30,
                        'inbound_token': f'link-from-{j}-to-{i}-' + 'x' * 30})
            hub.start()
        record('three-independent-hubs-ready')
        saved_federation = json.loads(json.dumps(a.config['federation']))

        exported = b.call({'op': 'publish', 'text': 'We maintain PNG and JPEG image decoders.'})['publication']
        hidden = b.call({'op': 'publish', 'text': 'PRIVATE_ARCHIVE_SENTINEL'})['publication']
        private = b.call({'op': 'send', 'recipient_id': 'bob', 'text': 'PRIVATE_MESSAGE_SENTINEL'})['delivery']
        b.stop()
        b.config['federation']['export_publication_ids'] = [exported['id'], private['id'], hidden['id'] + '-missing']
        b.start()
        q = a.query(deadline_ms=15000)
        assert q['status'] == 'pending' and len(q['peers']) == 2
        done = a.finish(q['id'])
        assert done['status'] == 'completed', done
        assert [r['project_id'] for r in done['responses']] == ['beta', 'gamma'], done
        positive, negative = done['responses']
        assert positive['matched'] is True and positive['probability_ppm'] == 990000
        assert positive['publications'] == [exported]
        assert negative['matched'] is False and negative['description'] == '' and negative['publications'] == []
        record('semantic-fixture-match-nonmatch-and-evidence')
        snapshots = [item['state']['project'] for item in model.states]
        assert len(snapshots) == 2, snapshots  # cyclic peers do not forward
        serialized = json.dumps([done, snapshots])
        assert 'PRIVATE_ARCHIVE_SENTINEL' not in serialized and 'PRIVATE_MESSAGE_SENTINEL' not in serialized
        for hub in hubs:
            for token in hub.tokens.values():
                assert token not in serialized
        record('export-allowlist-private-isolation-and-no-forwarding')
        a.call({'op': 'get_federated_query', 'query_id': q['id']}, agent='bob', error='FORBIDDEN')
        record('query-owner-isolation')

        cmd = {'op': 'federated_query', 'question': 'Which projects build image decoders?', 'deadline_ms': 15000}
        first = a.call(cmd, key='stable-creation')
        assert a.call(cmd, key='stable-creation') == first
        a.call({**cmd, 'question': 'Different question'}, key='stable-creation', error='IDEMPOTENCY_CONFLICT')
        a.finish(first['query']['id'])
        record('agent-creation-retry-and-conflict')

        peer_token = a.config['federation']['peers'][0]['token']
        body = {'op': 'status', 'origin_project_id': 'alpha', 'query_id': 'nonexistent'}
        assert request(b.base, '/federation', body, a.tokens['alice'])[0] == 401
        assert request(b.base, '/federation', body, b.config['admin_token'])[0] == 401
        assert request(b.base, '/federation', {**body, 'origin_project_id': 'gamma'}, peer_token)[0] == 403
        assert request(b.base, '/federation', body, peer_token)[0] == 404
        assert request(b.base, '/a2a', {}, peer_token)[0] == 401
        record('peer-identity-and-credential-role-separation')

        submit = {'op': 'submit', 'origin_project_id': 'alpha', 'query_id': 'wire-retry-key',
                  'question': 'Which projects build image decoders?',
                  'deadline_at': (datetime.now(timezone.utc) + timedelta(seconds=15)).isoformat().replace('+00:00', 'Z')}
        assert request(b.base, '/federation', submit, peer_token)[0] == 202
        assert request(b.base, '/federation', submit, peer_token)[0] in (200, 202)
        assert request(b.base, '/federation', {**submit, 'question': 'Conflicting body'}, peer_token)[0] == 409
        c_token = next(p['token'] for p in c.config['federation']['peers'] if p['project_id'] == 'beta')
        assert request(b.base, '/federation', {'op': 'status', 'origin_project_id': 'gamma',
                       'query_id': submit['query_id']}, c_token)[0] == 404
        record('peer-submission-retries-conflicts-and-status-isolation')

        c.stop()
        c.config['threshold_ppm'] = 5000
        c.start()
        policy = a.finish(a.query(deadline_ms=10000)['id'])
        assert policy['status'] == 'completed', policy
        gamma = next(r for r in policy['responses'] if r['project_id'] == 'gamma')
        assert gamma['matched'] is True and gamma['probability_ppm'] == 10000
        record('peers-can-calibrate-their-own-match-thresholds')
        c.stop()
        c.config['threshold_ppm'] = 900000
        c.start()

        model.mode = 'error'
        # Container cold starts include BEAM compilation twice. Keep the job's
        # deadline beyond that recovery window so expiry cannot mask recovery.
        pending = a.query(deadline_ms=120000)
        time.sleep(.5)
        assert a.get(pending['id'])['status'] == 'pending'
        start = time.monotonic()
        a.call({'op': 'publish', 'text': 'Ordinary local traffic remains usable.'})
        a.call({'op': 'poll'})
        assert time.monotonic() - start < 2
        a.stop(hard=True)
        b.stop(hard=True)
        a.start()
        b.start()
        assert a.get(pending['id'])['status'] == 'pending'
        model.mode = 'normal'
        recovered = a.finish(pending['id'])
        assert recovered['status'] == 'completed' and len(recovered['responses']) == 2
        record('model-outage-local-responsiveness-and-hard-restart-recovery')

        model.mode = 'error'
        cancelled = a.query(deadline_ms=10000)
        cmd = {'op': 'cancel_federated_query', 'query_id': cancelled['id']}
        assert a.call(cmd, key='cancel-key')['query']['status'] == 'cancelled'
        assert a.call(cmd, key='cancel-key')['query']['status'] == 'cancelled'
        model.mode = 'normal'
        time.sleep(.5)
        assert a.get(cancelled['id'])['status'] == 'cancelled'
        record('durable-cancellation-and-late-result-discard')

        c.stop()
        partial = a.query(deadline_ms=2000)
        incremental_deadline = time.monotonic() + 1.5
        while time.monotonic() < incremental_deadline:
            progressive = a.get(partial['id'])
            if progressive['responses']:
                break
            time.sleep(.05)
        assert progressive['status'] == 'pending' and progressive['responses'], progressive
        record('incremental-results-available-before-deadline')
        answer = a.finish(partial['id'])
        assert answer['status'] == 'partial', answer
        assert any(r['project_id'] == 'beta' for r in answer['responses'])
        assert not any(r['project_id'] == 'gamma' for r in answer['responses'])
        record('offline-peer-partial-coverage')
        c.start()

        model.mode = 'invalid'
        invalid = a.finish(a.query(deadline_ms=1500)['id'])
        assert invalid['status'] == 'partial' and not invalid['responses'], invalid
        record('boolean-model-result-rejected-without-keyword-fallback')
        model.mode = 'normal'

        model.mode = 'error'
        removed = a.query(deadline_ms=10000)
        a.stop(hard=True)
        a.config['federation']['peers'] = []
        a.start()
        removal = a.finish(removed['id'])
        assert removal['status'] == 'partial' and not removal['responses'], removal
        record('peer-removal-stops-persisted-dispatch')
        model.mode = 'normal'

        bad = BadPeer(negative)
        try:
            for mode in ('wrong-project', 'wrong-query', 'bad-probability', 'oversized',
                         'bad-publication', 'redirect'):
                bad.mode = mode
                a.stop()
                a.config['federation']['peers'] = [{
                    'project_id': 'gamma', 'url': bad.url,
                    'token': 'outgoing-test-token-' + 'x' * 30,
                    'inbound_token': 'incoming-test-token-' + 'x' * 30}]
                a.start()
                rejected = a.finish(a.query(deadline_ms=1200)['id'])
                assert rejected['status'] == 'partial' and not rejected['responses'], (mode, rejected)
                record('reject-wire-' + mode)
            assert bad.redirects_followed == 0
        finally:
            bad.close()

        a.stop()
        a.config.pop('federation')
        a.start()
        a.call({'op': 'federated_query', 'question': 'Anything?'}, error='FEDERATION_DISABLED')
        assert a.get(q['id'])['status'] == 'completed'
        assert request(a.base, '/federation', body, peer_token)[0] == 404
        assert a.call({'op': 'search', 'query': 'Ordinary local traffic'})['publications']
        record('disabled-federation-legacy-traffic-and-owned-history')
        a.stop()
        a.config['federation'] = {**saved_federation, 'peers': []}
        a.start()
        empty = a.finish(a.query()['id'])
        assert empty['status'] == 'completed' and empty['responses'] == [] and empty['peers'] == []
        record('empty-peer-set-has-explicit-empty-scope')

        live = {'state': 'not-run', 'reason': 'No real matcher URL supplied'}
        if args.matcher_url:
            for hub in hubs:
                hub.stop()
                hub.config['matcher']['url'] = args.matcher_url
            a.config['federation'] = saved_federation
            for hub in hubs:
                hub.start()
            result = a.finish(a.query(deadline_ms=90000)['id'], timeout=100)
            assert result['status'] == 'completed', result
            matches = [r['project_id'] for r in result['responses'] if r['matched']]
            assert matches == ['beta'], result
            live = {'state': 'passed', 'matching_projects': matches,
                    'probabilities_ppm': {r['project_id']: r['probability_ppm'] for r in result['responses']}}
            record('real-systemone-three-hub-project-discovery')

        a.stop()
        a.config['federation'] = saved_federation
        a.start()
        model.mode = 'error'
        # Use the fault model even if the optional live-model path ran above.
        for hub in (b, c):
            hub.stop()
            hub.config['matcher']['url'] = model.url
            hub.start()
        saturated = [a.query(deadline_ms=120000)['id'] for _ in range(64)]
        a.call({'op': 'federated_query', 'question': 'Over the active job budget',
                'deadline_ms': 120000}, error='RESOURCE_EXHAUSTED')
        for identity in saturated:
            a.call({'op': 'cancel_federated_query', 'query_id': identity})
        a.stop(hard=True)
        a.start()
        assert all(a.get(identity)['status'] == 'cancelled' for identity in saturated)
        record('bounded-active-query-budget-and-cancellation-survives-restart')

        # DETS must not retain configuration credentials.
        for hub in hubs:
            hub.stop()
            raw = (hub.root / 'hub.dets').read_bytes()
            snapshot = hub.root / 'hub.dets.snapshot'
            if snapshot.exists():
                assert snapshot.stat().st_mode & 0o777 == 0o600
                raw += snapshot.read_bytes()
            tokens = list(hub.tokens.values()) + [hub.config['admin_token']]
            for peer in hub.config.get('federation', {}).get('peers', []):
                tokens.extend((peer['token'], peer['inbound_token']))
            assert all(token.encode() not in raw for token in tokens)
        record('persisted-state-excludes-credentials')
        for name in ('blank-description', 'unknown-field', 'credential-collision', 'url-userinfo'):
            invalid_hub = Hub(command, root / name, 'invalid-config', model.url)
            invalid_hub.config['federation'] = json.loads(json.dumps(saved_federation))
            if name == 'blank-description':
                invalid_hub.config['federation']['description'] = ' '
            elif name == 'unknown-field':
                invalid_hub.config['federation']['unexpected'] = True
            elif name == 'credential-collision':
                invalid_hub.config['federation']['peers'][0]['inbound_token'] = invalid_hub.tokens['alice']
            else:
                invalid_hub.config['federation']['peers'][0]['url'] = 'https://user:password@example.test'
            try:
                try:
                    invalid_hub.start()
                except AssertionError:
                    assert invalid_hub.process.poll() is not None and invalid_hub.process.returncode != 0
                else:
                    raise AssertionError('Invalid federation configuration accepted: ' + name)
            finally:
                invalid_hub.stop()
        record('strict-federation-config-and-token-collision-rejection')
        report = {'schema': 'adhd/federation-acceptance@1', 'passed': True,
                  'cases': cases, 'live_model': live}
        if args.image:
            report['image_id'] = subprocess.check_output(
                ['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
        artifacts = [Path(p) for p in command if Path(p).is_file()]
        report['input_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    finally:
        for hub in hubs:
            hub.stop()
        model.close()


if __name__ == '__main__':
    main()
