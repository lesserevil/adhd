"""Production-private state preflight with mocked Docker and inaccessible host children."""
import json,stat,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import acme_platform_adapters as adapters
ROOT=Path(__file__).resolve().parents[1]
SUCCESS=b'ADHD_STATE_PREFLIGHT uid=10001 gid=10001 private=ok\n'
class State(unittest.TestCase):
 def runner(self,output=SUCCESS,error=None,unknown=False):
  calls=[]
  def command(argv,**kw):
   calls.append(argv)
   if argv[1]=='run':
    if error:raise error
    return subprocess.CompletedProcess(argv,0,output,b'')
   if argv[1]=='inspect':
    if unknown:return subprocess.CompletedProcess(argv,125,b'',b'daemon unavailable')
    return subprocess.CompletedProcess(argv,1,b'[]',('error: no such object: '+argv[-1]).encode())
   return subprocess.CompletedProcess(argv,0,b'',b'')
  return calls,command
 def host(self,state,uid=10001,mode=0o700,kind=stat.S_IFDIR):
  original=Path.lstat
  def lstat(path,*args,**kw):
   if path==state:return SimpleNamespace(st_mode=kind|mode,st_uid=uid,st_gid=10001)
   if path.is_relative_to(state):raise PermissionError('Private host children inaccessible to UID1003')
   return original(path,*args,**kw)
  return patch.object(Path,'lstat',lstat)
 def test_real_probe_argv_security_and_no_host_private_traversal(self):
  with tempfile.TemporaryDirectory() as raw:
   state=Path(raw)/'state';calls,command=self.runner();probe=adapters.StateProbe(command,'sha256:'+'a'*64,state/'config',state)
   with self.host(state):probe.preflight()
   self.assertTrue(probe.preflight_proven);self.assertFalse(probe.probe_cleanup_blocked)
   run=calls[0];self.assertEqual(run[run.index('--user')+1],'10001:10001')
   self.assertIn('type=bind,src='+str(state)+',dst=/state,readonly',run)
   for flag,value in [('--network','none'),('--cap-drop','ALL'),('--security-opt','no-new-privileges')]:self.assertEqual(run[run.index(flag)+1],value)
   self.assertIn('--read-only',run);self.assertIn(adapters.STATE_PREFLIGHT,run)
   self.assertEqual(len(probe.probe_events),1);self.assertTrue(probe.probe_events[0]['observed_absent'])
 def test_compose_start_preflights_before_up_without_host_children_access(self):
  with tempfile.TemporaryDirectory() as raw:
   work=Path(raw);state=work/'state';calls,command=self.runner()
   adapter=adapters.Compose(command,ROOT,work,'sha256:'+'a'*64,'adhd-acme-test',work/'seed',state,'10.231.240.1',18866)
   with self.host(state),patch.object(adapter,'observe',return_value={'owned':True}):self.assertEqual(adapter.start(),{'owned':True})
   probe_index=next(i for i,v in enumerate(calls) if v[1]=='run');up_index=next(i for i,v in enumerate(calls) if 'up' in v)
   self.assertLess(probe_index,up_index);self.assertTrue(adapter.state_probe.preflight_proven)
 def test_wrong_success_shape_never_becomes_preflight_success(self):
  with tempfile.TemporaryDirectory() as raw:
   state=Path(raw)/'state'
   for output in [b'',b'ADHD_STATE_PREFLIGHT uid=0 gid=0 private=ok\n',SUCCESS+b'extra']:
    calls,command=self.runner(output=output);probe=adapters.StateProbe(command,'sha256:'+'a'*64,state/'config',state)
    with self.host(state),self.assertRaises(AssertionError):probe.preflight()
    self.assertFalse(probe.preflight_proven);self.assertEqual(len(probe.probe_events),1)
 def test_unknown_cleanup_keeps_primary_timeout_and_blocks_next_probe(self):
  with tempfile.TemporaryDirectory() as raw:
   state=Path(raw)/'state';original=subprocess.TimeoutExpired('owned probe',30);calls,command=self.runner(error=original,unknown=True)
   probe=adapters.StateProbe(command,'sha256:'+'a'*64,state/'config',state)
   with self.host(state),self.assertRaises(subprocess.TimeoutExpired) as error:probe.preflight()
   self.assertIs(error.exception,original);self.assertTrue(probe.probe_cleanup_blocked);self.assertFalse(probe.preflight_proven)
   self.assertTrue(probe.probe_events[0]['owned_name']);self.assertFalse(probe.probe_events[0]['observed_absent'])
   count=len(calls)
   with self.assertRaises(AssertionError):probe.preflight()
   self.assertEqual(count,len(calls))
 def test_host_state_root_wrong_uid_mode_or_symlink_fails_before_probe(self):
  with tempfile.TemporaryDirectory() as raw:
   state=Path(raw)/'state'
   for kw in [{'uid':1003},{'mode':0o755},{'kind':stat.S_IFLNK}]:
    calls,command=self.runner();probe=adapters.StateProbe(command,'sha256:'+'a'*64,state/'config',state)
    with self.host(state,**kw),self.assertRaises(AssertionError):probe.preflight()
    self.assertEqual(calls,[])
 def test_seed_modes_set_while_owner_then_chown_without_extra_capabilities(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);seed=root/'seed';state=root/'state';seed.mkdir();state.mkdir()
   (seed/'hub.json').write_text(json.dumps({'host':'0.0.0.0','port':8766,'store_path':'/data/hub.dets','matcher':None,'eventing':{'enabled':False},'projects':[{'settings':{}}]}))
   calls,command=self.runner(output=b'')
   probe=adapters.SeedProbe(command,'sha256:'+'a'*64,seed,state);probe.initialize()
   run=calls[0];caps=[run[i+1] for i,v in enumerate(run) if v=='--cap-add']
   self.assertEqual(caps,['CHOWN','DAC_OVERRIDE']);self.assertIn('--cap-drop',run);self.assertNotIn('FOWNER',run)
   program=run[-1]
   self.assertLess(program.index('find /state -type d -exec chmod 700'),program.index('chown -R 10001:10001'))
   self.assertLess(program.index('find /state -type f -exec chmod 600'),program.index('chown -R 10001:10001'))
   self.assertTrue(program.endswith('chown -R 10001:10001 /state'));self.assertTrue(probe.probe_events[0]['observed_absent'])
 def test_preflight_script_checks_complete_private_state(self):
  body=adapters.STATE_PREFLIGHT
  for required in ['id -u','id -g','/state /state/config /state/data','test ! -L','10001:10001:700','10001:10001:600','test -f','stat -c %h','/state/config/hub.json','/state/config/directory-root.pem']:self.assertIn(required,body)
  self.assertNotIn('chmod',body);self.assertNotIn('chown',body)
if __name__=='__main__':unittest.main()
