"""Read-only actual accepted-target binding. Missing/null target fails closed.

Imports the existing compiled-admission readers only after authenticating the
reviewed helper files. No Docker, hub, CA or compiler is invoked here.
"""
import hashlib
import importlib
import json
from pathlib import Path
import re
from acme_runtime import regular,sha
from acme_image_runtime import OwnedACMEImage

ASSETS={'LICENSE.lego','LICENSE.musl','acme-build.json','acme-bundle.json','acme-guard','acme-pins.json','lego','lego-sbom.json'}


def closed(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            assert key not in value,'Duplicate target key'
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique)


class AcceptedImageTarget:
    def __init__(self,plan):
        assert isinstance(plan,dict)and isinstance(plan.get('target'),dict),'Actual accepted image target required'
        value=plan['target']
        required={'image','manifest','manifest_sha256','artifact','artifact_sha256','context',
          'admission','admission_sha256','source_admission','source_admission_sha256','receipt','rebuild',
          'docker','docker_sha256','socket_path','docker_config','reader_files','cache_manifest','cache_manifest_sha256'}
        assert set(value)==required,'Closed actual target fields required'
        assert re.fullmatch('sha256:[0-9a-f]{64}',value['image'])
        for name in ['manifest_sha256','artifact_sha256','admission_sha256','source_admission_sha256','docker_sha256','cache_manifest_sha256']:
            assert re.fullmatch('[0-9a-f]{64}',value[name])
        for name in ['manifest','artifact','admission','source_admission','receipt','rebuild','docker','cache_manifest']:
            path=Path(value[name]).absolute();assert path==path.resolve(strict=True)
            regular(path);assert path.stat().st_size<=32*1024*1024
            if name+'_sha256'in value:assert sha(path)==value[name+'_sha256']
        readers=value['reader_files']
        names={'image_compiled_inputs.py','image_compiled_admission.py','image_payload_audit.py'}
        assert set(readers)==names
        for name,digest in readers.items():
            path=Path(__file__).with_name(name);regular(path);assert sha(path)==digest,'Compiled reader dependency changed'
        inputs=importlib.import_module('image_compiled_inputs')
        admission=importlib.import_module('image_compiled_admission')
        source=admission.source_binding(Path(value['source_admission']).read_bytes(),value['source_admission_sha256'],
          Path(value['receipt']).read_bytes(),Path(value['rebuild']).read_bytes(),value['artifact_sha256'])
        target=closed(Path(value['admission']).read_bytes())
        assert target['passed']is True and target['image_config_identity']==value['image']
        assert target['canonical_manifest_sha256']==value['manifest_sha256']and target['artifact_sha256']==value['artifact_sha256']
        for field in admission.PROVENANCE:assert target[field]==source[field]
        binding=inputs.compiled_admission(value['context'],value['admission'],value['admission_sha256'],
          value['image'],value['artifact_sha256'],required=True)
        assert set(binding['acme_files'])==ASSETS
        cache=closed(Path(value['cache_manifest']).read_bytes())
        assert cache['schema']=='adhd/precompiled-cache@2'
        assert sha(value['cache_manifest'])==target['compiled_runtime_audit']['cache_manifest_sha256']
        assert cache['source_sha256']==value['artifact_sha256']and cache['payload_manifest_sha256']==value['manifest_sha256']
        assert cache['modules']==binding['payload_counts']['modules']
        assert cache['acme']=={n:binding['packaging_files_sha256'][n]for n in ASSETS}
        self.value,self.binding,self.cache=value,binding,cache
        self.instances=[]
        self.assets={name:{'path':'/runtime/adhd/'+name,'sha256':cache['acme'][name]}for name in ASSETS}
        self.runtime_files={'/runtime/adhd/manifest.json':sha(value['cache_manifest']),
          '/runtime/adhd/inputs.json':cache['inputs_sha256'],'/runtime/adhd/boot.exs':cache['boot_sha256'],
          '/runtime/adhd/build.exs':cache['build_sha256'],
          **{'/runtime/adhd/ebin/'+name:digest for name,digest in cache['beams'].items()}}

    def image(self,mount_root):
        v=self.value
        result=OwnedACMEImage(v['image'],v['manifest'],mount_root,manifest_sha256=v['manifest_sha256'],
          artifact_sha256=v['artifact_sha256'],assets=self.assets,docker=v['docker'],docker_sha256=v['docker_sha256'],
          socket_path=v['socket_path'],docker_config=v['docker_config'],runtime_files=self.runtime_files)
        self.instances.append(result)
        return result

    def runtime_evidence(self):
        return [{'image':x.image_id,'payload_verified':x.verified,'assets_verified':x.assets_verified,
          'name':x.name,'container_id':x.container_id,'events':list(x.events),'actual_vms':list(x.runtime_rows),
          'probes':list(x.probe_events),'probe_cleanup_blocked':x.probe_cleanup_blocked}for x in self.instances]

    def evidence(self):
        v=self.value
        return {'image_config_identity':v['image'],'artifact_sha256':v['artifact_sha256'],
          'canonical_manifest_sha256':v['manifest_sha256'],'admission_sha256':v['admission_sha256'],
          'source_admission_sha256':v['source_admission_sha256'],'cache_manifest_sha256':v['cache_manifest_sha256'],
          'cache_modules':len(self.cache['beams']),'packaged_assets':{k:x['sha256']for k,x in self.assets.items()},
          'scope':'Actual proper source/compiled admission bindings; runtime qualification remains required'}
