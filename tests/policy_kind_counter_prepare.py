#!/usr/bin/env python3
"""Read-only compiler/input preparation for counter19. No compiler/process runner.

This entry point deliberately has no compile or execute verb. A later reviewed
plan must bind the actual static ELF and prove the original image executable.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import time

IMAGE = 'sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21'
TOOLS = ('/usr/bin/x86_64-linux-gnu-gcc-13',
         '/usr/libexec/gcc/x86_64-linux-gnu/13/cc1',
         '/usr/libexec/gcc/x86_64-linux-gnu/13/collect2',
         '/usr/bin/x86_64-linux-gnu-as', '/usr/bin/x86_64-linux-gnu-ld.bfd')
TREES = ('/usr/include', '/usr/lib/gcc/x86_64-linux-gnu/13',
         '/usr/libexec/gcc/x86_64-linux-gnu/13', '/usr/lib/llvm-18/lib/clang/18/include')
STATIC = ('/usr/lib/x86_64-linux-gnu/crt1.o', '/usr/lib/x86_64-linux-gnu/crti.o',
          '/usr/lib/x86_64-linux-gnu/crtn.o', '/usr/lib/x86_64-linux-gnu/libc.a',
          '/usr/lib/x86_64-linux-gnu/libc_nonshared.a')
DOCS = ('/usr/share/doc/gcc-13/copyright', '/usr/share/doc/libc6-dev/copyright',
        '/usr/share/doc/binutils/copyright')
LIBDIRS = ('/lib/x86_64-linux-gnu', '/usr/lib/x86_64-linux-gnu', '/lib64', '/lib', '/usr/lib')

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def read(path, cap=256*1024*1024):
    """Hash one real regular input through an identity-stable descriptor."""
    p = Path(path)
    assert p.is_absolute() and not p.is_symlink() and p.resolve(strict=True) == p
    before = p.lstat()
    assert stat.S_ISREG(before.st_mode) and before.st_size <= cap
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        assert identity(os.fstat(fd)) == identity(before)
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, cap + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            assert len(data) <= cap
        assert identity(os.fstat(fd)) == identity(before) == identity(p.lstat())
        return bytes(data)
    finally:
        os.close(fd)

def file_binding(path):
    p = Path(path).absolute()
    # System-tool aliases are explicit bindings, never silently dereferenced.
    aliases = []
    q = p
    for _ in range(16):
        if not q.is_symlink():
            break
        target = os.readlink(q)
        aliases.append({'path': str(q), 'link': target})
        q = (q.parent / target).absolute() if not target.startswith('/') else Path(target)
    else:
        raise AssertionError('tool symlink depth')
    real = p.resolve(strict=True)
    data = read(real)
    return {'path': str(p), 'realpath': str(real), 'aliases': aliases,
            'sha256': sha(data), 'size': len(data), 'mode': stat.S_IMODE(real.stat().st_mode)}

def tree(path):
    root = Path(path)
    assert root.is_absolute() and not root.is_symlink() and root.resolve(strict=True) == root
    dirs, files, links = [], {}, {}
    for base, names, leaves in os.walk(root, followlinks=False):
        for name in sorted(names + leaves):
            p = Path(base) / name
            rel = p.relative_to(root).as_posix()
            info = p.lstat()
            if stat.S_ISLNK(info.st_mode):
                # Link graph and independently read target bytes are both frozen;
                # os.walk never traverses a redirected directory.
                real = p.resolve(strict=True)
                row = {'target': os.readlink(p), 'realpath': str(real)}
                if real.is_file():
                    row.update(sha256=sha(read(real)), size=real.stat().st_size)
                else:
                    assert real.is_dir() and (real == root or root in real.parents or str(real) in TREES), 'unbound external directory redirect'
                links[rel] = row
            elif stat.S_ISDIR(info.st_mode):
                dirs.append(rel)
            else:
                assert stat.S_ISREG(info.st_mode), 'special compiler input'
                data = read(p)
                files[rel] = {'sha256': sha(data), 'size': len(data), 'mode': stat.S_IMODE(info.st_mode)}
    return {'root': str(root), 'directories': sorted(dirs), 'files': files, 'links': links}

def elf_dependencies(raw):
    """Bounded ELF64 little-endian x86_64 program-header reader; never dlopen."""
    assert raw[:7] == b'\x7fELF\x02\x01\x01' and len(raw) >= 64
    assert struct.unpack_from('<H', raw, 18)[0] == 62
    off = struct.unpack_from('<Q', raw, 32)[0]
    entsize, count = struct.unpack_from('<HH', raw, 54)
    assert entsize == 56 and 0 < count <= 128 and off + count * 56 <= len(raw)
    headers = [struct.unpack_from('<IIQQQQQQ', raw, off+i*56) for i in range(count)]
    for h in headers:
        assert h[2] + h[5] <= len(raw)
    def cstring(start, end):
        assert 0 <= start < end <= len(raw)
        stop = raw.find(b'\0', start, end)
        assert stop >= start
        return raw[start:stop].decode('ascii')
    interpreter = [cstring(h[2], h[2]+h[5]) for h in headers if h[0] == 3]
    assert len(interpreter) <= 1
    dynamic = [h for h in headers if h[0] == 2]
    assert len(dynamic) <= 1
    needed, strings, stringsz = [], None, None
    if dynamic:
        h = dynamic[0]
        assert h[5] % 16 == 0 and h[5] <= 1024*1024
        ended = False
        for pos in range(h[2], h[2]+h[5], 16):
            tag, value = struct.unpack_from('<qQ', raw, pos)
            if tag == 0:
                ended = True
                break
            if tag == 1:
                needed.append(value)
            if tag == 5:
                strings = value
            if tag == 10:
                stringsz = value
            assert tag not in (15, 29), 'unmodeled ELF RPATH/RUNPATH'
        assert ended
    names = []
    if needed:
        assert strings is not None and stringsz is not None and stringsz <= 16*1024*1024
        loads = [h for h in headers if h[0] == 1 and h[3] <= strings and strings+stringsz <= h[3]+h[5]]
        assert len(loads) == 1
        base = loads[0][2] + strings-loads[0][3]
        for index in needed:
            assert index < stringsz
            name = cstring(base+index, base+stringsz)
            assert re.fullmatch(r'[A-Za-z0-9_+.-]+', name), 'unsafe ELF dependency'
            names.append(name)
    return interpreter, names

def tool_closure():
    pending = list(TOOLS)
    result = {}
    while pending:
        path = pending.pop()
        item = file_binding(path)
        real = item['realpath']
        if real in result:
            continue
        raw = read(Path(real))
        interp, needed = elf_dependencies(raw)
        item.update(interpreter=interp, needed=needed)
        result[real] = item
        pending.extend(interp)
        for name in needed:
            found = next((str(Path(d)/name) for d in LIBDIRS if (Path(d)/name).is_file()), None)
            assert found, name
            pending.append(found)
    return result

def serve(source):
    tree = ast.parse(source)
    rows = [n.value for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'SERVE' for t in n.targets)]
    assert len(rows) == 1
    value = ast.literal_eval(rows[0])
    assert isinstance(value, str) and 0 < len(value.encode()) <= 4096
    return value

def gate_argv(nonce, original):
    assert re.fullmatch('[a-f0-9]{32}', nonce)
    return ['/adhd-diagnostic/startup-gate', 'gate', nonce,
            '/usr/local/bin/elixir', 'elixir', '-e', original]

def vector_hash(values):
    assert values and all(isinstance(x, str) and '\0' not in x for x in values)
    return sha(b''.join(v.encode()+b'\0' for v in values))

def environment_hash(entries):
    assert entries and all('=' in x and '\0' not in x for x in entries)
    flags = [x.split('=', 1)[1] for x in entries if x.startswith('ERL_FLAGS=')]
    assert 1 <= len(flags) <= 2 and all(x in ('+S 2:2', '+S 1:1') for x in flags)
    return vector_hash(entries)

def counter_directory(namespace_path):
    # Input is the exact path derived from authenticated Pod UID/CID, never a
    # path discovered by walking cgroups. Match C open_counters mount join.
    assert isinstance(namespace_path, str) and namespace_path.startswith(('/kubepods/', '/kubepods.slice/', '/kubelet.slice/'))
    assert all(x not in ('', '.', '..') for x in namespace_path[1:].split('/'))
    assert re.fullmatch(r'/[A-Za-z0-9_./-]+', namespace_path)
    return '/sys/fs/cgroup' + namespace_path


def release_allowed(now, deadline):
    return isinstance(now, int) and isinstance(deadline, int) and 20_000_000_000 <= deadline-now <= 30_000_000_000

def prepare(work):
    work = Path(work).absolute()
    assert not work.exists() and work.parent.resolve(strict=True) == work.parent
    source = Path(__file__).with_name('policy_kind_counter.c').absolute()
    policy = source.with_name('kafka_network_policy.py')
    original = serve(read(policy).decode())
    c = read(source).decode()
    literal = re.search(r'static const char original_serve\[\] = (.*);\n', c)
    assert literal and json.loads(literal.group(1)) == original
    compiler = TOOLS[0]
    output = work/'startup-gate'
    command = [compiler, '-static', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fno-lto', '-fno-pie', '-no-pie', '-Wl,--build-id=none', '-nostdinc',
               '-isystem', '/usr/lib/gcc/x86_64-linux-gnu/13/include',
               '-isystem', '/usr/include/x86_64-linux-gnu', '-isystem', '/usr/include',
               '-o', str(output), str(source)]
    plan = {'schema': 'adhd/native-kind-live-counter19-source-preparation@1',
            'prepared': True, 'compiled': False, 'executed': False,
            'root_compile_and_execution_GO_required': True,
            'source': file_binding(source), 'original_policy': file_binding(policy),
            'preparer': file_binding(Path(__file__).absolute()),
            'original_SERVE_sha256': sha(original.encode()), 'utility_image': IMAGE,
            'future_compile_argv': command,
            'future_compile_environment': {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C',
                                           'HOME': '/nonexistent', 'SOURCE_DATE_EPOCH': '0'},
            'environment_policy': 'env -i exact map; no CPATH/LIBRARY_PATH/LD_/GCC override inheritance',
            'compiler_ELF_closure': tool_closure(), 'compiler_trees': [tree(p) for p in TREES],
            'static_and_license_inputs': [file_binding(p) for p in STATIC+DOCS],
            'gate_argv_example': gate_argv('0'*32, original),
            'gate_ENV': 'execve uses original environ pointer and ordered duplicates unchanged; full CRI vector hash required',
            'observer_argv': ['HELPER', 'inspect|observe', 'CRI_PID', 'POD_UID', 'CID', 'NONCE',
                              'GATE_SHA256', 'EXACT_GATE_ARGV_NUL_SHA256', 'ORDERED_ENV_NUL_SHA256',
                              'CRI_CGROUPS_PATH', 'ORIGINAL_READY30_ABSOLUTE_MONOTONIC_NS',
                              'observe-only:PREINSPECTED_START_TICKS', 'observe-only:PIDNS_INO', 'observe-only:MNTNS_INO'],
            'bounds': {'Ready_seconds_including_hold': 30, 'release_within_seconds': 10,
                       'sample_frames': 256, 'stdout_bytes': 8*1024*1024, 'ELF_bytes': 1048576,
                       'counter_files': 18, 'signals': 'gate self-SIGSTOP; observer pidfd-SIGCONT ONLY'},
            'invariant': 'one known PID/Pod/CID, actual proc cgroup equals exact CRI expansion, root cgroup2 mount only; unknown view fails closed',
            'not_yet_proven': ['C has NOT been compiled or executed; SHA256/parse/native behavior needs authorized probes',
                               'Actual original /usr/local/bin/elixir executable resolution in exact image must be verified before cluster plan',
                               'No ConfigMap delivery/CRI discovery/parent executor implementation or cluster execution in this preparation',
                               'Host and owned-node CLOCK_MONOTONIC/time namespace comparability must be bound by future executor before passing host Ready deadline',
                               'Parent hierarchical oom_kill alone cannot attribute this utility kill; child scoped delta/correlation is required',
                               'No OOM cause, route, app, model or production qualification'],
            'created_monotonic_ns': time.monotonic_ns()}
    work.mkdir(mode=0o700)
    raw = canonical(plan)
    (work/'plan.json').write_bytes(raw)
    return {'plan': str(work/'plan.json'), 'sha256': sha(raw), 'compiler_executed': False,
            'ELF_tool_count': len(plan['compiler_ELF_closure']),
            'tree_files': sum(len(t['files']) for t in plan['compiler_trees'])}

def verify(plan):
    for key in ('source', 'preparer', 'original_policy'):
        assert file_binding(plan[key]['path']) == plan[key]
    assert tool_closure() == plan['compiler_ELF_closure']
    for item in plan['compiler_trees']:
        assert tree(item['root']) == item
    for item in plan['static_and_license_inputs']:
        assert file_binding(item['path']) == item
    assert plan['compiled'] is False and plan['executed'] is False
    return {'verified': True, 'compiler_executed': False, 'runtime_starts': 0}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare')
    group.add_argument('--verify')
    args = parser.parse_args()
    print(json.dumps(prepare(args.prepare) if args.prepare else verify(json.loads(read(Path(args.verify).absolute()))), sort_keys=True))
