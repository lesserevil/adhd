"""Pure pinned ACME bundle/stager checks; no CA, Docker or application."""
import hashlib,importlib.util,json,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('acme_stage',ROOT/'scripts/stage_container.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
class Bundle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.tools=self.root/'tools';self.tools.mkdir()
  self.data={n:b'inventory' for n in stage.ACME_FILES-{'acme-pins.json','acme-bundle.json'}}
  for n in ['lego','acme-guard']:self.data[n]=b'\x7fELF\x02\x01bound fixture'
  pins={'runtime_bundle':{'files':{n:hashlib.sha256(b).hexdigest() for n,b in self.data.items()}}}
  self.pins=json.dumps(pins).encode();self.data['acme-pins.json']=self.pins
  self.data['acme-bundle.json']=json.dumps({'schema':'adhd/acme-runtime-bundle@1','platform':'linux_amd64','files':{n:hashlib.sha256(b).hexdigest() for n,b in self.data.items()}}).encode()
  for n,b in self.data.items():(self.tools/n).write_bytes(b)
 def test_exact_bundle_and_deterministic_context(self):
  bundle=stage.acme_tools(self.tools,self.pins);self.assertEqual(bundle,self.data)
  files={'Dockerfile':b'ADD packaging.tar /','hub.exs':b'defmodule ADHD.ACMEClient do\nend'}
  packaging={'boot.exs':b'boot','build.exs':b'build',**bundle}
  for n in ['a','b']:stage.write_context(files,self.root/n,packaging)
  for p in (self.root/'a').iterdir():self.assertEqual(p.read_bytes(),(self.root/'b'/p.name).read_bytes())
  inputs=json.loads((self.root/'a/compiler-inputs.json').read_bytes());self.assertEqual(inputs['schema'],'adhd/container-compiler-inputs@2');self.assertEqual(set(inputs['files']),set(packaging))
  with tarfile.open(self.root/'a/packaging.tar') as t:
   for m in t.getmembers():self.assertEqual(m.mtime,0);self.assertFalse(m.issym() or m.islnk())
 def test_missing_tools_fails_before_output(self):
  target=self.root/'bad'
  with self.assertRaises(SystemExit):stage.write_context({'Dockerfile':b'x','hub.exs':b'defmodule ADHD.ACMEClient do'},target,{'boot.exs':b'','build.exs':b''})
  self.assertFalse(target.exists())
 def test_changed_missing_extra_redirected_tools_fail(self):
  for change in ['changed','missing','extra','redirect']:
   with self.subTest(change=change):
    p=self.tools/'lego';original=p.read_bytes()
    if change=='changed':p.write_bytes(original+b'drift')
    if change=='missing':p.unlink()
    if change=='extra':(self.tools/'extra').write_bytes(b'x')
    if change=='redirect':p.unlink();p.symlink_to(self.tools/'acme-guard')
    with self.assertRaises(SystemExit):stage.acme_tools(self.tools,self.pins)
    if p.is_symlink():p.unlink()
    p.write_bytes(original)
    if (self.tools/'extra').exists():(self.tools/'extra').unlink()
 def test_unpinned_self_consistent_bundle_rejected(self):
  # Updating the bundled manifest cannot authorize new client bytes.
  (self.tools/'lego').write_bytes(b'\x7fELF\x02\x01foreign')
  m=json.loads((self.tools/'acme-bundle.json').read_bytes());m['files']['lego']=hashlib.sha256((self.tools/'lego').read_bytes()).hexdigest();(self.tools/'acme-bundle.json').write_text(json.dumps(m))
  with self.assertRaises(SystemExit):stage.acme_tools(self.tools,self.pins)
if __name__=='__main__':unittest.main()
