"""Owned local process tests only; no hub, CA, socket, shell or model."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = '''import json,os,signal,sys,time
mode=sys.argv[1]
if mode == 'exit': sys.exit(int(sys.argv[2]))
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=os.fork()
if child==0:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 while True: time.sleep(1)
with open(sys.argv[2],'w') as f: json.dump({'parent':os.getpid(),'child':child,'pgid':os.getpgrp(),'argv':sys.argv[3:]},f)
if mode=='leave':sys.exit(0)
while True: time.sleep(1)
'''

class Guardian(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix='acme-guard-test-'))
        cls.binary = cls.directory / 'acme-guard'
        supplied=os.environ.get('ADHD_TEST_ACME_GUARD')
        if supplied:
            source=Path(supplied).resolve(strict=True)
            if not source.is_file(): raise ValueError('test guardian binary')
            shutil.copyfile(source,cls.binary);cls.binary.chmod(0o755)
        else:
            subprocess.run([shutil.which('cc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(ROOT/'deploy/runtime/acme-guard.c'), '-o', str(cls.binary)], check=True)
        cls.helper = cls.directory / 'helper.py'
        cls.helper.write_text(HELPER)
        cls.libc = ctypes.CDLL(None, use_errno=True)
        if cls.libc.prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), 'test subreaper setup')
    @classmethod
    def tearDownClass(cls):
        cls.libc.prctl(36, 0, 0, 0, 0)
        shutil.rmtree(cls.directory)
    def setUp(self):
        self.owned = []
        self.state = self.directory / (self._testMethodName + '.json')
    def tearDown(self):
        for process in self.owned:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None: stream.close()
    def argv(self, timeout=2000, mode='hold', extra=()):
        return [str(self.binary), '--lock-file', str(self.directory/'owner.lock'), '--timeout-ms', str(timeout), '--grace-ms', '40', '--',
                sys.executable, str(self.helper), mode, str(self.state), *extra]
    def start(self, **kwargs):
        p=subprocess.Popen(self.argv(**kwargs), stdin=subprocess.PIPE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.owned.append(p)
        return p
    def ready(self, process):
        end=time.monotonic()+2
        while time.monotonic()<end:
            if self.state.exists():
                try:
                    state=json.loads(self.state.read_text())
                except json.JSONDecodeError:
                    continue
                self.assertEqual(state['parent'],state['pgid'])
                return state
            self.assertIsNone(process.poll())
            time.sleep(.005)
        self.fail('owned child never reached observable boundary')
    def absent(self, state):
        self.assertFalse(Path('/proc',str(state['parent'])).exists())
        self.assertFalse(Path('/proc',str(state['child'])).exists())
    def test_normal_exit_and_failure_preserved(self):
        for code in (0,7):
            p=subprocess.Popen([str(self.binary),'--lock-file',str(self.directory/'owner.lock'),'--timeout-ms','1000','--grace-ms','40','--',
                                sys.executable,str(self.helper),'exit',str(code)],stdin=subprocess.PIPE)
            self.owned.append(p)
            self.assertEqual(p.wait(timeout=2),code)
        p=subprocess.Popen([str(self.binary),'--lock-file',str(self.directory/'owner.lock'),'--timeout-ms','1000','--grace-ms','40','--',
                            '/definitely-absent-acme-client'],stdin=subprocess.PIPE)
        self.owned.append(p)
        self.assertEqual(p.wait(timeout=2),127)
    def test_eof_kills_and_reaps_entire_resistant_group(self):
        p=self.start();state=self.ready(p);p.stdin.close()
        self.assertEqual(p.wait(timeout=2),125);self.absent(state)
    def test_absolute_internal_deadline_kills_group(self):
        began=time.monotonic();p=self.start(timeout=180);state=self.ready(p)
        self.assertEqual(p.wait(timeout=2),124);self.absent(state)
        self.assertLess(time.monotonic()-began,1.5)
    def test_stdin_traffic_never_extends_deadline(self):
        began=time.monotonic();p=self.start(timeout=180);state=self.ready(p)
        while p.poll() is None:
            try:p.stdin.write(b'keepalive');p.stdin.flush()
            except BrokenPipeError:break
            time.sleep(.01)
        self.assertEqual(p.wait(timeout=2),124);self.absent(state)
        self.assertLess(time.monotonic()-began,1.5)
    def test_signal_cancellation_kills_group(self):
        p=self.start();state=self.ready(p);p.send_signal(signal.SIGTERM)
        self.assertEqual(p.wait(timeout=2),125);self.absent(state)
    def test_success_cannot_leave_descendants(self):
        p=self.start(mode='leave');state=self.ready(p)
        self.assertEqual(p.wait(timeout=2),0);self.absent(state)
    def test_no_shell_interpretation(self):
        value='literal;$(touch forbidden)'
        p=self.start(extra=(value,));state=self.ready(p)
        self.assertEqual(state['argv'],[value]);p.stdin.close()
        self.assertEqual(p.wait(timeout=2),125);self.absent(state)
    def test_invalid_deadlines_or_relative_executable_reject(self):
        for budget in ['0','-1','1x','3600001','+1']:
            self.assertEqual(subprocess.run([str(self.binary),'--lock-file',str(self.directory/'owner.lock'),'--timeout-ms',budget,'--grace-ms','40',
                                             '--',sys.executable,'-c','pass']).returncode,64)
        self.assertEqual(subprocess.run([str(self.binary),'--lock-file',str(self.directory/'owner.lock'),'--timeout-ms','100','--grace-ms','40',
                                         '--','python3','-c','pass']).returncode,64)
    def test_exclusive_lock_blocks_until_old_group_cleanup(self):
        p=self.start();state=self.ready(p)
        second=subprocess.Popen(self.argv(),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        self.owned.append(second)
        self.assertEqual(second.wait(timeout=2),75)
        self.assertEqual(subprocess.run([str(self.binary),'--probe-lock',str(self.directory/'owner.lock')]).returncode,75)
        p.stdin.close();self.assertEqual(p.wait(timeout=2),125);self.absent(state)
        third=subprocess.Popen([str(self.binary),'--lock-file',str(self.directory/'owner.lock'),
            '--timeout-ms','1000','--grace-ms','40','--',sys.executable,'-c','pass'],stdin=subprocess.PIPE)
        self.owned.append(third);self.assertEqual(third.wait(timeout=2),0)
        inode=(self.directory/'owner.lock').stat().st_ino
        self.assertEqual(subprocess.run([str(self.binary),'--probe-lock',str(self.directory/'owner.lock')]).returncode,0)
        self.assertEqual((self.directory/'owner.lock').stat().st_ino,inode)
        # Lock released only after the old guardian's group cleanup + waitpid.
    def test_unsafe_lock_paths_reject_without_following(self):
        target=self.directory/'foreign';target.write_text('unchanged');target.chmod(0o600)
        link=self.directory/'linked-lock';link.symlink_to(target)
        before=target.read_bytes()
        for path in [link,self.directory/'..'/'bad-lock']:
            a=self.argv();a[2]=str(path)
            p=subprocess.Popen(a,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            self.owned.append(p);self.assertEqual(p.wait(timeout=2),125)
        self.assertEqual(target.read_bytes(),before)
    def test_lock_requires_exact_private_mode_and_one_link(self):
        path=self.directory/'unsafe-mode.lock';path.write_text('unchanged')
        for mode in [0o700,0o640,0o1600]:
            os.chmod(path,mode)
            before=path.stat();data=path.read_bytes()
            self.assertEqual(subprocess.run([str(self.binary),'--probe-lock',str(path)]).returncode,125)
            after=path.stat();self.assertEqual((before.st_ino,before.st_mode),(after.st_ino,after.st_mode));self.assertEqual(path.read_bytes(),data)
        os.chmod(path,0o600);other=self.directory/'second-link';os.link(path,other)
        self.assertEqual(subprocess.run([str(self.binary),'--probe-lock',str(path)]).returncode,125)
        other.unlink();path.unlink()
    def test_hard_owner_death_cancels_and_reaps(self):
        ledger=self.directory/'owner-ledger.json'
        owner_code='''import subprocess,sys,json,time
p=subprocess.Popen(json.loads(sys.argv[1]),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
open(sys.argv[2],'w').write(str(p.pid))
while True:time.sleep(1)
'''
        owner=subprocess.Popen([sys.executable,'-c',owner_code,json.dumps(self.argv()),str(ledger)])
        self.owned.append(owner);state=self.ready(owner)
        guard=int(ledger.read_text());owner.kill();owner.wait(timeout=2)
        end=time.monotonic()+2;status=None
        while time.monotonic()<end:
            pid,value=os.waitpid(guard,os.WNOHANG)
            if pid==guard:status=value;break
            time.sleep(.005)
        self.assertIsNotNone(status);self.assertEqual(os.waitstatus_to_exitcode(status),125)
        self.absent(state);self.assertFalse(Path('/proc',str(guard)).exists())

if __name__=='__main__':
    unittest.main()
