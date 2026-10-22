"""Pure archive safety and provenance checks; synthetic state, no hub/DETS open."""
import hashlib
import io
import json
from pathlib import Path
import struct
import os
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace

from kafka_selective_platform import (prepare_bundle, bundle_tar, read_hub_archive,
                                     missing_target_anchor, MISSING_TARGET_SCRIPT, helper_absent)
from project_recovery_state import canonical


def etf(value):
    if isinstance(value, int):
        return b'a' + bytes([value])
    if isinstance(value, str):
        body = value.encode()
        return b'm' + struct.pack('>I', len(body)) + body
    return b't' + struct.pack('>I', len(value)) + b''.join(etf(k) + etf(v) for k, v in value.items())


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / 'hub-state.tgz'
        self.schema = Path(__file__).resolve().parents[1] / 'components/hub/project-recovery/interface.schema.json'
        self.state = {'schema': 4, 'server_id': 'c' * 32, 'project': 'project-red',
                      'route_generation': 1, 'project_epoch': 'a' * 32,
                      'allocation_epoch': 'b' * 32, 'storage_generation': 1, 'seq': 0}
        body = b'\x83' + etf(self.state)
        self.snapshot = b'ADHDSTATE\x01' + hashlib.sha256(body).digest() + body
        self.anchor = 'data/hub.dets.projects/red/g1/state.dets'

    def tearDown(self):
        self.temp.cleanup()

    def files(self):
        registry = {'schema': 1, 'config_file': '/config/hub.json', 'server_id': 'c' * 32,
                    'reserved_epochs': [], 'projects': {'project-red': {
                        'project_id': 'project-red', 'server_id': 'c' * 32, 'aliases': [],
                        'initialized': True, 'availability': 'ready', 'generation': 1,
                        'project_epoch': 'a' * 32, 'allocation_epoch': 'b' * 32,
                        'storage_anchor': '/' + self.anchor}}}
        registry['integrity_sha256'] = hashlib.sha256(canonical(registry)).hexdigest()
        identity = {'schema': 1, 'config_file': '/config/hub.json', 'server_id': 'c' * 32}
        recovery = {**identity, 'allocator_epoch': 'e' * 32, 'allocator_counter': 0,
                    'operations': {}, 'jobs': {}, 'receipts': {}, 'reserved_epochs': []}
        recovery['integrity_sha256'] = hashlib.sha256(canonical(recovery)).hexdigest()
        return {'config/hub.json': canonical({'server_id': 'c' * 32, 'config_revision': 2}),
                'config/hub.json.stores': canonical(registry),
                'config/hub.json.stores.marker': canonical(identity),
                'config/hub.json.journal': canonical({'f' * 64: {
                    'digest': 'a' * 64, 'result': {'config_revision': 2}}}),
                'config/hub.json.recovery': canonical(recovery), self.anchor: b'synthetic-checkpoint-not-opened',
                self.anchor + '.snapshot': self.snapshot}

    def write(self, files, extra=None):
        with tarfile.open(self.archive, 'w:gz') as archive:
            for name, body in files.items():
                member = tarfile.TarInfo('./' + name)
                member.size = len(body)
                archive.addfile(member, io.BytesIO(body))
            if extra:
                archive.addfile(extra, io.BytesIO(b'') if extra.isfile() else None)

    def prepare(self):
        return prepare_bundle(self.archive, self.root / 'bundle', 'c' * 32, 'project-red', self.schema)

    def test_exact_snapshot_and_config_bytes_and_private_upload(self):
        files = self.files()
        self.write(files)
        original = self.archive.read_bytes()
        proof = self.prepare()
        self.assertEqual((self.root / 'bundle/project.snapshot').read_bytes(), self.snapshot)
        self.assertEqual((self.root / 'bundle/server-config.json').read_bytes(), files['config/hub.json'])
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertEqual(len(proof['current_project_files']), 2)
        self.assertIn('config/hub.json.recovery', proof['external_journals'])
        self.assertEqual(set(proof['shared_metadata']), {name for name in files if name.startswith('config/')})
        with tarfile.open(fileobj=io.BytesIO(bundle_tar(self.root / 'bundle')), mode='r:') as upload:
            self.assertEqual(set(upload.getnames()), {'manifest.json', 'server-config.json', 'project.snapshot'})
            self.assertTrue(all(member.isfile() and member.mode == 0o600 for member in upload))

    def test_traversal_is_rejected(self):
        self.write(self.files(), tarfile.TarInfo('../escape'))
        with self.assertRaises(ValueError):
            read_hub_archive(self.archive)

    def test_link_is_rejected(self):
        link = tarfile.TarInfo('redirect')
        link.type, link.linkname = tarfile.SYMTYPE, '/config/hub.json'
        self.write(self.files(), link)
        with self.assertRaises(ValueError):
            read_hub_archive(self.archive)

    def test_duplicate_normalized_member_is_rejected(self):
        self.write(self.files(), tarfile.TarInfo('config/hub.json'))
        with self.assertRaises(ValueError):
            self.prepare()

    def test_missing_current_store_is_rejected(self):
        files = self.files()
        del files[self.anchor]
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_missing_external_journal_is_rejected(self):
        files = self.files()
        del files['config/hub.json.recovery']
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_registry_digest_is_checked(self):
        files = self.files()
        registry = json.loads(files['config/hub.json.stores'])
        registry['integrity_sha256'] = '0' * 64
        files['config/hub.json.stores'] = canonical(registry)
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_marker_is_required_and_bound_to_server_and_config(self):
        for marker in (None, b'{}', canonical({'schema': 1, 'config_file': '/other', 'server_id': 'c' * 32})):
            with self.subTest(marker=marker):
                files = self.files()
                if marker is None:
                    del files['config/hub.json.stores.marker']
                else:
                    files['config/hub.json.stores.marker'] = marker
                self.write(files)
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_recovery_journal_integrity_and_identity_are_required(self):
        for field, value in [('server_id', 'd' * 32), ('integrity_sha256', '0' * 64)]:
            with self.subTest(field=field):
                files = self.files()
                journal = json.loads(files['config/hub.json.recovery'])
                journal[field] = value
                if field != 'integrity_sha256':
                    del journal['integrity_sha256']
                    journal['integrity_sha256'] = hashlib.sha256(canonical(journal)).hexdigest()
                files['config/hub.json.recovery'] = canonical(journal)
                self.write(files)
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_active_shared_transaction_is_rejected(self):
        files = self.files()
        files['config/hub.json.transaction'] = b'{}'
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_configuration_journal_required_after_revision_one(self):
        files = self.files()
        del files['config/hub.json.journal']
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()
        files['config/hub.json'] = canonical({'server_id': 'c' * 32, 'config_revision': 1})
        self.write(files)
        self.assertNotIn('config/hub.json.journal', self.prepare()['shared_metadata'])

    def test_future_configuration_receipt_is_rejected(self):
        files = self.files()
        journal = json.loads(files['config/hub.json.journal'])
        journal['f' * 64]['result']['config_revision'] = 3
        files['config/hub.json.journal'] = canonical(journal)
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_snapshot_checksum_is_checked_before_upload(self):
        files = self.files()
        files[self.anchor + '.snapshot'] = self.snapshot[:-1] + b'x'
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_valid_checksum_cannot_authorize_foreign_snapshot(self):
        files = self.files()
        self.state['server_id'] = 'd' * 32
        body = b'\x83' + etf(self.state)
        files[self.anchor + '.snapshot'] = b'ADHDSTATE\x01' + hashlib.sha256(body).digest() + body
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_valid_registry_digest_cannot_select_outside_data_mount(self):
        files = self.files()
        registry = json.loads(files['config/hub.json.stores'])
        del registry['integrity_sha256']
        registry['projects']['project-red']['storage_anchor'] = '/config/hub.json'
        registry['integrity_sha256'] = hashlib.sha256(canonical(registry)).hexdigest()
        files['config/hub.json.stores'] = canonical(registry)
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_duplicate_config_key_is_rejected(self):
        files = self.files()
        files['config/hub.json'] = b'{"server_id":"first","server_id":"second"}'
        self.write(files)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_extra_or_nonprivate_upload_file_is_rejected(self):
        self.write(self.files())
        self.prepare()
        directory = self.root / 'bundle'
        (directory / 'extra').write_bytes(b'ignored-shadow-file')
        with self.assertRaises(ValueError):
            bundle_tar(directory)

        (directory / 'extra').unlink()
        (directory / 'manifest.json').chmod(0o644)
        with self.assertRaises(ValueError):
            bundle_tar(directory)

    def test_missing_target_selection_checks_integrity_and_foreign_aliases(self):
        raw = self.files()['config/hub.json.stores']
        self.assertEqual(missing_target_anchor(raw, 'c' * 32, 'project-red'), '/' + self.anchor)
        registry = json.loads(raw)
        registry['projects']['project-blue'] = {**registry['projects']['project-red'], 'project_id': 'project-blue'}
        del registry['integrity_sha256']
        registry['integrity_sha256'] = hashlib.sha256(canonical(registry)).hexdigest()
        with self.assertRaises(ValueError):
            missing_target_anchor(canonical(registry), 'c' * 32, 'project-red')
        with self.assertRaises(ValueError):
            missing_target_anchor(raw, 'd' * 32, 'project-red')


class StoppedLossScript(unittest.TestCase):
    """Local sh/filesystem checks only; no app, container or service starts."""
    def test_only_authoritative_helper_absence_passes(self):
        name = 'owned-helper'
        self.assertTrue(helper_absent(SimpleNamespace(returncode=1, stdout=b'[]\n', stderr=b'error: no such object: owned-helper\n'), name))
        for code, output, error in [(1,b'[]',b'Cannot connect to Docker daemon'),
                                   (1,b'[]',b'error: no such object: owned-helper\ntransport failure'),
                                   (1,b'[]',b'error: no such object: someone-else'),
                                   (1,b'[{"Id":"foreign"}]',b'error: no such object: owned-helper'),
                                   (125,b'[]',b'error: no such object: owned-helper')]:
            self.assertFalse(helper_absent(SimpleNamespace(returncode=code, stdout=output, stderr=error), name))

    def test_preserves_both_inodes_permissions_and_hashes(self):
        with tempfile.TemporaryDirectory() as name:
            anchor = Path(name) / 'state.dets'
            paths = [anchor, Path(str(anchor) + '.snapshot')]
            for path, body in zip(paths, [b'checkpoint', b'snapshot']):
                path.write_bytes(body);path.chmod(0o600)
            before = [(p.stat().st_ino, p.stat().st_mode, p.read_bytes()) for p in paths]
            result = subprocess.run(['sh', '-ec', MISSING_TARGET_SCRIPT, 'test-loss', str(anchor), '.platform-lost-test'],
                                    capture_output=True, check=True)
            self.assertEqual(len(result.stdout.splitlines()), 4)
            for path, expected in zip(paths, before):
                saved = Path(str(path) + '.platform-lost-test')
                self.assertFalse(path.exists())
                self.assertEqual((saved.stat().st_ino, saved.stat().st_mode, saved.read_bytes()), expected)

    def test_all_candidates_checked_before_any_rename(self):
        for obstruction in ('symlink', 'hardlink', 'destination'):
            with self.subTest(obstruction=obstruction), tempfile.TemporaryDirectory() as name:
                anchor = Path(name) / 'state.dets';anchor.write_bytes(b'checkpoint')
                snapshot = Path(str(anchor) + '.snapshot')
                if obstruction == 'symlink':
                    snapshot.symlink_to(anchor)
                else:
                    snapshot.write_bytes(b'snapshot')
                    if obstruction == 'hardlink':
                        os.link(snapshot, Path(name) / 'alias')
                    else:
                        Path(str(snapshot) + '.platform-lost-test').write_bytes(b'occupied')
                result = subprocess.run(['sh', '-ec', MISSING_TARGET_SCRIPT, 'test-loss', str(anchor), '.platform-lost-test'],
                                        capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(anchor.read_bytes(), b'checkpoint')
                self.assertFalse(Path(str(anchor) + '.platform-lost-test').exists())


if __name__ == '__main__':
    unittest.main()
