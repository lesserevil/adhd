#!/usr/bin/env python3
"""Construct one foreign-owned copy with a confined Docker CHOWN-only helper."""
import argparse,hashlib,json,os,stat,subprocess,tempfile
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--artifact',type=Path,required=True);p.add_argument('--configuration',type=Path,required=True);p.add_argument('--helper-image',required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 original=Path(json.loads(a.configuration.read_text())['store_path']);project=json.loads(a.configuration.read_text())['project_id']
 original_stat=original.stat();original_bytes=original.read_bytes();original_identity=(original_stat.st_dev,original_stat.st_ino,original_stat.st_uid,original_stat.st_gid,original_stat.st_mode,original_stat.st_nlink,original_stat.st_mtime_ns,original_stat.st_ctime_ns)
 a.work.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='owner-',dir=a.work)).resolve();root.chmod(0o700)
 checkpoint=root/'probe.dets';checkpoint.write_bytes(original_bytes);checkpoint.chmod(0o664);owner=checkpoint.stat()
 inspected=subprocess.run(['docker','image','inspect',a.helper_image,'--format','{{.Id}}'],check=True,capture_output=True,text=True).stdout.strip();assert inspected==a.helper_image
 helper_base=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--cap-add','CHOWN','--user','0:0','--security-opt','no-new-privileges','--mount',f'type=bind,src={checkpoint},dst=/probe.dets','--entrypoint','/bin/sh',inspected,'-c','chown "$1:$2" /probe.dets','fixture-owner']
 observed=[];restored=False;probe=None
 try:
  foreign=65534 if owner.st_uid!=65534 else 65533
  changed=subprocess.run(helper_base+[str(foreign),str(foreign)],capture_output=True,text=True,timeout=30)
  observed.append({'action':'assign-foreign-owner','returncode':changed.returncode})
  if changed.returncode:raise RuntimeError('Confined ownership helper failed; privileges not broadened')
  actual=checkpoint.stat();assert actual.st_uid==foreign and actual.st_uid!=os.getuid();assert checkpoint.read_bytes()==original_bytes
  probe=subprocess.run(['elixir',str(Path(__file__).with_suffix('.exs').resolve()),str(a.artifact.resolve()),str(checkpoint),project,str(root/'native.json')],capture_output=True,text=True,timeout=150)
  (root/'native.stdout').write_text(probe.stdout);(root/'native.stderr').write_text(probe.stderr)
 finally:
  cleanup=subprocess.run(helper_base+[str(owner.st_uid),str(owner.st_gid)],capture_output=True,text=True,timeout=30)
  observed.append({'action':'restore-original-owner','returncode':cleanup.returncode});restored=cleanup.returncode==0 and checkpoint.stat().st_uid==owner.st_uid and checkpoint.stat().st_gid==owner.st_gid
 r=json.loads((root/'native.json').read_text()) if (root/'native.json').exists() else {'passed':False,'probe_report_missing':True}
 now=original.stat();unchanged=original.read_bytes()==original_bytes and original_identity==(now.st_dev,now.st_ino,now.st_uid,now.st_gid,now.st_mode,now.st_nlink,now.st_mtime_ns,now.st_ctime_ns)
 r.update(helper_image=inspected,helper_scope='networknone/read-only/capdropALL+CHOWN/user0; exactly one fresh disposable file bind, no original or parent directory mount',helper_lifecycle=observed,owner_restored=restored,original_checkpoint_unchanged=unchanged,orchestrator_sha256=sha(Path(__file__)),helper_docker_argv_shape=helper_base[:helper_base.index('--mount')]+['--mount','type=bind,src=OWNED_COPY,dst=/probe.dets','--entrypoint','/bin/sh',inspected,'-c','chown "$1:$2" /probe.dets','fixture-owner','UID','GID'])
 r['passed']=r['passed'] and restored and unchanged and probe is not None and probe.returncode==0
 if restored:checkpoint.unlink()
 r['owned_checkpoint_copy_removed']=not checkpoint.exists();a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k] for k in ['passed','observed_foreign_uid','server_uid','owner_restored','original_checkpoint_unchanged','owned_checkpoint_copy_removed']}));assert r['passed']
if __name__=='__main__':main()
