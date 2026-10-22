#!/usr/bin/env python3
"""Build isolated static musl from its pinned source with closed host inputs.

No installation outside the fresh output directory; no hub/CA/container starts.
"""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from build_acme_client import archive_tree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
import image_host_dependencies as host

def tools():
 names=('make','ar','ranlib','install','sh','sed','grep','tr','cut','head','tail','sort','uniq','expr','awk','cp','rm','mv','ln','mkdir','touch','cmp','printf','uname','cat','dirname','basename')
 files={};queue=[Path(shutil.which(n,path='/usr/bin:/bin')) for n in names]
 while queue:
  p=queue.pop();row=host.path_binding(p)
  if row['path'] in files:continue
  files[row['path']]=row;parsed=host.elf_inputs(p)
  if parsed is None:continue
  assert all(Path(d).is_absolute() and '$' not in d for d in parsed['search'])
  if parsed['interpreter']:queue.append(Path(parsed['interpreter']))
  for name in parsed['needed']:
   assert '/' not in name
   choices=[Path(d)/name for d in parsed['search']+['/lib/x86_64-linux-gnu','/usr/lib/x86_64-linux-gnu','/lib64','/usr/lib64','/lib','/usr/lib']]
   found=next((q for q in choices if q.is_file()),None);assert found is not None
   queue.append(found)
 return files

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['host-closure','source-archive','source-tree','output']:p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.absolute();assert out.parent.resolve(strict=True)==out.parent and not out.exists()
 pins=json.loads((ROOT/'deploy/runtime/acme-pins.json').read_bytes())
 assert host.sha(a.source_archive)==pins['guardian_build']['musl_source_sha256']
 source=a.source_tree.absolute();source_files=archive_tree(a.source_archive,source)
 closure=json.loads(a.host_closure.read_bytes());host.verify(closure);extra=tools()
 out.mkdir(mode=0o700);build=out/'build';build.mkdir();(out/'tmp').mkdir(mode=0o700);prefix=out/'installed'
 env={'PATH':'/usr/bin:/bin','LC_ALL':'C','CC':'/usr/bin/cc','AR':'/usr/bin/ar','RANLIB':'/usr/bin/ranlib','CFLAGS':'-Os -fno-ident -ffile-prefix-map='+str(ROOT)+'=/adhd-acme','SOURCE_DATE_EPOCH':'0','TMPDIR':str(out/'tmp')}
 commands=[[str(source/'configure'),'--prefix='+str(prefix),'--syslibdir='+str(prefix/'lib'),'--disable-shared','--enable-static'],['/usr/bin/make','-j2','install']]
 inputs={'schema':'adhd/acme-musl-build@1','source_sha256':host.sha(a.source_archive),'source_files':source_files,'host_closure_sha256':host.sha(a.host_closure),'additional_tools':extra,'commands':commands,'env':env,'cwd':str(build)}
 (out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 for i,argv in enumerate(commands):
  with (out/f'{i}.stdout').open('wb') as stdout,(out/f'{i}.stderr').open('wb') as stderr:r=subprocess.run(argv,cwd=build,env=env,stdout=stdout,stderr=stderr,timeout=600)
  assert r.returncode==0
 host.verify(closure);assert tools()==extra and archive_tree(a.source_archive,source)==source_files
 tree=host.tree_inventory(prefix,[prefix]);assert not tree['links']
 (out/'result.json').write_text(json.dumps({'passed':True,'inputs_unchanged':True,'inputs_sha256':host.sha(out/'inputs.json'),'installed_tree':tree,'scope':'Actual isolated static musl build; no target-image/runtime claim'},indent=2)+'\n')
if __name__=='__main__':main()
