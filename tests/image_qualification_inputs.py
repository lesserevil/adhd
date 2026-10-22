"""Read-only exact admitted-image authority; live-root drift is never authority."""
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reviewed_payload(manifest_path, admission_path, expected_admission_sha, image, artifact, payload_path=None):
    manifest_path, admission_path = Path(manifest_path), Path(admission_path)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    assert manifest['schema'] == 'adhd/container-inputs@1'
    assert manifest['files']['hub.exs'] == artifact
    assert all(re.fullmatch('[a-f0-9]{64}', value) for value in manifest['files'].values())
    assert sha(admission_path) == expected_admission_sha
    admission = json.loads(admission_path.read_text())
    assert admission['passed'] is True and admission['image_config_identity'] == image
    assert admission['artifact_sha256'] == artifact and admission['canonical_manifest_sha256'] == sha(manifest_path)
    audit = admission['payload_audit']
    assert audit['passed'] is True and audit['image_id'] == image
    assert audit['artifact_sha256'] == artifact and audit['canonical_manifest_sha256'] == sha(manifest_path)
    payload_path = Path(payload_path or manifest_path.with_name('payload.tar'))
    assert payload_path.stat().st_size <= 32 * 1024 * 1024
    contents = {}
    seen = set()
    total_bytes = 0
    with tarfile.open(payload_path, mode="r:") as archive:
        members = archive.getmembers()
        assert len(members) <= 512
        for member in members:
            path = PurePosixPath(member.name)
            assert str(path) == member.name and not path.is_absolute()
            assert all(part not in ('.', '..') for part in path.parts) and path.parts[0] == 'app'
            assert member.name not in seen
            seen.add(member.name)
            assert member.isdir() or member.isfile(), 'Reject redirected archive entries'
            if member.isfile():
                assert 0 <= member.size <= 8 * 1024 * 1024
                total_bytes += member.size
                assert total_bytes <= 16 * 1024 * 1024
                contents[member.name] = archive.extractfile(member).read()
    expected = {'app/' + name for name in manifest['files'] if name != 'Dockerfile'} | {'app/manifest.json'}
    # The payload audit counts application files, excluding manifest metadata.
    assert set(contents) == expected and len(contents) - 1 == audit['actual_app_files']
    assert contents['app/manifest.json'] == raw
    assert sha(manifest_path.with_name('Dockerfile')) == manifest['files']['Dockerfile']
    for name, digest in manifest['files'].items():
        if name != 'Dockerfile':
            assert hashlib.sha256(contents['app/' + name]).hexdigest() == digest
    specifications = {name[len('app/specification/'):]: body for name, body in contents.items()
                      if name.startswith('app/specification/')}
    assert len(specifications) == audit['canonical_specifications']
    return {'specifications': specifications, 'artifact_bytes': contents['app/hub.exs'], 'audit': audit, 'payload_sha256': sha(payload_path),
            'component_lock_identity': admission['component_lock_identity'], 'admission_sha256': expected_admission_sha}


def freeze_inputs(root, frozen, specification_snapshot=None):
    """Current authored helpers plus the selected target's normative bytes."""
    root, frozen = Path(root), Path(frozen)
    inputs = {}
    subtrees = ('tests', 'scripts') if specification_snapshot is not None else ('tests', 'scripts', 'components')
    for subtree in subtrees:
        for source in sorted((root / subtree).rglob('*')):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix not in (
                    '.py', '.c', '.exs', '.json', '.md', '.yaml', '.yml', '.sh'):
                continue
            relative = source.relative_to(root)
            target = frozen / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            inputs[str(relative)] = sha(target)
    examples = root / 'docs/protocol/examples.json'
    if examples.is_file():
        relative = Path('docs/protocol/examples.json')
        target = frozen / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(examples, target)
        inputs[str(relative)] = sha(target)
    drift = {}
    if specification_snapshot is not None:
        for name, body in specification_snapshot.items():
            relative = Path('components/hub') / name
            target = frozen / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            inputs[str(relative)] = sha(target)
            current = root / relative
            current_sha = sha(current) if current.is_file() else None
            if current_sha != inputs[str(relative)]:
                drift[str(relative)] = {'target_sha256': inputs[str(relative)], 'live_root_sha256': current_sha}
    return inputs, drift


def verify_frozen_inputs(frozen, inputs):
    """Verify the complete immutable tree, including directories and aliases."""
    frozen = Path(frozen)
    assert frozen.is_absolute() and frozen.is_dir() and not frozen.is_symlink()
    assert frozen.resolve(strict=True) == frozen, 'Frozen root or ancestor redirected'
    expected_dirs = set()
    for name, digest in inputs.items():
        path = PurePosixPath(name)
        assert not path.is_absolute() and str(path) == name and path.parts
        assert all(part not in ('.', '..') for part in path.parts)
        assert re.fullmatch('[a-f0-9]{64}', digest)
        expected_dirs.update(str(parent) for parent in path.parents if str(parent) != '.')
    observed, observed_dirs = set(), set()
    for path in frozen.rglob('*'):
        info = path.lstat()
        assert not stat.S_ISLNK(info.st_mode), 'Frozen member redirected'
        relative = str(path.relative_to(frozen))
        if stat.S_ISDIR(info.st_mode):
            observed_dirs.add(relative)
        else:
            assert stat.S_ISREG(info.st_mode), 'Frozen special file'
            observed.add(relative)
    assert observed == set(inputs), 'Frozen file set changed'
    assert observed_dirs == expected_dirs, 'Frozen directory set changed'
    for name, digest in inputs.items():
        path = frozen / name
        before = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            assert stat.S_ISREG(opened.st_mode)
            assert (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino)
            value = hashlib.sha256()
            while True:
                body = os.read(descriptor, 1024 * 1024)
                if not body:
                    break
                value.update(body)
            after = path.lstat()
            assert (after.st_dev, after.st_ino, after.st_size) == (opened.st_dev, opened.st_ino, opened.st_size)
            assert value.hexdigest() == digest, 'Frozen file content changed'
        finally:
            os.close(descriptor)
    return True


def prepare_runtime_cwd(work, frozen, inputs):
    """Mutable outputs stay outside the immutable import/specification tree."""
    runtime = Path(work) / 'runtime'
    runtime.mkdir(mode=0o700)
    fixtures = {}
    for name in ('docs/protocol/examples.json',):
        if name in inputs:
            target = runtime / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(frozen) / name, target)
            fixtures[str(target.relative_to(work))] = sha(target)
    return runtime, fixtures
