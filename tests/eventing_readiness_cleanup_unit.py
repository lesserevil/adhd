"""Failure-injected ownership checks: no VM, proxy socket or broker is started."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import eventing_readiness_faults as f
import eventing_readiness_matrix as m

class Evidence:
 def __init__(self):self.value={}
 def write(self):pass

class Process:
 pid=99999999
 def __init__(self):self.code=None
 def poll(self):return self.code
 def wait(self,timeout):self.code=-15;return self.code

class Cleanup(unittest.TestCase):
 def test_fixture_constructor_failure_cannot_leave_proxy(self):
  args=SimpleNamespace(keep_work=None)
  with patch.object(f,'Fixture',side_effect=ValueError('fixture construction')),patch.object(f,'ReadinessProxy')as proxy:
   with self.assertRaisesRegex(ValueError,'fixture construction'):asyncio.run(f.run_case(args,'lag',Evidence()))
   proxy.assert_not_called()
 def test_proxy_constructor_failure_closes_constructed_fixture(self):
  closed=[]
  async def close():closed.append(True)
  fixture=SimpleNamespace(close=close,process=None,image_runtime=None,bind_evidence=lambda *a,**k:None)
  with patch.object(f,'Fixture',return_value=fixture),patch.object(f,'ReadinessProxy',side_effect=ValueError('proxy construction')):
   with self.assertRaisesRegex(ValueError,'proxy construction'):asyncio.run(f.run_case(SimpleNamespace(keep_work=None,eventing_rest_url='unused'),'lag',Evidence()))
  self.assertEqual(closed,[True])
 def test_close_failure_retains_original_and_reaps_exact_owned_process(self):
  process=Process();identity={'pid':process.pid,'start_ticks':17,'command_sha256':'owned'};closes=[]
  async def start():raise ValueError('original startup failure')
  async def close():raise RuntimeError('client close failure')
  fixture=SimpleNamespace(config={'eventing':{}},process=process,image_runtime=None,start=start,close=close,bind_evidence=lambda *a,**k:None)
  proxy=SimpleNamespace(url='unused',close=lambda:closes.append(True),handlers=0,thread=SimpleNamespace(is_alive=lambda:False),failures=[])
  args=SimpleNamespace(keep_work=None,eventing_rest_url='unused',recovery_schema='unused');e=Evidence()
  with patch.object(f,'Fixture',return_value=fixture),patch.object(f,'ReadinessProxy',return_value=proxy),patch.object(f,'Recovery'),patch.object(f,'owned_native_identity',return_value=identity),patch.object(f.os,'killpg')as kill:
   with self.assertRaisesRegex(ValueError,'original startup failure'):asyncio.run(f.run_case(args,'lag',e))
   kill.assert_called_once_with(process.pid,f.signal.SIGTERM)
  self.assertEqual(closes,[True]);self.assertTrue(e.value['native_runtime_cases']['lag']['reaped'])
  self.assertEqual(e.value['proxy_cleanup'][0]['cleanup_failure_types'],['RuntimeError'])
 def test_changed_start_identity_refuses_signal(self):
  fixture=SimpleNamespace(process=Process(),image_runtime=None)
  with patch.object(f,'owned_native_identity',return_value={'start_ticks':18}),patch.object(f.os,'killpg')as kill:
   with self.assertRaisesRegex(AssertionError,'identity changed'):f.reap_owned_native(fixture,{'start_ticks':17})
   kill.assert_not_called()
 def test_partial_failed_report_still_records_absence_and_unrun(self):
  with tempfile.TemporaryDirectory()as d:
   path=Path(d)/'report.json';path.write_text(json.dumps({'checks':[{'name':m.CASES[0]}],
    'proxy_cleanup':[{'case':c,'handlers':0,'thread_alive':False,'failures':[],'cleanup_failure_types':[]}for c in m.CASES[:2]],
    'native_runtime_cases':{'lag':{'pid':99999999,'start_ticks':17,'reaped':True}}}))
   _,observation=m.report_observations(path)
   self.assertEqual(observation['whole_passed'],list(m.CASES[:1]));self.assertEqual(observation['failed_case'],m.CASES[1])
   self.assertEqual(observation['unrun'],list(m.CASES[2:]));self.assertTrue(observation['reported_cleanup_verified'])
if __name__=='__main__':unittest.main()
