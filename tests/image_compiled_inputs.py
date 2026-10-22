"""Read-only compiled-container context bindings; never loads a BEAM or image.

This proves staged compiler inputs only. Actual image runtime/cache audit and
runtime qualification are separate required admission evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile


def digest(data):return hashlib.sha256(data).hexdigest()


def closed_object(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            assert key not in result,'Duplicate metadata key'
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)


def compiled_context(context,expected_manifest,expected_artifact):
    context=Path(context).absolute()
    assert context.resolve(strict=True)==context and context.is_dir()
    expected={'Dockerfile','manifest.json','payload.tar','packaging.tar','compiler-inputs.json'}
    assert {p.name for p in context.iterdir()}==expected
    for path in context.iterdir():assert path.is_file() and not path.is_symlink()
    assert (context/'payload.tar').stat().st_size<=32*1024*1024
    assert (context/'Dockerfile').stat().st_size<=1024*1024
    assert (context/'manifest.json').stat().st_size<=1024*1024
    manifest_raw=(context/'manifest.json').read_bytes();assert digest(manifest_raw)==expected_manifest
    manifest=closed_object(manifest_raw)
    assert manifest['schema']=='adhd/container-inputs@1' and manifest['files']['hub.exs']==expected_artifact
    dockerfile=(context/'Dockerfile').read_bytes();assert digest(dockerfile)==manifest['files']['Dockerfile']
    inputs_path=context/'compiler-inputs.json';assert inputs_path.stat().st_size<=65536
    raw=inputs_path.read_bytes();inputs=closed_object(raw)
    assert set(inputs)=={'schema','source_sha256','payload_manifest_sha256','files'}
    assert inputs['schema']=='adhd/container-compiler-inputs@1'
    assert inputs['source_sha256']==expected_artifact and inputs['payload_manifest_sha256']==expected_manifest
    assert set(inputs['files'])=={'build.exs','boot.exs'}
    assert all(re.fullmatch('[a-f0-9]{64}',v) for v in inputs['files'].values())
    packaging=context/'packaging.tar';assert packaging.stat().st_size<=1024*1024
    content={};seen=set()
    with tarfile.open(packaging,mode='r:') as archive:
        members=archive.getmembers();assert len(members)==4
        for member in members:
            assert member.name not in seen;seen.add(member.name)
            if member.name=='packaging':assert member.isdir() and member.mode==0o755
            else:
                assert member.name in {'packaging/boot.exs','packaging/build.exs','packaging/inputs.json'}
                assert member.isfile() and member.mode==0o444 and 0<=member.size<=65536
                content[member.name.removeprefix('packaging/')]=archive.extractfile(member).read()
    assert set(content)=={'boot.exs','build.exs','inputs.json'} and content['inputs.json']==raw
    assert all(digest(content[name])==value for name,value in inputs['files'].items())
    # This is a declarative expected entrypoint, never an inference that the
    # actual image obeys it. Root must bind its actual inspect/cache audit too.
    expected_entrypoint=['elixir','/runtime/adhd/boot.exs','/app/hub.exs']
    assert b'ENTRYPOINT ["elixir", "/runtime/adhd/boot.exs", "/app/hub.exs"]' in dockerfile
    return {'schema':'adhd/compiled-context-binding@1','source_sha256':expected_artifact,
        'canonical_manifest_sha256':expected_manifest,'compiler_inputs_sha256':digest(raw),
        'packaging_files_sha256':inputs['files'],'expected_entrypoint':expected_entrypoint,
        'context_files_sha256':{name:digest((context/name).read_bytes())for name in sorted(expected)},
        'actual_runtime_or_cache_qualified':False}


def retained_cache_files(admission_path, admission, audit, binding, context):
    """Read exact retained raw cache manifest and metadata, not SHA declarations."""
    parent=Path(admission_path).absolute().parent
    assert parent.resolve(strict=True)==parent and parent.is_dir()
    values={};raws={}
    for filename,field in [('cache-manifest.json','cache_manifest_sha256'),('cache-metadata.json','cache_metadata_sha256')]:
        expected=admission['files'][filename]
        assert expected==audit[field]
        path=parent/filename;before=path.lstat()
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=1024*1024
        identity=lambda st:(st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor,'rb') as handle:
            assert identity(os.fstat(handle.fileno()))==identity(before)
            raw=handle.read(1024*1024+1);assert len(raw)<=1024*1024
            assert identity(os.fstat(handle.fileno()))==identity(before)
        assert identity(path.lstat())==identity(before)
        assert digest(raw)==expected
        raws[filename]=raw;values[filename]=closed_object(raw)
    cache=values['cache-manifest.json'];metadata=values['cache-metadata.json']
    assert set(cache)=={'schema','source','source_sha256','payload_manifest_sha256','inputs_sha256','boot_sha256','build_sha256','modules','beams','toolchain'}
    assert cache['schema']=='adhd/precompiled-cache@1' and cache['source']=='/app/hub.exs'
    assert cache['source_sha256']==binding['source_sha256']
    assert cache['payload_manifest_sha256']==binding['canonical_manifest_sha256']
    assert cache['inputs_sha256']==binding['compiler_inputs_sha256']
    assert cache['boot_sha256']==binding['packaging_files_sha256']['boot.exs']
    assert cache['build_sha256']==binding['packaging_files_sha256']['build.exs']
    # The ordinary payload verifier authenticates the full tar. This scoped read
    # additionally binds module names/order to this exact source SHA. No code is
    # compiled or evaluated; the selected source has column-zero defmodules.
    with tarfile.open(Path(context)/'payload.tar',mode='r:') as archive:
        sources=[m for m in archive.getmembers() if m.name=='app/hub.exs']
        assert len(sources)==1 and sources[0].isfile() and 0<sources[0].size<=8*1024*1024
        source=archive.extractfile(sources[0]).read()
    assert digest(source)==binding['source_sha256']
    modules=['Elixir.'+name for name in re.findall(r'^defmodule ([A-Z][A-Za-z0-9_.]*) do\s*$',source.decode(),re.M)]
    assert len(modules)==len(set(modules))==audit['cache_modules'] and cache['modules']==modules
    expected_beams={name+'.beam' for name in modules}
    assert set(cache['beams'])==expected_beams
    assert all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in cache['beams'].values())
    toolchain=cache['toolchain']
    assert set(toolchain)=={'anchors','architecture','elixir','erts','otp'}
    assert toolchain['elixir']=='1.20.4' and toolchain['otp']=='29' and toolchain['erts']=='17.1.1' and toolchain['architecture']=='x86_64-pc-linux-musl'
    expected_anchors={'/proc/self/exe'}|{'/usr/local/lib/elixir/bin/../lib/elixir/ebin/'+name for name in ['Elixir.Code.beam','Elixir.JSON.beam','Elixir.Kernel.beam','elixir.beam']}
    assert set(toolchain['anchors'])==expected_anchors and all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in toolchain['anchors'].values())
    files={'adhd/boot.exs':cache['boot_sha256'],'adhd/build.exs':cache['build_sha256'],
           'adhd/inputs.json':cache['inputs_sha256'],'adhd/manifest.json':digest(raws['cache-manifest.json']),
           **{'adhd/ebin/'+name:sha for name,sha in cache['beams'].items()}}
    directories={'/runtime':'0o755','adhd':'0o555','adhd/ebin':'0o555'}
    assert set(metadata)==set(files)|set(directories) and len(metadata)-1==audit['cache_entries']
    for name,row in metadata.items():
        assert set(row)=={'mode','mtime','sha256'} and type(row['mtime']) is int and row['mtime']==0
        if name in directories:assert row['mode']==directories[name] and row['sha256'] is None
        else:assert row['mode']=='0o444' and row['sha256']==files[name]
    return {'cache_manifest_sha256':digest(raws['cache-manifest.json']),
            'cache_metadata_sha256':digest(raws['cache-metadata.json']),
            'source_bound_module_order':modules,'cache_file_hashes_cross_checked':len(files),
            'cache_metadata_entries_including_runtime_parent':len(metadata)}


def compiled_admission(context, admission_path, admission_sha256, image, artifact, *, required=False):
    """Bind reviewed compiled audit declarations, alongside reviewed_payload().

    The caller still verifies the ordinary payload/host admission. This does not
    replace the independent actual cache gate or start the boot entrypoint.
    """
    context=Path(context)
    has_inputs=(context/'compiler-inputs.json').exists()
    assert not required or has_inputs, 'Compiled runtime admission required'
    admission_raw=Path(admission_path).read_bytes();assert digest(admission_raw)==admission_sha256
    admission=closed_object(admission_raw)
    if not has_inputs:
        assert 'compiled_runtime_audit' not in admission
        return None
    assert admission['passed'] is True and admission['image_config_identity']==image
    assert admission['artifact_sha256']==artifact
    binding=compiled_context(context,admission['canonical_manifest_sha256'],artifact)
    audit=admission['compiled_runtime_audit']
    assert audit['passed'] is True and audit['image_id']==image
    assert audit['artifact_sha256']==artifact
    assert audit['canonical_manifest_sha256']==binding['canonical_manifest_sha256']
    assert audit['compiler_inputs_sha256']==binding['compiler_inputs_sha256']
    for field in ('cache_manifest_sha256','cache_metadata_sha256'):
        assert isinstance(audit[field],str) and re.fullmatch('[a-f0-9]{64}',audit[field])
    assert type(audit['cache_modules']) is int and audit['cache_modules']==59
    assert type(audit['cache_entries']) is int and audit['cache_entries']==65
    assert audit['entrypoint']==binding['expected_entrypoint']
    assert audit['container_started'] is False and audit['owned_container_absent'] is True
    retained=retained_cache_files(admission_path,admission,audit,binding,context)
    return {**binding,'retained_cache_binding':retained,'reviewed_admission_sha256':admission_sha256,
            'reviewed_compiled_runtime_audit':audit,
            'actual_runtime_or_cache_qualified':False,
            'scope':'Staged/compiler bindings plus reviewed offline-audit declarations only; no runtime/SDK/readiness/reproducibility gate result.'}
