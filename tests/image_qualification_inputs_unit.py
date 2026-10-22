"""Synthetic archive metadata guards; no application/runtime execution."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from image_qualification_inputs import reviewed_payload, freeze_inputs, sha


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        context, live = root / 'context', root / 'live'
        context.mkdir()
        (live / 'tests').mkdir(parents=True)
        (live / 'scripts').mkdir()
        (live / 'components/hub/presentation').mkdir(parents=True)
        (live / 'tests/helper.py').write_text('# current authored helper\n')
        (live / 'components/hub/presentation/spec.md').write_bytes(b'new live presentation intent')
        artifact = b'immutable target bytes, never executed'
        original_spec = b'old admitted presentation intent'
        dockerfile = b'FROM admitted-immutable-base\n'
        digest = lambda b: hashlib.sha256(b).hexdigest()
        manifest = {'schema':'adhd/container-inputs@1','files':{'hub.exs':digest(artifact),
            'specification/presentation/spec.md':digest(original_spec), 'Dockerfile':digest(dockerfile)}}
        raw = json.dumps(manifest).encode()
        (context / 'manifest.json').write_bytes(raw)
        (context / 'Dockerfile').write_bytes(dockerfile)
        image = 'sha256:' + 'a' * 64
        audit = {'passed':True,'image_id':image,'artifact_sha256':digest(artifact),
            'canonical_manifest_sha256':digest(raw),'actual_app_files':2,'canonical_specifications':1}
        admission = {'passed':True,'image_config_identity':image,'artifact_sha256':digest(artifact),
            'canonical_manifest_sha256':digest(raw),'payload_audit':audit,'component_lock_identity':'sha256:'+'b'*64}
        (context / 'admission.json').write_text(json.dumps(admission))
        payload = context / 'payload.tar'
        def archive(extra=None, changed=False):
            with tarfile.open(payload, 'w') as output:
                for name, body in {'app/hub.exs':artifact + (b'tampered' if changed else b''),
                        'app/specification/presentation/spec.md':original_spec,'app/manifest.json':raw}.items():
                    row = tarfile.TarInfo(name);row.size=len(body);output.addfile(row,io.BytesIO(body))
                if extra:
                    row = tarfile.TarInfo('app/escape');row.type=tarfile.SYMTYPE;row.linkname='/outside';output.addfile(row)
        def read():
            return reviewed_payload(context/'manifest.json',context/'admission.json',sha(context/'admission.json'),
                                    image,digest(artifact))
        archive()
        selected=read()
        frozen=root/'frozen';frozen.mkdir()
        inputs,drift=freeze_inputs(live,frozen,selected['specifications'])
        assert (frozen/'components/hub/presentation/spec.md').read_bytes()==original_spec
        assert 'components/hub/presentation/spec.md' in drift and 'tests/helper.py' in inputs
        for extra,changed in ((True,False),(False,True)):
            archive(extra,changed)
            try:
                read()
            except AssertionError:
                pass
            else:
                raise AssertionError('Redirected/tampered payload admitted')
    print('PASS image inputs3: exact target drift snapshot, redirected archive denial, payload hash denial')


if __name__ == '__main__':
    main()
