"""Prepare or execute one frozen, immutable-image core qualification ladder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys



def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true', help='Freeze inputs and commands; never starts a process')
    mode.add_argument('--execute', action='store_true', help='Execute the previously reviewed frozen plan')
    for name in ('repo-root', 'work'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--image')
    for name in ('image-manifest', 'legacy-hub', 'published-schema', 'published-openapi', 'producer-report'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--artifact-sha256')
    p.add_argument('--eventing-rest-url', default='http://127.0.0.1:18082')
    a = p.parse_args()
    root, work = a.repo_root.resolve(), a.work.resolve()
    if a.prepare:
        assert all(getattr(a, k) for k in ('image', 'image_manifest', 'legacy_hub', 'published_schema',
                                          'published_openapi', 'producer_report', 'artifact_sha256'))
        assert re.fullmatch(r'sha256:[a-f0-9]{64}', a.image), 'Require immutable image configuration ID'
        manifest = a.image_manifest.resolve()
        assert json.loads(manifest.read_text())['files']['hub.exs'] == a.artifact_sha256
        assert not work.exists(), 'Fresh qualification directory required'
        frozen = work / 'frozen'
        frozen.mkdir(parents=True, mode=0o700)
        inputs = {}
        for subtree in ('tests', 'scripts', 'components'):
            for source in sorted((root / subtree).rglob('*')):
                if not source.is_file() or '__pycache__' in source.parts or source.suffix not in (
                        '.py', '.c', '.exs', '.json', '.md', '.yaml', '.yml', '.sh'):
                    continue
                relative = source.relative_to(root)
                target = frozen / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                inputs[str(relative)] = sha(target)
        exports = work / 'exports'
        exports.mkdir()
        for source, name in ((a.published_schema, 'schema.json'), (a.published_openapi, 'openapi.json')):
            shutil.copyfile(source, exports / name)
        shutil.copyfile(manifest, work / 'image-manifest.json')
        shutil.copyfile(a.producer_report, work / 'producer-report.json')
        shutil.copyfile(Path(__file__), work / 'driver.py')
        legacy = a.legacy_hub.resolve()
        base = ['--image', a.image, '--image-manifest', str(work / 'image-manifest.json'),
                '--eventing-rest-url', a.eventing_rest_url, '--with-model']
        jobs = [
            ('foundation', 'foundation_acceptance.py', ['--image', a.image, '--protocol-version', '2', '--protocol-profile', '2.1']),
            ('wire', 'protocol_acceptance.py', ['--image', a.image, '--command', '[]', '--profile-version', '2.1.0',
                '--published-schema', str(exports / 'schema.json'), '--published-openapi', str(exports / 'openapi.json'),
                '--port-lock', str(work / 'foundation-port.lock')])]
        for name, file, extra in (
                ('multi', 'multi_acceptance.py', []), ('store-move', 'multi_store_move.py', []),
                ('move-no-default', 'multi_store_move.py', ['--no-default']), ('hot', 'multi_hot.py', []),
                ('backend-models', 'multi_model_capabilities.py', []),
                ('aliases', 'multi_aliases.py', ['--legacy-hub', str(legacy)]),
                ('retirement', 'multi_agent_retirement.py', []),
                ('retirement-faults', 'multi_agent_retirement_faults.py', []), ('registry', 'multi_registry_guard.py', [])):
            jobs.append((name, file, base + extra + ['--keep-work', str(work / (name + '-work'))]))
        jobs.append(('auth', 'auth_lifecycle.py', ['--image', a.image, '--image-manifest', str(work / 'image-manifest.json')]))
        jobs.append(('workflow-upgrade', 'multi_workflow_upgrade.py', ['--image', a.image,
            '--image-manifest', str(work / 'image-manifest.json'), '--producer-report', str(work / 'producer-report.json'),
            '--producer-root', str(root), '--producer-command', json.dumps(['elixir', str(legacy)]),
            '--work-root', str(work / 'workflow-work')]))
        plan = {'schema': 'adhd/image-core-plan@1', 'started': False, 'artifact_sha256': a.artifact_sha256,
            'image_config_identity': a.image, 'canonical_manifest_sha256': sha(work / 'image-manifest.json'),
            'legacy_sha256': sha(legacy), 'legacy_hub': str(legacy), 'driver_sha256': sha(work / 'driver.py'),
            'frozen_inputs': inputs, 'bound_inputs': {str(f.relative_to(work)): sha(f) for f in (
                work / 'image-manifest.json', work / 'producer-report.json', exports / 'schema.json', exports / 'openapi.json')},
            'first_two_serial': True, 'parallelism_after_first_two': 2, 'fail_fast': True, 'runs_per_suite': 1,
            'jobs': [{'name': n, 'script': f, 'arguments': v} for n, f, v in jobs]}
        (work / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        print('PREPARED image core13; no execution')
        return
    plan = json.loads((work / 'plan.json').read_text())
    assert sha(work / 'driver.py') == plan['driver_sha256']
    assert sha(Path(plan['legacy_hub'])) == plan['legacy_sha256']
    frozen = work / 'frozen'
    assert all(sha(frozen / path) == digest for path, digest in plan['frozen_inputs'].items())
    assert all(sha(work / path) == digest for path, digest in plan['bound_inputs'].items())
    sys.path.insert(0, str(frozen / "tests"))
    from container_fixture import OwnedImage
    from multi_eventing_matrix import bounded_jobs
    custody = OwnedImage(plan['image_config_identity'], work / 'image-manifest.json', work)
    custody.verify()
    assert custody.image_id == plan['image_config_identity']
    assert custody.manifest['files']['hub.exs'] == plan['artifact_sha256']
    env = os.environ.copy()
    env['PYTHONPATH'] = str(frozen / 'tests')
    def run(job):
        name = job['name']
        report = work / (name + '.json')
        print('START', name, flush=True)
        with (work / (name + '.log')).open('w') as log:
            result = subprocess.run([sys.executable, str(frozen / 'tests' / job['script']),
                *job['arguments'], '--report', str(report)], cwd=frozen, env=env, stdout=log, stderr=subprocess.STDOUT)
        print('DONE', name, result.returncode, flush=True)
        return {'name': name, 'exit_code': result.returncode, 'report': report.name,
            'report_sha256': sha(report) if report.exists() else None, 'log_sha256': sha(work / (name + '.log'))}
    results = []
    for job in plan['jobs'][:2]:
        results.append(run(job))
        if results[-1]['exit_code']:
            break
    if len(results) == 2 and all(row['exit_code'] == 0 for row in results):
        results += bounded_jobs(plan['jobs'][2:], run, 2, True)
    unrun = [job['name'] for job in plan['jobs'] if job['name'] not in {r['name'] for r in results}]
    unchanged = (all(sha(frozen / path) == digest for path, digest in plan['frozen_inputs'].items()) and
                 all(sha(work / path) == digest for path, digest in plan['bound_inputs'].items()))
    value = {'schema': 'adhd/image-core-matrix@1', 'passed': unchanged and not unrun and all(r['exit_code'] == 0 for r in results),
        'image_config_identity': custody.image_id, 'artifact_sha256': plan['artifact_sha256'],
        'canonical_manifest_sha256': plan['canonical_manifest_sha256'], 'plan_sha256': sha(work / 'plan.json'),
        'frozen_inputs_unchanged': unchanged, 'planned_suites': [j['name'] for j in plan['jobs']],
        'executed_suites': [r['name'] for r in results], 'unrun_suites': unrun, 'results': results}
    (work / 'matrix.json').write_text(json.dumps(value, indent=2) + '\n')
    sys.exit(0 if value['passed'] else 1)


if __name__ == '__main__':
    main()
