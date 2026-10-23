"""Actual once-driver custody guards without tools, listeners or resources."""
import copy
import importlib.util
import json
import ipaddress
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

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
 def test_platform_selection_defaults_and_exact_kind_continuation(self):
  self.assertEqual(m.platform_order(),['compose','kind'])
  self.assertEqual(m.platform_order(['kind']),['kind'])
  self.assertEqual(m.platform_order(['kind','compose']),['compose','kind'])
  for value in [[],['kind','kind'],['unknown'],'kind',[True],None]:
   if value is None:continue
   with self.assertRaises(AssertionError):m.platform_order(value)
  with patch.object(sys,'argv',['driver.py','--execute','--work','/not-read','--platforms','kind']),patch.object(m,'regular') as read:
   with self.assertRaisesRegex(AssertionError,'preparation only'):m.main()
   read.assert_not_called()
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
 def test_seed_initialize_failure_retains_issued_custody_and_primary(self):
  original=TimeoutError('seed timeout');probe=SimpleNamespace(probe_events=[],probe_cleanup_blocked=False)
  def initialize():
   probe.probe_events.append({'name':'adhd-accept-probe-owned','id':'a'*64,'closed':False})
   probe.probe_cleanup_blocked=True
   raise original
  probe.initialize=initialize;row={}
  with self.assertRaises(TimeoutError) as caught:m.initialize_seed(row,probe)
  self.assertIs(caught.exception,original)
  self.assertEqual(row['seed_probe'],probe.probe_events);self.assertTrue(row['seed_probe_cleanup_blocked'])
  # Phase finally refreshes the ledger even if later independent cleanup adds facts.
  probe.probe_events.append({'cleanup':'unknown'});m.seed_evidence(row,probe)
  self.assertEqual(len(row['seed_probe']),2)
 def test_nondefault_port_request_and_occupied_preflight_fail_closed(self):
  value=request();value['ownership']['private_http_port']=18866;m.validate_request(value)
  for port in [True,'18866',80,443,8080,8443,8766,18770,18082,19100,65536]:
   value['ownership']['private_http_port']=port
   with self.assertRaises(AssertionError):m.validate_request(value)
  for error in [None,OSError('occupied')]:
   stream=SimpleNamespace(bind=Mock(side_effect=error),close=Mock())
   with patch.object(m.socket,'socket',return_value=stream):
    if error:
     with self.assertRaises(OSError):m.private_port_preflight(18866)
    else:m.private_port_preflight(18866)
   stream.bind.assert_called_once_with(('127.0.0.1',18866));stream.close.assert_called_once()
 def test_nullable_host_none_IPAM_accepted_without_mutation(self):
  values=[{'Id':'a'*64,'Driver':'host','IPAM':{'Config':None}},{'Id':'b'*64,'Driver':'null','IPAM':{'Config':None}},
          {'Id':'c'*64,'Driver':'bridge','IPAM':{'Config':[{'Subnet':'172.18.0.0/16'},{'Subnet':'fd00::/64'}]}}]
  calls=[]
  def command(argv,**kw):
   calls.append(argv)
   if argv[2]=='ls':body='\n'.join(r['Id'] for r in values).encode()
   else:
    self.assertEqual(argv[2],'inspect');body=json.dumps([next(r for r in values if r['Id']==argv[-1])]).encode()
   return subprocess.CompletedProcess(argv,0,body,b'')
  rows=m.scan_networks(command,ipaddress.ip_network('10.231.240.0/24'))
  self.assertEqual([r['null_config'] for r in rows],[True,True,False])
  self.assertEqual(len(calls),4);self.assertFalse(any('create' in a for a in calls))
 def test_IPAM_malformed_types_subnets_and_overlap_still_reject(self):
  for config in [{},False,0,'bad',[None],[False],[{'Subnet':False}],[{'Subnet':0}],[{'Subnet':''}],[{'Subnet':'not-a-subnet'}],[{'Subnet':'10.0.0.1/24'}]]:
   with self.assertRaises((AssertionError,ValueError)):m.network_subnets({'IPAM':{'Config':config}})
  row={'Id':'a'*64,'Driver':'bridge','IPAM':{'Config':[{'Subnet':'10.231.0.0/16'}]}}
  def command(argv,**kw):return subprocess.CompletedProcess(argv,0,('a'*64).encode() if argv[2]=='ls' else json.dumps([row]).encode(),b'')
  with self.assertRaisesRegex(AssertionError,'overlaps'):m.scan_networks(command,ipaddress.ip_network('10.231.240.0/24'))
 def test_template_declares_new_adapter_transitive_shipped_service(self):
  path=Path(__file__).with_name('acme_platform_plan.py')
  spec=importlib.util.spec_from_file_location('recipe',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  self.assertIn('deploy/k8s/events.yaml',module.FILES)
  self.assertIn('tests/acme_platform_matrix.py',module.FILES)

if __name__=='__main__':unittest.main()
