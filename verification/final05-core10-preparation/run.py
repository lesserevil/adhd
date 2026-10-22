#!/usr/bin/env python3
"""Prepare then execute the unchanged failed/unrun core10 after three whole passes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
PREFIX = ('foundation', 'wire', 'store-move')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    spec = importlib.util.spec_from_file_location('original_core_guard', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows(parent):
    return [j for j in parent['jobs'] if j['name'] not in PREFIX]


def replace(value, old, new):
    return value.replace(str(old), str(new)) if isinstance(value, str) else value


def verify(work, plan):
    assert sha(Path(__file__)) == sha(work / 'run.py') == plan['driver_sha256']
    parent = Path(plan['parent_core'])
    guard = Path(plan['parent_guard'])
    assert sha(guard / 'plan.json') == plan['parent_guard_plan_sha256']
    assert sha(guard / 'guard.py') == plan['parent_guard_driver_sha256']
    original = load(guard / 'guard.py')
    original.verify(guard, json.loads((guard / 'plan.json').read_text()))
    assert original.inventory(work / 'frozen') == plan['frozen']
    old_tree = original.inventory(parent / 'frozen')
    assert old_tree['directories'] == plan['frozen']['directories']
    assert set(old_tree['files']) == set(plan['frozen']['files'])
    assert [name for name in old_tree['files'] if old_tree['files'][name] != plan['frozen']['files'][name]] == ['tests/multi_support.py']
    assert original.inventory(work / 'bound') == plan['bound']
    for name, digest in plan['runtime_fixtures'].items():
        assert sha(work / name) == digest
    for name, digest in plan['prefix_and_failure_files'].items():
        assert sha(parent / name) == digest
    for name, digest in plan['failure_audit_files'].items():
        assert sha(name) == digest
    source = json.loads((parent / 'plan.json').read_text())
    assert sha(parent / 'plan.json') == plan['parent_core_plan_sha256']
    expected = rows(source)
    assert len(expected) == len(plan['jobs']) == 10
    for old, new in zip(expected, plan['jobs']):
        assert {**old, 'arguments': [replace(x, parent, work) for x in old['arguments']]} == new
        assert sha(work / 'frozen/tests' / new['script']) == source['frozen_inputs']['tests/' + new['script']]
    assert plan['parallelism'] == 1 and plan['automatic_retries'] == 0
    return True


def prepare(args):
    parent = args.parent_core.absolute()
    guard = args.parent_guard.absolute()
    original = load(guard / 'guard.py')
    gp = json.loads((guard / 'plan.json').read_text())
    original.verify(guard, gp)
    p = json.loads((parent / 'plan.json').read_text())
    matrix = json.loads((parent / 'matrix.json').read_text())
    assert matrix['passed'] is False
    passed = {r['name'] for r in matrix['results'] if r['report_passed'] and r['process_exit_code'] == 0}
    assert passed == set(PREFIX)
    assert next(r for r in matrix['results'] if r['name'] == 'multi')['process_exit_code'] == 1
    work = args.work.absolute()
    assert not work.exists() and work.resolve() == work
    work.mkdir(mode=0o700, parents=True)
    shutil.copytree(parent / 'frozen', work / 'frozen')
    helper = args.bootstrap_helper.absolute()
    shutil.copyfile(helper, work / 'frozen/tests/multi_support.py')
    (work / 'bound').mkdir(mode=0o700)
    for name in p['bound_inputs']:
        target = work / name
        target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(parent / name, target)
    # The original auth entrypoint deliberately resolves this standard-library
    # script relative to CWD. Materialize exact already-frozen fixture bytes.
    runtime_script = work / 'runtime/scripts/configure_hub.py'
    runtime_script.parent.mkdir(exist_ok=True, parents=True)
    shutil.copyfile(work / 'frozen/scripts/configure_hub.py', runtime_script)
    runtime_script.chmod(0o444)
    (work / 'bound/docker-config').mkdir()
    (work / 'bound/docker-config/config.json').write_bytes(b'{}')
    shutil.copyfile(Path(__file__), work / 'run.py')
    fixtures = {name: sha(work / name) for name in p['bound_inputs']}
    fixtures['runtime/scripts/configure_hub.py'] = sha(runtime_script)
    prefix = {name: sha(parent / name) for name in ['matrix.json', 'plan.json', 'driver.py'] +
              [n + suffix for n in (*PREFIX, 'multi') for suffix in ('.json', '.log')]}
    plan = {'schema': 'adhd/compiled-core10-remainder@1', 'prepared': True, 'executed': False,
            'root_GO_required': True, 'parent_core': str(parent), 'parent_guard': str(guard),
            'parent_core_plan_sha256': sha(parent / 'plan.json'),
            'parent_guard_plan_sha256': sha(guard / 'plan.json'),
            'parent_guard_driver_sha256': sha(guard / 'guard.py'),
            'driver_sha256': sha(work / 'run.py'), 'image_config_identity': p['image_config_identity'],
            'artifact_sha256': p['artifact_sha256'], 'canonical_manifest_sha256': p['canonical_manifest_sha256'],
            'admission_sha256': p['admission_manifest_sha256'],
            'frozen': original.inventory(work / 'frozen'), 'bound': original.inventory(work / 'bound'),
            'runtime_fixtures': fixtures, 'prefix_and_failure_files': prefix,
            'failure_audit_files': {str(q): sha(q) for q in sorted(args.failure_proof.absolute().rglob('*')) if q.is_file()},
            'bootstrap_helper_sha256': sha(helper), 'bootstrap_overlay_only': 'tests/multi_support.py',
            'jobs': [{**j, 'arguments': [replace(x, parent, work) for x in j['arguments']]} for j in rows(p)],
            'whole_prefix': list(PREFIX), 'whole_prefix_checks': 35, 'failed_multi_partial_excluded': 8,
            'parallelism': 1, 'automatic_retries': 0, 'first_failure_stops': True,
            'timeout_policy': 'Original per-entrypoint bounds only; no new outer timeout',
            'provider_calls_authorized': 0,
            'scope': 'Fresh failed/unrun10 only, combined with three original whole35 prefix; original false aggregate preserved. Same final05 image, no source or assertion change.'}
    original.write(work / 'plan.json', (json.dumps(plan, indent=2) + '\n').encode())
    verify(work, plan)
    print(json.dumps({'prepared': True, 'executed': False, 'plan_sha256': sha(work / 'plan.json')}))


def absence(identifier):
    result = subprocess.run(['/usr/bin/docker', 'inspect', identifier], capture_output=True, timeout=30)
    assert result.returncode == 1 and result.stdout.strip() in (b'', b'[]') and re.fullmatch(
        r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)' + re.escape(identifier),
        result.stderr.decode(errors='replace').strip()), 'Recorded owned container absence unconfirmed'
    return {'identifier': identifier, 'returncode': result.returncode, 'stderr': result.stderr.decode()}


def runtime_handles(value):
    ids, names = set(), set()
    def visit(v):
        if isinstance(v, dict):
            if isinstance(v.get('container_lifecycle'), list):
                for event in v['container_lifecycle']:
                    if event.get('container_id'): ids.add(event['container_id'])
            if isinstance(v.get('payload_probe_lifecycle'), list):
                for event in v['payload_probe_lifecycle']:
                    names.add(event['owned_name'])
                    if event.get('container_id'): ids.add(event['container_id'])
            for child in v.values(): visit(child)
        elif isinstance(v, list):
            for child in v: visit(child)
    visit(value)
    assert all(re.fullmatch('[a-f0-9]{64}', x) for x in ids)
    assert all(re.fullmatch('adhd-accept-probe-[a-f0-9]{16}', x) for x in names)
    return sorted(ids | names)


def execute(args):
    work = args.work.absolute()
    assert Path(__file__).name == 'run.py' and sys.flags.isolated
    assert sha(work / 'plan.json') == args.plan_sha256
    plan = json.loads((work / 'plan.json').read_text())
    verify(work, plan)
    original = load(Path(plan['parent_guard']) / 'guard.py')
    original.write(work / 'execution.started', json.dumps({'plan_sha256': args.plan_sha256}).encode())
    gp = json.loads((Path(plan['parent_guard']) / 'plan.json').read_text())
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LD_', 'PYTHON', 'DOCKER_', 'ERL_', 'ELIXIR_'))}
    env.update(DOCKER_HOST='unix://' + gp['socket']['path'], DOCKER_CONFIG=str(work / 'bound/docker-config'),
               PYTHONPATH=str(work / 'frozen/tests'), PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(work / 'pycache'), ERL_FLAGS='+S 2:2',
               PATH=str(Path(gp['tools']['python']['path']).parent) + ':' +
               ':'.join(str(Path(t['root']) / 'bin') for t in gp['tool_trees'][1:]) + ':/usr/bin:/bin')
    results = []; failure = None
    try:
        for job in plan['jobs']:
            verify(work, plan)
            name = job['name']; report = work / (name + '.json')
            assert not report.exists()
            row = {'name': name, 'passed': False}; results.append(row)
            argv = [*job['prefix'], gp['tools']['python']['path'], str(work / 'frozen/tests' / job['script']),
                    *job['arguments'], '--report', str(report)]
            print('START', name, flush=True)
            with (work / (name + '.log')).open('xb') as output:
                child = subprocess.Popen(argv, cwd=work / 'runtime', env=env, stdout=output, stderr=subprocess.STDOUT)
                row['host_client_pid'] = child.pid
                row['process_exit_code'] = child.wait()
            assert row['process_exit_code'] == 0 and report.is_file()
            value = json.loads(report.read_text()); assert value['passed'] is True
            row['strict_recorded_container_absence'] = [absence(x) for x in runtime_handles(value)]
            row.update(passed=True, report_sha256=sha(report), log_sha256=sha(work / (name + '.log')))
            print('DONE', name, True, flush=True)
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        if 'child' in locals() and child.poll() is None: child.wait()
        try: verify(work, plan); unchanged = True
        except BaseException: unchanged = False
        unrun = [j['name'] for j in plan['jobs'] if j['name'] not in {r['name'] for r in results}]
        result = {'schema': 'adhd/compiled-core10-terminal@1', 'passed': not failure and unchanged and not unrun,
                  'plan_sha256': args.plan_sha256, 'results': results, 'unrun': unrun,
                  'input_closure_unchanged': unchanged, 'failure_type': failure,
                  'whole_prefix': plan['whole_prefix'], 'whole_prefix_checks': 35,
                  'original_false_aggregate_preserved': True}
        original.write(work / 'matrix.json', (json.dumps(result, indent=2) + '\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true'); group.add_argument('--execute', action='store_true')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--parent-core', type=Path); parser.add_argument('--parent-guard', type=Path)
    parser.add_argument('--bootstrap-helper', type=Path); parser.add_argument('--plan-sha256')
    parser.add_argument('--failure-proof', type=Path)
    args = parser.parse_args()
    prepare(args) if args.prepare else execute(args)


if __name__ == '__main__': main()
