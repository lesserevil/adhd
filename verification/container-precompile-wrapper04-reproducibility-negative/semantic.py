from pathlib import Path
import importlib.util,struct,tarfile,io,json
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('chunkreader',root/'chunks.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def decode(data):
 assert data[0]==131;p=1;nodes=0
 def term(depth=0):
  nonlocal p,nodes
  nodes+=1;assert nodes<10000000 and depth<512
  t=data[p];p+=1
  def read(n):
   nonlocal p
   v=data[p:p+n];assert len(v)==n;p+=n;return v
  def uint(n):return int.from_bytes(read(n),'big')
  if t==97:return ('int',uint(1))
  if t==98:return ('int',int.from_bytes(read(4),'big',signed=True))
  if t in (110,111):
   n=uint(1 if t==110 else 4);sg=uint(1);assert sg in (0,1);return ('int',(-1 if sg else 1)*int.from_bytes(read(n),'little'))
  if t==70:return ('float',read(8))
  if t in (100,118,119,115):return ('atom',read(uint(1 if t in (119,115) else 2)))
  if t in (104,105):return ('tuple',tuple(term(depth+1) for _ in range(uint(1 if t==104 else 4))))
  if t==106:return ('nil',)
  if t==108:
   items=tuple(term(depth+1) for _ in range(uint(4)));tail=term(depth+1);return ('list',items,tail)
  if t==109:return ('binary',read(uint(4)))
  if t==107:return ('string',read(uint(2)))
  if t==116:
   n=uint(4);entries=[(term(depth+1),term(depth+1)) for _ in range(n)];assert len(set(k for k,v in entries))==n
   return ('map',frozenset(entries))
  raise AssertionError(('unsupported ETF tag',t,p))
 v=term();assert p==len(data);return v
with tarfile.open(root/'images.tar') as outer:
 rows=json.load(outer.extractfile('manifest.json'));images=[]
 for row in rows:
  with tarfile.open(fileobj=io.BytesIO(outer.extractfile(row['Layers'][4]).read())) as layer:
   images.append({m.name:layer.extractfile(m).read() for m in layer if m.isfile() and m.name.endswith('.beam')})
 comparisons=[]
 for name in sorted(images[0]):
  a,b=[module.chunks(i[name])['ExCk'] for i in images]
  comparisons.append({'module':name,'raw_equal':a==b,'etf_terms_equal':decode(a)==decode(b)})
 report={'schema':'adhd/compiled04-checker-etf-comparison@1','passed':all(r['etf_terms_equal'] for r in comparisons),'module_count':len(comparisons),'raw_different':sum(not r['raw_equal'] for r in comparisons),'comparisons':comparisons,'scope':'Independent bounded Python decoding of observed ExCk data; map order ignored, every other term/list/tuple retained. No code load or compiler/application process.'}
(root/'semantic.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='comparisons'})
