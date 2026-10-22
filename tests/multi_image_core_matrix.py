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
from image_qualification_inputs import verify_frozen_inputs



def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_passed(path):
    try:
        value = json.loads(Path(path).read_text())
        return isinstance(value, dict) and value.get('passed') is True
    except (OSError, ValueError, TypeError):
        return False


def reviewed_plan(work, expected, running_driver):
    assert expected and sha(work / 'plan.json') == expected, 'Require reviewed exact plan hash'
    plan = json.loads((work / 'plan.json').read_text())
    assert sha(Path(running_driver)) == sha(work / 'driver.py') == plan['driver_sha256'], 'Running driver differs from reviewed driver'
    return plan


def claim_execution(work, plan_sha256, driver_sha256, marker_name="execution-started.json"):
    descriptor = os.open(work / marker_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, 'w') as receipt:
        json.dump({'plan_sha256': plan_sha256, 'driver_sha256': driver_sha256}, receipt)
        receipt.flush()
        os.fsync(receipt.fileno())
    directory = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true', help='Freeze inputs and commands; never starts a process')
    mode.add_argument('--execute', action='store_true', help='Execute the previously reviewed frozen plan')
    for name in ('repo-root', 'work'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--helper-root', type=Path, help='Explicit current-root plus reviewed test-only overlay to freeze')
    p.add_argument('--image')
    for name in ('image-manifest', 'legacy-hub', 'published-schema', 'published-openapi', 'producer-report', 'admission-manifest'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--artifact-sha256')
    p.add_argument('--admission-sha256')
    p.add_argument('--plan-sha256', help='Required reviewed exact plan digest for execution')
    p.add_argument('--eventing-rest-url', default='http://127.0.0.1:18082')
    a = p.parse_args()
    sys.dont_write_bytecode = True
    root, work = a.repo_root.resolve(), a.work.resolve()
    if a.prepare:
        assert all(getattr(a, k) for k in ('image', 'image_manifest', 'legacy_hub', 'published_schema',
                                          'published_openapi', 'producer_report', 'artifact_sha256', 'admission_manifest', 'admission_sha256'))
        assert re.fullmatch(r'sha256:[a-f0-9]{64}', a.image), 'Require immutable image configuration ID'
        manifest = a.image_manifest.resolve()
        from image_qualification_inputs import reviewed_payload, freeze_inputs, verify_frozen_inputs, prepare_runtime_cwd
        selected = reviewed_payload(manifest, a.admission_manifest, a.admission_sha256, a.image, a.artifact_sha256)
        audit = selected['audit']
        locked_specs = selected['specifications']
        assert not work.exists(), 'Fresh qualification directory required'
        frozen = work / 'frozen'
        frozen.mkdir(parents=True, mode=0o700)
        inputs, live_spec_drift = freeze_inputs(a.helper_root.resolve() if a.helper_root else root, frozen, locked_specs)
        verify_frozen_inputs(frozen, inputs)
        runtime, runtime_data = prepare_runtime_cwd(work, frozen, inputs)
        binding = work / 'hub-binding.exs'
        binding.write_bytes(selected['artifact_bytes'])
        exports = work / 'exports'
        exports.mkdir()
        for source, name in ((a.published_schema, 'schema.json'), (a.published_openapi, 'openapi.json')):
            shutil.copyfile(source, exports / name)
        shutil.copyfile(manifest, work / 'image-manifest.json')
        shutil.copyfile(a.producer_report, work / 'producer-report.json')
        shutil.copyfile(a.admission_manifest, work / 'admission-manifest.json')
        shutil.copyfile(Path(__file__), work / 'driver.py')
        legacy = a.legacy_hub.resolve()
        base = ['--image', a.image, '--image-manifest', str(work / 'image-manifest.json'),
                '--eventing-rest-url', a.eventing_rest_url, '--with-model']
        jobs = [
            ('foundation', 'foundation_acceptance.py', ['--image', a.image, '--protocol-version', '2', '--protocol-profile', '2.1']),
            ('wire', 'protocol_acceptance.py', ['--image', a.image, '--command', json.dumps(['elixir', str(binding)]), '--profile-version', '2.1.0',
                '--published-schema', str(exports / 'schema.json'), '--published-openapi', str(exports / 'openapi.json'),
                '--port-lock', str(root / '_build/roadmap/foundation-port.lock')])]
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
            'admission_manifest_sha256': a.admission_sha256, 'payload_audit': audit,
            'payload_tar_sha256': selected['payload_sha256'], 'target_component_lock_identity': selected['component_lock_identity'],
            'live_root_specification_drift': live_spec_drift,
            'scope': 'Admitted38 recovery/backend normative payload; live-root presentation changes excluded and unqualified',
            'locked_specifications': {name: hashlib.sha256(body).hexdigest() for name, body in locked_specs.items()},
            'legacy_sha256': sha(legacy), 'legacy_hub': str(legacy), 'driver_sha256': sha(work / 'driver.py'),
            'runtime_cwd': str(runtime), 'outer_child_timeout_seconds': None,
            'child_timeout_policy': 'Existing authored harness bounds only; no additional driver wall-clock cap; an incomplete child cannot pass',
            'wire_artifact_command_is_report_binding_only': True,
            'frozen_inputs': inputs, 'bound_inputs': {str(f.relative_to(work)): sha(f) for f in (
                work / 'image-manifest.json', work / 'producer-report.json', work / 'admission-manifest.json', exports / 'schema.json', exports / 'openapi.json', binding)} | runtime_data,
            'first_two_serial': True, 'parallelism_after_first_two': 2, 'fail_fast': True, 'runs_per_suite': 1,
            'foundation_flock_sha256': sha(Path('/usr/bin/flock')),
            'jobs': [{'name': n, 'script': f, 'prefix': ['/usr/bin/flock', str(root / '_build/roadmap/foundation-port.lock')] if n == 'foundation' else [], 'arguments': v} for n, f, v in jobs]}
        (work / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        print('PREPARED image core13; no execution')
        return
    plan = reviewed_plan(work, a.plan_sha256, __file__)
    assert sha(Path(plan['legacy_hub'])) == plan['legacy_sha256']
    frozen = work / 'frozen'
    verify_frozen_inputs(frozen, plan['frozen_inputs'])
    assert sha(Path('/usr/bin/flock')) == plan['foundation_flock_sha256']
    assert all(sha(work / path) == digest for path, digest in plan['bound_inputs'].items())
    sys.path.insert(0, str(frozen / "tests"))
    claim_execution(work, a.plan_sha256, plan['driver_sha256'])
    from container_fixture import OwnedImage
    from multi_eventing_matrix import bounded_jobs
    custody = OwnedImage(plan['image_config_identity'], work / 'image-manifest.json', work)
    custody.verify()
    assert custody.image_id == plan['image_config_identity']
    assert custody.manifest['files']['hub.exs'] == plan['artifact_sha256']
    env = os.environ.copy()
    env['PYTHONPATH'] = str(frozen / 'tests')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPYCACHEPREFIX'] = str(work / 'pycache')
    def run(job):
        name = job['name']
        report = work / (name + '.json')
        verify_frozen_inputs(frozen, plan['frozen_inputs'])
        assert all(sha(work / path) == digest for path, digest in plan['bound_inputs'].items())
        assert not report.exists(), 'Refuse stale report reuse'
        print('START', name, flush=True)
        with (work / (name + '.log')).open('w') as log:
            result = subprocess.run([*job['prefix'], sys.executable, str(frozen / 'tests' / job['script']),
                *job['arguments'], '--report', str(report)], cwd=plan['runtime_cwd'], env=env, stdout=log, stderr=subprocess.STDOUT)
        actual_report_passed = report_passed(report)
        qualified = result.returncode == 0 and actual_report_passed
        print('DONE', name, result.returncode, 'report_passed', actual_report_passed, flush=True)
        return {'name': name, 'exit_code': 0 if qualified else 1, 'exit_code_kind': 'qualification',
            'process_exit_code': result.returncode, 'report_passed': actual_report_passed, 'report': report.name,
            'report_sha256': sha(report) if report.exists() else None, 'log_sha256': sha(work / (name + '.log'))}
    results = []
    for job in plan['jobs'][:2]:
        results.append(run(job))
        if results[-1]['exit_code']:
            break
    if len(results) == 2 and all(row['exit_code'] == 0 for row in results):
        results += bounded_jobs(plan['jobs'][2:], run, 2, True)
    unrun = [job['name'] for job in plan['jobs'] if job['name'] not in {r['name'] for r in results}]
    unchanged = (sha(Path(plan['legacy_hub'])) == plan['legacy_sha256'] and verify_frozen_inputs(frozen, plan['frozen_inputs']) and sha(Path('/usr/bin/flock')) == plan['foundation_flock_sha256'] and
                 all(sha(work / path) == digest for path, digest in plan['bound_inputs'].items()))
    value = {'schema': 'adhd/image-core-matrix@1', 'passed': unchanged and not unrun and all(r['exit_code'] == 0 for r in results),
        'image_config_identity': custody.image_id, 'artifact_sha256': plan['artifact_sha256'],
        'canonical_manifest_sha256': plan['canonical_manifest_sha256'],
        'admission_manifest_sha256': plan['admission_manifest_sha256'], 'payload_audit': plan['payload_audit'],
        'live_root_specification_drift': plan['live_root_specification_drift'], 'scope': plan['scope'],
        'payload_tar_sha256': plan['payload_tar_sha256'],
        'locked_specifications': plan['locked_specifications'], 'plan_sha256': sha(work / 'plan.json'),
        'frozen_inputs_unchanged': unchanged, 'planned_suites': [j['name'] for j in plan['jobs']],
        'executed_suites': [r['name'] for r in results], 'unrun_suites': unrun, 'results': results}
    (work / 'matrix.json').write_text(json.dumps(value, indent=2) + '\n')
    sys.exit(0 if value['passed'] else 1)


if __name__ == '__main__':
    main()
