"""Pure production-UID Compose VM custody; no Docker/process/signal starts."""
import copy,json,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import acme_platform_adapters as adapter

def rawstat(pid,ticks='12345'):
 fields=['S']+['0']*19;fields[19]=ticks
 return (str(pid)+' (beam.smp) '+' '.join(fields)+'\n').encode()
def row():
 return {'Id':'a'*64,'Name':'/adhd-acme-owned-hub-1','Image':'sha256:'+'b'*64,'RestartCount':0,
  'State':{'Running':True,'Pid':87654,'StartedAt':'fixed'},
  'Config':{'User':'10001:10001','Entrypoint':adapter.vm.ENTRYPOINT,'Cmd':adapter.vm.COMMAND},
  'HostConfig':{'PidMode':'','ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true']}}
class Custody(unittest.TestCase):
 def execute(self,change=None,ns_ticks='12345',host_ticks='12345'):
  value=row();calls=[];stat_reads=[]
  def read(path):
   self.assertEqual(str(path),'/proc/87654/stat');stat_reads.append(1);return rawstat(87654,host_ticks)
  def command(argv,**kw):
   calls.append(argv);self.assertGreater(kw['timeout'],0);self.assertLessEqual(kw['timeout'],30)
   if argv[1]=='inspect':
    newer=copy.deepcopy(value)
    if change:change(newer)
    return subprocess.CompletedProcess(argv,0,json.dumps([newer]).encode(),b'')
   self.assertEqual(argv[:5],['docker','exec','--user','10001:10001','a'*64])
   self.assertIn(argv[5],['/bin/cat','/bin/busybox'])
   if argv[-1]=='/proc/1/exe':self.assertEqual(argv[5:],['/bin/busybox','readlink','/proc/1/exe'])
   else:self.assertEqual(argv[5],'/bin/cat')
   raw={'/proc/1/stat':rawstat(1,ns_ticks),'/proc/1/cmdline':b'beam\0/runtime/adhd/boot.exs\0/app/hub.exs\0["serve","/config/hub.json"]\0','/proc/1/exe':b'/usr/lib/erlang/erts/bin/beam.smp\n'}[argv[-1]]
   return subprocess.CompletedProcess(argv,0,raw,b'')
  with patch.object(Path,'read_bytes',read),patch.object(os,'readlink',side_effect=PermissionError('ForeignUID forbidden')):
   proof=adapter.compose_vm_custody(command,value,value['Image'])
  self.assertEqual(len(stat_reads),2);self.assertEqual(len(calls),5)
  return proof
 def test_production_uid_magiclink_denied_on_host_works_via_exact_cid_exec(self):
  proof=self.execute();self.assertEqual(proof['process']['pid'],87654)
  self.assertEqual(proof['namespace_process']['pid'],1);self.assertTrue(proof['pid1_start_equals_host_start'])
  self.assertEqual(proof['exec_user'],'10001:10001')
 def test_namespace_host_start_disagreement_rejects(self):
  with self.assertRaises(AssertionError):self.execute(ns_ticks='99999')
 def test_docker_replacement_restart_or_security_change_rejects(self):
  for change in [lambda r:r['State'].update(Pid=999),lambda r:r['State'].update(StartedAt='new'),lambda r:r.update(RestartCount=1),lambda r:r['Config'].update(User='0:0'),lambda r:r['Config'].update(Entrypoint=['override']),lambda r:r['HostConfig'].update(CapDrop=[]),lambda r:r.update(Image='sha256:'+'c'*64)]:
   with self.assertRaises(AssertionError):self.execute(change)
if __name__=='__main__':unittest.main()
