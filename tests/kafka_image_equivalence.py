#!/usr/bin/env python3
"""Verify an offline Kind OCI import retains original image config and layers.

The imported manifest may differ from its registry manifest. Only uncompressed
OCI tar layers are supported: their digests must equal Docker's rootfs diff IDs.
This is read-only and does not load, tag, run or publish images.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main(args):
    pairs=[]
    for pair in args.image:
        imported,original=pair.split('=',1)
        assert '@sha256:' in imported
        digest=imported.rsplit('@',1)[1]
        content=subprocess.check_output(['docker','exec',args.node,'ctr','-n','k8s.io','content','get',digest])
        assert 'sha256:'+hashlib.sha256(content).hexdigest()==digest
        manifest=json.loads(content)
        config_digest=manifest['config']['digest']
        config_bytes=subprocess.check_output(['docker','exec',args.node,'ctr','-n','k8s.io','content','get',config_digest])
        assert 'sha256:'+hashlib.sha256(config_bytes).hexdigest()==config_digest
        config=json.loads(config_bytes)
        local=json.loads(subprocess.check_output(['docker','image','inspect',original]))[0]
        assert local['Id']==config_digest
        assert config['rootfs']['diff_ids']==local['RootFS']['Layers']
        assert all(layer['mediaType']=='application/vnd.oci.image.layer.v1.tar' for layer in manifest['layers'])
        layers=[layer['digest'] for layer in manifest['layers']]
        assert layers==local['RootFS']['Layers']
        pairs.append({'imported_manifest':imported,'original_image':original,
            'image_config_digest':config_digest,'layer_count':len(layers),
            'uncompressed_layer_digest_list_sha256':hashlib.sha256(json.dumps(layers,separators=(',',':')).encode()).hexdigest()})
    report={'suite':'adhd/kind-import-config-layer-equivalence@1','passed':True,
        'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'images':pairs}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS immutable imported image config and every layer match originals')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--node',required=True,help='Explicit owned Kind Docker node container')
    p.add_argument('--image',action='append',required=True,help='imported-name@sha256:...=original-local-image-reference')
    p.add_argument('--report',type=Path,required=True)
    main(p.parse_args())
