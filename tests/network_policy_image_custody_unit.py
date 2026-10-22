"""Forged containerd custody vectors; no actual processes or resource access."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch, Mock
import network_policy_image_custody as m


def raw(value): return json.dumps(value, separators=(',', ':')).encode()


class Custody(unittest.TestCase):
    def fixture(self, media=None):
        config = raw({'architecture': 'amd64', 'os': 'linux', 'rootfs': {'type': 'layers', 'diff_ids': []}})
        expected = m.digest(config)
        media = media or next(iter(m.TYPES))
        manifest = {'schemaVersion': 2, 'mediaType': media,
            'config': {'mediaType': m.TYPES[media], 'digest': expected, 'size': len(config)}, 'layers': []}
        return config, expected, manifest

    def test_both_supported_manifest_formats(self):
        for media in m.TYPES:
            config, expected, value = self.fixture(media); body = raw(value)
            ref = 'docker.io/library/import-date@' + m.digest(body)
            descriptor = m.manifest(body, ref, expected)
            self.assertEqual(m.configuration(config, descriptor, expected)['os'], 'linux')

    def test_no_tag_or_index_or_forged_content_fallback(self):
        config, expected, value = self.fixture(); body = raw(value)
        for ref in ['mutable:tag', expected, 'name@sha256:' + 'A' * 64, 'https://foreign@' + m.digest(body), 'name@' + 'sha256:' + '0' * 64]:
            with self.subTest(ref=ref), self.assertRaises(AssertionError): m.manifest(body, ref, expected)
        for key, replacement in [('schemaVersion', True), ('schemaVersion', 2.0), ('schemaVersion', 1),
            ('mediaType', 'application/vnd.oci.image.index.v1+json'), ('mediaType', 'unknown')]:
            altered = copy.deepcopy(value); altered[key] = replacement; changed = raw(altered)
            with self.subTest(key=key, value=replacement), self.assertRaises(AssertionError):
                m.manifest(changed, 'name@' + m.digest(changed), expected)

    def test_wrong_descriptor_or_duplicate_keys(self):
        config, expected, value = self.fixture()
        for key, replacement in [('size', True), ('size', 1.0), ('size', 0), ('size', m.MAX_CONTENT + 1),
            ('digest', 'sha256:' + '0' * 64), ('mediaType', 'application/vnd.oci.image.config.v1+json'), ('urls', ['https://foreign'])]:
            altered = copy.deepcopy(value); altered['config'][key] = replacement; body = raw(altered)
            with self.subTest(key=key, value=replacement), self.assertRaises(AssertionError): m.manifest(body, 'name@' + m.digest(body), expected)
        duplicate = raw(value).replace(b'"schemaVersion":2', b'"schemaVersion":2,"schemaVersion":2')
        with self.assertRaises(AssertionError): m.manifest(duplicate, 'name@' + m.digest(duplicate), expected)

    def test_config_bytes_size_and_platform_mandatory(self):
        config, expected, value = self.fixture(); descriptor = value['config']
        for content in [config + b' ', config.replace(b'amd64', b'arm64'), config.replace(b'linux', b'other')]:
            with self.assertRaises(AssertionError): m.configuration(content, descriptor, expected)
        for platform in [{'architecture': 'arm64', 'os': 'linux'}, {'architecture': 'amd64', 'os': 'windows'}]:
            body = raw(platform)
            with self.assertRaises(AssertionError): m.configuration(body, {'size': len(body)}, m.digest(body))
        with self.assertRaises(AssertionError): m.document(b'{}' * (m.MAX_CONTENT // 2 + 1))

    def test_three_commands_one_deadline_and_immutable_cri_id(self):
        config, expected, value = self.fixture(); body = raw(value); reference = 'named@' + m.digest(body)
        calls = []
        def run(argv, deadline):
            calls.append((argv, deadline))
            return [body, config, raw({'status': {'id': expected}})][len(calls) - 1]
        actual, proof = m.observe('owned-node', reference, expected, run=run, clock=lambda: 123)
        self.assertEqual(len(calls), 3)
        self.assertEqual({v[1] for v in calls}, {153})
        self.assertEqual(calls[0][0], ['docker', 'exec', 'owned-node', 'ctr', '-n=k8s.io', 'content', 'get', m.digest(body)])
        self.assertEqual(calls[1][0][-1], expected); self.assertEqual(calls[2][0], ['docker', 'exec', 'owned-node', 'crictl', 'inspecti', expected])
        self.assertEqual(proof['pod_status_image_ref'], reference)
        self.assertEqual(actual['status']['id'], expected)
        with self.assertRaises(subprocess.TimeoutExpired):
            m.observe('owned-node', reference, expected, run=lambda a,d: (_ for _ in ()).throw(subprocess.TimeoutExpired(a, 30)))
        calls.clear()
        with self.assertRaises(AssertionError):
            m.observe('owned-node', reference, expected, run=run, clock=iter([123, 154]).__next__)

    def test_unavailable_content_and_foreign_cri_fail_without_retry(self):
        config, expected, value = self.fixture(); body = raw(value); reference = 'named@' + m.digest(body)
        calls = []
        def missing(argv, deadline):
            calls.append(argv)
            raise subprocess.CalledProcessError(1, argv, b'', b'content unavailable')
        with self.assertRaises(subprocess.CalledProcessError):
            m.observe('owned-node', reference, expected, run=missing)
        self.assertEqual(len(calls), 1)
        responses = iter([body, config, raw({'status': {'id': 'sha256:' + '0' * 64}})])
        with self.assertRaises(AssertionError):
            m.observe('owned-node', reference, expected, run=lambda argv, deadline: next(responses))

    def test_started_timeout_joins_client_and_preserves_primary(self):
        child = Mock(pid=123, stdout=Mock(), stderr=Mock())
        child.poll.return_value = None
        child.wait.side_effect = subprocess.TimeoutExpired(['docker'], 5)
        selector = Mock(); selector.get_map.return_value = {'out': object()}
        with patch.object(m.subprocess, 'Popen', return_value=child), \
             patch.object(m.selectors, 'DefaultSelector', return_value=selector), \
             patch.object(m.os, 'set_blocking'), patch.object(m.os, 'getpgid', return_value=123), \
             patch.object(m.os, 'killpg') as kill, patch.object(m.time, 'monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(AssertionError, 'Image custody deadline') as caught:
                m.command(['docker', 'exec', 'owned-node', 'ctr'], 30)
            kill.assert_called_once_with(123, m.signal.SIGKILL)
            child.wait.assert_called_once_with(timeout=5)
            child.stdout.close.assert_called_once(); child.stderr.close.assert_called_once()
            self.assertIn('TimeoutExpired', caught.exception.__notes__[0])

    def test_content_capture_overflow_is_error_and_joins(self):
        child = Mock(pid=123, stdout=Mock(), stderr=Mock())
        child.poll.return_value = None; child.wait.return_value = 0
        selector = Mock(); selector.get_map.return_value = {'out': object()}
        key = Mock(fd=10, fileobj=child.stdout, data='out')
        selector.select.return_value = [(key, 1)]
        with patch.object(m.subprocess, 'Popen', return_value=child), \
             patch.object(m.selectors, 'DefaultSelector', return_value=selector), \
             patch.object(m.os, 'set_blocking'), patch.object(m.os, 'read', return_value=b'x' * 11), \
             patch.object(m.os, 'getpgid', return_value=123), patch.object(m.os, 'killpg') as kill, \
             patch.object(m.time, 'monotonic', return_value=0):
            with self.assertRaisesRegex(AssertionError, 'Image custody output limit'):
                m.command(['docker', 'exec', 'owned-node', 'ctr'], 30, limit=10)
            kill.assert_called_once(); child.wait.assert_called_once_with(timeout=5)

    def test_expired_command_never_launches(self):
        with patch.object(m.time, 'monotonic', return_value=40), patch.object(m.subprocess, 'Popen') as launch:
            with self.assertRaises(AssertionError): m.command(['no-op'], 39)
            launch.assert_not_called()

    def test_selector_construction_failure_still_joins_owned_client(self):
        child = Mock(pid=123, stdout=Mock(), stderr=Mock())
        child.poll.return_value = None; child.wait.return_value = -9
        with patch.object(m.subprocess, 'Popen', return_value=child), \
             patch.object(m.selectors, 'DefaultSelector', side_effect=OSError('selector unavailable')), \
             patch.object(m.os, 'getpgid', return_value=123), patch.object(m.os, 'killpg') as kill, \
             patch.object(m.time, 'monotonic', return_value=0):
            with self.assertRaisesRegex(OSError, 'selector unavailable'):
                m.command(['docker', 'exec', 'owned-node', 'ctr'], 30)
            kill.assert_called_once_with(123, m.signal.SIGKILL)
            child.wait.assert_called_once_with(timeout=5)
            child.stdout.close.assert_called_once(); child.stderr.close.assert_called_once()


if __name__ == '__main__':
    with patch('subprocess.Popen', side_effect=AssertionError('No process starts')):
        unittest.main()
