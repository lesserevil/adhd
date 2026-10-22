"""Pure closed-path and identity checks; all runtime boundaries mocked."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import kafka_network_policy_cri as m
UID='12345678-1234-1234-1234-123456789abc';CID='a'*64
class Checks(unittest.TestCase):
 def test_systemd_parent_survives_missing_child(self):
  pod='kubepods-burstable-pod'+UID.replace('-','_')+'.slice'
  actual=m.paths(pod+':cri-containerd:'+CID,UID,CID)
  self.assertEqual(actual[0],'/sys/fs/cgroup/kubepods.slice/kubepods-burstable.slice/'+pod)
  self.assertEqual(actual[1],actual[0]+'/cri-containerd-'+CID+'.scope')
  self.assertEqual(m.paths(actual[1].removeprefix('/sys/fs/cgroup'),UID,CID),actual)
  self.assertIn('for root in "$@"',m.CGROUP_SCRIPT);self.assertLess(m.CGROUP_SCRIPT.index("printf 'UNAVAILABLE"),m.CGROUP_SCRIPT.index('for file in'))
 def test_cgroupfs_exact_and_unknown_no_scan(self):
  parent='/kubepods/burstable/pod'+UID
  self.assertEqual(m.paths(parent+'/'+CID,UID,CID),['/sys/fs/cgroup'+parent,'/sys/fs/cgroup'+parent+'/'+CID])
  for raw in ['/../../etc','/kubepods/burstable/podforeign/'+CID,parent+'/'+('b'*64),parent+'/../'+CID,'unknown.slice:cri-containerd:'+CID]:self.assertIsNone(m.paths(raw,UID,CID))
  self.assertNotIn('find ',m.CGROUP_SCRIPT);self.assertNotIn('journal',m.CGROUP_SCRIPT);self.assertNotIn('/proc',m.CGROUP_SCRIPT)
 def test_bad_uid_container_input_rejected(self):
  for uid,cid in [('foreign',CID),(UID,'a'*63),(UID,CID+';whoami')]:
   with self.assertRaises(AssertionError):m.paths('/ignored',uid,cid)
 def fixture(self):
  pod={'metadata':{'uid':UID,'name':'broker','namespace':'adhd-netpol-owned'},'spec':{'containers':[{'command':['elixir','-e','ORIGINAL'],'env':[{'name':'ERL_FLAGS','value':'+S 1:1'}],'resources':{'limits':{'cpu':'1','memory':'192Mi'}}}]},'status':{'containerStatuses':[{'name':'fixture','containerID':'containerd://'+CID,'imageID':'pinned-image'}]}}
  value={'status':{'id':CID,'metadata':{'name':'fixture'},'labels':{'io.kubernetes.pod.uid':UID,'io.kubernetes.pod.name':'broker','io.kubernetes.pod.namespace':'adhd-netpol-owned'},'imageRef':'pinned-image'},'info':{'runtimeSpec':{'process':{'args':['elixir','-e','ORIGINAL'],'user':{'uid':1000,'gid':1000}},'linux':{'resources':{'memory':{'limit':201326592}},'cgroupsPath':'/kubepods/pod'+UID+'/'+CID}}}}
  return pod,value
 def test_cri_exact_container_pod_image_process_resources(self):
  pod,x=self.fixture();self.assertEqual(m.container_info(x,pod)[0],CID)
  for group,key,value in [('status','id','b'*64),('status','imageRef','foreign')]:
   bad=copy.deepcopy(x);bad[group][key]=value
   with self.assertRaises(AssertionError):m.container_info(bad,pod)
  for key in ['io.kubernetes.pod.uid','io.kubernetes.pod.namespace','io.kubernetes.pod.name']:
   bad=copy.deepcopy(x);bad['status']['labels'][key]='foreign'
   with self.assertRaises(AssertionError):m.container_info(bad,pod)
  bad=copy.deepcopy(x);bad['info']['runtimeSpec']['linux']['resources']['memory']['limit']=805306368
  with self.assertRaises(AssertionError):m.container_info(bad,pod)
 def test_owned_node_and_network_never_accept_foreign(self):
  c={'node_id':CID,'node_name':'node','node_image':'pinned','cluster':'cluster','network_name':'net','network_id':'b'*64,'node_ip':'10.240.240.2','owner_nonce':'nonce'}
  node={'Id':CID,'Name':'/node','Image':'pinned','State':{'Running':True},'Config':{'Labels':{'io.x-k8s.kind.cluster':'cluster','io.x-k8s.kind.role':'control-plane'}},'NetworkSettings':{'Networks':{'net':{'NetworkID':'b'*64,'IPAddress':'10.240.240.2'}}}}
  net={'Id':'b'*64,'Name':'net','Driver':'bridge','Labels':{'adhd-policy-owner':'nonce'},'Containers':{CID:{'Name':'node'}}}
  m.owned_node(node,c);m.owned_network(net,c)
  node['Id']='foreign'
  with self.assertRaises(AssertionError):m.owned_node(node,c)
  net['Labels']['adhd-policy-owner']='foreign'
  with self.assertRaises(AssertionError):m.owned_network(net,c)
 def test_exact_six_commands_read_parent_before_destroyed_child(self):
  pod,cri=self.fixture();nodeid='c'*64;netid='d'*64
  c={'node_id':nodeid,'node_name':'node','node_image':'pinned','cluster':'cluster','network_name':'net','network_id':netid,'node_ip':'10.240.240.2','owner_nonce':'nonce','docker':{'path':'docker'},'socket':{'path':'/bound.sock'},'docker_config':'/private'}
  node={'Id':nodeid,'Name':'/node','Image':'pinned','State':{'Running':True},'Config':{'Labels':{'io.x-k8s.kind.cluster':'cluster','io.x-k8s.kind.role':'control-plane'}},'NetworkSettings':{'Networks':{'net':{'NetworkID':netid,'IPAddress':'10.240.240.2'}}}}
  net={'Id':netid,'Name':'net','Driver':'bridge','Labels':{'adhd-policy-owner':'nonce'},'Containers':{nodeid:{'Name':'node'}}}
  class Fake:
   def __init__(self):self.node='node';self.pod_value=pod;self.calls=[];self.saved=[];self.fences=[]
   def fence(self,name):self.fences.append(name)
   def external(self,name,argv,cap,environment):
    self.calls.append((name,argv,cap))
    if name.startswith('node-'):out=json.dumps([node]).encode()
    elif name.startswith('network-'):out=json.dumps([net]).encode()
    elif name=='cri-container':out=json.dumps(cri).encode()
    else:out=b'CGROUP parent\nFILE memory.events\noom_kill 1\nCGROUP child\nUNAVAILABLE\n'
    return name,0,out,b''
   def save(self,row):self.saved.append(row)
  capture=Fake()
  with patch.object(m,'context',return_value=c):result=m.observe(capture)
  self.assertTrue(result['available']);self.assertTrue(result['cgroup_layout_supported']);self.assertEqual(len(capture.calls),6);self.assertEqual(capture.fences,['cri-before','cri-after'])
  cg=next(row for row in capture.calls if row[0]=='cri-cgroup');self.assertEqual(cg[1][-2:],result['cgroup_paths']);self.assertIn('oom_kill 1',capture.saved[3][2].decode());self.assertIn('UNAVAILABLE',capture.saved[3][2].decode())
  cri['info']['runtimeSpec']['linux']['cgroupsPath']='unsupported'
  capture=Fake()
  with patch.object(m,'context',return_value=c):result=m.observe(capture)
  self.assertFalse(result['cgroup_layout_supported']);self.assertEqual(len(capture.calls),5);self.assertFalse(any(row[0]=='cri-cgroup'for row in capture.calls))
 def test_no_context_performs_no_read(self):
  with patch.dict(os.environ,{},clear=True),patch.object(m,'owned_node')as read:self.assertEqual(m.observe(None),{'enabled':False});read.assert_not_called()
 def test_foreign_context_regular_metadata_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   f=Path(d)/'context';f.write_text('{}');f.chmod(0o644)
   with patch.dict(os.environ,{'ADHD_POLICY_NODE_CONTEXT':str(f),'ADHD_POLICY_NODE_CONTEXT_SHA256':'bad'}):
    with self.assertRaises(AssertionError):m.context()
 def test_capture_failure_keeps_original_metadata_and_never_raises(self):
  import kafka_network_policy_readiness as r
  self.assertEqual(r.LIMITS['commands'],32);self.assertEqual(r.LIMITS['seconds'],60);self.assertEqual(r.LIMITS['total_bytes'],8*1024*1024)
  # Observer runs only after old capture; any exception is a truthful observation failure.
  with tempfile.TemporaryDirectory()as d,patch.dict(os.environ,{},clear=True),patch.object(r.Capture,'collect',side_effect=RuntimeError('mock')):
   result=r.capture(Path(d)/'private',['kubectl'],'adhd-netpol-owned','ns','a'*32,'broker','role','pinned','node')
  self.assertFalse(result['capture_passed']);self.assertEqual(result['failure_type'],'RuntimeError')
if __name__=='__main__':unittest.main()
