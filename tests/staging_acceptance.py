#!/usr/bin/env python3
"""Check container staging binds the accepted artifact to current evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild-result', required=True)
    parser.add_argument('--acceptance-report', required=True)
    parser.add_argument('--context', required=True, help='Previously staged passing context')
    parser.add_argument('--report', default='verification/federation-staging.json')
    args = parser.parse_args()
    parent = Path('_build/federation/staging-checks').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    result = json.loads(Path(args.rebuild_result).read_text())
    acceptance = json.loads(Path(args.acceptance_report).read_text())
    cases = []
    for name in ('stale-receipt', 'changed-artifact', 'failed-acceptance'):
        rebuild = json.loads(json.dumps(result))
        report = dict(acceptance)
        if name == 'stale-receipt':
            rebuild['result']['receipt_identity'] = 'sha256:' + '0' * 64
        elif name == 'changed-artifact':
            changed = root / 'changed.exs'
            changed.write_bytes(Path(rebuild['result']['artifact']).read_bytes() + b'\n')
            rebuild['result']['artifact'] = str(changed)
        else:
            report['passed'] = False
        result_path, report_path = root / (name + '-result.json'), root / (name + '-report.json')
        result_path.write_text(json.dumps(rebuild))
        report_path.write_text(json.dumps(report))
        run = subprocess.run([sys.executable, 'scripts/stage_container.py', '--rebuild-result',
                              str(result_path), '--acceptance-report', str(report_path),
                              '--output', str(root / name)], capture_output=True, text=True)
        assert run.returncode != 0 and not (root / name).exists(), name
        expected = {'stale-receipt': 'not bound to the current',
                    'changed-artifact': 'Artifact hash differs',
                    'failed-acceptance': 'Expected passing independent acceptance'}[name]
        assert expected in run.stderr + run.stdout, run.stderr
        cases.append({'case': name, 'passed': True})
    legacy = root / 'legacy-export.json'
    legacy.write_text(json.dumps({'component': 'components/hub',
                                'artifact': result['result']['artifact'],
                                'artifact_reference': {'identity': {'digest': acceptance['artifact_sha256']}}}))
    output = root / 'legacy-context'
    subprocess.run([sys.executable, 'scripts/stage_container.py', '--export', str(legacy),
                    '--output', str(output)], check=True, stdout=subprocess.DEVNULL)
    for name in ('payload.tar', 'manifest.json', 'Dockerfile'):
        assert (output / name).read_bytes() == (Path(args.context) / name).read_bytes(), name
    cases.append({'case': 'legacy-export-and-rebuild-input-stage-identical-bytes', 'passed': True})
    Path(args.report).write_text(json.dumps({'schema': 'adhd/staging-acceptance@1', 'passed': True,
                                            'cases': cases, 'artifact_sha256': acceptance['artifact_sha256'],
                                            'payload_sha256': hashlib.sha256((output / 'payload.tar').read_bytes()).hexdigest()},
                                           indent=2) + '\n')
    print('PASS staging integrity and deterministic legacy compatibility')


if __name__ == '__main__':
    main()
