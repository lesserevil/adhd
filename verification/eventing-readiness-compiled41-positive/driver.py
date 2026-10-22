#!/usr/bin/env python3
"""Closed compiled-image full23 readiness gate. Preparation is not runtime authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
SCHEMA = 'adhd/eventing-readiness-compiled23-plan@1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path):
    path = Path(path).absolute()
    info = path.lstat()
    assert path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
    return path


def bootstrap():
    here = regular(__file__)
    if here.name == 'driver.py':
        plan = json.loads(regular(here.parent / 'plan.json').read_text())
        assert plan['schema'] == SCHEMA and sha(here) == plan['driver_sha256']
        # Full immutable helper closure is authenticated before any helper
        # executes, not merely the first imported module.
        root = here.parent / 'frozen'
        assert root.resolve() == root and root.is_dir() and not root.is_symlink()
        files, directories = {}, []
        for path in sorted(root.rglob('*')):
            info = path.lstat()
            assert not stat.S_ISLNK(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                directories.append(str(path.relative_to(root)))
            else:
                files[str(path.relative_to(root))] = sha(regular(path))
        assert {'files': files, 'directories': directories} == plan['frozen']
        # Authenticate before importing any frozen code, independently of CWD.
        for name in ('eventing_readiness_matrix.py', 'eventing_readiness_compiled.py', 'eventing_retention_compiled.py',
                     'image_compiled_inputs.py', 'image_qualification_inputs.py'):
            selected = regular(here.parent / 'frozen/tests' / name)
            assert sha(selected) == plan['frozen']['files']['tests/' + name]
        sys.path.insert(0, str(here.parent / 'frozen/tests'))
    else:
        sys.path.insert(0, str(here.parent))


bootstrap()
import eventing_readiness_matrix as base
CHECKS=list(base.CASES)
from image_compiled_inputs import compiled_admission
from image_qualification_inputs import reviewed_payload


def socket_fact(path):
    path = Path(path).absolute()
    assert path.resolve() == path
    info = path.lstat()
    assert stat.S_ISSOCK(info.st_mode)
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}


def selected_bindings(context, admission, admission_sha, image):
    manifest = json.loads(regular(context / 'manifest.json').read_text())
    artifact = manifest['files']['hub.exs']
    payload = reviewed_payload(context / 'manifest.json', admission, admission_sha, image, artifact)
    compiled = compiled_admission(context, admission, admission_sha, image, artifact, required=True)
    raw = regular(admission.with_name('cache-manifest.json')).read_bytes()
    assert sha(admission.with_name('cache-manifest.json')) == compiled['retained_cache_binding']['cache_manifest_sha256']
    return artifact, payload, compiled, raw


def scenario_argv(work, python, image, rest):
    frozen, bound = work / 'frozen', work / 'bound'
    code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    return [python, '-I', '-B', '-c', code, str(frozen / 'tests'),
            str(frozen / 'tests/eventing_readiness_compiled.py'), '--image', image,
            '--image-manifest', str(bound / 'context/manifest.json'), '--eventing-rest-url', rest,
            '--recovery-schema', str(frozen / 'components/hub/project-recovery/interface.schema.json'),
            '--keep-work', str(work / 'results/fixtures'), '--report', str(work / 'results/report.json'),
            '--custody-plan', str(bound / 'custody.json'), '--custody-ledger', str(work / 'results/custody.json')]


def prepare(a):
    repo, work = a.repo.absolute(), a.work.absolute()
    assert repo.resolve() == repo and not work.exists()
    assert work.parent.is_dir() and work.parent.resolve() == work.parent
    context, admission = a.context.absolute(), a.admission.absolute()
    artifact, payload, compiled, cache = selected_bindings(context, admission, a.admission_sha256, a.image)
    official = base.validate_official(a.export, a.rebuild, a.receipt)
    assert artifact == official['artifact_sha256']
    rest = base.endpoint(a.eventing_rest_url)
    work.mkdir(mode=0o700)
    frozen, bound = work / 'frozen', work / 'bound'
    frozen.mkdir(mode=0o700); bound.mkdir(mode=0o700)
    for top in ('tests', 'scripts'):
        for source in sorted((repo / top).rglob('*')):
            if '__pycache__' in source.parts:
                continue
            if source.is_dir():
                assert not source.is_symlink()
                continue
            if source.suffix not in {'.py', '.json', '.md', '.exs', '.c', '.sh', '.yaml', '.yml'}:
                continue
            base.regular(source)
            target = frozen / source.relative_to(repo)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for name, raw in payload['specifications'].items():
        target = frozen / 'components/hub' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    # These are authored readiness-only overlays, never wholesale old helpers.
    for name in ('eventing_readiness_compiled.py', 'eventing_readiness_compiled_matrix.py'):
        shutil.copyfile(Path(__file__).with_name(name), frozen / 'tests' / name)
    shutil.copyfile(__file__, work / 'driver.py')
    for name in ('receipt.json', 'rebuild.json', 'hub.exs'):
        source = {'receipt.json': a.receipt, 'rebuild.json': a.rebuild, 'hub.exs': a.export}[name]
        shutil.copyfile(source, bound / name)
    shutil.copytree(context, bound / 'context', symlinks=False)
    source_files = {}
    for source in sorted(admission.parent.iterdir()):
        base.regular(source)
        target = bound / source.name
        if target.exists(): assert base.sha(target) == base.sha(source), 'Conflicting retained admission file'
        else: shutil.copyfile(source, target)
        source_files[str(source)] = base.sha(source)
    private = bound / 'docker-config'
    private.mkdir(mode=0o700)
    (private / 'config.json').write_text('{}')
    tools = {'python': base.tool(a.python), 'docker': base.tool(a.docker)}
    roots = [base.tool_root(path) for path in a.tool_root]
    assert roots
    environment = {'HOME': str(work), 'LANG': 'C.UTF-8', 'PATH': '/usr/bin:/bin',
                   'DOCKER_HOST': 'unix://' + str(a.socket.absolute()), 'DOCKER_CONFIG': str(private)}
    custody = {'image': a.image, 'docker': tools['docker']['path'],
               'payload_manifest': json.loads((context / 'manifest.json').read_text()),
               'payload_manifest_hex': (context / 'manifest.json').read_bytes().hex(),
               'cache_manifest': json.loads(cache), 'cache_manifest_sha256': hashlib.sha256(cache).hexdigest()}
    base.save(bound / 'custody.json', custody)
    argv = scenario_argv(work, tools['python']['path'], a.image, rest)
    plan = {'schema': SCHEMA, 'status': 'UNSTARTED_ROOT_REVIEW_REQUIRED', 'official': official,
            'image': a.image, 'admission_path': str(admission), 'admission_sha256': a.admission_sha256,
            'admission_files': source_files, 'context_path': str(context), 'compiled': compiled,
            'socket': socket_fact(a.socket), 'tools': tools, 'tool_roots': roots,
            'environment': environment, 'argv': argv, 'eventing_rest_url': rest, 'checks': CHECKS,
            'driver_sha256': sha(work / 'driver.py'), 'frozen': base.inventory(frozen), 'bound': base.inventory(bound),
            'automatic_retries': 0, 'parallelism': 1, 'provider_calls_authorized': 0, 'outer_timeout': None,
            'expected_VM_starts':23,'original_startup_seconds':45,'eventing_timeout_ms_by_case':{name:3000 if name in ('queue','queue-control')else 1000 for name in CHECKS},'scenario_sha256':sha(frozen/'tests/eventing_readiness_faults.py')}
    base.save(work / 'plan.json', plan)
    print(json.dumps({'plan': str(work / 'plan.json'), 'sha256': sha(work / 'plan.json')}))


def verify(work):
    work = Path(work).absolute()
    plan = json.loads(regular(work / 'plan.json').read_text())
    assert plan['schema'] == SCHEMA and regular(__file__) == work / 'driver.py'
    assert sha(__file__) == plan['driver_sha256']
    assert base.inventory(work / 'frozen') == plan['frozen'] and base.inventory(work / 'bound') == plan['bound']
    for path, expected in plan['admission_files'].items():
        assert sha(regular(path)) == expected
    o = plan['official']
    assert base.validate_official(o['artifact_path'], o['rebuild_path'], o['receipt_path']) == o
    for filename, field in [('hub.exs', 'artifact_sha256'), ('receipt.json', 'receipt_sha256'), ('rebuild.json', 'rebuild_sha256')]:
        assert sha(work / 'bound' / filename) == o[field]
    for context, admission in [(Path(plan['context_path']), Path(plan['admission_path'])),
                               (work / 'bound/context', work / 'bound' / Path(plan['admission_path']).name)]:
        artifact, _, compiled, _ = selected_bindings(context, admission, plan['admission_sha256'], plan['image'])
        assert artifact == o['artifact_sha256'] and compiled == plan['compiled']
    assert socket_fact(plan['socket']['path']) == plan['socket']
    for tool in plan['tools'].values():
        assert base.tool(tool['path']) == tool
    for root in plan['tool_roots']:
        assert base.tool_root(root['path']) == root
    assert plan['checks'] == CHECKS and plan['expected_VM_starts'] == 23
    assert (plan['automatic_retries'], plan['parallelism'], plan['provider_calls_authorized'], plan['outer_timeout']) == (0, 1, 0, None)
    assert plan['original_startup_seconds']==45
    assert plan['eventing_timeout_ms_by_case']=={name:3000 if name in ('queue','queue-control')else 1000 for name in CHECKS}
    assert sha(work/'frozen/tests/eventing_readiness_faults.py')==plan['scenario_sha256']
    assert plan['environment']['DOCKER_HOST'] == 'unix://' + plan['socket']['path']
    assert plan['environment']['DOCKER_CONFIG'] == str(work / 'bound/docker-config')
    assert plan['environment'] == {'HOME': str(work), 'LANG': 'C.UTF-8', 'PATH': '/usr/bin:/bin',
        'DOCKER_HOST': 'unix://' + plan['socket']['path'], 'DOCKER_CONFIG': str(work / 'bound/docker-config')}
    assert plan['argv'] == scenario_argv(work, plan['tools']['python']['path'], plan['image'], base.endpoint(plan['eventing_rest_url']))
    custody = base.read(work / 'bound/custody.json')
    assert custody['image'] == plan['image'] and custody['docker'] == plan['tools']['docker']['path']
    assert custody['payload_manifest_hex'] == (work / 'bound/context/manifest.json').read_bytes().hex()
    assert custody['payload_manifest'] == base.read(work / 'bound/context/manifest.json')
    assert custody['cache_manifest'] == base.read(work / 'bound/cache-manifest.json')
    assert custody['cache_manifest_sha256'] == sha(work / 'bound/cache-manifest.json')
    imported=subprocess.run([plan['tools']['python']['path'],'-I','-B','-c',
        "import sys;sys.path.insert(0,sys.argv[1]);import eventing_readiness_compiled",str(work/'frozen/tests')],
        cwd=work/'frozen',env=plan['environment'],capture_output=True,timeout=30)
    assert imported.returncode==0 and not imported.stdout and not imported.stderr,'Frozen scenario dependency import failed'
    assert base.inventory(work/'frozen')==plan['frozen']
    return plan


def observations(work,plan):
    report=base.read(work/'results/report.json')
    assert report['suite']=='adhd/eventing-readiness-faults@2'and report['planned_cases']==CHECKS
    assert all(row.get('passed')is True for row in report['checks'])
    names=[row['name']for row in report['checks']]
    attempted=[row['case']for row in report.get('proxy_cleanup',[])]
    assert names==CHECKS[:len(names)]and attempted==CHECKS[:len(attempted)]
    assert len(names)<=len(attempted)<=len(names)+1
    proxies=report.get('proxy_cleanup',[])
    clean=all(row['handlers']==0 and row['thread_alive']is False and not row['failures']and not row['cleanup_failure_types']for row in proxies)
    return {'whole_passed':names,'attempted':attempted,'failed_case':attempted[len(names)]if len(attempted)>len(names)else None,
        'unrun':CHECKS[len(attempted):],'report_sha256':sha(work/'results/report.json'),'proxy_cleanup':proxies,'reported_cleanup_verified':clean}


def execute(work):
    plan = verify(work); work = Path(work).absolute()
    assert not (work / 'results').exists()
    base.claim(work / 'started.json'); (work / 'results').mkdir(mode=0o700)
    result = {'schema': 'adhd/eventing-readiness-compiled23-result@1', 'passed': False,
              'plan_sha256': sha(work / 'plan.json'), 'image_config_identity': plan['image']}
    child = None; primary = None
    try:
        with (work / 'results/stdout.log').open('xb') as out, (work / 'results/stderr.log').open('xb') as err:
            child = subprocess.Popen(plan['argv'], cwd=work / 'frozen', env=plan['environment'],
                                     stdout=out, stderr=err, start_new_session=True)
            result['child']={'pid':child.pid,'start_ticks':int(Path('/proc',str(child.pid),'stat').read_text().split(') ',1)[1].split()[19])}
            result['exit_code'] = child.wait()
        report = base.read(work/'results/report.json');custody=base.read(work/'results/custody.json')
        result.update(observations(work,plan))
        assert result['exit_code']==0 and report['passed']is True and result['whole_passed']==CHECKS
        assert report['planned_cases']==CHECKS and report['original_case_prefix_count']==21
        assert report['provider_calls']==0 and report['artifact_sha256']==plan['official']['artifact_sha256']
        assert not report.get('native_runtime_cases')
        assert len(report['proxy_cleanup'])==23 and result['reported_cleanup_verified']
        assert len(custody['starts'])==len(custody['launches'])==23
        assert [row['case']for row in custody['starts']]==CHECKS
        assert len({row['container_id']for row in custody['starts']})==23
        assert all(row['actual_name_absent']for row in custody['launches'])
        for row in custody['starts']:
            assert row['same_actual_VM']and row['default_entrypoint']
            assert row['app_files']==59 and row['cache_and_toolchain_files']==67
            try:current=int(Path('/proc',str(row['host_vm_pid']),'stat').read_text().split(') ',1)[1].split()[19])
            except FileNotFoundError:current=None
            assert current!=row['start_ticks'],'Owned VM PID identity still live'
            row['same_identity_absent']=True
        result['actual_VM_starts']=custody['starts']
        result['passed'] = True
    except BaseException as error:
        primary = error; result['failure_type'] = type(error).__name__
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
            try: child.wait(15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); result['forced_cleanup'] = True
        if(work/'results/report.json').exists():
            try:result.update(observations(work,plan))
            except BaseException as error:result['report_audit_failure_type']=type(error).__name__;result['passed']=False
        if(work/'results/custody.json').exists():
            result['custody_sha256']=sha(work/'results/custody.json')
        try: verify(work); result['post_input_closure_verified'] = True
        except BaseException as error:
            result['post_input_closure_verified'] = False; result['closure_failure_type'] = type(error).__name__
        result['scoped_processes'] = base.scoped_processes(work / 'results')
        result['passed'] = bool(result['passed'] and result['post_input_closure_verified'] and
                                not result['scoped_processes'] and not result.get('forced_cleanup'))
        try:base.save(work/'result.json',result)
        except BaseException as error:
            if primary is None:raise
            primary.add_note('Result persistence failure type: '+type(error).__name__)
    if primary is not None: raise primary
    assert result['passed']


def main():
    parser = argparse.ArgumentParser(__doc__); sub = parser.add_subparsers(dest='phase', required=True)
    p = sub.add_parser('prepare')
    for name in ('repo', 'work', 'context', 'admission', 'export', 'rebuild', 'receipt', 'python', 'docker', 'socket'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--admission-sha256', required=True); p.add_argument('--image', required=True)
    p.add_argument('--eventing-rest-url', required=True); p.add_argument('--tool-root', type=Path, action='append', required=True)
    for phase in ('verify', 'execute'): sub.add_parser(phase).add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    if args.phase == 'prepare': prepare(args)
    elif args.phase == 'verify': verify(args.work); print(json.dumps({'verified': True, 'runtime_started': False}))
    else: execute(args.work)


if __name__ == '__main__': main()
