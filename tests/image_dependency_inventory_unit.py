"""Offline parser guards; no network, Docker, compiler or applications."""
import importlib.util,unittest,tempfile,tarfile,io,json,hashlib
from pathlib import Path
s=importlib.util.spec_from_file_location('inv',Path(__file__).parents[1]/'scripts/image_dependency_inventory.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Parse(unittest.TestCase):
 def image(self,directory,groups):
  layers=[]
  for group in groups:
   stream=io.BytesIO()
   with tarfile.open(fileobj=stream,mode='w') as archive:
    for name,body in group:
     member=tarfile.TarInfo(name);member.size=len(body);archive.addfile(member,io.BytesIO(body))
   layers.append(stream.getvalue())
  config=json.dumps({'rootfs':{'diff_ids':['sha256:'+hashlib.sha256(x).hexdigest() for x in layers]},'config':{}}).encode()
  path=Path(directory)/'image.tar';names=[str(i) for i in range(len(layers))]
  files=[('manifest.json',json.dumps([{'Config':'config','Layers':names}]).encode()),('config',config),*zip(names,layers)]
  with tarfile.open(path,'w') as archive:
   for name,body in files:
    member=tarfile.TarInfo(name);member.size=len(body);archive.addfile(member,io.BytesIO(body))
  return path,'sha256:'+hashlib.sha256(config).hexdigest()
 def test_whiteout_removes_each_lower_database_ancestor(self):
  for marker in m.DB_WHITEOUTS:
   with self.subTest(marker=marker),tempfile.TemporaryDirectory() as d:
    path,image=self.image(d,[[(m.DB,b'P:x\nV:1\nL:MIT\n')],[(marker,b'')]])
    with self.assertRaisesRegex(AssertionError,'No supported Alpine'):m.inventory(path,image)
 def test_same_layer_database_survives_whiteouts_in_either_tar_order(self):
  for marker in m.DB_WHITEOUTS:
   for reverse in (False,True):
    group=[(m.DB,b'P:x\nV:2\nL:MIT\n'),(marker,b'')]
    if reverse:group.reverse()
    with self.subTest(marker=marker,reverse=reverse),tempfile.TemporaryDirectory() as d:
     path,image=self.image(d,[[(m.DB,b'P:x\nV:1\nL:MIT\n')],group])
     self.assertEqual(m.inventory(path,image)['packages'][0]['version'],'2')
 def test_package_license_not_relicensed(self):
  p=m.apk(b'P:busybox\nV:1\nA:x86_64\nL:GPL-2.0-only\n\nP:.virtual\nV:1\nL:\n')
  self.assertIsNone(p[0]['license_declared_by_apk']);self.assertTrue(p[0]['license_unknown']);self.assertEqual(p[1]['license_declared_by_apk'],'GPL-2.0-only')
 def test_duplicate_package_fails(self):
  with self.assertRaises(AssertionError):m.apk(b'P:x\nV:1\n\nP:x\nV:2\n')
 def test_duplicate_header_fails(self):
  with self.assertRaises(AssertionError):m.apk(b'P:x\nP:y\nV:1\n')
 def test_non_utf8_fails(self):
  with self.assertRaises(UnicodeDecodeError):m.apk(b'P:x\nV:1\nL:\xff')
 def test_final_database_whiteout_is_respected(self):
  with tempfile.TemporaryDirectory() as directory:
   layers=[]
   for name,body in [('lib/apk/db/installed',b'P:x\nV:1\nL:MIT\n'),('lib/apk/db/.wh.installed',b'')]:
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
     member=tarfile.TarInfo(name);member.size=len(body);archive.addfile(member,io.BytesIO(body))
    layers.append(stream.getvalue())
   config=json.dumps({'rootfs':{'diff_ids':['sha256:'+hashlib.sha256(x).hexdigest() for x in layers]},'config':{}}).encode()
   path=Path(directory)/'image.tar'
   files=[('manifest.json',json.dumps([{'Config':'config','Layers':['first','second']}]).encode()),('config',config),('first',layers[0]),('second',layers[1])]
   with tarfile.open(path,'w') as archive:
    for name,body in files:
     member=tarfile.TarInfo(name);member.size=len(body);archive.addfile(member,io.BytesIO(body))
   with self.assertRaisesRegex(AssertionError,'No supported Alpine'):m.inventory(path,'sha256:'+hashlib.sha256(config).hexdigest())
 def test_wrong_image_rejected_before_layer_parsing(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'image.tar';config=b'{"rootfs":{"diff_ids":[]}}'
   with tarfile.open(path,'w') as t:
    for name,data in [('manifest.json',json.dumps([{'Config':'config','Layers':[]}]).encode()),('config',config)]:
     r=tarfile.TarInfo(name);r.size=len(data);t.addfile(r,io.BytesIO(data))
   with self.assertRaises(AssertionError):m.inventory(path,'sha256:'+'a'*64)
if __name__=='__main__':unittest.main()
