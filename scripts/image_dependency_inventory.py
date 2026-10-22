#!/usr/bin/env python3
"""Read-only inventory from a local Docker-save archive; never invokes Docker.

Reports package-manager license declarations, not legal clearance or a complete
binary SBOM. Source-built runtimes, Java/Python/npm transitive packages and model
weights need their own declared inventories. No archive member is extracted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import tarfile

DB='lib/apk/db/installed'
DB_WHITEOUTS={'.wh.lib','lib/.wh.apk','lib/apk/.wh.db','lib/apk/db/.wh.installed',
             '.wh..wh..opq','lib/.wh..wh..opq','lib/apk/.wh..wh..opq','lib/apk/db/.wh..wh..opq'}
MAX_LAYER=1024*1024*1024

def digest(stream):
 h=hashlib.sha256()
 while block:=stream.read(65536):h.update(block)
 return h.hexdigest()

def apk(data):
 assert len(data)<=2*1024*1024
 rows=[];seen=set()
 for block in data.decode('utf-8').strip().split('\n\n'):
  fields={}
  for line in block.splitlines():
   if len(line)>=2 and line[1]==':' and line[0] in 'PVALTU':
    assert line[0] not in fields,'Duplicate package header';fields[line[0]]=line[2:]
  assert fields.get('P') and fields.get('V') and fields['P'] not in seen
  seen.add(fields['P']);rows.append({'name':fields['P'],'version':fields['V'],'architecture':fields.get('A'),
   'license_declared_by_apk':fields.get('L') or None,'license_unknown':not fields.get('L'),
   'homepage':fields.get('U') or None,'description':fields.get('T')})
 assert 0<len(rows)<=10000
 return sorted(rows,key=lambda x:x['name'])

def inventory(archive,image):
 assert re.fullmatch('sha256:[a-f0-9]{64}',image)
 path=Path(archive).absolute();s=path.lstat();assert path.resolve(strict=True)==path and stat.S_ISREG(s.st_mode) and s.st_nlink==1
 state=None;license_paths=set();layer_rows=[]
 with tarfile.open(path,'r:') as outer:
  members=outer.getmembers();assert len(members)<=10000 and len({x.name for x in members})==len(members)
  byname={m.name:m for m in members}
  def read(name,limit):
   m=byname[name];assert m.isfile() and m.size<=limit
   return outer.extractfile(m).read()
  manifest=json.loads(read('manifest.json',1024*1024));assert len(manifest)==1
  selected=manifest[0];raw=read(selected['Config'],1024*1024);assert 'sha256:'+hashlib.sha256(raw).hexdigest()==image
  config=json.loads(raw);layers=selected['Layers'];assert 0<len(layers)<=32 and len(layers)==len(config['rootfs']['diff_ids'])
  for index,name in enumerate(layers):
   member=byname[name];assert member.isfile() and member.size<=MAX_LAYER
   actual=digest(outer.extractfile(member));assert 'sha256:'+actual==config['rootfs']['diff_ids'][index]
   count=0;targets=set();replacement=None;removed=False
   with tarfile.open(fileobj=outer.extractfile(member),mode='r|') as inner:
    for m in inner:
     count+=1;assert count<=250000
     n=m.name.removeprefix('./');assert not n.startswith('/') and '..' not in Path(n).parts
     if n in DB_WHITEOUTS:removed=True
     if n==DB:
      assert n not in targets and m.isfile() and m.size<=2*1024*1024;targets.add(n);replacement=inner.extractfile(m).read()
     if m.isfile() and re.search(r'(^|/)(?:COPYING|COPYRIGHT|NOTICE|LICENSE)(?:[./_-]|$)',n,re.I):license_paths.add(n)
   # Whiteouts remove lower-layer entries regardless of tar member order.
   # A database written in this same layer survives its directory's opacity.
   if removed:state=None
   if replacement is not None:state=replacement
   layer_rows.append({'index':index,'diff_id':'sha256:'+actual,'bytes':member.size})
 assert state is not None,'No supported Alpine package database in final layer view'
 env=dict(x.split('=',1) for x in config['config'].get('Env',[]) if '=' in x)
 current=path.lstat();assert (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)
 with path.open('rb') as stream:archive_sha=digest(stream)
 assert path.lstat()==current
 return {'schema':'adhd/offline-image-dependency-inventory@1','image_config_identity':image,
  'archive_sha256':archive_sha,'layer_digests_verified':layer_rows,
  'runtime_declared_versions':{k:env[k] for k in ('ELIXIR_VERSION','OTP_VERSION','REBAR3_VERSION') if k in env},
  'apk_database_sha256':hashlib.sha256(state).hexdigest(),'packages':apk(state),'license_file_paths_observed':sorted(license_paths),
  'application_oci_license_label':config['config'].get('Labels',{}).get('org.opencontainers.image.licenses'),
  'scope':'Exact image archive and Alpine package license declarations only; observed license paths may have been removed by a later layer. No legal clearance, comprehensive binary/Java/npm/Python/model SBOM, or vulnerability scan.',
  'container_or_application_starts':0}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--docker-save',type=Path,required=True);p.add_argument('--image',required=True);p.add_argument('--output',type=Path);a=p.parse_args()
 data=(json.dumps(inventory(a.docker_save,a.image),indent=2)+'\n').encode()
 if a.output:
  with a.output.open('xb') as stream:stream.write(data)
 else:print(data.decode(),end='')
if __name__=='__main__':main()
