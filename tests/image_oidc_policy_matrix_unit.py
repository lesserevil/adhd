#!/usr/bin/env python3
"""Pure driver custody checks; every process boundary is mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import sys
sys.path.insert(0,"/home/horde/src/adhd/tests")
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('m',Path(__file__).with_name('image_oidc_policy_matrix.py'))
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
  (self.root/'runtime').mkdir();plan={**TARGET,'driver_sha256':'test','lane_lock':str(self.root/'lock'),'runtime_cwd':str(self.root/'runtime'),'tools':{k:{'path':'/test/'+k} for k in ('python','elixir','erl','docker')},'docker_socket':{'path':'/test/socket'},'jobs':[{'name':'oidc-policy','argv':['never-run']}],'scope':'pure','custody_report':str(self.root/'custody.json')}
  m.save(self.root/'plan.json',plan);return m.sha(self.root/'plan.json')
 def test_once_before_boundary(self):
  digest=self.fixture()
  with patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=OSError('mock')) as run:
   with self.assertRaises(OSError):m.execute(self.root,digest)
   with self.assertRaises(FileExistsError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  value=json.loads((self.root/'matrix.json').read_text());self.assertFalse(value['passed']);self.assertEqual(value['unrun'],['oidc-policy'])
 def test_returned_exit_before_bad_report(self):
  digest=self.fixture()
  def fake(*args,**kwargs):(self.root/'oidc-policy.json').write_text('{}');return subprocess.CompletedProcess([],0)
  with patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=fake):
   with self.assertRaises(KeyError):m.execute(self.root,digest)
  value=json.loads((self.root/'matrix.json').read_text());self.assertEqual(value['results'][0]['process_exit_code'],0);self.assertFalse(value['passed'])
 def test_original_sixteen_assertions(self):
  import ast
  source=Path('/home/horde/src/adhd/tests/oidc_policy.py').read_text()
  self.assertEqual(sum(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(source))),16)
  self.assertIn('finally:provider.close()',source)
  self.assertEqual(m.NAMES,['oidc-policy'])
 def test_closed_scripts_tree(self):
  scripts=self.root/'scripts';scripts.mkdir();(scripts/'seed.py').write_text('pass')
  expected=m.inventory(scripts);(scripts/'redirect').symlink_to(self.root,target_is_directory=True)
  with self.assertRaises(AssertionError):m.check_tree(scripts,expected)
 def test_vm_identity_stability_without_process(self):
  import oidc_policy_image as runner
  image=object.__new__(runner.ObservedImage);image.image_id='sha256:'+'a'*64;image.container_id='id';image.vm_observations=[];image.vm_by_container={}
  row={'Id':'id','Image':image.image_id,'HostConfig':{'ReadonlyRootfs':True,'NetworkMode':'host','Memory':768*1024*1024,'NanoCpus':2000000000,'PidsLimit':256}}
  image.docker=lambda *args,**kwargs:subprocess.CompletedProcess([],0,json.dumps([row]).encode())
  with patch.object(runner.RetainedImage,'observe',return_value=None),patch.object(runner,'vm_identity',side_effect=[{'kernel_start_time':'1'},{'kernel_start_time':'1'},{'kernel_start_time':'2'}]):
   image.observe();image.observe()
   with self.assertRaises(AssertionError):image.observe()
  self.assertEqual(len(image.vm_observations),2)
 def test_passive_failure_report_never_probes(self):
  import oidc_policy_image as runner
  class Image:
   manifest_bytes=b'{}';manifest={'files':{'hub.exs':'hash'}};verified=False;events=[];vm_observations=[]
   def identity(self):raise AssertionError('must not call active identity')
   def verify(self):raise AssertionError('must not start probe')
  value=runner.passive_identity(Image());self.assertFalse(value['payload_verified']);self.assertEqual(value['payload_probe_lifecycle'],[])
 def test_qualified_five_cases_two_real_vm_lifetimes(self):
  ids=['1'*64,'2'*64]
  probes=[{'entrypoint':kind,'image_config_identity':TARGET['image_config_identity'],'observed_absent':True,'run_exit_code':0,'run_failure_type':None,'cleanup_failure_types':[],'foreign_object_not_removed':False,'owned_name':'adhd-accept-probe-'+str(i)*16,'container_id':None} for i,kind in enumerate(['cat','sha256sum'])]
  events=[{'action':'started','container_id':i} for i in ids]+[{'action':kind,'container_id':i,'observed_absent':True,'wait_observed':True,'exit_code':code} for i,kind,code in [(ids[0],'hard-killed',137),(ids[1],'stopped',0)]]
  observations=[{'container_id':i,'host_pid':9999999998+n,'kernel_start_time':str(n)} for n,i in enumerate(ids) for _ in range(2)]
  runtime={'kind':'docker',**TARGET,'canonical_manifest_sha256':'m','payload_verified':True,'probe_cleanup_blocked':False,'cleanup_blocked':False,'payload_probe_lifecycle':probes,'container_lifecycle':events,'kernel_vm_observations':observations}
  value={'passed':True,'schema':'adhd/oidc-policy@1','artifact_sha256':TARGET['artifact_sha256'],'cases':[{'passed':True} for _ in range(5)],'runtime':runtime}
  custody=self.root/'custody.json';custody.write_text(json.dumps({'failure_type':None,'application_assertions_unchanged':True,'runtimes':[runtime]}))
  plan={**TARGET,'canonical_manifest_sha256':'m','custody_report':str(custody)}
  self.assertEqual(m.qualify(value,{},plan)[0],ids)
  for change in (lambda v:v['runtime']['container_lifecycle'][-2].update(exit_code=1),lambda v:v['runtime'].update(payload_verified=False),lambda v:v.update(cases=[])):
   bad=copy.deepcopy(value);change(bad)
   with self.assertRaises(AssertionError):m.qualify(bad,{},plan)
if __name__=='__main__':unittest.main()
