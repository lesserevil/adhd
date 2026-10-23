"""Owned node readiness custody before app deployment, without cluster starts."""
import copy,json,stat,subprocess,tempfile,unittest
from unittest.mock import patch
import acme_platform_adapters as adapters
from pathlib import Path
from acme_platform_adapters import Kind
from kafka_oauth_custody import NamespaceLease

class Ready(unittest.TestCase):
 def fixture(self,path,change=None):
  value=Kind.__new__(Kind);value.work=path;value.node_id='a'*64;value.node='adhd-acme-owned-control-plane'
  value.kube_node_uid=None;value.node_readiness=[];value.node_readiness_count=0;value.node_readiness_last=None;value.node_readiness_successes=[];value.kubeconfig_sha='bound'
  value.lease=NamespaceLease('adhd-final-owned','b'*32,prefix='adhd-final-')
  row={'metadata':{'name':value.node,'uid':'owned-node-uid'},'spec':{},'status':{'conditions':[{'type':'Ready','status':'True'},{'type':'DiskPressure','status':'False'}]}}
  if change:change(row)
  calls=[]
  def kubectl(*args,**kw):
   calls.append(args);self.assertEqual(args,('get','node',value.node,'-o','json'));self.assertTrue(kw['sensitive'])
   return subprocess.CompletedProcess(args,0,json.dumps(row).encode(),b'')
  value.kubectl=kubectl;return value,row,calls
 @patch.object(adapters.time,'monotonic',return_value=0)
 def test_ready_bound_uid_rechecked_and_private_raw_kept(self,_clock):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));first=value.ready_node(180);second=value.ready_node(180)
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
    with patch.object(adapters.time,'monotonic',side_effect=[0,180]),self.assertRaises(AssertionError):value.ready_node(180)
    self.assertEqual(value.kube_node_uid,'owned-node-uid')
    self.assertEqual(len(value.node_readiness),1)
 @patch.object(adapters.time,'monotonic',return_value=0)
 def test_foreign_name_or_changed_uid_rejected(self,_clock):
  with tempfile.TemporaryDirectory() as raw:
   value,row,_=self.fixture(Path(raw));value.ready_node(180);row['metadata']['uid']='replacement-uid'
   with self.assertRaisesRegex(AssertionError,'UID changed'):value.ready_node(180)
  with tempfile.TemporaryDirectory() as raw:
   value,_,_=self.fixture(Path(raw),lambda r:r['metadata'].update(name='foreign'))
   with self.assertRaises(AssertionError):value.ready_node(180)
 @patch.object(adapters.time,'monotonic',return_value=0)
 def test_pre_namespace_diagnostics_capture_observed_node_only(self,_clock):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));value.ready_node(180)
   row['spec']['taints']=[{'key':'node.kubernetes.io/not-ready','effect':'NoSchedule','value':'private-secret'},
                         {'key':'private-secret','effect':'NoExecute'}]
   result=value.failure_diagnostics()
   self.assertTrue(result['attempted']);self.assertEqual(len(calls),4)
   self.assertFalse(value.lease.issued);self.assertIn('safe_node',result)
   self.assertNotIn('private-secret',json.dumps(result));self.assertEqual(result['safe_node']['taints'][0]['key'],'node.kubernetes.io/not-ready')
   self.assertEqual(result['safe_node']['taints'][1]['key'],'OTHER')
 @patch.object(adapters.time,'monotonic',return_value=0)
 def test_node_diagnostic_refuses_replaced_uid_before_namespace_reads(self,_clock):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));value.ready_node(180);value.lease.document()
   row['metadata']['uid']='replacement-uid'
   with self.assertRaisesRegex(AssertionError,'UID changed'):value.failure_diagnostics()
   self.assertEqual(len(calls),2)
 def test_ready_with_stale_taint_then_clear_is_joint_readiness(self):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));row['spec']['taints']=[{'key':'node.kubernetes.io/not-ready','effect':'NoExecute'}]
   original=value.kubectl
   def read(*args,**kw):
    self.assertGreater(kw['timeout'],0);self.assertLessEqual(kw['timeout'],30)
    if calls:row['spec']['taints']=[]
    return original(*args,**kw)
   value.kubectl=read
   with patch.object(adapters.time,'monotonic',side_effect=[0,1,2,3]),patch.object(adapters.time,'sleep') as sleep:
    result=value.ready_node(180)
   self.assertEqual(len(calls),2);self.assertEqual(result['uid'],'owned-node-uid');self.assertEqual(result['taints'],[])
   self.assertEqual(value.node_readiness_count,2);self.assertTrue(value.node_readiness[0]['taints']);sleep.assert_called_once_with(.5)
   self.assertTrue(all(c[:2]==('get','node') for c in calls))
 def test_permanent_taint_exhausts_existing_deadline_no_apply(self):
  with tempfile.TemporaryDirectory() as raw:
   value,row,calls=self.fixture(Path(raw));row['spec']['taints']=[{'key':'node.kubernetes.io/not-ready','effect':'NoExecute'}]
   with patch.object(adapters.time,'monotonic',side_effect=[0,180]),self.assertRaisesRegex(AssertionError,'infrastructure deadline'):
    value.ready_node(180)
   self.assertEqual(len(calls),1);self.assertTrue(all(c[:2]==('get','node') for c in calls));self.assertFalse(value.lease.issued)
 def test_start_fences_ready_before_and_after_image_load_without_rollout_extension(self):
  import inspect
  text=inspect.getsource(Kind.start)
  self.assertIn("'--wait','60s'",text);self.assertIn('timeout=180',text)
  self.assertEqual(text.count('self.ready_node(bootstrap_deadline)'),2)
  load=text.index("self.cmd(['kind','load'")
  self.assertLess(text.index('self.ready_node(bootstrap_deadline)'),load)
  self.assertGreater(text.rindex('self.ready_node(bootstrap_deadline)'),load)
  self.assertLess(text.rindex('self.ready_node(bootstrap_deadline)'),text.index('document=self.lease.document()'))
  self.assertIn("'--timeout=45s',timeout=50",text)

if __name__=='__main__':unittest.main()
