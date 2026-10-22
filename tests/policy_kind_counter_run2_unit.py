"""Mocked controller/source guards. No compiler/native/Docker execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import policy_kind_counter_run2 as run

class Guards(unittest.TestCase):
 def test_strict_absence_case_and_contradictions(self):
  def row(err,out='',code=1):return {'stderr':err,'stdout':out,'exit_code':code}
  self.assertTrue(run.missing(row('error: no such object: MixedName'),'MixedName'))
  self.assertTrue(run.missing(row('Error: No such container: MixedName','[]'),'MixedName'))
  for r in (row('error: no such object: mixedname'),row('error: no such object: MixedName\ndaemon unavailable'),row('daemon unavailable'),row('error: no such object: MixedName','{}'),row('error: no such object: MixedName',code=2)):
   self.assertFalse(run.missing(r,'MixedName'))
 def runner(self):
  r=run.Runner.__new__(run.Runner);r.plan={'image':run.IMAGE,'nonce':'a'*32};return r
 def object(self):
  return {'Id':'1'*64,'Name':'/owned','Image':run.IMAGE,'Config':{'Labels':{'adhd-counter19-owner':'a'*32},'User':'1000:1000','Entrypoint':['/probe/counter-probe'],'Cmd':['--image-fact'],'Healthcheck':{'Test':['NONE']}},'HostConfig':{'ReadonlyRootfs':True,'NetworkMode':'none','Memory':201326592,'PidsLimit':64,'NanoCpus':1000000000,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'Privileged':False,'PidMode':'','IpcMode':'private','UsernsMode':''},'Mounts':[{'Destination':'/probe/counter-probe','Source':'/owned/probe','RW':False,'Type':'bind'}]}
 def item(self):return {'id':'1'*64,'name':'owned','mounts':[('/owned/probe','/probe/counter-probe')],'command':['--image-fact'],'observed_absent':False}
 def test_actual_command_security_and_mounts(self):
  r=self.runner();item=self.item();value=self.object();self.assertIs(r.owned(value,item),value)
  for change in (lambda x:x['Config'].update(Cmd=['--other']),lambda x:x['HostConfig'].update(Privileged=True),lambda x:x['HostConfig'].update(PidMode='host'),lambda x:x['HostConfig'].update(CapAdd=['SYS_PTRACE']),lambda x:x['Mounts'][0].update(RW=True),lambda x:x.update(Image='sha256:'+'f'*64)):
   bad=copy.deepcopy(value);change(bad)
   with self.assertRaises(AssertionError):r.owned(bad,item)
 def test_initial_inspect_failure_still_removes_and_inspects(self):
  r=self.runner();item=self.item();r.inspect=Mock(side_effect=[RuntimeError('daemon'),None,None]);r.docker=Mock(return_value={'exit_code':0,'stdout':'','stderr':''})
  with self.assertRaisesRegex(RuntimeError,'daemon'):r.cleanup(item)
  self.assertTrue(item['observed_absent']);self.assertEqual(r.inspect.call_count,3);self.assertEqual(r.docker.call_args.args[0],['rm','--force','--volumes','1'*64])
 def test_remove_failure_still_gets_independent_absence(self):
  r=self.runner();item=self.item();r.inspect=Mock(side_effect=[self.object(),None,None]);r.docker=Mock(side_effect=RuntimeError('remove timeout'))
  with self.assertRaisesRegex(RuntimeError,'remove timeout'):r.cleanup(item)
  self.assertTrue(item['observed_absent']);self.assertEqual(r.inspect.call_count,3)
 def test_foreign_not_removed_and_unknown_not_success(self):
  r=self.runner();item=self.item();foreign=self.object();foreign['Config']['Labels']['adhd-counter19-owner']='b'*32
  r.inspect=Mock(return_value=foreign);r.docker=Mock()
  with self.assertRaises(AssertionError):r.cleanup(item)
  r.docker.assert_not_called();self.assertFalse(item['observed_absent'])
 def test_input_empty_directory_redirect_tamper_detection(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'driver').write_text('one');before=run.inventory(p);(p/'empty').mkdir();self.assertNotEqual(run.inventory(p),before);(p/'empty').rmdir();(p/'driver').write_text('two');self.assertNotEqual(run.inventory(p),before)
   (p/'redirect').symlink_to(p,target_is_directory=True)
   with self.assertRaises(AssertionError):run.inventory(p)
 def test_source_uses_in_container_same_UID_only(self):
  source=Path(run.__file__).read_text();self.assertIn("['exec','--user','1000:1000',item['id']",source)
  self.assertNotIn('/proc/'+"PID",source);self.assertNotIn('os.pidfd_open',source);self.assertNotIn('pidfd_send_signal(',source)
  c=Path(run.__file__).with_name('policy_kind_counter_probe3.c').read_text()
  for expected in ('proc_read(1, "stat"','SYS_pidfd_open, 1, 0','SYS_pidfd_send_signal, pfd, SIGCONT','resume-identity-changed','resume-same-container-view','resume-original-release-deadline','resume-ordered-env-hash'):
   self.assertIn(expected,c)
  self.assertEqual(c.count('SYS_pidfd_send_signal'),1)
 def test_execute_not_ready_and_once_boundary(self):
  with tempfile.TemporaryDirectory()as d:
   work=Path(d);(work/'plan.json').write_text('{}');plan={'execution_ready':False}
   with self.assertRaises(AssertionError),patch.object(run.subprocess,'Popen',side_effect=AssertionError('process forbidden')):run.execute(work,plan)
   self.assertFalse((work/'EXECUTION_STARTED').exists())
   plan={'execution_ready':True,'driver_sha256':'x','scope':'mock','cases':[{'mode':'--selftest','exit_code':0}],'inputs':{}}
   fake=Mock();fake.ledger=[];fake.used=[0,0];fake.run.side_effect=RuntimeError('injected first native failure')
   with patch.object(run.sys,'flags',type('Flags',(),{'isolated':True,'no_site':True})()),patch.object(run.sys,'dont_write_bytecode',True),patch.object(run,'Runner',return_value=fake),patch.object(run,'inventory',return_value={}):
    with self.assertRaisesRegex(RuntimeError,'injected'):run.execute(work,plan)
    self.assertTrue((work/'EXECUTION_STARTED').exists());self.assertFalse(json.loads((work/'result.json').read_text())['passed'])
    with self.assertRaises(FileExistsError):run.execute(work,plan)
   self.assertEqual(fake.run.call_count,1)


class ZeroOffsets(unittest.TestCase):
 def test_exact_zero_parser_and_nonzero_unknown_malformed(self):
  good=b'monotonic           0         0\nboottime            0         0\n'
  self.assertEqual(run.zero_offsets(good),{'monotonic':[0,0],'boottime':[0,0]})
  for bad in (good.replace(b'0',b'1',1),good.replace(b'0',b'-0',1),good.replace(b'0',b'+0',1),b'monotonic 0 0\n',good+b'monotonic 0 0\n',good.replace(b'boottime',b'other'),good.replace(b'monotonic ',b'monotonic\v'),good+b'\0'):
   with self.assertRaises(AssertionError):run.zero_offsets(bad)
 def fact(self,ns=4026534066):
  return {'kind':'clock-fact','time_namespace_inode':ns,'time_for_children_namespace_inode':ns,'timens_offsets_zero':True,'timens_offsets':{'monotonic':[0,0],'boottime':[0,0]},'monotonic_ns':150,'boottime_ns':250}
 def test_distinct_namespaces_aligned_zero_are_accepted(self):
  before={'monotonic_ns':100,'boottime_ns':200};after={'monotonic_ns':200,'boottime_ns':300}
  self.assertTrue(run.aligned_clock(self.fact(4026531834),before,after,100))
  self.assertTrue(run.aligned_clock(self.fact(4026534066),before,after,100))
  # Current-vs-children must match WITHIN a process because the offset file
  # describes children; no equality requirement ACROSS processes is used.
  bad=self.fact();bad['time_for_children_namespace_inode']+=1
  with self.assertRaises(AssertionError):run.aligned_clock(bad,before,after,100)
 def test_bracket_and_offsets_failure_never_infers_adjustment(self):
  before={'monotonic_ns':100,'boottime_ns':200};after={'monotonic_ns':200,'boottime_ns':300}
  for field,value in (('monotonic_ns',99),('boottime_ns',301),('timens_offsets_zero',False),('timens_offsets',{'monotonic':[1,0],'boottime':[0,0]})):
   bad=self.fact();bad[field]=value
   with self.assertRaises(AssertionError):run.aligned_clock(bad,before,after,100)
  with self.assertRaises(AssertionError):run.aligned_clock(self.fact(),before,after,99)
 def test_successor_source_offsets_and_namespace_identity(self):
  base=Path(run.__file__).parent;gate=(base/'policy_kind_counter2.c').read_text();probe=(base/'policy_kind_counter_probe3.c').read_text()
  self.assertIn('current == children',gate);self.assertIn('"timens_offsets"',gate)
  self.assertNotIn('v.timens==namespace_inode(getpid(),"time")',gate)
  self.assertIn('a->timens==b->timens&&a->observer_timens==b->observer_timens',gate)
  self.assertIn('zero_time_namespace(1)',probe);self.assertIn('zero_time_namespace(getpid())',probe)
  self.assertIn('before.timens == after.timens && before.observer_timens == after.observer_timens',probe)
  self.assertNotIn('expected_time',probe)
  self.assertIn('release_deadline - host_window_begin == 10 * NS',probe)
  self.assertIn('now_ns() < release_deadline',probe)
  self.assertIn('pidfd-SIGCONT',probe)

if __name__=='__main__':unittest.main()
