"""Pure local-path infrastructure gates; no cluster, apps or PVC probes."""
import copy,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import acme_platform_adapters as adapters
from acme_platform_adapters import Kind

class Storage(unittest.TestCase):
 def fixture(self,path):
  value=Kind.__new__(Kind);value.work=path;value.node_id='a'*64;value.node='owned-control-plane';value.kube_node_uid='node-uid'
  value.system_uids={};value.storage_readiness=[];value.storage_readiness_count=0;value.storage_readiness_last=None
  namespace={'kind':'Namespace','metadata':{'name':'local-path-storage','uid':'storage-ns'},'status':{'phase':'Active'}}
  deployment={'kind':'Deployment','metadata':{'name':'local-path-provisioner','namespace':'local-path-storage','uid':'controller-uid','generation':2},'spec':{'replicas':1},'status':{'observedGeneration':2,'replicas':1,'updatedReplicas':1,'readyReplicas':1,'availableReplicas':1}}
  node={'metadata':{'name':value.node,'uid':'node-uid'},'spec':{},'status':{'conditions':[{'type':'Ready','status':'True'}]}}
  calls=[]
  def kubectl(*args,**kw):
   calls.append(args);self.assertTrue(kw['sensitive']);self.assertGreater(kw['timeout'],0);self.assertLessEqual(kw['timeout'],30)
   body=namespace if args[:2]==('get','namespace') else node if args[:2]==('get','node') else deployment
   return subprocess.CompletedProcess(args,0,json.dumps(body).encode(),b'')
  value.kubectl=kubectl;return value,namespace,deployment,node,calls
 def test_current_ready_generation_then_same_node_no_pvc_or_apply(self):
  with tempfile.TemporaryDirectory() as raw,patch.object(adapters.time,'monotonic',return_value=0):
   value,_,_,_,calls=self.fixture(Path(raw));summary=value.ready_storage(180)
   self.assertTrue(summary['ready']);self.assertEqual(len(calls),3);self.assertEqual(calls[-1],('get','node',value.node,'-o','json'))
   self.assertFalse(any('pvc' in c or 'apply' in c for c in calls));self.assertEqual(value.storage_readiness_count,1)
 def test_stale_generation_and_false_replica_availability_timeout(self):
  for field,bad in [('observedGeneration',1),('readyReplicas',0),('availableReplicas',0),('updatedReplicas',0),('replicas',2),('unavailableReplicas',1)]:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as raw:
    value,_,dep,_,calls=self.fixture(Path(raw));dep['status'][field]=bad
    with patch.object(adapters.time,'monotonic',side_effect=[0,0,180]),self.assertRaisesRegex(AssertionError,'infrastructure deadline'):value.ready_storage(180)
    self.assertEqual(len(calls),2);self.assertFalse(value.storage_readiness_last['ready'])
 def test_pending_then_current_ready_with_same_bound_uids(self):
  with tempfile.TemporaryDirectory() as raw,patch.object(adapters.time,'monotonic',return_value=0),patch.object(adapters.time,'sleep'):
   value,_,dep,_,calls=self.fixture(Path(raw));dep['status']['readyReplicas']=0;original=value.kubectl
   def read(*args,**kw):
    if len(calls)>=2:dep['status']['readyReplicas']=1
    return original(*args,**kw)
   value.kubectl=read;self.assertTrue(value.ready_storage(180)['ready']);self.assertEqual(value.storage_readiness_count,2)
 def test_changed_namespace_or_controller_uid_blocks_dependents(self):
  for target in ('namespace','controller'):
   with tempfile.TemporaryDirectory() as raw,patch.object(adapters.time,'monotonic',return_value=0):
    value,ns,dep,_,calls=self.fixture(Path(raw));value.ready_storage(180);calls.clear()
    (ns if target=='namespace' else dep)['metadata']['uid']='foreign'
    with self.assertRaisesRegex(AssertionError,'UID changed'):value.ready_storage(180)
    self.assertEqual(len(calls),1 if target=='namespace' else 2)
 def test_foreign_node_after_controller_ready_refused(self):
  with tempfile.TemporaryDirectory() as raw,patch.object(adapters.time,'monotonic',return_value=0):
   value,_,_,node,_=self.fixture(Path(raw));node['metadata']['uid']='foreign'
   with self.assertRaisesRegex(AssertionError,'UID changed'):value.ready_storage(180)
 def test_expired_budget_issues_no_query_or_namespace(self):
  with tempfile.TemporaryDirectory() as raw,patch.object(adapters.time,'monotonic',return_value=180):
   value,_,_,_,calls=self.fixture(Path(raw))
   with self.assertRaisesRegex(AssertionError,'infrastructure deadline'):value.ready_storage(180)
   self.assertEqual(calls,[])
 def test_boolean_or_float_counts_rejected(self):
  for bad in (True,1.0):
   with tempfile.TemporaryDirectory() as raw:
    value,_,dep,_,_=self.fixture(Path(raw));dep['status']['readyReplicas']=bad
    with self.assertRaises(AssertionError):value.storage_summary(dep)
 def test_fence_precedes_namespace_and_does_not_change_rollout(self):
  import inspect
  source=inspect.getsource(Kind.start)
  self.assertLess(source.index('self.ready_storage(bootstrap_deadline)'),source.index('document=self.lease.document()'))
  self.assertIn("'--timeout=45s',timeout=50",source);self.assertIn('bootstrap_deadline=time.monotonic()+180',source)


class SystemDiagnostics(unittest.TestCase):
 def fixture(self,foreign=False):
  value=Kind.__new__(Kind);value.node_id='a'*64;value.node='owned-control-plane';value.kube_node_uid='node-uid';value.system_uids={('Namespace',None,'local-path-storage'):'storage-ns'}
  calls=[];pods={}
  def fetch(label,args):
   calls.append((label,args))
   ns='local-path-storage' if label.startswith('storage') else 'kube-system'
   if 'namespace' in label:
    body={'kind':'Namespace','metadata':{'name':ns,'uid':('foreign' if foreign else 'storage-ns') if ns=='local-path-storage' else 'system-ns'}}
   elif label=='storage-controller':
    body={'kind':'Deployment','metadata':{'name':'local-path-provisioner','namespace':ns,'uid':'controller-uid','generation':1},'spec':{'replicas':1},'status':{'observedGeneration':1,'replicas':1,'updatedReplicas':1,'readyReplicas':1,'availableReplicas':1}}
   elif label.endswith('-pods'):
    name='local-path-provisioner-owned' if ns=='local-path-storage' else 'kube-scheduler-'+value.node
    pod={'kind':'Pod','metadata':{'name':name,'namespace':ns,'uid':ns+'-pod','labels':{'app':'local-path-provisioner'}},'spec':{'nodeName':value.node,'containers':[{'name':'controller'}]},'status':{'phase':'Running','message':'private-secret'}}
    pods[ns]=pod;body={'items':[pod]}
   elif '-pod-' in label:body=pods[ns]
   elif label.endswith('-events'):body={'items':[{'reason':'ProvisioningFailed','message':'private-secret'},{'reason':'private-secret'}]}
   else:return subprocess.CompletedProcess(args,0,b'private-secret',b'')
   return subprocess.CompletedProcess(args,0,json.dumps(body).encode(),b'')
  return value,fetch,calls
 def test_controller_helpers_and_scheduler_uid_bound_logs_safe_summary(self):
  value,fetch,calls=self.fixture();result={'errors':[]};value.system_diagnostics(fetch,result)
  self.assertFalse(result['errors']);self.assertEqual(len(result['system']['pods']),2)
  self.assertNotIn('private-secret',json.dumps(result));self.assertIn('OTHER',result['system']['event_reasons'])
  for prefix in ('storage','scheduler'):
   labels=[label for label,args in calls]
   self.assertLess(labels.index(prefix+'-namespace'),labels.index(prefix+'-pods'))
   self.assertLess(labels.index(prefix+'-pod-0'),labels.index(prefix+'-log-0-0'))
   self.assertGreater(labels.index(prefix+'-pod-after-0'),labels.index(prefix+'-log-0-0'))
 def test_foreign_namespace_blocks_all_dependent_controller_pod_event_log_queries(self):
  value,fetch,calls=self.fixture(foreign=True);result={'errors':[]};value.system_diagnostics(fetch,result)
  self.assertEqual([l for l,a in calls if l.startswith('storage')],['storage-namespace'])
  self.assertEqual(result['errors'][0],{'label':'storage-diagnostics','failure_type':'AssertionError'})
 def test_foreign_pod_uid_blocks_logs_and_retains_failure(self):
  value,fetch,calls=self.fixture();result={'errors':[]}
  def changed(label,args):
   response=fetch(label,args)
   if label=='storage-pod-0':
    body=json.loads(response.stdout);body['metadata']['uid']='foreign';response.stdout=json.dumps(body).encode()
   return response
  value.system_diagnostics(changed,result)
  self.assertFalse(any(l.startswith('storage-log') for l,a in calls));self.assertIn({'label':'storage-pod-log','failure_type':'AssertionError'},result['errors'])
 def test_deadline_failure_stays_failed_no_logs_and_independent_attempts_bounded_by_fetch(self):
  value,_,_=self.fixture();calls=[];result={'errors':[]}
  def expired(label,args):calls.append(label);raise AssertionError('Diagnostic deadline')
  value.system_diagnostics(expired,result)
  self.assertEqual(calls,['storage-namespace','scheduler-namespace']);self.assertEqual(len(result['errors']),2)

if __name__=='__main__':unittest.main()
