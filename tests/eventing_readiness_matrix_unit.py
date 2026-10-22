"""Pure metadata/custody gate checks; never compile or start an application."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('eventing_readiness_matrix.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Gates(unittest.TestCase):
 def fixture(self,root):
  export=root/'official.exs';export.write_bytes(b'authored test bytes, not an actual admitted artifact')
  ident='sha256:'+'a'*64
  payload={'result':ident,'project_revision':ident,'tests':18,'project':'adhd'}
  receipt={'schema':'urn:literate-ai:schema:v1:project-test-receipt-finalized-candidate','receipt':payload,
   'receipt_identity':'sha256:'+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
   'lifecycle_request_identity':ident,'lifecycle_command_identity':ident,'component_lock_identities':[ident]}
  result={'schema':'literate-ai/project-rebuild@1','passed':True,'receipt_committed':True,'artifact':str(export),
   'receipt_identity':receipt['receipt_identity'],'receipt_update':{'identity':receipt['receipt_identity']},
   'lifecycle_request_identity':ident,'lifecycle_invocation_identity':ident,'lifecycle_result_identity':ident,
   'validated_project_authority_identity':ident,'project_revision_identity':ident,'component_lock_identities':[ident],
   'component_lock_identity':ident,'test_summary':{'failed':0,'passed':18,'skipped':0,'total':18},'project_id':'adhd'}
  r=root/'rebuild.json';r.write_text(json.dumps({'schema':'literate-ai/cli-result@1','command':'rebuild','ok':True,'result':result}))
  f=root/'receipt.json';f.write_text(json.dumps(receipt));return export,r,f
 def test_matching_metadata_shape_only(self):
  with tempfile.TemporaryDirectory()as d:
   e,r,f=self.fixture(Path(d));x=m.validate_official(e,r,f);self.assertEqual(x['artifact_sha256'],m.sha(e))
 def test_missing_official_input_rejected_before_work_or_child(self):
  with tempfile.TemporaryDirectory()as d,patch.object(m.subprocess,'Popen',side_effect=AssertionError('child forbidden'))as launch:
   root=Path(d);a=argparse.Namespace(export=root/'absent',rebuild=root/'absent2',receipt=root/'absent3',work=root/'never')
   with self.assertRaises(FileNotFoundError):m.prepare(a)
   self.assertFalse(a.work.exists());launch.assert_not_called()
 def test_candidate_substitution_and_failed_rebuild_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);e,r,f=self.fixture(root);candidate=root/'candidate.exs';candidate.write_bytes(e.read_bytes())
   with self.assertRaisesRegex(AssertionError,'actual official'):m.validate_official(candidate,r,f)
   data=json.loads(r.read_text());data['result']['passed']=False;r.write_text(json.dumps(data))
   with self.assertRaises(AssertionError):m.validate_official(e,r,f)
 def test_mismatching_lifecycle_and_receipt_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   e,r,f=self.fixture(Path(d));data=json.loads(f.read_text());data['lifecycle_request_identity']='sha256:'+'b'*64;f.write_text(json.dumps(data))
   with self.assertRaises(AssertionError):m.validate_official(e,r,f)
   data['receipt']['tests']=17;f.write_text(json.dumps(data))
   with self.assertRaises(AssertionError):m.validate_official(e,r,f)
 def test_tree_extra_and_symlink_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);(root/'a').write_bytes(b'one');before=m.inventory(root);(root/'extra').write_bytes(b'two')
   self.assertNotEqual(before,m.inventory(root));(root/'redirect').symlink_to(root/'a')
   with self.assertRaises(AssertionError):m.inventory(root)
 def test_once_is_durable_and_reentry_before_child(self):
  with tempfile.TemporaryDirectory()as d,patch.object(m,'sync_dir',wraps=m.sync_dir)as sync,patch.object(m.subprocess,'Popen')as launch:
   p=Path(d)/'started.json';m.claim(p);self.assertEqual(json.loads(p.read_text()),{'claimed':True});sync.assert_called_once_with(p.parent)
   with self.assertRaises(FileExistsError):m.claim(p)
   launch.assert_not_called()
 def test_wrong_driver_refused_before_child(self):
  with tempfile.TemporaryDirectory()as d,patch.object(m.subprocess,'Popen')as launch:
   root=Path(d);(root/'plan.json').write_text(json.dumps({'schema':m.SCHEMA}))
   with self.assertRaises(AssertionError):m.execute(root)
   launch.assert_not_called();self.assertFalse((root/'started.json').exists())
 def test_original21_prefix_and_two_reviewed_additions(self):
  old=('lag','queue-control','duplicate','duplicate-bad-topology','never','queue','forbidden','server-error','malformed','bad-cleanup','partitions-float','retention-missing','retention-float','retention-negative','retention-duplicate','existing-retention','offset-nonzero','offset-negative','offset-missing','offset-float','offset-string')
  self.assertEqual(m.CASES[:21],old);self.assertEqual(m.CASES[21:],('metadata-lag','offset-end-float'))
  self.assertEqual(m.SCHEMA,'adhd/eventing-readiness-native23-plan@1')
 def test_endpoint_cannot_select_model_or_remote(self):
  self.assertEqual(m.endpoint('http://127.0.0.1:18082'),'http://127.0.0.1:18082')
  for x in ['http://127.0.0.1:18770','http://example.org:18082','http://u:p@127.0.0.1:18082','http://127.0.0.1:18082/x']:
   with self.assertRaises(AssertionError):m.endpoint(x)
if __name__=='__main__':unittest.main()
