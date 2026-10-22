"""Pure static-cache/launch guards, never a Docker or app process."""
import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
from image_recovery_cache import static_files,inspected_launch,CacheCustody


def fixture():
 cache={'boot_sha256':'a'*64,'build_sha256':'b'*64,'inputs_sha256':'c'*64,'beams':{'Elixir.ADHD.M'+str(n)+'.beam':'d'*64 for n in range(59)},'toolchain':{'anchors':{'/proc/self/exe':'e'*64,**{'/usr/local/lib/elixir/M'+str(n)+'.beam':'f'*64 for n in range(4)}}}}
 compiled={'manifest':cache,'manifest_sha256':'g'*64,'reviewed_runtime_audit':{'entrypoint':['elixir','/runtime/adhd/boot.exs','/app/hub.exs']}}
 manifest={'files':{'Dockerfile':'z'*64,**{'file'+str(n):'h'*64 for n in range(59)}}}
 target=SimpleNamespace(image_id='sha256:owned',name='owned')
 row={'Id':'a'*64,'Image':target.image_id,'Name':'/owned','Config':{'Entrypoint':compiled['reviewed_runtime_audit']['entrypoint'],'Env':[]},'HostConfig':{'ReadonlyRootfs':True,'PidMode':'private'},'Mounts':[{'Destination':'/private/fixture'}],'State':{'Pid':100,'Running':True}}
 return cache,compiled,manifest,target,row


class Guards(unittest.TestCase):
 def test_exact_static_counts_do_not_claim_dynamic_vm_anchor(self):
  _,compiled,manifest,_,_=fixture();files=static_files(manifest,compiled)
  self.assertEqual(len(files),125);self.assertNotIn('/proc/self/exe',files);self.assertEqual(sum(p.startswith('/runtime/adhd/')for p in files),62)
 def test_extra_module_or_source_denied(self):
  for family in ['beams','source']:
   _,c,m,_,_=fixture()
   if family=='beams':c['manifest']['beams']['extra.beam']='a'*64
   else:m['files']['extra']='a'*64
   with self.assertRaises(AssertionError):static_files(m,c)
 def test_default_and_observer_are_distinct(self):
  _,c,_,t,r=fixture();self.assertEqual(inspected_launch(r,t,c)['execution_scope'],'precompiled-default-entrypoint')
  r['Config']['Env']=['LD_PRELOAD=/observer.so'];self.assertEqual(inspected_launch(r,t,c)['execution_scope'],'precompiled-entrypoint-with-scalar-observer')
 def test_protected_mounts_and_wrong_entrypoint_rejected(self):
  for path in ['/','/app','/app/hub.exs','/runtime','/runtime/adhd','/runtime/adhd/ebin']:
   _,c,_,t,r=fixture();r['Mounts']=[{'Destination':path}]
   with self.assertRaises(AssertionError):inspected_launch(r,t,c)
  for defect in ['entrypoint','readonly','hostpid','image']:
   _,c,_,t,r=fixture()
   if defect=='entrypoint':r['Config']['Entrypoint']=['elixir','/app/hub.exs']
   elif defect=='readonly':r['HostConfig']['ReadonlyRootfs']=False
   elif defect=='hostpid':r['HostConfig']['PidMode']='host'
   else:r['Image']='foreign'
   with self.assertRaises(AssertionError):inspected_launch(r,t,c)
 def test_static_success_is_once_per_immutable_owned_instance(self):
  import hashlib
  _,c,m,_,_=fixture();raw=json.dumps(c['manifest']).encode();c['manifest_sha256']=hashlib.sha256(raw).hexdigest();calls=[]
  class Owned:
   def verify(self):self.image_id='sha256:owned'
   def docker(self,*args,**kwargs):raise AssertionError('No Docker allowed')
  obj=Owned();obj.manifest=m;obj.probe_events=[{'observed_absent':True}]
  expected=static_files(m,c)
  def probe(*args):
   calls.append(args)
   return raw if args[0]=='cat'else('\n'.join(v+'  '+k for k,v in expected.items())+'\n').encode()
  obj.probe=probe;hook=CacheCustody(Owned,{'image_config_identity':'sha256:owned','compiled_cache':c});hook.install()
  try:obj.verify();obj.verify()
  finally:hook.restore()
  self.assertEqual(len(calls),2);self.assertEqual(obj.recovery_static_cache['cache_files'],62);self.assertFalse(obj.recovery_static_cache['dynamic_VM_anchor_observed_here'])
 def test_entry_cli_binding_precedes_original_remainder(self):
  import tempfile,hashlib,sys
  from pathlib import Path
  import image_recovery_entry as entry
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);script=root/'script.py';script.write_text('pass');binding=root/'binding.json';binding.write_text('{}');report=root/'cleanup.json'
   argv=['entry','--script',str(script),'--script-sha256',hashlib.sha256(script.read_bytes()).hexdigest(),'--timeout','900','--cleanup-report',str(report),'--compiled-binding',str(binding),'--compiled-binding-sha256',hashlib.sha256(binding.read_bytes()).hexdigest(),'--','--original','value']
   with patch.object(sys,'argv',argv),patch.object(entry,'run_script')as run:entry.main()
   self.assertEqual(run.call_args.args,(script,['--original','value'],900,report,{}))
 def test_static_failure_prevents_dispatch_and_hook_restores(self):
  _,c,m,_,_=fixture();original_calls=[]
  class Owned:
   def verify(self):self.image_id='sha256:owned';original_calls.append('payload-verified')
   def docker(self,*args,**kwargs):raise AssertionError('No Docker allowed')
  original_verify=Owned.verify;original_docker=Owned.docker
  obj=Owned();obj.manifest=m;obj.probe=lambda *args:b'wrong-manifest'
  hook=CacheCustody(Owned,{'image_config_identity':'sha256:owned','compiled_cache':c});hook.install()
  try:
   with self.assertRaises(AssertionError):obj.verify()
   self.assertFalse(hasattr(obj,'recovery_static_cache'))
   with self.assertRaises(AssertionError):obj.verify()
   self.assertEqual(obj.recovery_static_cache_failure,'AssertionError')
  finally:hook.restore()
  self.assertIs(Owned.verify,original_verify);self.assertIs(Owned.docker,original_docker);self.assertEqual(original_calls,['payload-verified'])


if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('Zero starts')):unittest.main()
