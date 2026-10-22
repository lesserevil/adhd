"""Selective platform restore fixtures from an actual stopped recovery archive.

This module never opens DETS, changes an accepted snapshot or restores a broker.
The platform runner owns service lifecycle and the private bundle upload.
"""
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
from uuid import uuid4

from multi_support import scoped, poll_until, reject
from foundation_acceptance import Client
from container_fixture import OwnedImage
from project_recovery_acceptance import Strict, RED, BLUE
from project_recovery_state import canonical, digest, snapshot
import jsonschema


def strict_json(body):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate archive metadata key')
            result[key] = value
        return result
    return json.loads(body, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def read_hub_archive(path):
    """Bound and inspect the stopped hub archive without extracting it."""
    contents, seen = {}, set()
    total = 0
    with tarfile.open(path, 'r:gz') as archive:
        for index, member in enumerate(archive):
            if index >= 10000:
                raise ValueError('Hub archive entry bound exceeded')
            name = member.name
            if name == '.':
                if not member.isdir() or name in seen:
                    raise ValueError('Invalid archive root')
                seen.add(name)
                continue
            if name.startswith('./'):
                name = name[2:]
            if member.isdir():
                name = name.rstrip('/')
            relative = PurePosixPath(name)
            if (not relative.parts or str(relative) != name or relative.is_absolute()
                    or '..' in relative.parts or name in seen):
                raise ValueError('Unsafe or duplicate archive path')
            seen.add(name)
            if not (member.isdir() or member.isfile()):
                raise ValueError('Archive links and special files are forbidden')
            if member.isfile():
                total += member.size
                if not 0 <= member.size <= 67108864 or total > 134217728:
                    raise ValueError('Hub archive byte bound exceeded')
                contents[name] = archive.extractfile(member).read()
    return contents


def archive_metadata(files, server_id):
    """Check closed shared identities before using any archived project bytes.

    This is an independent archive inspector, not a replacement for the runtime's
    complete metadata validation. The application validates the uploaded bundle.
    """
    prefix = 'config/hub.json'
    config = strict_json(files[prefix])
    identity = {'schema': 1, 'config_file': '/config/hub.json', 'server_id': server_id}
    if config.get('server_id') != server_id:
        raise ValueError('Foreign archived configuration')
    if prefix + '.transaction' in files:
        raise ValueError('Cold recovery set contains an unfinished shared decision')
    if strict_json(files.get(prefix + '.stores.marker', b'null')) != identity:
        raise ValueError('Missing or foreign storage marker')
    metadata = {}
    for suffix in ('.stores', '.recovery'):
        name = prefix + suffix
        value = strict_json(files.get(name, b'null'))
        if (not isinstance(value, dict) or any(value.get(k) != v for k, v in identity.items())
                or digest(canonical({k: v for k, v in value.items() if k != 'integrity_sha256'}))
                != value.get('integrity_sha256')):
            raise ValueError('Missing, damaged or foreign archived shared metadata')
        metadata[suffix] = value
    journal_name = prefix + '.journal'
    revision = config.get('config_revision', 1)
    if type(revision) is not int or revision < 1:
        raise ValueError('Invalid archived configuration revision')
    if journal_name not in files:
        if revision > 1:
            raise ValueError('Recovery set omits the current configuration journal')
    else:
        journal = strict_json(files[journal_name])
        if not isinstance(journal, dict):
            raise ValueError('Invalid configuration journal')
        for key, row in journal.items():
            if (not re.fullmatch('[a-f0-9]{64}', key)
                    or not isinstance(row, dict) or set(row) != {'digest', 'result'}
                    or not re.fullmatch('[a-f0-9]{64}', str(row['digest']))
                    or not isinstance(row['result'], dict)):
                raise ValueError('Invalid configuration journal receipt')
            receipt_revision = row['result'].get('config_revision', 1)
            if type(receipt_revision) is not int or not 1 <= receipt_revision <= revision:
                raise ValueError('Configuration journal receipt is newer than archive')
    names = [prefix, prefix + '.stores', prefix + '.stores.marker', prefix + '.recovery']
    if journal_name in files:
        names.append(journal_name)
    return config, metadata['.stores'], {name: digest(files[name]) for name in names}


def prepare_bundle(archive, destination, server_id, project_id, schema_file):
    """Derive the closed three-file bundle; all accepted input bytes stay intact."""
    archive, destination = Path(archive), Path(destination)
    if destination.exists() or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', destination.name):
        raise ValueError('Fresh private bundle directory with safe ID required')
    if archive.stat().st_size > 134217728:
        raise ValueError('Stopped hub archive byte bound exceeded')
    original = digest(archive.read_bytes())
    files = read_hub_archive(archive)
    configuration = files['config/hub.json']
    config, registry, shared = archive_metadata(files, server_id)
    inventory = {}
    for key, entry in registry['projects'].items():
        if key != entry['project_id'] or entry['server_id'] != server_id:
            raise ValueError('Foreign project registry entry')
        if not entry.get('initialized'):
            continue
        anchor = PurePosixPath(entry['storage_anchor'])
        if (not anchor.is_absolute() or '..' in anchor.parts or str(anchor) != entry['storage_anchor']
                or anchor.parts[:2] != ('/', 'data')):
            raise ValueError('Project store is outside the platform data mount')
        relative = str(anchor.relative_to('/'))
        for name in (relative, relative + '.snapshot'):
            if name not in files:
                raise ValueError('Recovery set omits a current project generation')
            inventory[name] = digest(files[name])
    entry = registry['projects'][project_id]
    if not entry.get('initialized') or entry.get('availability') != 'ready':
        raise ValueError('Bundle requires an initialized ready source target')
    # This external journal survives target replacement; it is not target state.
    journals = [name for name in shared if name.endswith(('.recovery', '.journal'))]
    destination.mkdir(parents=True, mode=0o700)
    raw = files[str(PurePosixPath(entry['storage_anchor']).relative_to('/')) + '.snapshot']
    snapshot_file = destination / 'project.snapshot'
    snapshot_file.write_bytes(raw)
    snapshot_file.chmod(0o600)
    state = snapshot(snapshot_file)
    try:
        if (state['schema'] != 4 or state['server_id'] != server_id or state['project'] != project_id
                or state['route_generation'] != entry['generation']
                or any(state[key] != entry[key] for key in ('project_epoch', 'allocation_epoch'))):
            raise ValueError('Snapshot headers do not match the current registered source')
        config_file = destination / 'server-config.json'
        config_file.write_bytes(configuration)
        config_file.chmod(0o600)
        manifest = {
            'schema': 'adhd/project-backup@1', 'server_id': server_id, 'project_id': project_id,
            'aliases': sorted(entry['aliases']),
            'captured_at': datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat().replace('+00:00', 'Z'),
            'source': {'route_generation': state['route_generation'], 'project_epoch': state['project_epoch'],
                       'allocation_epoch': state['allocation_epoch'], 'storage_generation': state['storage_generation'],
                       'sequence': state['seq']},
            'principal_proof': {'kind': 'configuration-v1'},
        }
        for key, name in [('snapshot', 'project.snapshot'), ('configuration', 'server-config.json')]:
            body = (destination / name).read_bytes()
            manifest[key] = {'name': name, 'bytes': len(body), 'sha256': digest(body)}
        definitions = strict_json(Path(schema_file).read_bytes())['$defs']
        Strict({'$defs': definitions, '$ref': '#/$defs/BackupManifest'},
               format_checker=jsonschema.FormatChecker()).validate(manifest)
        body = canonical(manifest)
        (destination / 'manifest.json').write_bytes(body)
        (destination / 'manifest.json').chmod(0o600)
        if digest(archive.read_bytes()) != original:
            raise ValueError('Stopped source archive changed during bundle preparation')
        return {'backup_id': destination.name, 'manifest_sha256': digest(body),
                'source_archive_sha256': original, 'source_project_epoch': state['project_epoch'],
                'source_allocation_epoch': state['allocation_epoch'],
                'current_project_files': inventory,
                'shared_metadata': shared,
                'external_journals': {name: digest(files[name]) for name in journals}}
    except BaseException:
        # Preserve the failed private preparation for diagnosis, never upload it.
        raise


def bundle_tar(directory):
    """Only these three private, regular, unlinked files enter the upload."""
    directory = Path(directory)
    if directory.is_symlink() or directory.resolve() != directory.absolute():
        raise ValueError('Bundle directory redirected')
    names = {'manifest.json', 'project.snapshot', 'server-config.json'}
    if {p.name for p in directory.iterdir()} != names:
        raise ValueError('Unexpected bundle file set')
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:') as archive:
        for name in sorted(names):
            path = directory / name
            info = path.lstat()
            if (path.is_symlink() or not path.is_file() or info.st_nlink != 1
                    or info.st_mode & 0o077 or info.st_uid != os.getuid()):
                raise ValueError('Private regular unlinked bundle files required')
            body = path.read_bytes()
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(body), 0o600
            archive.addfile(member, io.BytesIO(body))
    return output.getvalue()


def missing_target_anchor(registry_body, server_id, project_id):
    """Select only the stopped fixture's registered target; never guess a path."""
    registry = strict_json(registry_body)
    if (registry.get('schema') != 1 or registry.get('server_id') != server_id
            or registry.get('config_file') != '/config/hub.json'
            or digest(canonical({k: v for k, v in registry.items() if k != 'integrity_sha256'}))
            != registry.get('integrity_sha256')):
        raise ValueError('Invalid stopped registry identity or integrity')
    entry = registry['projects'][project_id]
    anchor = entry['storage_anchor']
    if (entry['server_id'] != server_id or entry['project_id'] != project_id
            or entry['availability'] != 'ready' or entry['initialized'] is not True
            or not re.fullmatch(r'/data/[a-zA-Z0-9_./-]+', anchor)
            or str(PurePosixPath(anchor)) != anchor or '..' in PurePosixPath(anchor).parts):
        raise ValueError('Target must be an owned ready initialized data path')
    targets = {anchor, anchor + '.snapshot'}
    for key, other in registry['projects'].items():
        if key != other['project_id'] or other['server_id'] != server_id:
            raise ValueError('Foreign registry route')
        if key != project_id and targets & {other['storage_anchor'], other['storage_anchor'] + '.snapshot'}:
            raise ValueError('Target aliases another project file')
    return anchor


def helper_absent(result, name):
    return OwnedImage.probe_absence(result, name)


# Runs only while the actual hub is stopped, in an unprivileged helper
# with the hub's data mount. Preserve both files, including inode/mode/owner/hash;
# no broker volume is mounted. Check BOTH candidates before the first rename.
MISSING_TARGET_SCRIPT = r'''
set -efu
loss_anchor="$1"; loss_suffix="$2"
case "$loss_suffix" in .platform-lost-*) ;; *) exit 71;; esac
for loss_file in "$loss_anchor" "$loss_anchor.snapshot"; do
  test "$(readlink -f "$loss_file")" = "$loss_file"
  test -f "$loss_file"
  test ! -L "$loss_file"
  test "$(stat -c %u "$loss_file")" = "$(id -u)"
  test "$(stat -c %h "$loss_file")" = 1
  test ! -e "$loss_file$loss_suffix"
  test ! -L "$loss_file$loss_suffix"
done
loss_checkpoint_identity=$(stat -c '%d:%i:%u:%g:%a:%s' "$loss_anchor")
loss_snapshot_identity=$(stat -c '%d:%i:%u:%g:%a:%s' "$loss_anchor.snapshot")
loss_checkpoint_hash=$(sha256sum "$loss_anchor"); loss_checkpoint_hash=${loss_checkpoint_hash%% *}
loss_snapshot_hash=$(sha256sum "$loss_anchor.snapshot"); loss_snapshot_hash=${loss_snapshot_hash%% *}
mv "$loss_anchor" "$loss_anchor$loss_suffix"
mv "$loss_anchor.snapshot" "$loss_anchor.snapshot$loss_suffix"
test "$(stat -c '%d:%i:%u:%g:%a:%s' "$loss_anchor$loss_suffix")" = "$loss_checkpoint_identity"
test "$(stat -c '%d:%i:%u:%g:%a:%s' "$loss_anchor.snapshot$loss_suffix")" = "$loss_snapshot_identity"
test "$(sha256sum "$loss_anchor$loss_suffix" | cut -d ' ' -f1)" = "$loss_checkpoint_hash"
test "$(sha256sum "$loss_anchor.snapshot$loss_suffix" | cut -d ' ' -f1)" = "$loss_snapshot_hash"
test ! -e "$loss_anchor"
test ! -L "$loss_anchor"
test ! -e "$loss_anchor.snapshot"
test ! -L "$loss_anchor.snapshot"
printf '%s\n' "$loss_checkpoint_hash" "$loss_snapshot_hash" "$loss_checkpoint_identity" "$loss_snapshot_identity"
'''


async def exercise_selective_restore(fixture, recovery, bundle, broker_end, vm_identity, evidence,
                                     lose_target, group_offset, sensitive_values):
    """Restore Red while newer Blue/security/broker state stays current."""
    admin = fixture.admin()
    red, reader = await fixture.agent('red-a'), await fixture.agent('red-b')
    blue, blue_reader = await fixture.agent('blue-a'), await fixture.agent('blue-b')
    discarded = (await red.call(scoped(RED, 'publish', text='Selective restore discarded Red ' + uuid4().hex)))['publication']
    await poll_until(reader, RED, {discarded['id']}, fixture.args.deadline)
    current_blue = (await blue.call(scoped(BLUE, 'publish', text='Selective restore current Blue ' + uuid4().hex)))['publication']
    rows = await poll_until(blue_reader, BLUE, {current_blue['id']}, fixture.args.deadline)
    acknowledged = [row for row in rows if row.get('publication_id') == current_blue['id']]
    assert len(acknowledged) == 1
    await blue_reader.call(scoped(BLUE, 'ack', delivery_ids=[acknowledged[0]['id']]))
    private = (await blue.call(scoped(BLUE, 'send', recipient_id='blue-b', text='Current Blue private queue')))['delivery']
    blue_pending = (await blue_reader.call(scoped(BLUE, 'poll')))['deliveries']
    assert any(row['id'] == private['id'] for row in blue_pending)
    config = admin.call({'op': 'config_get'})['config']
    different = 601 if config['resources']['max_waiters'] != 601 else 602
    admin.call({'op': 'config_update', 'patch': {'resources': {'max_waiters': different}}}, mutation=True)
    # This account is absent from the older backup and must remain present.
    viewer_password = uuid4().hex + uuid4().hex
    sensitive_values.append(viewer_password)
    admin.call({'op': 'save_user', 'user': {
        'username': 'platform-current-viewer', 'name': 'Current platform security',
        'email': 'platform-current@example.invalid', 'password': viewer_password,
        'role': 'Viewer', 'project_ids': [BLUE]}}, mutation=True)
    config = admin.call({'op': 'config_get'})['config']
    blue_route = recovery.status(BLUE)['route']
    old_red = admin.call(scoped(RED, 'eventing_status'))
    blue_status = admin.call(scoped(BLUE, 'eventing_status'))
    old_red_end, blue_end = broker_end(old_red['topic']), broker_end(blue_status['topic'])
    assert blue_status['next_offset'] == blue_end
    assert group_offset(blue_status['topic'], blue_end) == blue_end
    # Fault setup may restart the hub, but it must leave all other services and
    # current metadata intact. Measure the no-restart restore claim only AFTER
    # the missing registered target is visible on the replacement runtime.
    fixture = await lose_target()
    recovery.f = fixture
    assert recovery.status(RED)['availability'] == 'recovery_required'
    live_vm = vm_identity()
    receipt = recovery.call(RED, 'project_restore_plan', backup_id=bundle['backup_id'],
        manifest_sha256=bundle['manifest_sha256'], expected_revision=recovery.revision(),
        message_id=uuid4().hex, allow_missing=True)
    plan = (await recovery.settle(RED, receipt, {'ready'}))['plan']
    recovery.assert_plan(plan, RED, 'restore')
    assert plan['target']['availability'] == 'missing'
    assert plan['selected']['project_epoch'] != bundle['source_project_epoch']
    assert plan['selected']['allocation_epoch'] != bundle['source_allocation_epoch']
    assert plan['selected']['topic'] != old_red['topic']
    fields = dict(plan_id=plan['plan_id'], plan_sha256=plan['plan_sha256'],
                  expected_revision=recovery.revision(), confirm=True, message_id=uuid4().hex)
    accepted = recovery.call(RED, 'project_restore_apply', **fields)
    complete = await recovery.settle(RED, accepted, {'complete'})
    assert complete['result']['transport_discontinuity'] is True
    assert complete['result']['initialized'] is False
    assert recovery.call(RED, 'project_restore_apply', **fields) == accepted
    assert vm_identity() == live_vm, 'Selective restore restarted the actual hub VM'
    state = {'config': config, 'blue_route': blue_route, 'blue_publication': current_blue,
             'blue_pending': blue_pending, 'blue_acked': acknowledged[0]['id'],
             'blue_topic': blue_status['topic'], 'blue_end': blue_end,
             'blue_next_offset': blue_status['next_offset'],
             'discarded_red': discarded['id'], 'old_red_topic': old_red['topic'],
             'old_red_end': old_red_end, 'restored_red_topic': plan['selected']['topic'],
             'restored_red_epoch': plan['selected']['project_epoch']}
    # Kept solely in the private process state; never serialized in evidence.
    state['viewer_password'] = viewer_password
    state['restored_allocation_epoch'] = plan['selected']['allocation_epoch']
    await verify_selective_restore(fixture, recovery, state, broker_end)
    evidence.record('selective-red-restore-preserves-current-blue-security-and-broker-without-vm-restart',
        old_red_log_unchanged=True, blue_ack_and_private_queue_unchanged=True,
        backup_manifest_sha256=bundle['manifest_sha256'], source_archive_sha256=bundle['source_archive_sha256'])
    return state


def verify_viewer_access(fixture, password):
    viewer = Client(fixture)
    user = viewer.login('platform-current-viewer', password)
    assert user['role'] == 'Viewer'
    assert user['project_ids'] == [BLUE]
    assert [p['id'] for p in viewer.api({'op': 'list_projects'})['projects']] == [BLUE]
    viewer.api(scoped(BLUE, 'overview'))
    # Event recovery status is explicitly Admin-only. Preserve both the
    # current account's permitted project reads and its authorization limits.
    viewer.api(scoped(BLUE, 'eventing_status'), expected=403)
    viewer.api(scoped(RED, 'overview'), expected=404)


async def verify_selective_restore(fixture, recovery, state, broker_end):
    admin = fixture.admin()
    red, reader = await fixture.agent('red-a'), await fixture.agent('red-b')
    blue, blue_reader = await fixture.agent('blue-a'), await fixture.agent('blue-b')
    assert admin.call({'op': 'config_get'})['config'] == state['config']
    verify_viewer_access(fixture, state['viewer_password'])
    assert recovery.status(BLUE)['route'] == state['blue_route']
    assert (await blue.call(scoped(BLUE, 'get', publication_id=state['blue_publication']['id'])))['publication'] == state['blue_publication']
    pending = (await blue_reader.call(scoped(BLUE, 'poll')))['deliveries']
    assert pending == state['blue_pending']
    assert not any(row['id'] == state['blue_acked'] for row in pending)
    reject(await fixture.raw('red-a', scoped(RED, 'get', publication_id=state['discarded_red'])), code='NOT_FOUND')
    reject(await fixture.raw('blue-a', scoped(RED, 'get', publication_id=state['discarded_red'])))
    red_status = admin.call(scoped(RED, 'eventing_status'))
    blue_status = admin.call(scoped(BLUE, 'eventing_status'))
    assert red_status['topic'] == state['restored_red_topic']
    assert recovery.status(RED)['route']['project_epoch'] == state['restored_red_epoch']
    assert recovery.status(RED)['route']['allocation_epoch'] == state['restored_allocation_epoch']
    assert blue_status['topic'] == state['blue_topic']
    assert blue_status['next_offset'] == state['blue_next_offset']
    assert broker_end(state['old_red_topic']) == state['old_red_end']
    assert broker_end(state['blue_topic']) == state['blue_end']
