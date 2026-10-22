"""Pure custody regressions; every subprocess/resource boundary is mocked."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load('eventing_retention_compiled')
matrix = load('eventing_retention_compiled_matrix')


def running():
    return {'Id': 'cid', 'Image': 'sha256:image', 'Name': '/owned',
            'State': {'Running': True, 'Pid': 5}, 'Mounts': [],
            'HostConfig': {'PidMode': '', 'ReadonlyRootfs': True},
            'Config': {'Entrypoint': ['elixir', '/runtime/adhd/boot.exs', '/app/hub.exs']}}


class Guards(unittest.TestCase):
    def test_default_readonly_image(self):
        runtime.check_running(running(), 'sha256:image', 'cid', 'owned')
        for field, value in [('Id', 'foreign'), ('Image', 'foreign'), ('Name', '/other')]:
            row = running(); row[field] = value
            with self.assertRaises(AssertionError): runtime.check_running(row, 'sha256:image', 'cid', 'owned')

    def test_no_entrypoint_or_host_pid_escape(self):
        for key, value in [('PidMode', 'host'), ('ReadonlyRootfs', False)]:
            row = running(); row['HostConfig'][key] = value
            with self.assertRaises(AssertionError): runtime.check_running(row, 'sha256:image', 'cid', 'owned')
        row = running(); row['Config']['Entrypoint'] = ['elixir']
        with self.assertRaises(AssertionError): runtime.check_running(row, 'sha256:image', 'cid', 'owned')

    def test_protected_mounts(self):
        for target in ('/', '/app', '/app/hub.exs', '/runtime', '/runtime/adhd', '/runtime/adhd/ebin'):
            row = running(); row['Mounts'] = [{'Destination': target}]
            with self.assertRaises(AssertionError): runtime.check_running(row, 'sha256:image', 'cid', 'owned')
        row = running(); row['Mounts'] = [{'Destination': '/fixture'}]
        runtime.check_running(row, 'sha256:image', 'cid', 'owned')

    def test_kernel_executable_anchor(self):
        value = {'boot_sha256': 'a', 'build_sha256': 'b', 'inputs_sha256': 'c',
                 'beams': {'Elixir.A.beam': 'd'}, 'toolchain': {'anchors': {'/proc/self/exe': 'e'}}}
        files = runtime.cache_files(value)
        self.assertEqual(files['/proc/1/exe'], 'e')
        self.assertNotIn('/proc/self/exe', files)

    def test_image_adapter_preserves_argv_except_bound_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            custody = runtime.Custody({'docker': '/qualified/docker'}, Path(directory) / 'ledger.json')
            cls = custody.image_class(); image = cls.__new__(cls); image.name = 'owned'
            original = ['docker', 'run', '--read-only', '--memory', '768m', '--cpus', '2', '--pids-limit', '256', 'sha256:actual']
            with patch.object(runtime.RetainedImage, 'argv', return_value=list(original)), patch.object(custody, 'save'):
                result = image.argv(Path('/fixture/config.json'))
            self.assertEqual(result, ['/qualified/docker', *original[1:]])
            self.assertEqual(image.config_file, Path('/fixture/config.json'))
            self.assertEqual(custody.launches, [{'owned_name': 'owned'}])

    def test_partial_capture_never_verifies_or_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            custody = runtime.Custody({}, Path(directory) / 'ledger.json')
            image = types.SimpleNamespace(image_id=None, events=[], probe_events=[], probe_cleanup_blocked=False,
                                          identity=lambda: self.fail('identity may implicitly launch verification'))
            custody.images.append(image)
            with patch('subprocess.run', side_effect=AssertionError('no process allowed')):
                custody.save()
            self.assertEqual(json.loads(custody.ledger.read_text())['images'][0]['image_config_identity'], None)

    def test_unknown_probe_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            custody = runtime.Custody({}, Path(directory) / 'ledger.json')
            custody.images.append(types.SimpleNamespace(image_id=None, events=[], probe_events=[],
                probe_cleanup_blocked=True, stop=lambda: None))
            with self.assertRaises(AssertionError): custody.close()

    def test_requires_actual_admission_before_work_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'new'
            args = types.SimpleNamespace(repo=Path(directory), work=work, context=Path(directory),
                                         admission=Path(directory) / 'absent', admission_sha256='0' * 64,
                                         image='sha256:unknown')
            with patch('subprocess.run', side_effect=AssertionError('no resource boundary allowed')):
                with self.assertRaises(FileNotFoundError): matrix.prepare(args)
            self.assertFalse(work.exists())

    def test_fixed_original_scenario_arguments(self):
        argv = matrix.scenario_argv(Path('/private/work'), '/qualified/python', 'sha256:actual', 'http://127.0.0.1:18082')
        self.assertEqual(argv[:4], ['/qualified/python', '-I', '-B', '-c'])
        self.assertEqual(argv[argv.index('--image') + 1], 'sha256:actual')
        self.assertEqual(argv[argv.index('--eventing-rest-url') + 1], 'http://127.0.0.1:18082')
        self.assertNotIn('--command', argv)
        self.assertNotIn('--with-model', argv)
        self.assertNotIn('--deadline', argv)
        self.assertNotIn('--timeout', argv)

    def test_bootstrap_rejects_tamper_before_import(self):
        # Execute only the stdlib bootstrap prefix, as python -I would. A valid
        # self hash is deliberately supplied, but the unlisted helper is not.
        text = Path(matrix.__file__).read_text().split('\nbootstrap()\n', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); driver = work / 'driver.py'; driver.write_text(text)
            frozen = work / 'frozen'; frozen.mkdir(); (frozen / 'unlisted.py').write_text('raise RuntimeError("must not import")')
            plan = {'schema': matrix.SCHEMA, 'driver_sha256': matrix.sha(driver),
                    'frozen': {'files': {}, 'directories': []}}
            (work / 'plan.json').write_text(json.dumps(plan))
            scope = {'__file__': str(driver), '__name__': 'guard_only'}
            exec(compile(text, str(driver), 'exec'), scope)
            with self.assertRaises(AssertionError): scope['bootstrap']()


if __name__ == '__main__': unittest.main()
