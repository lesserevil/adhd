"""Failure-observer guards with all command execution mocked; zero resources."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import kafka_network_policy_readiness as m

NS='adhd-netpol-owned';UID='ns-uid';NONCE='a'*32
class Guards(unittest.TestCase):
 def run_capture(self,root,defect=None,restarts=1):
  calls=[];pod_reads=0
  def bounded(argv,env,cwd,seconds,cap):
   nonlocal pod_reads
   calls.append((argv,seconds,cap));self.assertLessEqual(seconds,10)
   if 'namespace'in argv:
    body={'metadata':{'name':NS,'uid':'foreign'if defect=='namespace'else UID,'labels':{'adhd-policy-owner':NONCE}}}
    if defect=='bytes':return 0,b'x'*(cap+1),b''
   elif 'get'in argv and'pod'in argv:
    pod_reads+=1;body={'metadata':{'name':'broker','namespace':NS,'uid':'foreign'if defect=='pod-uid'and pod_reads>1 else'pod-uid','labels':{'app':'role'}},'spec':{'nodeName':'node','containers':[{'name':'fixture','image':'pinned'}]},'status':{'containerStatuses':[{'name':'fixture','restartCount':restarts}]}}
    if defect=='image':body['spec']['containers'][0]['image']='foreign'
   elif 'events'in argv:body={'items':[{'metadata':{'namespace':NS},'involvedObject':{'uid':'foreign'if defect=='event-uid'else'pod-uid'}}]}
   elif 'describe'in argv:return 0,b'owned fixture pending reason',b''
   elif 'logs'in argv:return 0,b'owned fixture log',b''
   else:raise AssertionError('Unexpected command')
   return 0,json.dumps(body).encode(),b''
  with patch.object(m,'bounded',side_effect=bounded):value=m.capture(root,['kubectl'],NS,UID,NONCE,'broker','role','pinned','node')
  return value,calls
 def test_complete_capture_exact22_commands_two_logs_and_caps(self):
  with tempfile.TemporaryDirectory()as d:
   value,calls=self.run_capture(Path(d)/'private');self.assertTrue(value['capture_passed']);self.assertEqual(value['commands'],22);self.assertEqual(value['log_requests'],2)
   for argv,seconds,cap in calls:
    if 'logs'in argv:self.assertIn('--limit-bytes=65536',argv);self.assertLessEqual(cap,65536)
    self.assertFalse(any(x in argv for x in ['create','delete','patch','exec','secret','secrets']))
   self.assertLess(value['bytes'],m.LIMITS['total_bytes'])
 def test_no_previous_log_when_restart_zero(self):
  with tempfile.TemporaryDirectory()as d:
   value,calls=self.run_capture(Path(d)/'private',restarts=0);self.assertTrue(value['capture_passed']);self.assertEqual(value['log_requests'],1);self.assertFalse(any('--previous'in a for a,_,_ in calls))
 def test_foreign_namespace_before_pod_or_raw_retention(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d)/'private';value,calls=self.run_capture(root,'namespace');self.assertFalse(value['capture_passed']);self.assertEqual(len(calls),1);self.assertEqual(list(root.iterdir()),[root/'index.json'])
 def test_pod_identity_image_and_foreign_events_failclosed(self):
  for defect in ['pod-uid','image','event-uid']:
   with tempfile.TemporaryDirectory()as d:
    root=Path(d)/'private';value,_=self.run_capture(root,defect);self.assertFalse(value['capture_passed'])
    self.assertFalse(any(b'foreign'in p.read_bytes()for p in root.iterdir()))
 def test_byte_and_total_time_bound_prevents_extra_commands(self):
  with tempfile.TemporaryDirectory()as d:
   value,_=self.run_capture(Path(d)/'private','bytes');self.assertFalse(value['capture_passed']);self.assertEqual(value['commands'],1)
  with tempfile.TemporaryDirectory()as d,patch.object(m.time,'monotonic',side_effect=[0,61]),patch.object(m,'bounded')as command:
   value=m.capture(Path(d)/'private',['kubectl'],NS,UID,NONCE,'broker','role','pinned','node');self.assertFalse(value['capture_passed']);command.assert_not_called()
 def test_failed_ready_primary_and_assertion_survive_capture_error(self):
  import textwrap,subprocess
  from types import SimpleNamespace
  for diagnostic_error in [None,RuntimeError('diagnostic')]:
   error=AssertionError('original Ready30 failure');calls=[]
   def checked(argv):calls.append(argv);raise error
   namespace={'checked':checked,'subprocess':subprocess,'namespace':NS,'name':'broker','root':Path('/private'),'kubectl':['kubectl'],'created':{NS:UID},'owner':NONCE,'role':'role','args':SimpleNamespace(cluster_image='pinned',kind_node='node'),'report':{}}
   with patch.object(m,'capture',side_effect=diagnostic_error,return_value={'capture_passed':True}):
    try:exec(textwrap.dedent(m.REPLACEMENT.decode()),namespace)
    except AssertionError as caught:self.assertIs(caught,error)
    else:self.fail('Original failure swallowed')
   self.assertEqual(len(calls),1);self.assertIn('--timeout=30s',calls[0])
 def test_explicit_interrupt_does_not_start_diagnostic_reads(self):
  import textwrap,subprocess
  from types import SimpleNamespace
  namespace={'checked':lambda argv:(_ for _ in ()).throw(KeyboardInterrupt()),'subprocess':subprocess,'namespace':NS,'name':'broker'}
  with patch.object(m,'capture')as capture:
   with self.assertRaises(KeyboardInterrupt):exec(textwrap.dedent(m.REPLACEMENT.decode()),namespace)
   capture.assert_not_called()
 def test_overlay_only_exact_original_ready_statement(self):
  raw=b'prefix\n'+m.ORIGINAL+b'\nsuffix\n';changed=m.overlay(raw);self.assertEqual(changed,b'prefix\n'+m.REPLACEMENT+b'\nsuffix\n');self.assertIn(b'--timeout=30s',changed)
  for bad in [b'other',raw+raw,changed]:
   with self.assertRaises(AssertionError):m.overlay(bad)
if __name__=='__main__':unittest.main()
