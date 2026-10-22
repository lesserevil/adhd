"""Optional immutable-image cache custody for original full-app recovery programs.

Static network-none probes precede application dispatch. They are not in-VM67
measurements, health calls, warmups or compilation. Existing runtime observers
remain responsible for kernel/CLI/fault custody. Codec-only -e tools are separate.
"""
import hashlib
import json
from pathlib import PurePosixPath


def static_files(manifest,compiled):
    cache=compiled['manifest'];files={'/app/'+k:v for k,v in manifest['files'].items()if k!='Dockerfile'}
    assert len(files)==59
    files.update({'/runtime/adhd/boot.exs':cache['boot_sha256'],'/runtime/adhd/build.exs':cache['build_sha256'],'/runtime/adhd/inputs.json':cache['inputs_sha256']})
    files.update({'/runtime/adhd/ebin/'+k:v for k,v in cache['beams'].items()})
    anchors=cache['toolchain']['anchors'];assert len(anchors)==5 and '/proc/self/exe'in anchors
    files.update({k:v for k,v in anchors.items()if k!='/proc/self/exe'})
    assert len(files)==125 # source59 +cache62 +static toolchain4; dynamic VM anchor is not claimed here.
    return files


def inspected_launch(row,target,compiled):
    assert row['Image']==target.image_id and row['Name']=='/'+target.name
    assert row['Config']['Entrypoint']==compiled['reviewed_runtime_audit']['entrypoint']
    assert row['HostConfig']['ReadonlyRootfs'] is True and row['HostConfig']['PidMode']in('','private')
    for mount in row['Mounts']:
        destination=PurePosixPath(mount['Destination']);assert destination.is_absolute()
        for protected in map(PurePosixPath,['/app','/runtime/adhd']):
            assert not(destination.is_relative_to(protected)or protected.is_relative_to(destination)),'Protected source/cache mount'
    environment=row['Config'].get('Env')or[]
    return {'container_id':row['Id'],'image_config_identity':row['Image'],'host_container_pid':row['State']['Pid'],
        'readonly_rootfs':True,'private_pid_namespace':True,'protected_paths_not_mounted':True,
        'execution_scope':'precompiled-entrypoint-with-scalar-observer'if any(v.startswith('LD_PRELOAD=')for v in environment)else'precompiled-default-entrypoint',
        'entrypoint':row['Config']['Entrypoint']}


class CacheCustody:
    def __init__(self,owned,binding):
        self.owned=owned;self.compiled=binding['compiled_cache'];self.target=binding['image_config_identity'];self.original_verify=owned.verify;self.original_docker=owned.docker
    def install(self):
        owner=self
        def checked_verify(target):
            owner.original_verify(target)
            if getattr(target,'recovery_static_cache',None)is not None:return
            assert target.image_id==owner.target
            raw=target.probe('cat','/runtime/adhd/manifest.json')
            assert hashlib.sha256(raw).hexdigest()==owner.compiled['manifest_sha256']and json.loads(raw)==owner.compiled['manifest']
            expected=static_files(target.manifest,owner.compiled)
            observed=target.probe('sha256sum',*expected).decode().splitlines()
            assert {line.split(None,1)[1].strip():line.split(None,1)[0]for line in observed}==expected
            target.recovery_static_cache={'scope':'Immutable-image readonly network-none probes before app dispatch; not in-VM67',
                'manifest_sha256':owner.compiled['manifest_sha256'],'cache_modules':59,'source_files':59,'cache_files':62,
                'static_toolchain_anchors':4,'dynamic_VM_anchor_observed_here':False,'image_config_identity':target.image_id,
                'probe_lifecycle':list(target.probe_events),'health_or_model_calls':0}
        def verify(target):
            assert not getattr(target,'recovery_static_cache_failure',None),'Prior cache verification failed'
            try:return checked_verify(target)
            except BaseException as error:
                target.recovery_static_cache_failure=type(error).__name__;raise
        def docker(target,*args,**kwargs):
            result=owner.original_docker(target,*args,**kwargs)
            if args and args[0]=='inspect'and result.returncode==0 and target.name:
                rows=json.loads(result.stdout)
                for row in rows:
                    if row.get('Name')=='/'+target.name and row.get('State',{}).get('Running'):
                        proof=inspected_launch(row,target,owner.compiled)
                        observations=getattr(target,'recovery_compiled_launches',[])
                        if not any(p['container_id']==proof['container_id']for p in observations):observations.append(proof)
                        target.recovery_compiled_launches=observations
            return result
        self.owned.verify=verify;self.owned.docker=docker
    def restore(self):self.owned.verify=self.original_verify;self.owned.docker=self.original_docker
