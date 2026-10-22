#!/usr/bin/env python3
"""Pure guards only: no compiler, native executable, Docker or sockets."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('tcp_probe',Path(__file__).with_name('network_policy_tcp_probe.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Guards(unittest.TestCase):
 def test_banner_and_fault_contract(self):
  self.assertEqual(len(m.BANNER),15);self.assertEqual(m.BANNER[-1:],b'\n')
  cases={n:(c,o) for n,_,c,o in m.CASES}
  self.assertEqual(cases['extra-suffix-prefix-semantics'],(0,'REACHABLE\n'))
  for name in ['wrong','short','receive-timeout']:self.assertEqual(cases[name],(2,''))
  for name in ['refused','unroutable']:self.assertEqual(cases[name],(0,'DENIED\n'))
 def test_literal_exact(self):
  raw=b'PROBE = '+repr('result = :gen_tcp.recv(socket, byte_size("adhd-policy-v1\\n"), 1000)\n[:timeout, :ehostunreach, :enetunreach, :econnrefused]').encode()
  self.assertIn(':gen_tcp.recv',m.probe_literal(raw))
  with self.assertRaises(AssertionError):m.probe_literal(raw+b'\nPROBE="x"')
  with self.assertRaises(AssertionError):m.probe_literal(raw.replace(b'1000',b'2000'))
 def test_exec_failure_never_denied(self):
  for code in [125,126,127,137,3,2]:
   with self.assertRaises(AssertionError):m.expected_probe({'error':None,'exit_code':code,'stdout':'DENIED\n','stderr':''},0,'DENIED\n')
  with self.assertRaises(AssertionError):m.expected_probe({'error':'Timeout','exit_code':0,'stdout':'DENIED\n','stderr':''},0,'DENIED\n')
  with self.assertRaises(AssertionError):m.expected_probe({'error':None,'exit_code':0,'stdout':'DENIED\n','stderr':'daemon error'},0,'DENIED\n')
 def test_classified_outputs(self):
  m.expected_probe({'error':None,'exit_code':0,'stdout':'DENIED\n','stderr':''},0,'DENIED\n')
  m.expected_probe({'error':None,'exit_code':2,'stdout':'','stderr':''},2,'')
  m.expected_probe({'error':None,'exit_code':3,'stdout':'','stderr':''},3,'')
 def test_inventory_exact_dirs_redirect_hardlink(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'a').write_bytes(b'a');one=m.inventory(root)
   (root/'empty').mkdir();self.assertNotEqual(m.inventory(root),one)
   (root/'redirect').symlink_to(root/'empty',target_is_directory=True)
   with self.assertRaises(AssertionError):m.inventory(root)
   (root/'redirect').unlink();(root/'hard').hardlink_to(root/'a')
   with self.assertRaises(AssertionError):m.inventory(root)
 def test_actual_compile_record_bound(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);elf=r/'elf';proof=r/'proof';elf.write_bytes(b'ELF fixture only, not executed')
   source=b'source';plan=b'compiler plan'
   record={'schema':'adhd/cni-static-helper-compile@1','passed':True,'source_sha256':m.sha(source),'elf_sha256':m.sha(elf.read_bytes()),'plan_sha256':m.sha(plan),'exit_code':0,'complete_input_closure_unchanged':True,'native_executions':0,'container_starts':0,'stdout_sha256':m.sha(b''),'stderr_sha256':m.sha(b''),'elf_bytes':elf.stat().st_size,'elf':{'interpreter':None,'needed':[],'search':[]}}
   proof.write_text(json.dumps(record));self.assertEqual(m.compile_binding(elf,proof,source,plan),elf.read_bytes())
   for key,value in [('passed',False),('source_sha256','0'*64),('plan_sha256','0'*64),('complete_input_closure_unchanged',False),('container_starts',1),('elf',{'interpreter':'/loader','needed':[],'search':[]})]:
    bad=dict(record);bad[key]=value;proof.write_text(json.dumps(bad))
    with self.assertRaises(AssertionError):m.compile_binding(elf,proof,source,plan)
 def test_once_before_any_runner(self):
  with tempfile.TemporaryDirectory() as t:
   w=Path(t);(w/'EXECUTION_STARTED').write_text('previous execution')
   with mock.patch.object(m.sys,'flags',mock.Mock(isolated=1,no_site=1)),mock.patch.object(m.sys,'dont_write_bytecode',True),mock.patch.object(m,'TCPRunner') as runner:
    with self.assertRaises(FileExistsError):m.execute(w,{'execution_ready':True},None)
    runner.assert_not_called()
 def test_cleanup_kill_wait_then_independent_removal(self):
  obj=m.TCPRunner.__new__(m.TCPRunner);obj.r=mock.Mock();item={'id':'a'*64,'name':'own'}
  obj.owned=mock.Mock(side_effect=lambda v,i:v)
  obj.r.inspect.side_effect=[{'Id':item['id'],'State':{'Running':True}}, {'State':{'Running':False,'ExitCode':137}}]
  obj.r.docker.side_effect=[{'exit_code':0},{'exit_code':0,'stdout':'137\n'}]
  obj.cleanup(item)
  self.assertEqual(item['requested_kill_exit_code'],137)
  self.assertEqual(obj.r.docker.call_args_list[0].args[0],['kill','--signal','KILL',item['id']])
  obj.r.cleanup.assert_called_once_with(item)
 def test_cleanup_inspect_failure_still_independent_remove(self):
  obj=m.TCPRunner.__new__(m.TCPRunner);obj.r=mock.Mock();item={'id':'a'*64,'name':'own'}
  obj.r.inspect.side_effect=RuntimeError('daemon unavailable')
  with self.assertRaisesRegex(RuntimeError,'daemon unavailable'):obj.cleanup(item)
  obj.r.cleanup.assert_called_once_with(item)
  obj.r.docker.assert_not_called()
 def test_bad_wait_still_removed_and_failure_preserved(self):
  obj=m.TCPRunner.__new__(m.TCPRunner);obj.r=mock.Mock();item={'id':'a'*64,'name':'own'}
  obj.owned=mock.Mock(side_effect=lambda v,i:v)
  obj.r.inspect.return_value={'State':{'Running':True}}
  obj.r.docker.side_effect=[{'exit_code':0},{'exit_code':0,'stdout':'0\n'}]
  with self.assertRaises(AssertionError):obj.cleanup(item)
  obj.r.cleanup.assert_called_once_with(item)
 def test_exact_create_security_and_exec_failure_cleanup(self):
  obj=m.TCPRunner.__new__(m.TCPRunner);obj.w=Path('/private/fixture');obj.p={'image':m.IMAGE,'nonce':'a'*32};obj.r=mock.Mock();obj.ledger=[]
  obj.r.inspect.side_effect=[None,{}];obj.owned=mock.Mock(side_effect=lambda v,i:v);obj.cleanup=mock.Mock()
  obj.r.docker.side_effect=[{'exit_code':0,'stdout':json.dumps([{'Id':m.IMAGE,'Config':{'Volumes':None}}])}, {'exit_code':0,'stdout':'b'*64}, {'exit_code':0}, {'error':None,'exit_code':125,'stdout':'','stderr':'exec failed'}]
  with self.assertRaises(AssertionError):obj.container('static')
  args=obj.r.docker.call_args_list[1].args[0]
  for part in ['--read-only','--no-healthcheck','no-new-privileges','192m','64','1000:1000']:self.assertIn(part,args)
  self.assertEqual(args[args.index('--network')+1],'none')
  self.assertEqual(args[args.index('--cpus')+1],'1')
  self.assertEqual(args[args.index('--cap-drop')+1],'ALL')
  self.assertNotIn('--privileged',args);self.assertNotIn('--pid',args)
  obj.cleanup.assert_called_once_with(obj.ledger[0])
 def test_source_only_cannot_execute(self):
  with mock.patch.object(m.sys,'flags',mock.Mock(isolated=1,no_site=1)),mock.patch.object(m.sys,'dont_write_bytecode',True),mock.patch.object(m,'TCPRunner') as runner:
   with self.assertRaises(AssertionError):m.execute(Path('/unused'),{'execution_ready':False},None)
   runner.assert_not_called()
 def test_foreign_custody_rejected(self):
  obj=m.TCPRunner.__new__(m.TCPRunner);obj.p={'image':m.IMAGE}
  with self.assertRaises(AssertionError):obj.owned({'Id':'foreign'}, {'id':'owned'})

if __name__=='__main__':unittest.main()
