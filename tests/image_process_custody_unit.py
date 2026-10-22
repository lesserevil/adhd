#!/usr/bin/env python3
"""Pure process/mapping custody checks. No Docker, processes, or signals run."""
import copy,hashlib,json,os
from pathlib import Path
import subprocess,tempfile,unittest
from unittest.mock import patch
import image_eventing_fault as m

class Custody(unittest.TestCase):
 def exercise(self,mutation=None,expect=True):
  with tempfile.TemporaryDirectory() as directory:
   library=Path(directory)/'observer.so';library.write_bytes(b'known library bytes');info=library.stat()
   digest=hashlib.sha256(library.read_bytes()).hexdigest();pid=23456;cid='a'*64;image='sha256:'+'b'*64;target='/adhd-test/observer.so'
   row={'Id':cid,'Image':image,'State':{'Pid':pid,'Running':True},'HostConfig':{'PidMode':'','ReadonlyRootfs':True},'Mounts':[{'Destination':target,'Source':str(library),'Type':'bind','RW':False}]}
   state={'maps':0,'stopped':False,'inspects':0};signals=[];closed=[];allmaps=[]
   mapsrow=f'1000-2000 r-xp 00000000 {os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x} {info.st_ino} {target}'
   class Proc:
    def __init__(self,path):self.path=path
    def read_text(self):
     index=state['maps']
     if self.path.endswith('/status'):return f'Uid:\t{os.getuid()} {os.getuid()} {os.getuid()} {os.getuid()}\nNSpid:\t{pid} 1\nState:\t'+('T' if state['stopped'] else 'S')+'\n'
     if self.path.endswith('/stat'):
      start='changed' if mutation=='start' and index>=2 else '100'
      if mutation=='after-start' and state['stopped']:start='changed'
      return f'{pid} (beam.smp) '+('0 '*19)+start
     if self.path.endswith('/maps'):
      state['maps']+=1;index=state['maps']
      selected=mapsrow
      if mutation=='mapping' and index>=2:selected=selected.replace(str(info.st_ino),str(info.st_ino+1))
      if mutation=='missing' and index>=2:selected=''
      if mutation=='deleted' and index>=2:selected+=' (deleted)'
      if mutation=='after-mapping' and state['stopped']:selected=selected.replace(str(info.st_ino),str(info.st_ino+1))
      text=selected+f'\n{index}000-{index}fff rw-p 00000000 00:00 0 [heap]\n3000-4000 r-xp 00000000 00:00 1 /lib/ld-musl-x86_64.so.1\n'
      allmaps.append(text);return text
     raise AssertionError(self.path)
    def read_bytes(self):
     assert self.path.endswith('/cmdline')
     extra=b'changed\0' if mutation=='cmdline' and state['maps'] else b''
     return b'beam.smp\0/app/hub.exs\0serve\0'+extra
   actual_path=m.Path;actual_close=m.os.close
   def path(value):return Proc(str(value)) if str(value).startswith('/proc/') else actual_path(value)
   def link(value):
    value=str(value)
    if value=='/proc/self/ns/pid':return 'pid:[100]'
    if value.endswith('/ns/pid'):return 'pid:[changed]' if mutation=='namespace' and state['maps'] else 'pid:[200]'
    if value.endswith('/exe'):return '/changed/beam.smp' if mutation=='executable' and state['maps'] else '/usr/bin/beam.smp'
    raise AssertionError(value)
   def docker(*args,**kwargs):
    assert args==('inspect',cid);state['inspects']+=1;current=copy.deepcopy(row)
    if mutation=='mount':current['Mounts'][0]['RW']=True
    if mutation=='image' and state['stopped']:current['Image']='foreign'
    if mutation=='pid' and state['stopped']:current['State']['Pid']+=1
    return subprocess.CompletedProcess([],0,json.dumps([current]).encode(),b'')
   def signal(fd,sig):signals.append((fd,sig));state['stopped']=True
   def close(fd):
    if fd==98765:closed.append(fd)
    else:actual_close(fd)
   with patch.object(m,'Path',side_effect=path),patch.object(m,'docker',side_effect=docker),patch.object(m.os,'readlink',side_effect=link),patch.object(m.os,'pidfd_open',return_value=98765),patch.object(m.os,'close',side_effect=close),patch.object(m.signal,'pidfd_send_signal',side_effect=signal):
    if expect:
     result=m.stop_owned_process(cid,image,{'pid':1},target,'beam.smp',['/app/hub.exs','serve'],digest)
     self.assertEqual(result['process_maps_witness_phase'],'kernel-stopped');self.assertEqual(result['process_maps_sha256'],hashlib.sha256(allmaps[-1].encode()).hexdigest());self.assertEqual(len(signals),1);self.assertEqual(closed,[98765]);return result
    with self.assertRaises(AssertionError):m.stop_owned_process(cid,image,{'pid':1},target,'beam.smp',['/app/hub.exs','serve'],'0'*64 if mutation=='hash' else digest)
    if mutation in ('after-start','after-mapping','image','pid'):self.assertEqual(len(signals),1)
    else:self.assertFalse(signals)
 def test_all_custody_callers_pass_expected_library_hash(self):
  import ast
  for name in ('image_eventing_fault.py','image_eventing_runtime.py','image_filesystem_fault.py','image_filesystem_abi.py'):
   tree=ast.parse(Path(__file__).with_name(name).read_text());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Name) and n.func.id=='stop_owned_process') or (isinstance(n.func,ast.Attribute) and n.func.attr=='stop_owned_process'))]
   self.assertTrue(calls,name)
   for call in calls:self.assertEqual(len(call.args),7,name)
 def test_unrelated_live_heap_maps_may_change(self):self.exercise()
 def test_start_time_change_denied(self):self.exercise('start',False)
 def test_namespace_change_denied(self):self.exercise('namespace',False)
 def test_executable_change_denied(self):self.exercise('executable',False)
 def test_cmdline_change_denied(self):self.exercise('cmdline',False)
 def test_mapping_inode_change_denied(self):self.exercise('mapping',False)
 def test_missing_library_mapping_denied(self):self.exercise('missing',False)
 def test_deleted_library_mapping_denied(self):self.exercise('deleted',False)
 def test_start_time_rechecked_after_stop(self):self.exercise('after-start',False)
 def test_library_mapping_rechecked_after_stop(self):self.exercise('after-mapping',False)
 def test_image_rechecked_after_stop(self):self.exercise('image',False)
 def test_pid_rechecked_after_stop(self):self.exercise('pid',False)
 def test_readwrite_mount_denied(self):self.exercise('mount',False)
 def test_wrong_library_bytes_denied(self):self.exercise('hash',False)

if __name__=='__main__':unittest.main()
