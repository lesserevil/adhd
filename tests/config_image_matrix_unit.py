"""No-startup checks for the dedicated three-boundary image driver."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import config_image_matrix as matrix

TARGET=matrix.target_identity('sha256:'+'a'*64,'b'*64,'c'*64)
def plan_with(**extra):return {**TARGET,**extra}

class ConfigMatrixGuards(unittest.TestCase):
 def test_explicit_target_parameters_reject_malformed_bindings(self):
  self.assertEqual(matrix.target_identity(TARGET['image_config_identity'],TARGET['artifact_sha256'],TARGET['admission_sha256']),TARGET)
  for changed in [dict(TARGET,image_config_identity='tag:latest'),dict(TARGET,artifact_sha256='B'*64),dict(TARGET,admission_sha256=None)]:
   with self.assertRaises(AssertionError):matrix.target_identity(changed['image_config_identity'],changed['artifact_sha256'],changed['admission_sha256'])
 def test_current40_admission_file_and_target_mismatches_fail_before_startup(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for name in ['receipt.json','rebuild.json','image-manifest.json']:(root/name).write_text('{}')
   admission={'schema':'adhd/current40-admission-and-image-binding@1','passed':True,'image_built':True,
    'image_config_identity':TARGET['image_config_identity'],'artifact_sha256':TARGET['artifact_sha256'],
    'canonical_manifest_sha256':matrix.sha(root/'image-manifest.json'),
    'files':{name:matrix.sha(root/name) for name in ['receipt.json','rebuild.json']},
    'payload_audit':{'passed':True,'image_id':TARGET['image_config_identity'],'artifact_sha256':TARGET['artifact_sha256'],
     'canonical_manifest_sha256':matrix.sha(root/'image-manifest.json'),'actual_app_files':59,'canonical_specifications':33}}
   matrix.save(root/'admission.json',admission);target=dict(TARGET,admission_sha256=matrix.sha(root/'admission.json'))
   self.assertTrue(matrix.validate_admission(root,target))
   for changed in [dict(target,image_config_identity='sha256:'+'d'*64),dict(target,artifact_sha256='d'*64),dict(target,admission_sha256='d'*64)]:
    with self.assertRaises(AssertionError):matrix.validate_admission(root,changed)
   (root/'receipt.json').write_text('changed')
   with self.assertRaises(AssertionError):matrix.validate_admission(root,target)
 def test_config_selection_rejects_real_provider_and_broker(self):
  base={'matcher':{'url':'http://127.0.0.1:1/v1/systemone'},'eventing':{'enabled':False}}
  self.assertTrue(matrix.audit_configuration(base,False))
  for changed in [dict(base,matcher={'url':'http://127.0.0.1:18770/v1/systemone'}),dict(base,eventing={'enabled':True,'rest_url':'http://127.0.0.1:18082'}),dict(base,history={'assessment':{'endpoint':'http://127.0.0.1:18770'}}),dict(base,projects=[{'settings':{'history':{'assessment':{'url':'http://127.0.0.1:18770'}}}}])]:
   with self.assertRaises(AssertionError):matrix.audit_configuration(changed,False)
 def test_legacy_disabled_shape_requires_actual_public_transport_proof(self):
  base={'matcher':{'url':'http://127.0.0.1:1/v1/systemone'}}
  self.assertTrue(matrix.audit_configuration(base,False))
  self.assertTrue(matrix.audit_configuration(dict(base,eventing={'enabled':False}),False))
  for changed in [dict(base,eventing=None),dict(base,eventing={}),dict(base,eventing={'enabled':True}),dict(base,eventing={'enabled':False,'rest_url':'http://127.0.0.1:18082'}),dict(base,projects=[{'settings':{'eventing':{'topic_prefix':'different'}}}])]:
   with self.assertRaises(AssertionError):matrix.audit_configuration(changed,False)
  command={'op':'project_restore_status','project_id':'legacy'}
  response={'operation':{'state':'ready','kind':'plan','plan':{'mode':'initialize','selected':{'transport_enabled':False,'topic':None}}}}
  row=matrix.initialization_observation(command,response)
  self.assertFalse(row['transport_enabled']);self.assertIsNone(row['topic'])
  for selected in [{'transport_enabled':True,'topic':'active'}, {'transport_enabled':False,'topic':'unexpected'}]:
   changed={'operation':{**response['operation'],'plan':{'mode':'initialize','selected':selected}}}
   with self.assertRaises(AssertionError):matrix.initialization_observation(command,changed)
  self.assertIsNone(matrix.initialization_observation(command,{'operation':None}))
 def test_actual_execute_once_refuses_before_child(self):
  from controlled_image_matrix import durable_once_marker
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'frozen/tests').mkdir(parents=True)
   plan=plan_with(runtime_cwd=str(root/'runtime'));matrix.save(root/'plan.json',plan)
   durable_once_marker(root/'started.json',{'plan_sha256':matrix.sha(root/'plan.json')})
   helper=type('Helper',(),{'durable_once_marker':staticmethod(durable_once_marker)})()
   with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'load',return_value=helper):
    with self.assertRaises(FileExistsError):matrix.execute(root,matrix.sha(root/'plan.json'))
   self.assertFalse((root/'runtime').exists())
 def test_full_tree_rejects_aliases_and_extra_file(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'original').write_text('bound');before=matrix.tree(root)
   (root/'alias').symlink_to(root/'original')
   with self.assertRaises(AssertionError):matrix.tree(root)
   (root/'alias').unlink();(root/'extra').write_text('extra')
   self.assertNotEqual(matrix.tree(root),before)
 def test_absence_checks_all_issued_names_even_on_transport_failure(self):
  from controlled_image_matrix import authoritative_absence
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);matrix.save(root/'custody-progress.json',{'runtimes':[],'launches':[{'name':'adhd-accept-probe-0000000000000001'},{'name':'adhd-multi-accept-0000000000000002'}]})
   helper=type('Helper',(),{'authoritative_absence':staticmethod(authoritative_absence)})()
   def inspect(argv,**kwargs):
    name=argv[-1]
    if name.endswith('1'):return subprocess.CompletedProcess(argv,125,b'',b'daemon unavailable')
    return subprocess.CompletedProcess(argv,1,b'[]\n',('error: no such object: '+name+'\n').encode())
   with patch.object(matrix,'load',return_value=helper),patch.object(matrix.subprocess,'run',side_effect=inspect) as calls:
    rows=matrix.independent_absence(root,plan_with(tools={'docker':{'path':'docker'}}))
   self.assertEqual(calls.call_count,2);self.assertEqual([r['observed_absent'] for r in rows],[False,True])
 def test_known_container_replacement_is_never_removed(self):
  from controlled_image_matrix import authoritative_absence
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);name='adhd-multi-accept-0000000000000001';cid='a'*64
   matrix.save(root/'custody-progress.json',{'runtimes':[],'launches':[{'name':name,'container_id':cid}]})
   helper=type('Helper',(),{'authoritative_absence':staticmethod(authoritative_absence)})()
   obj={'Id':'b'*64,'Image':TARGET['image_config_identity'],'Name':'/'+name}
   with patch.object(matrix,'load',return_value=helper),patch.object(matrix.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps([obj]).encode(),b'')) as calls:
    rows=matrix.independent_absence(root,plan_with(tools={'docker':{'path':'docker'}}))
   self.assertEqual(calls.call_count,1);self.assertFalse(rows[0]['fallback_removal']);self.assertFalse(rows[0]['observed_absent'])

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No runtime process allowed')):
  unittest.main()
