"""Preparation/runtime-adapter guards without app/container/provider startup."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch
import controlled_sdk_matrix as matrix
import controlled_sdk_runtime as runtime

class SDKPreparationGuards(unittest.TestCase):
 def test_fixed_sdk_scope_and_order(self):
  self.assertEqual(list(matrix.CASES.items()),[('feedback_sdk',5),('archive_sdk',4),('history_sdk',4),('retrieval_sdk',4)])
 def fake_custody(self):
  root=Path('/private/owned');image='sha256:'+'a'*64;cid='b'*64;name='adhd-test-000000000000'
  files={'hub.exs':'c'*64,**{'f'+str(i):'d'*64 for i in range(58)}};manifest={'files':{**files,'Dockerfile':'e'*64}}
  obj=SimpleNamespace(root=root,tokens={'a':'private-test-token'},_controlled_custody_attempt={})
  custody=SimpleNamespace(name=lambda obj:name,is_image=lambda obj:True,image=image,manifest=manifest,manifest_bytes=json.dumps(manifest).encode(),plan={'expected_app_files':59})
  row={'Name':'/'+name,'Id':cid,'Image':image,'Mounts':[{'Source':str(root),'Destination':str(root)}],'State':{'Running':True,'Pid':123},'HostConfig':{'PidMode':''}}
  return custody,obj,row,files
 def test_foreign_inspection_never_issues_logs_or_exec(self):
  custody,obj,row,files=self.fake_custody();row['Image']='sha256:'+'f'*64;calls=[]
  def read(argv,deadline):calls.append(argv);return {'returncode':0,'stdout':json.dumps([row]).encode(),'stderr':b''}
  result=runtime.startup_diagnostics(custody,obj,read)
  self.assertFalse(result['owned_identity_verified']);self.assertEqual(len(calls),1);self.assertEqual(result['observations'],{})
 def test_owned_readonly_diagnostics_bind_actual_vm_payload_and_redact(self):
  custody,obj,row,files=self.fake_custody();calls=[]
  def read(argv,deadline):
   calls.append(argv);self.assertLessEqual(deadline,time.monotonic()+3)
   if argv[1]=='inspect':body=json.dumps([row]).encode()
   elif argv[1]=='logs':body=b'private-test-token'
   elif argv[-1]=='/app/manifest.json':body=custody.manifest_bytes
   elif 'sha256sum' in argv:body=('\n'.join(d+'  /app/'+p for p,d in files.items())+'\n').encode()
   else:body=b'/opt/erts/bin/beam.smp\nPid:\t1\n'
   return {'returncode':0,'stdout':body,'stderr':b''}
  result=runtime.startup_diagnostics(custody,obj,read)
  self.assertTrue(result['owned_identity_verified']);self.assertTrue(result['actual_beam_pid1_observed']);self.assertTrue(result['all59_actual_app_hashes_matched']);self.assertTrue(result['actual_canonical_manifest_matched'])
  self.assertNotIn('private-test-token',json.dumps(result));self.assertNotIn('health',str(calls))
 def test_original_start_exception_identity_is_preserved(self):
  custody=runtime.SDKCustody.__new__(runtime.SDKCustody);custody.is_image=lambda obj:True
  obj=SimpleNamespace(_controlled_custody_attempt={});failure=AssertionError('Original30s failure')
  def original(obj):raise failure
  def parent(self,observed,obj,*a,**kw):return observed(obj,*a,**kw)
  with patch.object(runtime.base.Custody,'start',parent),patch.object(runtime,'startup_diagnostics',return_value={'unavailable':[]}):
   with self.assertRaises(AssertionError) as caught:custody.start(original,obj)
  self.assertIs(caught.exception,failure);self.assertIn('startup_failure_diagnostics',obj._controlled_custody_attempt)
 def test_actual_execute_once_rejects_before_compiler_or_child(self):
  from controlled_image_matrix import durable_once_marker
  with tempfile.TemporaryDirectory() as directory:
   work=Path(directory);plan={'runtime_cwd':str(work/'runtime')};matrix.write(work/'plan.json',plan);digest=matrix.sha(work/'plan.json');durable_once_marker(work/'started.json',{'plan_sha256':digest})
   helper=SimpleNamespace(durable_once_marker=durable_once_marker)
   with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'load',return_value=helper):
    with self.assertRaises(FileExistsError):matrix.execute(work,digest)
   self.assertFalse((work/'runtime').exists())
 def test_actual_changed_driver_fails_before_other_work(self):
  with tempfile.TemporaryDirectory() as directory:
   work=Path(directory);driver=work/'run.py';shutil.copyfile(matrix.__file__,driver);plan={'driver_sha256':matrix.sha(driver)}
   spec=importlib.util.spec_from_file_location('actual_sdk_copy',driver);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   driver.write_text(driver.read_text()+'\n# unreviewed edit\n')
   with self.assertRaises(AssertionError):module.verify(plan,work)
 def test_diagnostic_deadline_and_output_limit_reap_only_fake_client(self):
  for payload,limit,exception in [(b'',32,TimeoutError),(b'x'*64,32,ValueError)]:
   pipes=[];writers=[]
   for _ in range(2):
    read,write=os.pipe();pipes.append(os.fdopen(read,'rb',buffering=0));writers.append(write)
   if payload:os.write(writers[0],payload)
   state={'closed':False,'killed':0,'waited':0}
   def kill():
    state['killed']+=1;state['closed']=True
    for fd in writers:os.close(fd)
   def wait(**kwargs):state['waited']+=1;return 0
   process=SimpleNamespace(stdout=pipes[0],stderr=pipes[1],poll=lambda:0 if state['closed'] else None,kill=kill,wait=wait)
   with patch.object(runtime.subprocess,'Popen',return_value=process):
    with self.assertRaises(exception):runtime.bounded(['never-executed'],time.monotonic()+.025,limit)
   self.assertEqual(state['killed'],1);self.assertEqual(state['waited'],1);self.assertTrue(all(stream.closed for stream in pipes))

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No actual processes allowed')):
  unittest.main()
