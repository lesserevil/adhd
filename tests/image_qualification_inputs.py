"""Read-only exact admitted-image authority; live-root drift is never authority."""
import hashlib
import json
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
    with tarfile.open(payload_path) as archive:
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
                contents[member.name] = archive.extractfile(member).read()
    expected = {'app/' + name for name in manifest['files'] if name != 'Dockerfile'} | {'app/manifest.json'}
    assert set(contents) == expected and len(contents) - 1 == audit['actual_app_files']
    assert contents['app/manifest.json'] == raw
    assert sha(manifest_path.with_name('Dockerfile')) == manifest['files']['Dockerfile']
    for name, digest in manifest['files'].items():
        if name != 'Dockerfile':
            assert hashlib.sha256(contents['app/' + name]).hexdigest() == digest
    specifications = {name[len('app/specification/'):]: body for name, body in contents.items()
                      if name.startswith('app/specification/')}
    assert len(specifications) == audit['canonical_specifications']
    return {'specifications': specifications, 'audit': audit, 'payload_sha256': sha(payload_path),
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
