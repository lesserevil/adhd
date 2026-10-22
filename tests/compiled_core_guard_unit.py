"""Outer core13 admission guards only; all child process boundaries mocked."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
spec=importlib.util.spec_from_file_location('guard',Path(__file__).with_name('compiled_core_guard.py'));g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class Guards(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
 def test_added_symlink_directory_denied(self):
  (self.root/'real').mkdir();(self.root/'redirect').symlink_to(self.root/'real',target_is_directory=True)
  with self.assertRaises(AssertionError):g.inventory(self.root)
 def test_added_empty_directory_changes_closure(self):
  before=g.inventory(self.root);(self.root/'extra').mkdir();self.assertNotEqual(g.inventory(self.root),before)
 def test_executable_pycache_denied(self):
  (self.root/'__pycache__').mkdir()
  with self.assertRaises(AssertionError):g.inventory(self.root)
 def test_fsynced_once_exclusive(self):
  g.write(self.root/'once',b'first')
  with self.assertRaises(FileExistsError):g.write(self.root/'once',b'second')
  self.assertEqual((self.root/'once').read_bytes(),b'first')
 def execute_fixture(self):
  p={'driver_sha256':'d','core_work':str(self.root),'argv':['never'],'bound_inputs':{},'tool_trees':[{}, {'root':'/elixir'},{'root':'/erl'}],'tools':{'python':{'path':'/python'}}}
  (self.root/'plan.json').write_text(json.dumps(p));return g.sha(self.root/'plan.json')
 def test_duplicate_admission_zero_second_child(self):
  digest=self.execute_fixture();args=MagicMock(work=self.root,plan_sha256=digest);child=MagicMock(pid=123);child.wait.return_value=0;child.poll.return_value=0
  (self.root/'matrix.json').write_text('{"passed":true}')
  with patch.object(g,'__file__',str(self.root/'guard.py')),patch.object(g.sys,'flags',MagicMock(isolated=1)),patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen',return_value=child) as process:
   g.execute(args)
   with self.assertRaises(FileExistsError):g.execute(args)
   self.assertEqual(process.call_count,1)
 def test_failed_child_does_not_pass(self):
  digest=self.execute_fixture();args=MagicMock(work=self.root,plan_sha256=digest);child=MagicMock(pid=123);child.wait.return_value=1;child.poll.return_value=1
  (self.root/'matrix.json').write_text('{"passed":true}')
  with patch.object(g,'__file__',str(self.root/'guard.py')),patch.object(g.sys,'flags',MagicMock(isolated=1)),patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen',return_value=child):
   with self.assertRaises(AssertionError):g.execute(args)
  self.assertFalse(json.loads((self.root/'result.json').read_text())['passed'])
if __name__=='__main__':unittest.main()
