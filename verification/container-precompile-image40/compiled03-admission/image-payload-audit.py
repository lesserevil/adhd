from pathlib import Path,PurePosixPath
import subprocess,hashlib,io,tarfile,json,sys,re
from uuid import uuid4
sys.path.insert(0,str(Path('tests').resolve()))
from container_fixture import OwnedImage
root=Path('_build/roadmap/final/container-context-40-compiled03')
image=Path('_build/roadmap/final/compiled40-image03.iid').read_text().strip()
assert re.fullmatch('sha256:[a-f0-9]{64}',image)
expected=(root/'manifest.json').read_bytes();manifest=json.loads(expected)
assert manifest['schema']=='adhd/container-inputs@1'
assert manifest['files']['hub.exs']=='c635c2429c9af646944f740194e841260ed6e102e5e148272a247883ed66ccd3'
name='adhd-image-audit-'+uuid4().hex[:16];identifier=None;result=None
try:
 identifier=subprocess.check_output(['docker','create','--name',name,'--network','none','--read-only',image],text=True).strip()
 assert re.fullmatch('[a-f0-9]{64}',identifier)
 observed=json.loads(subprocess.check_output(['docker','inspect',identifier],text=True))[0]
 assert observed['Image']==image and observed['Name']=='/'+name and observed['State']['Status']=='created'
 body=subprocess.check_output(['docker','cp',identifier+':/app/.','-']);assert len(body)<=32*1024*1024
 files={};seen=set()
 with tarfile.open(fileobj=io.BytesIO(body)) as archive:
  for item in archive.getmembers():
   p=PurePosixPath(item.name);assert not p.is_absolute() and '..' not in p.parts
   assert item.name not in seen;seen.add(item.name)
   if item.isdir():continue
   assert item.isfile() and item.size<=8*1024*1024,'Nonregular or oversized app payload'
   key=p.as_posix().removeprefix('./');assert key not in files
   files[key]=archive.extractfile(item).read()
 assert files.pop('manifest.json')==expected
 targets={k:v for k,v in manifest['files'].items() if k!='Dockerfile'}
 assert set(files)==set(targets)
 assert all(hashlib.sha256(files[k]).hexdigest()==h for k,h in targets.items())
 assert hashlib.sha256((root/'Dockerfile').read_bytes()).hexdigest()==manifest['files']['Dockerfile']
 specs=sum(k.startswith('specification/') for k in files);assert specs==33
 cache_body=subprocess.check_output(['docker','cp',identifier+':/runtime/adhd','-'])
 runtime_body=subprocess.check_output(['docker','cp',identifier+':/runtime','-'])
 with tarfile.open(fileobj=io.BytesIO(runtime_body)) as rt:
  parent=rt.getmember('runtime')
  assert parent.isdir() and parent.uid==parent.gid==0 and parent.mode==0o755 and parent.mtime==0
 cache={};metadata={}
 metadata['/runtime']={'mode':oct(parent.mode),'mtime':parent.mtime,'sha256':None}
 with tarfile.open(fileobj=io.BytesIO(cache_body)) as archive:
  for item in archive.getmembers():
   assert item.name not in cache and item.uid==item.gid==0
   assert item.isdir() or item.isfile()
   assert item.mode==(0o555 if item.isdir() else 0o444), (item.name, oct(item.mode), item.type)
   assert item.mtime==0, (item.name,item.mtime)
   cache[item.name]=archive.extractfile(item).read() if item.isfile() else None
   metadata[item.name]={'mode':oct(item.mode),'mtime':item.mtime,'sha256':hashlib.sha256(cache[item.name]).hexdigest() if item.isfile() else None}
 cm=json.loads(cache['adhd/manifest.json'])
 assert cm['source_sha256']==targets['hub.exs'] and cm['payload_manifest_sha256']==hashlib.sha256(expected).hexdigest()
 names=['Elixir.'+n for n in re.findall(r'^defmodule ([A-Za-z0-9_.]+) do$',files['hub.exs'].decode(),re.M)]
 assert cm['modules']==names and len(names)==59
 assert set(cache)=={'adhd','adhd/ebin','adhd/manifest.json','adhd/inputs.json','adhd/boot.exs','adhd/build.exs'}|{'adhd/ebin/'+n+'.beam' for n in names}
 assert set(cm['beams'])=={n+'.beam' for n in names}
 for n in names:assert hashlib.sha256(cache['adhd/ebin/'+n+'.beam']).hexdigest()==cm['beams'][n+'.beam']
 for n in ('boot','build'):assert hashlib.sha256(cache['adhd/'+n+'.exs']).hexdigest()==cm[n+'_sha256']==hashlib.sha256(Path('deploy/runtime/'+n+'.exs').read_bytes()).hexdigest()
 assert cache['adhd/inputs.json']==(root/'compiler-inputs.json').read_bytes()
 assert hashlib.sha256(cache['adhd/inputs.json']).hexdigest()==cm['inputs_sha256']
 Path('verification/container-precompile-image40/compiled03-admission/cache-manifest.json').write_bytes(cache['adhd/manifest.json'])
 Path('verification/container-precompile-image40/compiled03-admission/cache-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
 result={'schema' :'adhd/actual-image-payload-audit@1','passed':True,'image_id':image,'artifact_sha256':targets['hub.exs'],'canonical_manifest_sha256':hashlib.sha256(expected).hexdigest(),'actual_app_files':len(files),'canonical_specifications':specs,'cache_modules':len(names),'cache_entries':len(cache),'cache_all_zero_timestamps':True,'runtime_parent_mtime':parent.mtime,'runtime_parent_reproducibility_pending':parent.mtime!=0,'container_started':False,'audit_container_id':identifier,'audit_container_name':name}
finally:
 inspected=subprocess.run(['docker','inspect',identifier or name],capture_output=True)
 if not OwnedImage.probe_absence(inspected,identifier or name):
  assert inspected.returncode==0
  row=json.loads(inspected.stdout)[0]
  assert row['Image']==image and row['Name']=='/'+name
  identifier=row['Id']
  subprocess.run(['docker','rm','--force',identifier],check=True,capture_output=True)
 for target in (identifier,name):
  if target:assert OwnedImage.probe_absence(subprocess.run(['docker','inspect',target],capture_output=True),target)
if result:
 result['owned_container_absent']=True
 Path('verification/container-precompile-image40/compiled03-admission/image-payload.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
