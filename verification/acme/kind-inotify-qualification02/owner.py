"""Bounded, temporary Kind inotify ceiling; no persistent host configuration."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time

assert os.getuid() == os.geteuid() == 0
setting = Path('/proc/sys/fs/inotify/max_user_instances')
assert setting.resolve(strict=True) == setting
original, temporary = '128', '512'
stop = threading.Event()
for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(sig, lambda *_: stop.set())
parent = os.getppid()
libc = ctypes.CDLL(None, use_errno=True)
assert libc.prctl(1, signal.SIGTERM, 0, 0, 0) == 0
assert os.getppid() == parent and not stop.is_set()
assert setting.read_text().strip() == original
deadline = time.monotonic() + 900
attempted = False

def write(value):
    fd = os.open(setting, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        raw = (value + '\n').encode()
        assert os.write(fd, raw) == len(raw)
    finally:
        os.close(fd)
    assert setting.read_text().strip() == value

def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)

try:
    attempted = True
    write(temporary)
    stat = Path('/proc/self/stat').read_text()
    emit({'schema': 'adhd/acme-temporary-inotify-owner@1', 'ready': True,
          'pid': os.getpid(), 'start_ticks': stat.rsplit(')', 1)[1].split()[19],
          'parent_pid': parent, 'original': int(original), 'temporary': int(temporary),
          'max_lifetime_seconds': 900, 'persistent_configuration_changed': False,
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    while not stop.is_set() and time.monotonic() < deadline:
        stop.wait(min(1, max(0, deadline - time.monotonic())))
finally:
    current = setting.read_text().strip()
    restored = current == original
    if attempted and current == temporary:
        write(original)
        restored = True
    emit({'schema': 'adhd/acme-temporary-inotify-restoration@1',
          'restored': restored, 'observed_before_restoration': int(current),
          'observed_final': int(setting.read_text().strip()),
          'external_value_preserved': current not in (original, temporary)})
