#!/usr/bin/env python3
"""Build the fixed guardian against an explicitly bound installed static musl.

The installed musl's separate source-build provenance remains a prerequisite;
this command proves the guardian compile's exact source/tool/library closure.
It never starts a hub, CA, container or network request.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import image_host_dependencies as host

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['host-closure','musl-root','musl-archive','output']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.absolute();assert not out.exists() and out.parent.resolve(strict=True)==out.parent
 pins=json.loads((ROOT/'deploy/runtime/acme-pins.json').read_bytes());source=ROOT/'deploy/runtime/acme-guard.c'
 assert host.sha(source)==pins['guardian_build']['guardian_source_sha256']
 assert host.sha(a.musl_archive)==pins['guardian_build']['musl_source_sha256']
 closure=json.loads(a.host_closure.read_bytes());host.verify(closure)
 musl=a.musl_root.absolute();assert musl.resolve(strict=True)==musl
 tree=host.tree_inventory(musl,[musl]);assert not tree['links']
 compiler=musl/'bin/musl-gcc';assert compiler.is_file()
 assert str(closure['tools']['cc']['path'])=='/usr/bin/cc'
 out.mkdir(mode=0o700);(out/'tmp').mkdir(mode=0o700)
 argv=[str(compiler),'-static','-std=c11','-Os','-Wall','-Wextra','-Werror','-fno-ident','-fstack-protector-strong','-Wl,--build-id=none','-ffile-prefix-map='+str(ROOT)+'=/adhd-acme',str(source),'-o',str(out/'acme-guard')]
 env={'PATH':'/usr/bin:/bin','LC_ALL':'C','SOURCE_DATE_EPOCH':'0','TMPDIR':str(out/'tmp'),'REALGCC':'/usr/bin/cc'}
 before={'host_closure_sha256':host.sha(a.host_closure),'source_sha256':host.sha(source),'musl_archive_sha256':host.sha(a.musl_archive),'musl_tree':tree,'argv':argv,'env':env}
 (out/'inputs.json').write_text(json.dumps(before,indent=2)+'\n')
 result=subprocess.run(argv,env=env,capture_output=True,timeout=60)
 (out/'stdout').write_bytes(result.stdout);(out/'stderr').write_bytes(result.stderr)
 host.verify(closure);assert host.tree_inventory(musl,[musl])==tree and host.sha(source)==before['source_sha256']
 assert result.returncode==0
 elf=host.elf_inputs(out/'acme-guard');assert elf=={'interpreter':None,'needed':[],'search':[]}
 (out/'result.json').write_text(json.dumps({'passed':True,'exit_code':0,'inputs_unchanged':True,'binary_sha256':host.sha(out/'acme-guard'),'binary_bytes':(out/'acme-guard').stat().st_size,'elf':elf,'scope':'Actual static guardian compile only; installed-musl source provenance and target image/process qualification remain separate'},indent=2)+'\n')
if __name__=='__main__':main()
