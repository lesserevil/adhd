"""Passive owned-VM descendant ledger; no global process enumeration or launch."""
import os
from pathlib import Path
import signal
import threading
import time


def identity(pid):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'start_ticks':stat[19],'state':stat[0],'parent_pid':int(stat[1])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def same(row):
    current = identity(row['pid'])
    return current is not None and current['start_ticks']==row['start_ticks']


class Descendants:
    def __init__(self, pid, start_ticks):
        self.root = {'pid':pid,'start_ticks':start_ticks}
        self.rows, self.errors = {}, []
        self.stop_event = threading.Event()
        self.thread = None

    def sample(self):
        if not same(self.root):
            return
        queue, visited = [self.root], set()
        while queue:
            parent_row = queue.pop()
            parent = parent_row['pid']
            if parent in visited:
                continue
            if not same(parent_row):
                continue
            visited.add(parent)
            if len(visited)>128:
                raise AssertionError('Owned process graph bound')
            try:
                children = Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
            except (FileNotFoundError, ProcessLookupError):
                continue
            if not same(parent_row):
                continue
            for value in children:
                pid = int(value)
                row = identity(pid)
                if row is None or row['parent_pid'] != parent:
                    continue
                queue.append(row)
                key = (pid,row['start_ticks'])
                if key not in self.rows:
                    try:
                        exe = os.readlink(f'/proc/{pid}/exe')
                    except (FileNotFoundError,ProcessLookupError):
                        continue
                    if same(row):
                        self.rows[key] = {**row,'parent_pid':parent,'executable_basename':Path(exe).name,
                                          'first_observed_monotonic':time.monotonic()}

    def start(self):
        assert self.thread is None
        self.sample()
        def watch():
            while not self.stop_event.wait(.05):
                try:
                    self.sample()
                except BaseException as error:
                    self.errors.append(type(error).__name__)
                    return
        self.thread = threading.Thread(target=watch)
        self.thread.start()
        return self

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
            assert not self.thread.is_alive()
        deadline = time.monotonic()+5
        while any(same(row) for row in self.rows.values()) and time.monotonic()<deadline:
            time.sleep(.05)
        remaining = [row for row in self.rows.values()if same(row)]
        # Any observed child that outlives the original EOF/reap allowance is a
        # failure, even if final emergency own-PID cleanup succeeds.
        for row in remaining:
            try:
                descriptor = os.pidfd_open(row['pid'])
            except ProcessLookupError:
                continue
            try:
                if same(row):
                    try:
                        signal.pidfd_send_signal(descriptor,signal.SIGKILL)
                        row['emergency_own_pid_kill'] = True
                    except ProcessLookupError:
                        pass
            finally:
                os.close(descriptor)
        for row in self.rows.values():
            row['original_identity_absent'] = not same(row)
        assert not remaining and not self.errors, 'Owned observed child closure failed'

    def evidence(self):
        return {'scope':'Observed descendants only; polling cannot prove complete historical issuance of very short-lived children',
                'rows':list(self.rows.values()),'errors':list(self.errors),
                'observer_closed':self.thread is None or not self.thread.is_alive()}
