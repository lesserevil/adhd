#!/usr/bin/env python3
"""Stage Agentic Distributed Harness Depot (ADHD) for Docker from a verified Literate AI artifact export."""
import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', default='generated/artifacts/hub/execution.json')
    parser.add_argument('--output', default='_build/container')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['litai', 'verify'], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('Project verification failed; run litai verify and refresh the build receipt')
    evidence = json.loads(result.stdout)
    if not evidence.get('result', {}).get('ok'):
        raise SystemExit('Project verification is not passing; run litai verify before staging')
    export = json.loads(Path(args.export).read_text())
    if export.get('component') != 'components/hub':
        raise SystemExit('Expected a hub artifact export')
    if export.get('schema') == 'adhd/artifact-export@1':
        receipt = json.loads((root / 'verification/current.json').read_text())
        if export.get('receipt_identity') != receipt.get('receipt_identity'):
            raise SystemExit('Export is bound to an older lifecycle receipt; build again')
    artifact = Path(export['artifact'])
    payload = artifact.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != export['artifact_reference']['identity']['digest']:
        raise SystemExit('Artifact hash differs from its export; build again')
    files = {'hub.exs': payload,
             'Dockerfile': (root / 'deploy/Dockerfile').read_bytes(),
             'health.exs': (root / 'deploy/health.exs').read_bytes(),
             'component.md': (root / 'components/hub/component.md').read_bytes()}
    # Package every authored behavioral root, preserving its namespace.
    frontmatter = (root / 'components/hub/component.md').read_text().split('---', 2)[1]
    roots = frontmatter.split('specification_roots:\n', 1)[1].splitlines()
    for line in roots:
        if not line.startswith('  - '):
            break
        relative = Path(line[4:].strip())
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('Unsafe specification root')
        files[relative.as_posix()] = (root / 'components/hub' / relative).read_bytes()

    manifest = {'schema': 'adhd/container-inputs@1', 'files': {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    manifest_bytes = (json.dumps(manifest, indent=2) + '\n').encode()
    with tarfile.open(output / 'payload.tar', 'w', format=tarfile.USTAR_FORMAT) as archive:
        directory = tarfile.TarInfo('app')
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        payloads = {name: content for name, content in files.items() if name != 'Dockerfile'}
        payloads['manifest.json'] = manifest_bytes
        directories = set()
        for name in payloads:
            directories.update(parent.as_posix() for parent in Path(name).parents if parent.as_posix() != '.')
        for name in sorted(directories, key=lambda value: (value.count('/'), value)):
            info = tarfile.TarInfo('app/' + name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            archive.addfile(info)
        for name, content in sorted(payloads.items()):
            info = tarfile.TarInfo('app/' + name)
            info.mode = 0o644
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    (output / 'Dockerfile').write_bytes(files['Dockerfile'])
    (output / 'manifest.json').write_bytes(manifest_bytes)
    for path in output.iterdir():
        path.chmod(0o644)
        os.utime(path, (0, 0))
    print(json.dumps({'context': str(output.resolve()), 'artifact_sha256': digest}))


if __name__ == '__main__':
    main()
