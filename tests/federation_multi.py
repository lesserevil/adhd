#!/usr/bin/env python3
"""Independent multi-project federation transport, routing and revocation checks.

Uses three real ADHD processes, deliberately identical project IDs, and a
controlled typed decision service. It proves protocol/authorization behavior,
not semantic quality, Kafka durability, Kubernetes operation or release readiness.
No generated modules, private stores or implementation manifests are imported.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from uuid import uuid4

from federation_acceptance import Hub, Model, request


PROJECTS = ('shared', 'other')
SCOPE = {'provider': 'github', 'host': 'github.com', 'tenant': 'fixture', 'resource': 'canonical'}


def wait(fn, message, seconds=30):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        value = fn()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--command', required=True, help='JSON argv before the serve argument')
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--work', type=Path)
    args = p.parse_args()
    root = args.work.resolve() if args.work else Path(tempfile.mkdtemp(prefix='adhd-federation-multi-'))
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    model = Model()
    hubs = []
    cases = []
    report = {'schema': 'adhd/multi-federation-acceptance@1', 'passed': False,
              'limitations': ['Controlled model fixture qualifies transport and authority, not semantic quality.',
                              'Eventing is explicitly legacy mode; this suite does not qualify Kafka or deployments.'],
              'checks': cases}

    def record(name, **details):
        cases.append({'name': name, 'passed': True, **details})
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print('PASS', name, flush=True)

    def call(hub, project, op, **fields):
        return hub.call({'op': op, 'project_id': project, **fields})

    def admin(hub, body):
        status, value = request(hub.base, '/admin/api', body, hub.config['admin_token'])
        assert status == 200, (status, value)
        return value

    def patch(hub, change):
        revision = admin(hub, {'op': 'config_get'})['config_revision']
        result = admin(hub, {'op': 'config_update', 'expected_revision': revision,
                            'message_id': uuid4().hex, 'confirm': True, 'patch': change})
        hub.config = json.loads((hub.root / 'config.json').read_text())
        return result

    def wire(origin, target, origin_project, target_project, op='catalog', **fields):
        body = {'protocol_version': 2, 'op': op, 'origin_server_id': origin.config['server_id'],
                'origin_project_id': origin_project, 'destination_project_id': target_project, **fields}
        return request(target.base, '/federation/v2', body, tokens[hubs.index(origin), hubs.index(target)])

    def finish(hub, project, op, qid):
        def observe():
            q = call(hub, project, op, query_id=qid)['query']
            return q if q['status'] != 'pending' else None
        return wait(observe, 'Federated query did not become terminal')

    try:
        command = json.loads(args.command)
        for i in range(3):
            hub = Hub(command, root / f'server-{i}', 'shared', model.url)
            hub.config.update(server_id=f'{i+1:032x}', eventing={'enabled': False},
                              projects=[{'id': name, 'name': 'Same display label', 'status': 'active',
                                         'description': 'Transport fixture', 'settings': {
                                             'federation': {'description': f'Server {i} {name} builds image decoders.',
                                                            'catalog': {'visible': True, 'entries': []}}}}
                                        for name in PROJECTS],
                              agent_projects={'alice': list(PROJECTS), 'bob': ['shared']})
            hub.config['federation']['description'] = f'Server {i} builds image decoders.'
            hub.config['federation']['catalog'] = {'visible': True, 'entries': []}
            hubs.append(hub)
        tokens = {(a, b): secrets.token_urlsafe(32) for a in range(3) for b in range(3) if a != b}
        for a, hub in enumerate(hubs):
            hub.config['federation']['peers'] = [
                {'server_id': peer.config['server_id'], 'url': peer.base,
                 'token': tokens[a, b], 'inbound_token': tokens[b, a],
                 'project_pairs': [{'local_project_id': local, 'remote_project_id': remote}
                                   for local in PROJECTS for remote in PROJECTS]}
                for b, peer in enumerate(hubs) if b != a]
        canonical = {'scope': SCOPE, 'aliases': ['canonical-fixture'], 'description': 'Canonical image decoders.',
                     'relationship': 'contained', 'canonical': True, 'export_publication_ids': []}
        hubs[0].config['projects'][1]['settings']['federation']['catalog']['entries'] = [canonical]
        for hub in hubs:
            hub.start()
        a, b, c = hubs
        descriptor = request(a.base, '/protocol')[1]
        assert descriptor['federation']['versions'] == [1, 2]
        record('three-real-servers-with-identical-project-ids-and-display-labels')

        for hub in hubs:
            for project in PROJECTS:
                def observed(hub=hub, project=project):
                    rows = call(hub, project, 'federation_directory')['peers']
                    if len(rows) == 4 and all(row['status'] == 'ready' for row in rows):
                        return rows
                rows = wait(observed, 'Expected four distinct ready server/project peers')
                assert len({(row['server_id'], row['project_id']) for row in rows}) == 4
        record('catalog-cache-identity-is-server-project-pair-without-false-conflicts')

        q = call(a, 'shared', 'federated_query', question='Which projects build image decoders?')['query']
        done = finish(a, 'shared', 'get_federated_query', q['id'])
        assert done['status'] == 'completed', done
        expected = {(hub.config['server_id'], project) for hub in (b, c) for project in PROJECTS}
        assert {(row['server_id'], row['project_id']) for row in done['responses']} == expected
        assert all(row['matched'] for row in done['responses'])
        record('asynchronous-discovery-retains-all-four-server-project-answers')

        deadline = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        for origin, project, question in [(a, 'shared', 'namespace-one'), (a, 'other', 'namespace-two'),
                                          (c, 'shared', 'namespace-three')]:
            status, result = wire(origin, b, project, 'shared', 'submit', query_id='same-query-id',
                                  question=question, deadline_at=deadline)
            assert status == 202 and result['query_id'] == 'same-query-id', (status, result)
        status, _ = wire(a, b, 'shared', 'shared', 'submit', query_id='same-query-id',
                         question='conflicting-command', deadline_at=deadline)
        assert status == 409
        status, _ = wire(a, b, 'shared', 'other', 'status', query_id='same-query-id')
        assert status == 404
        status, _ = wire(a, b, 'not-admitted', 'shared')
        assert status == 403
        forged = {'protocol_version': 2, 'op': 'catalog', 'origin_server_id': c.config['server_id'],
                  'origin_project_id': 'shared', 'destination_project_id': 'shared'}
        assert request(b.base, '/federation/v2', forged, tokens[0, 1])[0] == 403
        assert request(b.base, '/federation/v2', forged, a.tokens['alice'])[0] == 401
        record('query-id-namespace-binds-origin-server-origin-project-and-destination-project')

        # Aggregate pages are a complete authorized snapshot, not a full registry.
        body = {'protocol_version': 2, 'op': 'catalog', 'origin_server_id': a.config['server_id'],
                'origin_project_id': 'shared'}
        seen = []
        cursor = None
        revisions = set()
        for _ in range(4):
            payload = {**body, **({'cursor': cursor} if cursor else {})}
            status, result = request(b.base, '/federation/v2', payload, tokens[0, 1])
            assert status == 200 and len(result['projects']) <= 1, (status, result)
            revisions.add(result['revision'])
            seen += [row['project_id'] for row in result['projects']]
            cursor = result['next_cursor']
            if cursor is None:
                break
        assert seen == list(PROJECTS) and len(revisions) == 1 and cursor is None
        record('bounded-server-catalog-pagination-with-complete-authorized-project-snapshot')

        initial = call(a, 'shared', 'source_query', project_ids=['other'], sources=[SCOPE],
                       question='Which canonical project maintains image decoders?')['query']
        answer = finish(a, 'shared', 'get_source_query', initial['id'])
        assert answer['status'] == 'completed', answer
        row = answer['results'][0]
        assert row['status'] == 'answered' and row['owner_server_id'] == a.config['server_id']
        assert row['owner_project_id'] == 'other' and row['response']['project_id'] == 'other'
        denied = a.call({'op': 'source_query', 'project_id': 'shared', 'project_ids': ['other'],
                         'sources': [SCOPE], 'question': 'Must not cross admission'}, agent='bob', error='PROJECT_NOT_FOUND')
        record('same-server-canonical-routing-requires-explicit-frozen-admitted-project-scope')

        # A duplicate claim on this same server must conflict rather than pick one.
        projects = json.loads(json.dumps(a.config['projects']))
        projects[0]['settings']['federation']['catalog']['entries'] = [canonical]
        patch(a, {'projects': projects})
        query = call(a, 'shared', 'source_query', project_ids=['other'], sources=[SCOPE],
                     question='Check conflicting ownership')['query']
        conflict = finish(a, 'shared', 'get_source_query', query['id'])
        assert conflict['results'][0]['status'] == 'conflict', conflict
        record('duplicate-canonical-claims-across-local-projects-are-conflicts')

        peers = json.loads(json.dumps(b.config['federation']['peers']))
        for peer in peers:
            if peer['server_id'] == a.config['server_id']:
                peer['project_pairs'] = [pair for pair in peer['project_pairs']
                                         if pair['remote_project_id'] != 'other']
        pid = b.process.pid
        patch(b, {'federation': {'peers': peers}})
        assert b.process.pid == pid
        assert wire(a, b, 'other', 'shared')[0] == 403
        assert wire(a, b, 'shared', 'shared')[0] == 200
        record('live-project-pair-revocation-keeps-other-origin-grants-without-restart')

        b.stop(hard=True)
        b.start()
        assert wire(a, b, 'other', 'shared')[0] == 403
        status, result = wire(a, b, 'shared', 'shared', 'status', query_id='same-query-id')
        assert status == 200 and result['status'] in ('pending', 'completed', 'expired')
        record('hard-restart-preserves-project-pair-revocation-and-accepted-query-identity')

        for hub in hubs:
            hub.stop()
            product = (hub.root / 'hub.dets').read_bytes() + (hub.root / 'hub.dets.snapshot').read_bytes()
            private = list(hub.tokens.values()) + [hub.config['admin_token']]
            for peer in hub.config['federation']['peers']:
                private += [peer['token'], peer['inbound_token']]
            assert not any(secret.encode() in product for secret in private)
        record('durable-project-peer-jobs-and-caches-exclude-transport-credentials')
        report['passed'] = True
        report['input_sha256'] = {Path(item).name: hashlib.sha256(Path(item).read_bytes()).hexdigest()
                                  for item in command if Path(item).is_file()}
        report['model_requests'] = len(model.states)
    except BaseException as error:
        report['failure_type'] = type(error).__name__
        raise
    finally:
        for hub in hubs:
            hub.stop()
        model.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
