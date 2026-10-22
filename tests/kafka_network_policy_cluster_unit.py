"""No runtime or provider calls: executor admission, identity and failure cleanup."""
import importlib.util
import json
import runpy
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch,MagicMock
s=importlib.util.spec_from_file_location('gate',Path(__file__).with_name('kafka_network_policy_cluster.py'));g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class Guards(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
 def tearDown(self):self.temp.cleanup()
 def plan(self):return {'cluster':'adhd-netpol-qa40','network':'adhd-netpol-qa40-net','node':'adhd-netpol-qa40-control-plane','owner_label':'owner','owner_nonce':'nonce','bridge_subnet':'10.240.240.0/24','node_image':{'configuration_digest':'sha256:node'},'tools':{'python':{'path':'/test/python'},'docker':{'path':'/test/docker'}},'docker_socket':{'path':'/test/socket'}}
 def test_direct_endpoint_uid_mismatch_prevents_configmap_creation(self):
  import base64
  import kafka_network_policy_endpoint as endpoint
  p=self.plan();runner=g.Executor(self.root,p);runner.known_node='a'*64;runner.known_network='net'
  p.update(diagnostic_only=True,direct_api_endpoint={'mode':'owned-node-InternalIP','port':6443,'require_peer_hostname_tls':True,'read_preflight_only_before_configmap':True})
  runtime=self.root/'runtime';runtime.mkdir()
  Path(runner.env['KUBECONFIG']).write_text(json.dumps({'clusters':[{'name':'kind-'+p['cluster'],'cluster':{'server':'https://127.0.0.1:1','certificate-authority-data':base64.b64encode(b'-----BEGIN CERTIFICATE-----').decode()}}]}))
  node={'Id':runner.known_node,'Name':'/'+p['node'],'State':{'Running':True},'Image':'sha256:node','Config':{'Labels':{'io.x-k8s.kind.cluster':p['cluster'],'io.x-k8s.kind.role':'control-plane'}},'NetworkSettings':{'Networks':{p['network']:{'NetworkID':'net','IPAddress':'10.240.240.2'}}}}
  api={'metadata':{'name':p['node'],'uid':'node-uid'},'status':{'addresses':[{'type':'InternalIP','address':'10.240.240.2'}]}}
  ns={'metadata':{'name':'kube-system','uid':'ns-uid'}};seen=[]
  def run(name,args,**kw):
   seen.append(name);value=api if name in ['endpoint-node','endpoint-direct-node'] else ns
   return subprocess.CompletedProcess([],0,json.dumps(value).encode(),b'')
  with patch.object(runner,'inspect',return_value=node),patch.object(runner,'node_owned'),patch.object(runner,'network_owned'),patch.object(runner,'run',side_effect=run),patch.object(runner,'docker',return_value=subprocess.CompletedProcess([],0,b'{"metadata":{"uid":"foreign"}}',b'')),patch.object(endpoint,'verify_tls',return_value={'verified':True}):
   with self.assertRaises(AssertionError):runner.install_direct_api_endpoint(['kubectl'])
  self.assertNotIn('create-direct-api-configmap',seen)
  self.assertFalse((runtime/'direct-api-configmap.json').exists())
 def test_stream_command_fixed_namespace_targets(self):
  for index in range(3):
   command,target=g.stream_command('a'*64,index)
   self.assertEqual(command[:4],['exec','-i','a'*64,'sh'])
   self.assertEqual(target,'/var/lib/adhd-policy-oci/'+str(index)+'.oci.tar')
   self.assertEqual(command[-1],target);self.assertIn('set -C',g.CNI_STREAM_SCRIPT)
   self.assertNotIn('/tmp',target);self.assertNotIn('eval ',g.CNI_STREAM_SCRIPT)
  for node,index in [('foreign',0),('a'*64,3),('a'*64,True),('a'*64,'0')]:
   with self.assertRaises(AssertionError):g.stream_command(node,index)
 def test_stream_stdin_uses_bounded_communicate(self):
  (self.root/'runtime').mkdir();runner=g.Executor(self.root,self.plan());child=MagicMock();child.pid=321;child.returncode=0;child.communicate.return_value=(b'ok',b'')
  with patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen',return_value=child) as process:
   runner.run('stream',['docker','exec','-i','owned'],timeout=300,data=b'archive')
  self.assertEqual(process.call_args.kwargs['stdin'],g.subprocess.PIPE)
  child.communicate.assert_called_once_with(input=b'archive',timeout=300)
  self.assertEqual(runner.events[0]['input_bytes'],7);self.assertIn('intended stdin',runner.events[0]['input_observation'])
 def test_stream_timeout_never_resends_input_and_joins_child(self):
  (self.root/'runtime').mkdir();runner=g.Executor(self.root,self.plan());child=MagicMock();child.pid=321;child.returncode=-9;child.poll.return_value=None
  child.communicate.side_effect=[g.subprocess.TimeoutExpired(['docker'],300,output=b'partial',stderr=b'err'),(b'partial',b'err')]
  with patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen',return_value=child),patch.object(g.os,'getpgid',return_value=321),patch.object(g.os,'killpg') as kill:
   with self.assertRaises(g.subprocess.TimeoutExpired):runner.run('stream',['docker'],timeout=300,data=b'archive')
  self.assertEqual(child.communicate.call_count,2);self.assertEqual(child.communicate.call_args.kwargs,{'timeout':15});kill.assert_called_once_with(321,g.signal.SIGKILL)
  self.assertTrue(runner.events[0]['owned_client_joined_after_failure']);self.assertEqual(runner.events[0]['returncode'],-9)
 def test_exact_tree(self):
  (self.root/'a').write_text('x');v=g.inventory(self.root);(self.root/'empty').mkdir();self.assertNotEqual(g.inventory(self.root),v)
  (self.root/'alias').symlink_to(self.root/'empty',target_is_directory=True)
  with self.assertRaises(AssertionError):g.inventory(self.root)
 def test_strict_absence(self):
  cp=lambda rc,out,err:subprocess.CompletedProcess([],rc,out,err)
  self.assertTrue(g.absent(cp(1,b'[]',b'error: no such object: Name'),'Name'))
  self.assertTrue(g.absent(cp(1,b'[]',b'Error response from daemon: network Name not found'),'Name',True))
  for result in [cp(1,b'[{}]',b'error: no such object: Name'),cp(1,b'',b'error: no such object: name'),cp(2,b'',b'error: no such object: Name'),cp(1,b'',b'daemon failed')]:self.assertFalse(g.absent(result,'Name'))
  self.assertFalse(g.absent(cp(1,b'[]',b'Error response from daemon: network name not found'),'Name',True))
 def test_node_ownership(self):
  p=self.plan();runner=g.Executor(self.root,p);runner.known_network='net'
  row={'Name':'/'+p['node'],'Id':'id','Image':'sha256:node','Config':{'Labels':{'io.x-k8s.kind.cluster':p['cluster'],'io.x-k8s.kind.role':'control-plane'}},'NetworkSettings':{'Networks':{p['network']:{'NetworkID':'net'}}}}
  self.assertEqual(runner.node_owned(row),'id');row['Image']='foreign'
  with self.assertRaises(AssertionError):runner.node_owned(row)
 def test_network_ownership(self):
  p=self.plan();runner=g.Executor(self.root,p);row={'Name':p['network'],'Driver':'bridge','Labels':{'owner':'nonce'},'IPAM':{'Config':[{'Subnet':p['bridge_subnet']}]},'Id':'network'}
  self.assertEqual(runner.network_owned(row),'network');row['Labels']['owner']='other'
  with self.assertRaises(AssertionError):runner.network_owned(row)
 def test_known_id_inspect_failure_independent_remove_and_absence(self):
  runner=g.Executor(self.root,self.plan());runner.node_issued=True;runner.known_node='owned';calls=[]
  def docker(*args,**kwargs):calls.append(args);return subprocess.CompletedProcess([],0,b'',b'')
  with patch.object(runner,'inspect',side_effect=[OSError('daemon'),None,None]),patch.object(runner,'docker',side_effect=docker):errors=runner.finish()
  self.assertTrue(errors);self.assertEqual(calls,[('fallback-remove-node','rm','--force','owned')]);self.assertTrue(runner.cleanup[0]['observed_absent'])
 def test_positive_foreign_never_removed(self):
  runner=g.Executor(self.root,self.plan());runner.node_issued=True;runner.known_node='owned'
  with patch.object(runner,'inspect',return_value={'Image':'foreign'}),patch.object(runner,'node_owned',side_effect=AssertionError('foreign')),patch.object(runner,'docker') as docker:errors=runner.finish()
  self.assertTrue(errors);docker.assert_not_called();self.assertFalse(runner.cleanup[0]['observed_absent']);self.assertTrue(runner.cleanup[0]['foreign_object_not_removed'])
 def test_network_cleanup_cannot_remove_busy_network(self):
  runner=g.Executor(self.root,self.plan());runner.network_issued=True;runner.known_network='ownednet'
  # Even fallback network-rm is non-force; Docker itself refuses active endpoints.
  with patch.object(runner,'inspect',side_effect=[OSError('daemon'),{'Id':'ownednet'}, {'Id':'ownednet'}]),patch.object(runner,'docker',return_value=subprocess.CompletedProcess([],1,b'',b'active endpoints')) as docker:errors=runner.finish()
  self.assertTrue(errors);self.assertEqual(docker.call_args.args,('fallback-remove-network','network','rm','ownednet'));self.assertFalse(runner.cleanup[0]['observed_absent'])
 def fixture(self):
  plan=dict(self.plan(),lane_lock=str(self.root/'lock'),driver_sha256='d',scope='pure',image='sha256:app');g.save(self.root/'plan.json',plan);return g.sha(self.root/'plan.json')
 def test_once_before_any_operation(self):
  digest=self.fixture()
  with patch.object(g,'verify',return_value=True),patch.object(g.Executor,'perform',side_effect=OSError('mock')) as operation,patch.object(g.Executor,'finish',return_value=[]):
   with self.assertRaises(OSError):g.execute(self.root,digest)
   with self.assertRaises(FileExistsError):g.execute(self.root,digest)
   self.assertEqual(operation.call_count,1)
  result=json.loads((self.root/'result.json').read_text());self.assertFalse(result['passed']);self.assertEqual(result['failure_type'],'OSError')
 def test_protected_comparison_after_failed_perform(self):
  digest=self.fixture()
  def fail(runner):runner.protected_before={'original':True};raise OSError('mock')
  with patch.object(g,'verify',return_value=True),patch.object(g.Executor,'perform',fail),patch.object(g.Executor,'finish',return_value=[]),patch.object(g.Executor,'protected',return_value={'original':False}) as check:
   with self.assertRaises(OSError):g.execute(self.root,digest)
   self.assertEqual(check.call_count,1)
  self.assertIn('AssertionError',json.loads((self.root/'result.json').read_text())['cleanup_failure_types'])
 def test_authored_execute_denied_before_any_process(self):
  with patch.object(sys,'argv',['source','--execute']),patch.object(g.subprocess,'Popen',side_effect=AssertionError('No process')) as process:
   with self.assertRaises(AssertionError):runpy.run_path(str(Path(__file__).with_name('kafka_network_policy_cluster.py')),run_name='__main__')
   process.assert_not_called()
 def test_command_creation_error_not_started(self):
  (self.root/'runtime').mkdir();runner=g.Executor(self.root,self.plan())
  with patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen',side_effect=OSError('mock')):
   with self.assertRaises(OSError):runner.run('mock',['never'])
  self.assertFalse(runner.events[0]['started']);self.assertEqual(runner.events[0]['error_type'],'OSError')
 def test_timeout_owned_group_killed_joined_primary_retained(self):
  from unittest.mock import Mock
  (self.root/'runtime').mkdir();runner=g.Executor(self.root,self.plan());child=Mock(pid=123456,returncode=-9);child.poll.return_value=None;child.communicate.side_effect=[subprocess.TimeoutExpired(['mock'],1),(b'out',b'err')]
  with patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen',return_value=child),patch.object(g.os,'getpgid',return_value=123456),patch.object(g.os,'killpg') as kill:
   with self.assertRaises(subprocess.TimeoutExpired):runner.run('mock',['never'],timeout=1)
   kill.assert_called_once_with(123456,g.signal.SIGKILL)
  self.assertTrue(runner.events[0]['started']);self.assertTrue(runner.events[0]['owned_client_joined_after_failure']);self.assertEqual(runner.events[0]['returncode'],-9)
 def test_changed_kubeconfig_rejected_before_process(self):
  (self.root/'runtime').mkdir();runner=g.Executor(self.root,self.plan());f=self.root/'runtime/owned.kubeconfig';f.write_text('before');runner.kubeconfig_sha256=g.sha(f);f.write_text('after')
  with patch.object(g,'verify',return_value=True),patch.object(g.subprocess,'Popen') as process:
   with self.assertRaises(AssertionError):runner.run('mock',['never'])
   process.assert_not_called()
 def test_fresh_anonymous_volume_bound_to_owned_node(self):
  runner=g.Executor(self.root,dict(self.plan(),node_anonymous_volume_destinations=['/var']));runner.preexisting_volumes={'other'};name='a'*64
  row={'Config':{'Volumes':{'/var':{}}},'HostConfig':{'Binds':['/lib/modules:/lib/modules:ro']},'Mounts':[{'Type':'volume','Name':name,'Driver':'local','Destination':'/var','Source':'/vol/'+name}]}
  volume={'Name':name,'Driver':'local','Scope':'local','CreatedAt':'now','Mountpoint':'/vol/'+name,'Labels':{'com.docker.volume.anonymous':''},'Options':None}
  with patch.object(runner,'node_owned',return_value='node'),patch.object(runner,'docker',return_value=subprocess.CompletedProcess([],0,json.dumps([volume]).encode())):
   runner.capture_volumes(row);self.assertTrue(runner.volumes_verified);self.assertEqual(runner.owned_volumes[0]['name'],name)
   runner.preexisting_volumes.add(name)
   with self.assertRaises(AssertionError):runner.capture_volumes(row)
   self.assertFalse(runner.volumes_verified)
 def test_named_volume_request_rejected(self):
  runner=g.Executor(self.root,dict(self.plan(),node_anonymous_volume_destinations=['/var']));runner.preexisting_volumes=set()
  with patch.object(runner,'node_owned',return_value='node'),patch.object(runner,'docker') as docker:
   with self.assertRaises(AssertionError):runner.capture_volumes({'Config':{'Volumes':{'/var':{}}},'HostConfig':{'Binds':['named:/var']},'Mounts':[]})
   docker.assert_not_called();self.assertFalse(runner.volumes_verified)
 def test_missing_anonymous_label_or_external_options_rejected(self):
  name='a'*64
  row={'Config':{'Volumes':{'/var':{}}},'Mounts':[{'Type':'volume','Name':name,'Driver':'local','Destination':'/var','Source':'/vol/'+name}]}
  for changes in [{'Labels':{}},{'Options':{'device':'foreign'}}]:
   runner=g.Executor(self.root,dict(self.plan(),node_anonymous_volume_destinations=['/var']));runner.preexisting_volumes=set()
   volume={'Name':name,'Driver':'local','Scope':'local','CreatedAt':'now','Mountpoint':'/vol/'+name,'Labels':{'com.docker.volume.anonymous':''},'Options':None,**changes}
   with patch.object(runner,'node_owned',return_value='node'),patch.object(runner,'docker',return_value=subprocess.CompletedProcess([],0,json.dumps([volume]).encode())):
    with self.assertRaises(AssertionError):runner.capture_volumes(row)
   self.assertFalse(runner.volumes_verified)
 def test_verified_known_volume_cleanup_flags_and_strict_absence(self):
  runner=g.Executor(self.root,self.plan());runner.node_issued=True;runner.known_node='owned';runner.volumes_verified=True;runner.volume_candidates={'a'*64};calls=[]
  missing=subprocess.CompletedProcess([],1,b'[]',('Error response from daemon: get '+'a'*64+': no such volume').encode())
  def docker(*args,**kwargs):calls.append(args);return missing if args[0]=='verify-volume-absence' else subprocess.CompletedProcess([],0,b'',b'')
  with patch.object(runner,'inspect',side_effect=[OSError('daemon'),None,None]),patch.object(runner,'docker',side_effect=docker):errors=runner.finish()
  self.assertTrue(errors);self.assertEqual(calls[0],('fallback-remove-node','rm','--force','--volumes','owned'));self.assertTrue(runner.cleanup[-1]['observed_absent'])
 def test_volume_absence_not_mixed_or_casefolded(self):
  good=lambda name:subprocess.CompletedProcess([],1,b'[]',('Error response from daemon: get '+name+': no such volume').encode())
  self.assertTrue(g.volume_absent(good('Name'),'Name'));self.assertFalse(g.volume_absent(good('name'),'Name'))
  mixed=good('Name');mixed.stderr+=b'\ndaemon error';self.assertFalse(g.volume_absent(mixed,'Name'))
class BootstrapDependencyGuards(unittest.TestCase):
 def fixture(self,root,defect=None):
  directory=root/'bootstrap12';directory.mkdir();(root/'calico-pinned.yaml').write_bytes(b'pinned')
  plan={k:k for k in ['node_image','CNI_images','CNI_archives','image','artifact_sha256','admission_sha256','canonical_manifest_sha256','direct_api_endpoint']};plan['controller_direct_api_endpoint']={'mode':'exclusive-owned-configmap-envFrom','container':'calico-kube-controllers'}
  plan.update(frozen={'files':{'tests/kafka_network_policy.py':'same','deploy/k8s/private.yaml':'same'}},bound={'files':{'kind.yaml':'same','calico-pinned.yaml':'same','images.json':'same'}})
  prior=dict(plan,diagnostic_only=True)
  proof={'host_direct_API_verified':True,'inside_own_node_verified':True,'tls':{'verify_peer':True,'port':6443},'configmap_uid':'same','controller_overlay':{'guarded_json_patch':True,'configmap_uid':'same','pinned_manifest_unchanged':True},'pinned_calico_manifest_sha256':g.sha(root/'calico-pinned.yaml')}
  result={'passed':True,'failure_type':None,'cleanup_failure_types':[],'inputs_unchanged':True,'direct_api_endpoint_proof':proof,'events':[{'name':n,'returncode':0}for n in ['ready-calico','ready-controller','controller-endpoint-overlay']]}
  audit={'schema':'adhd/cni12-independent-bootstrap-positive@1','passed':True,'full_input_closure_unchanged':True,'both_calico_rollouts_passed':True,'controller_overlay_guard_passed':True,'policy_routes_qualified':0,'original_rollout_seconds':300,'current_strict_absence':[{'observed_absent':True}for _ in range(5)],'protected_cluster_before_after_same_ID':'protected','protected_cluster_currently_running_same_ID':'protected','direct_api_endpoint_proof':proof}
  if defect=='false':result['passed']=False
  elif defect=='routes':audit['policy_routes_qualified']=18
  elif defect=='cleanup':audit['current_strict_absence'][0]['observed_absent']=False
  elif defect=='wrong-node':prior['node_image']='foreign'
  elif defect=='controller':proof['controller_overlay']['guarded_json_patch']=False
  elif defect=='configmap':proof['controller_overlay']['configmap_uid']='foreign'
  elif defect=='rollout':result['events'][1]['returncode']=1
  elif defect=='diagnostic':prior['diagnostic_only']=False
  elif defect=='pin':proof['pinned_calico_manifest_sha256']='foreign'
  (directory/'plan.json').write_text(json.dumps(prior));ph=g.sha(directory/'plan.json');result['plan_sha256']=ph
  (directory/'result.json').write_text(json.dumps(result));rh=g.sha(directory/'result.json');audit.update(plan_sha256=ph,result_sha256=rh)
  (directory/'audit.json').write_text(json.dumps(audit));binding={'audit_sha256':g.sha(directory/'audit.json'),'plan_sha256':ph,'result_sha256':rh}
  return directory,binding,plan
 def test_positive_dependency_and_hash_tamper(self):
  with tempfile.TemporaryDirectory()as value:
   directory,binding,plan=self.fixture(Path(value));self.assertTrue(g.verify_bootstrap_dependency(directory,binding,plan));(directory/'result.json').write_text('{}')
   with self.assertRaises(AssertionError):g.verify_bootstrap_dependency(directory,binding,plan)
 def test_semantic_false_proofs_cannot_authorize_full_route_mode(self):
  for defect in ['false','routes','cleanup','wrong-node','controller','configmap','rollout','diagnostic','pin']:
   with tempfile.TemporaryDirectory()as value:
    directory,binding,plan=self.fixture(Path(value),defect)
    with self.assertRaises(AssertionError,msg=defect):g.verify_bootstrap_dependency(directory,binding,plan)

if __name__=='__main__':unittest.main()
