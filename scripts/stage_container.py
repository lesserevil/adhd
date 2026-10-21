#!/usr/bin/env python3
"""Stage Agentic Distributed Harness Depot (ADHD) for Docker from a verified Literate AI artifact export."""
import argparse
import hashlib
import io
import json
import os
import subprocess
import stat
import tarfile
from pathlib import Path


def read_regular(path):
    """Read a regular, non-symlink input without opening device/FIFO payloads."""
    path = Path(path)
    for parent in path.parents:
        if parent.is_symlink():
            raise SystemExit(f'Symlink input directory is not allowed: {parent}')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SystemExit(f'Expected regular staging input: {path}')
            content = stream.read()
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise SystemExit(f'Staging input changed during read: {path}')
            return content
    except OSError as error:
        raise SystemExit(f'Cannot read regular staging input {path}: {error}') from error


def specification_files(component):
    """Include the complete authored Markdown tree; generated files stay outside it."""
    component = Path(component)
    if component.is_symlink() or not component.is_dir():
        raise SystemExit('Expected a regular specification directory')
    files = {}
    def fail_walk(error):
        raise SystemExit(f'Cannot enumerate specification inputs: {error}')

    for directory, children, names in os.walk(component, followlinks=False, onerror=fail_walk):
        for name in children:
            if (Path(directory) / name).is_symlink():
                raise SystemExit(f'Symlink specification directory is not allowed: {name}')
        for name in sorted(names):
            if name.endswith('.md'):
                path = Path(directory) / name
                files['specification/' + path.relative_to(component).as_posix()] = read_regular(path)
    if 'specification/component.md' not in files:
        raise SystemExit('Missing canonical component specification')
    return dict(sorted(files.items()))


def write_context(files, output):
    manifest = {'schema': 'adhd/container-inputs@1', 'files': {
        name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest_bytes = (json.dumps(manifest, indent=2) + '\n').encode()
    with tarfile.open(output / 'payload.tar', 'w', format=tarfile.USTAR_FORMAT) as archive:
        payloads = {name: content for name, content in files.items() if name != 'Dockerfile'}
        payloads['manifest.json'] = manifest_bytes
        directories = {'app'}
        for name in payloads:
            directories.update(str(parent) for parent in Path('app', name).parents if str(parent) != '.')
        for name in sorted(directories, key=lambda value: (value.count('/'), value)):
            directory = tarfile.TarInfo(name)
            directory.type = tarfile.DIRTYPE
            directory.mode = 0o755
            archive.addfile(directory)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--export', help='Literate AI artifact export (the default input)')
    source.add_argument('--rebuild-result', help='Passing litai rebuild JSON result for retained-source qualification')
    parser.add_argument('--acceptance-report', help='Passing independent hub acceptance report, required with --rebuild-result')
    parser.add_argument('--output', default='_build/container')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['litai', 'verify'], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('Project verification failed; run litai verify and refresh the build receipt')
    evidence = json.loads(result.stdout)
    if not evidence.get('result', {}).get('ok'):
        raise SystemExit('Project verification is not passing; run litai verify before staging')
    if args.rebuild_result:
        if not args.acceptance_report:
            parser.error('--rebuild-result requires --acceptance-report')
        envelope = json.loads(Path(args.rebuild_result).read_text())
        rebuild = envelope.get('result', {})
        definition = json.loads((root / 'literate.project.json').read_text())
        receipt = json.loads((root / definition['test_receipt']).read_text())
        if (envelope.get('command') != 'rebuild' or envelope.get('ok') is not True or
                rebuild.get('passed') is not True or rebuild.get('specification') != 'components/hub' or
                rebuild.get('receipt_identity') != receipt.get('receipt_identity') or
                rebuild.get('lifecycle_result_identity') != receipt['receipt'].get('result') or
                rebuild.get('lifecycle_request_identity') != receipt.get('lifecycle_request_identity')):
            raise SystemExit('Rebuild result is not bound to the current passing hub receipt')
        acceptance = json.loads(Path(args.acceptance_report).read_text())
        if acceptance.get('passed') is not True or not acceptance.get('artifact_sha256'):
            raise SystemExit('Expected passing independent acceptance with an artifact hash')
        artifact = Path(rebuild['artifact'])
        expected_digest = acceptance['artifact_sha256']
    else:
        if args.acceptance_report:
            parser.error('--acceptance-report is only used with --rebuild-result')
        export = json.loads(Path(args.export or 'generated/artifacts/hub/execution.json').read_text())
        if export.get('component') != 'components/hub':
            raise SystemExit('Expected a hub artifact export')
        artifact = Path(export['artifact'])
        expected_digest = export['artifact_reference']['identity']['digest']
    if not artifact.is_file() or artifact.is_symlink():
        raise SystemExit('Expected a regular hub artifact file')
    payload = read_regular(artifact)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_digest:
        raise SystemExit('Artifact hash differs from its export; build again')
    files = {'hub.exs': payload,
             'LICENSE': read_regular(root / 'LICENSE'),
             'Dockerfile': read_regular(root / 'deploy/Dockerfile'),
             'health.exs': read_regular(root / 'deploy/health.exs'),
             'component.md': read_regular(root / 'components/hub/component.md'),
             'core-spec.md': read_regular(root / 'components/hub/core/spec.md'),
             'information-spec.md': read_regular(root / 'components/hub/information/spec.md'),
             'management-spec.md': read_regular(root / 'components/hub/management/spec.md'),
             'presentation-spec.md': read_regular(root / 'components/hub/presentation/spec.md'),
             'federation-spec.md': read_regular(root / 'components/hub/federation/spec.md'),
             'configuration-spec.md': read_regular(root / 'components/hub/configuration/spec.md'),
             'identity-spec.md': read_regular(root / 'components/hub/identity/spec.md'),
             'protocol-spec.md': read_regular(root / 'components/hub/protocol/spec.md'),
             'directory-spec.md': read_regular(root / 'components/hub/directory/spec.md'),
             'directory-queries.md': read_regular(root / 'components/hub/directory/queries.md'),
             'history-spec.md': read_regular(root / 'components/hub/history/spec.md'),
             'history-interface.md': read_regular(root / 'components/hub/history/interface.md'),
             'history-evaluator.md': read_regular(root / 'components/hub/history/evaluator.md'),
             'retrieval-spec.md': read_regular(root / 'components/hub/retrieval/spec.md'),
             'retrieval-index.md': read_regular(root / 'components/hub/retrieval/index.md'),
             'retrieval-interface.md': read_regular(root / 'components/hub/retrieval/interface.md'),
             'feedback-spec.md': read_regular(root / 'components/hub/feedback/spec.md'),
             'feedback-replay.md': read_regular(root / 'components/hub/feedback/replay.md'),
             'feedback-interface.md': read_regular(root / 'components/hub/feedback/interface.md'),
             'archive-spec.md': read_regular(root / 'components/hub/archive/spec.md'),
             'archive-interface.md': read_regular(root / 'components/hub/archive/interface.md'),
             'evidence-spec.md': read_regular(root / 'components/hub/evidence/spec.md')}
    files.update(specification_files(root / "components/hub"))
    write_context(files, args.output)
    output = Path(args.output)
    print(json.dumps({'context': str(output.resolve()), 'artifact_sha256': digest}))


if __name__ == '__main__':
    main()
