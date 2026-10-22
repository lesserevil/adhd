#!/usr/bin/env python3
"""Pure packaging checks. No Elixir, Docker, application, or compilation calls."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stage_precompile', ROOT / 'scripts/stage_container.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class Packaging(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {'Dockerfile': b'FROM pinned\n', 'hub.exs': b'admitted source\n',
                      'specification/interface.schema.json': b'{"type":"object"}\n'}
        self.helpers = {name: (ROOT / 'deploy/runtime' / name).read_bytes()
                        for name in ('build.exs', 'boot.exs')}

    def stage(self, name='context', helpers=None):
        target = self.root / name
        stage.write_context(self.files, target, self.helpers if helpers is None else helpers)
        return target

    def test_source_payload_unchanged_and_helpers_outside_app(self):
        output = self.stage()
        with tarfile.open(output / 'payload.tar') as archive:
            names = archive.getnames()
            self.assertFalse(any('boot.exs' in name or 'build.exs' in name for name in names))
            for name, data in self.files.items():
                if name != 'Dockerfile':
                    self.assertEqual(archive.extractfile('app/' + name).read(), data)
            self.assertEqual(archive.extractfile('app/manifest.json').read(),
                             (output / 'manifest.json').read_bytes())

    def test_compiler_inputs_bind_exact_helpers_and_payload(self):
        output = self.stage()
        inputs = json.loads((output / 'compiler-inputs.json').read_bytes())
        self.assertEqual(inputs['source_sha256'], hashlib.sha256(self.files['hub.exs']).hexdigest())
        self.assertEqual(inputs['payload_manifest_sha256'], hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest())
        self.assertEqual(inputs['files'], {k: hashlib.sha256(v).hexdigest() for k, v in self.helpers.items()})
        with tarfile.open(output / 'packaging.tar') as archive:
            self.assertEqual(archive.getnames(), ['packaging', 'packaging/boot.exs', 'packaging/build.exs', 'packaging/inputs.json'])
            for member in archive.getmembers():
                self.assertEqual(member.mtime, 0)
                self.assertFalse(member.issym() or member.islnk())
                if member.isfile():
                    self.assertEqual(member.mode, 0o444)

    def test_deterministic_context(self):
        a, b = self.stage('a'), self.stage('b')
        self.assertEqual(sorted(p.name for p in a.iterdir()), sorted(p.name for p in b.iterdir()))
        for path in a.iterdir():
            self.assertEqual(path.read_bytes(), (b / path.name).read_bytes())

    def test_extra_or_missing_helper_rejected(self):
        for name, helpers in [('missing', {'boot.exs': b'x'}),
                              ('extra', {**self.helpers, 'other.exs': b'x'})]:
            with self.assertRaises(SystemExit):
                self.stage(name, helpers)

    def test_helper_drift_changes_binding_without_source_change(self):
        a = self.stage('a')
        b = self.stage('b', {**self.helpers, 'boot.exs': self.helpers['boot.exs'] + b'\n'})
        self.assertEqual((a / 'payload.tar').read_bytes(), (b / 'payload.tar').read_bytes())
        self.assertNotEqual((a / 'compiler-inputs.json').read_bytes(), (b / 'compiler-inputs.json').read_bytes())

    def test_redirected_helper_rejected(self):
        real = self.root / 'real'
        real.write_bytes(b'helper')
        link = self.root / 'link'
        link.symlink_to(real)
        with self.assertRaises(SystemExit):
            stage.read_regular(link)

    def test_redirected_helper_parent_rejected(self):
        real = self.root / 'real'
        real.mkdir()
        (real / 'helper').write_bytes(b'helper')
        link = self.root / 'link'
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(SystemExit):
            stage.read_regular(link / 'helper')

    def test_production_dockerfile_requires_compiler_closure(self):
        self.files['Dockerfile'] = (ROOT / 'deploy/Dockerfile').read_bytes()
        with self.assertRaises(SystemExit):
            stage.write_context(self.files, self.root / 'missing')
        self.assertFalse((self.root / 'missing').exists())

    def test_no_context_overwrite(self):
        self.stage()
        with self.assertRaises(FileExistsError):
            self.stage()

    def test_generated_cache_has_fixed_timestamp_policy(self):
        build = self.helpers['build.exs'].decode()
        self.assertIn('File.touch!(path, 0)', build)
        self.assertIn('[wrapper, wrapper <> "/runtime", output | Path.wildcard(output <> "/**/*")]', build)
        self.assertIn('if File.exists?(wrapper), do: fail.()', build)
        self.assertGreater(build.index('File.touch!(path, 0)'), build.index('File.chmod!(output, 0o555)'))
        dockerfile = (ROOT / 'deploy/Dockerfile').read_text()
        self.assertIn('COPY --from=compiler /image-root/ /', dockerfile)
        final_stage = dockerfile.split('FROM ')[-1]
        self.assertFalse(any(line.startswith('RUN ') for line in final_stage.splitlines()))

    def test_deterministic_option_is_only_fresh_compiler_process(self):
        dockerfile = (ROOT / 'deploy/Dockerfile').read_text()
        stages = dockerfile.split('FROM ')[1:]
        self.assertEqual(len(stages), 2)
        commands = [json.loads(line.removeprefix('RUN '))
                    for line in stages[0].splitlines() if line.startswith('RUN ')]
        self.assertEqual(commands, [['env', 'ERL_COMPILER_OPTIONS=[deterministic]',
                                     'elixir', '/packaging/build.exs']])
        self.assertNotIn('ERL_COMPILER_OPTIONS', stages[1])
        self.assertEqual([line for line in stages[1].splitlines() if line.startswith('ENV ')],
                         ['ENV ERL_FLAGS="+S 2:2" HOME=/tmp'])
        self.assertEqual(dockerfile.count('ERL_COMPILER_OPTIONS'), 1)
        self.files['Dockerfile'] = dockerfile.encode()
        output = self.stage()
        manifest = json.loads((output / 'manifest.json').read_bytes())
        self.assertEqual(manifest['files']['Dockerfile'],
                         hashlib.sha256(dockerfile.encode()).hexdigest())
        inputs = json.loads((output / 'compiler-inputs.json').read_bytes())
        self.assertEqual(inputs['payload_manifest_sha256'],
                         hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest())

    def test_same_pinned_runtime_and_visible_original_argv(self):
        lines = (ROOT / 'deploy/Dockerfile').read_text().splitlines()
        bases = [line.split()[1] for line in lines if line.startswith('FROM ')]
        self.assertEqual(len(bases), 2)
        self.assertEqual(bases[0], bases[1])
        self.assertIn('@sha256:', bases[0])
        entry = json.loads(next(line.removeprefix('ENTRYPOINT ') for line in lines if line.startswith('ENTRYPOINT ')))
        self.assertEqual(entry, ['elixir', '/runtime/adhd/boot.exs', '/app/hub.exs'])
        self.assertIn('case System.argv() do', self.helpers['boot.exs'].decode())
        self.assertIn('[^source | rest] -> System.argv(rest)', self.helpers['boot.exs'].decode())


if __name__ == '__main__':
    unittest.main()
