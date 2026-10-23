#!/usr/bin/env python3
"""Inert until explicitly invoked: bind actual whole Kind evidence to a new request.

Never invokes the final composition writer or any process/service/CLI.
Unknown future proof layouts reject rather than infer compatibility.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path

ROOT = Path('/home/horde/src/adhd')
BASE = ROOT / 'verification/acme/final-composition-preparation'
HELPER_SHA = '982e1faf23ce33c11edc8c2344d7ceb2fd65570f677070a96aa8e9a93a6a407a'
REQUEST_SHA = '6f3080525c5a8bd17c4e9fdf9e3f9ab3abd1d8c5f853a6e0406c90f823163d3d'
OUTPUT = ROOT / '_build/acme/final-composition-request-kind19.json'

def regular(path, expected):
    assert path.absolute() == path.resolve(strict=True)
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 16 * 1024 * 1024
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    return raw

def prepare(manifest, manifest_sha):
    regular(BASE / 'compose06.py', HELPER_SHA)
    spec = importlib.util.spec_from_file_location('reviewed_composition06', BASE / 'compose06.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = module.decode(regular(BASE / 'request.json', REQUEST_SHA))
    before = module.collect(request)
    assert before['passed'] is False
    assert before['pending'] == [{'gate': 'platform/kind', 'reason': 'Missing/pending actual positive binding'}]
    assert request['platforms']['kind'] is None
    ref = {'path': str(manifest.absolute()), 'sha256': manifest_sha}
    module.read(ref)  # Exact hash, regular/noalias and verification-only path guard.
    request['platforms']['kind'] = ref
    request['pending_scope'] = ('Both separately observed whole-platform scopes supplied for strict checking. '
                                'Original Compose12 aggregate remains false. Final writer still requires separate root GO.')
    checked = module.collect(request)
    assert checked['passed'] is True and checked['pending'] == [], 'Actual Kind evidence rejected; no request emitted'
    assert checked['evidence']['platform/kind']['selected_whole_named_checks'] == list(module.PLATFORM_NAMES)
    assert checked['platform_composition']['single_aggregate_matrix_pass_claimed'] is False
    assert not OUTPUT.exists() and OUTPUT.parent.resolve(strict=True) == OUTPUT.parent
    raw = (json.dumps(request, indent=2) + '\n').encode()
    fd = os.open(OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(OUTPUT.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'request_path': str(OUTPUT), 'request_sha256': hashlib.sha256(raw).hexdigest(),
            'final_manifest_written': False, 'runtime_calls': 0, 'helper_sha256': HELPER_SHA,
            'read_only_check_argv': [str(ROOT / '.venv/bin/python'), '-I', '-S', '-B',
                str(BASE / 'compose06.py'), '--request', str(OUTPUT),
                '--request-sha256', hashlib.sha256(raw).hexdigest()]}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind-manifest', type=Path, required=True)
    parser.add_argument('--kind-manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.kind_manifest, args.kind_manifest_sha256), indent=2))
