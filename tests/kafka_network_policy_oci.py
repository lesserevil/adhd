#!/usr/bin/env python3
"""Bounded exact OCI archive preparation; no Docker, node, or image execution."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import tarfile
import time
import urllib.parse
import urllib.request

MAX_BLOB = 256 * 1024 * 1024
MAX_TOTAL = 384 * 1024 * 1024
REPOSITORIES = ('quay.io/calico/calico', 'quay.io/calico/third-party-cni-plugins', 'quay.io/calico/node')


def sha(data): return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path).absolute()
    assert path.resolve(strict=True) == path and path.is_file() and path.stat().st_nlink == 1
    return path


def descriptor(value, maximum=MAX_BLOB):
    assert isinstance(value, dict) and set(value) <= {'mediaType', 'digest', 'size'}
    assert re.fullmatch('sha256:[a-f0-9]{64}', value['digest'])
    assert type(value['size']) is int and 0 < value['size'] <= maximum
    assert isinstance(value['mediaType'], str)
    return value


def manifest_inputs(image, source):
    assert image['repository'] in REPOSITORIES
    source = regular(source)
    raw = source.read_bytes()
    assert 'sha256:' + sha(raw) == image['linux_amd64_digest']
    value = json.loads(raw)
    assert set(value) == {'schemaVersion', 'mediaType', 'config', 'layers'} and value['schemaVersion'] == 2
    assert value['mediaType'] == 'application/vnd.docker.distribution.manifest.v2+json'
    descriptor(value['config'], 1024 * 1024)
    assert value['config']['digest'] == image['configuration_digest']
    assert value['config']['mediaType'] == 'application/vnd.docker.container.image.v1+json'
    assert 1 <= len(value['layers']) <= 32
    for layer in value['layers']:
        descriptor(layer)
        assert layer['mediaType'] == 'application/vnd.docker.image.rootfs.diff.tar.gzip'
    return raw, value


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        assert target.scheme == 'https' and target.port in (None, 443)
        assert not target.username and not target.password
        # Only registry/CDN hosts used by Quay public blob storage are admitted.
        assert target.hostname == 'quay.io' or target.hostname.endswith(('.quay.io', '.googleapis.com', '.cloudfront.net'))
        count = getattr(request, '_redirects', 0) + 1
        assert count <= 4
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected._redirects = count
            redirected.remove_header('Authorization')
        return redirected


def download(repository, item, output, deadline, opener=None):
    descriptor(item)
    assert repository in REPOSITORIES and not output.exists()
    url = 'https://quay.io/v2/' + repository.removeprefix('quay.io/') + '/blobs/' + item['digest']
    opener = opener or urllib.request.build_opener(Redirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    remaining = deadline - time.monotonic()
    assert remaining > 0
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity', 'User-Agent': 'adhd-oci-preparation/1'})
    digest = hashlib.sha256()
    total = 0
    # No automatic retry, no decompression, and no credentials/redirect query logged.
    with opener.open(request, timeout=min(40, remaining)) as response, output.open('xb') as stream:
        assert response.status == 200
        header = response.headers.get('Content-Length')
        if header is not None: assert int(header) == item['size']
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0
            # HTTPResponse closes fp after consuming a declared Content-Length.
            # An EOF read then needs no socket and must remain a normal EOF.
            if response.fp is not None:
                response.fp.raw._sock.settimeout(min(40, remaining))
            data = response.read(min(1024 * 1024, item['size'] - total + 1))
            if not data: break
            total += len(data)
            assert total <= item['size']
            digest.update(data); stream.write(data)
        stream.flush(); os.fsync(stream.fileno())
    assert time.monotonic() < deadline and total == item['size'] and 'sha256:' + digest.hexdigest() == item['digest']
    output.chmod(0o444)
    return {'digest': item['digest'], 'size': total, 'sha256': digest.hexdigest()}


def write_archive(image, raw, value, blobs, output):
    reference = image['repository'] + '@' + image['linux_amd64_digest']
    index = {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.index.v1+json', 'manifests': [{
        'mediaType': value['mediaType'], 'digest': image['linux_amd64_digest'], 'size': len(raw),
        'platform': {'os': 'linux', 'architecture': 'amd64'},
        'annotations': {'io.containerd.image.name': reference,
                        'org.opencontainers.image.ref.name': reference}}]}
    extras = {'oci-layout': b'{"imageLayoutVersion":"1.0.0"}',
              'index.json': json.dumps(index, sort_keys=True, separators=(',', ':')).encode(),
              'blobs/sha256/' + image['linux_amd64_digest'].split(':')[1]: raw}
    assert not output.exists()
    with tarfile.open(output, mode='x', format=tarfile.USTAR_FORMAT) as tar:
        for name, body in sorted(extras.items()):
            member = tarfile.TarInfo(name); member.size = len(body); member.mode = 0o444
            tar.addfile(member, io.BytesIO(body))
        unique = {item['digest']: item for item in [value['config'], *value['layers']]}
        for item in unique.values():
            path = regular(blobs / item['digest'].split(':')[1])
            assert path.stat().st_size == item['size'] and 'sha256:' + sha(path.read_bytes()) == item['digest']
            member = tarfile.TarInfo('blobs/sha256/' + item['digest'].split(':')[1])
            member.size = item['size']; member.mode = 0o444
            with path.open('rb') as stream: tar.addfile(member, stream)
    output.chmod(0o444)
    return {'reference': reference, 'archive_sha256': sha(output.read_bytes()), 'archive_bytes': output.stat().st_size,
            'manifest_sha256': sha(raw), 'configuration_digest': image['configuration_digest'],
            'original_manifest_preserved': True, 'layers': [dict(x) for x in value['layers']]}


def verify_import(image, listing, actual_manifest, expected_manifest, cri):
    reference = image['repository'] + '@' + image['linux_amd64_digest']
    rows = [line.split() for line in listing.splitlines() if line.split() and line.split()[0] == reference]
    assert len(rows) == 1 and len(rows[0]) >= 3 and rows[0][2] == image['linux_amd64_digest']
    assert actual_manifest == expected_manifest and 'sha256:' + sha(actual_manifest) == image['linux_amd64_digest']
    assert cri['status']['id'] == image['configuration_digest'] and reference in cri['status']['repoDigests']
    return {'reference': reference, 'actual_target_digest': rows[0][2],
            'actual_manifest_sha256': sha(actual_manifest), 'actual_configuration_digest': cri['status']['id']}


def validate_archives(bundle, images, manifests):
    """Verify complete OCI members without extracting or rewriting upstream bytes."""
    report = json.loads(regular(bundle / 'manifest.json').read_text())
    assert report['schema'] == 'adhd/cni-exact-oci-archives@1' and report['passed'] is True
    assert report['executed_images'] is False and report['source_manifests_rewritten'] is False
    selected = [image for image in images if image['repository'] in REPOSITORIES]
    assert tuple(image['repository'] for image in selected) == REPOSITORIES
    assert len(report['images']) == 3
    for index, image in enumerate(selected):
        stem = image['repository'].removeprefix('quay.io/').replace('/', '-')
        raw, value = manifest_inputs(image, manifests / (stem + '-amd64.json'))
        row = report['images'][index]
        assert row['reference'] == image['repository'] + '@' + image['linux_amd64_digest']
        assert row['manifest_sha256'] == sha(raw) and row['configuration_digest'] == image['configuration_digest']
        assert row['original_manifest_preserved'] is True and row['layers'] == value['layers']
        archive = regular(bundle / (str(index) + '.oci.tar'))
        assert archive.stat().st_size == row['archive_bytes'] <= MAX_TOTAL
        assert sha(archive.read_bytes()) == row['archive_sha256']
        expected = {'oci-layout', 'index.json', 'blobs/sha256/' + sha(raw)}
        descriptors = {item['digest']: item for item in [value['config'], *value['layers']]}
        expected |= {'blobs/sha256/' + digest.split(':')[1] for digest in descriptors}
        with tarfile.open(archive, 'r:') as tar:
            members = tar.getmembers()
            assert len(members) == len(expected) and {m.name for m in members} == expected
            for member in members:
                assert member.isfile() and member.uid == member.gid == member.mtime == 0 and member.mode == 0o444
                assert member.size <= MAX_BLOB
                stream = tar.extractfile(member)
                if member.name == 'oci-layout':
                    assert json.loads(stream.read()) == {'imageLayoutVersion': '1.0.0'}
                elif member.name == 'index.json':
                    ix = json.loads(stream.read()); assert ix['schemaVersion'] == 2 and len(ix['manifests']) == 1
                    target = ix['manifests'][0]
                    assert target['digest'] == image['linux_amd64_digest'] and target['size'] == len(raw)
                    assert target['mediaType'] == value['mediaType'] and target['platform'] == {'os': 'linux', 'architecture': 'amd64'}
                    assert target['annotations'] == {'io.containerd.image.name': row['reference'], 'org.opencontainers.image.ref.name': row['reference']}
                elif member.name == 'blobs/sha256/' + sha(raw):
                    assert stream.read() == raw
                else:
                    key = 'sha256:' + member.name.split('/')[-1]
                    assert member.size == descriptors[key]['size']
                    digest = hashlib.sha256()
                    for data in iter(lambda: stream.read(1024 * 1024), b''): digest.update(data)
                    assert 'sha256:' + digest.hexdigest() == key
    return report


def prepare(images_file, manifests, work):
    images_file = regular(images_file)
    images = [v for v in json.loads(images_file.read_text()) if v['repository'] in REPOSITORIES]
    assert tuple(v['repository'] for v in images) == REPOSITORIES
    inputs = []
    for image in images:
        stem = image['repository'].removeprefix('quay.io/').replace('/', '-')
        raw, value = manifest_inputs(image, manifests / (stem + '-amd64.json'))
        inputs.append((image, raw, value))
    assert sum(d['size'] for _, _, v in inputs for d in [v['config'], *v['layers']]) <= MAX_TOTAL
    assert not work.exists() and work.absolute().resolve() == work.absolute()
    work.mkdir(parents=True, mode=0o700); blobs = work / 'blobs'; blobs.mkdir()
    rows = []
    for index, (image, raw, value) in enumerate(inputs):
        deadline = time.monotonic() + 240
        blob_rows = []
        for item in [value['config'], *value['layers']]:
            path = blobs / item['digest'].split(':')[1]
            if path.exists():
                assert path.stat().st_size == item['size'] and 'sha256:' + sha(regular(path).read_bytes()) == item['digest']
                blob_rows.append({'digest': item['digest'], 'size': item['size'], 'deduplicated_exact_blob': True})
            else: blob_rows.append(download(image['repository'], item, path, deadline))
        config = json.loads((blobs / value['config']['digest'].split(':')[1]).read_text())
        assert config['os'] == 'linux' and config['architecture'] == 'amd64'
        assert config['rootfs']['type'] == 'layers' and len(config['rootfs']['diff_ids']) == len(value['layers'])
        for digest in config['rootfs']['diff_ids']: assert re.fullmatch('sha256:[a-f0-9]{64}', digest)
        row = write_archive(image, raw, value, blobs, work / (str(index) + '.oci.tar'))
        assert time.monotonic() < deadline
        row['blob_checks'] = blob_rows; rows.append(row)
    report = {'schema': 'adhd/cni-exact-oci-archives@1', 'passed': True, 'executed_images': False,
              'images_file_sha256': sha(images_file.read_bytes()), 'images': rows,
              'dns_or_cluster_mutation': False, 'source_manifests_rewritten': False,
              'scope': 'Host HTTPS byte preparation only; actual owned-node import target verification remains required'}
    (work / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images', type=Path, required=True); p.add_argument('--manifests', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    args = p.parse_args(); print(json.dumps(prepare(args.images, args.manifests, args.work)))
