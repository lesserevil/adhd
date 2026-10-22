"""Read-only compiled-container context bindings; never loads a BEAM or image.

This proves staged compiler inputs only. Actual image runtime/cache audit and
runtime qualification are separate required admission evidence.
"""
import hashlib
import json
from pathlib import Path
import re
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
    return {**binding,'reviewed_admission_sha256':admission_sha256,
            'reviewed_compiled_runtime_audit':audit,
            'actual_runtime_or_cache_qualified':False,
            'scope':'Staged/compiler bindings plus reviewed offline-audit declarations only; no runtime/SDK/readiness/reproducibility gate result.'}
