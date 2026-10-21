#!/usr/bin/env python3
"""Independent shared-pool fairness and raw Kafka progress through public APIs.

A bounded controlled HTTP decision/peer fixture supplies slow/failing responses;
the Kafka service remains real. Counts distinguish provider observations from
pool grants. Run only against isolated projects supplied by multi_support.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time

from multi_support import PROJECTS, arguments, execute, poll_until, scoped


RED, BLUE = 'project-red', 'project-blue'


class Gate:
    def __init__(self, bind, advertise=None, model=True):
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.observed = []
        self.active = 0
        self.maximum = 0
        self.model = model
        gate = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.reply(200, {'ready': True})

            def reply(self, status, value):
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 1048576:
                    self.reply(413, {})
                    return
                body = json.loads(self.rfile.read(length))
                project = (body.get('state', {}).get('publication', {}).get('project_id')
                           if model else body.get('origin_project_id', body.get('project_id')))
                with gate.lock:
                    gate.active += 1
                    gate.maximum = max(gate.maximum, gate.active)
                    gate.observed.append({'project_id': project, 'at': time.monotonic()})
                try:
                    if project == RED:
                        gate.release.wait(14)
                    if model:
                        self.reply(200, {'model': body['model'], 'answers': {
                            key: {'type': 'noul', 'noul': 1.0} for key in body['questions']}})
                    else:
                        # A failed real HTTP peer is a fault fixture, not fabricated
                        # successful federation evidence or a Kafka substitute.
                        self.reply(503, {'error': {'code': 'UNAVAILABLE'}})
                finally:
                    with gate.lock:
                        gate.active -= 1

        self.server = ThreadingHTTPServer((bind, 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://{advertise or bind}:{self.server.server_port}'
        self.url = self.base + '/v1/systemone'

    def rows(self):
        with self.lock:
            return list(self.observed)

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


async def until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(.025)
    raise AssertionError('Bounded fairness observation deadline exceeded')


def lane(admin, name):
    value = admin.call({'op': 'resource_status'})
    assert value['started'] is True
    assert not any(key in json.dumps(value).lower() for key in ('bearer', 'password', 'http://', 'https://'))
    return value['lanes'][name]


async def checks(f, evidence):
    assert f.model is None, 'This suite owns its bounded decision fixture; do not pass --with-model'
    model = Gate(f.args.fixture_bind, f.args.fixture_advertise)
    peer = Gate(f.args.fixture_bind, f.args.fixture_advertise, model=False)
    a, b, c, d, bridge = [await f.agent(name) for name in ('red-a', 'red-b', 'blue-a', 'blue-b', 'bridge')]
    admin = f.admin()
    try:
        admin.call({'op': 'config_update', 'patch': {
            'resources': {'model_concurrency': 1, 'project_model_concurrency': 1,
                          'network_concurrency': 1, 'project_network_concurrency': 1,
                          'eventing_concurrency': 2, 'project_eventing_concurrency': 1,
                          'max_waiters': 8},
            'matcher': {'url': model.url, 'model': 'Nemotron-Deciffusion-8B-v2.1',
                        'timeout_ms': 10000, 'retry_ms': 100}}}, mutation=True)
        await b.call(scoped(RED, 'subscribe', mode='filtered', filter='All API changes'))
        await d.call(scoped(BLUE, 'subscribe', mode='filtered', filter='All API changes'))
        await bridge.call(scoped(BLUE, 'subscribe', mode='raw'))
        red = (await a.call(scoped(RED, 'publish', text='Held red model request for API change')))['publication']
        await until(lambda: any(row['project_id'] == RED for row in model.rows()))
        for number in range(4):
            await a.call(scoped(RED, 'publish', text=f'Red API backlog item {number}'))
        blue = (await c.call(scoped(BLUE, 'publish', text='Blue API change must get a fair model turn')))['publication']
        await until(lambda: lane(admin, 'model')['projects'].get(BLUE, {}).get('queued', 0) >= 1)
        held = lane(admin, 'model')
        assert held['active'] == 1 and held['projects'][RED]['active'] == 1
        assert not any(row['project_id'] == BLUE for row in model.rows())
        began = time.monotonic()
        await poll_until(bridge, BLUE, {blue['id']}, deadline=4)
        assert (await c.call(scoped(BLUE, 'search', query='Blue API change must get a fair model turn')))['publications'] == [blue]
        assert time.monotonic() - began < 4
        assert not model.release.is_set()
        assert not (await d.call(scoped(BLUE, 'poll')))['deliveries']
        evidence.record('model-global-cap-and-real-raw-kafka-literal-search-progress-while-held',
                        actual_provider_calls=len(model.rows()), observed_model_concurrency=model.maximum,
                        model_pool_active=held['active'], blue_model_queued=True)
        model.release.set()
        await poll_until(d, BLUE, {blue['id']}, deadline=10)
        await poll_until(b, RED, {red['id']}, deadline=10)
        assert model.maximum == 1
        order = [row['project_id'] for row in model.rows()]
        assert order.index(BLUE) <= 2, order
        observed = lane(admin, 'model')
        assert observed['grants'] >= len(model.rows())
        evidence.record('another-project-model-turn-precedes-hot-project-backlog-drain',
                        provider_project_order=order, actual_provider_calls=len(model.rows()),
                        pool_grants=observed['grants'], grants_are_not_provider_call_count=True)

        # A separate slow/failing peer lane must not consume Kafka/model capacity.
        await until(lambda: lane(admin, 'model')['active'] == 0)
        admin.call({'op': 'config_update', 'patch': {
            'matcher': None,
            'federation': {'description': 'Controlled peer network fairness fixture',
                'timeout_ms': 10000, 'retry_ms': 100,
                'peers': [{'server_id': secrets.token_hex(16), 'url': peer.base,
                    'token': secrets.token_urlsafe(32), 'inbound_token': secrets.token_urlsafe(32),
                    'project_pairs': [{'local_project_id': project, 'remote_project_id': 'remote-'+project}
                                      for project in (RED, BLUE)]}]}}}, mutation=True)
        await a.call(scoped(RED, 'federated_query', question='Held red peer request', deadline_ms=10000))
        await until(lambda: any(row['project_id'] == RED for row in peer.rows()))
        await c.call(scoped(BLUE, 'federated_query', question='Blue peer request must be fair', deadline_ms=10000))
        await until(lambda: lane(admin, 'network')['projects'].get(BLUE, {}).get('queued', 0) >= 1)
        unfiltered = (await c.call(scoped(BLUE, 'publish', text='Raw event during a failing peer request')))['publication']
        before_calls = len(model.rows())
        await poll_until(bridge, BLUE, {unfiltered['id']}, deadline=4)
        assert len(model.rows()) == before_calls
        assert not peer.release.is_set()
        peer.release.set()
        await until(lambda: any(row['project_id'] == BLUE for row in peer.rows()))
        assert peer.maximum == 1
        evidence.record('slow-failing-peer-network-cap-independent-of-kafka-and-model-free-raw',
                        actual_peer_http_calls=len(peer.rows()), observed_peer_concurrency=peer.maximum,
                        additional_model_calls=0)
        state = admin.call({'op': 'resource_status'})
        assert state['waiting'] <= 8
        assert state['ingress_tickets'] <= 3*(256+4096)
        evidence.record('bounded-redacted-server-diagnostics', maximum_waiters=8,
                        observed_waiters=state['waiting'], finite_ingress_tickets=True)
    finally:
        model.close()
        peer.close()


if __name__ == '__main__':
    parser = arguments(__doc__)
    parser.add_argument('--fixture-bind', default='127.0.0.1')
    parser.add_argument('--fixture-advertise')
    args = parser.parse_args()
    asyncio.run(execute(args, 'adhd/multi-project-resource-fairness@1', checks))
