"""Pure tests: forbid processes, sockets, real relay threads and provider calls."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import quality_image_matrix as matrix
import quality_image_runtime as runtime

class FakeThread:
 def __init__(self,*a,**kw):pass
 def start(self):pass
 def cancel(self):pass
 def join(self,*a):pass
 def is_alive(self):return False
class FakeServer:
 def __init__(self,address,handler):self.handler=handler;self.server_port=54321
 def serve_forever(self):pass
 def shutdown(self):pass
 def server_close(self):pass

class QualityGuards(unittest.TestCase):
 def test_original_scope_and_fixed_caps(self):
  self.assertEqual(list(matrix.CASES.values()),[22,21,23,3]);self.assertEqual(sum(matrix.CAPS.values()),288)
 def test_same_request_bytes_response_and_count_no_retry(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ThreadingHTTPServer',FakeServer),patch.object(runtime.threading,'Thread',FakeThread),patch.object(runtime.threading,'Timer',FakeThread):
   relay=runtime.Relay({'provider_window_seconds':450,'provider_post_cap':64},Path(directory)/'exchanges.jsonl')
   raw=b'{"model":"Nemotron-Deciffusion-8B-v2.1","state":{"question":"fixed question"},"questions":{"useful":{"type":"noul"}}}'
   handler=relay.server.handler.__new__(relay.server.handler);handler.path='/v1/systemone';handler.headers={'Content-Length':str(len(raw))};handler.rfile=io.BytesIO(raw);handler.wfile=io.BytesIO();observed=[]
   handler.send_response=lambda code:observed.append(code);handler.send_header=lambda *a:None;handler.end_headers=lambda:None;handler.send_error=lambda code:observed.append(code)
   reply=b'{"answers":{"useful":{"type":"noul","noul":0.8}}}'
   def exchange(url,body,deadline,*a):
    self.assertEqual(url,'http://127.0.0.1:18770/v1/systemone');self.assertEqual(body,raw);self.assertLessEqual(deadline,time.monotonic()+10);return 200,reply
   with patch.object(runtime,'exchange',side_effect=exchange) as call:handler.do_POST();call.assert_called_once()
   self.assertEqual(handler.wfile.getvalue(),reply);self.assertEqual(observed,[200]);self.assertEqual(relay.count,1);self.assertEqual(relay.inflight,0)
   relay.close();evidence=relay.evidence();self.assertTrue(evidence['closed']);self.assertEqual(evidence['handlers'],0);self.assertEqual(evidence['relay_retries'],0)
 def test_budget_scope_and_absolute_deadline_reject_before_transport(self):
  for failure in ['cap','deadline','scope']:
   relay=runtime.Relay.__new__(runtime.Relay);relay.lock=threading.Condition();relay.job={'provider_post_cap':1};relay.count=1 if failure=='cap' else 0;relay.inflight=0;relay.closed=False;relay.deadline=time.monotonic()+(-1 if failure=='deadline' else 450);relay.violations=[]
   value={'model':'wrong' if failure=='scope' else 'Nemotron-Deciffusion-8B-v2.1','state':{},'questions':{'useful':{}}}
   with patch.object(runtime,'exchange') as transport:
    with self.assertRaises(AssertionError):relay.admit(value)
    transport.assert_not_called()
   self.assertEqual(relay.inflight,0);self.assertTrue(relay.violations)
 def test_no_native_fallback_before_original(self):
  c=runtime.QualityCustody.__new__(runtime.QualityCustody);c.is_image=lambda obj:False
  with patch.object(runtime.sdk.SDKCustody,'start') as original:
   with self.assertRaises(AssertionError):c.start(None,object())
   original.assert_not_called()
 def test_federation_original_write_stays_inside_start_once(self):
  import federation_acceptance
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);obj=federation_acceptance.Hub.__new__(federation_acceptance.Hub);obj.root=root;obj.config={'matcher':{'url':'owned'}};obj.image='image';obj.container=None;obj.handles=[]
   c=runtime.QualityCustody.__new__(runtime.QualityCustody);c.busy=set();c.instances=[];c.events=[];c.errors=[];c.is_image=lambda _:True;c.inspect_image=lambda *a:None;result=object();writes=[]
   def original(instance):
    path=root/'config.json';self.assertFalse(path.exists());self.assertFalse(hasattr(instance,'config_file'))
    path.write_text(json.dumps(instance.config));path.chmod(0o600);writes.append(path);c.original_launch_config(instance,path);return result
   with patch.object(runtime.sdk.base,'audit_models',return_value=[{'url':'owned'}]):self.assertIs(c.start(original,obj),result)
   self.assertEqual(len(writes),1);self.assertEqual(obj.config_file,root/'config.json');self.assertTrue(c.events[0]['completed']);self.assertEqual(c.busy,set())
 def test_federation_launch_rejects_changed_original_config(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'config.json';path.write_text('{}');path.chmod(0o600)
   obj=SimpleNamespace(root=root,_controlled_custody_attempt={'config_sha256':'0'*64});c=runtime.QualityCustody.__new__(runtime.QualityCustody)
   with self.assertRaises(AssertionError):c.original_launch_config(obj,path)
   self.assertFalse(hasattr(obj,'config_file'))
 def test_changed_driver_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   w=Path(directory);p=w/'run.py';shutil.copyfile(matrix.__file__,p);plan={'driver_sha256':matrix.sha(p)};s=importlib.util.spec_from_file_location('changed_quality',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);p.write_text(p.read_text()+'\n# changed\n')
   with self.assertRaises(AssertionError):m.verify(plan,w)
 def test_once_reentry_refuses_before_relay_or_child(self):
  from controlled_image_matrix import durable_once_marker
  with tempfile.TemporaryDirectory() as directory:
   w=Path(directory);p={'runtime_cwd':str(w/'runtime')};matrix.write(w/'plan.json',p);digest=matrix.sha(w/'plan.json');durable_once_marker(w/'started.json',{})
   with patch.object(matrix,'verify'),patch.object(matrix,'load',return_value=SimpleNamespace(durable_once_marker=durable_once_marker)):
    with self.assertRaises(FileExistsError):matrix.execute(w,digest)
   self.assertFalse((w/'runtime').exists())
 def test_recursive_selector_rejects_direct_provider_and_foreign_project_override(self):
  audit=runtime.sdk.base.audit_models;url='http://127.0.0.1:54321/v1/systemone'
  self.assertEqual(len(audit({'matcher':{'url':url}},{url})),1)
  for value in [{'matcher':{'url':'http://127.0.0.1:18770/v1/systemone'}},{'projects':[{'settings':{'history':{'endpoint':'http://127.0.0.1:54322/v1/systemone'}}}]}]:
   with self.assertRaises(AssertionError):audit(value,{url})

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No actual process start')),patch('socket.socket',side_effect=AssertionError('No actual socket')):unittest.main()
