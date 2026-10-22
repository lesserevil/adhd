"""Read-only post-terminal input verifier and exact frozen child predicates.

Extracts only reviewed verifier/predicate ASTs; never calls execute, main, Docker,
Kubernetes, a model endpoint, application code or a compiler. Run with isolated
Python, no site/bytecode and an explicit fresh pycache prefix.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def closed(root, expected):
    assert root.resolve(strict=True) == root and not root.is_symlink()
    files = {}
    directories = set()
    wanted_directories = set()
    for name in expected:
        path = Path(name)
        assert not path.is_absolute() and '..' not in path.parts and str(path) == name
        wanted_directories.update(str(v) for v in path.parents if str(v) != '.')
    for path in root.rglob('*'):
        info = path.lstat()
        assert not stat.S_ISLNK(info.st_mode)
        relative = str(path.relative_to(root))
        if stat.S_ISDIR(info.st_mode):
            directories.add(relative)
        else:
            assert stat.S_ISREG(info.st_mode)
            files[relative] = sha(path)
    assert files == expected and directories == wanted_directories
    return {'files': len(files), 'directories': len(directories)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--family', choices=['baseline', 'secured'], required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
    assert sys._xoptions.get('pycache_prefix') == sys.pycache_prefix
    cache = Path(sys.pycache_prefix)
    assert cache.is_absolute() and cache.resolve(strict=True) == cache
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700 and not any(cache.iterdir())
    work = args.work.absolute()
    assert work.resolve(strict=True) == work
    assert sha(work / 'plan.json') == args.plan_sha256
    plan = json.loads((work / 'plan.json').read_text())
    assert sha(work / 'driver.py') == plan['driver_sha256']
    closure = {name: closed(work / name, plan[key]) for key, name in
               [('frozen_inputs', 'frozen'), ('bound_inputs', 'bound'), ('context_inputs', 'context')]}
    # No helper is imported until its complete frozen SET/hash custody passes.
    sys.path.insert(0, str(work / 'frozen/tests'))
    from image_qualification_inputs import verify_frozen_inputs
    from image_compiled_inputs import compiled_admission
    from kube_qualification_inputs import json_kube_endpoint
    import image_host_dependencies as host_dependencies
    helpers = ast.parse((work / 'frozen/tests/image_recovery_remaining_matrix.py').read_bytes())
    driver = ast.parse((work / 'driver.py').read_bytes())
    definitions = {node.name: node for node in driver.body if isinstance(node, ast.FunctionDef)}
    cache_verifier = next(node for node in helpers.body
                          if isinstance(node, ast.FunctionDef) and node.name == 'verify_empty_cache')
    names = ['verify', 'own_matrix', 'qualified'] if args.family == 'baseline' else ['verify', 'verify_own_matrix']
    selected = [definitions[name] for name in names] + [cache_verifier]
    predicates_sha256 = {}
    if args.family == 'secured':
        # Preserve the exact original inline child assertion ASTs from execute.
        block = next(node for node in definitions['execute'].body if isinstance(node, ast.Try))
        start = next(i for i, node in enumerate(block.body) if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'child' for t in node.targets))
        checks = [block.body[start]]
        for node in block.body[start + 1:]:
            if not isinstance(node, ast.Assert):
                break
            checks.append(node)
        assert len(checks) == 4 and all(isinstance(n, ast.Assert) for n in checks[1:])
        predicates_sha256['exact_inline_child_checks'] = hashlib.sha256(
            ast.dump(ast.Module(body=checks, type_ignores=[]), include_attributes=False).encode()).hexdigest()
        fn = ast.FunctionDef(name='qualify_secured', args=ast.arguments(
            posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
            body=checks + [ast.Return(value=ast.Constant(value=True))], decorator_list=[])
        selected.append(fn)
    for name in names:
        predicates_sha256[name] = hashlib.sha256(ast.dump(definitions[name], include_attributes=False).encode()).hexdigest()
    namespace = {'__file__': str(work / 'driver.py'), 'Path': Path, 'json': json, 'os': os,
                 'stat': stat, 'sha': sha, 'verify_frozen_inputs': verify_frozen_inputs,
                 'compiled_admission': compiled_admission, 'json_kube_endpoint': json_kube_endpoint,
                 'kube_endpoint': json_kube_endpoint, 'host_dependencies': host_dependencies,
                 'work': work, 'plan': plan}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])),
                 str(work / 'driver.py'), 'exec'), namespace)
    assert namespace['verify'](work, plan, preflight=False) is True
    qualified = []
    if args.family == 'baseline':
        matrix = json.loads((work / 'matrix.json').read_text())
        assert matrix['passed'] and matrix['inputs_unchanged'] and not matrix['unrun_platforms']
        for row in matrix['rows']:
            assert row['started'] and row['exit_code'] == 0 and row['passed']
            report = work / (row['name'] + '.json')
            assert sha(report) == row['report_sha256']
            assert namespace['qualified'](json.loads(report.read_text()), plan) is True
            qualified.append(row['name'])
    else:
        result = json.loads((work / 'execution.json').read_text())
        assert result['passed'] and result['exit_code'] == 0
        assert sha(work / 'result.json') == result['report_sha256']
        namespace['result'] = result
        assert namespace['qualify_secured']() is True
        qualified.append('secured-kind')
    output = {'schema': 'adhd/frozen-terminal-child-qualifier-review@1', 'passed': True,
              'family': args.family, 'plan_sha256': args.plan_sha256,
              'driver_sha256': plan['driver_sha256'], 'closure': closure,
              'actual_frozen_verify_called_preflight_false': True,
              'actual_frozen_child_predicates_invoked': qualified,
              'predicate_AST_sha256': predicates_sha256,
              'reviewer_sha256': sha(Path(__file__)),
              'application_compiler_service_probe_provider_starts': 0,
              'scope': 'Exact frozen verifier and child predicates only; no execute/main, resource preflight or retry.'}
    with args.report.open('x') as stream:
        json.dump(output, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'family': args.family, 'qualified': qualified}))


if __name__ == '__main__':
    main()
