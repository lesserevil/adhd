from pathlib import Path
import io,tarfile,json,hashlib
root=Path('/home/horde/src/adhd/.worktrees/contracts/_build/container-layer-review04');sha=lambda b:hashlib.sha256(b).hexdigest()
with tarfile.open(root/'images.tar','r:') as outer:
 entries={m.name:m for m in outer.getmembers()};rows=json.load(outer.extractfile('manifest.json'));assert len(rows)==2
 images=[]
 for row in rows:
  raw=outer.extractfile(row['Config']).read();config=json.loads(raw);identity='sha256:'+sha(raw)
  layers=[]
  for i,path in enumerate(row['Layers']):
   data=outer.extractfile(path).read();assert 'sha256:'+sha(data)==config['rootfs']['diff_ids'][i]
   with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as inner:
    observed=[]
    for m in inner.getmembers():
     observed.append({'name':m.name,'mode':format(m.mode,'04o'),'type':m.type.decode('ascii'),'uid':m.uid,'gid':m.gid,'uname':m.uname,'gname':m.gname,'size':m.size,'mtime':m.mtime,'pax_headers':m.pax_headers,'linkname':m.linkname,'body_sha256':sha(inner.extractfile(m).read()) if m.isfile() else None})
   layers.append({'index':i,'diff_id':config['rootfs']['diff_ids'][i],'tar_bytes':len(data),'headers':observed})
  images.append({'image':identity,'config_runtime':config['config'],'layers':layers})
 assert {x['image'] for x in images}=={'sha256:184d16bf19d292da7f741338eee68d2b61f657eed8fd32f774a1ad1bc2b46a59','sha256:698d9f32ac1d2931f34a5778e21047c6f66c58dad78c6853e53120697ceee5d9'}
 a,b=images;differences=[]
 assert len(a['layers'])==len(b['layers'])
 for x,y in zip(a['layers'],b['layers']):
  if x['diff_id']==y['diff_id']:continue
  old={v['name']:v for v in x['headers']};new={v['name']:v for v in y['headers']}
  changes={n:{'first':old.get(n),'second':new.get(n)} for n in sorted(set(old)|set(new)) if old.get(n)!=new.get(n)}
  differences.append({'index':x['index'],'first_diff_id':x['diff_id'],'second_diff_id':y['diff_id'],'headers_different':changes,'first_entries':len(old),'second_entries':len(new),'all_common_file_bodies_equal':all(old[n]['body_sha256']==new[n]['body_sha256'] for n in set(old)&set(new))})
 report={'schema':'adhd/compiled04-layer-header-comparison@1','passed':False,'audit_passed':True,'bitwise_reproducible':False,'images':[x['image'] for x in images],'runtime_configuration_equal':a['config_runtime']==b['config_runtime'],'different_layers':differences,'source_archive_sha256':sha((root/'images.tar').read_bytes()),'scope':'Read-only Docker image export/header inspection; no application/compiler/build/start, no image mutation. No causal inference beyond directly differing archive fields.'}
(root/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
