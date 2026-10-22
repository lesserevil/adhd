"""No runtime or provider calls: executor admission, identity and failure cleanup."""
import importlib.util
import json
import runpy
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
s=importlib.util.spec_from_file_location('gate',Path(__file__).with_name('kafka_network_policy_cluster.py'));g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class Guards(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
 def tearDown(self):self.temp.cleanup()
 def plan(self):return {'cluster':'adhd-netpol-qa40','network':'adhd-netpol-qa40-net','node':'adhd-netpol-qa40-control-plane','owner_label':'owner','owner_nonce':'nonce','bridge_subnet':'10.240.240.0/24','node_image':{'configuration_digest':'sha256:node'},'tools':{'python':{'path':'/test/python'},'docker':{'path':'/test/docker'}},'docker_socket':{'path':'/test/socket'}}
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
if __name__=='__main__':unittest.main()
