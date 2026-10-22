"""Pure guards: no native runtime, compiler, provider or container may start."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import native_core_remaining as m

class NativeRemainingGuards(unittest.TestCase):
 def test_wire_original_self_lock_never_gets_coordinator_flock(self):
  wire=['python','wire.py','--port-lock','/owned/lock'];foundation=['python','foundation.py']
  self.assertIs(m.coordinator_argv('wire',wire,'/owned/lock'),wire)
  self.assertEqual(m.coordinator_argv('foundation',foundation,'/owned/lock'),['/usr/bin/flock','/owned/lock',*foundation])
  self.assertEqual(wire,['python','wire.py','--port-lock','/owned/lock'])
 def test_changed_actual_driver_refuses_before_external_reads(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);driver=root/'run.py';shutil.copyfile(m.__file__,driver);digest=m.sha(driver)
   driver.write_text(driver.read_text()+'\n#changed\n');module=m.load(driver,'native_changed_driver')
   with self.assertRaises(AssertionError):module.verify({'driver_sha256':digest},root)
 def test_once_refusal_before_compiler_or_runtime_creation(self):
  from controlled_image_matrix import durable_once_marker
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);plan={'runtime':str(root/'runtime'),'driver_sha256':'a'*64};m.write(root/'plan.json',plan);digest=m.sha(root/'plan.json');durable_once_marker(root/'started.json',{'plan_sha256':digest})
   with patch.object(m,'verify',return_value=True),patch.object(m,'load',return_value=SimpleNamespace(durable_once_marker=durable_once_marker)):
    with self.assertRaises(FileExistsError):m.execute(root,digest)
   self.assertFalse((root/'runtime').exists())
 def test_ledger_preserves_actual_popen_arguments_and_object(self):
  with tempfile.TemporaryDirectory()as tmp:
   process=SimpleNamespace(pid=123,returncode=0,poll=lambda:0);identity={'pid':123,'starttime':'7','state':'R'}
   with patch.object(m.subprocess,'Popen',return_value=process)as original,patch.object(m,'identity',return_value=identity),patch.object(m,'same',return_value=False):
    ledger=m.ChildLedger(Path(tmp)/'ledger.json');ledger.install()
    try:
     value=m.subprocess.Popen(['unchanged','arguments'],start_new_session=True)
     self.assertIs(value,process);original.assert_called_once_with(['unchanged','arguments'],start_new_session=True)
    finally:orphans=ledger.close()
    self.assertEqual(orphans,[]);self.assertIs(m.subprocess.Popen,original)
    self.assertTrue(json.loads(ledger.path.read_text())['processes'][0]['same_process_absent'])
 def test_identity_reuse_is_not_owned_process(self):
  with patch.object(m,'identity',return_value={'pid':123,'starttime':'8','state':'R'}):self.assertFalse(m.same({'pid':123,'starttime':'7'}))
 def test_exact_nonce_scan_excludes_foreign_and_prefix_matches(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp)
   for pid,body in [('1',b'ADHD_NATIVE_CORE_RUN_NONCE=exact\0'),('2',b'ADHD_NATIVE_CORE_RUN_NONCE=exact-foreign\0'),('3',b'OTHER=exact\0')]:
    p=root/pid;p.mkdir();(p/'environ').write_bytes(body)
   with patch.object(m,'identity',side_effect=lambda pid:{'pid':pid,'starttime':'7','state':'R'}):rows=m.owned_nonce_processes('exact',root)
   self.assertEqual([r['pid']for r in rows],[1])
 def cwd_fixture(self,root):
  frozen=root/'frozen';(frozen/'docs/protocol').mkdir(parents=True);(frozen/'scripts').mkdir()
  (frozen/'docs/protocol/examples.json').write_text('{"fixture":true}')
  (frozen/'scripts/configure_hub.py').write_text('# original helper\n')
  return frozen,m.runtime_fixture(frozen)
 def test_cwd_materializes_exact_plain_copies(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp).resolve();frozen,contract=self.cwd_fixture(root);runtime=root/'runtime';runtime.mkdir()
   self.assertTrue(m.materialize_runtime_fixture(runtime,frozen,contract))
   self.assertFalse((runtime/'docs/protocol/examples.json').is_symlink())
   self.assertEqual((runtime/'scripts/configure_hub.py').read_bytes(),(frozen/'scripts/configure_hub.py').read_bytes())
   (runtime/'tmp').mkdir();self.assertTrue(m.verify_runtime_fixture(runtime,contract))
 def test_cwd_missing_extra_tampered_and_redirect_fail(self):
  for mode in ['missing','extra','directory','tamper','redirect']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as tmp:
    root=Path(tmp).resolve();frozen,contract=self.cwd_fixture(root);runtime=root/'runtime';runtime.mkdir();m.materialize_runtime_fixture(runtime,frozen,contract)
    target=runtime/'docs/protocol/examples.json'
    if mode=='missing':target.unlink()
    elif mode=='extra':(runtime/'scripts/extra.py').write_text('unexpected')
    elif mode=='directory':(runtime/'docs/protocol/extra').mkdir()
    elif mode=='tamper':target.write_text('changed')
    else:target.unlink();target.symlink_to(frozen/'docs/protocol/examples.json')
    with self.assertRaises(AssertionError):m.verify_runtime_fixture(runtime,contract)
 def test_cwd_redirected_runtime_root_fails(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp).resolve();frozen,contract=self.cwd_fixture(root);actual=root/'actual';actual.mkdir();alias=root/'runtime';alias.symlink_to(actual,target_is_directory=True)
   with self.assertRaises(AssertionError):m.materialize_runtime_fixture(alias,frozen,contract)
 def test_cwd_missing_required_fixture_fails_at_prepare(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp).resolve();frozen,contract=self.cwd_fixture(root);(frozen/'docs/protocol/examples.json').unlink()
   with self.assertRaises(AssertionError):m.runtime_fixture(frozen)
 def test_tree_rejects_undeclared_redirect(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'target').write_text('x');(root/'redirect').symlink_to(root/'target')
   with self.assertRaises(AssertionError):m.owned_tree(root)

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No actual subprocess allowed')):unittest.main()
