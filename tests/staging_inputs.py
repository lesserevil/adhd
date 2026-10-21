#!/usr/bin/env python3
"""Independent container specification closure and immutable-input regression checks.

This tests staging construction only; real lifecycle/receipt gates remain in
stage_container.main and are independently covered by staging_acceptance.py.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('stage_container', ROOT / 'scripts/stage_container.py')
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)


class Inputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.component = self.root / 'hub'
        self.component.mkdir()
        (self.component / 'component.md').write_text('Canonical authority\n')

    def reject(self, callback):
        with self.assertRaises(SystemExit):
            callback()

    def test_complete_tree_exact_bytes_and_deterministic_archive(self):
        expected = {'specification/component.md': b'Canonical authority\n'}
        for name in ('multi', 'eventing', 'resources', 'storage-relocation', 'optimization'):
            folder = self.component / name
            folder.mkdir()
            content = ('Authority ' + name + '\n').encode()
            (folder / 'spec.md').write_bytes(content)
            expected['specification/' + name + '/spec.md'] = content
        (self.component / 'component.lock.json').write_text('generated, not authority')
        files = STAGE.specification_files(self.component)
        self.assertEqual(files, expected)
        files.update({'hub.exs': b'accepted artifact', 'Dockerfile': b'FROM scratch\n',
                      'core-spec.md': b'compatibility alias'})
        first, second = self.root / 'first', self.root / 'second'
        STAGE.write_context(files, first)
        STAGE.write_context(dict(reversed(list(files.items()))), second)
        for name in ('payload.tar', 'manifest.json', 'Dockerfile'):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
        manifest = json.loads((first / 'manifest.json').read_text())
        self.assertEqual(manifest['files'], {k: hashlib.sha256(v).hexdigest() for k, v in files.items()})
        with tarfile.open(first / 'payload.tar') as archive:
            for member in archive.getmembers():
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))
                self.assertEqual(member.mode, 0o755 if member.isdir() else 0o644)
                self.assertFalse(member.issym() or member.islnk())
            for name, content in files.items():
                if name != 'Dockerfile':
                    self.assertEqual(archive.extractfile('app/' + name).read(), content)
        with self.assertRaises(FileExistsError):
            STAGE.write_context(files, first)

    def test_symlink_markdown_rejected(self):
        (self.component / 'leak.md').symlink_to('/etc/hostname')
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_symlink_directory_rejected_even_when_not_followed(self):
        (self.component / 'outside').symlink_to(self.root, target_is_directory=True)
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_missing_component_authority_rejected(self):
        (self.component / 'component.md').unlink()
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_fifo_input_rejected_without_blocking(self):
        path = self.component / 'pipe.md'
        os.mkfifo(path)
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_regular_reader_rejects_symlink_ancestor(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.component, target_is_directory=True)
        self.reject(lambda: STAGE.read_regular(alias / 'component.md'))


if __name__ == '__main__':
    unittest.main()
