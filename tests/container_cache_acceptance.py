#!/usr/bin/env python3
"""Closed cache/CLI qualification; writable offline-tamper negatives are explicit.

No application/container/compiler starts occur without --execute and a reviewed
plan digest. SDK readiness and syscall observer qualification are separate gates.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
from uuid import uuid4


ACME_FILES = {'LICENSE.lego','LICENSE.musl','acme-build.json','acme-bundle.json','acme-guard','acme-pins.json','lego','lego-sbom.json'}
ACME_CASES = ('missing-lego','changed-lego','missing-acme-guard','changed-acme-guard','nonexecutable-lego')


def target_binding(context, manifest, artifact):
    """Preparation-only trusted helper load; execution remains self-contained."""
    inputs = json.loads(read(Path(context) / 'compiler-inputs.json'))
    if inputs['schema'] != 'adhd/container-compiler-inputs@2':
        assert inputs['schema'] == 'adhd/container-compiler-inputs@1'
        return None, None
    helper = Path(__file__).with_name('image_compiled_inputs.py')
    code = read(helper)
    namespace = {'__name__': 'bound_compiler_inputs', '__file__': str(helper)}
    exec(compile(code, str(helper), 'exec'), namespace)
    binding = namespace['compiled_context'](context, manifest, artifact)
    assert set(binding['acme_files']) == ACME_FILES
    return {'modules': binding['payload_counts']['modules'],
            'acme': {n: binding['packaging_files_sha256'][n] for n in sorted(ACME_FILES)},
            'cache_schema': 'adhd/precompiled-cache@2'}, code


def sha(data): return hashlib.sha256(data).hexdigest()

def read(path):
    path = Path(path).absolute()
    assert path.resolve(strict=True) == path and path.is_file() and path.stat().st_nlink == 1
    return path.read_bytes()

def absent(result, identity):
    return (result.returncode == 1 and result.stdout.strip() in (b'', b'[]') and
            re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)' +
                         re.escape(identity), result.stderr.decode(errors='replace').strip()) is not None)

def archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, (data, mode, kind, target) in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.uid = item.gid = 0
            item.mode = mode
            item.type = kind
            item.linkname = target
            item.size = len(data) if kind == tarfile.REGTYPE else 0
            tar.addfile(item, io.BytesIO(data) if item.isfile() else None)
    return output.getvalue()


def inspect_archive(data, acme=False):
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tar:
        members = tar.getmembers()
        assert len(members) <= 256
        for m in members:
            assert m.name not in result and not m.name.startswith('/') and '..' not in Path(m.name).parts
            assert m.isdir() or m.isfile() or m.issym()
            assert m.size <= (80*1024*1024 if acme and m.name in ('adhd/lego','adhd/acme-guard') else 8*1024*1024)
            body = tar.extractfile(m).read() if m.isfile() else b''
            result[m.name] = (body, m.mode, m.type, m.linkname)
            assert m.uid == m.gid == 0, 'Docker offline staging must preserve root cache ownership'
    return result


def cache_summary(entries):
    return {name: {'sha256': sha(body), 'mode': format(mode, '04o'),
                   'type': kind.decode('ascii'), 'target': target}
            for name, (body, mode, kind, target) in sorted(entries.items())}


def archive_witness(data, acme=False):
    assert len(data) <= (128 if acme else 64) * 1024 * 1024
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tar:
        members = tar.getmembers(); assert len(members) <= 256
        rows = []
        for item in members:
            assert item.size <= (80*1024*1024 if acme and item.name in ('adhd/lego','adhd/acme-guard') else 8*1024*1024)
            body = tar.extractfile(item).read() if item.isfile() else b''
            rows.append({'name': item.name, 'uid': item.uid, 'gid': item.gid,
                         'mode': format(item.mode, '04o'), 'type': item.type.decode('ascii'),
                         'target': item.linkname, 'size': item.size, 'sha256': sha(body)})
        return rows


def prefix_contract(plan, result, image, artifact, mode, context):
    assert result['passed'] is False and result['image'] == plan['image'] == image
    assert result['artifact_sha256'] == plan['artifact_sha256'] == artifact
    assert plan['cache_root_mode'] == mode and plan['context_files'] == context
    expected = ['original-native18', 'describe', 'protocol-schema', 'protocol-openapi',
                'offline-copy-control', 'missing-manifest', 'missing-beam', 'changed-beam', 'extra-beam']
    assert [r['case'] for r in result['results']] == expected and all(r['passed'] is True for r in result['results'])
    assert result['results'][0]['checks'] == 18
    assert len(result['container_ledger']) == 11
    assert result['container_ledger'][-1]['case'] == 'beam-symlink' and 'exit_code' not in result['container_ledger'][-1]
    assert all(row['observed_absent'] and not row['cleanup_errors'] for row in result['container_ledger'])
    return expected


CASES = ('missing-manifest', 'missing-beam', 'changed-beam', 'extra-beam',
         'beam-symlink', 'missing-build-helper', 'changed-build-helper',
         'changed-boot-comment', 'changed-source', 'toolchain-version',
         'toolchain-vm-anchor', 'toolchain-extra-anchor')


def mutation(files, name):
    files = dict(files)
    prefix = 'adhd/'
    beam = next(n for n in sorted(files) if n.startswith(prefix + 'ebin/') and n.endswith('.beam'))
    manifest = prefix + 'manifest.json'
    target = {'missing-manifest': manifest, 'missing-beam': beam,
              'missing-build-helper': prefix + 'build.exs'}.get(name)
    if target:
        raise AssertionError('True missing entries require the fixed setup helper')
    elif name in ('changed-lego', 'changed-acme-guard', 'nonexecutable-lego'):
        target = prefix + ('acme-guard' if name == 'changed-acme-guard' else 'lego')
        data, mode, kind, link = files[target]
        files[target] = (data if name == 'nonexecutable-lego' else data+b'controlled drift', 0o444 if name == 'nonexecutable-lego' else mode, kind, link)
    elif name in ('missing-lego','missing-acme-guard'):
        raise AssertionError('True missing entries require the fixed setup helper')
    elif name in ('changed-beam', 'changed-build-helper', 'changed-boot-comment'):
        target = {'changed-beam': beam, 'changed-build-helper': prefix + 'build.exs',
                  'changed-boot-comment': prefix + 'boot.exs'}[name]
        data, mode, kind, link = files[target]
        files[target] = (data + b'\n# controlled cache drift\n', mode, kind, link)
    elif name == 'extra-beam':
        files[prefix + 'ebin/Elixir.Unexpected.beam'] = (b'not a BEAM', 0o444, tarfile.REGTYPE, '')
    elif name == 'beam-symlink':
        files[beam] = (b'', 0o777, tarfile.SYMTYPE, '/app/hub.exs')
    elif name in ('missing-manifest', 'missing-beam', 'missing-build-helper'):
        raise AssertionError('True missing entries require the fixed setup helper')
    elif name == 'changed-source':
        pass  # Original source copy is tampered separately; cache stays byte-identical.
    else:
        value = json.loads(files[manifest][0])
        if name == 'toolchain-version': value['toolchain']['elixir'] = '0.0.0-invalid'
        elif name == 'toolchain-vm-anchor': value['toolchain']['anchors']['/proc/self/exe'] = '0' * 64
        elif name == 'toolchain-extra-anchor': value['toolchain']['anchors']['/unexpected'] = '0' * 64
        else: raise AssertionError('Unknown cache mutation')
        old = files[manifest]
        files[manifest] = (json.dumps(value).encode(), old[1], old[2], old[3])
    return files


class ForeignContainer(Exception): pass


MISSING_HELPER = ('set -eu; case "$1" in /runtime/adhd/manifest.json|/runtime/adhd/build.exs|'
                  '/runtime/adhd/lego|/runtime/adhd/acme-guard|/runtime/adhd/ebin/Elixir.*.beam) ;; *) exit 72;; esac; '
                  'case "$2" in 555|755) ;; *) exit 74;; esac; '
                  'p=${1%/*}; case "$p" in /runtime/adhd) mode=$2;; /runtime/adhd/ebin) mode=555;; *) exit 73;; esac; '
                  'chmod 755 "$p"; rm -- "$1"; chmod "$mode" "$p"; '
                  "exec elixir /runtime/adhd/boot.exs /app/hub.exs '[\"cache-guard-must-not-dispatch\"]'")


class Runner:
    def __init__(self, work, plan):
        self.work, self.plan = work, plan
        self.ledger = []

    def command(self, args, timeout=30, data=None):
        socket = Path(self.plan['docker_socket']['path'])
        info = socket.stat()
        assert socket.resolve() == socket and stat.S_ISSOCK(info.st_mode)
        assert [info.st_dev, info.st_ino] == self.plan['docker_socket']['identity']
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DOCKER_', 'LD_', 'PYTHON'))}
        env['DOCKER_CONFIG'] = str(self.work / 'docker-config')
        assert read(self.work / 'docker-config/config.json') == b'{}'
        return subprocess.run(['/usr/bin/docker', '--host', 'unix://' + str(socket), *args],
                              input=data, capture_output=True, timeout=timeout, env=env)

    def inspect(self, name):
        p = self.command(['inspect', name])
        if absent(p, name): return None
        assert p.returncode == 0, 'Docker inspection failed without authoritative absence'
        rows = json.loads(p.stdout)
        assert len(rows) == 1
        return rows[0]

    def owned(self, state, row):
        if (state['Name'] != '/' + row['name'] or state['Image'] != self.plan['image'] or
                (row.get('container_id') and state['Id'] != row['container_id'])):
            raise ForeignContainer('Container identity mismatch')

    def close(self, row):
        errors = []
        identity = row.get('container_id', row['name'])
        foreign = False
        try:
            state = self.inspect(identity)
            if state is not None:
                self.owned(state, row)
                identity = state['Id']
                assert re.fullmatch('[0-9a-f]{64}', identity)
                row['container_id'] = identity
                if state['State']['Running']:
                    killed = self.command(['kill', identity])
                    assert killed.returncode == 0
                    waited = self.command(['wait', identity])
                    assert waited.returncode == 0 and waited.stdout.strip() == b'137'
                    row['observed_kernel_kill_exit_code'] = 137
                result = self.command(['rm', identity])
                assert result.returncode == 0
        except ForeignContainer:
            foreign = True
            errors.append('ForeignContainer')
        except BaseException as e:
            errors.append(type(e).__name__)
        # A successful create establishes an owned immutable ID independently of
        # a transient inspect failure. Never force-remove a positively foreign ID.
        if errors and row.get('container_id') and not foreign:
            try:
                result = self.command(['rm', '--force', row['container_id']])
                if result.returncode and not absent(self.command(['inspect', identity]), identity):
                    errors.append('IndependentRemovalFailed')
            except BaseException as e: errors.append(type(e).__name__)
        absence = True
        for key in dict.fromkeys([identity, row['name']]):
            try: assert absent(self.command(['inspect', key]), key)
            except BaseException as e:
                absence = False
                errors.append(type(e).__name__)
        row['observed_absent'] = absence
        row['cleanup_errors'] = errors
        assert absence and not errors, 'Owned container cleanup failed or was not proven'

    def create(self, label, argv, negative=False, helper_target=None):
        row = {'case': label, 'name': 'adhd-cache-' + uuid4().hex,
               'rootfs': 'writable-offline-tamper' if negative else 'production-readonly',
               'runtime_user': '0:0' if helper_target else '10001:10001'}
        self.ledger.append(row)
        args = ['create', '--pull', 'never', '--name', row['name'], '--network', 'none', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--user', row['runtime_user'],
                '--memory', '768m', '--cpus', '2', '--pids-limit', '256', '--workdir', '/tmp',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m']
        if not negative: args += ['--read-only']
        if helper_target:
            assert negative and helper_target in self.allowed_missing
            args += ['--entrypoint', '/bin/sh']
            assert self.plan['cache_root_mode'] in (0o555, 0o755)
            argv = ['-c', MISSING_HELPER, 'cache-missing-setup', helper_target, format(self.plan['cache_root_mode'], 'o')]
            row['fixed_setup_target'] = helper_target
        p = self.command([*args, self.plan['image'], *argv])
        assert p.returncode == 0
        identity = p.stdout.decode().strip()
        assert re.fullmatch('[0-9a-f]{64}', identity)
        row['container_id'] = identity
        state = self.inspect(identity)
        self.owned(state, row)
        assert state['HostConfig']['ReadonlyRootfs'] is (not negative)
        assert state['Config']['User'] == row['runtime_user']
        assert state['HostConfig']['NetworkMode'] == 'none'
        assert state['HostConfig']['CapDrop'] == ['ALL']
        return row

    def cache_snapshot(self):
        row = {'case': 'offline-cache-export', 'name': 'adhd-cache-export-' + uuid4().hex}
        self.ledger.append(row)
        primary = None
        try:
            p = self.command(['create', '--pull', 'never', '--name', row['name'], '--network', 'none', '--cap-drop', 'ALL',
                              '--security-opt', 'no-new-privileges', '--read-only', '--user', '10001:10001', self.plan['image']])
            assert p.returncode == 0
            identity = p.stdout.decode().strip()
            assert re.fullmatch('[0-9a-f]{64}', identity)
            row['container_id'] = identity
            self.owned(self.inspect(identity), row)
            p = self.command(['cp', identity + ':/runtime/adhd', '-'])
            assert p.returncode == 0 and len(p.stdout) <= (128 if self.plan.get("acme") else 64) * 1024 * 1024
            (self.work / 'original-cache.tar').write_bytes(p.stdout)
            result = inspect_archive(p.stdout, bool(self.plan.get("acme")))
            manifest = json.loads(result['adhd/manifest.json'][0])
            assert manifest['source_sha256'] == self.plan['artifact_sha256']
            assert manifest['payload_manifest_sha256'] == self.plan['context_files']['manifest.json']
            if self.plan.get('admission'):
                assert sha(result['adhd/manifest.json'][0]) == self.plan['admission']['cache_manifest_sha256']
            assert manifest['modules'] == self.plan['expected_modules'] and len(manifest['modules']) == (len(self.plan['expected_modules']) if self.plan.get('acme') else 59)
            expected = {'adhd', 'adhd/ebin', 'adhd/boot.exs', 'adhd/build.exs', 'adhd/inputs.json', 'adhd/manifest.json'}
            expected |= {'adhd/ebin/' + name + '.beam' for name in manifest['modules']}
            expected |= {'adhd/'+n for n in self.plan.get('acme', {})}
            assert set(result) == expected
            if self.plan.get('acme'):
                assert manifest['schema']=='adhd/precompiled-cache@2' and manifest['acme']==self.plan['acme']
                for n,h in self.plan['acme'].items():assert sha(result['adhd/'+n][0])==h
            for name, (body, mode, kind, target) in result.items():
                assert not target and kind in (tarfile.REGTYPE, tarfile.DIRTYPE)
                expected_mode = self.plan['cache_root_mode'] if name == 'adhd' else (0o555 if kind == tarfile.DIRTYPE or (self.plan.get('acme') and name in ('adhd/lego','adhd/acme-guard')) else 0o444)
                assert mode == expected_mode
                if name.startswith('adhd/ebin/'):
                    assert sha(body) == manifest['beams'][name.removeprefix('adhd/ebin/')]
            for key in ('boot', 'build'):
                assert sha(result['adhd/' + key + '.exs'][0]) == manifest[key + '_sha256']
            assert sha(result['adhd/inputs.json'][0]) == manifest['inputs_sha256']
            row['started'] = False
            self.allowed_missing = {'/runtime/adhd/manifest.json', '/runtime/adhd/build.exs'}
            self.allowed_missing |= {'/runtime/adhd/ebin/' + name + '.beam' for name in manifest['modules']}
            if self.plan.get('acme'):self.allowed_missing |= {'/runtime/adhd/lego','/runtime/adhd/acme-guard'}
            self.original_cache = result
            return result
        except BaseException as e:
            primary = e
            raise
        finally:
            try: self.close(row)
            except BaseException as e:
                if primary: primary.add_note('Cleanup: ' + str(e))
                else: raise

    def case(self, label, argv, cache=None, source=None, negative=False, helper_target=None):
        row = None
        primary = None
        try:
            row = self.create(label, argv, negative or cache is not None, helper_target)
            identity = row['container_id']
            if cache is not None:
                p = self.command(['cp', '-', identity + ':/runtime'], data=archive(cache))
                assert p.returncode == 0
                observed = self.command(['cp', identity + ':/runtime/adhd', '-'])
                assert observed.returncode == 0
                witness = {'expected': cache_summary(cache), 'actual': archive_witness(observed.stdout, bool(self.plan.get("acme")))}
                witness_path = self.work / (label + '.cache-before-start.json')
                witness_path.write_text(json.dumps(witness, indent=2) + '\n')
                row['offline_cache_metadata_sha256'] = sha(read(witness_path))
                row['offline_cache_archive_sha256'] = sha(observed.stdout)
                assert inspect_archive(observed.stdout, bool(self.plan.get("acme"))) == cache
            if source is not None:
                p = self.command(['cp', '-', identity + ':/app'], data=archive({'hub.exs': (source, 0o644, tarfile.REGTYPE, '')}))
                assert p.returncode == 0
                observed = self.command(['cp', identity + ':/app/hub.exs', '-'])
                assert observed.returncode == 0
                assert inspect_archive(observed.stdout) == {'hub.exs': (source, 0o644, tarfile.REGTYPE, '')}
            started = time.monotonic()
            p = self.command(['start', '--attach', identity], timeout=30)
            row.update(exit_code=p.returncode, elapsed_seconds=time.monotonic() - started,
                       stdout_sha256=sha(p.stdout), stderr_sha256=sha(p.stderr))
            (self.work / (label + '.stdout')).write_bytes(p.stdout)
            (self.work / (label + '.stderr')).write_bytes(p.stderr)
            state = self.inspect(identity)
            self.owned(state, row)
            assert not state['State']['Running'] and state['State']['ExitCode'] == p.returncode
            if helper_target:
                observed = self.command(['cp', identity + ':/runtime/adhd', '-'])
                assert observed.returncode == 0
                expected = dict(self.original_cache)
                del expected['adhd/' + helper_target.removeprefix('/runtime/adhd/')]
                assert inspect_archive(observed.stdout, bool(self.plan.get("acme"))) == expected
                row['true_missing_entry_verified_after_exit'] = helper_target
            difference = self.command(['diff', identity])
            assert difference.returncode == 0
            paths = [line.split(' ', 1)[1] for line in difference.stdout.decode().splitlines()]
            assert not any(path.startswith(('/config', '/data', '/guard')) for path in paths)
            assert all(path.startswith('/runtime') or (source is not None and path in ('/app', '/app/hub.exs')) for path in paths)
            row['filesystem_changes'] = paths
            row['no_configuration_or_data_writes'] = True
            if negative:
                assert p.returncode != 0 and b'Invalid precompiled application cache' in p.stderr
            else: assert p.returncode == 0
            return p
        except BaseException as e:
            primary = e
            if row is None and self.ledger and self.ledger[-1]['case'] == label:
                row = self.ledger[-1]
            if isinstance(e, subprocess.TimeoutExpired):
                (self.work / (label + '.stdout')).write_bytes(e.stdout or b'')
                (self.work / (label + '.stderr')).write_bytes(e.stderr or b'')
            if row: row['failure_type'] = type(e).__name__
            raise
        finally:
            if row:
                try: self.close(row)
                except BaseException as cleanup:
                    if primary: primary.add_note('Cleanup: ' + str(cleanup))
                    else: raise


def selection_contract(plan):
    acme=plan.get('acme',{})
    if acme:
        assert set(acme)==ACME_FILES and all(isinstance(h,str) and re.fullmatch('[a-f0-9]{64}',h) for h in acme.values())
        assert not plan.get('prefix') and plan.get('admission') and plan.get('target_validator_sha256')
        assert 'Elixir.ADHD.ACMEClient' in plan['expected_modules']
        assert len(plan['expected_modules'])==len(set(plan['expected_modules']))
        checks=plan['native_checks'];assert type(checks) is int and 1<=checks<=4096
        assert plan['native_case_label']=='source-native'+str(checks)
    else:
        assert plan.get('native_checks',18)==18 and plan.get('native_case_label','original-native18')=='original-native18'
        assert len(plan['expected_modules'])==len(set(plan['expected_modules']))==59
    assert plan['cases']==(list(CASES[4:]) if plan.get('prefix') else list(CASES)+(list(ACME_CASES) if acme else []))


def verify(work, plan):
    selection_contract(plan)
    assert work.resolve(strict=True) == work
    assert sha(read(__file__)) == plan['driver_sha256'] == sha(read(work / 'driver.py'))
    context = Path(plan['context'])
    assert {p.name: sha(read(p)) for p in context.iterdir()} == plan['context_files']
    assert sha(read('/usr/bin/docker')) == plan['docker_sha256']
    assert str(Path(sys.executable).absolute()) == plan['python']['path']
    assert str(Path('/proc/self/exe').resolve()) == plan['python']['realpath']
    assert sha(read(plan['python']['realpath'])) == plan['python']['sha256']
    assert sys.version == plan['python']['version']
    assert read(work / 'docker-config/config.json') == b'{}'
    socket = Path(plan['docker_socket']['path']); info = socket.stat()
    assert socket.resolve() == socket and stat.S_ISSOCK(info.st_mode)
    assert [info.st_dev, info.st_ino] == plan['docker_socket']['identity']
    if plan.get('admission'):
        assert {p.name: sha(read(p)) for p in (work / 'admission').iterdir()} == plan['admission']['files']
    if plan.get('target_validator_sha256'):
        assert sha(read(work / 'input-validator.py')) == plan['target_validator_sha256']
    if plan.get('prefix'):
        assert {p.name: sha(read(p)) for p in (work / 'prefix').iterdir()} == plan['prefix']['files']


def validate_compiled_admission(admission, image, artifact, context, *, target=None):
    assert admission['schema'] == 'adhd/compiled40-admission-and-image-binding@1'
    assert admission['passed'] is True and admission['image_config_identity'] == image
    assert admission['artifact_sha256'] == artifact and admission['canonical_manifest_sha256'] == context
    audit = admission['compiled_runtime_audit']
    assert audit['passed'] is True and audit['image_id'] == image
    assert audit['artifact_sha256'] == artifact and audit['canonical_manifest_sha256'] == context
    if target is None:
        assert audit['cache_modules'] == 59 and audit['cache_entries'] == 65
    else:
        assert set(target)=={'modules','acme','cache_schema'} and target['cache_schema']=='adhd/precompiled-cache@2'
        assert 'Elixir.ADHD.ACMEClient' in target['modules'] and len(target['modules'])==len(set(target['modules']))
        assert set(target['acme'])==ACME_FILES and all(re.fullmatch('[a-f0-9]{64}',h) for h in target['acme'].values())
        assert type(audit['cache_modules']) is int and audit['cache_modules']==len(target['modules'])
        assert type(audit['cache_entries']) is int and audit['cache_entries']==len(target['modules'])+6+len(ACME_FILES)
    files = admission['files']
    assert 'manifest.json' not in files and files['cache-manifest.json'] == audit['cache_manifest_sha256']
    assert all(Path(name).name == name and name not in ('.', '..') and
               re.fullmatch('[a-f0-9]{64}', expected) for name, expected in files.items())
    return audit


def prepare(args):
    work = args.work.absolute()
    assert not work.exists() and work.resolve() == work
    assert re.fullmatch('sha256:[0-9a-f]{64}', args.image)
    assert args.cache_root_mode in (0o555, 0o755), 'Explicit actual image cache mode is required'
    context = args.context.absolute()
    files = {p.name: sha(read(p)) for p in sorted(context.iterdir())}
    manifest = json.loads(read(context / 'manifest.json'))
    with tarfile.open(context / 'payload.tar') as tar:
        source = tar.extractfile('app/hub.exs').read()
    assert sha(source) == manifest['files']['hub.exs']
    modules = ['Elixir.' + name for name in re.findall(r'^defmodule ([A-Za-z0-9_.]+) do$', source.decode(), re.M)]
    target, validator = target_binding(context, files['manifest.json'], sha(source))
    if target:
        assert target['modules']==modules and args.admission_manifest and not args.prefix_work
        native_checks=getattr(args,'native_checks',None)
        assert type(native_checks) is int and 1<=native_checks<=4096,'Explicit reviewed native count required for new source'
    else:
        assert len(modules) == len(set(modules)) == 59
        assert getattr(args,'native_checks',None) in (None,18)
        native_checks=18
    work.mkdir(parents=True, mode=0o700)
    shutil.copyfile(__file__, work / 'driver.py')
    (work / 'docker-config').mkdir(mode=0o700)
    (work / 'docker-config/config.json').write_bytes(b'{}')
    socket = Path('/var/run/docker.sock').resolve(strict=True)
    info = socket.stat()
    assert stat.S_ISSOCK(info.st_mode)
    plan = {'schema': 'adhd/cache-qualification-plan@1', 'prepared': True,
            'execution_ready': True, 'root_GO_required': True,
            'image': args.image, 'context': str(context), 'context_files': files,
            'artifact_sha256': sha(source), 'expected_modules': modules,
            'acme': target['acme'] if target else {}, 'native_checks': native_checks,
            'native_case_label': 'source-native'+str(native_checks) if target else 'original-native18',
            'cache_root_mode': args.cache_root_mode, 'cache_ebin_mode': 0o555, 'cache_file_mode': 0o444,
            'driver_sha256': sha(read(work / 'driver.py')), 'docker_sha256': sha(read('/usr/bin/docker')),
            'docker_socket': {'path': str(socket), 'identity': [info.st_dev, info.st_ino]},
            'python': {'path': str(Path(sys.executable).absolute()), 'realpath': str(Path('/proc/self/exe').resolve()),
                       'sha256': sha(read(Path('/proc/self/exe').resolve())), 'version': sys.version},
            'cases': list(CASES), 'application_deadline_seconds': 30,
            'SDK30_and_fault_custody': 'Separate unchanged original harness gates; not covered by this cache driver',
            'negative_scope': 'RW rootfs ONLY for offline tamper; fixed missing-file setup additionally user0 then original boot/non-serving sentinel. Other cases remain user10001. No host mounts, models or brokers.',
            'parallelism': 1, 'automatic_retries': 0}
    if target:
        (work/'input-validator.py').write_bytes(validator)
        plan['target_validator_sha256']=sha(validator)
        plan['cases'] += list(ACME_CASES)
    if args.admission_manifest:
        original_admission = args.admission_manifest.absolute()
        assert sha(read(original_admission)) == args.admission_sha256
        admission = json.loads(read(original_admission))
        audit = validate_compiled_admission(admission, args.image, sha(source), files['manifest.json'], target=target)
        if target:
            namespace={'__name__':'bound_compiler_inputs','__file__':str(work/'input-validator.py')}
            exec(compile(validator,str(work/'input-validator.py'),'exec'),namespace)
            namespace['compiled_admission'](context, original_admission, args.admission_sha256,
                                            args.image, sha(source), required=True)
        (work / 'admission').mkdir()
        selected = {'manifest.json': args.admission_sha256, **admission['files']}
        for name, expected in selected.items():
            assert Path(name).name == name and name not in ('.', '..')
            data = read(original_admission.parent / name); assert sha(data) == expected
            (work / 'admission' / name).write_bytes(data)
        assert sha(read(work / 'admission/cache-manifest.json')) == audit['cache_manifest_sha256']
        if target:
            raw_cache=json.loads(read(work/'admission/cache-manifest.json'))
            assert raw_cache['schema']==target['cache_schema'] and raw_cache['modules']==modules and raw_cache['acme']==target['acme']
            assert raw_cache['source_sha256']==sha(source) and raw_cache['payload_manifest_sha256']==files['manifest.json']
        plan['admission'] = {'manifest_sha256': args.admission_sha256, 'files': selected,
                             'cache_manifest_sha256': audit['cache_manifest_sha256']}
    else:
        assert args.admission_sha256 is None
    if args.prefix_work:
        old = args.prefix_work.absolute()
        old_plan = json.loads(read(old / 'plan.json')); old_result = json.loads(read(old / 'result.json'))
        completed = prefix_contract(old_plan, old_result, args.image, sha(source), args.cache_root_mode, files)
        assert old_result['plan_sha256'] == sha(read(old / 'plan.json'))
        (work / 'prefix').mkdir()
        names = {'plan.json', 'result.json', 'driver.py', 'execution.started'}
        names |= {p.name for p in old.glob('*.stdout')} | {p.name for p in old.glob('*.stderr')}
        for name in sorted(names): (work / 'prefix' / name).write_bytes(read(old / name))
        plan['prefix'] = {'plan_sha256': sha(read(old / 'plan.json')), 'result_sha256': sha(read(old / 'result.json')),
                          'whole_completed_cases': completed, 'original_passed': False,
                          'files': {p.name: sha(read(p)) for p in (work / 'prefix').iterdir()}}
        plan['cases'] = list(CASES[4:])
    (work / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    verify(work, plan)
    print(json.dumps({'prepared': True, 'executed': False, 'plan_sha256': sha(read(work / 'plan.json'))}))


def execute(args):
    work = args.work.absolute()
    assert args.plan_sha256 and sha(read(work / 'plan.json')) == args.plan_sha256
    plan = json.loads(read(work / 'plan.json'))
    verify(work, plan)
    fd = os.open(work / 'execution.started', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'plan_sha256': args.plan_sha256}, stream); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    runner = Runner(work, plan)
    results = []
    primary = None
    try:
        original = runner.cache_snapshot()
        if not plan.get('prefix'):
            label=plan.get('native_case_label','original-native18');checks=plan.get('native_checks',18)
            native = runner.case(label, ['--litai-test'])
            cases = json.loads(native.stdout)['cases']
            assert len(cases) == checks and all(c['outcome'] == 'passed' for c in cases)
            results.append({'case': label, 'passed': True, 'checks': checks})
            for operation in ('describe', 'protocol-schema', 'protocol-openapi'):
                result = runner.case(operation, [json.dumps([operation])])
                assert isinstance(json.loads(result.stdout), dict)
                results.append({'case': operation, 'passed': True})
            # The positive copied-cache control must pass before testing cp mutations.
            control = runner.case('offline-copy-control', ['["describe"]'], cache=original, negative=False)
            assert json.loads(control.stdout)['name'] == 'ADHD'
            results.append({'case': 'offline-copy-control', 'passed': True})
        with tarfile.open(Path(plan['context']) / 'payload.tar') as tar:
            source = tar.extractfile('app/hub.exs').read()
        beam = next(n for n in sorted(original) if n.endswith('.beam'))
        for name in plan['cases']:
            verify(work, plan)
            target = {'missing-manifest': '/runtime/adhd/manifest.json',
                      'missing-build-helper': '/runtime/adhd/build.exs',
                      'missing-lego': '/runtime/adhd/lego',
                      'missing-acme-guard': '/runtime/adhd/acme-guard',
                      'missing-beam': '/runtime/' + beam}.get(name)
            modified = None if target else mutation(original, name)
            changed_source = source + b'\n# controlled source drift\n' if name == 'changed-source' else None
            runner.case(name, ['["cache-guard-must-not-dispatch"]'], cache=modified,
                        source=changed_source, negative=True, helper_target=target)
            results.append({'case': name, 'passed': True})
        verify(work, plan)
    except BaseException as e:
        primary = e
        raise
    finally:
        report = {'schema': 'adhd/cache-qualification-result@1', 'passed': primary is None,
                  'plan_sha256': args.plan_sha256, 'image': plan['image'],
                  'artifact_sha256': plan['artifact_sha256'], 'results': results,
                  'prefix': plan.get('prefix'),
                  'container_ledger': runner.ledger,
                  'failure_type': type(primary).__name__ if primary else None,
                  'scope': 'Cache/CLI only; SDK cold readiness and fault observer custody remain separate gates'}
        (work / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true'); mode.add_argument('--execute', action='store_true')
    p.add_argument('--image'); p.add_argument('--context', type=Path)
    p.add_argument('--prefix-work', type=Path)
    p.add_argument('--native-checks', type=int, help='Explicit accepted native case count for a fresh schema2 source')
    p.add_argument('--admission-manifest', type=Path); p.add_argument('--admission-sha256')
    p.add_argument('--cache-root-mode', type=lambda value: int(value, 8), choices=(0o555, 0o755))
    p.add_argument('--work', type=Path, required=True); p.add_argument('--plan-sha256')
    args = p.parse_args()
    if args.prepare: prepare(args)
    else:
        assert Path(__file__).name == 'driver.py' and sys.flags.isolated, 'Execute only the reviewed frozen driver with python -I'
        execute(args)


if __name__ == '__main__': main()
