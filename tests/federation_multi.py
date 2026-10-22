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
from eventing_target import RuntimeTarget, add_target_arguments
import jsonschema
from jsonschema.validators import extend


def byte_bound(validator, limit, value, schema):
    if isinstance(value, str) and len(value.encode()) > limit:
        yield jsonschema.ValidationError("UTF-8 byte bound exceeded")


def integer_token(validator, enabled, value, schema):
    if enabled and (not isinstance(value, int) or isinstance(value, bool)):
        yield jsonschema.ValidationError("Integer JSON token required")


WireValidator = extend(jsonschema.Draft202012Validator, {"x-maxBytes": byte_bound,
                                                        "x-integerToken": integer_token})


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


ADMIN_TIMING_LIMIT = 256
ADMIN_PATCH_KEYS = frozenset(('projects', 'agent_projects', 'federation', 'eventing',
                             'agents', 'users', 'auth', 'resources', 'model',
                             'server_id', 'default_project_id'))


def timed_admin_request(hub, body, diagnostics, server_ordinal):
    """Observe the original request without retaining credentials or body values."""
    started = time.monotonic()
    row = {'monotonic_start': started, 'server_ordinal': server_ordinal,
           'op': body.get('op') if body.get('op') in ('config_get', 'config_update') else 'other'}
    mid = body.get('message_id')
    if isinstance(mid, str):
        row['message_id_sha256'] = hashlib.sha256(mid.encode()).hexdigest()
    patch = body.get('patch')
    if isinstance(patch, dict):
        row['patch_keys'] = sorted({key if key in ADMIN_PATCH_KEYS else '<other>' for key in patch})
    try:
        status, value = request(hub.base, '/admin/api', body, hub.config['admin_token'])
        row['status'] = status if isinstance(status, int) and not isinstance(status, bool) else None
        return status, value
    except BaseException as error:
        row['exception_type'] = type(error).__name__
        raise
    finally:
        row['duration_seconds'] = time.monotonic() - started
        if len(diagnostics['requests']) < ADMIN_TIMING_LIMIT:
            diagnostics['requests'].append(row)
        else:
            diagnostics['omitted_requests'] += 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    add_target_arguments(p)
    p.add_argument('--legacy-command', help='JSON argv for a previously accepted single-project server')
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--work', type=Path)
    p.add_argument('--eventing-rest-urls', help='JSON array of three distinct real Kafka REST services')
    args = p.parse_args()
    target = RuntimeTarget(args)
    root = args.work.resolve() if args.work else Path(tempfile.mkdtemp(prefix='adhd-federation-multi-'))
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    broker_urls = json.loads(args.eventing_rest_urls) if args.eventing_rest_urls else None
    if broker_urls is not None:
        assert len(broker_urls) == 3 and len(set(broker_urls)) == 3
    harness_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    model = Model()
    legacy = None
    hubs = []
    cases = []
    schema = None
    validated = 0
    report = {'schema': 'adhd/multi-federation-acceptance@1', 'passed': False,
              'limitations': ['Controlled model fixture qualifies transport and authority, not semantic quality.',
                              'Eventing is explicitly legacy mode; this suite does not qualify Kafka or deployments.'],
              'checks': cases, 'admin_request_timings': {'requests': [], 'omitted_requests': 0}}
    report.update(target.report())

    def record(name, **details):
        cases.append({'name': name, 'passed': True, **details})
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print('PASS', name, flush=True)

    def validate(name, value):
        nonlocal validated
        if schema is not None:
            WireValidator({'$defs': schema['$defs'], '$ref': '#/$defs/' + name}).validate(value)
            validated += 1

    def call(hub, project, op, **fields):
        body = {'op': op, 'project_id': project, **fields}
        validate('agent_' + op, body)
        result = hub.call(body)
        validate('result_' + op, result)
        return result

    def admin(hub, body):
        status, value = timed_admin_request(hub, body, report['admin_request_timings'], hubs.index(hub))
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
        validate('PeerV2_' + op, body)
        status, result = request(target.base, '/federation/v2', body, tokens[hubs.index(origin), hubs.index(target)])
        validate('PeerV2Error' if status >= 400 else 'PeerV2Result', result)
        return status, result

    def finish(hub, project, op, qid):
        def observe():
            q = call(hub, project, op, query_id=qid)['query']
            return q if q['status'] != 'pending' else None
        return wait(observe, 'Federated query did not become terminal')

    try:
        command = target.command
        if broker_urls:
            clusters = [request(url.rstrip('/'), '/v3/clusters')[1]['data'][0]['cluster_id'] for url in broker_urls]
            assert len(set(clusters)) == 3, 'Each server must have a distinct Kafka cluster'
            report['broker_cluster_ids'] = clusters
            report['limitations'] = [item for item in report['limitations'] if not item.startswith('Eventing')]
            report['limitations'].append('Kafka is exercised as independent per-server services; this suite does not qualify Kubernetes or replicated broker durability.')
        for i in range(3):
            hub = target.hub(root / f'server-{i}', 'shared', model.url)
            hub.config.update(server_id=uuid4().hex, eventing={'enabled': False},
                              projects=[{'id': name, 'name': 'Same display label', 'status': 'active',
                                         'description': 'Transport fixture', 'settings': {
                                             'federation': {'description': f'Server {i} {name} builds image decoders.',
                                                            'catalog': {'visible': True, 'entries': []}}}}
                                        for name in PROJECTS],
                              agent_projects={'alice': list(PROJECTS), 'bob': ['shared']})
            if broker_urls:
                hub.config['eventing'] = {'enabled': True, 'rest_url': broker_urls[i], 'timeout_ms': 3000, 'retry_ms': 100}
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
        schema = request(a.base, '/protocol/schema')[1]
        jsonschema.Draft202012Validator.check_schema(schema)
        descriptor = request(a.base, '/protocol')[1]
        validate('Descriptor', descriptor)
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

        if broker_urls:
            before = len(model.states)
            for index, hub in enumerate(hubs):
                call(hub, 'shared', 'subscribe', mode='raw')
                marker = f'Independent broker fixture {index} {uuid4().hex}'
                publication = call(hub, 'shared', 'publish', text=marker)['publication']
                def received(hub=hub, publication=publication):
                    return any(row.get('publication_id') == publication['id']
                               for row in call(hub, 'shared', 'poll')['deliveries'])
                wait(received, 'Own-server Kafka event did not reach its A2A subscriber')
                for other in hubs:
                    if other is not hub:
                        assert not call(other, 'shared', 'search', query=marker)['publications']
            assert len(model.states) == before
            record('three-independent-kafka-services-feed-raw-a2a-streams-with-zero-inference')


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
            validate('PeerV2_server_catalog', payload)
            status, result = request(b.base, '/federation/v2', payload, tokens[0, 1])
            validate('PeerV2Result', result)
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

        remote_scope = {'provider': 'jira', 'host': 'jira.example.invalid',
                        'tenant': 'fixture', 'resource': 'remote-canonical'}
        remote_entry = {**canonical, 'scope': remote_scope, 'aliases': ['remote-canonical']}
        projects = json.loads(json.dumps(b.config['projects']))
        projects[1]['settings']['federation']['catalog']['entries'] = [remote_entry]
        patch(b, {'projects': projects})
        def remote_known():
            rows = call(a, 'shared', 'federation_directory')['peers']
            return any(row['server_id'] == b.config['server_id'] and row['project_id'] == 'other'
                       and any(entry['scope'] == remote_scope for entry in row['catalog']) for row in rows)
        wait(remote_known, 'Remote canonical advertisement was not observed')
        initial = call(a, 'shared', 'source_query', sources=[remote_scope],
                       question='Which remote source maintains image decoders?')['query']
        remote = finish(a, 'shared', 'get_source_query', initial['id'])
        assert remote['status'] == 'completed', remote
        row = remote['results'][0]
        assert row['owner_server_id'] == b.config['server_id'] and row['owner_project_id'] == 'other'
        assert row['response']['server_id'] == b.config['server_id'] and row['response']['project_id'] == 'other'
        record('remote-canonical-source-query-uses-server-project-pair-and-v2-source-jobs')

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

        if args.legacy_command:
            legacy_command = json.loads(args.legacy_command)
            legacy = Hub(legacy_command, root / 'legacy-server', 'legacy', model.url)
            outgoing, incoming = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            legacy.config['federation']['description'] = 'Legacy project builds image decoders.'
            legacy.config['federation']['peers'] = [{'project_id': 'shared', 'url': a.base,
                'token': outgoing, 'inbound_token': incoming}]
            legacy.start()
            peers = json.loads(json.dumps(a.config['federation']['peers']))
            peers.append({'project_id': 'legacy', 'url': legacy.base,
                          'token': incoming, 'inbound_token': outgoing})
            patch(a, {'federation': {'peers': peers}})
            def legacy_ready():
                return any(row['project_id'] == 'legacy' and row['status'] == 'ready'
                           for row in call(a, 'shared', 'federation_directory')['peers'])
            wait(legacy_ready, 'New server did not observe legacy peer')
            old_query = legacy.query()
            old_done = legacy.finish(old_query['id'])
            assert old_done['status'] == 'completed' and old_done['responses'][0]['project_id'] == 'shared', old_done
            new_query = call(a, 'shared', 'federated_query', question='Which projects build image decoders?')['query']
            new_done = finish(a, 'shared', 'get_federated_query', new_query['id'])
            assert any(row['project_id'] == 'legacy' and row['matched'] for row in new_done['responses']), new_done
            record('accepted-legacy-binary-and-multi-project-server-query-in-both-directions')
            projects = json.loads(json.dumps(a.config['projects']))
            projects[0]['status'] = 'archived'
            patch(a, {'projects': projects})
            status, catalog = request(a.base, '/federation/v1', {'protocol_version': 1, 'op': 'catalog', 'origin_project_id': 'legacy'}, outgoing)
            assert status == 200 and catalog['visible'] is False and catalog['items'] == [], (status, catalog)
            before = len(model.states)
            status, value = request(a.base, '/federation', {'op': 'submit', 'origin_project_id': 'legacy',
                'query_id': uuid4().hex, 'question': 'Must not invoke a model', 'deadline_at': deadline}, outgoing)
            assert status == 403 and value['error']['code'] == 'PROJECT_ARCHIVED', (status, value)
            time.sleep(.3)
            assert len(model.states) == before
            record('archived-default-project-legacy-routes-export-no-catalog-and-reject-work')
            report['legacy_input_sha256'] = {Path(item).name: hashlib.sha256(Path(item).read_bytes()).hexdigest()
                                             for item in legacy_command if Path(item).is_file()}

        for hub in hubs + ([legacy] if legacy else []):
            hub.stop()
            stores = [path for path in hub.root.rglob('*') if path.is_file()
                      and (path.name.endswith('.dets') or path.name.endswith('.snapshot'))]
            assert stores, 'No durable stores found for credential scan'
            product = b''.join(path.read_bytes() for path in stores)
            private = list(hub.tokens.values()) + [hub.config['admin_token']]
            for peer in hub.config['federation']['peers']:
                private += [peer['token'], peer['inbound_token']]
            assert not any(secret.encode() in product for secret in private)
        record('durable-project-peer-jobs-and-caches-exclude-transport-credentials')
        report['passed'] = True
        report['input_sha256'] = {Path(item).name: hashlib.sha256(Path(item).read_bytes()).hexdigest()
                                  for item in command if Path(item).is_file()}
        report['model_requests'] = len(model.states)
        report['validated_messages'] = validated
        report['harness_sha256'] = harness_sha256
    except BaseException as error:
        report['failure_type'] = type(error).__name__
        raise
    finally:
        try:
            for hub in hubs:
                hub.stop()
            if legacy:
                legacy.stop()
            model.close()
        finally:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
