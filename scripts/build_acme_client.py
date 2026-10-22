#!/usr/bin/env python3
"""Build the pinned patched Lego offline from verified source/tool archives.

A fresh owned Go cache prevents adoption of precompiled cache entries. Go module
source closure is captured before/after; GOPROXY and GOSUMDB are disabled. This
never runs Lego, a CA, a hub or a container.
"""
import argparse,hashlib,json,os,subprocess,sys,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
import image_host_dependencies as host

def sha(b):return hashlib.sha256(b).hexdigest()
def archive_tree(path,root):
 root=Path(root).absolute();assert root.resolve(strict=True)==root
 expected={}
 with tarfile.open(path) as archive:
  for member in archive.getmembers():
   assert not member.name.startswith('/') and '..' not in Path(member.name).parts
   if member.isdir():continue
   assert member.isfile() and member.size<=128*1024*1024
   name='/'.join(Path(member.name).parts[1:]);assert name and name not in expected
   expected[name]=sha(archive.extractfile(member).read())
 actual={str(p.relative_to(root)):host.sha(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
 assert not any(p.is_symlink() for p in root.rglob('*')) and actual==expected
 return actual

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['source-archive','upstream-source','patched-source','go-archive','go-root','module-cache','output']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.absolute();assert not out.exists() and out.parent.resolve(strict=True)==out.parent
 pins=json.loads((ROOT/'deploy/runtime/acme-pins.json').read_bytes());pin=pins['patched_client']
 assert host.sha(a.source_archive)==pin['source_archive_sha256'] and host.sha(a.go_archive)==pin['go_linux_amd64_sha256']
 assert host.sha(ROOT/'deploy/runtime/lego-retry-metadata.patch')==pin['patch_sha256']
 original=archive_tree(a.source_archive,a.upstream_source);toolchain=archive_tree(a.go_archive,a.go_root)
 patched=a.patched_source.absolute();assert patched.resolve(strict=True)==patched
 expected={**original,**pin['patched_files_sha256']}
 actual={str(f.relative_to(patched)):host.sha(f) for f in patched.rglob('*') if f.is_file() and not f.is_symlink()}
 assert not any(f.is_symlink() for f in patched.rglob('*')) and actual==expected
 go=a.go_root.absolute()/'bin/go';elf=host.elf_inputs(go);assert elf=={'interpreter':None,'needed':[],'search':[]}
 module=a.module_cache.absolute();assert module.resolve(strict=True)==module
 modules=host.tree_inventory(module,[module]);assert not modules['links']
 out.mkdir(mode=0o700);(out/'cache').mkdir(mode=0o700);(out/'tmp').mkdir(mode=0o700)
 env={'PATH':str(go.parent)+':/usr/bin:/bin','GOTOOLCHAIN':'local','GOENV':'off','CGO_ENABLED':'0','GOMAXPROCS':'2','GOFLAGS':'-p=2','GOPATH':str(module.parent.parent),'GOMODCACHE':str(module),'GOCACHE':str(out/'cache'),'GOPROXY':'off','GOSUMDB':'off','SOURCE_DATE_EPOCH':'0','TMPDIR':str(out/'tmp')}
 argv=[str(go),'build','-trimpath','-buildvcs=false','-mod=readonly','-ldflags=-s -w -buildid= -X main.version=v5.5.2+adhd.retry2','-o',str(out/'lego'),'.']
 plan={'schema':'adhd/acme-client-build@1','source_archive_sha256':host.sha(a.source_archive),'upstream_files':original,'patched_files':actual,'patch_sha256':pin['patch_sha256'],'go_archive_sha256':host.sha(a.go_archive),'go_files':toolchain,'module_tree':modules,'argv':argv,'cwd':str(patched),'env':env}
 (out/'inputs.json').write_text(json.dumps(plan,indent=2)+'\n');began=time.monotonic()
 with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:result=subprocess.run(argv,cwd=patched,env=env,stdout=stdout,stderr=stderr,timeout=1800)
 assert result.returncode==0
 assert archive_tree(a.source_archive,a.upstream_source)==original and archive_tree(a.go_archive,a.go_root)==toolchain
 assert {str(f.relative_to(patched)):host.sha(f) for f in patched.rglob('*') if f.is_file()}==actual
 assert host.tree_inventory(module,[module])==modules
 parsed=host.elf_inputs(out/'lego');assert parsed=={'interpreter':None,'needed':[],'search':[]}
 info=subprocess.run([str(go),'version','-m','-json',str(out/'lego')],capture_output=True,env=env,timeout=10,check=True)
 (out/'go-build-info.json').write_bytes(info.stdout)
 (out/'result.json').write_text(json.dumps({'passed':True,'exit_code':0,'fresh_cache':True,'inputs_unchanged':True,'binary_sha256':host.sha(out/'lego'),'binary_bytes':(out/'lego').stat().st_size,'elapsed_seconds':time.monotonic()-began,'elf':parsed,'inputs_sha256':host.sha(out/'inputs.json'),'go_buildinfo_sha256':sha(info.stdout),'scope':'Source/tool/module-closed offline client build only; target-image/runtime qualification separate'},indent=2)+'\n')
if __name__=='__main__':main()
