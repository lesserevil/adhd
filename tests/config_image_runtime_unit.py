"""Configuration VM dispatch and standalone ABI selection without processes."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from config_image_runtime import ConfigurationFaultRuntime
from image_filesystem_abi import selected_families, fixture
from image_filesystem_fault import SOURCES


class ConfigurationImageGuards(unittest.TestCase):
    def test_original_abi_inventory_is_unchanged(self):
        self.assertEqual(sum(map(len, selected_families().values())), 18)
        self.assertEqual(selected_families(['config_rename_fault.c']), {'config_rename_fault.c': ('rename',)})
        for names in [[], ['unknown.c'], ['config_rename_fault.c'] * 2]:
            with self.assertRaises(AssertionError):
                selected_families(names)

    def test_standalone_control_is_real_rename_input(self):
        with tempfile.TemporaryDirectory() as directory:
            control = fixture(Path(directory) / 'probe', 'config_rename_fault.c', 'rename')
            self.assertEqual(control['stage'], 'journal')
            self.assertTrue(control['source'].is_file())
            self.assertFalse(control['target'].exists())
            self.assertTrue(Path(control['environment']['ADHD_CONFIG_FAULT_ARM']).is_file())
            self.assertEqual(SOURCES['config_rename_fault.c']['exports'], {'rename'})

    def test_arm_and_exact_vm_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = ConfigurationFaultRuntime.__new__(ConfigurationFaultRuntime)
            runtime.arm = root / 'armed'
            runtime.sentinel = root / 'sentinel'
            runtime.boundary = 'config'
            calls = []
            runtime.image_runtime = SimpleNamespace(stop_at_observed_boundary=calls.append)
            self.assertFalse(runtime.observe_boundary())
            runtime.arm_mutation()
            self.assertEqual(runtime.arm.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(AssertionError):
                runtime.arm_mutation()
            trace = {'stage': 'config', 'pid': 1, 'rename_result': 0}
            runtime.sentinel.write_text(json.dumps(trace))
            self.assertTrue(runtime.observe_boundary())
            self.assertEqual(calls, [trace])
            for wrong in [dict(trace, pid=999), dict(trace, stage='journal'), dict(trace, rename_result=-1)]:
                runtime.sentinel.write_text(json.dumps(wrong))
                with self.assertRaises(AssertionError):
                    runtime.observe_boundary()
            self.assertEqual(calls, [trace])

    def test_actual_vm_exit_and_cleanup_failure_propagation(self):
        runtime = ConfigurationFaultRuntime.__new__(ConfigurationFaultRuntime)
        calls = []
        runtime.logs = [SimpleNamespace(close=lambda: calls.append('log-close'))]
        runtime.process = SimpleNamespace(returncode=137, wait=lambda **kw: calls.append('client-wait'))
        runtime.image_runtime = SimpleNamespace(last_exit_code=137, stop=lambda **kw: calls.append(kw))
        runtime.stop(hard=True)
        self.assertEqual(calls, [{'hard': True}, 'client-wait', 'log-close'])
        failure = OSError('Unconfirmed owned closure')
        def reject(**kwargs):
            raise failure
        runtime.image_runtime.stop = reject
        with self.assertRaises(OSError) as caught:
            runtime.stop()
        self.assertIs(caught.exception, failure)


if __name__ == '__main__':
    with patch('subprocess.run', side_effect=AssertionError('No process')), patch('subprocess.Popen', side_effect=AssertionError('No process')):
        unittest.main()
