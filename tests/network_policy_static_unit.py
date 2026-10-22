"""Pure preparation checks; no compiler, sockets, containers or cluster operations."""
import ast
import copy
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import kafka_network_policy as gate
import network_policy_static as helper


class StaticFixture(unittest.TestCase):
    def test_complete_nine_pod_security_and_resource_conservation(self):
        for name, role in {**gate.PODS, **gate.PEERS}.items():
            namespace = 'adhd-netpol-unit' + ('-peer' if name in gate.PEERS else '')
            original = gate.pod(name, role, namespace, 'same-immutable-tag')
            self.assertEqual(gate.fixture_pod(name, role, namespace, 'same-immutable-tag'), original)
            actual = gate.fixture_pod(name, role, namespace, 'same-immutable-tag', True)
            expected = copy.deepcopy(original)
            expected['spec']['containers'][0]['command'] = [helper.PATH, 'serve']
            expected['spec']['containers'][0]['volumeMounts'] = [{'name': helper.NAME, 'mountPath': '/policy-helper', 'readOnly': True}]
            expected['spec']['volumes'] = [{'name': helper.NAME, 'configMap': {'name': helper.NAME, 'defaultMode': 0o555, 'items': [{'key': 'tcp', 'path': 'tcp'}]}}]
            self.assertEqual(actual, expected)
            helper.verify_mount(actual, expected)
            for field, value in [('readOnly', False), ('mountPath', '/foreign')]:
                bad = copy.deepcopy(actual); bad['spec']['containers'][0]['volumeMounts'][0][field] = value
                with self.assertRaises(AssertionError): helper.verify_mount(bad, expected)
        self.assertEqual(len(gate.PODS) + len(gate.PEERS), 9)

    def test_foreign_mount_shadow_and_service_account_mount(self):
        expected = gate.fixture_pod('hub', 'hub', 'adhd-netpol-unit', 'tag', True)
        actual = copy.deepcopy(expected)
        actual['spec']['containers'][0]['volumeMounts'].append({
            'name': 'service-account', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True})
        helper.verify_mount(actual, expected)
        for path in ('/policy-helper/tcp', '/policy-helper', '/', '/policy-helper/child',
                     '/other/../policy-helper/tcp', '//policy-helper/tcp'):
            bad = copy.deepcopy(expected)
            bad['spec']['containers'][0]['volumeMounts'].append({'name': 'foreign', 'mountPath': path})
            with self.subTest(path=path), self.assertRaises(AssertionError):
                helper.verify_mount(bad, expected)

    def test_atime_only_change_is_not_source_mutation(self):
        fields = ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns')
        base = dict(zip(('st_' + x for x in fields), range(len(fields))))
        before = SimpleNamespace(**base, st_atime_ns=1)
        after = SimpleNamespace(**base, st_atime_ns=2)
        self.assertEqual(helper.identity(before), helper.identity(after))
        for field in ('st_mtime_ns', 'st_ctime_ns', 'st_size', 'st_ino'):
            changed = dict(base); changed[field] += 1
            self.assertNotEqual(helper.identity(before), helper.identity(SimpleNamespace(**changed, st_atime_ns=2)))

    def test_all_original_routes_and_command_boundaries(self):
        routes = gate.ROUTES + gate.CROSS_ROUTES
        self.assertEqual(len(routes), 18)
        self.assertEqual(sum(r[3] for r in routes), 5)
        self.assertEqual(sum(not r[3] for r in routes), 13)
        self.assertEqual(gate.probe_command('10.0.0.2', 8082), ['elixir', '-e', gate.PROBE, '--', '10.0.0.2', '8082'])
        self.assertEqual(gate.probe_command('10.0.0.2', 8082, True), [helper.PATH, 'probe', '10.0.0.2', '8082'])
        tree = ast.parse(Path(gate.__file__).read_text())
        literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
        self.assertIn('--timeout=30s', literals); self.assertIn(60, literals); self.assertIn(40, literals)

    def test_exact_original_banner_and_source_taxonomy(self):
        literals = re.findall(r'"(adhd-policy-v1\\n)"', gate.SERVE + gate.PROBE)
        self.assertEqual(len(literals), 3)
        banner = literals[0].replace('\\n', '\n').encode()
        source = Path(__file__).with_name('network_policy_tcp.c').read_text()
        numbers = re.search(r'banner\[\] = \{([^}]+)\}', source).group(1)
        self.assertEqual(bytes(map(int, numbers.split(','))), banner)
        self.assertEqual(banner, b'adhd-policy-v1\n'); self.assertEqual(len(banner), 15)
        self.assertIn('ETIMEDOUT || e == EHOSTUNREACH || e == ENETUNREACH || e == ECONNREFUSED', source)
        self.assertEqual(source.count('now_ms() + 1000'), 2)
        self.assertIn('sizeof(got) - used', source)  # fragmented exact-prefix receive
        self.assertIn('if (n <= 0) { close(fd); return 2; }', source)

    def test_both_namespace_configmaps_are_hash_nonce_uid_bound(self):
        for namespace, uid in [('adhd-netpol-unit', 'primary'), ('adhd-netpol-unit-peer', 'peer')]:
            expected = helper.configmap(namespace, uid, 'nonce', b'elf-bytes')
            actual = copy.deepcopy(expected); actual['metadata']['uid'] = 'map-uid'
            self.assertEqual(helper.verify_configmap(actual, expected), 'map-uid')
            for mutate in (lambda x: x['metadata']['annotations'].update({'adhd-policy-namespace-uid': 'foreign'}),
                           lambda x: x['metadata']['labels'].update({'adhd-policy-owner': 'foreign'}),
                           lambda x: x['binaryData'].update({'tcp': 'tampered'}),
                           lambda x: x['metadata'].update({'uid': 'replaced'})):
                bad = copy.deepcopy(actual); mutate(bad)
                with self.assertRaises(AssertionError): helper.verify_configmap(bad, expected, 'map-uid')

    def test_elf_hash_link_dynamic_and_size_failclosed(self):
        data = bytearray(120); data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<H', data, 18, 62); struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1); struct.pack_into('<I', data, 64, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tcp'; path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.assertEqual(helper.read_helper(path, digest), data)
            info = path.stat()
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
            fields['st_atime_ns'] += 1
            with patch.object(helper.os, 'fstat', return_value=SimpleNamespace(**fields)):
                self.assertEqual(helper.read_helper(path, digest), data)
            changed = dict(fields); changed['st_mtime_ns'] += 1
            with patch.object(helper.os, 'fstat', return_value=SimpleNamespace(**changed)):
                with self.assertRaises(AssertionError): helper.read_helper(path, digest)
            altered = bytearray(data); altered[-1] = 1; path.write_bytes(altered)
            with self.assertRaises(AssertionError): helper.read_helper(path, digest)
            path.write_bytes(data)
            with self.assertRaises(AssertionError): helper.read_helper(path, '0' * 64)
            alias = path.with_name('alias'); alias.symlink_to(path)
            with self.assertRaises(AssertionError): helper.read_helper(alias, digest)
            for kind in (2, 3):
                struct.pack_into('<I', data, 64, kind); path.write_bytes(data)
                with self.assertRaises(AssertionError): helper.read_helper(path, hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    with patch('subprocess.Popen', side_effect=AssertionError('No process starts')):
        unittest.main()
