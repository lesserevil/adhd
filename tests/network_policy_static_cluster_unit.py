"""Mocked static CNI dependency gate; no process, compiler or network starts."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import kafka_network_policy_cluster as driver


class Dependencies(unittest.TestCase):
    def fixture(self, work):
        directory = work / 'bound/static-helper'; directory.mkdir(parents=True)
        data = bytearray(120); data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<H', data, 18, 62); struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1); struct.pack_into('<I', data, 64, 1)
        for name, body in [('tcp', bytes(data)), ('source.c', b'reviewed source'), ('route-basis.py', b'original gate'),
                           ('compile-plan.json', b'{}'), ('protocol-plan.json', b'{}')]:
            (directory / name).write_bytes(body)
        binding = {'helper_sha256': driver.sha(directory / 'tcp'), 'source_sha256': driver.sha(directory / 'source.c'),
                   'route_basis_sha256': driver.sha(directory / 'route-basis.py')}
        compile = {'passed': True, 'exit_code': 0, 'elf_sha256': binding['helper_sha256'],
            'source_sha256': binding['source_sha256'], 'elf': {'interpreter': None, 'needed': [], 'search': []},
            'plan_sha256': driver.sha(directory / 'compile-plan.json')}
        (directory / 'compile.json').write_text(json.dumps(compile))
        binding['compile_proof_sha256'] = driver.sha(directory / 'compile.json')
        protocol = {'schema': 'adhd/network-policy-static-protocol-result@1', 'passed': True,
            'image_config_identity': 'exact-image', 'helper_sha256': binding['helper_sha256'],
            'source_sha256': binding['source_sha256'], 'compile_proof_sha256': binding['compile_proof_sha256'],
            'inputs_unchanged': True, 'all_issued_containers_absent': True,
            'plan_sha256': driver.sha(directory / 'protocol-plan.json')}
        (directory / 'protocol.json').write_text(json.dumps(protocol))
        binding['protocol_proof_sha256'] = driver.sha(directory / 'protocol.json')
        return directory, {'image': 'exact-image', 'static_helper': binding}, protocol

    def test_exact_source_image_helper_and_cleanup_required(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root); directory, plan, protocol = self.fixture(work)
            self.assertTrue(driver.verify_static_helper(work, plan))
            for key, value in [('passed', False), ('image_config_identity', 'foreign'),
                               ('helper_sha256', '0' * 64), ('source_sha256', '0' * 64),
                               ('compile_proof_sha256', '0' * 64), ('inputs_unchanged', False),
                               ('all_issued_containers_absent', False), ('plan_sha256', '0' * 64)]:
                bad = copy.deepcopy(protocol); bad[key] = value
                (directory / 'protocol.json').write_text(json.dumps(bad))
                current = copy.deepcopy(plan); current['static_helper']['protocol_proof_sha256'] = driver.sha(directory / 'protocol.json')
                with self.subTest(key=key), self.assertRaises(AssertionError): driver.verify_static_helper(work, current)

    def test_actual_bound_bytes_and_route_basis_cannot_drift(self):
        for name in ('tcp', 'source.c', 'route-basis.py', 'compile.json', 'protocol-plan.json', 'compile-plan.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                work = Path(root); directory, plan, _ = self.fixture(work)
                (directory / name).write_bytes(b'changed')
                with self.assertRaises(AssertionError): driver.verify_static_helper(work, plan)


if __name__ == '__main__':
    with patch('subprocess.Popen', side_effect=AssertionError('No processes')):
        unittest.main()
