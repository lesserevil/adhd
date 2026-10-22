"""One-Pod entry exercised with every external command mocked; zero resources."""
import json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import kafka_network_policy_utility as m

class Checks(unittest.TestCase):
 def test_one_original_pod_failure_preserved_and_capture_before_delete(self):
  for ready in (False,True):
   with tempfile.TemporaryDirectory()as directory:
    root=Path(directory);args=SimpleNamespace(work=root/'private',report=root/'report.json',kind_node='node',namespace='adhd-netpol-utility40',kubectl=Path('/kubectl'),kubeconfig=root/'config',cluster_image='adhd-hub:qa40')
    active=False;body=None;calls=[];observed=[];nonce='a'*32
    def bounded(argv,env,cwd,seconds,cap):
     nonlocal active,body
     calls.append(argv)
     if argv[0]=='docker':return 0,b'[{}]',b''
     if 'get'in argv:
      value={'metadata':{'name':args.namespace,'uid':'ns-uid','labels':{'adhd-policy-owner':nonce}}}if active else None
      return 0,json.dumps(value).encode()if value else b'',b''
     if 'create'in argv:
      value=json.loads(Path(argv[-1]).read_bytes())
      if value['kind']=='Namespace':active=True
      else:body=value
      return 0,b'created',b''
     if 'delete'in argv:observed.append('delete');active=False;return 0,b'deleted',b''
     if '--for=condition=Ready'in argv:return (0,b'ready',b'')if ready else(1,b'',b'originalreadyfalse')
     if '--for=delete'in argv:return 0,b'deleted',b''
     raise AssertionError(argv)
    def capture(*args):observed.append('capture');return {'capture_passed':True,'owned_node_observation':{'available':True,'cgroup_layout_supported':True,'cgroup_read_returncode':0}}
    ctx={'node_name':'node','node_id':'c'*64,'network_id':'d'*64,'docker':{'path':'docker'}}
    with patch.object(m,'context',return_value=ctx),patch.object(m,'owned_node'),patch.object(m,'owned_network'),patch.object(m,'bounded',side_effect=bounded),patch.object(m,'capture',side_effect=capture),patch.object(m.secrets,'token_hex',return_value=nonce):result=m.main(args)
    value=json.loads(args.report.read_bytes());self.assertEqual(result,0 if ready else 1);self.assertEqual(value['original_ready_passed'],ready);self.assertTrue(value['diagnostic_completed']);self.assertEqual(value['routes_qualified'],0);self.assertFalse(value['passed']);self.assertEqual(observed,['capture','delete']);self.assertTrue(value['namespace_cleanup'][0]['observed_absent'])
    expected=m.pod('broker','kafka',args.namespace,args.cluster_image);self.assertEqual(body,expected);self.assertEqual(sum('create'in a and a[-1].endswith('pod.json')for a in calls),1)
    self.assertFalse(any(any(v in a for v in ['apply','exec'])for a in calls));self.assertIn('--timeout=30s',next(a for a in calls if '--for=condition=Ready'in a))
 def test_capture_unavailable_not_reported_completed(self):
  # The real entry's expression must require actualCRI+supportedlayout+read return0.
  import ast
  tree=ast.parse(Path(m.__file__).read_bytes());nodes=[n for n in ast.walk(tree)if isinstance(n,ast.Assign)and any(isinstance(v,ast.Subscript)and isinstance(v.slice,ast.Constant)and v.slice.value=='diagnostic_completed'for v in n.targets)]
  expression=nodes[-1].value
  for observation in [{},{'available':True,'cgroup_layout_supported':False},{'available':True,'cgroup_layout_supported':True,'cgroup_read_returncode':1}]:
   value=eval(compile(ast.Expression(expression),'actual-expression','eval'),{'report':{'readiness_diagnostics':{'capture_passed':True}},'observation':observation});self.assertFalse(value)
if __name__=='__main__':unittest.main()
