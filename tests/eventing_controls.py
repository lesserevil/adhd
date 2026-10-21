#!/usr/bin/env python3
"""Independent real-Kafka Admin recovery, bounded replay and frozen-policy checks."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import jsonschema
from federation_acceptance import Hub, Model, request
from federation_multi import WireValidator, wait

class ControlledGateway:
    """Forward actual Kafka HTTP, optionally block or corrupt one produced value."""
    def __init__(self, upstream):
        self.upstream = upstream.rstrip('/')
        self.blocked, self.corrupt_next = False, False
        self.produces = []
        self.fail_topic = self.hold_topic = None
        self.block_produces = False
        self.holding, self.release = threading.Event(), threading.Event()
        self.alters = []
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self): self.forward()
            def do_POST(self): self.forward()
            def do_DELETE(self): self.forward()
            def forward(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if fixture.blocked or (fixture.fail_topic and fixture.fail_topic in self.path) or (fixture.block_produces and self.command=="POST" and self.path.startswith("/topics/")):
                    self.send_error(503)
                    return
                if self.command=="POST" and self.path.endswith("/configs:alter"):
                    fixture.alters.append(json.loads(body))
                original = None
                if self.command == 'POST' and self.path.startswith('/topics/'):
                    original = json.loads(body)
                    if fixture.corrupt_next:
                        fixture.corrupt_next = False
                        changed = json.loads(body)
                        changed['records'][0]['value'] = {'foreign': 'corrupted-real-producer-value'}
                        body = json.dumps(changed).encode()
                headers = {k: v for k, v in self.headers.items()
                           if k.lower() not in {'host', 'content-length', 'connection', 'accept-encoding'}}
                with httpx.Client(trust_env=False, timeout=10) as client:
                    try:
                        response = client.request(self.command, fixture.upstream + self.path,
                                                  content=body, headers=headers)
                    except httpx.HTTPError:
                        self.send_error(502)
                        return
                if original is not None and response.is_success:
                    result = response.json()
                    assert result['offsets'] and all(type(row.get('offset')) is int
                        and row.get('error_code') is None for row in result['offsets'])
                    fixture.produces.append({'body': original, 'actual': json.loads(body), 'ack': result})
                if fixture.hold_topic and fixture.hold_topic in self.path and "/records" in self.path and response.is_success and response.json():
                    fixture.hold_topic = None
                    fixture.holding.set()
                    fixture.release.wait(10)
                self.send_response(response.status_code)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.send_header('Content-Length', str(len(response.content)))
                self.end_headers()
                try: self.wfile.write(response.content)
                except (BrokenPipeError, ConnectionResetError): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--command', required=True)
    p.add_argument('--eventing-rest-url', required=True)
    p.add_argument('--legacy-command', help='Optional accepted old binary to seed pre-cutover originals')
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    args.work = args.work.resolve()
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.work.mkdir(parents=True, exist_ok=True)
    model, replacement = Model(), Model()
    gateway = ControlledGateway(args.eventing_rest_url)
    hub = Hub(json.loads(args.command), args.work / 'hub', 'p', model.url)
    hub.config.update(server_id=uuid4().hex, threshold_ppm=5000,
        projects=[{'id': 'p', 'name': 'Project P'}, {'id': 'q', 'name': 'Project Q'}],
        agent_projects={'alice': ['p'], 'bob': ['p']},
        eventing={'enabled': True, 'rest_url': gateway.url, 'timeout_ms': 3000, 'retry_ms': 100})
    report = {'schema': 'adhd/eventing-controls-acceptance@1', 'passed': False,
              'harness_sha256': sha, 'checks': [], 'limitations': [
                  'Controlled typed model proves frozen-policy use, not model semantic quality.',
                  'Single-partition actual Kafka; no claim about replicated durability.']}
    schema = None
    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print('PASS', name, flush=True)
    def validate(name, value):
        WireValidator({'$defs': schema['$defs'], '$ref': '#/$defs/' + name}).validate(value)
    def admin(op, error=None, **fields):
        command = {'op': op, 'project_id': 'p', **fields}
        validate('admin_' + op, command)
        status, result = request(hub.base, '/admin/api', command, hub.config['admin_token'])
        if error:
            assert status == {'EVENTING_CONFLICT': 409, 'BACKPRESSURE': 503, 'PROJECT_ARCHIVED': 403}.get(error, 400) and result['error']['code'] == error, (status, result)
        else:
            assert status == 200, (status, result)
            validate('admin_result_' + op, result)
        return result
    def patch(change):
        current = request(hub.base, '/admin/api', {'op': 'config_get'}, hub.config['admin_token'])[1]
        status, result = request(hub.base, '/admin/api', {'op': 'config_update',
            'expected_revision': current['config_revision'], 'message_id': uuid4().hex,
            'confirm': True, 'patch': change}, hub.config['admin_token'])
        assert status == 200, (status, result)
        hub.config = json.loads((hub.root / 'config.json').read_text())
    def call(op, agent='alice', **fields):
        command = {'op': op, 'project_id': 'p', **fields}
        validate('agent_' + op, command)
        result = hub.call(command, agent=agent)
        validate('result_' + op, result)
        return result
    def deliveries(agent='alice'):
        return call('poll', agent=agent)['deliveries']
    def status():
        return admin('eventing_status')
    def replay(sub, publication, **extra):
        sequence = next(row['body']['records'][0]['value']['project_sequence']
                        for row in gateway.produces
                        if row['body']['records'][0]['value']['publication_id'] == publication['id'])
        return {'message_id': uuid4().hex, 'confirm': True, 'reason': 'Explicit historical fixture replay',
                'from_sequence': sequence, 'to_sequence': sequence,
                'expected_watermark': status()['replay_watermark'],
                'subscriptions': [{'id': sub['id'], 'revision': sub['revision']}], **extra}
    try:
        seed = None
        if args.legacy_command:
            config, command = hub.config, hub.command
            hub.command = json.loads(args.legacy_command)
            hub.config = {k: v for k, v in config.items()
                          if k not in {'projects', 'server_id', 'eventing', 'agent_projects'}}
            hub.start()
            seed = hub.call({'op': 'publish', 'text': 'Retained pre-cutover original'})['publication']
            config['server_id'] = hub.call({'op': 'federation_directory'})['server_id']
            hub.stop()
            hub.command, hub.config = command, config
        hub.start()
        schema = request(hub.base, '/protocol/schema')[1]
        jsonschema.Draft202012Validator.check_schema(schema)
        raw = call('subscribe', mode='raw')['subscription']
        if seed:
            assert not deliveries()
            seed_status = status()
            seed_command = {'message_id': uuid4().hex, 'confirm': True,
                'reason': 'Explicit replay of retained pre-cutover original',
                'from_sequence': seed_status['replay_watermark'], 'to_sequence': seed_status['replay_watermark'],
                'expected_watermark': seed_status['replay_watermark'],
                'subscriptions': [{'id': raw['id'], 'revision': raw['revision']}]}
            admin('replay_events', **seed_command)
            seeded = wait(lambda: deliveries(), 'Pre-cutover original could not enter real Kafka explicitly', 45)
            assert seeded[0]['publication_id'] == seed['id']
            call('ack', delivery_ids=[row['id'] for row in seeded])
            check('retained-pre-cutover-original-replays-with-original-identity-and-no-automatic-history')
        call('subscribe', mode='filtered', filter='A frozen criterion')
        gateway.blocked = True
        original = call('publish', text='Accepted behind a real unavailable Kafka gateway')['publication']
        patch({'threshold_ppm': 900000, 'matcher': {'url': replacement.url, 'model': 'replacement-model'}})
        gateway.blocked = False
        def filtered():
            rows = deliveries()
            return rows if any(reason.get('mode') == 'filtered'
                               for row in rows for reason in row['matches']) else None
        rows = wait(filtered, 'Accepted filtered job did not use frozen pre-change policy', 45)
        match = next(reason for row in rows for reason in row['matches'] if reason.get('mode') == 'filtered')
        assert match['threshold_ppm'] == 5000 and match['model'] == 'Nemotron-Deciffusion-8B-v2.1', match
        assert model.states and not replacement.states
        check('blocked-real-kafka-publication-keeps-accepted-threshold-model-and-endpoint', threshold=match['threshold_ppm'])
        call('ack', delivery_ids=[row['id'] for row in rows])

        late = call('subscribe', agent='bob', mode='raw')['subscription']
        assert not deliveries('bob')
        command = replay(late, original)
        accepted = admin('replay_events', **command)
        assert admin('replay_events', **command) == accepted
        rid = accepted['replay']['id']
        historical = wait(lambda: deliveries('bob'), 'Explicit replay did not reach late subscriber', 45)
        assert historical[0]['publication_id'] == original['id']
        assert any(reason.get('replay_id') == rid for reason in historical[0]['matches'])
        wait(lambda: admin('eventing_replay', replay_id=rid)['replay']['status'] == 'materialized', 'Replay never materialized')
        assert admin('replay_events', **command) == accepted
        admin('replay_events', error='EVENTING_CONFLICT', **{**command, 'message_id': uuid4().hex,
              'expected_watermark': command['expected_watermark'] + 1})
        admin('replay_events', error='EVENTING_CONFLICT', **{**command, 'message_id': uuid4().hex,
              'subscriptions': [{'id': late['id'], 'revision': late['revision'] + 1}]})
        call('ack', agent='bob', delivery_ids=[row['id'] for row in historical])
        again = admin('replay_events', **{**command, 'message_id': uuid4().hex})
        wait(lambda: admin('eventing_replay', replay_id=again['replay']['id'])['replay']['status'] == 'materialized', 'Second replay stalled')
        assert not deliveries('bob') and not deliveries()
        check('bounded-explicit-replay-preserves-activation-idempotency-and-acknowledgements')

        # Inject actual foreign Kafka content. It must quarantine, never become an original.
        st = status()
        with httpx.Client(trust_env=False) as client:
            response = client.post(args.eventing_rest_url.rstrip('/') + '/topics/' + st['topic'],
                headers={'Content-Type': 'application/vnd.kafka.json.v2+json', 'Accept': 'application/vnd.kafka.v2+json'},
                json={'records': [{'key': 'p', 'partition': 0, 'value': {'foreign': uuid4().hex}}]})
            response.raise_for_status()
            poison_offset = response.json()['offsets'][0]['offset']
        quarantined = wait(lambda: (value if (value := status())['quarantined'] else None), 'Foreign record did not quarantine')
        item = quarantined['quarantines'][0]
        assert item['offset'] == poison_offset
        repair = {'message_id': uuid4().hex, 'confirm': True, 'reason': 'Retry actual poison record',
                  'offset': poison_offset, 'expected_checkpoint': quarantined['next_offset'],
                  'expected_digest': item['digest'], 'action': 'retry'}
        retry = admin('repair_eventing', **repair)
        wait(lambda: status()['quarantined'] == 1, 'Retry silently discarded poison')
        assert admin('repair_eventing', **repair) == retry
        admin('repair_eventing', error='EVENTING_CONFLICT', **{**repair, 'message_id': uuid4().hex,
              'expected_digest': '0' * 64})
        reconcile = {**repair, 'message_id': uuid4().hex, 'action': 'reconcile', 'reason': 'Audited physical skip'}
        recovered = admin('repair_eventing', **reconcile)
        assert recovered['next_offset'] == poison_offset + 1
        publication = call('publish', text='Legitimate original after audited foreign-record skip')['publication']
        wait(lambda: any(row.get('publication_id') == publication['id'] for row in deliveries('bob')), 'Repair did not restore real Kafka progress', 45)
        # A corrupted physical producer record must requeue its linked backend
        # original; accepting the foreign payload or losing logical work is forbidden.
        gateway.corrupt_next = True
        linked_publication = call('publish', text='Accepted original whose physical record will be corrupted')['publication']
        linked_status = wait(lambda: (value if (value := status())['quarantined'] else None), 'Corrupted actual producer record did not quarantine', 45)
        linked_item = linked_status['quarantines'][0]
        linked_repair = {'message_id': uuid4().hex, 'confirm': True, 'reason': 'Recover accepted logical original',
            'offset': linked_item['offset'], 'expected_checkpoint': linked_status['next_offset'],
            'expected_digest': linked_item['digest'], 'action': 'reconcile'}
        admin('repair_eventing', **linked_repair)
        wait(lambda: any(row.get('publication_id') == linked_publication['id'] for row in deliveries('bob')),
             'Reconcile lost a linked accepted original instead of republishing it', 45)
        linked_produces = [row for row in gateway.produces
                           if row['body']['records'][0]['value']['publication_id'] == linked_publication['id']]
        assert len(linked_produces) >= 2
        assert linked_produces[0]['actual'] != linked_produces[0]['body']
        assert linked_produces[-1]['actual'] == linked_produces[-1]['body']
        assert linked_produces[0]['body'] == linked_produces[-1]['body']
        check('physical-corruption-repair-republishes-linked-accepted-original-with-stable-envelope')
        wait(lambda: status()['pending_events'] == 0, 'Expected durable materialization before capacity test')
        before_refusal = admin('eventing_audit', offset=0, limit=100)
        patch({'eventing': {'max_pending_events': 1}})
        gateway.blocked = True
        capacity = {**replay(late, original), 'to_sequence': status()['replay_watermark']}
        admin('replay_events', error='BACKPRESSURE', **capacity)
        assert status()['pending_events'] == 0
        assert admin('eventing_audit', offset=0, limit=100) == before_refusal
        gateway.blocked = False
        patch({'eventing': {'max_pending_events': 100000}})
        check('replay-range-admission-is-atomic-and-obeys-current-durable-backpressure')
        audit = admin('eventing_audit', offset=0, limit=100)
        assert any(row['kind'] == 'repair' and row['details'].get('missing_logical_proof') for row in audit['items'])
        check('exact-digest-retry-and-audited-reconcile-recover-real-foreign-kafka-record')
        hub.stop(hard=True)
        hub.start()
        assert admin('repair_eventing', **reconcile) == recovered
        assert admin('eventing_audit', offset=0, limit=100) == audit
        assert admin('eventing_replay', replay_id=rid)['replay']['status'] == 'materialized'
        assert not any(row.get('publication_id') == original['id'] for row in deliveries('bob'))
        check('repair-replay-audit-and-acknowledgements-survive-hard-restart')
        projects = json.loads(json.dumps(hub.config['projects']))
        projects[0]['status'] = 'archived'
        patch({'projects': projects})
        assert admin('replay_events', **command) == accepted
        admin('replay_events', error='PROJECT_ARCHIVED', **{**command, 'message_id': uuid4().hex})
        assert admin('eventing_audit', offset=0, limit=100) == audit
        check('archived-project-rejects-new-replay-and-preserves-accepted-control-idempotency')
        report['passed'] = True
        report['input_sha256'] = {Path(item).name: hashlib.sha256(Path(item).read_bytes()).hexdigest()
                                  for item in json.loads(args.command) if Path(item).is_file()}
    except BaseException as exc:
        report['failure_type'] = type(exc).__name__
        raise
    finally:
        hub.stop()
        gateway.close()
        model.close()
        replacement.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
