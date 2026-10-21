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
    payload = artifact.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_digest:
        raise SystemExit('Artifact hash differs from its export; build again')
    files = {'hub.exs': payload,
             'LICENSE': (root / 'LICENSE').read_bytes(),
             'Dockerfile': (root / 'deploy/Dockerfile').read_bytes(),
             'health.exs': (root / 'deploy/health.exs').read_bytes(),
             'component.md': (root / 'components/hub/component.md').read_bytes(),
             'core-spec.md': (root / 'components/hub/core/spec.md').read_bytes(),
             'information-spec.md': (root / 'components/hub/information/spec.md').read_bytes(),
             'management-spec.md': (root / 'components/hub/management/spec.md').read_bytes(),
             'presentation-spec.md': (root / 'components/hub/presentation/spec.md').read_bytes(),
             'federation-spec.md': (root / 'components/hub/federation/spec.md').read_bytes(),
             'configuration-spec.md': (root / 'components/hub/configuration/spec.md').read_bytes(),
             'identity-spec.md': (root / 'components/hub/identity/spec.md').read_bytes(),
             'protocol-spec.md': (root / 'components/hub/protocol/spec.md').read_bytes(),
             'directory-spec.md': (root / 'components/hub/directory/spec.md').read_bytes(),
             'directory-queries.md': (root / 'components/hub/directory/queries.md').read_bytes(),
             'history-spec.md': (root / 'components/hub/history/spec.md').read_bytes(),
             'history-interface.md': (root / 'components/hub/history/interface.md').read_bytes(),
             'history-evaluator.md': (root / 'components/hub/history/evaluator.md').read_bytes(),
             'retrieval-spec.md': (root / 'components/hub/retrieval/spec.md').read_bytes(),
             'retrieval-index.md': (root / 'components/hub/retrieval/index.md').read_bytes(),
             'retrieval-interface.md': (root / 'components/hub/retrieval/interface.md').read_bytes(),
             'feedback-spec.md': (root / 'components/hub/feedback/spec.md').read_bytes(),
             'feedback-replay.md': (root / 'components/hub/feedback/replay.md').read_bytes(),
             'feedback-interface.md': (root / 'components/hub/feedback/interface.md').read_bytes(),
             'archive-spec.md': (root / 'components/hub/archive/spec.md').read_bytes(),
             'archive-interface.md': (root / 'components/hub/archive/interface.md').read_bytes(),
             'evidence-spec.md': (root / 'components/hub/evidence/spec.md').read_bytes()}
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
