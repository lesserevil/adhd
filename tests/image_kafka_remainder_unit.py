#!/usr/bin/env python3
"""Pure admission/custody guards; every process boundary is mocked."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('image_kafka_remainder.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

TARGET={'image_config_identity':'sha256:'+'4'*64,'artifact_sha256':'5'*64,'admission_sha256':'6'*64}

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
 def test_original_basis_order_preserved(self):
  native=json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/image38-reviewed-preparation/eventing/plan.json').read_text())
  self.assertEqual([r['name'] for r in m.selected_native_jobs(native)],m.BASIS_NAMES)
  self.assertEqual(m.NAMES,['optional-filter','federation']);self.assertEqual(m.COUNTS,{'optional-filter':2,'federation':14})
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
   'composed_prefix':{},'jobs':[{'name':n,'argv':['never-run']} for n in m.NAMES],'scope':'pure',**TARGET}
  m.save(self.root/'plan.json',plan);return m.sha(self.root/'plan.json')
 def test_once_before_actual_boundary_and_no_retry(self):
  digest=self.fixture()
  with patch.object(m,'preflight',return_value={}),patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=OSError('mock launch')) as run:
   with self.assertRaises(OSError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
   with self.assertRaises(FileExistsError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'matrix.json').read_text())
  self.assertFalse(result['passed']);self.assertEqual(result['attempted'],['optional-filter']);self.assertEqual(result['executed'],[]);self.assertEqual(result['unrun'],m.NAMES)
 def test_returned_exit_retained_before_bad_report(self):
  digest=self.fixture()
  def fake(*args,**kwargs):
   (self.root/'optional-filter.json').write_text('{"passed":true}')
   return subprocess.CompletedProcess([],0)
  with patch.object(m,'preflight',return_value={}),patch.object(m,'verify',return_value=True),patch.object(m.subprocess,'run',side_effect=fake) as run:
   with self.assertRaises(KeyError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'matrix.json').read_text());self.assertEqual(result['executed'],['optional-filter']);self.assertEqual(result['results'][0]['process_exit_code'],0);self.assertFalse(result['passed'])
 def test_unknown_cleanup_not_qualified(self):
  runtime={'kind':'docker',**TARGET,'canonical_manifest_sha256':'m',
   'cleanup_blocked':True,'container_lifecycle':[]}
  value={'passed':True,'artifact_sha256':TARGET['artifact_sha256'],'checks':[{'passed':True}],'runtime':runtime}
  with self.assertRaises(AssertionError):m.qualify(value,{'name':'federation','script':'federation_multi.py','expected_check_count':1,'observer_source':None},{**TARGET,'canonical_manifest_sha256':'m'})

 def test_target_no_defaults_and_no_global_mutation(self):
  first=m.target_bindings(TARGET);second=m.target_bindings(dict(image_config_identity='sha256:'+'7'*64,artifact_sha256='8'*64,admission_sha256='9'*64))
  self.assertNotEqual(first,second);self.assertEqual(first,m.target_bindings(TARGET))
  with self.assertRaises(KeyError):m.target_bindings({})
 def test_malformed_target(self):
  for key in TARGET:
   for bad in (None,'','sha256:tag','A'*64):
    with self.assertRaises(AssertionError):m.target_bindings({**TARGET,key:bad})
 def test_absence_identifier_case_sensitive(self):
  name='MixedCase'
  self.assertTrue(m.absent(subprocess.CompletedProcess([],1,b'',b'error: no such object: MixedCase'),name))
  self.assertFalse(m.absent(subprocess.CompletedProcess([],1,b'[]',b'error: no such object: mixedcase'),name))
 def test_absence_contradictory_stdout(self):
  for out in (b'[{}]',b'connected',b'{}'):
   self.assertFalse(m.absent(subprocess.CompletedProcess([],1,out,b'error: no such object: Name'),'Name'))
 def valid_report(self):
  probe=lambda kind:{'entrypoint':kind,'image_config_identity':TARGET['image_config_identity'],'observed_absent':True,'run_exit_code':0,'run_failure_type':None,'cleanup_failure_types':[],'foreign_object_not_removed':False,'owned_name':'adhd-accept-probe-'+'a'*16,'container_id':None}
  runtime={'kind':'docker',**TARGET,'canonical_manifest_sha256':'m','payload_verified':True,'probe_cleanup_blocked':False,'payload_probe_lifecycle':[probe('cat'),probe('sha256sum')],'container_lifecycle':[{'action':'started','container_id':'a'*64},{'action':'hard-killed','container_id':'a'*64,'observed_absent':True,'wait_observed':True,'exit_code':137}]}
  return {'passed':True,'artifact_sha256':TARGET['artifact_sha256'],'checks':[{'passed':True}],'runtime':runtime}
 def test_payload_probe_ledger_required(self):
  v=self.valid_report();job={'name':'federation','script':'eventing_optional_faults.py','expected_check_count':1,'observer_source':None};plan={**TARGET,'canonical_manifest_sha256':'m'}
  self.assertEqual(m.qualify(v,job,plan)[0],['a'*64])
  for modify in (lambda r:r.update(payload_verified=False),lambda r:r.update(probe_cleanup_blocked=True),lambda r:r.update(payload_probe_lifecycle=[]),lambda r:r['payload_probe_lifecycle'][0].update(observed_absent=False)):
   bad=copy.deepcopy(v);modify(bad['runtime'])
   with self.assertRaises(AssertionError):m.qualify(bad,job,plan)
 def test_other_target_report_refused(self):
  v=self.valid_report();v['runtime']['image_config_identity']='sha256:'+'1'*64
  with self.assertRaises(AssertionError):m.qualify(v,{'name':'federation','script':'federation_multi.py','expected_check_count':1,'observer_source':None},{**TARGET,'canonical_manifest_sha256':'m'})
 def test_no_old_result_composition(self):
  self.assertEqual(m.NAMES,['optional-filter','federation']);self.assertTrue(hasattr(m,'read_prefix'))

class MissingPhase(unittest.IsolatedAsyncioTestCase):
 async def test_reuses_original_two_assertion_functions_only(self):
  import eventing_acceptance as original
  import eventing_optional_faults as wrapper
  self.assertIs(wrapper.filtered_faults,original.filtered_faults)
  calls=[]
  class Agent:
   async def call(self,value):calls.append(value);return {}
  class F:
   args=type('Args',(),{'with_model':True,'rest_url':None})()
   model=type('Model',(),{'calls':1,'requests':[{}]})()
   async def agent(self,name):return Agent()
  class E:value={}
  async def phase(*args):calls.append('original-two')
  with patch.object(wrapper,'filtered_faults',phase):await wrapper.checks(F(),E())
  self.assertEqual(len(calls),2);self.assertEqual(calls[0]['op'],'subscribe');self.assertEqual(calls[0]['mode'],'raw');self.assertEqual(calls[1],'original-two')
 def test_real_complete_prefix_false_aggregate_retained(self):
  prefix=Path(__file__).resolve().parents[1]/'verification/image40-kafka-current02-negative'
  plan=json.loads((prefix/'plan.json').read_text());v=m.read_prefix(prefix,plan['image_config_identity'],plan['artifact_sha256'])
  self.assertFalse(v['matrix_passed']);self.assertEqual(v['independently_complete_prefix_checks'],52)
 def test_controlled_fixture_not_provider(self):
  source=Path('/home/horde/src/adhd/tests/multi_support.py').read_text()
  self.assertIn('self.model = ModelFixture() if args.with_model else None',source)
  tree=ast.parse(Path(__file__).with_name('eventing_optional_faults.py').read_text())
  calls=[n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
  self.assertIn('filtered_faults',calls);self.assertNotIn('broker_faults',calls)

if __name__=='__main__':unittest.main()
