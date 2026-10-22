"""Pure fresh-suite selection guards; no browser/application/CLI execution."""
import copy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).with_name('image_ui_matrix.py')
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load(SOURCE,'ui_selection')

class Selection(unittest.TestCase):
 def test_default_remains_original_nine_86(self):
  self.assertEqual(m.fresh_suites(),list(m.CASES));self.assertEqual(sum(m.CASES.values()),86)
 def test_focused_canonical_order_complete_32(self):
  names=m.fresh_suites(['recovery','admin','eventing'])
  self.assertEqual(names,['admin','eventing','recovery']);self.assertEqual(sum(m.CASES[n] for n in names),32)
 def test_unknown_duplicate_empty_or_wrong_type_rejected(self):
  for value in ([],['admin','admin'],['unknown'],['admin',None],'admin'):
   with self.subTest(value=value),self.assertRaises(AssertionError):m.fresh_suites(value)
 def test_selection_only_fresh_prepare(self):
  for prepare,remainder in [(False,False),(False,True),(True,True)]:
   with self.assertRaises(AssertionError):m.selection_mode(SimpleNamespace(suites=['admin'],prepare=prepare,prepare_remainder=remainder))
  self.assertEqual(m.selection_mode(SimpleNamespace(suites=['admin'],prepare=True,prepare_remainder=False)),['admin'])
 def test_remainder_refuses_before_reading_inputs(self):
  with self.assertRaises(AssertionError):m.prepare_remainder(SimpleNamespace(suites=['admin']))
  with self.assertRaises(AssertionError):m.selected_plan_suites({'fresh_suite_selection':['admin'],'resume_basis':{'original':True}})
 def test_old_plan_without_selection_is_full_default(self):
  self.assertEqual(m.selected_plan_suites({}),list(m.CASES))
 def fixture(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);w=Path(tmp.name).resolve();shutil.copyfile(SOURCE,w/'run.py');(w/'frozen').mkdir()
  driver=load(w/'run.py','frozen_ui_pure');names=['admin','eventing','recovery'];path='/usr/bin:/bin'
  p={'driver_sha256':driver.sha(w/'run.py'),'frozen_tree':driver.tree(w/'frozen'),'frozen_inputs':{},'externals':{},'tool_roots':{},'bound_inputs':{},'fresh_suite_selection':names,'planned_suites':names,'jobs':[{'name':n,'expected_units':driver.CASES[n]} for n in names],'docker':{'path':'/usr/bin/docker','sha256':driver.sha('/usr/bin/docker')},'qualified_path':path,'env':{'PATH':path},'parallelism':1,'automatic_retries':0,'expected_units':32}
  return driver,w,p
 def test_actual_plan_verifier_accepts_exact_selection(self):
  driver,w,p=self.fixture();self.assertTrue(driver.verify(p,w))
 def test_actual_plan_verifier_rejects_invented_job_count_order_or_set(self):
  driver,w,p=self.fixture()
  variants=[]
  q=copy.deepcopy(p);q['jobs'][0]['expected_units']=17;variants.append(q)
  q=copy.deepcopy(p);q['jobs'].reverse();variants.append(q)
  q=copy.deepcopy(p);q['planned_suites']=['admin'];variants.append(q)
  q=copy.deepcopy(p);q['expected_units']=86;variants.append(q)
  q=copy.deepcopy(p);q.pop('fresh_suite_selection');variants.append(q)
  q=copy.deepcopy(p);q['fresh_suite_selection']=['admin','eventing','recovery','admin'];variants.append(q)
  q=copy.deepcopy(p);q['resume_basis']={'invalid':True};variants.append(q)
  for q in variants:
   with self.assertRaises(AssertionError):driver.verify(q,w)
 def test_actual_plan_verifier_preserves_legacy_remainder_path(self):
  driver,w,p=self.fixture();p.pop('fresh_suite_selection');names=['openrig','accounts-oidc','session-fence'];p.update(planned_suites=names,jobs=[{'name':n,'expected_units':driver.CASES[n]} for n in names],expected_units=15,image_config_identity='same',artifact_sha256='same')
  for name,value in [('parent-plan.json',{'image_config_identity':'same','artifact_sha256':'same'}),('parent-matrix.json',{})]:(w/name).write_text(json.dumps(value))
  p['resume_basis']={'parent_plan_sha256':driver.sha(w/'parent-plan.json'),'parent_matrix_sha256':driver.sha(w/'parent-matrix.json')}
  with patch.object(driver,'resume_prefix',return_value=names) as resume:self.assertTrue(driver.verify(p,w));resume.assert_called_once()
 def test_original_selected_entrypoints_and_bounds_are_conserved(self):
  after=SOURCE.read_text();start="  old=row['argv'];entry=";end=" assert [v['name'] for v in jobs]"
  self.assertEqual(hashlib.sha256(after[after.index(start):after.index(end)].encode()).hexdigest(),'c406dfd7caf3bd35e24e37e4cdfae24e1a67810bb8a9d1404f0c775415f9c887')
  original_digests={'unit_count': 'db2b1e9ec3c2e11d17914283137ca61606314dc4973690c15b1aa8ef9ee258a8', 'captures': '63801f5a2bcb37163e2d6b7cc07b5a2500457bf63044ae535a3645f8dab60247', 'cleanup_ledger': '694a6b63081f3206d0bea256b698ce74ffbb842dbf924175c8e9f9d069a30dc4', 'execute': '2eddda4e2e42e3fb674be5fb670cfd30b5a45e8f23842958387a26a6878760e1'}
  tree=ast.parse(after)
  for name,digest in original_digests.items():
   body=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
   self.assertEqual(hashlib.sha256(ast.dump(body,include_attributes=False).encode()).hexdigest(),digest)

if __name__=='__main__':unittest.main()
