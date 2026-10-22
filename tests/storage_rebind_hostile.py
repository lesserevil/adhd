#!/usr/bin/env python3
"""Real offline rebind CLI rejects hash-bound hostile checkpoints pre-decision."""
import argparse,hashlib,json,shutil,struct,subprocess,sys
from pathlib import Path
from storage_rebind import copied,command_for,sha,target_arguments
from image_rebind_runtime import ImageRebindRuntime

def tree(root):
 return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def word(b,p):return struct.unpack_from('>I',b,p)[0]
def put(b,p,v):return b[:p]+struct.pack('>I',v)+b[p+4:]
def seal(b):return b[:168]+hashlib.md5(b[12:168]).digest()+b[184:]
def missing(b):
 fl=word(b,0);size=word(b,fl);out=b[:fl]+b[fl+size:-4]
 return out+struct.pack('>I',len(out)+4-word(b,184))
def main():
 ap=argparse.ArgumentParser(__doc__);target_arguments(ap);ap.add_argument('--artifact',type=Path,required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--vectors',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
 work=a.work.resolve();work.mkdir(parents=True,exist_ok=False);work.chmod(0o700)
 command=ImageRebindRuntime(a,work) if a.image else json.loads(a.command)
 cases=[('actual-state-missing-free-block',missing),('actual-state-forged-arena',lambda b:put(put(b,184,5448),len(b)-4,len(b)-5448)),('actual-state-directory-cycle',lambda b:put(b,word(b,312),word(b,312))),('valid-compressed-etf',lambda _: (a.vectors/'compressed-etf.dets').read_bytes()),('valid-executable-etf',lambda _: (a.vectors/'executable-etf.dets').read_bytes()),('live-padding-free-block',lambda _: (a.vectors/'free-block-inside-live-padding.dets').read_bytes())]
 results=[]
 for name,mutate in cases:
  root=work/name;p=copied(a.source,root);req=command_for(p,'hostile-'+name);checkpoint=Path(req['stores'][0]['store_path']);original=checkpoint.read_bytes();hostile=mutate(original);checkpoint.write_bytes(hostile);checkpoint.chmod(0o600)
  req['stores'][0]['checkpoint_sha256']=sha(checkpoint);before=tree(root)
  r=command.run(['rebind-storage',req],timeout=150) if a.image else subprocess.run(command+[json.dumps(['rebind-storage',req],separators=(',',':'))],capture_output=True,timeout=150)
  (work/(name+'.stdout')).write_bytes(r.stdout);(work/(name+'.stderr')).write_bytes(r.stderr)
  assert r.returncode==1 and not r.stdout,(name,r.returncode,r.stdout,r.stderr[-1500:])
  err=json.loads(r.stderr);assert set(err)=={'error'} and set(err['error'])=={'code','message'} and err['error']['code']=='RESTORE_CONFLICT',(name,err)
  assert not Path(str(p)+'.transaction').exists(),name
  after=tree(root);assert before==after,(name,'copied set mutated')
  results.append({'id':name,'passed':True,'error':err,'original_checkpoint_sha256':hashlib.sha256(original).hexdigest(),'hostile_checkpoint_sha256':sha(checkpoint),'explicit_request_binds_hostile_hash':True,'no_durable_decision':True,'all_copied_bytes_unchanged':True,'copied_file_count':len(before),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest()})
  print('PASS',name,flush=True)
 output={'schema':'adhd/storage-rebind-hostile-check@1','passed':True,'scope':'Actual public offline CLI rejections before durable decision; no native-opener tracing claim (separate pure parser vectors prove that boundary)','artifact_sha256':sha(a.artifact),'harness_sha256':sha(__file__),'shared_fixture_helper_sha256':sha(Path(__file__).with_name('storage_rebind.py')),'checks':results}
 if a.image:output['runtime']=command.evidence()
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(output,indent=2)+'\n');print('PASS',len(results),'hostile checkpoint CLI groups',flush=True)
if __name__=='__main__':main()
