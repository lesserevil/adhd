"""Real startup proof race and malformed-checkpoint rejection before decisions."""
import argparse,hashlib,json,os,re,signal,socket,stat,subprocess,time
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stamp(p):
 s=p.lstat();return (sha(p),s.st_mode,s.st_ino,s.st_dev,s.st_uid,s.st_nlink)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('hub','legacy-config','work','report'):p.add_argument('--'+k,type=Path,required=True)
 a=p.parse_args();a.hub=a.hub.resolve();a.legacy_config=a.legacy_config.resolve();a.work=a.work.resolve();assert not a.work.exists();a.work.mkdir(parents=True,mode=0o700)
 original=json.loads(a.legacy_config.read_text());origin=Path(original['store_path']);before=stamp(origin);library=a.work/'fault.so'
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-O2',str(Path(__file__).with_name('local_legacy_fault.c')),'-o',str(library),'-ldl'],check=True)
 checks=[]
 def fixture(name):
  root=a.work/name;root.mkdir(mode=0o700);data=root/'hub.dets';data.write_bytes(origin.read_bytes());data.chmod(0o664)
  with socket.socket()as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  c={**original,'store_path':str(data),'port':port};config=root/'config.json';config.write_text(json.dumps(c));config.chmod(0o600)
  return root,data,config
 def start(root,config,env):
  out=(root/'stdout.log').open('w');err=(root/'stderr.log').open('w')
  return subprocess.Popen(['elixir',str(a.hub),json.dumps(['serve',str(config)])],env=env,stdout=out,stderr=err,start_new_session=True),out,err
 def no_decision(config,data,backups):
  paths=[str(config)+n for n in ('.project-upgrade','.transaction','.stores','.stores.marker','.recovery')]
  if backups:paths += [str(config)+'.before-projects',str(data)+'.before-projects']
  assert all(not Path(n).exists()for n in paths),'Untrusted startup published migration metadata'
 root,data,config=fixture('appearing-snapshot');source=stamp(data);cfg=stamp(config);snapshot=root/'snapshot.fixture'
 subprocess.run(['elixir',str(Path(__file__).with_name('local_legacy_snapshot.exs')),str(a.hub),str(config),str(snapshot)],check=True,capture_output=True,text=True)
 sentinel=root/'observed.json';env={**os.environ,'LD_PRELOAD':str(library),'ADHD_ADOPTION_TARGET':str(data)+'.before-projects','ADHD_ADOPTION_SENTINEL':str(sentinel)}
 process,out,err=start(root,config,env)
 try:
  end=time.monotonic()+90;observed=None
  while time.monotonic()<end:
   if sentinel.exists():
    try:observed=json.loads(sentinel.read_text())
    except json.JSONDecodeError:time.sleep(.005);continue
    state=Path('/proc/'+str(process.pid)+'/status').read_text()
    if re.search(r'^State:\s+T',state,re.M):break
   assert process.poll()is None,'Actual startup exited before requested backup boundary'
   time.sleep(.01)
  assert observed and observed['pid']==process.pid
  assert re.search(r'^State:\s+T',Path('/proc/'+str(process.pid)+'/status').read_text(),re.M)
  assert Path(str(data)+'.before-projects').read_bytes()==data.read_bytes()
  no_decision(config,data,False)
  appeared=Path(str(data)+'.snapshot');appeared.write_bytes(snapshot.read_bytes());appeared.chmod(0o600);appearance=stamp(appeared)
  os.killpg(process.pid,signal.SIGCONT);process.wait(timeout=45);assert process.returncode!=0
  no_decision(config,data,False);assert stamp(data)==source and stamp(config)==cfg and stamp(appeared)==appearance
  checks.append({'name':'actual-successful-backup-rename-stopped-before-prepared-marker-rejects-appearing-valid-snapshot-after-SIGCONT','passed':True,'observer':observed,'kernel_state_before_injection':'stopped','exit_code':process.returncode,'decision_absent':True})
 finally:
  if process.poll()is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
  out.close();err.close()
 root,data,config=fixture('malformed-checkpoint');payload=bytearray(data.read_bytes());payload[0]^=1;data.write_bytes(payload);source=stamp(data);cfg=stamp(config)
 process,out,err=start(root,config,os.environ.copy())
 try:
  process.wait(timeout=90);assert process.returncode!=0
  no_decision(config,data,True);assert stamp(data)==source and stamp(config)==cfg
  checks.append({'name':'actual-malformed-native-bytes-reject-before-any-config-or-store-backup-marker-decision-writer','passed':True,'exit_code':process.returncode,'before_projects_backups_absent':True})
 finally:
  if process.poll()is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
  out.close();err.close()
 assert stamp(origin)==before
 result={'schema':'adhd/local-legacy-startup-races@1','passed':True,'lifecycle_admitted':False,'artifact_sha256':sha(a.hub),'harness_sha256':sha(Path(__file__)),'observer_sha256':sha(Path(__file__).with_name('local_legacy_fault.c')),'snapshot_fixture_harness_sha256':sha(Path(__file__).with_name('local_legacy_snapshot.exs')),'original_checkpoint_sha256':before[0],'original_checkpoint_unchanged':True,'checks':checks,'limitations':['Diagnostic developmentnative proof, not formalartifact/imageadmission.','Observer onlystops afterreal successfulbackup rename; no I/O successbody fabricated.','Tests requireexclusive ownstorage fixture; no same-UIDadversary claim.','Nativeopenerzero provenseparately bycomponent+independentreview traces, notinstrumented inthis whole-service run.']}
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n');print('PASS local startup races',len(checks),flush=True)
if __name__=='__main__':main()
