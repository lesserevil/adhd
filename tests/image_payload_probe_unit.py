#!/usr/bin/env python3
"""Owned payload probes: mocked Docker only, no containers/processes/signals."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import container_fixture as m

IMAGE='sha256:'+'a'*64
NAME='adhd-accept-probe-'+'c'*16
ID='f'*64

def reply(code=0,out=b'',err=b''):return subprocess.CompletedProcess([],code,out,err)
def missing(key):return reply(1,b'[]',('error: no such object: '+key+'\n').encode())
def present(image=IMAGE,name=NAME):return reply(out=json.dumps([{'Id':ID,'Image':image,'Name':'/'+name}]).encode())

class Probe(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'b'*64}}))
  self.target=m.OwnedImage(IMAGE,manifest,root);self.target.image_id=IMAGE;self.calls=[]
  self.random=patch.object(m,'uuid4',return_value=SimpleNamespace(hex='c'*32));self.random.start()
  self.no_run=patch.object(subprocess,'run',side_effect=AssertionError('No process allowed'));self.no_popen=patch.object(subprocess,'Popen',side_effect=AssertionError('No process allowed'));self.no_run.start();self.no_popen.start()
 def tearDown(self):self.no_popen.stop();self.no_run.stop();self.random.stop();self.tmp.cleanup()
 def transport(self,initial=None,run_error=None,final=None,rm=None):
  inspections=0
  def docker(*args,**kwargs):
   nonlocal inspections
   self.calls.append(args)
   if args[0]=='run':
    if run_error:raise run_error
    return reply(out=b'payload')
   if args[0]=='inspect':
    inspections+=1;value=initial if inspections==1 else final
    if isinstance(value,BaseException):raise value
    return value if value is not None else missing(args[1])
   if args[0]=='rm':
    if isinstance(rm,BaseException):raise rm
    return rm if rm is not None else reply(out=(args[-1]+'\n').encode())
   raise AssertionError(args)
  self.target.docker=docker
 def assert_reset(self):self.assertIsNone(self.target.probe_active_name);self.assertIsNone(self.target.probe_active_id)
 def test_normal_auto_remove_and_exact_run_argv(self):
  self.transport();self.assertEqual(self.target.probe('cat','/app/manifest.json'),b'payload')
  self.assertEqual(self.calls[0],('run','--rm','--name',NAME,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','cat',IMAGE,'/app/manifest.json'))
  self.assertFalse(any(c[0]=='rm' for c in self.calls));event=self.target.probe_events[-1];self.assertTrue(event['observed_absent']);self.assertIsNone(event['container_id']);self.assert_reset()
 def test_present_owned_removed_by_bound_id(self):
  self.transport(initial=present());self.target.probe('cat','/app/manifest.json')
  self.assertIn(('rm','--force',ID),self.calls);self.assertIn(('inspect',ID),self.calls);self.assertEqual(self.calls[-1],('inspect',NAME));self.assertEqual(self.target.probe_events[-1]['container_id'],ID);self.assert_reset()
 def test_timeout_preserves_primary_after_known_id_cleanup(self):
  error=subprocess.TimeoutExpired('owned run',30);self.transport(initial=present(),run_error=error)
  with self.assertRaises(subprocess.TimeoutExpired) as caught:self.target.probe('cat','/app/manifest.json')
  self.assertIs(caught.exception,error);self.assertTrue(error.__notes__);self.assertIn(('rm','--force',ID),self.calls);self.assertTrue(self.target.probe_events[-1]['observed_absent']);self.assert_reset()
 def test_run_exit_failure_preserved_and_closed(self):
  error=subprocess.CalledProcessError(125,['owned run']);self.transport(run_error=error)
  with self.assertRaises(subprocess.CalledProcessError) as caught:self.target.probe('cat','/app/manifest.json')
  self.assertIs(caught.exception,error);self.assertEqual(self.target.probe_events[-1]['run_exit_code'],125);self.assertTrue(self.target.probe_events[-1]['observed_absent'])
 def test_run_creation_error_preserved_and_closed(self):
  error=OSError('mock creation');self.transport(run_error=error)
  with self.assertRaises(OSError) as caught:self.target.probe('cat','/app/manifest.json')
  self.assertIs(caught.exception,error);self.assertTrue(self.target.probe_events[-1]['observed_absent']);self.assertIsNone(self.target.probe_events[-1]['run_exit_code'])
 def test_initial_transport_failure_still_removes_and_inspects(self):
  self.transport(initial=OSError('mock daemon'))
  with self.assertRaises(OSError):self.target.probe('cat','/app/manifest.json')
  self.assertIn(('rm','--force',NAME),self.calls);self.assertTrue(self.target.probe_events[-1]['observed_absent']);self.assertFalse(self.target.probe_cleanup_blocked);self.assert_reset()
 def test_unknown_absence_blocks_probe_verify_writer(self):
  self.transport(initial=OSError('mock daemon'),final=OSError('still unavailable'))
  with self.assertRaises(OSError):self.target.probe('cat','/app/manifest.json')
  self.assertTrue(self.target.probe_cleanup_blocked);calls=len(self.calls)
  for action in (lambda:self.target.probe('cat','/app/manifest.json'),self.target.verify,lambda:self.target.argv(Path('config.json'))):
   with self.assertRaises(AssertionError):action()
  self.assertEqual(len(self.calls),calls);self.assert_reset()
 def test_foreign_image_never_removed(self):
  foreign=present(image='sha256:'+'d'*64);self.transport(initial=foreign,final=foreign)
  with self.assertRaises(AssertionError):self.target.probe('cat','/app/manifest.json')
  self.assertFalse(any(c[0]=='rm' for c in self.calls));self.assertTrue(self.target.probe_cleanup_blocked);self.assertTrue(self.target.probe_events[-1]['foreign_object_not_removed']);self.assert_reset()
 def test_wrong_name_never_removed(self):
  foreign=present(name='foreign');self.transport(initial=foreign,final=foreign)
  with self.assertRaises(AssertionError):self.target.probe('cat','/app/manifest.json')
  self.assertFalse(any(c[0]=='rm' for c in self.calls));self.assertTrue(self.target.probe_cleanup_blocked)
 def test_primary_survives_cleanup_failure(self):
  primary=subprocess.TimeoutExpired('owned run',30);self.transport(initial=present(),run_error=primary,rm=OSError('mock removal'),final=OSError('mock inspect'))
  with self.assertRaises(subprocess.TimeoutExpired) as caught:self.target.probe('cat','/app/manifest.json')
  self.assertIs(caught.exception,primary);self.assertTrue(self.target.probe_cleanup_blocked);self.assertIn(('inspect',ID),self.calls);self.assertEqual(self.calls[-1],('inspect',NAME));self.assert_reset()
 def test_removal_error_cannot_succeed_even_if_final_absent(self):
  self.transport(initial=present(),rm=reply(1,err=b'Cannot connect to Docker daemon'))
  with self.assertRaises(AssertionError):self.target.probe('cat','/app/manifest.json')
  self.assertTrue(self.target.probe_events[-1]['observed_absent']);self.assertFalse(self.target.probe_cleanup_blocked)
 def test_name_reuse_after_auto_remove_blocks_without_removal(self):
  self.transport(final=present(image='sha256:'+'d'*64))
  with self.assertRaises(AssertionError):self.target.probe('cat','/app/manifest.json')
  self.assertFalse(any(c[0]=='rm' for c in self.calls));self.assertTrue(self.target.probe_cleanup_blocked)
 def test_failed_probe_identity_observable_without_retry(self):
  self.transport(initial=OSError('mock daemon'),final=OSError('mock daemon'))
  with self.assertRaises(OSError):self.target.probe('cat','/app/manifest.json')
  count=len(self.calls);identity=self.target.identity();self.assertEqual(len(self.calls),count);self.assertFalse(identity['payload_verified']);self.assertTrue(identity['probe_cleanup_blocked']);self.assertEqual(identity['payload_probe_lifecycle'][0]['owned_name'],NAME)
 def test_strict_exact_missing_classifier(self):
  for out in (b'',b'[]'):
   for text in ('error: no such object: '+NAME,'Error response from daemon: No such container: '+NAME):self.assertTrue(m.OwnedImage.probe_absence(reply(1,out,text.encode()),NAME))
  for code,out,text in [(0,b'',f'Error: No such object: {NAME}'),(2,b'',f'Error: No such object: {NAME}'),(1,b'{}',f'Error: No such object: {NAME}'),(1,b'',f'Error: No such object: {NAME}\nCannot connect'),(1,b'',f'Error: No such object: other'),(1,b'','Cannot connect to Docker daemon')]:self.assertFalse(m.OwnedImage.probe_absence(reply(code,out,text.encode()),NAME))

if __name__=='__main__':unittest.main()
