import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

root = Path('/home/horde/src/adhd')
preparation = root / '_build/acme/image42-plans05/preparation.json'
assert hashlib.sha256(preparation.read_bytes()).hexdigest() == 'ad9e2d02c702c496de6d6e36d434764ac64a8052d830bd6983f99cfc03655160'
value = json.loads(preparation.read_bytes())
selection = sys.argv[1:]
assert selection and len(selection) == len(set(selection))
assert 'foundation' not in selection, 'Foundation04 positive is preserved; do not rerun it here'
rows = {row['name']: row for row in value['plans']}
assert all(name in rows for name in selection)
lock = root / '_build/acme/http01.lane.lock'
descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
try:
    entry = os.fstat(descriptor)
    assert stat.S_ISREG(entry.st_mode) and entry.st_uid == os.getuid() and entry.st_nlink == 1
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name in selection:
        row = rows[name]
        path = Path(row['plan'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['plan_sha256']
        assert not path.with_name('started.json').exists()
        print('START', name, flush=True)
        with path.with_name('execution.stdout').open('xb') as out, path.with_name('execution.stderr').open('xb') as err:
            result = subprocess.run(row['execute_argv'], cwd=root, stdout=out, stderr=err)
        print('EXIT', name, result.returncode, flush=True)
        assert result.returncode == 0, 'Phase failed; original evidence retained: ' + name
        report = json.loads(path.with_name('result.json').read_bytes())
        assert report['passed'] is True
finally:
    os.close(descriptor)
