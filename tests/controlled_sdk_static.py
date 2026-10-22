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
 def compiled_fixture(self,root):
  import copy
  modules=['Elixir.ADHD.M'+str(i) for i in range(59)];artifact='a'*64;manifest='b'*64;image='sha256:'+'c'*64
  anchors={'/proc/self/exe':'d'*64,**{'/usr/local/lib/elixir/ebin/'+n+'.beam':'e'*64 for n in ['Code','JSON','Kernel','elixir']}}
  value={'schema':'adhd/precompiled-cache@1','source':'/app/hub.exs','source_sha256':artifact,'payload_manifest_sha256':manifest,
   'modules':modules,'beams':{n+'.beam':'f'*64 for n in modules},'inputs_sha256':'1'*64,'boot_sha256':'2'*64,'build_sha256':'3'*64,
   'toolchain':{'elixir':'1.20.4','otp':'29','anchors':anchors}}
  path=root/'cache-manifest.json';matrix.write(path,value);metadata=root/'cache-metadata.json';matrix.write(metadata,{'offline_only':True})
  audit={'passed':True,'image_config_identity':image,'artifact_sha256':artifact,'canonical_manifest_sha256':manifest,'cache_manifest_sha256':matrix.sha(path),
   'cache_metadata_sha256':matrix.sha(metadata),'inputs_sha256':value['inputs_sha256'],'entrypoint':['elixir','/runtime/adhd/boot.exs','/app/hub.exs']}
  admission={'files':{'cache-manifest.json':matrix.sha(path),'cache-metadata.json':matrix.sha(metadata)},'compiled_runtime_audit':audit}
  return path,admission,image,artifact,manifest
 def test_optional_compiled_binding_rejects_foreign_or_incomplete_proof(self):
  import copy
  with tempfile.TemporaryDirectory() as directory:
   args=self.compiled_fixture(Path(directory));binding=matrix.compiled_cache_binding(*args)
   self.assertEqual(len(binding['manifest']['modules']),59)
   for key in ['image_config_identity','artifact_sha256','inputs_sha256','cache_manifest_sha256','cache_metadata_sha256','canonical_manifest_sha256','entrypoint']:
    bad=copy.deepcopy(args[1]);bad['compiled_runtime_audit'][key]='wrong'
    with self.assertRaises(AssertionError):matrix.compiled_cache_binding(args[0],bad,*args[2:])
   bad=copy.deepcopy(args[1]);del bad['compiled_runtime_audit']
   with self.assertRaises(KeyError):matrix.compiled_cache_binding(args[0],bad,*args[2:])
   value=json.loads(args[0].read_text());value['beams']['../foreign.beam']=value['beams'].pop(next(iter(value['beams'])))
   matrix.write(args[0],value);args[1]['files']['cache-manifest.json']=matrix.sha(args[0])
   with self.assertRaises(AssertionError):matrix.compiled_cache_binding(*args)
 def test_compiled_actual_vm_checks_are_after_original_source_custody_no_health(self):
  with tempfile.TemporaryDirectory() as directory:
   args=self.compiled_fixture(Path(directory));compiled=matrix.compiled_cache_binding(*args)
   custody=runtime.SDKCustody.__new__(runtime.SDKCustody);custody.plan={'compiled_cache':compiled};custody.name=lambda obj:'owned';calls=[]
   event={'container_id':'i'*64,'host_vm_pid':123};obj=SimpleNamespace()
   files={'/runtime/adhd/boot.exs':'2'*64,'/runtime/adhd/build.exs':'3'*64,'/runtime/adhd/inputs.json':'1'*64,
    **{'/runtime/adhd/ebin/'+k:v for k,v in compiled['manifest']['beams'].items()},
    **{('/proc/1/exe' if k=='/proc/self/exe' else k):v for k,v in compiled['manifest']['toolchain']['anchors'].items()}}
   def docker(*argv):
    calls.append(argv)
    if argv[0]=='inspect':body=json.dumps([{'Id':event['container_id'],'State':{'Pid':123,'Running':True},'Config':{'Entrypoint':compiled['reviewed_runtime_audit']['entrypoint']}}]).encode()
    elif argv[2]=='cat':body=args[0].read_bytes()
    else:body=('\n'.join(v+'  '+k for k,v in files.items())+'\n').encode()
    return SimpleNamespace(stdout=body)
   custody.docker=docker
   with patch.object(runtime.base.Custody,'inspect_image',side_effect=lambda *a:calls.append(('original-source-custody',))):custody.inspect_image(obj,event)
   self.assertEqual(calls[0],('original-source-custody',));self.assertEqual(len(calls),4);self.assertNotIn('health',str(calls))
   self.assertEqual(event['compiled_cache']['modules'],59);self.assertEqual(event['compiled_cache']['extra_health_or_warmup_requests'],0)
 def fake_custody(self):
  root=Path('/private/owned');image='sha256:'+'a'*64;cid='b'*64;name='adhd-test-000000000000'
  files={'hub.exs':'c'*64,**{'f'+str(i):'d'*64 for i in range(58)}};manifest={'files':{**files,'Dockerfile':'e'*64}}
  obj=SimpleNamespace(root=root,tokens={'a':'private-test-token'},_controlled_custody_attempt={})
  custody=SimpleNamespace(name=lambda obj:name,is_image=lambda obj:True,image=image,manifest=manifest,manifest_bytes=json.dumps(manifest).encode(),plan={'expected_app_files':59})
  row={'Name':'/'+name,'Id':cid,'Image':image,'Mounts':[{'Type':'bind','Source':str(root),'Destination':str(root)}],'State':{'Running':True,'Pid':123},'HostConfig':{'PidMode':''}}
  return custody,obj,row,files
 def test_foreign_inspection_never_issues_logs_or_exec(self):
  for foreign in ['image','mount-type']:
   custody,obj,row,files=self.fake_custody();calls=[]
   if foreign=='image':row['Image']='sha256:'+'f'*64
   else:row['Mounts'][0]['Type']='volume'
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
 def test_health_recorder_preserves_original_calls_objects_and_exceptions(self):
  import httpx
  obj=SimpleNamespace(base='http://127.0.0.1:54321')
  def original(obj):return httpx.get(obj.base+'/health',timeout=1)
  response=httpx.Response(503,content=b'x'*2048);failure=httpx.ConnectError('original exception')
  for outcome in [response,failure]:
   with patch.object(httpx,'get',side_effect=outcome if isinstance(outcome,BaseException) else None,return_value=response) as get:
    with runtime.OriginalHealthCalls(original,obj) as recorder:
     if isinstance(outcome,BaseException):
      with self.assertRaises(httpx.ConnectError) as caught:original(obj)
      self.assertIs(caught.exception,failure)
     else:self.assertIs(original(obj),response)
    get.assert_called_once_with(obj.base+'/health',timeout=1)
   rows=recorder.evidence()['calls'];self.assertEqual(len(rows),1)
   if outcome is response:
    self.assertEqual(rows[0]['status_code'],503);self.assertEqual(rows[0]['body_bytes'],2048);self.assertEqual(len(rows[0]['body_prefix_hex']),2048)
   else:self.assertEqual(rows[0]['exception_type'],'ConnectError')
 def test_health_recorder_ignores_nonoriginal_calls_and_restores_get(self):
  import httpx
  obj=SimpleNamespace(base='http://127.0.0.1:54321')
  def original(obj):return httpx.get(obj.base+'/health',timeout=1)
  result=httpx.Response(200,json={'status':'ready'})
  with patch.object(httpx,'get',return_value=result) as get:
   with runtime.OriginalHealthCalls(original,obj) as recorder:
    self.assertIs(httpx.get(obj.base+'/health',timeout=1),result)
    self.assertIs(original(obj),result)
   self.assertIs(httpx.get,get);self.assertEqual(get.call_count,2);self.assertEqual(len(recorder.rows),1)
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
    with self.assertRaises(exception) as caught:runtime.bounded(['never-executed'],time.monotonic()+.025,limit)
   self.assertTrue(caught.exception.owned_diagnostic_client['reaped']);self.assertTrue(caught.exception.owned_diagnostic_client['forced_kill'])
   self.assertEqual(state['killed'],1);self.assertEqual(state['waited'],1);self.assertTrue(all(stream.closed for stream in pipes))

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No actual processes allowed')):
  unittest.main()
