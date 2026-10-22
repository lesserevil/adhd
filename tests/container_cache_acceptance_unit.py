#!/usr/bin/env python3
"""Mocked cache qualification boundaries: zero Docker/compiler/app processes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location('cache', Path(__file__).with_name('container_cache_acceptance.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Guards(unittest.TestCase):
    def test_absence_identifier_case_is_strict(self):
        p = subprocess.CompletedProcess([], 1, b'[]\n', b'error: no such object: MiXeD')
        self.assertTrue(m.absent(p, 'MiXeD')); self.assertFalse(m.absent(p, 'mixed'))

    def test_daemon_or_contradictory_absence_rejected(self):
        for rc, out, err in [(2, b'[]', b'Error: No such object: x'),
                             (1, b'present', b'Error: No such object: x'),
                             (1, b'[]', b'Error: No such object: x\ndaemon unavailable')]:
            self.assertFalse(m.absent(subprocess.CompletedProcess([], rc, out, err), 'x'))

    def test_archive_preserves_root_metadata(self):
        files = {'adhd': (b'', 0o555, tarfile.DIRTYPE, ''),
                 'adhd/boot.exs': (b'boot', 0o444, tarfile.REGTYPE, '')}
        self.assertEqual(m.inspect_archive(m.archive(files)), files)

    def test_mutations_have_exact_scope(self):
        files = {'adhd/ebin/Elixir.A.beam': (b'beam', 0o444, tarfile.REGTYPE, ''),
                 'adhd/build.exs': (b'build', 0o444, tarfile.REGTYPE, ''),
                 'adhd/boot.exs': (b'boot', 0o444, tarfile.REGTYPE, ''),
                 'adhd/manifest.json': (json.dumps({'toolchain': {'elixir': '1', 'anchors': {'/proc/self/exe': 'a'}}}).encode(), 0o444, tarfile.REGTYPE, '')}
        for case in m.CASES:
            if case.startswith('missing-'):
                with self.assertRaises(AssertionError): m.mutation(files, case)
                continue
            result = m.mutation(files, case)
            difference = {k for k in set(result) | set(files) if result.get(k) != files.get(k)}
            self.assertEqual(len(difference), 0 if case == 'changed-source' else 1)
        self.assertEqual(files['adhd/boot.exs'][0], b'boot')

    def runner(self, directory):
        return m.Runner(Path(directory), {'image': 'sha256:' + 'a' * 64})

    def test_inspection_failure_attempts_independent_cleanup_and_preserves_error(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            calls = []
            runner.inspect = lambda _: (_ for _ in ()).throw(RuntimeError('daemon unavailable'))
            def command(args, **_):
                calls.append(args)
                return subprocess.CompletedProcess(args, 1 if args[0] == 'inspect' else 0, b'[]' if args[0] == 'inspect' else b'',
                    ('Error: No such object: ' + args[1]).encode() if args[0] == 'inspect' else b'')
            runner.command = command
            row = {'name': 'owned', 'container_id': 'c' * 64}
            with self.assertRaises(AssertionError): runner.close(row)
            self.assertIn(['rm', '--force', 'c' * 64], calls)
            self.assertTrue(row['observed_absent']); self.assertIn('RuntimeError', row['cleanup_errors'])

    def test_foreign_object_never_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            runner.inspect = lambda _: {'Name': '/foreign', 'Image': runner.plan['image']}
            calls = []
            def command(args, **_):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, b'[{}]', b'')
            runner.command = command
            row = {'name': 'owned', 'container_id': 'c' * 64}
            with self.assertRaises(AssertionError): runner.close(row)
            self.assertFalse(any(args[0] == 'rm' for args in calls))

    def test_fixed_socket_and_private_client_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            runner.plan['docker_socket'] = {'path': '/run/docker.sock', 'identity': [1, 2]}
            socket = MagicMock()
            socket.stat.return_value = SimpleNamespace(st_mode=m.stat.S_IFSOCK, st_dev=1, st_ino=2)
            socket.resolve.return_value = socket
            socket.__str__.return_value = '/run/docker.sock'
            with patch.object(m, 'Path', return_value=socket), patch.object(m, 'read', return_value=b'{}'), \
                 patch.dict(m.os.environ, {'DOCKER_HOST': 'tcp://untrusted', 'LD_PRELOAD': '/untrusted'}), \
                 patch.object(m.subprocess, 'run') as process:
                runner.command(['inspect', 'owned'])
                self.assertEqual(process.call_args.args[0][:3], ['/usr/bin/docker', '--host', 'unix:///run/docker.sock'])
                self.assertNotIn('DOCKER_HOST', process.call_args.kwargs['env'])
                self.assertNotIn('LD_PRELOAD', process.call_args.kwargs['env'])
                socket.stat.return_value.st_ino = 3
                process.reset_mock()
                with self.assertRaises(AssertionError): runner.command(['inspect', 'owned'])
                process.assert_not_called()

    def test_known_id_mismatch_is_foreign(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            with self.assertRaises(m.ForeignContainer):
                runner.owned({'Name': '/owned', 'Image': runner.plan['image'], 'Id': 'd' * 64},
                             {'name': 'owned', 'container_id': 'c' * 64})

    def test_true_missing_helper_is_fixed_allowlist(self):
        self.assertIn('rm -- "$1"', m.MISSING_HELPER)
        self.assertNotIn('eval ', m.MISSING_HELPER)
        self.assertIn('chmod 555 "$p"', m.MISSING_HELPER)
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory); runner.allowed_missing = {'/runtime/adhd/manifest.json'}
            with patch.object(runner, 'command', side_effect=AssertionError('must not spawn')) as command:
                with self.assertRaises(AssertionError): runner.create('bad', [], True, '/etc/passwd')
                command.assert_not_called()

    def test_once_marker_blocks_retry_before_new_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            raw = json.dumps({'image': 'sha256:' + 'a' * 64, 'artifact_sha256': 'b' * 64}).encode()
            (work / 'plan.json').write_bytes(raw)
            args = SimpleNamespace(work=work, plan_sha256=m.sha(raw))
            with patch.object(m, 'verify'), patch.object(m, 'Runner') as constructor:
                constructor.return_value.cache_snapshot.side_effect = RuntimeError('controlled first failure')
                constructor.return_value.ledger = []
                with self.assertRaises(RuntimeError): m.execute(args)
                self.assertTrue((work / 'execution.started').is_file())
                self.assertFalse(json.loads((work / 'result.json').read_bytes())['passed'])
            with patch.object(m, 'verify'), patch.object(m, 'Runner') as constructor:
                with self.assertRaises(FileExistsError): m.execute(args)
                constructor.assert_not_called()

    def test_production_control_is_nonroot_readonly(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            captured = []
            def command(args, **_):
                captured.append(args)
                return subprocess.CompletedProcess(args, 0, ('c' * 64).encode(), b'')
            runner.command = command
            runner.inspect = lambda _: {'Name': '/' + runner.ledger[-1]['name'], 'Image': runner.plan['image'], 'Id': 'c' * 64,
                'Config': {'User': '10001:10001'}, 'HostConfig': {'ReadonlyRootfs': True, 'NetworkMode': 'none', 'CapDrop': ['ALL']}}
            runner.create('production', ['["describe"]'])
            self.assertIn('--read-only', captured[0])
            self.assertNotIn('--entrypoint', captured[0])

    def test_negative_control_rootfs_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            captured = []
            def command(args, **_):
                captured.append(args)
                return subprocess.CompletedProcess(args, 0, ('c' * 64).encode(), b'')
            runner.command = command
            runner.inspect = lambda _: {'Name': '/' + runner.ledger[-1]['name'], 'Image': runner.plan['image'], 'Id': 'c' * 64,
                'Config': {'User': '10001:10001'}, 'HostConfig': {'ReadonlyRootfs': False, 'NetworkMode': 'none', 'CapDrop': ['ALL']}}
            row = runner.create('copy', ['["describe"]'], True)
            self.assertNotIn('--read-only', captured[0]); self.assertEqual(row['runtime_user'], '10001:10001')


if __name__ == '__main__': unittest.main()
