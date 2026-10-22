#!/usr/bin/env python3
"""OCI byte-custody tests; every HTTPS boundary mocked, zero image execution."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
import urllib.request

spec = importlib.util.spec_from_file_location('oci', Path(__file__).with_name('kafka_network_policy_oci.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def digest(data): return 'sha256:' + hashlib.sha256(data).hexdigest()


class OCI(unittest.TestCase):
    def test_descriptor_closed_and_bounded(self):
        good = {'digest': 'sha256:' + 'a' * 64, 'size': 1, 'mediaType': 'layer'}
        self.assertEqual(m.descriptor(good), good)
        for bad in ({**good, 'urls': ['http://untrusted']}, {**good, 'size': True},
                    {**good, 'size': m.MAX_BLOB + 1}, {**good, 'digest': 'sha512:abc'}):
            with self.assertRaises(AssertionError): m.descriptor(bad)

    def test_redirects_https_known_cdns_only_and_no_auth(self):
        request = urllib.request.Request('https://quay.io/blob', headers={'Authorization': 'opaque'})
        handler = m.Redirect()
        redirected = handler.redirect_request(request, None, 302, '', {}, 'https://cdn01.quay.io/blob?sig=opaque')
        self.assertIsNone(redirected.get_header('Authorization'))
        for url in ('http://cdn01.quay.io/blob', 'https://localhost/blob', 'https://quay.io:444/blob', 'https://evil.example/blob'):
            with self.assertRaises(AssertionError): handler.redirect_request(request, None, 302, '', {}, url)
        request._redirects = 4
        with self.assertRaises(AssertionError): handler.redirect_request(request, None, 302, '', {}, 'https://cdn01.quay.io/blob')

    def response(self, body, size=None):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {'Content-Length': str(len(body) if size is None else size)}
        stream = io.BytesIO(body); response.read.side_effect = stream.read
        return response

    def test_download_checks_exact_size_digest_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            body = b'opaque compressed layer'
            item = {'digest': digest(body), 'size': len(body), 'mediaType': 'layer'}
            response = self.response(body)
            opener = MagicMock(); opener.open.return_value = response
            target = Path(directory) / 'blob'
            row = m.download('quay.io/calico/node', item, target, time.monotonic() + 10, opener)
            self.assertEqual(target.read_bytes(), body); self.assertEqual(row['digest'], item['digest'])
            self.assertEqual(target.stat().st_mode & 0o777, 0o444)
            opener.open.assert_called_once(); response.fp.raw._sock.settimeout.assert_called()

    def test_download_rejects_hash_drift_and_preserves_failed_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            item = {'digest': digest(b'ab'), 'size': 2, 'mediaType': 'layer'}
            opener = MagicMock(); opener.open.return_value = self.response(b'cd')
            target = Path(directory) / 'blob'
            with self.assertRaises(AssertionError): m.download('quay.io/calico/node', item, target, time.monotonic() + 10, opener)
            self.assertEqual(target.read_bytes(), b'cd'); opener.open.assert_called_once()

    def test_exact_content_length_can_close_socket_before_eof_read(self):
        with tempfile.TemporaryDirectory() as directory:
            body = b'closed response'
            item = {'digest': digest(body), 'size': len(body), 'mediaType': 'layer'}
            response = self.response(body)
            def read(size):
                response.fp = None
                response.read.side_effect = lambda _: b''
                return body
            response.read.side_effect = read
            opener = MagicMock(); opener.open.return_value = response
            target = Path(directory) / 'blob'
            self.assertEqual(m.download('quay.io/calico/node', item, target, time.monotonic() + 10, opener)['size'], len(body))
            opener.open.assert_called_once()

    def test_download_deadline_denies_before_request(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = MagicMock()
            with self.assertRaises(AssertionError): m.download('quay.io/calico/node', {'digest': digest(b'x'), 'size': 1, 'mediaType': 'layer'}, Path(directory) / 'x', time.monotonic() - 1, opener)
            opener.open.assert_not_called()

    def fixture(self, root):
        config, layer = b'{"os":"linux","architecture":"amd64"}', b'actual compressed bytes'
        value = {'schemaVersion': 2, 'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
                 'config': {'mediaType': 'application/vnd.docker.container.image.v1+json', 'size': len(config), 'digest': digest(config)},
                 'layers': [{'mediaType': 'application/vnd.docker.image.rootfs.diff.tar.gzip', 'size': len(layer), 'digest': digest(layer)}]}
        raw = json.dumps(value, indent=3).encode() + b'\n'  # Preserve even noncanonical whitespace.
        image = {'repository': 'quay.io/calico/node', 'linux_amd64_digest': digest(raw), 'configuration_digest': digest(config)}
        for body in (config, layer): (root / digest(body).split(':')[1]).write_bytes(body)
        return image, raw, value

    def test_archive_preserves_original_manifest_and_exact_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); image, raw, value = self.fixture(root)
            result = m.write_archive(image, raw, value, root, root / 'one.tar')
            m.write_archive(image, raw, value, root, root / 'two.tar')
            self.assertEqual((root / 'one.tar').read_bytes(), (root / 'two.tar').read_bytes())
            with tarfile.open(root / 'one.tar') as tar:
                self.assertEqual(tar.extractfile('blobs/sha256/' + digest(raw).split(':')[1]).read(), raw)
                index = json.load(tar.extractfile('index.json')); target = index['manifests'][0]
                self.assertEqual(target['digest'], digest(raw))
                self.assertEqual(target['annotations']['io.containerd.image.name'], result['reference'])
                for member in tar.getmembers():
                    self.assertEqual(member.mtime, 0); self.assertEqual(member.uid, 0)
                    self.assertFalse(member.islnk() or member.issym())

    def test_actual_import_requires_original_target_and_manifest(self):
        image = {'repository': 'quay.io/calico/node', 'linux_amd64_digest': digest(b'manifest'), 'configuration_digest': digest(b'config')}
        ref = image['repository'] + '@' + image['linux_amd64_digest']
        listing = ref + ' type ' + image['linux_amd64_digest'] + ' 1B linux/amd64 -'
        cri = {'status': {'id': image['configuration_digest'], 'repoDigests': [ref]}}
        self.assertEqual(m.verify_import(image, listing, b'manifest', b'manifest', cri)['actual_target_digest'], image['linux_amd64_digest'])
        for modified_listing, raw, state in [(listing.replace(image['linux_amd64_digest'], digest(b'foreign')), b'manifest', cri),
                                              (listing, b'foreign', cri),
                                              (listing, b'manifest', {'status': {'id': digest(b'foreign'), 'repoDigests': [ref]}}),
                                              (listing, b'manifest', {'status': {'id': image['configuration_digest'], 'repoDigests': []}})]:
            with self.assertRaises(AssertionError): m.verify_import(image, modified_listing, raw, b'manifest', state)

    def test_corrupt_blob_never_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); image, raw, value = self.fixture(root)
            (root / value['layers'][0]['digest'].split(':')[1]).write_bytes(b'corrupt')
            with self.assertRaises(AssertionError): m.write_archive(image, raw, value, root, root / 'bad.tar')

    def test_manifest_rejects_drift_and_foreign_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); image, raw, value = self.fixture(root)
            path = root / 'manifest'; path.write_bytes(raw)
            self.assertEqual(m.manifest_inputs(image, path)[0], raw)
            path.write_bytes(raw + b' ')
            with self.assertRaises(AssertionError): m.manifest_inputs(image, path)
            value['layers'][0]['urls'] = ['https://untrusted']
            changed = json.dumps(value).encode(); path.write_bytes(changed)
            with self.assertRaises(AssertionError): m.manifest_inputs({**image, 'linux_amd64_digest': digest(changed)}, path)


if __name__ == '__main__': unittest.main()
