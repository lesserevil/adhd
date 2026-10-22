"""No-startup checks for the dedicated three-boundary image driver."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import config_image_matrix as matrix

class ConfigMatrixGuards(unittest.TestCase):
 def test_config_selection_rejects_real_provider_and_broker(self):
  base={'matcher':{'url':'http://127.0.0.1:1/v1/systemone'},'eventing':{'enabled':False}}
  self.assertTrue(matrix.audit_configuration(base,False))
  for changed in [dict(base,matcher={'url':'http://127.0.0.1:18770/v1/systemone'}),dict(base,eventing={'enabled':True,'rest_url':'http://127.0.0.1:18082'}),dict(base,history={'assessment':{'endpoint':'http://127.0.0.1:18770'}}),dict(base,projects=[{'settings':{'history':{'assessment':{'url':'http://127.0.0.1:18770'}}}}])]:
   with self.assertRaises(AssertionError):matrix.audit_configuration(changed,False)
 def test_actual_execute_once_refuses_before_child(self):
  from controlled_image_matrix import durable_once_marker
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'frozen/tests').mkdir(parents=True)
   plan={'runtime_cwd':str(root/'runtime')};matrix.save(root/'plan.json',plan)
   durable_once_marker(root/'started.json',{'plan_sha256':matrix.sha(root/'plan.json')})
   helper=type('Helper',(),{'durable_once_marker':staticmethod(durable_once_marker)})()
   with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'load',return_value=helper):
    with self.assertRaises(FileExistsError):matrix.execute(root,matrix.sha(root/'plan.json'))
   self.assertFalse((root/'runtime').exists())
 def test_full_tree_rejects_aliases_and_extra_file(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'original').write_text('bound');before=matrix.tree(root)
   (root/'alias').symlink_to(root/'original')
   with self.assertRaises(AssertionError):matrix.tree(root)
   (root/'alias').unlink();(root/'extra').write_text('extra')
   self.assertNotEqual(matrix.tree(root),before)
 def test_absence_checks_all_issued_names_even_on_transport_failure(self):
  from controlled_image_matrix import authoritative_absence
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);matrix.save(root/'custody-progress.json',{'runtimes':[],'launches':[{'name':'adhd-accept-probe-0000000000000001'},{'name':'adhd-multi-accept-0000000000000002'}]})
   helper=type('Helper',(),{'authoritative_absence':staticmethod(authoritative_absence)})()
   def inspect(argv,**kwargs):
    name=argv[-1]
    if name.endswith('1'):return subprocess.CompletedProcess(argv,125,b'',b'daemon unavailable')
    return subprocess.CompletedProcess(argv,1,b'[]\n',('error: no such object: '+name+'\n').encode())
   with patch.object(matrix,'load',return_value=helper),patch.object(matrix.subprocess,'run',side_effect=inspect) as calls:
    rows=matrix.independent_absence(root,{'tools':{'docker':{'path':'docker'}}})
   self.assertEqual(calls.call_count,2);self.assertEqual([r['observed_absent'] for r in rows],[False,True])
 def test_known_container_replacement_is_never_removed(self):
  from controlled_image_matrix import authoritative_absence
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);name='adhd-multi-accept-0000000000000001';cid='a'*64
   matrix.save(root/'custody-progress.json',{'runtimes':[],'launches':[{'name':name,'container_id':cid}]})
   helper=type('Helper',(),{'authoritative_absence':staticmethod(authoritative_absence)})()
   obj={'Id':'b'*64,'Image':matrix.IMAGE,'Name':'/'+name}
   with patch.object(matrix,'load',return_value=helper),patch.object(matrix.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps([obj]).encode(),b'')) as calls:
    rows=matrix.independent_absence(root,{'tools':{'docker':{'path':'docker'}}})
   self.assertEqual(calls.call_count,1);self.assertFalse(rows[0]['fallback_removal']);self.assertFalse(rows[0]['observed_absent'])

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No runtime process allowed')):
  unittest.main()
