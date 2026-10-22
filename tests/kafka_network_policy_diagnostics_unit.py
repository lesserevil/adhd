"""Pure diagnostics ownership, deadline and failure guards: no child starts."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import json

spec=importlib.util.spec_from_file_location('diagnostics',Path(__file__).with_name('kafka_network_policy_diagnostics.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name).resolve();self.session=d.Diagnostics(self.root/'private',['kubectl'],{},self.root,'owned-node',lambda timeout,cap:0)
 def test_owner_requires_controller_kind_and_uid(self):
  obj={'metadata':{'ownerReferences':[{'uid':'a','kind':'DaemonSet','controller':True}]}}
  self.assertTrue(d.owner(obj,'a','DaemonSet'));self.assertFalse(d.owner(obj,'b','DaemonSet'));self.assertFalse(d.owner(obj,'a','ReplicaSet'))
  obj['metadata']['ownerReferences'][0]['controller']=False;self.assertFalse(d.owner(obj,'a','DaemonSet'))
 def test_actual_pinned_five_container_template(self):
  expected=['upgrade-ipam','cni-plugins','install-cni','ebpf-bootstrap','calico-node']
  pod={'spec':{'initContainers':[{'name':n}for n in expected[:4]],'containers':[{'name':'calico-node'}]}}
  self.assertEqual(d.EXPECTED_CONTAINERS['calico-node'],tuple(expected))
  self.assertEqual(d.container_names(pod,{'containers':expected}),expected)
 def test_six_container_even_expanded_pin_denied(self):
  names=list(d.EXPECTED_CONTAINERS['calico-node'])+['extra']
  with self.assertRaises(AssertionError):d.container_names({'spec':{'containers':[{'name':n}for n in names]}},{'containers':names})
 def test_duplicate_container_or_foreign_name_denied(self):
  for names in [['calico-node','calico-node'],['foreign']]:
   with self.assertRaises(AssertionError):d.container_names({'spec':{'containers':[{'name':n}for n in names]}},{'containers':d.EXPECTED_CONTAINERS['calico-node']})
 def test_closed_fixed_limits(self):
  self.assertEqual(d.LIMITS['anchor_seconds']+d.LIMITS['capture_seconds'],90)
  self.assertEqual(d.LIMITS['command_seconds'],10);self.assertEqual(d.LIMITS['total_bytes'],8*1024*1024)
  self.assertEqual(d.LIMITS['log_requests'],16)
 def test_custody_and_api_output_share_same_aggregate_cap(self):
  self.session.phase(10);self.session.fence=lambda timeout,cap:3
  with patch.dict(d.LIMITS,total_bytes=10),patch.object(d,'bounded',return_value=(0,b'{}',b'')) as run:
   self.assertEqual(self.session.call('budget',[]),{})
   self.assertEqual(run.call_args.args[-1],7)
   self.assertEqual(self.session.used,8)
 def test_deadline_prevents_command(self):
  self.session.phase(0)
  with patch.object(d,'bounded') as run:
   with self.assertRaises(AssertionError):self.session.call('expired',[])
   run.assert_not_called()
 def test_foreign_fence_prevents_command(self):
  self.session.phase(10);self.session.fence=MagicMock(side_effect=AssertionError('foreign node'))
  with patch.object(d,'bounded') as run:
   with self.assertRaises(AssertionError):self.session.call('foreign',[])
   run.assert_not_called()
 def test_partial_failure_private_and_preserved(self):
  self.session.phase(10);error=TimeoutError();error.diagnostic_partial=(b'partial',b'error')
  with patch.object(d,'bounded',side_effect=error):
   with self.assertRaises(TimeoutError):self.session.call('bounded',[])
  self.assertEqual(self.session.used,12);self.assertEqual(self.session.rows[0]['error_type'],'TimeoutError')
  for p in self.session.root.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
 def test_nonzero_exit_not_ownership_error(self):
  self.session.phase(10)
  with patch.object(d,'bounded',return_value=(1,b'',b'unavailable')):
   with self.assertRaises(d.CommandUnavailable):self.session.call('unavailable',[])
  self.assertFalse(self.session.rows[0]['passed'])
 def test_pod_namespace_uid_must_match(self):
  self.session.pins={'namespace':'old','node':'node','controllers':{}}
  with patch.object(self.session,'call',return_value={'metadata':{'name':'kube-system','uid':'foreign'}}) as call:
   with self.assertRaises(AssertionError):self.session.capture()
   self.assertEqual(call.call_count,1)
 def test_no_logs_for_foreign_owner(self):
  self.session.pins={'namespace':'ns','node':'n','controllers':{'calico-node':{'uid':'c','kind':'daemonset','object_kind':'DaemonSet','containers':['calico-node']}}}
  responses=[{'metadata':{'name':'kube-system','uid':'ns'}},{'metadata':{'name':'owned-node','uid':'n'}},{'metadata':{'namespace':'kube-system','name':'calico-node','uid':'c'}},{'items':[{'metadata':{'namespace':'kube-system','name':'pod','uid':'p','labels':{'k8s-app':'calico-node'},'ownerReferences':[{'uid':'foreign','kind':'DaemonSet','controller':True}]},'spec':{'nodeName':'owned-node'}}]}]
  with patch.object(self.session,'call',side_effect=responses) as call:
   with self.assertRaises(AssertionError):self.session.capture()
   self.assertEqual(call.call_count,4)
 def test_size_cap_kills_and_joins_owned_process(self):
  child=MagicMock(pid=123);child.poll.return_value=None
  selector=MagicMock();selector.__enter__.return_value=selector
  key=MagicMock();key.fileobj=child.stdout;key.data=0
  selector.get_map.return_value={'pipe':key};selector.select.return_value=[(key,1)]
  with patch.object(d.subprocess,'Popen',return_value=child),patch.object(d.selectors,'DefaultSelector',return_value=selector),patch.object(d.os,'set_blocking'),patch.object(d.os,'read',return_value=b'abcd'),patch.object(d.os,'getpgid',return_value=123),patch.object(d.os,'killpg') as kill:
   with self.assertRaises(ValueError) as error:d.bounded(['never'],{},self.root,1,3)
   self.assertEqual(error.exception.diagnostic_partial,(b'abc',b''));kill.assert_called_once_with(123,d.signal.SIGKILL);child.wait.assert_called_once()
 def test_original_rollout_failure_survives_capture_failure(self):
  original=AssertionError('original300s rollout')
  def rollout():raise original
  diagnostic=MagicMock();diagnostic.capture.side_effect=TimeoutError('bounded diagnostics')
  with self.assertRaises(AssertionError) as error:d.observe_rollout(rollout,diagnostic)
  self.assertIs(error.exception,original);self.assertEqual(diagnostic.capture_error,'TimeoutError')
  diagnostic.capture.assert_called_once()
 def test_capture_failure_not_labeled_success_on_ready_bootstrap(self):
  diagnostic=MagicMock();diagnostic.capture.side_effect=ValueError('output cap')
  with self.assertRaises(ValueError):d.observe_rollout(lambda:None,diagnostic)
 def test_metadata_identity_requires_namespace(self):
  with self.assertRaises(AssertionError):d.named({'metadata':{'name':'pod','uid':'x','namespace':'foreign'}},'pod','kube-system')

if __name__=='__main__':unittest.main()
