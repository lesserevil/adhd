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

spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('image_kafka_matrix.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

UNIT_IMAGE='sha256:'+'a'*64
UNIT_ARTIFACT='b'*64
UNIT_ADMISSION='c'*64
BINDINGS={'image_config_identity':UNIT_IMAGE,'artifact_sha256':UNIT_ARTIFACT,'admission_sha256':UNIT_ADMISSION}

class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
 def tearDown(self):self.tmp.cleanup()
 def test_exact_tree_and_empty_directories(self):
  (self.root/'file').write_text('a');expected=m.inventory(self.root)
  (self.root/'extra').mkdir()
  with self.assertRaises(AssertionError):m.check_tree(self.root,expected)
 def test_tool_internal_directory_alias_bound(self):
  target=self.root/'lib';target.mkdir();(target/'tool').write_text('v1');(self.root/'lib64').symlink_to('lib',target_is_directory=True)
  before=m.tool_tree(self.root);self.assertEqual(before['files']['lib64']['directory_symlink'],'lib')
  (target/'tool').write_text('v2');self.assertNotEqual(m.tool_tree(self.root),before)
 def test_tool_external_directory_alias_denied(self):
  (self.root/'external').symlink_to('/usr/lib',target_is_directory=True)
  with self.assertRaises(AssertionError):m.tool_tree(self.root)
 def test_directory_symlink(self):
  (self.root/'actual').mkdir();(self.root/'redirect').symlink_to(self.root/'actual',target_is_directory=True)
  with self.assertRaises(AssertionError):m.inventory(self.root)
 def test_root_redirect(self):
  target=self.root/'real';target.mkdir();link=self.root/'link';link.symlink_to(target,target_is_directory=True)
  with self.assertRaises(AssertionError):m.inventory(link)
 def test_native_exact_selection(self):
  native=json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/image38-reviewed-preparation/eventing/plan.json').read_text())
  self.assertEqual([r['name'] for r in m.selected_native_jobs(native)],m.BASIS_NAMES)
  bad=copy.deepcopy(native);row=next(r for r in bad['jobs'] if r['name']=='cutover-project');row['arguments'][row['arguments'].index('--deadline')+1]='91'
  with self.assertRaises(AssertionError):m.selected_native_jobs(bad)
 def test_complete_seven_outage_plus_two_filter_checks_without_changing_original_jobs(self):
  native=json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/image38-reviewed-preparation/eventing/plan.json').read_text());before=copy.deepcopy(native)
  rows=m.complete_jobs(native)
  self.assertEqual([r['name'] for r in rows],m.NAMES)
  self.assertEqual([r for r in rows if r['name']!='optional-filter'],before['jobs'])
  optional=next(r for r in rows if r['name']=='optional-filter')
  outage=next(r for r in rows if r['name']=='outage')
  self.assertEqual(optional['arguments'],outage['arguments'])
  self.assertEqual(optional['script'],'eventing_optional_faults.py')
  arguments=m.optional_filter_arguments(optional['arguments'])
  self.assertIn('--with-model',arguments);self.assertNotIn('--broker-container',arguments)
  self.assertEqual(arguments[arguments.index('--deadline')+1],'90')
  self.assertNotIn('--with-model',outage['arguments']);self.assertEqual(native,before)
  self.assertEqual(m.COUNTS['outage'],7);self.assertEqual(m.COUNTS['optional-filter'],2)
  self.assertEqual(sum(m.COUNTS.values()),68)
 def test_owned_rest_port_preserves_default_and_all_original_program_arguments(self):
  native=json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/image38-reviewed-preparation/eventing/plan.json').read_text())
  rows=m.complete_jobs(native)
  for row in rows:
   original=row['arguments'];self.assertEqual(m.private_rest_arguments(original,18088),original)
   changed=m.private_rest_arguments(original,18089)
   differences=[(a,b) for a,b in zip(original,changed) if a!=b]
   if row['name'] in ('retention','outage','optional-filter','federation'):
    self.assertEqual(len(differences),1);self.assertIn('18088',differences[0][0]);self.assertIn('18089',differences[0][1])
   else:self.assertEqual(changed,original)
   self.assertEqual(len(changed),len(original))
  self.assertEqual(sum(m.COUNTS.values()),68);self.assertEqual(len(rows),14)
 def test_private_port_rejects_collision_bad_types_and_foreign_federation_urls(self):
  for value in (True,'18089',0,1023,65536,18082,18085):
   with self.assertRaises(AssertionError):m.private_rest_arguments([],value)
  for urls in (["http://foreign:18088"],['http://127.0.0.1:18085','http://127.0.0.1:18082','http://127.0.0.1:18088']):
   with self.assertRaises(AssertionError):m.private_rest_arguments(['--eventing-rest-urls',json.dumps(urls)],18089)
 def test_authoritative_absence_only(self):
  id='a'*64
  good=subprocess.CompletedProcess([],1,b'[]',('error: no such object: '+id).encode())
  self.assertTrue(m.absent(good,id))
  for rc,err in [(2,good.stderr),(1,b'daemon unavailable'),(1,good.stderr+b'\nconnection failed')]:
   self.assertFalse(m.absent(subprocess.CompletedProcess([],rc,b'',err),id))
 def test_absence_identifier_is_case_sensitive(self):
  for key in ('aBcD'*16,'adhd-accept-probe-aBcD1234'):
   self.assertTrue(m.absent(subprocess.CompletedProcess([],1,b'[]',('error: no such object: '+key).encode()),key))
   for wrong in (key.upper(),key.lower()):self.assertFalse(m.absent(subprocess.CompletedProcess([],1,b'[]',('Error: No such object: '+wrong).encode()),key))
 def test_absence_cannot_contradict_stdout(self):
  key='a'*64
  for out in (b'[{"Id":"foreign"}]',b'{"State":"running"}',b'[]\nforeign'):
   self.assertFalse(m.absent(subprocess.CompletedProcess([],1,out,('error: no such object: '+key).encode()),key))
 def fixture(self):
  (self.root/'runtime').mkdir()
  plan={'driver_sha256':'test','lane_lock':str(self.root/'lock'),'runtime_cwd':str(self.root/'runtime'),
   'tools':{k:{'path':'/test/'+k} for k in ('python','elixir','erl','docker')},'docker_socket':{'path':'/test/socket'},
   'tool_trees':[],'jobs':[{'name':n,'argv':['never-run']} for n in m.NAMES],'scope':'pure','image_config_identity':UNIT_IMAGE,'artifact_sha256':UNIT_ARTIFACT,'admission_sha256':UNIT_ADMISSION}
  m.save(self.root/'plan.json',plan);return m.sha(self.root/'plan.json')
 def test_once_before_actual_boundary_and_no_retry(self):
  digest=self.fixture()
  with patch.object(m,'verify',return_value=True),patch.object(m,'preflight',return_value={}),patch.object(m.subprocess,'run',side_effect=OSError('mock launch')) as run:
   with self.assertRaises(OSError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
   with self.assertRaises(FileExistsError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'matrix.json').read_text())
  self.assertFalse(result['passed']);self.assertEqual(result['attempted'],['controls']);self.assertEqual(result['executed'],[]);self.assertEqual(result['unrun'],m.NAMES)
 def test_returned_exit_retained_before_bad_report(self):
  digest=self.fixture()
  def fake(*args,**kwargs):
   (self.root/'controls.json').write_text('{"passed":true}')
   return subprocess.CompletedProcess([],0)
  with patch.object(m,'verify',return_value=True),patch.object(m,'preflight',return_value={}),patch.object(m.subprocess,'run',side_effect=fake) as run:
   with self.assertRaises(KeyError):m.execute(self.root,digest)
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'matrix.json').read_text());self.assertEqual(result['executed'],['controls']);self.assertEqual(result['results'][0]['process_exit_code'],0);self.assertFalse(result['passed'])
 def test_unknown_cleanup_not_qualified(self):
  runtime={'kind':'docker','image_config_identity':UNIT_IMAGE,'artifact_sha256':UNIT_ARTIFACT,'canonical_manifest_sha256':'m',
   'cleanup_blocked':True,'container_lifecycle':[]}
  value={'passed':True,'artifact_sha256':UNIT_ARTIFACT,'checks':[{'passed':True}],'runtime':runtime}
  with self.assertRaises(AssertionError):m.qualify(value,{'script':'eventing_cutover.py','expected_check_count':1},{**BINDINGS,'canonical_manifest_sha256':'m'})

class ClusterGuards(unittest.TestCase):
 def plan(self):return {'tools':{'docker':{'path':'/never-execute'}},'private_service':{'project':'owned','broker':'owned-kafka-1','rest':'owned-kafka-rest-1','port':'18088','urls':['http://127.0.0.1:'+str(p) for p in (18082,18085,18088)]}}
 def inspected(self,service,project='owned'):
  row={'Id':service+'-id','Image':'sha256:test','State':{'Running':True},'Config':{'Labels':{'com.docker.compose.project':project,'com.docker.compose.service':service}},'NetworkSettings':{'Ports':{'8082/tcp':[{'HostPort':'18088','HostIp':'127.0.0.1'}]}}}
  return subprocess.CompletedProcess([],0,json.dumps([row]).encode(),b'')
 def test_foreign_service_rejected_before_network(self):
  import urllib.request
  with patch.object(m.subprocess,'run',return_value=self.inspected('kafka','foreign')) as run,patch.object(urllib.request,'build_opener') as opened:
   with self.assertRaises(AssertionError):m.preflight(self.plan(),{})
   self.assertEqual(run.call_count,1);opened.assert_not_called()
 def test_three_cluster_identity_and_bound_loopback(self):
  import urllib.request
  from contextlib import contextmanager
  class Opener:
   def __init__(self,ids):self.ids=iter(ids)
   @contextmanager
   def open(self,url,timeout):
    class Response:
     status=200
     def read(self,limit):return json.dumps({'data':[{'cluster_id':next(ids)}]}).encode()
    ids=self.ids;yield Response()
  for ids,valid in [(['a','b','c'],True),(['a','b','a'],False)]:
   with patch.object(m.subprocess,'run',side_effect=[self.inspected('kafka'),self.inspected('kafka-rest')]),patch.object(urllib.request,'build_opener',return_value=Opener(ids)):
    if valid:self.assertEqual(len(m.preflight(self.plan(),{})['clusters']),3)
    else:
     with self.assertRaises(AssertionError):m.preflight(self.plan(),{})
 def test_nonloopback_private_rest_binding_denied(self):
  foreign=self.inspected('kafka-rest');row=json.loads(foreign.stdout);row[0]['NetworkSettings']['Ports']['8082/tcp'][0]['HostIp']='0.0.0.0';foreign.stdout=json.dumps(row).encode()
  with patch.object(m.subprocess,'run',side_effect=[self.inspected('kafka'),foreign]):
   with self.assertRaises(AssertionError):m.preflight(self.plan(),{})

class ProbeLedger(unittest.TestCase):
 def fixture(self):
  probes=[{'owned_name':'adhd-accept-probe-'+str(i)*16,'container_id':None,'image_config_identity':UNIT_IMAGE,'entrypoint':entry,'run_exit_code':0,'run_failure_type':None,'foreign_object_not_removed':False,'observed_absent':True,'cleanup_failure_types':[]} for i,entry in [(1,'cat'),(2,'sha256sum')]]
  runtime={'kind':'docker','image_config_identity':UNIT_IMAGE,'artifact_sha256':UNIT_ARTIFACT,'canonical_manifest_sha256':'m','payload_verified':True,'probe_cleanup_blocked':False,'payload_probe_lifecycle':probes,'container_lifecycle':[{'action':'started','container_id':'a'*64},{'action':'stopped','container_id':'a'*64,'observed_absent':True,'wait_observed':True}]}
  return {'passed':True,'artifact_sha256':UNIT_ARTIFACT,'checks':[{'passed':True}],'runtime':runtime}
 def qualify(self,value):return m.qualify(value,{'script':'eventing_acceptance.py','expected_check_count':1,'observer_source':None},{**BINDINGS,'canonical_manifest_sha256':'m'})
 def test_probe_names_in_independent_absence_set(self):
  ids,names=self.qualify(self.fixture());self.assertEqual(ids,['a'*64]);self.assertEqual(len(names),2)
 def test_unknown_probe_cleanup_denied(self):
  value=self.fixture();value['runtime']['payload_probe_lifecycle'][0]['observed_absent']=False
  with self.assertRaises(AssertionError):self.qualify(value)
 def test_failed_verification_never_qualifies(self):
  value=self.fixture();value['runtime']['payload_verified']=False
  with self.assertRaises(AssertionError):self.qualify(value)
 def test_probe_failure_cannot_be_erased_by_later_absence(self):
  value=self.fixture();value['runtime']['payload_probe_lifecycle'][0]['run_failure_type']='TimeoutExpired'
  with self.assertRaises(AssertionError):self.qualify(value)

 def test_hub_payload_is_verified_in_actual_app_without_standalone_probes(self):
  value=self.fixture();runtime=value['runtime']
  for key in ('payload_verified','probe_cleanup_blocked','payload_probe_lifecycle'):runtime.pop(key)
  ids,names=m.qualify(value,{'script':'eventing_retention.py','expected_check_count':1,'observer_source':None},{**BINDINGS,'canonical_manifest_sha256':'m'})
  self.assertEqual(ids,['a'*64]);self.assertEqual(names,[])

class TargetBindings(unittest.TestCase):
 def test_explicit_target_has_no_ambient_default(self):
  self.assertEqual(m.target_bindings(BINDINGS),(UNIT_IMAGE,UNIT_ARTIFACT,UNIT_ADMISSION))
  for bad in ({},{**BINDINGS,'image_config_identity':'tag:latest'},{**BINDINGS,'artifact_sha256':None},{**BINDINGS,'admission_sha256':'short'}):
   with self.assertRaises((KeyError,AssertionError)):m.target_bindings(bad)
 def test_two_targets_stay_distinct_without_mutable_selection(self):
  for image,artifact,admission in [(UNIT_IMAGE,UNIT_ARTIFACT,UNIT_ADMISSION),('sha256:'+'d'*64,'e'*64,'f'*64)]:
   target={'image_config_identity':image,'artifact_sha256':artifact,'admission_sha256':admission,'canonical_manifest_sha256':'manifest'}
   value={'passed':True,'artifact_sha256':artifact,'checks':[{'passed':True}],'runtime':{'kind':'docker','image_config_identity':image,'artifact_sha256':artifact,'canonical_manifest_sha256':'manifest','container_lifecycle':[{'action':'started','container_id':'9'*64},{'action':'stopped','container_id':'9'*64,'observed_absent':True}]}}
   job={'script':'eventing_retention.py','expected_check_count':1,'observer_source':None}
   self.assertEqual(m.qualify(value,job,target),(['9'*64],[]))
   value['runtime']['image_config_identity']='sha256:'+'0'*64
   with self.assertRaises(AssertionError):m.qualify(value,job,target)
  self.assertEqual(m.target_bindings(BINDINGS),(UNIT_IMAGE,UNIT_ARTIFACT,UNIT_ADMISSION))

if __name__=='__main__':unittest.main()
