"""Pure retarget admission denial cases, no compiler/container/provider calls."""
import copy,json,tempfile
from pathlib import Path
from image_compiled_inputs import compiled_admission,digest
from image_compiled_inputs_unit import make


def main():
    count=0
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);context=root/'context';context.mkdir();manifest,artifact=make(context)
        audit={'passed':True,'image_id':'sha256:'+'a'*64,'artifact_sha256':artifact,'canonical_manifest_sha256':manifest,
            'cache_manifest_sha256':'d'*64,'cache_metadata_sha256':'e'*64,'compiler_inputs_sha256':digest((context/'compiler-inputs.json').read_bytes()),
            'cache_modules':59,'cache_entries':65,'entrypoint':['elixir','/runtime/adhd/boot.exs','/app/hub.exs'],'container_started':False,'owned_container_absent':True}
        basis={'passed':True,'image_config_identity':audit['image_id'],'artifact_sha256':artifact,'canonical_manifest_sha256':manifest,'compiled_runtime_audit':audit}
        cases=[None,'missing-audit','image','source','manifest','compiler-inputs','entrypoint','module-count','entry-count','cache-hash','started','cleanup']
        for case in cases:
            value=copy.deepcopy(basis)
            if case=='missing-audit':del value['compiled_runtime_audit']
            elif case:
                key,bad={'image':('image_id','sha256:'+'b'*64),'source':('artifact_sha256','f'*64),'manifest':('canonical_manifest_sha256','f'*64),
                    'compiler-inputs':('compiler_inputs_sha256','f'*64),'entrypoint':('entrypoint',['elixir','/app/hub.exs']),
                    'module-count':('cache_modules',58),'entry-count':('cache_entries',64),'cache-hash':('cache_manifest_sha256','bad'),
                    'started':('container_started',True),'cleanup':('owned_container_absent',False)}[case]
                value['compiled_runtime_audit'][key]=bad
            path=root/'admission';path.write_text(json.dumps(value))
            try:result=compiled_admission(context,path,digest(path.read_bytes()),basis['image_config_identity'],artifact,required=True)
            except (AssertionError,KeyError):assert case
            else:assert case is None and result['actual_runtime_or_cache_qualified'] is False
            count+=1
        legacy=root/'legacy';legacy.mkdir();path=root/'admission';path.write_text(json.dumps({}))
        try:compiled_admission(legacy,path,digest(path.read_bytes()),basis['image_config_identity'],artifact,required=True)
        except AssertionError:pass
        else:raise AssertionError('Compiled gate accepted legacy source-only context')
        count+=1
    print(json.dumps({'passed':True,'checks':count,'runtime_or_compiler_starts':0}))


if __name__=='__main__':main()
