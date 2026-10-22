import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location('utility',Path(__file__).with_name('policy_utility_startup.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Checks(unittest.TestCase):
 def test_exact_pod_flags_memory_security_no_health(self):
  original=Path('/home/horde/src/adhd/tests/kafka_network_policy.py').read_bytes();pod=m.original(original)
  a=m.argv({'name':'owned','nonce':'nonce','image':'sha256:pinned','pod':pod})
  self.assertIn('--no-healthcheck',a);self.assertEqual(a[a.index('--env')+1],'ERL_FLAGS=+S 1:1');self.assertEqual(a[a.index('--memory')+1],'192m');self.assertEqual(a[a.index('--cpus')+1],'1');self.assertNotIn('run',a);self.assertEqual(a[-2:],pod['command'][1:]);self.assertEqual(a[a.index('--network')+1],'none')
  for name in ['--mount','--volume','--pid','--privileged','--publish']:self.assertNotIn(name,a)
 def test_original_modified_policy_rejected(self):
  raw=Path('/home/horde/src/adhd/tests/kafka_network_policy.py').read_bytes()
  for old,new in [(b'+S 1:1',b'+S 2:2'),(b"'192Mi'",b"'768Mi'"),(b"'runAsUser': 1000",b"'runAsUser': 0")]:
   with self.assertRaises(AssertionError):m.original(raw.replace(old,new))
 def test_private_docker_endpoint_no_ambient(self):
  with patch.dict(m.os.environ,{'DOCKER_HOST':'tcp://foreign','DOCKER_CONTEXT':'foreign','LD_PRELOAD':'foreign','PYTHONPATH':'foreign'}):
   value=m.env({'socket':{'path':'/bound.sock'}},Path('/private'))
  self.assertEqual(value['DOCKER_HOST'],'unix:///bound.sock');self.assertEqual(value['DOCKER_CONFIG'],'/private/docker-config');self.assertFalse(any(k in value for k in ['DOCKER_CONTEXT','LD_PRELOAD','PYTHONPATH']))
 def test_strict_absence_identifiers_and_errors(self):
  r={'code':1,'stdout':b'[]','stderr':b'error: no such object: Name'};self.assertTrue(m.absence(r,'Name'));self.assertFalse(m.absence(r,'name'))
  for key,value in [('stdout',b'[{}]'),('code',2),('stderr',b'error: no such object: Name\ndaemon failed')]:self.assertFalse(m.absence(dict(r,**{key:value}),'Name'))
 def test_once_prevents_second_executor_construction(self):
  with tempfile.TemporaryDirectory()as d:
   w=Path(d);(w/'plan.json').write_text('{}');digest=m.sha(w/'plan.json')
   with patch.object(m.sys,'flags',type('Flags',(),{'isolated':True})()),patch.object(m,'verify',return_value=True),patch.object(m,'Runner',side_effect=RuntimeError('constructor'))as runner:
    with self.assertRaises(RuntimeError):m.execute(w,digest)
    with self.assertRaises(FileExistsError):m.execute(w,digest)
   self.assertEqual(runner.call_count,1)
 def test_cleanup_independent_after_inspect_daemon_failure(self):
  r=m.Runner(Path('/private'),{'name':'owned'});r.issued=True;r.cid='known';calls=[]
  with patch.object(r,'inspect',side_effect=[OSError('daemon'),None,None]),patch.object(r,'run',side_effect=lambda a,seconds=10:(calls.append(a)or{'code':0,'stdout':b'','stderr':b''})):
   errors=r.finish()
  self.assertEqual(errors,['OSError']);self.assertEqual(calls,[['rm','--force','known']]);self.assertTrue(r.cleanup[0]['observed_absent'])
 def test_cumulative_budget_preserves_independent_cleanup_reserve(self):
  r=m.Runner(Path('/private'),{'tools':{'docker':{'path':'/bound/docker'}},'socket':{'path':'/bound.sock'}})
  r.usage['normal']={'calls':40,'bytes':524288}
  with patch.object(m.subprocess,'Popen')as start:
   with self.assertRaises(AssertionError):r.run(['inspect','owned'])
   start.assert_not_called()
  r.cleaning=True
  with patch.object(m.subprocess,'Popen',side_effect=RuntimeError('mock boundary'))as start:
   with self.assertRaises(RuntimeError):r.run(['rm','--force','owned'])
   start.assert_called_once()
  self.assertEqual(r.usage['cleanup']['calls'],1)
 def test_foreign_object_never_removed(self):
  r=m.Runner(Path('/private'),{'name':'owned'});r.issued=True;r.cid='known'
  with patch.object(r,'inspect',return_value={'foreign':True}),patch.object(r,'run')as docker:
   errors=r.finish()
  self.assertTrue(errors);docker.assert_not_called();self.assertTrue(r.cleanup[0]['foreign_not_removed'])
if __name__=='__main__':unittest.main()
