"""Owned node readiness custody before app deployment, without cluster starts."""
import copy,json,stat,subprocess,tempfile,unittest
from pathlib import Path
from acme_platform_adapters import Kind
from kafka_oauth_custody import NamespaceLease

class Ready(unittest.TestCase):
 def fixture(self,path,change=None):
  value=Kind.__new__(Kind);value.work=path;value.node_id='a'*64;value.node='adhd-acme-owned-control-plane'
  value.kube_node_uid=None;value.node_readiness=[];value.kubeconfig_sha='bound'
  value.lease=NamespaceLease('adhd-final-owned','b'*32,prefix='adhd-final-')
  row={'metadata':{'name':value.node,'uid':'owned-node-uid'},'spec':{},'status':{'conditions':[{'type':'Ready','status':'True'},{'type':'DiskPressure','status':'False'}]}}
  if change:change(row)
  calls=[]
  def kubectl(*args,**kw):
   calls.append(args);self.assertEqual(args,('get','node',value.node,'-o','json'));self.assertTrue(kw['sensitive'])
   return subprocess.CompletedProcess(args,0,json.dumps(row).encode(),b'')
  value.kubectl=kubectl;return value,row,calls
 def test_ready_bound_uid_rechecked_and_private_raw_kept(self):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));first=value.ready_node();second=value.ready_node()
   self.assertEqual(first['uid'],second['uid']);self.assertEqual(len(calls),2)
   self.assertEqual(len(value.node_readiness),2)
   for path in Path(raw).iterdir():self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
 def test_unready_unschedulable_or_tainted_never_admitted(self):
  changes=[lambda r:r['status']['conditions'][0].update(status='False'),lambda r:r['status']['conditions'].clear(),
   lambda r:r['spec'].update(unschedulable=True),lambda r:r['spec'].update(unschedulable=0),
   lambda r:r['spec'].update(taints=[{'key':'node.kubernetes.io/not-ready','effect':'NoSchedule'}])]
  for change in changes:
   with tempfile.TemporaryDirectory() as raw:
    value,_,_=self.fixture(Path(raw),change)
    with self.assertRaises(AssertionError):value.ready_node()
    self.assertEqual(value.kube_node_uid,'owned-node-uid')
    self.assertEqual(len(value.node_readiness),1)
 def test_foreign_name_or_changed_uid_rejected(self):
  with tempfile.TemporaryDirectory() as raw:
   value,row,_=self.fixture(Path(raw));value.ready_node();row['metadata']['uid']='replacement-uid'
   with self.assertRaisesRegex(AssertionError,'UID changed'):value.ready_node()
  with tempfile.TemporaryDirectory() as raw:
   value,_,_=self.fixture(Path(raw),lambda r:r['metadata'].update(name='foreign'))
   with self.assertRaises(AssertionError):value.ready_node()
 def test_pre_namespace_diagnostics_capture_observed_node_only(self):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));value.ready_node()
   row['spec']['taints']=[{'key':'node.kubernetes.io/not-ready','effect':'NoSchedule','value':'private-secret'},
                         {'key':'private-secret','effect':'NoExecute'}]
   result=value.failure_diagnostics()
   self.assertTrue(result['attempted']);self.assertEqual(len(calls),2)
   self.assertFalse(value.lease.issued);self.assertIn('safe_node',result)
   self.assertNotIn('private-secret',json.dumps(result));self.assertEqual(result['safe_node']['taints'][0]['key'],'node.kubernetes.io/not-ready')
   self.assertEqual(result['safe_node']['taints'][1]['key'],'OTHER')
 def test_node_diagnostic_refuses_replaced_uid_before_namespace_reads(self):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));value.ready_node();value.lease.document()
   row['metadata']['uid']='replacement-uid'
   with self.assertRaisesRegex(AssertionError,'UID changed'):value.failure_diagnostics()
   self.assertEqual(len(calls),2)
 def test_start_fences_ready_before_and_after_image_load_without_rollout_extension(self):
  import inspect
  text=inspect.getsource(Kind.start)
  self.assertIn("'--wait','60s'",text);self.assertIn('timeout=180',text)
  self.assertEqual(text.count('self.ready_node()'),2)
  load=text.index("self.cmd(['kind','load'")
  self.assertLess(text.index('self.ready_node()'),load)
  self.assertGreater(text.rindex('self.ready_node()'),load)
  self.assertLess(text.rindex('self.ready_node()'),text.index('document=self.lease.document()'))
  self.assertIn("'--timeout=45s',timeout=50",text)

if __name__=='__main__':unittest.main()
