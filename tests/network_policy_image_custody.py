"""Immutable containerd image custody for owned TCP fixture Pods.

No tag fallback or index guessing. Every content/CRI command shares one30s
absolute custody deadline; errors never become network-policy denials.
"""
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import time

TYPES = {
    'application/vnd.docker.distribution.manifest.v2+json': 'application/vnd.docker.container.image.v1+json',
    'application/vnd.oci.image.manifest.v1+json': 'application/vnd.oci.image.config.v1+json',
}
MAX_CONTENT = 1024 * 1024


def digest(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def document(raw):
    assert isinstance(raw, bytes) and 0 < len(raw) <= MAX_CONTENT
    def unique(pairs):
        value = {}
        for key, item in pairs:
            assert key not in value, 'Duplicate image JSON key'
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(AssertionError('Nonfinite image JSON')))
    assert isinstance(value, dict)
    return value


def manifest_digest(reference):
    assert isinstance(reference, str)
    # Pod.status imageID may contain Docker's explicit scheme, never a tag-only fallback.
    reference = reference.removeprefix('docker-pullable://')
    match = re.fullmatch(r'([a-z0-9][a-z0-9._:/-]*)@(sha256:[a-f0-9]{64})', reference)
    assert match and '//' not in match[1] and not match[1].endswith('/'), 'Immutable Pod manifest reference required'
    return match[2]


def manifest(raw, reference, expected):
    assert isinstance(raw, bytes) and 0 < len(raw) <= MAX_CONTENT
    selected = manifest_digest(reference)
    assert re.fullmatch(r'sha256:[a-f0-9]{64}', expected)
    assert digest(raw) == selected, 'Manifest content digest mismatch'
    value = document(raw)
    assert type(value.get('schemaVersion')) is int and value['schemaVersion'] == 2
    assert value.get('mediaType') in TYPES, 'Image manifest required; no index resolution'
    config = value.get('config'); assert isinstance(config, dict)
    assert config.get('mediaType') == TYPES[value['mediaType']]
    assert config.get('digest') == expected
    assert type(config.get('size')) is int and 0 < config['size'] <= MAX_CONTENT
    assert not config.get('urls')
    assert isinstance(value.get('layers'), list)
    return config


def configuration(raw, descriptor, expected):
    assert isinstance(raw, bytes) and 0 < len(raw) <= MAX_CONTENT
    assert len(raw) == descriptor['size'] and digest(raw) == expected
    value = document(raw)
    assert value.get('os') == 'linux' and value.get('architecture') == 'amd64'
    return value


def command(argv, deadline, limit=MAX_CONTENT):
    remaining = deadline - time.monotonic(); assert remaining > 0, 'Image custody deadline'
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    streams = None; output = {'out': bytearray(), 'err': bytearray()}
    primary = None
    try:
        streams = selectors.DefaultSelector()
        for name, stream in [('out', child.stdout), ('err', child.stderr)]:
            os.set_blocking(stream.fileno(), False); streams.register(stream, selectors.EVENT_READ, name)
        while streams.get_map():
            remaining = deadline - time.monotonic(); assert remaining > 0, 'Image custody deadline'
            ready = streams.select(remaining)
            assert ready, 'Image custody deadline'
            for key, _ in ready:
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    streams.unregister(key.fileobj); continue
                output[key.data].extend(chunk)
                assert len(output[key.data]) <= (limit if key.data == 'out' else 65536), 'Image custody output limit'
        remaining = deadline - time.monotonic(); assert remaining > 0, 'Image custody deadline'
        rc = child.wait(timeout=remaining)
        assert time.monotonic() <= deadline, 'Image custody deadline'
        if rc:
            raise subprocess.CalledProcessError(rc, argv, bytes(output['out']), bytes(output['err']))
        assert not output['err'].strip(), 'Unexpected image custody diagnostics'
        return bytes(output['out'])
    except BaseException as error:
        primary = error
        raise
    finally:
        errors = []
        try:
            if streams is not None: streams.close()
        except BaseException as error: errors.append(error)
        try:
            if child.poll() is None:
                assert os.getpgid(child.pid) == child.pid
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        except BaseException as error: errors.append(error)
        for stream in (child.stdout, child.stderr):
            try: stream.close()
            except BaseException as error: errors.append(error)
        if errors:
            if primary is not None:
                primary.add_note('Image custody client cleanup: ' + ','.join(type(e).__name__ for e in errors))
            else: raise errors[0]


def observe(node, reference, expected, run=command, clock=time.monotonic):
    deadline = clock() + 30
    selected = manifest_digest(reference)
    raw_manifest = run(['docker', 'exec', node, 'ctr', '-n=k8s.io', 'content', 'get', selected], deadline)
    descriptor = manifest(raw_manifest, reference, expected)
    raw_config = run(['docker', 'exec', node, 'ctr', '-n=k8s.io', 'content', 'get', expected], deadline)
    configuration(raw_config, descriptor, expected)
    raw_cri = run(['docker', 'exec', node, 'crictl', 'inspecti', expected], deadline)
    actual_image = document(raw_cri)
    assert actual_image['status']['id'] == expected
    assert clock() <= deadline, 'Image custody deadline'
    return actual_image, {'pod_status_image_ref': reference, 'manifest_digest': selected,
        'manifest_bytes': len(raw_manifest), 'manifest_media_type': document(raw_manifest)['mediaType'],
        'config_digest': expected, 'config_bytes': len(raw_config), 'os': 'linux', 'architecture': 'amd64',
        'cri_image_config_identity': actual_image['status']['id']}
