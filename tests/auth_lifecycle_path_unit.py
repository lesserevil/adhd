"""Pure auth setup invocation checks; no configure/app/Provider starts."""
import ast
from collections import Counter
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock

SOURCE=Path(__file__).with_name('auth_lifecycle.py').resolve()

class AuthPath(unittest.TestCase):
 def configure_call(self):
  tree=ast.parse(SOURCE.read_text())
  return next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='run')
 def test_auth_setup_uses_script_beside_frozen_tests_from_unrelated_cwd(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);template=root/'seed';state=root/'runtime/state.dets';port=54321;run=Mock()
   previous=Path.cwd()
   try:
    os.chdir(root)
    eval(compile(ast.Expression(self.configure_call()),str(SOURCE),'eval'),{'Path':Path,'__file__':str(SOURCE),'subprocess':types.SimpleNamespace(run=run,DEVNULL=subprocess.DEVNULL),'template':template,'port':port,'r':types.SimpleNamespace(root=state.parent)})
   finally:os.chdir(previous)
   expected=SOURCE.parents[1]/'scripts/configure_hub.py'
   run.assert_called_once_with(['python3',str(expected),'--directory',str(template),'--port',str(port),'--store-path',str(state)],check=True,stdout=subprocess.DEVNULL)
   self.assertTrue(expected.is_absolute());self.assertTrue(expected.is_file())
 def test_only_configure_script_argument_changes_and_assertions_conserved(self):
  # Exact authored baseline is the frozen root copy prior to this one-line fix.
  current=SOURCE.read_text();original=current.replace("str(Path(__file__).resolve().parents[1]/'scripts/configure_hub.py')","'scripts/configure_hub.py'")
  self.assertNotEqual(original,current)
  self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),'f4ca59ebbe89cff09d33c79d190673d6bedbf03b8dbcaee79ba5af542bf0afba')
  before=Counter(ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(original)) if isinstance(n,ast.Assert))
  after=Counter(ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(current)) if isinstance(n,ast.Assert))
  self.assertEqual(before,after)
  call=self.configure_call();self.assertEqual(ast.literal_eval(call.args[0].elts[0]),'python3')

if __name__=='__main__':unittest.main()
