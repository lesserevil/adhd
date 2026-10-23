"""Actual once-driver custody guards without tools, listeners or resources."""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('acme_platform_matrix.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def request():
 return {'schema':'adhd/acme-platform-request@1',
  'target':{'image':'sha256:'+'a'*64,'image_reference':'adhd-hub:actual','artifact_sha256':'b'*64,
    'context':'/owned/context','admission':'/owned/admission/manifest.json','admission_sha256':'c'*64,'source_admission_sha256':'d'*64},
  'toolchain':{'python':'/owned/venv/bin/python','docker':'/usr/bin/docker','compose_plugin':'/owned/docker-compose',
    'kind':'/owned/kind','kubectl':'/owned/kubectl','host_closure':'/owned/host.json','host_closure_sha256':'e'*64},
  'daemon':{'id':'actual-daemon-id','socket_path':'/run/docker.sock','socket_identity':[1,2]},
  'networks':{'compose':{'name':'adhd-acme-compose_default','subnet':'172.30.0.0/24','gateway':'172.30.0.1','nonce':'1'*32},
              'kind':{'name':'adhd-acme-kind-network','subnet':'172.31.0.0/24','gateway':'172.31.0.1','nonce':'2'*32}},
  'ownership':{'compose_project':'adhd-acme-compose','kind_cluster':'adhd-acme-kind','kind_namespace':'adhd-final-adhd-acme-kind',
    'node_image':'kindest/node@sha256:'+'f'*64,'node_config_identity':'sha256:'+'0'*64,'relay_lock':'/owned/_build/acme/http01.lane.lock'},
  'ca':{'manifest':'/owned/ca02/manifest.json','sha256':'3'*64,'minimum_remaining_seconds':1200},
  'protected':{'path':'/owned/protected.json','sha256':'4'*64}}


class Guards(unittest.TestCase):
 def setUp(self):
  self.forbid=[patch.object(subprocess,'Popen',side_effect=AssertionError('No process')),
               patch.object(socket,'socket',side_effect=AssertionError('No listener'))]
  for p in self.forbid:p.start();self.addCleanup(p.stop)
 def test_target_null_template_cannot_prepare_or_launch(self):
  example=m.template();self.assertIsNone(example['target'])
  example.pop('instruction')
  with self.assertRaises(AssertionError):m.validate_request(example)
  for missing in ['toolchain','daemon','networks','ownership','ca','protected']:
   value=request();value[missing]=None
   with self.assertRaises((AssertionError,TypeError)):m.validate_request(value)
 def test_actual_target_shape_and_exact_owned_topology(self):
  value=request();self.assertEqual(m.validate_request(value),value)
  changes=[lambda p:p['target'].update(image='adhd-hub:mutable'),lambda p:p['ownership'].update(kind_cluster='adhd-event-qual'),
   lambda p:p['ownership'].update(kind_namespace='foreign'),lambda p:p['ownership'].update(node_config_identity='mutable'),
   lambda p:p['target'].update(context='relative'),lambda p:p['toolchain'].update(host_closure_sha256='unknown')]
  for change in changes:
   value=request();change(value)
   with self.assertRaises(AssertionError):m.validate_request(value)
 def test_networks_public_overlap_and_unknown_gateway_reject(self):
  for subnet,gateway in [('0.0.0.0/0','0.0.0.1'),('203.0.113.0/24','203.0.113.1'),('172.31.0.0/24','172.31.0.1'),('172.30.0.0/24','172.31.0.1'),('172.30.0.0/24','172.30.0.0')]:
   value=request();value['networks']['compose'].update(subnet=subnet,gateway=gateway)
   with self.assertRaises(AssertionError):m.validate_request(value)
 def test_once_marker_is_exclusive_and_retains_original(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);m.claim(root);first=(root/'execution.started').read_bytes()
   with self.assertRaises(FileExistsError):m.claim(root)
   self.assertEqual(first,(root/'execution.started').read_bytes())
 def test_frozen_set_hash_and_directory_alias_reject(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw)/'tree';root.mkdir();(root/'file').write_bytes(b'bound');expected=m.tree(root);m.verify_tree(root,expected)
   (root/'extra').write_bytes(b'shadow')
   with self.assertRaises(AssertionError):m.verify_tree(root,expected)
   (root/'extra').unlink();(root/'directory').mkdir()
   with self.assertRaises(AssertionError):m.verify_tree(root,expected)
   (root/'directory').rmdir();(root/'file').unlink();(root/'file').symlink_to('/dev/null')
   with self.assertRaises(AssertionError):m.verify_tree(root,expected)
 def test_actual_main_execute_rejects_null_target_before_helper_bootstrap(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);m.dump(root/'plan.json',{'target':None})
   argv=['driver.py','--execute','--work',raw,'--plan-sha256',m.sha(root/'plan.json')]
   with patch.object(sys,'argv',argv),patch.object(m,'bootstrap') as bootstrap:
    with self.assertRaises(AssertionError):m.main()
    bootstrap.assert_not_called()
   self.assertFalse((root/'execution.started').exists())
 def test_existing_network_never_issued_or_deleted(self):
  # network() imports only the inert library and examines authoritative absence.
  value=request()['networks']['compose'];ledger={'issued':False,'id':None};calls=[]
  def command(argv,**kw):
   calls.append(argv);return subprocess.CompletedProcess(argv,0,b'[{"Id":"existing"}]',b'')
  with self.assertRaises(AssertionError):m.network(command,value,'adhd-acme-compose',ledger)
  self.assertFalse(ledger['issued']);self.assertEqual(len(calls),1)
 def test_execution_root_cannot_redirect_or_copy(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);plan={'work':str(root)};m.work_binding(root,plan)
   alias=root/'alias';alias.symlink_to(root,target_is_directory=True)
   for path,declared in [(alias,{'work':str(alias)}),(root,{'work':str(root/'different')})]:
    with self.assertRaises(AssertionError):m.work_binding(path,declared)
 def test_lease_close_independent_of_unlock_and_preserves_primary(self):
  primary=RuntimeError('original');report={'cleanup_errors':[]};calls=[]
  def unlock(*args):calls.append('unlock');raise OSError('unknown')
  with patch.object(m.fcntl,'flock',side_effect=unlock),patch.object(m.os,'close',side_effect=lambda fd:calls.append('close')):
   m.release_lease(17,report,primary)
  self.assertEqual(calls,['unlock','close']);self.assertFalse(report['relay_lease_released'])
  self.assertEqual(str(primary),'original');self.assertTrue(primary.__notes__)
  report={'cleanup_errors':[]}
  with patch.object(m.fcntl,'flock'),patch.object(m.os,'close'):
   m.release_lease(17,report,None)
  self.assertTrue(report['relay_lease_released']);self.assertEqual(report['cleanup_errors'],[])
 def test_template_declares_new_adapter_transitive_shipped_service(self):
  path=Path(__file__).with_name('acme_platform_plan.py')
  spec=importlib.util.spec_from_file_location('recipe',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  self.assertIn('deploy/k8s/events.yaml',module.FILES)
  self.assertIn('tests/acme_platform_matrix.py',module.FILES)

if __name__=='__main__':unittest.main()
