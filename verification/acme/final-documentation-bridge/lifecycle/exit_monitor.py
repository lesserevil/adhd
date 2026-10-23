"""Observe only the exact orphaned CLI's kernel exit event; never trace children or memory."""
import ctypes,hashlib,json,os,signal,sys
from pathlib import Path
pid=745807
proc=Path('/proc')/str(pid)
def identity():
 assert proc.stat().st_uid==1003
 assert (proc/'stat').read_text().rsplit(')',1)[1].split()[19]=='29172594'
 args=(proc/'cmdline').read_bytes().split(b'\0');assert args[-1]==b'';args=args[:-1]
 assert args[:3]==[b'/home/horde/src/adhd/_build/federation/litai/bin/python',b'/home/horde/src/adhd/_build/federation/litai/bin/litai',b'rebuild']
 assert b'sha256:7f15828d71f643bc5f32ffc8ec5465f225039f4c2801b351bc748b25ada8b354' in args
 return hashlib.sha256(b'\0'.join(args)).hexdigest()
assert os.getuid()==os.geteuid()==0
argsha=identity()
lib=ctypes.CDLL(None,use_errno=True);lib.ptrace.restype=ctypes.c_long
SEIZE,CONT,DETACH,GETEVENTMSG=0x4206,7,17,0x4201
attached=False
try:
 assert lib.ptrace(SEIZE,pid,0,0x40)==0,ctypes.get_errno()
 attached=True
 assert identity()==argsha
 print(json.dumps({'ready':True,'pid':pid,'start_ticks':'29172594','argv_sha256':argsha,'kernel_exit_events_only':True,'trace_children':False,'read_or_write_process_memory':False,'exitkill_option':False}),flush=True)
 while True:
  observed,status=os.waitpid(pid,0x40000000)
  assert observed==pid
  if os.WIFEXITED(status)or os.WIFSIGNALED(status):
   attached=False
   print(json.dumps({'terminal_observed':True,'actual_wait_status':status,'actual_exit_code':os.waitstatus_to_exitcode(status)}),flush=True)
   break
  assert os.WIFSTOPPED(status)
  event=status>>16
  if event==6:
   value=ctypes.c_ulong()
   assert lib.ptrace(GETEVENTMSG,pid,0,ctypes.byref(value))==0,ctypes.get_errno()
   print(json.dumps({'kernel_exit_event':True,'actual_wait_status':value.value,'actual_exit_code':os.waitstatus_to_exitcode(value.value)}),flush=True)
   assert lib.ptrace(CONT,pid,0,0)==0,ctypes.get_errno()
  else:
   sig=os.WSTOPSIG(status)
   assert event==0,('unexpected_ptrace_event',event)
   print(json.dumps({'forward_original_signal':sig}),flush=True)
   assert lib.ptrace(CONT,pid,0,sig)==0,ctypes.get_errno()
finally:
 if attached:
  # Exiting this observer detaches automatically; EXITKILL was deliberately never set.
  print(json.dumps({'observer_ended_before_terminal':True,'tracee_not_killed':True}),flush=True)
