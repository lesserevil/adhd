#!/usr/bin/env python3
"""Create a byte-pinned native Linux front door for an installed Elixir launcher."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elixir', default=shutil.which('elixir'))
    parser.add_argument('--directory', default='_build/tools/elixir-front')
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('This compatibility launcher is only needed on Linux')
    if not args.elixir:
        parser.error('Install Elixir 1.18+ and Erlang/OTP 27+ first')
    script = Path(args.elixir).resolve(strict=True)
    payload = script.read_bytes()
    if not payload.startswith(b'#!'):
        parser.error('Select the official shell launcher; a native executable needs no front door')
    root = Path(args.directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    header = root / 'pin.h'
    header.write_text('#define ADHD_ELIXIR_PINNED_BYTES {' + ','.join(map(str, payload)) + '}\n')
    executable = root / 'elixir'
    subprocess.run([args.cc, '-O2', '-Wall', '-Wextra',
                    '-DADHD_ELIXIR_SCRIPT=' + json.dumps(str(script)),
                    '-include', str(header), str(Path(__file__).with_suffix('.c')),
                    '-o', str(executable)], check=True)
    record = {'executable': str(executable), 'script': str(script),
              'script_sha256': hashlib.sha256(payload).hexdigest()}
    (root / 'launcher.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
