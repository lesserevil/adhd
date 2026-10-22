"""Pure compiler-input/source/context drift probes; no image or code loads."""
import io,json,tarfile,tempfile
from pathlib import Path
from image_compiled_inputs import compiled_context,digest


def make(root,kind=None):
    source='b'*64;docker=b'ENTRYPOINT ["elixir", "/runtime/adhd/boot.exs", "/app/hub.exs"]\n'
    manifest=json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':source,'Dockerfile':digest(docker)}}).encode()
    files={'boot.exs':b'synthetic boot text','build.exs':b'synthetic compiler text'}
    inputs={'schema':'adhd/container-compiler-inputs@1','source_sha256':source,'payload_manifest_sha256':digest(manifest),'files':{k:digest(v)for k,v in files.items()}}
    if kind=='source':inputs['source_sha256']='c'*64
    if kind=='manifest':inputs['payload_manifest_sha256']='c'*64
    if kind=='unknown':inputs['files']['foreign.exs']='c'*64
    raw=json.dumps(inputs).encode();(root/'compiler-inputs.json').write_bytes(raw)
    (root/'manifest.json').write_bytes(manifest);(root/'Dockerfile').write_bytes(docker);(root/'payload.tar').write_bytes(b'synthetic opaque payload; separately checked by reviewed_payload')
    with tarfile.open(root/'packaging.tar','w') as archive:
        directory=tarfile.TarInfo('packaging');directory.type=tarfile.DIRTYPE;directory.mode=0o755;archive.addfile(directory)
        for name,value in {**files,'inputs.json':raw}.items():
            member=tarfile.TarInfo('packaging/'+name);member.size=len(value);member.mode=0o444
            if kind=='redirect' and name=='boot.exs':member.type=tarfile.SYMTYPE;member.linkname='/outside';member.size=0;archive.addfile(member);continue
            if kind=='boot-hash' and name=='boot.exs':value=b'different compiler input';member.size=len(value)
            if kind=='duplicate-inputs' and name=='inputs.json':value=b'{"schema":1,"schema":2}';member.size=len(value)
            archive.addfile(member,io.BytesIO(value))
    if kind=='extra':(root/'unbound').write_bytes(b'extra')
    if kind=='symlink':(root/'payload.tar').unlink();(root/'payload.tar').symlink_to('/dev/null')
    if kind=='dockerfile':(root/'Dockerfile').write_bytes(docker+b'foreign')
    return digest(manifest),source


def main():
    count=0
    with tempfile.TemporaryDirectory() as temp:
        for kind in [None,'source','manifest','unknown','redirect','boot-hash','duplicate-inputs','extra','symlink','dockerfile']:
            root=Path(temp)/str(kind);root.mkdir();manifest,source=make(root,kind)
            try:result=compiled_context(root,manifest,source)
            except AssertionError:assert kind is not None
            else:assert kind is None and result['actual_runtime_or_cache_qualified'] is False
            count+=1
    print(json.dumps({'passed':True,'checks':count,'image_compiler_provider_starts':0}))


if __name__=='__main__':main()
