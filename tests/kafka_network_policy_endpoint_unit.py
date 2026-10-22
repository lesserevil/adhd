"""Pure direct-endpoint ownership and TLS policy guards; zero sockets/processes."""
import importlib.util,unittest,base64
from pathlib import Path
from unittest.mock import patch,MagicMock
s=importlib.util.spec_from_file_location('endpoint',Path(__file__).with_name('kafka_network_policy_endpoint.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Guards(unittest.TestCase):
 def fixture(self):
  p={'node':'owned','cluster':'qa','network':'private','bridge_subnet':'10.240.240.0/24','node_image':{'configuration_digest':'sha256:pinned'}}
  n={'Id':'cid','Name':'/owned','State':{'Running':True},'Image':'sha256:pinned','Config':{'Labels':{'io.x-k8s.kind.cluster':'qa','io.x-k8s.kind.role':'control-plane'}},'NetworkSettings':{'Networks':{'private':{'NetworkID':'net','IPAddress':'10.240.240.2'}}}}
  a={'metadata':{'name':'owned','uid':'node-uid'},'status':{'addresses':[{'type':'InternalIP','address':'10.240.240.2'}]}}
  return p,n,a
 def test_exact_owned_ip_required(self):
  p,n,a=self.fixture();self.assertEqual(m.address_for(n,a,p,'cid','net'),'10.240.240.2');a['status']['addresses'][0]['address']='10.240.240.3'
  with self.assertRaises(AssertionError):m.address_for(n,a,p,'cid','net')
 def test_foreign_node_bridge_and_outside_subnet_denied(self):
  for mode in ['image','network','subnet']:
   p,n,a=self.fixture()
   if mode=='image':n['Image']='foreign'
   elif mode=='network':n['NetworkSettings']['Networks']['private']['NetworkID']='foreign'
   else:p['bridge_subnet']='10.0.0.0/24'
   with self.assertRaises(AssertionError):m.address_for(n,a,p,'cid','net')
 def test_no_proxy_or_tls_override_authority(self):
  c={'clusters':[{'name':'kind-qa','cluster':{'server':'https://127.0.0.1:1234','certificate-authority-data':base64.b64encode(b'-----BEGIN CERTIFICATE-----').decode()}}]}
  self.assertIn(b'CERTIFICATE',m.authority(c,'qa'));c['clusters'][0]['cluster']['insecure-skip-tls-verify']=True
  with self.assertRaises(AssertionError):m.authority(c,'qa')
 def test_exact_configmap_and_no_manifest_mutation(self):
  c=m.configmap('10.240.240.2','ns-uid','node-uid','a'*32)
  self.assertEqual(c['metadata']['name'],'kubernetes-services-endpoint');self.assertEqual(c['data'],{'KUBERNETES_SERVICE_HOST':'10.240.240.2','KUBERNETES_SERVICE_PORT':'6443'})
  self.assertEqual(c['metadata']['annotations']['adhd.policy/node-uid'],'node-uid')
 def test_inside_command_fixed_no_tls_bypass(self):
  argv=m.inside_command('a'*64,'10.240.240.2');self.assertIn('--server=https://10.240.240.2:6443',argv);self.assertIn('--request-timeout=10s',argv)
  self.assertNotIn('sh',argv);self.assertFalse(any('insecure'in x for x in argv))
  with self.assertRaises(AssertionError):m.inside_command('foreign','127.0.0.1')
 def test_tls_checks_remain_enabled(self):
  context=MagicMock(verify_mode=m.ssl.CERT_REQUIRED,check_hostname=True);secured=context.wrap_socket.return_value.__enter__.return_value;secured.getpeercert.return_value=b'leaf'
  with patch.object(m.ssl,'create_default_context',return_value=context),patch.object(m.socket,'create_connection',return_value=MagicMock())as connect:
   proof=m.verify_tls('10.240.240.2',b'CA');connect.assert_called_once_with(('10.240.240.2',6443),timeout=5)
  self.assertTrue(proof['verify_peer']);self.assertEqual(context.wrap_socket.call_args.kwargs['server_hostname'],'10.240.240.2')
class ControllerGuards(unittest.TestCase):
 def fixture(self):
  from copy import deepcopy
  expected={'kind':'Deployment','metadata':{'name':'calico-kube-controllers'},'spec':{'selector':{'matchLabels':{'k8s-app':'calico-kube-controllers'}},'template':{'metadata':{'labels':{'k8s-app':'calico-kube-controllers'}},'spec':{'containers':[{'name':'calico-kube-controllers','image':'pinned','env':[{'name':'DATASTORE_TYPE','value':'kubernetes'}]}]}}}}
  actual=deepcopy(expected);actual['metadata'].update(namespace='kube-system',uid='deployment-uid');actual['spec']['template']['spec']['containers'][0].update(terminationMessagePath='/dev/termination-log',terminationMessagePolicy='File')
  proof={'address':'10.240.240.2','namespace_uid':'ns-uid','node_uid':'node-uid','owner_nonce':'a'*32,'configmap_uid':'cm-uid'}
  cm=m.configmap(proof['address'],proof['namespace_uid'],proof['node_uid'],proof['owner_nonce']);cm['metadata']['uid']='cm-uid'
  return actual,expected,cm,proof
 def test_atomic_patch_preserves_containers_and_tests_uid(self):
  from copy import deepcopy
  actual,expected,cm,proof=self.fixture();before=deepcopy(actual);patch=m.controller_patch(actual,expected,cm,proof)
  self.assertEqual(actual,before);self.assertEqual([p['op']for p in patch],['test','test','add']);self.assertEqual(patch[0]['value'],'deployment-uid');self.assertEqual(patch[1]['value'],actual['spec']['template']['spec']['containers']);self.assertEqual(patch[2]['path'],'/spec/template/spec/containers/0/envFrom')
 def test_only_exact_api_probe_defaults_allowed(self):
  actual,expected,cm,proof=self.fixture();a=actual['spec']['template']['spec']['containers'][0];e=expected['spec']['template']['spec']['containers'][0]
  e['readinessProbe']={'exec':{'command':['health']},'periodSeconds':10};a['readinessProbe']={'exec':{'command':['health']},'periodSeconds':10,'failureThreshold':3,'successThreshold':1,'timeoutSeconds':1};a['resources']={}
  self.assertEqual(len(m.controller_patch(actual,expected,cm,proof)),3);a['readinessProbe']['timeoutSeconds']=2
  with self.assertRaises(AssertionError):m.controller_patch(actual,expected,cm,proof)
 def test_foreign_existing_env_and_wrong_configmap_rejected(self):
  for defect in ['namespace','name','image','envFrom','env','extra','configmap_uid','nonce','node','address']:
   actual,expected,cm,proof=self.fixture();c=actual['spec']['template']['spec']['containers'][0]
   if defect=='namespace':actual['metadata']['namespace']='other'
   elif defect=='name':actual['metadata']['name']='other'
   elif defect=='image':c['image']='foreign'
   elif defect=='envFrom':c['envFrom']=[]
   elif defect=='env':c['env']=[]
   elif defect=='extra':actual['spec']['template']['spec']['containers'].append(dict(c))
   elif defect=='configmap_uid':cm['metadata']['uid']='other'
   elif defect=='nonce':cm['metadata']['labels']['adhd-policy-owner']='b'*32
   elif defect=='node':cm['metadata']['annotations']['adhd.policy/node-uid']='foreign'
   else:cm['data']['KUBERNETES_SERVICE_HOST']='10.240.240.3'
   with self.assertRaises(AssertionError,msg=defect):m.controller_patch(actual,expected,cm,proof)

if __name__=='__main__':unittest.main()
