"""Pure cooperative lease guards: no Docker, model, HTTP or driver execution."""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import model_service_lease as lease

class LeaseGuards(unittest.TestCase):
 def row(self):return {'Id':lease.MODEL,'Image':lease.IMAGE,'Name':'/owned-model','State':{'Running':True,'Pid':123,'Health':{'Status':'healthy'},'StartedAt':'2026-10-22T00:00:00Z'},'RestartCount':0,'NetworkSettings':{'Ports':{'8770/tcp':[{'HostIp':'127.0.0.1','HostPort':'18770'}]}},'HostConfig':{'PortBindings':{'8770/tcp':[{'HostIp':'127.0.0.1','HostPort':'18770'}]}}}
 def expected(self):return {'container_id':lease.MODEL,'image_config_identity':lease.IMAGE,'name':'/owned-model'}
 def test_exact_model_identity_and_loopback_binding(self):
  self.assertTrue(lease.validate_identity([self.row()],self.expected())['healthy'])
  for kind in ['id','image','name','health','port','hostip']:
   row=self.row()
   if kind=='id':row['Id']='0'*64
   if kind=='image':row['Image']='sha256:'+'0'*64
   if kind=='name':row['Name']='/foreign'
   if kind=='health':row['State']['Health']['Status']='starting'
   if kind=='port':row['NetworkSettings']['Ports']['8770/tcp'][0]['HostPort']='18771'
   if kind=='hostip':row['HostConfig']['PortBindings']['8770/tcp'][0]['HostIp']='0.0.0.0'
   with self.assertRaises(AssertionError):lease.validate_identity([row],self.expected())
 def test_busy_owned_flock_rejected_without_mutating_lease(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'lease';fd,identity=lease.acquire(path)
   try:
    os.write(fd,b'held');before=path.read_bytes()
    with self.assertRaises(BlockingIOError):lease.acquire(path)
    self.assertEqual(path.read_bytes(),before)
   finally:os.close(fd)
 def test_foreign_metadata_hardlink_or_symlink_refused(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'lease';path.write_text('old');path.chmod(0o644)
   with self.assertRaises(AssertionError):lease.acquire(path)
   path.chmod(0o600);os.link(path,root/'hard')
   with self.assertRaises(AssertionError):lease.acquire(path)
   (root/'hard').unlink();alias=root/'alias';alias.symlink_to(path)
   with self.assertRaises(AssertionError):lease.acquire(alias)
 def build(self,root):
  planroot=root/'quality';planroot.mkdir();driver=planroot/'run.py';driver.write_text('# never executed\n');plan=planroot/'plan.json';plan.write_text(json.dumps({'schema':'adhd/live-quality-image-plan@1','driver_sha256':lease.sha(driver)}));work=root/'request'
  args=SimpleNamespace(work=work,plan=plan,model_name='/owned-model',lease_path=root/'lease')
  lease.prepare(args);sp=importlib.util.spec_from_file_location('copied_model_lease',work/'launch.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
  return m,work,driver
 def test_changed_driver_refused_before_inspect_or_child(self):
  with tempfile.TemporaryDirectory() as directory:
   m,w,driver=self.build(Path(directory));driver.write_text('# changed\n')
   with patch.object(m,'inspect_model') as inspect:
    with self.assertRaises(AssertionError):m.execute(w/'request.json',m.sha(w/'request.json'))
    inspect.assert_not_called()
   self.assertFalse((w/'driver.log').exists())
 def test_mismatched_service_rejects_before_driver_and_releases_lock(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);m,w,driver=self.build(root)
   with patch.object(m,'inspect_model',side_effect=AssertionError('wrong identity')):self.assertEqual(m.execute(w/'request.json',m.sha(w/'request.json')),1)
   report=json.loads((w/'result.json').read_text());self.assertIsNone(report['child_pid']);self.assertTrue(report['lease_released']);self.assertFalse(report['passed'])
   fd,_=m.acquire(root/'lease');os.close(fd)
 def test_busy_execute_rejects_before_metadata_or_driver(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);m,w,driver=self.build(root);fd,_=m.acquire(root/'lease')
   try:
    with patch.object(m,'inspect_model') as inspect:self.assertEqual(m.execute(w/'request.json',m.sha(w/'request.json')),1);inspect.assert_not_called()
    self.assertIsNone(json.loads((w/'result.json').read_text())['child_pid']);self.assertFalse((w/'driver.log').exists())
   finally:os.close(fd)
 def test_existing_result_refuses_before_lease_or_inspect(self):
  with tempfile.TemporaryDirectory() as directory:
   m,w,driver=self.build(Path(directory));(w/'result.json').write_text('old')
   with patch.object(m,'acquire') as acquire:
    with self.assertRaises(AssertionError):m.execute(w/'request.json',m.sha(w/'request.json'))
    acquire.assert_not_called()

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No Docker/model/driver process start')):unittest.main()
