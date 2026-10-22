#!/usr/bin/env python3
"""Independent all-project hot backend relocation through Admin and A2A APIs.

Runs only disposable local hubs. Every original, source retry and delivery is
created through the public protocol; no backend fixture is manufactured.
"""
import asyncio
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from multi_support import Evidence, Fixture, arguments, poll_until, scoped


async def main(args):
    if args.rest_url:
        raise ValueError('Relocation requires a disposable locally owned process')
    f = Fixture(args)
    if args.no_default:
        f.config.pop('project_id')
    evidence = Evidence(args.report, 'adhd/multi-store-relocation@1')
    evidence.value.update(artifact_sha256=hashlib.sha256(args.hub.read_bytes()).hexdigest() if args.hub else None,
                          harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          no_default=args.no_default)
    try:
        await f.start()
        admin = f.admin()
        actors = {name: await f.agent(name) for name in ('red-a', 'red-b', 'blue-a', 'blue-b', 'hidden-a')}
        pairs = [('project-red', 'red-a', 'red-b'), ('project-blue', 'blue-a', 'blue-b')]
        originals, retained, acknowledged = {}, {}, {}
        for project, sender, receiver in pairs:
            await actors[receiver].call(scoped(project, 'subscribe', mode='raw'))
            command = scoped(project, 'publish', text='Relocation retains original ' + project,
                             source={'kind': 'slack', 'id': 'move-channel', 'item_id': 'move-item'})
            mid = uuid4().hex
            result = await actors[sender].call(command, mid)
            originals[project] = (sender, command, mid, result)
            rows = await poll_until(actors[receiver], project, {result['publication']['id']}, args.deadline)
            await actors[receiver].call(scoped(project, 'ack', delivery_ids=[rows[0]['id']]))
            acknowledged[project] = rows[0]['id']
            second = (await actors[sender].call(scoped(project, 'publish', text='Unacknowledged relocation ' + project)))['publication']
            retained[project] = await poll_until(actors[receiver], project, {second['id']}, args.deadline)
        pending_job = None
        if f.model:
            f.model.mode = 'error'
            await actors['hidden-a'].call(scoped('project-hidden', 'subscribe', mode='filtered', filter='API breaking change'))
        hidden = (await actors['hidden-a'].call(scoped('project-hidden', 'publish', text='Hidden original relocation')))['publication']
        if f.model:
            end = time.monotonic() + args.deadline
            while time.monotonic() < end:
                pending = admin.call(scoped('project-hidden', 'jobs', status='pending'))['items']
                if pending:
                    pending_job = pending[0]['job_id']
                    break
                await asyncio.sleep(.05)
            assert pending_job, 'Controlled provider outage must leave a real durable semantic job'
        identity = admin.call({'op': 'config_get'})['config']['server_id']
        old_root = Path(admin.call({'op': 'config_get'})['config']['store_path'])
        project_filenames = [p.name for p in Path(str(old_root) + '.projects').glob('*.dets')]
        registry_file = Path(str(f.file) + '.stores')
        selected_sources = None
        if registry_file.exists():
            from project_recovery_state import registry
            selected_sources = [Path(entry['storage_anchor']) for entry in registry(f.file)['projects'].values() if entry['initialized']]
            assert len(selected_sources) == 3
        def destinations(anchor):
            if selected_sources is not None:
                return [Path(str(anchor) + str(path)[len(str(old_root)):]) for path in selected_sources]
            return ([anchor] if not args.no_default else []) + [Path(str(anchor) + '.projects') / name for name in project_filenames]
        evidence.record('originals-source-retries-acknowledged-and-unacknowledged-deliveries-created-in-isolated-projects')

        # A foreign destination is never overwritten, and no proposal activates.
        collision = f.root / 'foreign.dets'
        collision.write_bytes(b'foreign destination must survive\n')
        foreign_digest = hashlib.sha256(collision.read_bytes()).hexdigest()
        before = admin.call({'op': 'config_get'})['config']
        protected = destinations(collision)[0] if selected_sources is not None or args.no_default else collision
        if protected != collision:
            protected.parent.mkdir(parents=True)
            protected.write_bytes(b'foreign destination must survive\n')
        admin.call({'op': 'config_update', 'patch': {'store_path': str(collision)}}, mutation=True, expected=409)
        assert admin.call({'op': 'config_get'})['config'] == before
        assert hashlib.sha256(protected.read_bytes()).hexdigest() == foreign_digest
        evidence.record('occupied-project-destination-rejected-without-config-or-foreign-file-change')

        destination = f.root / 'relocated' / 'all.dets'
        destination.parent.mkdir()
        pid = f.process.pid
        accepted = []
        retryable = []
        writes_started = time.monotonic()
        writes_deadline = writes_started + args.deadline
        timing = {'write_deadline_seconds': args.deadline, 'retry_after_seconds': [], 'retry_count': 0}
        evidence.value['relocation_timing'] = timing
        async def concurrent_writer(project, sender):
            for n in range(8):
                command = scoped(project, 'publish', text='Concurrent move write ' + project + ' ' + str(n))
                mid = uuid4().hex
                while time.monotonic() < writes_deadline:
                    response = await asyncio.wait_for(f.raw(sender, command, mid),
                                                      timeout=max(0, writes_deadline - time.monotonic()))
                    assert time.monotonic() <= writes_deadline, 'Concurrent write acknowledgement exceeded the shared deadline'
                    value = response.json()
                    if 'error' not in value:
                        result = value['result']['message']['parts'][0]['data']
                        accepted.append((sender, project, command, mid, result))
                        break
                    assert 'CONFIG_APPLY_IN_PROGRESS' in json.dumps(value), value
                    retryable.append(project)
                    timing['retry_count'] += 1
                    retry_after = response.headers.get('Retry-After')
                    delay = float(retry_after) if retry_after and retry_after.isdecimal() else .01
                    timing['retry_after_seconds'].append(delay)
                    await asyncio.sleep(min(delay, max(0, writes_deadline - time.monotonic())))
                else:
                    raise AssertionError('Frozen project writer did not resume')
                await asyncio.sleep(.01)
        writes = [asyncio.create_task(concurrent_writer(project, sender)) for project,sender,_ in pairs]
        await asyncio.sleep(.025)
        move_started = time.monotonic()
        await asyncio.to_thread(admin.call, {'op': 'config_update', 'patch': {'store_path': str(destination)}}, mutation=True)
        timing['admin_move_ms'] = round((time.monotonic() - move_started) * 1000, 3)
        await asyncio.gather(*writes)
        timing['all_writes_ms'] = round((time.monotonic() - writes_started) * 1000, 3)
        timing['accepted_writes'] = len(accepted)
        assert time.monotonic() <= writes_deadline, 'All concurrent writes exceeded the shared deadline'
        assert len(accepted) == 16
        assert f.process.pid == pid and f.process.poll() is None
        config = admin.call({'op': 'config_get'})['config']
        assert config['store_path'] == str(destination) and config['server_id'] == identity
        expected = destinations(destination)
        assert all(p.is_file() and Path(str(p) + '.snapshot').is_file() for p in expected)
        if selected_sources is not None:
            assert all(path.is_file() for path in selected_sources)
        elif not args.no_default:
            assert old_root.is_file()
        assert not Path(str(f.file) + '.transaction').exists()
        evidence.record('every-project-writer-moves-hot-at-one-revision-without-process-restart', project_count=3)

        async def verify():
            for project, sender, receiver in pairs:
                _, command, mid, result = originals[project]
                assert await actors[sender].call(command, mid) == result
                # Source retry uses another transport ID, preserving the original.
                assert await actors[sender].call(command) == result
                assert (await actors[receiver].call(scoped(project, 'poll')))['deliveries'] == retained[project]
                assert acknowledged[project] not in {d['id'] for d in retained[project]}
                assert (await actors[sender].call(scoped(project, 'get', publication_id=result['publication']['id'])))['publication'] == result['publication']
            assert (await actors['hidden-a'].call(scoped('project-hidden', 'get', publication_id=hidden['id'])))['publication'] == hidden
            if pending_job:
                assert any(job['job_id'] == pending_job and job['status'] == 'pending'
                           for job in admin.call(scoped('project-hidden', 'jobs'))['items'])
            for sender,project,command,mid,result in accepted:
                assert await actors[sender].call(command,mid) == result
                assert (await actors[sender].call(scoped(project,'get',publication_id=result['publication']['id'])))['publication'] == result['publication']
        # Drain concurrent raw deliveries before taking the stable expected inbox.
        for project,_,receiver in pairs:
            ids = {row[4]['publication']['id'] for row in accepted if row[1] == project}
            retained[project] = await poll_until(actors[receiver], project, ids, args.deadline)
        await verify()
        evidence.record('concurrent-accepted-writes-retain-message-idempotency-and-data', accepted_count=len(accepted), retryable_busy_count=len(retryable))
        evidence.record('all-project-originals-source-idempotency-and-delivery-identities-survive-live-switch')
        after = (await actors['blue-a'].call(scoped('project-blue', 'publish', text='Accepted after every store moved')))['publication']
        await poll_until(actors['blue-b'], 'project-blue', {after['id']}, args.deadline)
        # Include the new unacknowledged item in the durable expected set.
        retained['project-blue'] = (await actors['blue-b'].call(scoped('project-blue', 'poll')))['deliveries']
        f.hard_stop()
        await f.start()
        admin = f.admin()
        assert admin.call({'op': 'config_get'})['config']['store_path'] == str(destination)
        assert admin.call({'op': 'config_get'})['config']['server_id'] == identity
        await verify()
        assert (await actors['blue-a'].call(scoped('project-blue', 'get', publication_id=after['id'])))['publication'] == after
        evidence.record('hard-restart-opens-every-relocated-project-and-preserves-postmove-accepted-write')
        if pending_job:
            f.model.mode = 'match'
            await poll_until(actors['hidden-a'], 'project-hidden', {hidden['id']}, args.deadline)
            assert any(job['job_id'] == pending_job and job['status'] == 'done'
                       for job in admin.call(scoped('project-hidden', 'jobs'))['items'])
            evidence.record('same-durable-semantic-job-survives-switch-and-restart-then-completes-after-provider-recovery')
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        try:
            await f.close()
        except BaseException as exc:
            evidence.finish(exc)
            raise
        f.bind_evidence(evidence)
        evidence.write()


if __name__ == '__main__':
    parser = arguments(__doc__)
    parser.add_argument('--no-default', action='store_true')
    asyncio.run(main(parser.parse_args()))
