"""Parameter-bound, create-only compiled image payload/cache audit.

Requires explicit --execute. This never starts an image process. Runtime/cache
execution qualification and proper source receipt issuance are separate gates.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
from uuid import uuid4

_HELPERS = Path(__file__).absolute().parent
assert Path(__file__).resolve(strict=True) == Path(__file__).absolute()
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))
from container_fixture import OwnedImage
from image_compiled_inputs import compiled_context


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path, maximum=64 * 1024 * 1024):
    path = Path(path).absolute()
    assert path.resolve(strict=True) == path
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum
    identity = lambda v: (v.st_dev, v.st_ino, v.st_mode, v.st_uid, v.st_gid, v.st_nlink, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        assert identity(os.fstat(stream.fileno())) == identity(before)
        data = stream.read(maximum + 1)
        assert identity(os.fstat(stream.fileno())) == identity(before)
    assert identity(path.lstat()) == identity(before) and len(data) <= maximum
    return data


def json_bytes(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def checked_directory(path):
    path = Path(path).absolute()
    assert path.resolve(strict=True) == path and path.is_dir()
    return path


class Docker:
    def __init__(self, executable, socket, config):
        self.executable = Path(executable).absolute()
        regular(self.executable)
        self.socket = Path(socket).absolute()
        assert self.socket.resolve(strict=True) == self.socket and stat.S_ISSOCK(self.socket.stat().st_mode)
        self.config = checked_directory(config)
        assert regular(self.config / 'config.json', 1024).strip() == b'{}'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('DOCKER_')}

    def run(self, args, timeout=60):
        return subprocess.run([str(self.executable), '--host', 'unix://' + str(self.socket),
                               '--config', str(self.config), *args],
                              capture_output=True, timeout=timeout, env=self.env)

    def checked(self, args):
        result = self.run(args)
        assert result.returncode == 0, 'Docker operation failed'
        return result.stdout


def cleanup(docker, image, name, identifier):
    """Keep initial uncertainty observable while independently closing known ID."""
    errors = []
    foreign = False
    known = identifier
    try:
        inspected = docker.run(['inspect', known or name])
        if not OwnedImage.probe_absence(inspected, known or name):
            assert inspected.returncode == 0
            rows = json.loads(inspected.stdout)
            assert len(rows) == 1
            row = rows[0]
            if (row['Image'] != image or row['Name'] != '/' + name or
                    (known is not None and row['Id'] != known)):
                foreign = True
                raise AssertionError('Foreign container identity')
            known = row['Id']
            assert re.fullmatch('[a-f0-9]{64}', known)
            assert row['State']['Status'] == 'created' and not row['State']['Running'], 'Audit container was started'
            assert docker.run(['rm', '--force', known]).returncode == 0
    except BaseException as error:
        errors.append(type(error).__name__)
    if errors and known and not foreign:
        try:
            removed = docker.run(['rm', '--force', known])
            if removed.returncode:
                assert OwnedImage.probe_absence(docker.run(['inspect', known]), known)
        except BaseException as error:
            errors.append('IndependentCleanup:' + type(error).__name__)
    absent = True
    for target in dict.fromkeys(x for x in (known, name) if x):
        try:
            assert OwnedImage.probe_absence(docker.run(['inspect', target]), target)
        except BaseException as error:
            absent = False
            errors.append('Absence:' + type(error).__name__)
    return {'container_id': known, 'container_name': name, 'observed_absent': absent,
            'failure_types': errors, 'foreign_identity': foreign}


def inspect_payload(app_body, cache_body, runtime_body, context, expected_source, runtime_helpers):
    """Pure archive/byte validation; does not load BEAM/source or invoke Docker."""
    context = checked_directory(context)
    expected = regular(context / 'manifest.json', 1024 * 1024)
    manifest = json.loads(expected)
    assert manifest['schema'] == 'adhd/container-inputs@1'
    assert manifest['files']['hub.exs'] == expected_source
    binding = compiled_context(context, digest(expected), expected_source)
    assert len(app_body) <= 32 * 1024 * 1024
    assert len(cache_body) <= 128 * 1024 * 1024 and len(runtime_body) <= 128 * 1024 * 1024
    files = {}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(app_body)) as archive:
        for item in archive.getmembers():
            path = PurePosixPath(item.name)
            assert not path.is_absolute() and '..' not in path.parts
            assert item.name not in seen
            seen.add(item.name)
            if item.isdir():
                continue
            assert item.isfile() and item.size <= 8 * 1024 * 1024, 'Nonregular or oversized app payload'
            key = path.as_posix().removeprefix('./')
            assert key not in files
            files[key] = archive.extractfile(item).read()
    assert files.pop('manifest.json') == expected
    targets = {k: v for k, v in manifest['files'].items() if k != 'Dockerfile'}
    assert set(files) == set(targets)
    assert all(digest(files[k]) == value for k, value in targets.items())
    assert digest(regular(context / 'Dockerfile')) == manifest['files']['Dockerfile']
    specifications = sum(key.startswith('specification/') for key in files)
    counts=binding["payload_counts"]
    assert specifications == (counts["specifications"] if counts else 33) and len(files) == (counts["app_files"] if counts else 59)
    with tarfile.open(fileobj=io.BytesIO(runtime_body)) as archive:
        parents = [item for item in archive.getmembers() if item.name == 'runtime']
        assert len(parents) == 1
        parent = parents[0]
        assert parent.isdir() and parent.uid == parent.gid == 0 and parent.mode == 0o755 and parent.mtime == 0
    cache = {}
    metadata = {'/runtime': {'mode': oct(parent.mode), 'mtime': parent.mtime, 'sha256': None}}
    with tarfile.open(fileobj=io.BytesIO(cache_body)) as archive:
        for item in archive.getmembers():
            path = PurePosixPath(item.name)
            assert not path.is_absolute() and '..' not in path.parts
            assert item.name not in cache and item.uid == item.gid == 0
            assert item.isdir() or item.isfile()
            assert item.mode == (0o555 if item.isdir() or item.name in ["adhd/lego", "adhd/acme-guard"] else 0o444)
            assert item.mtime == 0
            cache[item.name] = archive.extractfile(item).read() if item.isfile() else None
            metadata[item.name] = {'mode': oct(item.mode), 'mtime': item.mtime,
                                   'sha256': digest(cache[item.name]) if item.isfile() else None}
    cm = json.loads(cache['adhd/manifest.json'])
    assert cm['source_sha256'] == targets['hub.exs'] and cm['payload_manifest_sha256'] == digest(expected)
    names = ['Elixir.' + n for n in re.findall(r'^defmodule ([A-Za-z0-9_.]+) do$', files['hub.exs'].decode(), re.M)]
    assert cm['modules'] == names and len(names) == len(set(names)) == (len(counts["modules"]) if counts else 59)
    assert set(cache) == {'adhd', 'adhd/ebin', 'adhd/manifest.json', 'adhd/inputs.json', 'adhd/boot.exs', 'adhd/build.exs'} | {'adhd/ebin/' + n + '.beam' for n in names} | {'adhd/'+n for n in binding['acme_files']}
    assert set(cm['beams']) == {n + '.beam' for n in names}
    for name in names:
        assert digest(cache['adhd/ebin/' + name + '.beam']) == cm['beams'][name + '.beam']
    if binding['acme_files']:
        assert cm['schema']=='adhd/precompiled-cache@2' and cm['acme']=={n:binding['packaging_files_sha256'][n] for n in binding['acme_files']}
        for name, value in cm['acme'].items():assert digest(cache['adhd/'+name])==value
    else:assert cm['schema']=='adhd/precompiled-cache@1'
    runtime_helpers = checked_directory(runtime_helpers)
    for name in ('boot', 'build'):
        assert digest(cache['adhd/' + name + '.exs']) == cm[name + '_sha256'] == digest(regular(runtime_helpers / (name + '.exs')))
    assert cache['adhd/inputs.json'] == regular(context / 'compiler-inputs.json')
    assert digest(cache['adhd/inputs.json']) == cm['inputs_sha256'] == binding['compiler_inputs_sha256']
    return {'cache_manifest': cache['adhd/manifest.json'], 'cache_metadata': metadata,
            'artifact_sha256': targets['hub.exs'], 'canonical_manifest_sha256': digest(expected),
            'actual_app_files': len(files), 'canonical_specifications': specifications,
            'cache_modules': len(names), 'cache_entries': len(cache), 'cache_all_zero_timestamps': True,
            'runtime_parent_mtime': parent.mtime, 'runtime_parent_reproducibility_pending': parent.mtime != 0}


def execute(args, docker=None):
    assert re.fullmatch('sha256:[a-f0-9]{64}', args.image)
    assert re.fullmatch('[a-f0-9]{64}', args.artifact_sha256)
    assert re.fullmatch('[a-f0-9]{64}', args.context_sha256)
    context = checked_directory(args.context)
    assert digest(regular(context / 'manifest.json')) == args.context_sha256
    compiled_context(context, args.context_sha256, args.artifact_sha256)
    helpers = checked_directory(args.runtime_helpers)
    output = Path(args.output).absolute()
    assert output.parent.resolve(strict=True) == output.parent and not output.exists()
    output.mkdir(mode=0o700)
    docker = docker or Docker(args.docker, args.docker_socket, args.docker_config)
    name = 'adhd-image-audit-' + uuid4().hex[:16]
    identifier = None
    primary = None
    result = {'schema': 'adhd/actual-image-payload-audit@1', 'passed': False,
              'image_id': args.image, 'artifact_sha256': args.artifact_sha256,
              'canonical_manifest_sha256': args.context_sha256,
              'container_started': False, 'audit_container_name': name}
    (output / 'image-payload.json').write_bytes(json_bytes(result))
    try:
        raw_identifier = docker.checked(['create', '--pull', 'never', '--name', name, '--network', 'none', '--read-only', args.image]).decode().strip()
        assert re.fullmatch('[a-f0-9]{64}', raw_identifier), 'Malformed create container ID'
        identifier = raw_identifier
        result['audit_container_id'] = identifier
        observed = json.loads(docker.checked(['inspect', identifier]))
        assert len(observed) == 1
        observed = observed[0]
        assert observed['Image'] == args.image and observed['Name'] == '/' + name and observed['Id'] == identifier
        assert observed['State']['Status'] == 'created' and not observed['State']['Running']
        values = inspect_payload(docker.checked(['cp', identifier + ':/app/.', '-']),
                                 docker.checked(['cp', identifier + ':/runtime/adhd', '-']),
                                 docker.checked(['cp', identifier + ':/runtime', '-']),
                                 context, args.artifact_sha256, helpers)
        (output / 'cache-manifest.json').write_bytes(values.pop('cache_manifest'))
        (output / 'cache-metadata.json').write_bytes(json_bytes(values.pop('cache_metadata')))
        result.update(values)
    except BaseException as error:
        primary = error
        result['failure_type'] = type(error).__name__
    finally:
        closure = cleanup(docker, args.image, name, identifier)
        result['cleanup'] = closure
        result['owned_container_absent'] = closure['observed_absent'] and not closure['failure_types']
        result['passed'] = primary is None and result['owned_container_absent']
        try:
            (output / 'image-payload.json').write_bytes(json_bytes(result))
        except BaseException as error:
            if primary is not None:
                primary.add_note('Audit result persistence failed: ' + type(error).__name__)
            else:
                raise
    if primary is not None:
        if not result['owned_container_absent']:
            primary.add_note('Audit cleanup was not fully qualified')
        raise primary
    assert result['passed'], 'Audit cleanup failed'
    print(json.dumps(result))
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true', required=True)
    for name in ('context', 'runtime-helpers', 'output', 'docker', 'docker-socket', 'docker-config'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('image', 'artifact-sha256', 'context-sha256'):
        p.add_argument('--' + name, required=True)
    return p


if __name__ == '__main__':
    execute(parser().parse_args())
