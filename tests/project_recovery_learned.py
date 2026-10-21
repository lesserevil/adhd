#!/usr/bin/env python3
"""Recover an actual accepted learned selection, without new model inference.

The legacy producer is an untouched copied accepted store, not fabricated state.
Its already-qualified previous recipe is selected by the public rollback API.
A process-local network fence blocks its configured model port before connect.
The profile2.1 target explicitly pauses model work; no new cohort is created.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import sys
from urllib.parse import urlsplit
from uuid import uuid4

from foundation_acceptance import Client, Runtime, free_port
from multi_support import Admin, Evidence, Fixture, arguments, scoped
from multi_workflow_upgrade import wait
from project_recovery_acceptance import Recovery, BLUE
from project_recovery_restore import offline_bundle
from project_recovery_state import canonical, digest, exact, route, snapshot


class LegacyFixture(Fixture):
    """Retain the accepted installation's existing public Admin credential."""
    def admin(self):
        if self.admin_client is None and self.config.get('admin_token'):
            self.admin_client = Admin(Client(self, self.config['admin_token']), self)
        return super().admin()


def capture(api):
    jobs, counts = [], {}
    for kind in ('history', 'retrieval', 'archive', 'replay', 'optimization'):
        rows = api({'op': 'query_jobs', 'kind': kind, 'limit': 100})['items']
        assert rows and len(rows) < 100, (kind, len(rows))
        counts[kind] = len(rows)
        for row in rows:
            assert row['kind'] == kind and row['query']['status'] != 'pending'
            identifier = row['query']['id']
            jobs.append({'kind': kind, 'id': identifier,
                'value': api({'op': 'query_job', 'query_id': identifier, 'limit': 64})})
    attempts = api({'op': 'feedback_attempts', 'offset': 0, 'limit': 64})['items']
    assert attempts and len(attempts) < 64
    labels = {a['id']: api({'op': 'feedback_attempt', 'attempt_id': a['id']}) for a in attempts}
    assert all(v['attempt']['label_revision'] > 0 for v in labels.values())
    return {'jobs': jobs, 'labels': labels, 'counts': counts,
        'cohorts': api({'op': 'feedback_cohorts', 'limit': 64}),
        'deliveries': api({'op': 'deliveries'}),
        'publications': api({'op': 'overview'})['counts']['publications']}


def compare(api, expected, allow_retired=False):
    expected = copy.deepcopy(expected)
    retired = []
    if allow_retired:
        index = api({'op': 'retrieval_index'})['index']
        generations = {index[k]['id'] for k in ('active', 'previous') if index[k] is not None}
    for row in expected['jobs']:
        actual = api({'op': 'query_job', 'query_id': row['id'], 'limit': 64})
        if (allow_retired and row['kind'] == 'optimization'
                and row['value']['query'].get('global_evidence_available') is True
                and actual['query'].get('global_evidence_available') is False):
            assert row['value']['query']['index_manifest']['id'] not in generations
            row['value']['query']['global_evidence_available'] = False
            retired.append(row['id'])
        assert exact(actual) == exact(row['value']), (row['kind'], row['id'])
    for identifier, value in expected['labels'].items():
        assert exact(api({'op': 'feedback_attempt', 'attempt_id': identifier})) == exact(value)
    assert exact(api({'op': 'feedback_cohorts', 'limit': 64})) == exact(expected['cohorts'])
    assert exact(api({'op': 'deliveries'})) == exact(expected['deliveries'])
    assert api({'op': 'overview'})['counts']['publications'] == expected['publications']
    return expected, retired


def fence(args, f, config):
    """Prove the owned interposer blocks connect, without touching the service."""
    url = config['matcher']['url']
    parsed = urlsplit(url)
    assert parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    library = f.root / 'no-provider.so'
    source = Path(__file__).with_name('project_recovery_no_provider.c')
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-O2',
        '-o', str(library), str(source), '-ldl'], check=True)
    audit = f.root / 'provider-fence.log'
    prefix = ['env', 'LD_PRELOAD=' + str(library), 'ADHD_RECOVERY_DENY_PROVIDER_PORT=' + str(port),
        'ADHD_RECOVERY_PROVIDER_FENCE_AUDIT=' + str(audit)]
    probe = ('import socket\ntry: socket.create_connection(("127.0.0.1",' + str(port) + '),1)\n'
        'except ConnectionRefusedError: pass\nelse: raise AssertionError("Provider fence was bypassed")\n')
    subprocess.run(prefix + [sys.executable, '-c', probe], check=True)
    assert audit.read_text() == 'blocked-provider-connect\n'
    return prefix, audit, digest(source.read_bytes())


async def checks(args, f, evidence):
    accepted = json.loads(args.producer_report.read_text())
    command = json.loads(args.producer_command)
    assert accepted['passed'] and not accepted.get('image')
    assert accepted['artifact_sha256'] == digest(Path(command[-1]).read_bytes())
    original_root = (args.producer_root / accepted['workdir'] / 'hub').resolve()
    config = json.loads((original_root / 'hub.json').read_text())
    store = Path(config['store_path'])
    assert store.is_relative_to(original_root)
    originals = {p.name: digest(p.read_bytes()) for p in original_root.iterdir()
        if p.is_file() and p.name.startswith(store.name)}
    assert store.name in originals and store.name + '.snapshot' in originals
    assert all(config.get(k, {}).get('url') is None for k in ('history', 'retrieval', 'archive'))
    prefix, audit, fence_hash = fence(args, f, config)
    producer = Runtime(f.root / 'accepted-producer', prefix + command)
    old_api = lambda body, mutation=False: Client(producer, producer.config['admin_token']).api(body, mutation=mutation)
    try:
        for name in originals:
            shutil.copy2(original_root / name, producer.root / name)
        config.update(store_path=str(producer.root / store.name), port=free_port())
        config['public_url'] = 'http://127.0.0.1:' + str(config['port'])
        producer.file.write_text(json.dumps(config)); producer.file.chmod(0o600)
        producer.start()
        assert str(f.root / 'no-provider.so') in Path('/proc/' + str(producer.process.pid) + '/maps').read_text(), 'Owned legacy VM did not load provider fence'
        before = old_api({'op': 'retrieval_index'})['index']
        assert before['selection']['rollback_available']
        rollback = old_api({'op': 'rollback_index', 'expected_selection_revision': before['selection']['revision']}, True)['proposal']
        settled = wait(lambda: value if (value := old_api({'op': 'index_proposal', 'proposal_id': rollback['id']})['proposal'])['status'] != 'pending' else None)
        assert settled['status'] == 'promoted' and settled['usage']['calls'] == 0
        selected = old_api({'op': 'retrieval_index'})['index']['selection']
        assert selected['applied'] and selected['qualification_current']
        assert selected['effective_recipe'] != selected['base_recipe']
        expected = capture(old_api)
        offline = Path(producer.config['store_path'])
        old_api({'op': 'config_update', 'patch': {'store_path': str(producer.root / 'moved.dets')}}, True)
        compare(old_api, expected)
        assert old_api({'op': 'retrieval_index'})['index']['selection'] == selected
        producer.stop()
        for path in producer.root.iterdir():
            if path.is_file() and path.name.startswith(offline.name):
                shutil.copy2(path, f.root / path.name)
        config = producer.config
        legacy_state = snapshot(f.root / (offline.name + '.snapshot'))
        project = config['project_id']
        assert project != BLUE
        # Retain the actual server identity from its independently verified snapshot.
        config.setdefault('server_id', legacy_state['server_id'])
        config.update(store_path=str(f.root / offline.name), port=int(f.base.rsplit(':', 1)[1]),
            public_url=f.base, matcher=None, eventing={'enabled': False},
            recovery={'backup_root': str(f.root / 'offline-backups')})
        config['optimization'] = {**config.get('optimization', {}), 'enabled': False}
        assert all(config.get(k, {}).get('url') is None for k in ('history', 'retrieval', 'archive'))
        config['projects'] = [
            {'id': project, 'name': 'Accepted legacy project', 'status': 'active', 'description': '', 'settings': {}},
            {'id': BLUE, 'name': 'Unrelated project', 'status': 'active', 'description': '', 'settings': {}}]
        config['agent_projects'] = {name: [project] for name in config['agents']}
        f.config = config; f.tokens = config['agents']
        f.file.write_text(json.dumps(config)); f.file.chmod(0o600)
        await f.start()
        r = Recovery(f, args.recovery_schema)
        assert r.status(project)['availability'] == 'ready', 'Actual legacy store was not adopted'
        api = lambda body: f.admin().call(scoped(project, **body))
        index = wait(lambda: value if (value := api({'op': 'retrieval_index'})['index'])['status'] == 'ready' else None)
        adopted = index['selection']
        for key in ('revision', 'applied', 'base_identity', 'base_recipe', 'effective_recipe', 'selected', 'previous'):
            assert adopted[key] == selected[key], key
        expected, retired = compare(api, expected, allow_retired=True)
        await r.initialize(BLUE)
        for name in ('recovery-blue-writer', 'recovery-blue-reader'):
            token = secrets.token_urlsafe(32)
            f.admin().call({'op': 'create_agent', 'agent_id': name, 'token': token, 'project_ids': [BLUE]}, mutation=True)
            f.tokens[name] = token
        writer, reader = await f.agent('recovery-blue-writer'), await f.agent('recovery-blue-reader')
        blue_before = (await writer.call(scoped(BLUE, 'publish_record', text='Independent Blue original before target backup')))['record']
        evidence.record('actual-accepted-store-adopted-with-learned-selection-and-all-five-workflow-families',
            counts=expected['counts'], labels=len(expected['labels']), retired_global_generation_ids=retired,
            paused_model=True, provider_posts=0,
            compatibility={'producer_runtime': selected['current_runtime'], 'target_runtime': adopted['current_runtime'],
                'producer_qualification_current': selected['qualification_current'], 'target_qualification_current': adopted['qualification_current'],
                'explicit_policy_change': 'matcher:null; optimization.enabled:false'})
        f.hard_stop()
        manifest, manifest_sha, retained = offline_bundle(f, r, 'accepted-learned', project=project)
        await f.start()
        writer, reader = await f.agent('recovery-blue-writer'), await f.agent('recovery-blue-reader')
        blue_newer = (await writer.call(scoped(BLUE, 'publish_record', text='Independent Blue newer original after target backup')))['record']
        acknowledged = (await writer.call(scoped(BLUE, 'send', recipient_id='recovery-blue-reader', text='Blue acknowledged after target backup')))['delivery']
        await reader.call(scoped(BLUE, 'ack', delivery_ids=[acknowledged['id']]))
        blue_expected = f.admin().call(scoped(BLUE, 'overview'))['counts']
        current_config = copy.deepcopy(f.admin().call({'op': 'config_get'})['config'])
        blue_route = copy.deepcopy(r.status(BLUE)['route'])
        _, checkpoint = route(f.file, project)
        f.hard_stop()
        held = f.root / 'held-target'; held.mkdir(mode=0o700)
        for path in (checkpoint, Path(str(checkpoint) + '.snapshot')):
            os.replace(path, held / path.name)
        await f.start()
        assert r.status(project)['availability'] == 'recovery_required'
        revision = r.revision()
        receipt = r.call(project, 'project_restore_plan', mode='restore', backup_id='accepted-learned',
            manifest_sha256=manifest_sha, allow_missing=True, expected_revision=revision, message_id=uuid4().hex)
        ready = await r.settle(project, receipt, {'ready'})
        plan = ready['plan']; r.assert_plan(plan, project, 'restore')
        apply = {'plan_id': plan['plan_id'], 'plan_sha256': plan['plan_sha256'],
            'expected_revision': revision, 'confirm': True, 'message_id': uuid4().hex}
        receipt = r.call(project, 'project_restore_apply', **apply)
        await r.settle(project, receipt, {'complete'})
        assert f.admin().call({'op': 'config_get'})['config'] == current_config
        assert r.status(BLUE)['route'] == blue_route
        assert f.admin().call(scoped(BLUE, 'overview'))['counts'] == blue_expected
        writer, reader = await f.agent('recovery-blue-writer'), await f.agent('recovery-blue-reader')
        for record in (blue_before, blue_newer):
            found = await writer.call(scoped(BLUE, 'get', publication_id=record['publication']['id']))
            assert exact(found['publication']) == exact(record['publication'])
        blue_deliveries = await reader.call(scoped(BLUE, 'poll'))
        assert acknowledged['id'] not in json.dumps(blue_deliveries), 'Target restore resurrected a newer Blue acknowledgement'
        compare(api, expected)
        restored = api({'op': 'retrieval_index'})['index']['selection']
        assert exact(restored) == exact(adopted), 'Restore changed the selected recipe or its qualification projection'
        _, checkpoint = route(f.file, project)
        actual = snapshot(str(checkpoint) + '.snapshot')
        for key in ('publications', 'subscriptions', 'deliveries', 'contexts', 'idempotency', 'sources',
                'admin_idempotency', 'history_queries', 'retrieval_queries', 'archive_queries', 'feedback', 'replay_queries',
                'optimization', 'retrieval_selection'):
            assert exact(actual[key]) == exact(retained[key]), key
        f.hard_stop(); await f.start()
        assert r.call(project, 'project_restore_apply', **apply) == receipt
        compare(api, expected)
        assert exact(api({'op': 'retrieval_index'})['index']['selection']) == exact(restored)
        evidence.record('target-only-restore-and-hard-restart-preserve-actual-selected-recipe-qualification-and-historical-evidence',
            projection_sha256=digest(canonical(expected)), source_manifest_sha256=manifest_sha,
            snapshot_sha256=manifest['snapshot']['sha256'], provider_posts=0)
    finally:
        producer.stop()
        assert originals == {name: digest((original_root / name).read_bytes()) for name in originals}
        evidence.value['producer'] = {'artifact_sha256': accepted['artifact_sha256'],
            'report_sha256': digest(args.producer_report.read_bytes()), 'original_store_sha256': originals,
            'provider_fence_source_sha256': fence_hash,
            'blocked_connects': len(audit.read_text().splitlines()), 'provider_posts': 0}


async def main(args):
    assert not args.rest_url and not args.with_model
    f = LegacyFixture(args, initialize_projects=False)
    evidence = Evidence(args.report, 'project-recovery-accepted-learned-selection')
    evidence.value['harness_sha256'] = digest(Path(__file__).read_bytes())
    if args.hub: evidence.value['artifact_sha256'] = digest(args.hub.read_bytes())
    try:
        await checks(args, f, evidence)
    except BaseException as error:
        evidence.finish(error); raise
    else:
        evidence.finish()
    finally:
        try:
            await f.close()
        finally:
            f.bind_evidence(evidence); evidence.write()


if __name__ == '__main__':
    parser = arguments(__doc__)
    parser.add_argument('--recovery-schema', type=Path, required=True)
    parser.add_argument('--producer-report', type=Path, required=True)
    parser.add_argument('--producer-root', type=Path, required=True)
    parser.add_argument('--producer-command', required=True)
    asyncio.run(main(parser.parse_args()))
