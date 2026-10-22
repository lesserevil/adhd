"""Scalar-ABI filesystem observer preparation and non-application image probe.

The test observer has no application changes or broker/model implementation.
Native build tools may create the shared object; only a successful actual-image
loader/rename/STOP/KILL probe permits its later use for image crash qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from uuid import uuid4

from container_fixture import OwnedImage

# No libc structure crosses this boundary: only stable scalar/pointer POSIX/Linux
# interfaces. The object has no glibc symbol versions, NEEDED libs or init runtime.
SCALAR_SYMBOLS = frozenset(('_exit', 'close', 'dlsym', 'free', 'fsync', 'getenv', 'getpid', 'kill',
    'malloc', 'memcpy', 'memmem', 'open', 'pause', 'read', 'snprintf', 'strchr', 'strcmp', 'strlen',
    'strncmp', 'strstr', 'syscall', 'write'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_observer(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = Path(__file__).with_name('multi_fault.c')
    library = root / 'image-filesystem-observer.so'
    assert not library.exists()
    argv = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-nostdlib',
            '-fno-stack-protector', '-U_FORTIFY_SOURCE', '-D_FORTIFY_SOURCE=0', '-O2', str(source), '-o', str(library)]
    subprocess.run(argv, check=True)
    dynamic = subprocess.check_output(['readelf', '-W', '-d', str(library)], text=True)
    versions = subprocess.check_output(['readelf', '-W', '-V', str(library)], text=True)
    header = subprocess.check_output(['readelf', '-W', '-h', str(library)], text=True)
    symbols = subprocess.check_output(['readelf', '-W', '--dyn-syms', str(library)], text=True)
    assert 'NEEDED' not in dynamic and 'GLIBC_' not in versions and 'Version needs section' not in versions
    assert re.search(r'Machine:\s+Advanced Micro Devices X86-64', header)
    assert re.search(r'Class:\s+ELF64', header) and re.search(r'Type:\s+DYN', header)
    undefined = set()
    for line in symbols.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[6] == 'UND':
            undefined.add(parts[7])
    assert undefined and undefined <= SCALAR_SYMBOLS, 'Observer uses an unreviewed ABI symbol'
    assert 'GLIBC_' not in symbols and '__' not in ' '.join(undefined)
    return library, {'source_sha256': digest(source), 'library_sha256': digest(library),
        'compile_argv': argv, 'elf_machine': 'x86_64', 'elf_class': 'ELF64',
        'undefined_scalar_symbols': sorted(undefined), 'needed_libraries': [], 'glibc_symbol_versions': [],
        'dynamic_sha256': hashlib.sha256(dynamic.encode()).hexdigest(),
        'symbol_table_sha256': hashlib.sha256(symbols.encode()).hexdigest(),
        'compiler_version': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0]}


def docker(*args, check=True, timeout=30):
    return subprocess.run(['docker', *args], capture_output=True, check=check, timeout=timeout)


def stop_owned_process(container_id, image, sentinel, library, expected_executable, expected_arguments):
    """Ancestor signal through a pidfd after binding the exact owned process."""
    row = json.loads(docker('inspect', container_id).stdout)[0]
    assert row['Id'] == container_id and row['Image'] == image and row['State']['Running']
    assert row['HostConfig']['PidMode'] in ('', 'private') and row['HostConfig']['ReadonlyRootfs']
    host_pid = row['State']['Pid']
    assert type(host_pid) is int and host_pid > 1
    descriptor = os.pidfd_open(host_pid)
    try:
        def identity():
            status = Path('/proc/' + str(host_pid) + '/status').read_text()
            fields = {line.split(':', 1)[0]: line.split(':', 1)[1].strip()
                      for line in status.splitlines() if ':' in line}
            assert [int(value) for value in fields['Uid'].split()] == [os.getuid()] * 4
            assert int(fields['NSpid'].split()[-1]) == sentinel['pid'] == 1
            namespace = os.readlink('/proc/' + str(host_pid) + '/ns/pid')
            assert namespace != os.readlink('/proc/self/ns/pid')
            executable = os.readlink('/proc/' + str(host_pid) + '/exe')
            assert Path(executable).name == expected_executable
            cmdline = Path('/proc/' + str(host_pid) + '/cmdline').read_bytes()
            arguments = cmdline.split(b'\0')
            assert all(str(value).encode() in arguments for value in expected_arguments)
            maps = Path('/proc/' + str(host_pid) + '/maps').read_text()
            assert str(library) in maps and '/lib/ld-musl-x86_64.so.1' in maps
            stat = Path('/proc/' + str(host_pid) + '/stat').read_text()
            start_time = stat.rsplit(')', 1)[1].split()[19]
            return (start_time, namespace, executable, hashlib.sha256(cmdline).hexdigest(),
                    hashlib.sha256(maps.encode()).hexdigest())
        first = identity()
        again = json.loads(docker('inspect', container_id).stdout)[0]
        assert again['Id'] == container_id and again['Image'] == image and again['State']['Pid'] == host_pid
        assert identity() == first
        signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = Path('/proc/' + str(host_pid) + '/status').read_text()
            if re.search(r'^State:\s+T\b', status, re.M):
                break
            time.sleep(.005)
        else:
            raise AssertionError('Actual owned image process did not enter kernel STOP')
        return {'host_process_pid': host_pid, 'namespace_pid': sentinel['pid'],
            'signal_method': 'ancestor-pidfd-SIGSTOP', 'pid_namespace': first[1],
            'executable_basename': expected_executable, 'cmdline_sha256': first[3],
            'process_maps_sha256': first[4], 'kernel_state': 'stopped'}
    finally:
        os.close(descriptor)


def probe_image(image, manifest, work):
    assert re.fullmatch(r'sha256:[a-f0-9]{64}', image)
    work = Path(work).resolve()
    assert not work.exists()
    work.mkdir(parents=True, mode=0o700)
    library, build = compile_observer(work)
    manifest = Path(manifest).resolve()
    reviewed = manifest.read_bytes()
    artifact = json.loads(reviewed)['files']['hub.exs']
    config, store = work / 'probe-config.json', work / 'probe-state.dets'
    marker = Path(str(config) + '.project-upgrade')
    marker.write_text('{"phase":"decided"}')
    marker.chmod(0o600)
    source, target = work / 'stage.snapshot', Path(str(store) + '.snapshot')
    source.write_bytes(b'owned-image-observer-real-rename\n')
    source.chmod(0o600)
    content = source.read_bytes()
    sentinel = work / 'observer.json'
    name = 'adhd-observer-probe-' + uuid4().hex[:16]
    inspected = None
    observed = None
    result = None
    try:
        identifier = docker('run', '--detach', '--name', name, '--network', 'none', '--read-only',
            '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', '128m', '--cpus', '1', '--pids-limit', '32',
            '--mount', 'type=bind,src=' + str(work) + ',dst=' + str(work),
            '--env', 'LD_PRELOAD=' + str(library), '--env', 'ADHD_CRASH_STAGE=after-snapshot',
            '--env', 'ADHD_CRASH_CONFIG=' + str(config), '--env', 'ADHD_CRASH_STORE=' + str(store),
            '--env', 'ADHD_CRASH_SENTINEL=' + str(sentinel), '--entrypoint', '/bin/mv', image,
            str(source), str(target)).stdout.decode().strip()
        assert re.fullmatch('[a-f0-9]{64}', identifier)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            inspected = json.loads(docker('inspect', identifier).stdout)[0]
            assert inspected['Image'] == image
            if sentinel.exists():
                observed = json.loads(sentinel.read_text())
                assert observed == {'stage': 'after-snapshot', 'pid': 1}
                custody = stop_owned_process(identifier, image, observed, library, 'busybox',
                                              ['/bin/mv', str(source), str(target)])
                host_pid = custody['host_process_pid']
                break
            assert inspected['State']['Running'], 'Image observer process exited without reaching the real boundary'
            time.sleep(.01)
        else:
            raise AssertionError('Image observer did not stop at the real rename boundary')
        assert observed == {'stage': 'after-snapshot', 'pid': 1}
        assert target.read_bytes() == content and not source.exists(), 'Observer stopped before successful rename'
        assert inspected['HostConfig']['NetworkMode'] == 'none' and inspected['HostConfig']['ReadonlyRootfs']
        assert inspected['HostConfig']['PidMode'] in ('', 'private')
        maps = docker('exec', identifier, 'cat', '/proc/1/maps').stdout.decode()
        assert str(library) in maps and re.search(r'/lib/ld-musl-x86_64.so.1', maps)
        actual_manifest = docker('exec', identifier, 'cat', '/app/manifest.json').stdout
        assert actual_manifest == reviewed
        actual_artifact = docker('exec', identifier, 'sha256sum', '/app/hub.exs').stdout.decode().split()[0]
        assert actual_artifact == artifact
        docker('kill', '--signal', 'KILL', identifier)
        exit_code = int(docker('wait', identifier).stdout)
        assert exit_code == 137
        result = {'schema': 'adhd/image-observer-loader-probe@1', 'passed': True,
            'application_started': False, 'model_or_broker_calls': 0, 'image_config_identity': image,
            'artifact_sha256': artifact, 'canonical_manifest_sha256': hashlib.sha256(reviewed).hexdigest(),
            'observer': build, 'container_id': identifier, 'network_mode': 'none', 'readonly_rootfs': True,
            'namespace_pid': 1, 'host_process_pid': host_pid, 'kernel_state': 'stopped',
            'successful_rename_verified': True, 'actual_musl_loader': '/lib/ld-musl-x86_64.so.1',
            'process_maps_sha256': hashlib.sha256(maps.encode()).hexdigest(), 'exit_code': exit_code,
            'process_custody': custody, 'pid1_signal_reference':
            'https://www.man7.org/linux/man-pages/man7/pid_namespaces.7.html'}
    finally:
        docker('rm', '--force', name, check=False)
        absent = docker('inspect', name, check=False)
        assert absent.returncode != 0 and b'no such' in absent.stderr.lower(), 'Owned observer probe cleanup unproven'
    assert result is not None
    result['owned_container_absent'] = True
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True)
    p.add_argument('--image-manifest', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    value = probe_image(a.image, a.image_manifest, a.work)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(value, indent=2) + '\n')
    print('PASS actual-image scalar observer loader/rename/STOP/KILL probe')
