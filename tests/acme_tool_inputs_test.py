"""Pure dependency-source/package input tests; no compiler or service."""
import importlib.util,io,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
client=load('build_acme_client');pack=load('package_acme_tools')
class Inputs(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
 def test_archive_full_set_and_content(self):
  root=self.root/'source';root.mkdir();(root/'main.go').write_bytes(b'pinned')
  archive=self.root/'source.tar'
  with tarfile.open(archive,'w') as tar:
   m=tarfile.TarInfo('tag/main.go');m.size=6;tar.addfile(m,io.BytesIO(b'pinned'))
  self.assertEqual(client.archive_tree(archive,root),{'main.go':client.sha(b'pinned')})
  for name in ['changed','extra','redirect']:
   with self.subTest(name=name):
    p=root/'main.go'
    if name=='changed':p.write_bytes(b'other')
    elif name=='extra':(root/'shadow.go').write_bytes(b'x')
    else:p.unlink();p.symlink_to(archive)
    with self.assertRaises(AssertionError):client.archive_tree(archive,root)
    if p.is_symlink():p.unlink()
    p.write_bytes(b'pinned')
    if (root/'shadow.go').exists():(root/'shadow.go').unlink()
 def test_archive_cannot_introduce_link(self):
  root=self.root/'source';root.mkdir();archive=self.root/'source.tar'
  with tarfile.open(archive,'w') as tar:
   m=tarfile.TarInfo('tag/redirect');m.type=tarfile.SYMTYPE;m.linkname='/foreign';tar.addfile(m)
  with self.assertRaises(AssertionError):client.archive_tree(archive,root)
 def test_module_cache_escape_and_version(self):
  cache=self.root/'modules';cache.mkdir();expected=cache/'github.com/!example/client@v1.2.3';expected.mkdir(parents=True)
  self.assertEqual(pack.module_dir(cache,'github.com/Example/client','v1.2.3'),expected)
  for name,version in [('../foreign','v1.2.3'),('/foreign','v1.2.3'),('github.com/a/b','../../../foreign')]:
   with self.assertRaises(AssertionError):pack.module_dir(cache,name,version)
 def test_notice_input_cannot_redirect(self):
  real=self.root/'notice';real.write_bytes(b'terms');link=self.root/'link';link.symlink_to(real)
  self.assertEqual(pack.raw(real),b'terms')
  with self.assertRaises(AssertionError):pack.raw(link)
if __name__=='__main__':unittest.main()
