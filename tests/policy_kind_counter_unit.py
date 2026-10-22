"""Pure preparation guards only. No compiler/native behavior or process proof."""
import ast
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import policy_kind_counter_prepare as prep
import kafka_network_policy_cri as cri

class Preparation(unittest.TestCase):
    def test_original_argv_literal_and_raw_ENV(self):
        root = Path(__file__).parent
        original = prep.serve((root/'kafka_network_policy.py').read_text())
        source = (root/'policy_kind_counter.c').read_text()
        import re
        literal = re.search(r'static const char original_serve\[\] = (.*);\n', source)
        self.assertEqual(json.loads(literal.group(1)), original)
        values = prep.gate_argv('a'*32, original)
        self.assertEqual(values[3:], ['/usr/local/bin/elixir', 'elixir', '-e', original])
        env = ['HOME=/tmp', 'ERL_FLAGS=+S 2:2', 'ERL_FLAGS=+S 1:1']
        self.assertEqual(prep.environment_hash(env), hashlib.sha256(b'HOME=/tmp\0ERL_FLAGS=+S 2:2\0ERL_FLAGS=+S 1:1\0').hexdigest())
        self.assertNotEqual(prep.environment_hash(env), prep.environment_hash(env[::-1]))
        for bad in (['ERL_FLAGS=+S 8:8'], ['X=1'], ['ERL_FLAGS=+S 1:1\0X=1']):
            with self.assertRaises(AssertionError): prep.environment_hash(bad)
        self.assertIn('execve(argv[3],argv+4,environ)', source)
        for forbidden in ('setenv(', 'putenv(', 'system(', 'popen(', 'execvp(', 'SIGKILL', 'SIGTERM'):
            self.assertNotIn(forbidden, source)
        self.assertEqual(source.count('SYS_pidfd_send_signal'), 1)
        self.assertIn('SYS_pidfd_send_signal,pfd,SIGCONT,NULL,0', source)
        self.assertIn('kill(getpid(),SIGSTOP)', source)

    def test_deadline_includes_hold_and_never_extends(self):
        self.assertTrue(prep.release_allowed(0, 30_000_000_000))
        self.assertTrue(prep.release_allowed(10_000_000_000, 30_000_000_000))
        self.assertFalse(prep.release_allowed(10_000_000_001, 30_000_000_000))
        self.assertFalse(prep.release_allowed(0, 30_000_000_001))
        self.assertFalse(prep.release_allowed(31_000_000_000, 30_000_000_000))
        source = Path(prep.__file__).with_name('policy_kind_counter.c').read_text()
        self.assertIn('now_ns()+20*NS<=x.deadline', source)
        self.assertIn('while(now_ns()<x.deadline&&seq<MAX_SAMPLES)', source)
        self.assertIn('different-monotonic-view', source)

    def test_closed_exact_Pod_and_CID_paths(self):
        uid = '88e9a64a-e762-401c-8ac7-a7f008d67c72'; cid = '8'*64
        pod = 'kubelet-kubepods-burstable-pod'+uid.replace('-', '_')+'.slice'
        meta = pod+':cri-containerd:'+cid
        paths = cri.paths(meta, uid, cid)
        self.assertEqual(paths[1], paths[0]+'/cri-containerd-'+cid+'.scope')
        self.assertTrue(paths[0].startswith('/sys/fs/cgroup/kubelet.slice/kubelet-kubepods.slice/'))
        for bad in (meta.replace('kubelet-', 'foreign-', 1), meta+'../', meta.replace(cid, '9'*64), '/other/'+meta):
            self.assertIsNone(cri.paths(bad, uid, cid))
        source = Path(prep.__file__).with_name('policy_kind_counter.c').read_text()
        self.assertIn('live-cgroup-view-mismatch', source)
        self.assertIn('unsupported-cgroup-mount-view', source)
        self.assertIn('O_NOFOLLOW', source)
        self.assertIn('fstatfs(fd,&fs)', source)
        self.assertIn('not-private-PID1', source)
        self.assertIn('observer-inside-Pod-budget', source)
        self.assertIn('memory-max-not-original192Mi', source)

    def test_mount_join_uses_verified_namespace_path(self):
        uid = '88e9a64a-e762-401c-8ac7-a7f008d67c72'; cid = '8'*64
        meta = 'kubelet-kubepods-burstable-pod'+uid.replace('-', '_')+'.slice:cri-containerd:'+cid
        for value in cri.paths(meta, uid, cid):
            relative = value.removeprefix('/sys/fs/cgroup')
            self.assertEqual(prep.counter_directory(relative), value)
        self.assertEqual(prep.counter_directory('/kubepods/burstable/pod'+uid+'/'+cid),
                         '/sys/fs/cgroup/kubepods/burstable/pod'+uid+'/'+cid)
        for bad in ('/sys/fs/cgroup/kubelet.slice/x', '/kubelet.slice/../x', '/foreign/x', '/kubelet.slice//x'):
            with self.assertRaises(AssertionError): prep.counter_directory(bad)
        source = Path(prep.__file__).with_name('policy_kind_counter.c').read_text()
        self.assertIn('"/sys/fs/cgroup%s",paths[j]', source)
        self.assertIn('directory(absolute)', source)
        self.assertNotIn('directory(paths[j])', source)

    def test_identity_and_counter_errors_not_zero(self):
        source = Path(prep.__file__).with_name('policy_kind_counter.c').read_text()
        for required in ('preinspected-identity', 'identity-before-CONT', 'gate-exe-hash',
                         'argv-hash', 'ordered-environment-hash', 'gate-not-stopped',
                         'ENODATA', 'ENODEV', 'errno', 'available\\\":false'):
            # ENODEV is emitted numerically by errno, not a synthetic zero.
            if required == 'ENODEV':
                self.assertIn('if(n<0)err=errno', source)
            else: self.assertIn(required, source)
        self.assertLess(source.index('open_counters(&second)'), source.index('SYS_pidfd_send_signal'))
        self.assertLess(source.index('sample(seq++, pf)'), source.index('if(pf[0].revents'))
        self.assertIn('for(unsigned j=0;j<2;j++)', source)
        self.assertIn('"not-inferred', source.replace('\\"', '"'))

    def test_no_process_capability_in_preparer(self):
        tree = ast.parse(Path(prep.__file__).read_text())
        modules = [n.names[0].name for n in tree.body if isinstance(n, ast.Import)]
        self.assertNotIn('subprocess', modules)
        self.assertNotIn('ctypes', modules)
        text = Path(prep.__file__).read_text()
        self.assertNotIn('os.system(', text)
        self.assertNotIn('os.exec', text)
        self.assertIn("group.add_argument('--prepare')", text)
        self.assertIn("group.add_argument('--verify')", text)
        self.assertNotIn("group.add_argument('--execute')", text)

    def test_descriptor_input_rejects_redirects_special_and_cap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = root/'input'; p.write_bytes(b'original')
            self.assertEqual(prep.read(p), b'original')
            with self.assertRaises(AssertionError): prep.read(p, 3)
            link = root/'alias'; link.symlink_to(p)
            with self.assertRaises(AssertionError): prep.read(link)
            fifo = root/'fifo'; os.mkfifo(fifo)
            with self.assertRaises(AssertionError): prep.read(fifo)
            redirected = root/'redirect'; redirected.symlink_to(root, target_is_directory=True)
            with self.assertRaises(AssertionError): prep.read(redirected/'input')

    def test_tree_full_empty_directory_file_link_set(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'f').write_bytes(b'one'); before = prep.tree(root)
            (root/'empty').mkdir(); self.assertNotEqual(prep.tree(root), before)
            (root/'empty').rmdir(); (root/'f').write_bytes(b'two'); self.assertNotEqual(prep.tree(root), before)
            (root/'f').write_bytes(b'one'); (root/'link').symlink_to('f')
            self.assertIn('link', prep.tree(root)['links'])
            with tempfile.TemporaryDirectory() as other:
                (root/'bad-dir').symlink_to(other, target_is_directory=True)
                with self.assertRaises(AssertionError): prep.tree(root)

    def test_ELF_reader_bounds_machine_path_and_RPATH(self):
        def fixture(machine=62, name=b'libc.so.6\0', tag=1):
            b = bytearray(1024); b[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<H', b, 18, machine); struct.pack_into('<Q', b, 32, 64)
            struct.pack_into('<HH', b, 54, 56, 2)
            struct.pack_into('<IIQQQQQQ', b, 64, 1, 0, 0, 0, 0, 1024, 1024, 0)
            struct.pack_into('<IIQQQQQQ', b, 120, 2, 0, 256, 256, 0, 64, 64, 0)
            for i, value in enumerate(((tag, 0), (5, 512), (10, len(name)), (0, 0))):
                struct.pack_into('<qQ', b, 256+16*i, *value)
            b[512:512+len(name)] = name
            return bytes(b)
        self.assertEqual(prep.elf_dependencies(fixture()), ([], ['libc.so.6']))
        for raw in (fixture(machine=3), fixture(name=b'../libc.so.6\0'), fixture(tag=29), fixture()[:300]):
            with self.assertRaises(AssertionError): prep.elf_dependencies(raw)

    def test_future_plan_no_implicit_execution(self):
        # Keep the native syntax/ABI/hash algorithms explicitly unproven here.
        with patch.object(prep, 'tool_closure', return_value={}), patch.object(prep, 'tree', side_effect=lambda p: {'root':p,'files':{},'directories':[],'links':{}}), patch.object(prep, 'file_binding', side_effect=lambda p: {'path':str(p)}):
            with tempfile.TemporaryDirectory() as d:
                info = prep.prepare(Path(d)/'plan')
                value = json.loads(Path(info['plan']).read_bytes())
                self.assertFalse(value['compiled']); self.assertFalse(value['executed'])
                self.assertTrue(value['root_compile_and_execution_GO_required'])
                self.assertEqual(value['bounds']['Ready_seconds_including_hold'], 30)
                self.assertEqual(value['bounds']['release_within_seconds'], 10)
                self.assertEqual(value['future_compile_environment']['PATH'], '/usr/bin:/bin')
                self.assertIn('-static', value['future_compile_argv'])
                self.assertTrue(any('NOT been compiled' in x for x in value['not_yet_proven']))

if __name__ == '__main__': unittest.main()
