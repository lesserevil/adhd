from pathlib import Path
import json,tarfile,io,struct,hashlib
root=Path(__file__).parent;sha=lambda x:hashlib.sha256(x).hexdigest()
def chunks(data):
 assert data[:4]==b'FOR1' and data[8:12]==b'BEAM'; assert struct.unpack('>I',data[4:8])[0]==len(data)-8
 out={};p=12
 while p<len(data):
  name=data[p:p+4].decode();n=struct.unpack('>I',data[p+4:p+8])[0];body=data[p+8:p+8+n];assert len(body)==n
  out[name]=body;p+=8+((n+3)//4)*4
 assert p==len(data);return out
with tarfile.open(root/'images.tar') as outer:
 rows=json.load(outer.extractfile('manifest.json'));images=[]
 for row in rows:
  with tarfile.open(fileobj=io.BytesIO(outer.extractfile(row['Layers'][4]).read())) as layer:
   files={m.name:layer.extractfile(m).read() for m in layer if m.isfile()}
  images.append(files)
 a,b=images;reports={}
 for name in sorted(a):
  if not name.endswith('.beam') or a[name]==b[name]:continue
  x,y=chunks(a[name]),chunks(b[name]);reports[name]={n:{'first_size':len(x.get(n,b'')),'second_size':len(y.get(n,b'')),'first_sha256':sha(x.get(n,b'')),'second_sha256':sha(y.get(n,b''))} for n in sorted(set(x)|set(y)) if x.get(n)!=y.get(n)}
  if name.endswith('ADHD.Allocator.beam'):
   for tag,blob in [('first',a[name]),('second',b[name])]:
    (root/(tag+'-Allocator.beam')).write_bytes(blob)
    for chunk,body in chunks(blob).items():(root/(tag+'-'+chunk+'.bin')).write_bytes(body)
 report={'changed_beams':len(reports),'chunk_differences':reports}
(root/'chunks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'changed_beams':len(reports),'chunk_sets':sorted({','.join(v) for v in reports.values()})}))
