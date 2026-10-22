#!/usr/bin/env python3
"""Pure driver custody checks; every process boundary is mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('m',Path(__file__).with_name('image_stale_owner_matrix.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
TARGET={'image_config_identity':'sha256:'+'a'*64,'artifact_sha256':'b'*64,'admission_sha256':'c'*64}
class Guards(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
 def tearDown(self):self.tmp.cleanup()
 def test_tree_set(self):
  (self.root/'file').write_text('a');expected=m.inventory(self.root);(self.root/'extra').mkdir()
  with self.assertRaises(AssertionError):m.check_tree(self.root,expected)
 def test_redirect(self):
  (self.root/'real').mkdir();(self.root/'link').symlink_to(self.root/'real',target_is_directory=True)
  with self.assertRaises(AssertionError):m.inventory(self.root)
  with self.assertRaises(AssertionError):m.inventory(self.root/'link')
 def test_targets_explicit(self):
  self.assertEqual(m.target_bindings(TARGET),tuple(TARGET.values()))
  with self.assertRaises(KeyError):m.target_bindings({})
  with self.assertRaises(AssertionError):m.target_bindings({**TARGET,'image_config_identity':'tag'})
 def test_authoritative_absence(self):
  self.assertTrue(m.absent(subprocess.CompletedProcess([],1,b'[]',b'error: no such object: Mixed'),'Mixed'))
  for rc,out,err in [(1,b'[{}]',b'error: no such object: Mixed'),(1,b'[]',b'error: no such object: mixed'),(2,b'',b'error: no such object: Mixed'),(1,b'',b'daemon failed')]:self.assertFalse(m.absent(subprocess.CompletedProcess([],rc,out,err),'Mixed'))
 def fixture(self):
  (self.root/'runtime').mkdir();plan={**TARGET,'driver_sha256':'test','lane_lock':str(self.root/'lock'),'runtime_cwd':str(self.root/'runtime'),'tools':{k:{'path':'/test/'+k} for k in ('python','elixir','erl','docker')},'docker_socket':{'path':'/test/socket'},'jobs':[{'name':'stale-owner','argv':['never-run']}],'scope':'pure'}
  m.save(self.root/'plan.json',plan);return m.sha(self.root/'plan.json')
 def test_once_before_boundary(self):
  digest=self.fixture()
  with patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=OSError('mock')) as run:
   with self.assertRaises(OSError):m.execute(self.root,digest)
   with self.assertRaises(FileExistsError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  value=json.loads((self.root/'matrix.json').read_text());self.assertFalse(value['passed']);self.assertEqual(value['unrun'],['stale-owner'])
 def test_returned_exit_before_bad_report(self):
  digest=self.fixture()
  def fake(*args,**kwargs):(self.root/'stale-owner.json').write_text('{}');return subprocess.CompletedProcess([],0)
  with patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=fake):
   with self.assertRaises(KeyError):m.execute(self.root,digest)
  value=json.loads((self.root/'matrix.json').read_text());self.assertEqual(value['results'][0]['process_exit_code'],0);self.assertFalse(value['passed'])
 def valid(self):
  ids=[str(i)*64 for i in range(1,5)]
  events=[{'action':'started','container_id':i} for i in ids]+[{'action':'stopped','container_id':i,'observed_absent':True,'wait_observed':True} for i in ids]
  return {'schema':'adhd/federation-v2-stale-canonical-owner@1','passed':True,'artifact_sha256':TARGET['artifact_sha256'],'harness_sha256':'h','checks':[{'passed':True} for _ in range(4)],'runtime':{'kind':'docker',**TARGET,'canonical_manifest_sha256':'m','container_lifecycle':events}}
 def test_four_actual_hubs_and_harness_bound(self):
  value=self.valid();self.assertEqual(len(m.qualify(value,{},dict(TARGET,canonical_manifest_sha256='m',unchanged_harness_sha256='h'))[0]),4)
  for edit in (lambda v:v.update(checks=v['checks'][:3]),lambda v:v.update(harness_sha256='other'),lambda v:v['runtime']['container_lifecycle'][-1].update(observed_absent=False),lambda v:v['runtime'].update(image_config_identity='sha256:'+'d'*64)):
   bad=copy.deepcopy(value);edit(bad)
   with self.assertRaises(AssertionError):m.qualify(bad,{},dict(TARGET,canonical_manifest_sha256='m',unchanged_harness_sha256='h'))
 def test_original_timeout_and_controlled_fixture_not_modified(self):
  source=Path('/home/horde/src/adhd/tests/federation_stale_owner.py').read_text()
  for literal in ('deadline_ms=3000','expiry_observed=True','catalog_ttl_ms=10000','model, hubs, observers = Model(), [], []'):self.assertIn(literal,source)
  self.assertEqual(m.NAMES,['stale-owner'])
if __name__=='__main__':unittest.main()
