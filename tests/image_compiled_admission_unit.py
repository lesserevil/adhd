"""Pure retarget/cache-file denial cases; no code/compiler/container loads."""
import copy,json,tempfile
from pathlib import Path
from image_compiled_inputs import compiled_admission,digest
from image_compiled_inputs_unit import make


def retain(root,context,manifest,artifact):
    inputs=json.loads((context/'compiler-inputs.json').read_text())
    modules=['Elixir.ADHD.M'+str(i) for i in range(59)]
    cache={'schema':'adhd/precompiled-cache@1','source':'/app/hub.exs','source_sha256':artifact,
        'payload_manifest_sha256':manifest,'inputs_sha256':digest((context/'compiler-inputs.json').read_bytes()),
        'boot_sha256':inputs['files']['boot.exs'],'build_sha256':inputs['files']['build.exs'],
        'modules':modules,'beams':{m+'.beam':digest(m.encode())for m in modules},
        'toolchain':{'elixir':'1.20.4','otp':'29','erts':'17.1.1','architecture':'x86_64-pc-linux-musl','anchors':{name:'d'*64 for name in ['/proc/self/exe']+['/usr/local/lib/elixir/bin/../lib/elixir/ebin/'+n for n in ['Elixir.Code.beam','Elixir.JSON.beam','Elixir.Kernel.beam','elixir.beam']]}}}
    raw=json.dumps(cache,separators=(',',':')).encode();(root/'cache-manifest.json').write_bytes(raw)
    files={'adhd/boot.exs':cache['boot_sha256'],'adhd/build.exs':cache['build_sha256'],'adhd/inputs.json':cache['inputs_sha256'],
        'adhd/manifest.json':digest(raw),**{'adhd/ebin/'+k:v for k,v in cache['beams'].items()}}
    metadata={k:{'mode':'0o444','mtime':0,'sha256':v}for k,v in files.items()}
    metadata.update({k:{'mode':v,'mtime':0,'sha256':None}for k,v in {'/runtime':'0o755','adhd':'0o555','adhd/ebin':'0o555'}.items()})
    (root/'cache-metadata.json').write_text(json.dumps(metadata))
    audit={'passed':True,'image_id':'sha256:'+'a'*64,'artifact_sha256':artifact,'canonical_manifest_sha256':manifest,
        'cache_manifest_sha256':digest(raw),'cache_metadata_sha256':digest((root/'cache-metadata.json').read_bytes()),
        'compiler_inputs_sha256':cache['inputs_sha256'],'cache_modules':59,'cache_entries':65,
        'entrypoint':['elixir','/runtime/adhd/boot.exs','/app/hub.exs'],'container_started':False,'owned_container_absent':True}
    basis={'passed':True,'image_config_identity':audit['image_id'],'artifact_sha256':artifact,'canonical_manifest_sha256':manifest,'compiled_runtime_audit':audit,
        'files':{n:digest((root/n).read_bytes())for n in ['cache-manifest.json','cache-metadata.json']}}
    return basis,cache,metadata


def main():
    count=0
    with tempfile.TemporaryDirectory() as temp:
        for case in [None,'missing-audit','image','source','manifest','compiler-inputs','entrypoint','module-count','entry-count','cache-hash','started','cleanup',
                     'missing-cache','missing-metadata','redirect-cache','redirect-metadata','tampered-cache','tampered-metadata','files-hash',
                     'cache-source','cache-payload','cache-inputs','cache-helper','cache-modules','cache-beam-set','cache-beam-metadata','metadata-extra','metadata-mode','metadata-mtime','metadata-manifest-hash','duplicate-cache-key']:
            root=Path(temp)/str(case);root.mkdir();context=root/'context';context.mkdir();manifest,artifact=make(context)
            value,cache,metadata=retain(root,context,manifest,artifact)
            update=False
            if case=='missing-audit':del value['compiled_runtime_audit']
            elif case in ['image','source','manifest','compiler-inputs','entrypoint','module-count','entry-count','cache-hash','started','cleanup']:
                key,bad={'image':('image_id','sha256:'+'b'*64),'source':('artifact_sha256','f'*64),'manifest':('canonical_manifest_sha256','f'*64),
                    'compiler-inputs':('compiler_inputs_sha256','f'*64),'entrypoint':('entrypoint',['elixir','/app/hub.exs']),
                    'module-count':('cache_modules',58),'entry-count':('cache_entries',64),'cache-hash':('cache_manifest_sha256','bad'),
                    'started':('container_started',True),'cleanup':('owned_container_absent',False)}[case];value['compiled_runtime_audit'][key]=bad
            elif case in ['missing-cache','missing-metadata','redirect-cache','redirect-metadata','tampered-cache','tampered-metadata']:
                file=root/('cache-manifest.json' if case.endswith('cache') else 'cache-metadata.json')
                if case.startswith('missing'):file.unlink()
                elif case.startswith('redirect'):target=root/'actual';file.rename(target);file.symlink_to(target)
                else:file.write_text(file.read_text()+'\n')
            elif case=='files-hash':value['files']['cache-manifest.json']='c'*64
            elif case:
                update=True
                if case=='cache-source':cache['source_sha256']='f'*64
                if case=='cache-payload':cache['payload_manifest_sha256']='f'*64
                if case=='cache-inputs':cache['inputs_sha256']='f'*64
                if case=='cache-helper':cache['boot_sha256']='f'*64
                if case=='cache-modules':cache['modules'].reverse()
                if case=='cache-beam-set':cache['beams']['foreign.beam']='f'*64
                if case=='cache-beam-metadata':cache['beams']['Elixir.ADHD.M0.beam']='f'*64
                if case=='metadata-extra':metadata['foreign']={'mode':'0o444','mtime':0,'sha256':'f'*64}
                if case=='metadata-mode':metadata['adhd']['mode']='0o755'
                if case=='metadata-mtime':metadata['/runtime']['mtime']=123
                if case=='metadata-manifest-hash':metadata['adhd/manifest.json']['sha256']='f'*64
                raw=json.dumps(cache,separators=(',',':')).encode()
                if case=='duplicate-cache-key':raw=b'{"schema":1,"schema":2}'
                (root/'cache-manifest.json').write_bytes(raw)
                if case!='metadata-manifest-hash':metadata['adhd/manifest.json']['sha256']=digest(raw)
                (root/'cache-metadata.json').write_text(json.dumps(metadata))
                for name,field in [('cache-manifest.json','cache_manifest_sha256'),('cache-metadata.json','cache_metadata_sha256')]:
                    value['files'][name]=value['compiled_runtime_audit'][field]=digest((root/name).read_bytes())
            path=root/'admission';path.write_text(json.dumps(value))
            try:result=compiled_admission(context,path,digest(path.read_bytes()),'sha256:'+'a'*64,artifact,required=True)
            except (AssertionError,KeyError,OSError):assert case
            else:assert case is None and result['actual_runtime_or_cache_qualified'] is False and result['retained_cache_binding']['cache_file_hashes_cross_checked']==63
            count+=1
        legacy=Path(temp)/'legacy';legacy.mkdir();path=Path(temp)/'admission';path.write_text(json.dumps({}))
        try:compiled_admission(legacy,path,digest(path.read_bytes()),'sha256:'+'a'*64,'b'*64,required=True)
        except AssertionError:pass
        else:raise AssertionError('Compiled gate accepted legacy source-only context')
        count+=1
    print(json.dumps({'passed':True,'checks':count,'runtime_or_compiler_starts':0}))


if __name__=='__main__':main()
