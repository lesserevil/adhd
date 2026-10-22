"""Pure static NetworkPolicy fixture descriptors; no compiler or runtime launch."""
import base64
import hashlib
import os
import posixpath
from pathlib import Path
import re
import stat
import struct

NAME = 'policy-tcp-helper'
PATH = '/policy-helper/tcp'


def identity(info):
    # Reading may legitimately update atime. All source identity/content clocks remain bound.
    return tuple(getattr(info, 'st_' + field) for field in
        ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns'))


def read_helper(path, expected):
    assert re.fullmatch(r'[a-f0-9]{64}', expected or '')
    path = Path(path).absolute()
    assert path.resolve() == path and all(not p.is_symlink() for p in (path, *path.parents))
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1
    assert 0 < before.st_size <= 1024 * 1024
    with path.open('rb') as stream:
        assert identity(os.fstat(stream.fileno())) == identity(before)
        data = stream.read(1024 * 1024 + 1)
        assert identity(os.fstat(stream.fileno())) == identity(before)
    assert identity(path.lstat()) == identity(before) and hashlib.sha256(data).hexdigest() == expected
    assert data[:7] == b'\x7fELF\x02\x01\x01' and len(data) >= 64
    assert struct.unpack_from('<H', data, 18)[0] == 62
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    assert size == 56 and 0 < count <= 128 and offset + size * count <= len(data)
    assert all(struct.unpack_from('<I', data, offset + i * size)[0] not in (2, 3) for i in range(count))
    return data


def configmap(namespace, namespace_uid, owner, data):
    return {'apiVersion': 'v1', 'kind': 'ConfigMap', 'immutable': True,
        'metadata': {'name': NAME, 'namespace': namespace,
            'labels': {'adhd-policy-owner': owner},
            'annotations': {'adhd-policy-namespace-uid': namespace_uid,
                            'adhd-policy-helper-sha256': hashlib.sha256(data).hexdigest()}},
        'binaryData': {'tcp': base64.b64encode(data).decode()}}


def verify_configmap(actual, expected, uid=None):
    assert actual['metadata']['name'] == NAME
    assert actual['metadata']['namespace'] == expected['metadata']['namespace']
    for key in ('labels', 'annotations'):
        assert actual['metadata'][key] == expected['metadata'][key]
    assert actual['immutable'] is True and actual['binaryData'] == expected['binaryData']
    assert not actual.get('data') and actual['metadata']['uid']
    assert uid is None or actual['metadata']['uid'] == uid
    return actual['metadata']['uid']


def mount(pod):
    pod['spec']['containers'][0]['command'] = [PATH, 'serve']
    pod['spec']['containers'][0]['volumeMounts'] = [
        {'name': NAME, 'mountPath': '/policy-helper', 'readOnly': True}]
    pod['spec']['volumes'] = [{'name': NAME, 'configMap': {
        'name': NAME, 'defaultMode': 0o555, 'items': [{'key': 'tcp', 'path': 'tcp'}]}}]
    return pod


def verify_mount(actual, expected):
    # Kubernetes adds service-account volumes/mounts; match only our closed owned volume.
    assert [v for v in actual['spec']['volumes'] if v['name'] == NAME] == expected['spec']['volumes']
    container = actual['spec']['containers'][0]
    assert container['command'] == [PATH, 'serve']
    assert [v for v in container['volumeMounts'] if v['name'] == NAME] == expected['spec']['containers'][0]['volumeMounts']

    owned = '/policy-helper'
    for entry in container['volumeMounts']:
        if entry['name'] == NAME:
            continue
        path = entry['mountPath']
        assert isinstance(path, str) and path.startswith('/')
        path = posixpath.normpath('/' + path.lstrip('/'))
        assert not (path == owned or path.startswith(owned + '/') or
                    owned.startswith(path.rstrip('/') + '/')), 'Foreign mount shadows owned helper'
