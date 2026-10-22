"""Pure file/argv/closure guards only; never load an observer or start a process."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('prepared_abi',Path(__file__).with_name('image_filesystem_abi.py'))
abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)
IMAGE='sha256:'+'a'*64


class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.starts=[]
  def denied(*args,**kwargs):self.starts.append('attempt');raise AssertionError('No process permitted')
  self.patches=[patch('subprocess.run',denied),patch('subprocess.Popen',denied),patch('subprocess.check_output',denied)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.assertEqual(self.starts,[]);self.tmp.cleanup()
 def test_full_eighteen_fixtures(self):
  self.assertEqual(sum(map(len,abi.FAMILIES.values())),18)
  for source,ops in abi.FAMILIES.items():
   for op in ops:
    root=self.root/(source+'-'+op);c=abi.fixture(root,source,op)
    env=c['environment'];self.assertEqual(env['ADHD_ABI_OP'],op);self.assertFalse(c['sentinel'].exists())
    self.assertIn(env['ADHD_ABI_PREFIX']+'STAGE',env)
    self.assertEqual(env[env['ADHD_ABI_PREFIX']+'STAGE'],c['stage'])
    if source=='multi_fault.c' and op in ('link','linkat'):
     transaction=json.loads((root/'control.json.transaction').read_text())
     self.assertEqual(transaction['kind'],'registry_adoption');self.assertTrue(str(c['source']).endswith('.snapshot'))
     self.assertEqual(transaction['stage'],str(c['source']).removesuffix('.snapshot'))
    if op=='fsync' and source in ('project_recovery_fault.c','rebind_fault.c'):
     self.assertEqual(env['ADHD_ABI_SYNC'],str(root));self.assertEqual(env['ADHD_ABI_PREPARE_RENAME'],str(c['source']))
    if source=='rebind_fault.c' and op=='rename':self.assertEqual(env['ADHD_ABI_AFTER_RENAME_SYNC'],str(root))
    for f in root.rglob('*'):
     self.assertFalse(f.is_symlink())
     if f.is_file():self.assertEqual(f.stat().st_mode&0o777,0o600)
 def test_no_fixture_reuse(self):
  root=self.root/'case';abi.fixture(root,'store_move_fault.c','unlink')
  with self.assertRaises(FileExistsError):abi.fixture(root,'store_move_fault.c','unlink')
 def test_argv_private_exact_and_readonly(self):
  root=self.root/'case';case={'source':'storage_write_fault.c','op':'pwrite64'};c=abi.fixture(root,**case)
  cmd=abi.command({'image_config_identity':IMAGE},case,self.root/'observer.so',self.root/'caller.so',c,'adhd-abi-'+'b'*20,root)
  self.assertEqual(cmd[-1],IMAGE);self.assertEqual(cmd[cmd.index('--network')+1],'none')
  self.assertIn('--read-only',cmd);self.assertNotIn('--privileged',cmd);self.assertFalse(any(s=='--pid' or s.startswith('--pid=') for s in cmd))
  self.assertIn('LD_PRELOAD=/adhd-test/observer.so:/adhd-test/caller.so',cmd)
  self.assertIn('dst=/adhd-test/observer.so,readonly',next(v for v in cmd if v.endswith('dst=/adhd-test/observer.so,readonly')))
 def test_bad_image_denied(self):
  with self.assertRaises(AssertionError):abi.command({'image_config_identity':'mutable:tag'},None,None,None,None,None,None)
 def test_ordinary_control_effect_and_missing_effect(self):
  root=self.root/'case';c=abi.fixture(root,'store_move_fault.c','rename')
  with self.assertRaises(FileNotFoundError):abi.effects(c,'rename')
  c['source'].rename(c['target']);self.assertTrue(abi.effects(c,'rename')['verified'])
 def test_sparse_size_and_bytes_guard(self):
  c=abi.fixture(self.root/'case','storage_write_fault.c','pwrite64')
  with self.assertRaises(AssertionError):abi.effects(c,'pwrite64')
  with c['target'].open('r+b') as f:f.seek(abi.BIG_OFFSET);f.write(abi.PAYLOAD)
  self.assertTrue(abi.effects(c,'pwrite64')['verified'])
  with c['target'].open('r+b') as f:f.seek(abi.BIG_OFFSET);f.write(b'bad')
  with self.assertRaises(AssertionError):abi.effects(c,'pwrite64')
 def test_binding_and_redirect_guards(self):
  work=self.root/'work';(work/'inputs').mkdir(parents=True);(work/'build').mkdir()
  manifest=work/'inputs/manifest.json';manifest.write_text('{}')
  driver=work/'run.py';driver.write_bytes(Path(abi.__file__).read_bytes())
  inv={str(f.relative_to(work)):{'sha256':abi.sha(f),'bytes':f.stat().st_size} for f in (driver,manifest)}
  plan={'work':str(work),'driver_sha256':abi.sha(Path(abi.__file__)),'cases':[{'source':s,'op':op} for s,ops in abi.FAMILIES.items() for op in ops],
    'limits':{'cases':18},'directories':['inputs','build'],'inventory':inv,'canonical_manifest_sha256':abi.sha(manifest)}
  abi.verify(plan)
  empty=work/'inputs/empty';empty.mkdir()
  with self.assertRaises(AssertionError):abi.verify(plan)
  empty.rmdir()
  broken=dict(plan,driver_sha256='0'*64)
  with self.assertRaises(AssertionError):abi.verify(broken)
  extra=work/'inputs/extra';extra.symlink_to(manifest)
  with self.assertRaises(AssertionError):abi.verify(plan)
  extra.unlink();manifest.write_text('changed')
  with self.assertRaises(AssertionError):abi.verify(plan)

 def test_execute_once_marker_survives_partial_failure(self):
  work=self.root/'once';(work/'inputs').mkdir(parents=True);(work/'build').mkdir()
  manifest=work/'inputs/manifest.json';manifest.write_text('{}')
  driver=work/'run.py';driver.write_bytes(Path(abi.__file__).read_bytes())
  inv={str(f.relative_to(work)):{'sha256':abi.sha(f),'bytes':f.stat().st_size} for f in (driver,manifest)}
  plan={'work':str(work),'driver_sha256':abi.sha(Path(abi.__file__)),'cases':[{'source':s,'op':op} for s,ops in abi.FAMILIES.items() for op in ops],
    'limits':{'cases':18},'directories':['inputs','build'],'inventory':inv,'canonical_manifest_sha256':abi.sha(manifest),
    'image_config_identity':IMAGE,'artifact_sha256':'b'*64}
  path=work/'plan.json';path.write_text(json.dumps(plan));args=SimpleNamespace(plan=path,reviewed_plan_sha256=abi.sha(path))
  entered=[]
  def stop_case(*args):entered.append('first-case');raise RuntimeError('synthetic first case failure')
  with patch.object(abi,'load_helpers',return_value=(None,None)),patch.object(abi,'run_case',stop_case):
   with self.assertRaisesRegex(RuntimeError,'synthetic first'):abi.execute(args)
   marker=work/'execution.started';self.assertEqual(json.loads(marker.read_text())['plan_sha256'],args.reviewed_plan_sha256)
   self.assertFalse(json.loads((work/'result.json').read_text())['passed'])
   # Even if a partial runtime result is lost, exclusive durable admission is
   # authoritative. Re-entry cannot reach a second mocked case/helper import.
   (work/'result.json').unlink()
   with self.assertRaises(FileExistsError):abi.execute(args)
  self.assertEqual(entered,['first-case'])
 def test_truthful_forwarding_symbol_and_offset_width(self):
  call={'op':'pwrite64','namespace_pid':1,'wrapper_resolved':True,'next_resolved_distinct':True,'direct_syscall':False,
    'unarmed_success':True,'real_forwarding_symbol':'pwrite','off_t_bytes':8,'off64_t_bytes':8,'sparse_offset':abi.BIG_OFFSET}
  abi.validate_call(call,'pwrite64')
  abi.validate_call(dict(call,real_forwarding_symbol='pwrite64'),'pwrite64')
  for changed in [dict(call,off_t_bytes=4),dict(call,off64_t_bytes=4),dict(call,real_forwarding_symbol='unknown'),dict(call,next_resolved_distinct=False),dict(call,sparse_offset=17)]:
   with self.assertRaises(AssertionError):abi.validate_call(changed,'pwrite64')
  # No generic alias fallback is admitted for unrelated operations.
  with self.assertRaises(AssertionError):abi.validate_call(dict(call,op='fsync'),'fsync')
 def test_independent_cleanup_after_known_id_inspect_failure(self):
  identifier='f'*64
  def absent(result,key):return result.returncode==1 and result.stderr==('No such object: '+key).encode()
  def reply(code=0,body=b'',error=b''):return SimpleNamespace(returncode=code,stdout=body,stderr=error)
  calls=[]
  def docker(*args,**kwargs):
   calls.append(args)
   if len(calls)==1:raise OSError('synthetic inspect transport failure')
   if args[0]=='rm':return reply()
   return reply(1,error=('No such object: '+identifier).encode())
  result=abi.cleanup_owned(docker,identifier,IMAGE,identifier,absent)
  self.assertTrue(result['owned_container_absent']);self.assertIn(('rm','--force',identifier),calls)
  self.assertIn('InitialInspect:OSError',result['cleanup_notes'])
  # Positive foreign inspection is never removed, even for a claimed knownID.
  calls=[]
  def foreign(*args,**kwargs):
   calls.append(args);return reply(body=json.dumps([{'Id':identifier,'Image':'sha256:'+'c'*64}]).encode())
  result=abi.cleanup_owned(foreign,identifier,IMAGE,identifier,absent)
  self.assertFalse(result['owned_container_absent']);self.assertFalse(any(a[0]=='rm' for a in calls))
  # Persistent daemon errors cannot establish absence, although the independent
  # known-ID force removal is still attempted exactly once.
  calls=[]
  def daemon(*args,**kwargs):calls.append(args);return reply(1,error=b'daemon unavailable')
  result=abi.cleanup_owned(daemon,identifier,IMAGE,identifier,absent)
  self.assertFalse(result['owned_container_absent']);self.assertEqual(calls.count(('rm','--force',identifier)),1)


if __name__=='__main__':unittest.main()
