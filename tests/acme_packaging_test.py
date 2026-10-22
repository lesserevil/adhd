"""Pure pinned ACME bundle/stager checks; no CA, Docker or application."""
import hashlib,importlib.util,json,tarfile,tempfile,unittest,sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parent))
from image_compiled_inputs import compiled_context,digest
from image_payload_audit import inspect_payload
from image_compiled_admission import cache_binding
import io,copy
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
  files={'Dockerfile':b'ADD packaging.tar /\nENTRYPOINT ["elixir", "/runtime/adhd/boot.exs", "/app/hub.exs"]','hub.exs':b'defmodule ADHD.ACMEClient do\nend'}
  packaging={'boot.exs':b'boot','build.exs':b'build',**bundle}
  for n in ['a','b']:stage.write_context(files,self.root/n,packaging)
  for p in (self.root/'a').iterdir():self.assertEqual(p.read_bytes(),(self.root/'b'/p.name).read_bytes())
  binding=compiled_context(self.root/'a',digest((self.root/'a/manifest.json').read_bytes()),digest(files['hub.exs']));self.assertEqual(binding['payload_counts']['modules'],['Elixir.ADHD.ACMEClient']);self.assertEqual(len(binding['acme_files']),8)
  inputs=json.loads((self.root/'a/compiler-inputs.json').read_bytes());self.assertEqual(inputs['schema'],'adhd/container-compiler-inputs@2');self.assertEqual(set(inputs['files']),set(packaging))
  with tarfile.open(self.root/'a/packaging.tar') as t:
   for m in t.getmembers():self.assertEqual(m.mtime,0);self.assertFalse(m.issym() or m.islnk())
 def test_offline_cache_audit_checks_tools_and_source_bound_counts(self):
  bundle=stage.acme_tools(self.tools,self.pins);helpers={'boot.exs':b'boot','build.exs':b'build'};helper_root=self.root/'helpers';helper_root.mkdir()
  for n,b in helpers.items():(helper_root/n).write_bytes(b)
  files={'Dockerfile':b'ADD packaging.tar /\nENTRYPOINT ["elixir", "/runtime/adhd/boot.exs", "/app/hub.exs"]','hub.exs':b'defmodule ADHD.ACMEClient do\nend'}
  context=self.root/'context';stage.write_context(files,context,{**helpers,**bundle})
  inputs=(context/'compiler-inputs.json').read_bytes();pi=json.loads(inputs);manifest=(context/'manifest.json').read_bytes()
  name='Elixir.ADHD.ACMEClient';beam=b'actual image gate must validate real BEAM separately'
  cm={'schema':'adhd/precompiled-cache@2','source':'/app/hub.exs','source_sha256':digest(files['hub.exs']),'payload_manifest_sha256':digest(manifest),'inputs_sha256':digest(inputs),'boot_sha256':digest(helpers['boot.exs']),'build_sha256':digest(helpers['build.exs']),'modules':[name],'beams':{name+'.beam':digest(beam)},'toolchain':{},'acme':{n:digest(b) for n,b in bundle.items()}}
  cache_files={'adhd/boot.exs':helpers['boot.exs'],'adhd/build.exs':helpers['build.exs'],'adhd/inputs.json':inputs,'adhd/manifest.json':json.dumps(cm).encode(),'adhd/ebin/'+name+'.beam':beam,**{'adhd/'+n:b for n,b in bundle.items()}}
  def tar(files,directories,wrong=False):
   stream=io.BytesIO()
   with tarfile.open(fileobj=stream,mode='w') as archive:
    for n in directories:
     m=tarfile.TarInfo(n);m.type=tarfile.DIRTYPE;m.mode=0o755 if n=='runtime' else 0o555;archive.addfile(m)
    for n,b in files.items():
     m=tarfile.TarInfo(n);m.mode=0o555 if n in ['adhd/lego','adhd/acme-guard'] else 0o444
     if wrong and n=='adhd/lego':m.mode=0o444
     m.size=len(b);archive.addfile(m,io.BytesIO(b))
   return stream.getvalue()
  # Docker cp /app/. yields relative names, unlike the staging app/ tar prefix.
  app={n:b for n,b in files.items() if n!='Dockerfile'};app['manifest.json']=manifest
  result=inspect_payload(tar(app,[]),tar(cache_files,['adhd','adhd/ebin']),tar({},['runtime']),context,digest(files['hub.exs']),helper_root)
  self.assertEqual((result['cache_modules'],result['cache_entries']),(1,15))
  audit={**{k:v for k,v in result.items() if k not in ['cache_manifest','cache_metadata']},'passed':True,'image_id':'sha256:'+'a'*64,'container_started':False,'owned_container_absent':True}
  raw=json.dumps(audit).encode();metadata=json.dumps(result['cache_metadata']).encode()
  cache_binding(context,audit['image_id'],digest(files['hub.exs']),digest(manifest),raw,digest(raw),result['cache_manifest'],metadata)
  with self.assertRaises(AssertionError):inspect_payload(tar(app,[]),tar(cache_files,['adhd','adhd/ebin'],True),tar({},['runtime']),context,digest(files['hub.exs']),helper_root)
  corrupted=copy.deepcopy(cm);corrupted['acme']['lego']='f'*64
  with self.assertRaises(AssertionError):cache_binding(context,audit['image_id'],digest(files['hub.exs']),digest(manifest),raw,digest(raw),json.dumps(corrupted).encode(),metadata)
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
