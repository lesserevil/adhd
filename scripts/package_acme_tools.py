#!/usr/bin/env python3
"""Assemble a reviewable immutable ACME bundle from actual isolated builds.

Writes a candidate pin update beside the bundle. The reviewed tracked pin must
be updated separately before stage_container --acme-tools accepts these bytes.
No download, app execution, compiler, receipt or source-authority mutation.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import image_host_dependencies as host

def raw(path,limit=80*1024*1024):
 p=Path(path).absolute();assert p.resolve(strict=True)==p and p.is_file() and p.stat().st_size<=limit
 return p.read_bytes()
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def module_dir(cache,name,version):
 assert re.fullmatch(r'[A-Za-z0-9._~!+/@-]+',name) and '..' not in name.split('/') and not name.startswith('/')
 assert re.fullmatch(r'v[A-Za-z0-9.+-]+',version)
 escape=lambda s:''.join('!'+c.lower() if c.isupper() else c for c in s)
 p=cache/(escape(name)+'@'+escape(version));assert p.resolve(strict=True)==p and p.is_dir();return p

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['lego','guardian','go-build-info','module-cache','go-license','guardian-proof','output']:p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.absolute();assert not out.exists() and out.parent.resolve(strict=True)==out.parent
 pins=json.loads(raw(ROOT/'deploy/runtime/acme-pins.json'))
 binaries={'lego':raw(a.lego),'acme-guard':raw(a.guardian)}
 for path in [a.lego,a.guardian]:assert host.elf_inputs(path)=={'interpreter':None,'needed':[],'search':[]}
 info=json.loads(raw(a.go_build_info));assert info['GoVersion']==pins['patched_client']['go_version'] and info['Path']=='github.com/go-acme/lego/v5'
 settings={r['Key']:r['Value'] for r in info['Settings']};assert settings['CGO_ENABLED']=='0' and settings['GOOS']=='linux' and settings['GOARCH']=='amd64' and settings['-trimpath']=='true'
 cache=a.module_cache.absolute();assert cache.resolve(strict=True)==cache
 components=[]
 for dep in info['Deps']:
  assert set(dep)<= {'Path','Version','Sum'} and re.fullmatch('h1:[A-Za-z0-9+/=]+',dep['Sum'])
  directory=module_dir(cache,dep['Path'],dep['Version']);notices=[]
  for f in sorted(directory.iterdir()):
   if f.is_file() and re.match(r'(?i)^(licen[cs]e|notice|copying|copyright)([._-].*)?$',f.name):
    b=raw(f,1024*1024);notices.append({'name':f.name,'sha256':sha(b),'text':b.decode('utf-8')})
  components.append({'module':dep['Path'],'version':dep['Version'],'go_sum':dep['Sum'],'license_notice_files':notices,'license_review':'Retained upstream text only; no independent legal-clearance claim'})
 sbom={'schema':'adhd/acme-go-binary-inventory@1','binary_sha256':sha(binaries['lego']),'go_version':info['GoVersion'],'upstream':pins['lego'],'patch_sha256':pins['patched_client']['patch_sha256'],'build_settings':settings,'components':components,'go_license':{'sha256':sha(raw(a.go_license)),'text':raw(a.go_license).decode()},'scope':'Actual linked Go build-info inventory with module-root notices; full transitive/legal clearance not asserted; upstream stock SPDX remains a distinct artifact'}
 proof=json.loads(raw(a.guardian_proof));assert proof['passed'] is True and proof['inputs_unchanged'] is True and proof['binary_sha256']==sha(binaries['acme-guard'])
 files={**binaries,'LICENSE.lego':raw(ROOT/'deploy/runtime/licenses/lego-5.5.2.LICENSE'),'LICENSE.musl':raw(ROOT/'deploy/runtime/licenses/musl-1.2.6.COPYRIGHT'),'lego-sbom.json':encoded(sbom),'acme-build.json':encoded({'schema':'adhd/acme-build-provenance@1','lego_sha256':sha(binaries['lego']),'guardian_sha256':sha(binaries['acme-guard']),'lego_source_commit':pins['lego']['source_commit'],'lego_patch_sha256':pins['patched_client']['patch_sha256'],'guardian_source_sha256':pins['guardian_build']['guardian_source_sha256'],'guardian_proof_sha256':sha(raw(a.guardian_proof)),'go_buildinfo_sha256':sha(raw(a.go_build_info)),'musl_source_sha256':pins['guardian_build']['musl_source_sha256']})}
 pins['runtime_bundle']={'platform':'linux_amd64','files':{n:sha(b) for n,b in sorted(files.items())}}
 files['acme-pins.json']=encoded(pins)
 bundle={'schema':'adhd/acme-runtime-bundle@1','platform':'linux_amd64','files':{n:sha(b) for n,b in sorted(files.items())}}
 files['acme-bundle.json']=encoded(bundle)
 assert len(files)==8
 out.mkdir(mode=0o700)
 for n,b in files.items():(out/n).write_bytes(b);(out/n).chmod(0o555 if n in binaries else 0o444)
 (out.parent/(out.name+'-pin-update.json')).write_bytes(files['acme-pins.json'])
 print(json.dumps({'bundle_files':len(files),'components':len(components),'components_without_root_license_notice':sum(not x['license_notice_files'] for x in components),'bundle_sha256':sha(files['acme-bundle.json']),'candidate_pin_update_sha256':sha(files['acme-pins.json'])}))
if __name__=='__main__':main()
