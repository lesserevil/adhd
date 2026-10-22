#!/usr/bin/env python3
"""Independent container specification closure and immutable-input regression checks.

This tests staging construction only; real lifecycle/receipt gates remain in
stage_container.main and are independently covered by staging_acceptance.py.
"""
import hashlib
import importlib.util
import json
import os
import argparse
from unittest.mock import patch
from types import SimpleNamespace
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
        self.lock(['component.md'])

    def lock(self, names):
        references = [{'uri': name, 'kind': 'specification', 'identity': {
            'algorithm': 'sha256', 'digest': hashlib.sha256(
                (self.component / name).read_bytes()).hexdigest()}} for name in names]
        root = {'algorithm': 'sha256', 'digest': '1' * 64}
        value = {'root_revision': root, 'nodes': [{'target_flavor_selection': {
            'component_revision': root}, 'revision': {'specifications': references}}]}
        (self.component / 'component.lock.json').write_text(json.dumps(value))
        return value

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
        recovery = self.component / 'project-recovery'
        recovery.mkdir()
        payload = b'{"$id":"urn:test:recovery","type":"object"}\n'
        (recovery / 'interface.schema.json').write_bytes(payload)
        expected['specification/project-recovery/interface.schema.json'] = payload
        self.lock([name.removeprefix('specification/') for name in expected])
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
        lock = json.loads((self.component / 'component.lock.json').read_text())
        lock['nodes'][0]['revision']['specifications'].append({
            'uri': 'pipe.md', 'kind': 'specification',
            'identity': {'algorithm': 'sha256', 'digest': '0' * 64}})
        (self.component / 'component.lock.json').write_text(json.dumps(lock))
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_regular_reader_rejects_symlink_ancestor(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.component, target_is_directory=True)
        self.reject(lambda: STAGE.read_regular(alias / 'component.md'))


    def test_changed_locked_json_rejected(self):
        path = self.component / 'interface.schema.json'
        path.write_text('{"type":"object"}')
        self.lock(['component.md', path.name])
        path.write_text('{"type":"null"}')
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_declared_non_markdown_arbitrary_suffix_included(self):
        path = self.component / 'contract.data'
        path.write_bytes(b'Exact declared authority')
        self.lock(['component.md', path.name])
        self.assertEqual(STAGE.specification_files(self.component)['specification/contract.data'],
                         path.read_bytes())

    def test_missing_lock_and_missing_declared_file_rejected(self):
        (self.component / 'component.lock.json').unlink()
        self.reject(lambda: STAGE.specification_files(self.component))
        self.lock(['component.md'])
        (self.component / 'component.md').unlink()
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_duplicate_and_unsafe_locked_paths_rejected(self):
        original = self.lock(['component.md'])
        for name in ('component.md', '../outside.json', '/absolute.json',
                     './component.md', 'nested/../component.md', 'nested\\file.json'):
            lock = json.loads(json.dumps(original))
            item = dict(lock['nodes'][0]['revision']['specifications'][0])
            item['uri'] = name
            lock['nodes'][0]['revision']['specifications'].append(item)
            (self.component / 'component.lock.json').write_text(json.dumps(lock))
            with self.subTest(name=name):
                self.reject(lambda: STAGE.specification_files(self.component))

    def test_linked_declared_json_and_lock_rejected(self):
        path = self.component / 'interface.schema.json'
        path.write_text('{}')
        self.lock(['component.md', path.name])
        path.unlink()
        path.symlink_to('/etc/hostname')
        self.reject(lambda: STAGE.specification_files(self.component))
        path.unlink()
        lock = self.component / 'component.lock.json'
        lock.unlink()
        lock.symlink_to('/etc/hostname')
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_duplicate_roots_and_lock_json_fields_rejected(self):
        value = self.lock(['component.md'])
        value['nodes'].append(value['nodes'][0])
        (self.component / 'component.lock.json').write_text(json.dumps(value))
        self.reject(lambda: STAGE.specification_files(self.component))
        (self.component / 'component.lock.json').write_text('{"nodes":[],"nodes":[]}')
        self.reject(lambda: STAGE.specification_files(self.component))

    def test_explicit_cli_argv_is_used_without_shell_before_output(self):
        command = ['/selected/python', '/selected/litai']
        result = SimpleNamespace(returncode=1, stdout='', stderr='verification rejected')
        with patch.object(STAGE.subprocess, 'run', return_value=result) as run:
            with patch('sys.argv', ['stage_container.py', '--litai-command', json.dumps(command)]):
                self.reject(STAGE.main)
        run.assert_called_once_with(command + ['verify'], capture_output=True, text=True)

    def test_invalid_cli_argv_rejected(self):
        for value in ('null', '{}', '[]', '[1]', '[""]', '["bad\\u0000argument"]', 'not-json'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                STAGE.cli_command(value)


if __name__ == '__main__':
    unittest.main()
