"""Pure custody/once/input guards; never launch an app/browser/rig/model."""
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import image_ui_matrix as matrix
import image_ui_runtime as runtime

class UIInputGuards(unittest.TestCase):
 def test_original_nine_suite_scope_is_explicit(self):
  self.assertEqual(list(matrix.CASES),['admin','evidence','eventing','roles','recovery','index-epoch','openrig','accounts-oidc','session-fence'])
  self.assertEqual(sum(matrix.CASES.values()),86)
 def test_tree_rejects_added_files_and_redirected_roots(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);owned=root/'owned';owned.mkdir();(owned/'source').write_text('source');before=matrix.tree(owned)
   (owned/'extra').write_text('extra');self.assertNotEqual(matrix.tree(owned),before)
   alias=root/'alias';alias.symlink_to(owned,target_is_directory=True)
   with self.assertRaises(AssertionError):matrix.tree(alias)
 def test_tool_symlinks_cannot_escape_declared_tree(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);owned=root/'tools';owned.mkdir();(owned/'binary').write_text('bin');(owned/'alias').symlink_to('binary')
   self.assertEqual(matrix.tree(owned,links=True)['links'],{'alias':'binary'})
   (owned/'alias').unlink();(root/'foreign').write_text('foreign');(owned/'alias').symlink_to(root/'foreign')
   with self.assertRaises(AssertionError):matrix.tree(owned,links=True)
   rule={'alias':{'link':str(root/'foreign'),'resolved':str(root/'foreign'),'sha256':matrix.sha(root/'foreign')}}
   self.assertEqual(matrix.tree(owned,links=True,external_links=rule)['external_links'],rule)
   (root/'foreign').write_text('changed')
   with self.assertRaises(AssertionError):matrix.tree(owned,links=True,external_links=rule)
 def test_actual_driver_edit_rejected_before_execution(self):
  with tempfile.TemporaryDirectory() as directory:
   work=Path(directory);driver=work/'run.py';shutil.copyfile(matrix.__file__,driver);plan={'driver_sha256':matrix.sha(driver)}
   sp=importlib.util.spec_from_file_location('changed_ui_driver',driver);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);driver.write_text(driver.read_text()+'\n# unreviewed\n')
   with self.assertRaises(AssertionError):m.verify(plan,work)
 def test_actual_execute_reentry_refuses_before_child(self):
  from controlled_image_matrix import durable_once_marker
  with tempfile.TemporaryDirectory() as directory:
   work=Path(directory);plan={'runtime_cwd':str(work/'runtime'),'openrig_root':str(work/'rigs'),'lane_lock':str(work/'lane.lock')};matrix.write(work/'plan.json',plan);digest=matrix.sha(work/'plan.json');durable_once_marker(work/'started.json',{'plan_sha256':digest})
   with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'load',return_value=SimpleNamespace(durable_once_marker=durable_once_marker)):
    with self.assertRaises(FileExistsError):matrix.execute(work,digest)
   self.assertFalse((work/'runtime').exists());self.assertFalse((work/'rigs').exists())
 def test_model_selection_requires_live_owned_typed_loopback(self):
  custody=runtime.Custody.__new__(runtime.Custody);custody.servers=[]
  with self.assertRaises(AssertionError):custody.audit_models({'matcher':{'url':'http://127.0.0.1:18770/v1/systemone'}})
  fake=SimpleNamespace(fileno=lambda:4,server_address=('127.0.0.1',42345));custody.servers=[(fake,'owned fixture')]
  selected=custody.audit_models({'matcher':{'url':'http://127.0.0.1:42345/v1/systemone'}});self.assertEqual(len(selected),1)
  with self.assertRaises(AssertionError):custody.audit_models({'projects':[{'settings':{'history':{'endpoint':'http://127.0.0.1:18770/v1/systemone'}}}]})
 def test_foreign_or_host_pid_container_rejected_before_exec(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);manifest=root/'manifest.json';manifest.write_text(json.dumps({'files':{'hub.exs':'a'*64}}));image_id='sha256:'+'b'*64;cid='c'*64
   for field in ['image','mount-type','pid-mode']:
    custody=runtime.Custody({'image_config_identity':image_id,'manifest':str(manifest)},{},root);calls=[]
    row={'Id':cid,'Image':image_id,'Name':'/owned','State':{'Running':True,'Pid':123},'HostConfig':{'PidMode':''},'Mounts':[{'Type':'bind','Source':str(root),'Destination':str(root)}]}
    if field=='image':row['Image']='sha256:'+'d'*64
    elif field=='mount-type':row['Mounts'][0]['Type']='volume'
    else:row['HostConfig']['PidMode']='host'
    custody.docker=lambda *a:calls.append(a) or SimpleNamespace(stdout=json.dumps([row]).encode())
    image=SimpleNamespace(name='owned',container_id=cid,root=root,observe=lambda:None)
    with self.assertRaises(AssertionError):custody.observe_vm(image,'test')
    self.assertEqual(len(calls),1)
 def test_pidfd_stale_identity_never_signals_replacement(self):
  with patch.object(runtime.os,'pidfd_open',return_value=99),patch.object(runtime,'same',return_value=False),patch.object(runtime.signal,'pidfd_send_signal') as send,patch.object(runtime.os,'close') as close:
   self.assertFalse(runtime.kill_known({'pid':777,'starttime':'old'}));send.assert_not_called();close.assert_called_once_with(99)

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No app/browser/rig/process start allowed')):
  unittest.main()
