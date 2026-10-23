"""UID-bound private Kind failure diagnostics; no resource starts or network."""
import json,stat,subprocess,tempfile,unittest
from pathlib import Path
from acme_platform_adapters import Kind
from kafka_oauth_custody import NamespaceLease

class Diagnostics(unittest.TestCase):
 def fixture(self,path,foreign=False,fail_logs=False):
  value=Kind.__new__(Kind);value.work=path;value.kubeconfig_sha='bound'
  value.lease=NamespaceLease('adhd-final-owned','a'*32,prefix='adhd-final-')
  namespace=value.lease.document();namespace['metadata']['uid']='exact-uid';value.lease.observe(namespace)
  calls=[]
  def kubectl(*args,**kw):
   calls.append(args);self.assertTrue(kw['sensitive']);self.assertTrue(kw['capture']);self.assertFalse(kw['check'])
   self.assertGreater(kw['timeout'],0);self.assertLessEqual(kw['timeout'],4)
   if args[0]=='get' and args[1]=='namespace':
    body=json.loads(json.dumps(namespace))
    if foreign:body['metadata']['uid']='replacement-uid'
   else:
    self.assertEqual(args[:2],('-n',value.lease.name))
    if 'pods' in args:
     body={'items':[{'metadata':{'uid':'poduid','namespace':value.lease.name},'status':{'phase':'Pending','message':'secret-not-public','initContainerStatuses':[{'name':'config-seed','state':{'waiting':{'reason':'CrashLoopBackOff','message':'private-secret'}}}],'containerStatuses':[{'name':'hub','state':{'terminated':{'reason':'private-secret','exitCode':17}}}]}}]}
    elif 'events' in args:body={'items':[{'reason':'FailedMount','message':'private-secret'},{'reason':'private-secret'}]}
    elif 'logs' in args:
     if fail_logs:raise TimeoutError('rawprivate failure')
     return subprocess.CompletedProcess(args,0,b'private-bootstrap-password',b'private-secret')
    else:body={'items':[{'spec':{'private':'secret'}}]}
   return subprocess.CompletedProcess(args,0,json.dumps(body).encode(),b'')
  value.kubectl=kubectl;return value,calls
 def test_private_files_safe_summary_actual_uid_before_queries(self):
  with tempfile.TemporaryDirectory() as raw:
   value,calls=self.fixture(Path(raw));result=value.failure_diagnostics()
   self.assertEqual(len(calls),6);self.assertEqual(calls[0][:2],('get','namespace'))
   self.assertNotIn('private-secret',json.dumps(result));self.assertNotIn('password',json.dumps(result))
   self.assertEqual(result['safe_pods'][0]['containers'][1]['reason'],'OTHER')
   self.assertEqual(result['safe_pods'][0]['containers'][1]['exit_code'],17)
   self.assertEqual(result['safe_event_reasons'],['FailedMount','OTHER'])
   directory=Path(raw)/'failure-diagnostics';self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
   for path in directory.iterdir():self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
   self.assertEqual((directory/'hub-log.stdout').read_bytes(),b'private-bootstrap-password')
 def test_foreign_namespace_uid_blocks_all_pod_or_log_reads(self):
  with tempfile.TemporaryDirectory() as raw:
   value,calls=self.fixture(Path(raw),foreign=True)
   with self.assertRaisesRegex(AssertionError,'UID changed'):value.failure_diagnostics()
   self.assertEqual(len(calls),1)
 def test_log_failure_is_reported_and_later_independent_query_attempted(self):
  with tempfile.TemporaryDirectory() as raw:
   value,calls=self.fixture(Path(raw),fail_logs=True);result=value.failure_diagnostics()
   self.assertEqual([r['label'] for r in result['errors']],['hub-log','init-log'])
   self.assertEqual(len(calls),6);self.assertNotIn('rawprivate',json.dumps(result))
 def test_unissued_namespace_causes_zero_commands(self):
  with tempfile.TemporaryDirectory() as raw:
   value,calls=self.fixture(Path(raw));value.lease.issued=False
   self.assertFalse(value.failure_diagnostics()['attempted']);self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
