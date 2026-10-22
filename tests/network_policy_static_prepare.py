#!/usr/bin/env python3
"""Prepare static TCP compiler inputs only; never invoke a compiler or runtime.

Uses the existing reviewed host closure, including compiler binaries, headers,
archives, linker scripts and their dynamic tool dependencies. Compilation and
an actual immutable-image protocol probe require separate root GO/evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import image_host_dependencies as host


def prepare(source, host_closure, output):
    source = Path(source).absolute(); output = Path(output).absolute()
    assert source.resolve(strict=True) == source and source.is_file() and not source.is_symlink()
    assert output.resolve() == output and not output.exists()
    closure = json.loads(Path(host_closure).read_text())
    host.verify(closure)  # read-only full SET/hash/alias verification; no subprocess
    compiler = closure['tools']['cc']
    assert compiler['path'] == '/usr/bin/cc' and compiler['realpath'] == '/usr/bin/x86_64-linux-gnu-gcc-13'
    # Static glibc startup is additional to prior shared-observer compilation.
    additions = {str(p): host.path_binding(p) for p in (
        Path('/usr/lib/x86_64-linux-gnu/crt1.o'), Path('/usr/lib/x86_64-linux-gnu/crti.o'),
        Path('/usr/lib/x86_64-linux-gnu/crtn.o'), Path('/usr/lib/x86_64-linux-gnu/libc.a'),
        Path('/usr/lib/gcc/x86_64-linux-gnu/13/crtbeginT.o'),
        Path('/usr/lib/gcc/x86_64-linux-gnu/13/crtend.o'),
        Path('/usr/lib/gcc/x86_64-linux-gnu/13/libgcc.a'),
        Path('/usr/lib/gcc/x86_64-linux-gnu/13/libgcc_eh.a'))}
    source_bytes = source.read_bytes()
    value = {'schema': 'adhd/network-policy-static-build-preparation@1', 'executed': False,
        'runtime_ready': False, 'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'host_closure_sha256': host.sha(host_closure), 'static_additions': additions,
        'argv': [compiler['path'], '-static', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-fno-ident', '-Wl,--build-id=none', '-o', 'tcp', 'network_policy_tcp.c'],
        'cwd': str(output), 'env': {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
            'SOURCE_DATE_EPOCH': '0', 'TMPDIR': str(output / 'tmp')},
        'required_after_compile': ['compiler exit0 and unchanged complete host/source closure',
            'ELF64 x86_64 no PT_INTERP/PT_DYNAMIC; decoded size <=1MiB',
            'actual admitted-image serve/probe fragmented exact15-byte prefix and failure taxonomy',
            'known-ID/name strict absence and immutable image/namespace custody'],
        'scope': 'TCP policy fixture only; no application/Kafka/BEAM or OOM qualification'}
    output.mkdir(mode=0o700)
    (output / 'network_policy_tcp.c').write_bytes(source_bytes)
    (output / 'host-dependencies.json').write_bytes(Path(host_closure).read_bytes())
    (output / 'plan.json').write_text(json.dumps(value, indent=2) + '\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'host-closure', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    prepare(args.source, args.host_closure, args.output)
