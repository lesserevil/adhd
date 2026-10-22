#!/usr/bin/env python3
"""Kill actual target-only restores at observed Linux filesystem boundaries.

All data enters through Admin/A2A, backup files are complete stopped-owner
copies, and actual Kafka carries events. The observer stops the real VM; the
harness verifies Linux stopped state before SIGKILL. No provider is used.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from uuid import uuid4

from multi_support import Evidence, Fixture, arguments, poll_until, scoped
from project_recovery_acceptance import Recovery, RED, BLUE
from project_recovery_restore import offline_bundle
from project_recovery_state import digest, exact, read_json, registry, route

STAGES = ('before-stage-snapshot', 'after-stage-snapshot', 'before-decision',
    'after-decision', 'after-decision-sync', 'after-install-snapshot',
    'after-install-checkpoint', 'after-route-selected', 'after-route-ready',
    'after-completion', 'before-cleanup', 'after-cleanup')
UNDECIDED = set(STAGES[:3])


async def stopped(f, sentinel, pending, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not sentinel.exists():
        if f.process.poll() is not None:
            raise AssertionError('Owner exited before requested filesystem boundary')
        if pending.done():
            # A receipt may return before the worker reaches the boundary.
            await pending
        await asyncio.sleep(.02)
    assert sentinel.exists(), 'Requested actual filesystem boundary was not observed'
    observed = read_json(sentinel)
    assert observed['pid'] == f.process.pid
    end = time.monotonic() + 2
    while time.monotonic() < end:
        state = Path('/proc/' + str(f.process.pid) + '/status').read_text()
        if re.search(r'^State:\s+T\b', state, re.M):
            return observed
        await asyncio.sleep(.01)
    raise AssertionError('Owner was not kernel-stopped at observed boundary')


async def publication(f, project, recipient, text):
    sender = await f.agent('bridge')
    reader = await f.agent(recipient)
    item = (await sender.call(scoped(project, 'publish_record', text=text)))['record']['publication']
    rows = await poll_until(reader, project, {item['id']}, f.args.deadline)
    return item, next(d for d in rows if d.get('publication_id') == item['id'])


async def main(args):
    if not args.hub or args.rest_url or args.with_model:
        raise ValueError('Requires an owned native Linux --hub, real Kafka, and no model')
    if args.damage_stage and args.crash_at not in {'after-decision-sync', 'after-install-snapshot'}:
        raise ValueError('Stage damage requires a decided checkpoint that has not been installed')
    f = Fixture(args, initialize_projects=False)
    if args.no_default:
        f.config.pop('project_id')
    backup_root = f.root / 'backups'
    backup_root.mkdir(mode=0o700)
    f.config['recovery'] = {'backup_root': str(backup_root)}
    if args.archived:
        f.config['projects'] = copy.deepcopy(f.config['projects'])
    source = Path(__file__).with_name('project_recovery_fault.c')
    library = f.root / 'recovery-fault.so'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-O2',
        '-o', str(library), str(source), '-ldl'], check=True)
    arm, sentinel = f.root / 'armed', f.root / 'stopped.json'
    injected = copy.copy(args)
    injected.hub = None
    injected.command = json.dumps(['env', 'LD_PRELOAD=' + str(library),
        'ADHD_RECOVERY_FAULT_STAGE=' + args.crash_at,
        'ADHD_RECOVERY_FAULT_CONFIG=' + str(f.file), 'ADHD_RECOVERY_FAULT_ROOT=' + str(f.root),
        'ADHD_RECOVERY_FAULT_ARM=' + str(arm), 'ADHD_RECOVERY_FAULT_SENTINEL=' + str(sentinel),
        'elixir', str(args.hub.resolve())])
    f.args = injected
    r = Recovery(f, args.recovery_schema)
    evidence = Evidence(args.report, 'adhd/project-recovery-process-kill@1')
    evidence.value.update(artifact_sha256=digest(args.hub.read_bytes()),
        harness_sha256=digest(Path(__file__).read_bytes()), fault_source_sha256=digest(source.read_bytes()),
        fault_library_sha256=digest(library.read_bytes()), recovery_schema_sha256=r.schema_sha256,
        crash_at=args.crash_at, no_default=args.no_default, archived=args.archived,
        damaged_stage=args.damage_stage, provider_calls=0, full_recovery_qualified=False)
    pending = None
    try:
        await f.start()
        await r.initialize(RED)
        await r.initialize(BLUE)
        red = await f.agent('red-b')
        blue = await f.agent('blue-b')
        actor = await f.agent('bridge')
        await red.call(scoped(RED, 'subscribe', mode='raw'))
        await blue.call(scoped(BLUE, 'subscribe', mode='raw'))
        original, acknowledged = await publication(f, RED, 'red-b', 'Original retained target fact')
        await red.call(scoped(RED, 'ack', delivery_ids=[acknowledged['id']]))
        private = (await actor.call(scoped(RED, 'send', recipient_id='red-b', text='Retained private target message')))['delivery']
        f.hard_stop()
        _, manifest_sha, _ = offline_bundle(f, r, 'crash-backup')
        await f.start()
        lost, _ = await publication(f, RED, 'red-b', 'Post-backup target fact must stay lost')
        newer, blue_ack = await publication(f, BLUE, 'blue-b', 'Unrelated newer fact must stay current')
        blue = await f.agent('blue-b')
        await blue.call(scoped(BLUE, 'ack', delivery_ids=[blue_ack['id']]))
        actor = await f.agent('bridge')
        blue_private = (await actor.call(scoped(BLUE, 'send', recipient_id='blue-b', text='Unrelated current private message')))['delivery']
        if args.archived:
            projects = f.admin().call({'op': 'config_get'})['config']['projects']
            for project in projects:
                if project['id'] == RED:
                    project['status'] = 'archived'
            f.admin().call({'op': 'config_update', 'patch': {'projects': projects}}, mutation=True)
        before_config = copy.deepcopy(f.admin().call({'op': 'config_get'})['config'])
        f.hard_stop()
        old_entry, anchor = route(f.file, RED)
        blue_entry, _ = route(f.file, BLUE)
        for path in (anchor, Path(str(anchor) + '.snapshot')):
            os.replace(path, path.with_name(path.name + '.lost'))
        await f.start()
        assert r.status(RED)['availability'] == 'recovery_required'
        old_entry, _ = route(f.file, RED)
        plan_receipt = r.call(RED, 'project_restore_plan', mode='restore', backup_id='crash-backup',
            manifest_sha256=manifest_sha, allow_missing=True, expected_revision=r.revision(),
            message_id=uuid4().hex)
        plan = (await r.settle(RED, plan_receipt, {'ready'}))['plan']
        r.assert_plan(plan, RED, 'restore')
        evidence.record('actual-stopped-backup-missing-target-current-blue-and-reviewed-plan',
            old_generation=old_entry['generation'], selected_generation=plan['selected']['route_generation'])
        apply = dict(plan_id=plan['plan_id'], plan_sha256=plan['plan_sha256'],
            expected_revision=r.revision(), confirm=True, message_id=uuid4().hex)
        arm.write_bytes(b'owned-ready-plan\n')
        arm.chmod(0o600)
        pending = asyncio.create_task(asyncio.to_thread(r.call, RED, 'project_restore_apply', **apply))
        observed = await stopped(f, sentinel, pending, args.deadline)
        assert observed['stage'] == args.crash_at
        decision_path = Path(str(f.file) + '.transaction')
        decided = args.crash_at not in UNDECIDED
        assert decision_path.exists() == (decided and args.crash_at != 'after-cleanup')
        journal = read_json(str(f.file) + '.recovery')
        matches = [opid for opid, job in journal['jobs'].items()
            if job['command'].get('message_id') == apply['message_id']]
        assert len(matches) == 1
        operation_id = matches[0]
        if args.crash_at in {'after-completion', 'before-cleanup', 'after-cleanup'}:
            assert journal['operations'][operation_id]['state'] == 'complete'
        f.hard_stop()
        assert f.process.returncode == -signal.SIGKILL
        try:
            await pending
        except Exception:
            pass
        pending = None
        evidence.record('real-libc-boundary-kernel-stopped-before-whole-owner-sigkill',
            stage=args.crash_at, signal='SIGKILL', observed_state='T', decision_selected=decided)
        if args.damage_stage:
            decision = read_json(decision_path)
            checkpoint = Path(decision['stage']['stage'])
            assert checkpoint.is_file() and not checkpoint.is_symlink()
            assert checkpoint.stat().st_nlink == 1
            checkpoint.unlink()
            evidence.record('owned-decided-stage-checkpoint-deliberately-lost-before-cold-start')
        f.args = args
        await f.start()
        assert exact(f.admin().call({'op': 'config_get'})['config']) == exact(before_config)
        assert route(f.file, BLUE)[0] == blue_entry
        actor, blue = await f.agent('bridge'), await f.agent('blue-b')
        assert (await actor.call(scoped(BLUE, 'get', publication_id=newer['id'])))['publication'] == newer
        blue_rows = (await blue.call(scoped(BLUE, 'poll')))['deliveries']
        assert blue_private['id'] in {d['id'] for d in blue_rows}
        assert blue_ack['id'] not in {d['id'] for d in blue_rows}
        status = r.status(RED, operation_id)
        if not decided:
            assert status['availability'] == 'recovery_required'
            assert route(f.file, RED)[0] == old_entry
            assert not anchor.exists() and not Path(str(anchor) + '.snapshot').exists()
            assert status['operation']['state'] in {'failed', 'blocked'}
            evidence.record('predecision-kill-keeps-original-missing-route-and-does-not-install-stage')
        elif args.damage_stage:
            assert status['availability'] == 'recovery_required'
            assert status['operation']['state'] == 'blocked'
            assert status['operation']['failure']['code'] == 'RECOVERY_REQUIRED'
            entry, _ = route(f.file, RED)
            assert entry['generation'] == plan['selected']['route_generation']
            assert entry['project_epoch'] == plan['selected']['project_epoch']
            assert decision_path.exists()
            evidence.record('damaged-decided-target-stays-blocked-with-original-decision-and-global-admin-blue-available')
        else:
            assert status['availability'] == 'ready' and status['operation']['state'] == 'complete'
            entry, _ = route(f.file, RED)
            assert entry['generation'] == plan['selected']['route_generation']
            assert entry['project_epoch'] == plan['selected']['project_epoch']
            assert entry['allocation_epoch'] == plan['selected']['allocation_epoch']
            assert r.call(RED, 'project_restore_apply', **apply)['operation_id'] == operation_id
            assert (await actor.call(scoped(RED, 'get', publication_id=original['id'])))['publication'] == original
            red = await f.agent('red-b')
            deliveries = (await red.call(scoped(RED, 'poll')))['deliveries']
            assert private['id'] in {d['id'] for d in deliveries}
            assert acknowledged['id'] not in {d['id'] for d in deliveries}
            assert all(d.get('publication_id') != lost['id'] for d in deliveries)
            assert not decision_path.exists()
            evidence.record('decided-kill-completes-original-plan-on-cold-start-with-original-ack-and-no-old-tail')
            if not args.archived:
                fresh, _ = await publication(f, RED, 'red-b', 'Accepted after crash recovery')
                assert fresh['id'] not in {original['id'], lost['id']}
                f.hard_stop()
                await f.start()
                actor = await f.agent('bridge')
                assert (await actor.call(scoped(RED, 'get', publication_id=fresh['id'])))['publication'] == fresh
                evidence.record('later-accepted-write-survives-another-cold-start-without-baseline-rollback')
        evidence.record('global-security-current-config-and-unrelated-newer-facts-private-delivery-and-ack-preserved')
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        if pending and not pending.done():
            if f.process and f.process.poll() is None:
                f.hard_stop()
            try:
                await pending
            except Exception:
                pass
        f.args = args
        await f.close()


if __name__ == '__main__':
    parser = arguments(__doc__)
    parser.add_argument('--recovery-schema', type=Path, default=Path('components/hub/project-recovery/interface.schema.json'))
    parser.add_argument('--crash-at', choices=STAGES, required=True)
    parser.add_argument('--no-default', action='store_true')
    parser.add_argument('--archived', action='store_true')
    parser.add_argument('--damage-stage', action='store_true')
    asyncio.run(main(parser.parse_args()))
