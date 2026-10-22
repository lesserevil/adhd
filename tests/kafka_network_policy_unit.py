"""Static policy controls and failure guards; no cluster or process starts."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import kafka_network_policy as gate


class PolicyGuards(unittest.TestCase):
    def test_shipped_selectors_ports_and_same_namespace_boundaries(self):
        source = Path(__file__).resolve().parents[1] / 'deploy/k8s/private.yaml'
        before = source.read_bytes()
        rules = gate.policies(source, 'adhd-netpol-unit')
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual({v['metadata']['namespace'] for v in rules}, {'adhd-netpol-unit'})
        by_target = {v['spec']['podSelector']['matchLabels']['app']: v['spec'] for v in rules}
        for who, target, port, expected in gate.ROUTES:
            spec = by_target[gate.PODS[target]]
            allowed = any(
                any(p['port'] == port and p['protocol'] == 'TCP' for p in rule['ports'])
                and any(v == {'podSelector': {'matchLabels': {'app': gate.PODS[who]}}} for v in rule['from'])
                for rule in spec['ingress'])
            self.assertEqual(allowed, expected, (who, target, port))
            self.assertNotEqual(who, target, 'Self traffic bypasses policy and cannot prove a selector')
        self.assertTrue(all('namespaceSelector' not in peer for spec in by_target.values()
                            for rule in spec['ingress'] for peer in rule['from']))
        self.assertEqual({gate.PEERS[r[0]] for r in gate.CROSS_ROUTES}, {'hub', 'kafka-rest', 'kafka'})
        self.assertTrue(all(r[3] is False for r in gate.CROSS_ROUTES))

    def test_namespace_delete_carries_atomic_server_uid_precondition(self):
        import json
        argv, body = gate.namespace_delete('adhd-netpol-owned', 'original-uid')
        self.assertEqual(argv, ['delete', '--raw', '/api/v1/namespaces/adhd-netpol-owned', '-f', '-'])
        self.assertEqual(json.loads(body)['preconditions'], {'uid': 'original-uid'})
        with self.assertRaises(AssertionError):
            gate.namespace_delete('adhd-netpol-owned/foreign', 'original-uid')

    def test_transport_and_exec_failures_never_count_as_denial(self):
        result = lambda rc, out, err=b'': subprocess.CompletedProcess([], rc, out, err)
        self.assertTrue(gate.probe_result(result(0, b'REACHABLE\n')))
        self.assertFalse(gate.probe_result(result(0, b'DENIED\n')))
        for value in (result(1, b'DENIED'), result(0, b''), result(0, b'DENIED', b'exec failure'),
                      result(0, b'REACHABLE\nDENIED'), result(125, b'')):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                gate.probe_result(value)

    def test_fixture_cannot_start_application_or_pull_unreviewed_images(self):
        value = gate.pod('test', 'hub', 'adhd-netpol-test', 'adhd-hub:pinned')
        container = value['spec']['containers'][0]
        self.assertEqual(container['command'], ['elixir', '-e', gate.SERVE])
        self.assertNotIn('/app/hub.exs', gate.SERVE)
        self.assertEqual(container['imagePullPolicy'], 'Never')
        self.assertTrue(container['securityContext']['readOnlyRootFilesystem'])
        self.assertFalse(container['securityContext']['allowPrivilegeEscalation'])
        self.assertEqual(container['securityContext']['capabilities']['drop'], ['ALL'])
        self.assertEqual(value['spec']['restartPolicy'], 'Never')

    def test_unexpected_policy_documents_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.yaml'
            for body in ('[]', '', 'kind: Pod\n', '---\n---\n---\n'):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises((AssertionError, TypeError)):
                    gate.policies(path, 'adhd-netpol-unit')


if __name__ == '__main__':
    with patch('subprocess.Popen', side_effect=AssertionError('No process starts in static guards')):
        unittest.main()
