"""Mutation-specific syscall witnesses; no application or process starts."""
from pathlib import Path
import tempfile
import unittest

from config_recovery import configuration_rename_after


class ConfigurationRenameWitness(unittest.TestCase):
    def test_bootstrap_cannot_satisfy_later_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace'
            target = '/owned/hub.json'
            rename = ('123 rename("/owned/staged", "' + target + '") = 0\n').encode()
            trace.write_bytes(rename)
            offset = trace.stat().st_size
            self.assertTrue(configuration_rename_after(trace, target, 0))
            self.assertFalse(configuration_rename_after(trace, target, offset))
            with trace.open('ab') as output:
                output.write(b'123 rename("/owned/other", "/owned/other-target") = 0\n')
            self.assertFalse(configuration_rename_after(trace, target, offset))
            with trace.open('ab') as output:
                output.write(rename)
            self.assertTrue(configuration_rename_after(trace, target, offset))

    def test_missing_trace_and_truncated_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace'
            self.assertFalse(configuration_rename_after(trace, '/owned/hub.json', 0))
            trace.write_bytes(b'short')
            with self.assertRaisesRegex(AssertionError, 'truncated'):
                configuration_rename_after(trace, '/owned/hub.json', 10)


if __name__ == '__main__':
    unittest.main()
