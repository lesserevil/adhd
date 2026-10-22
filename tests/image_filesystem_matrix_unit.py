#!/usr/bin/env python3
"""Pure admission/custody guards; every process boundary is mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('image_filesystem_matrix.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
 def tearDown(self):self.tmp.cleanup()
 def test_exact_tree_and_empty_directories(self):
  (self.root/'file').write_text('a');expected=m.inventory(self.root)
  (self.root/'extra').mkdir()
  with self.assertRaises(AssertionError):m.check_tree(self.root,expected)
 def test_directory_symlink(self):
  (self.root/'actual').mkdir();(self.root/'redirect').symlink_to(self.root/'actual',target_is_directory=True)
  with self.assertRaises(AssertionError):m.inventory(self.root)
 def test_root_redirect(self):
  target=self.root/'real';target.mkdir();link=self.root/'link';link.symlink_to(target,target_is_directory=True)
  with self.assertRaises(AssertionError):m.inventory(link)
 def test_native_exact_selection(self):
  native=json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/kafka/core38/plan.json').read_text())
  self.assertEqual([r['name'] for r in m.selected_native_jobs(native)],m.NAMES)
  bad=copy.deepcopy(native)
  row=next(r for r in bad['jobs'] if r['name']=='migration-damage-config');row['arguments'][row['arguments'].index('--crash-at')+1]='before-config'
  with self.assertRaises(AssertionError):m.selected_native_jobs(bad)
 def test_authoritative_absence_only(self):
  id='a'*64
  good=subprocess.CompletedProcess([],1,b'[]',('error: no such object: '+id).encode())
  self.assertTrue(m.absent(good,id))
  for rc,err in [(2,good.stderr),(1,b'daemon unavailable'),(1,good.stderr+b'\nconnection failed')]:
   self.assertFalse(m.absent(subprocess.CompletedProcess([],rc,b'',err),id))
 def fixture(self):
  (self.root/'runtime').mkdir()
  plan={'driver_sha256':'test','lane_lock':str(self.root/'lock'),'runtime_cwd':str(self.root/'runtime'),
   'tools':{k:{'path':'/test/'+k} for k in ('python','elixir','erl','docker')},'docker_socket':{'path':'/test/socket'},
   'jobs':[{'name':n,'argv':['never-run']} for n in m.NAMES],'scope':'pure','image_config_identity':m.IMAGE,'artifact_sha256':m.ARTIFACT}
  m.save(self.root/'plan.json',plan);return m.sha(self.root/'plan.json')
 def test_once_before_actual_boundary_and_no_retry(self):
  digest=self.fixture()
  with patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=OSError('mock launch')) as run:
   with self.assertRaises(OSError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
   with self.assertRaises(FileExistsError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'matrix.json').read_text())
  self.assertFalse(result['passed']);self.assertEqual(result['attempted'],['storage-crash']);self.assertEqual(result['executed'],[]);self.assertEqual(result['unrun'],m.NAMES)
 def test_returned_exit_retained_before_bad_report(self):
  digest=self.fixture()
  def fake(*args,**kwargs):
   (self.root/'storage-crash.json').write_text('{"passed":true}')
   return subprocess.CompletedProcess([],0)
  with patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=fake) as run:
   with self.assertRaises(KeyError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'matrix.json').read_text());self.assertEqual(result['executed'],['storage-crash']);self.assertEqual(result['results'][0]['process_exit_code'],0);self.assertFalse(result['passed'])
 def test_unknown_cleanup_not_qualified(self):
  runtime={'kind':'docker','image_config_identity':m.IMAGE,'artifact_sha256':m.ARTIFACT,'canonical_manifest_sha256':'m',
   'cleanup_blocked':True,'container_lifecycle':[]}
  value={'passed':True,'artifact_sha256':m.ARTIFACT,'checks':[{'passed':True}],'runtime':runtime}
  with self.assertRaises(AssertionError):m.qualify(value,{'script':'multi_migration.py','expected_check_count':1},{'canonical_manifest_sha256':'m'})

if __name__=='__main__':unittest.main()
