#!/usr/bin/env python3
"""Verify the selected checkpoint and start its pinned Docker Compose service."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

CHECKPOINT_SHA256 = 'f892562cfd1dcd0ac7d245e1790edf7ea0f3e78bd3427ced5468b8bd874eb1fc'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=Path, help='BF16 checkpoint directory from the approved weights repository')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve(strict=True)
    if not checkpoint.is_dir():
        parser.error('checkpoint must be a directory')
    for name in ('config.json', 'tokenizer.json', 'modeling_nemotron_labs_diffusion.py',
                 'configuration_nemotron_labs_diffusion.py', 'modeling_ministral.py'):
        if not (checkpoint / name).is_file():
            parser.error(f'checkpoint is incomplete: missing {name}')
    config = json.loads((checkpoint / 'config.json').read_text())
    if not isinstance(config, dict):
        parser.error('checkpoint config must be an object')
    with (checkpoint / 'model.safetensors').open('rb') as weights:
        digest = hashlib.file_digest(weights, 'sha256').hexdigest()
    if digest != CHECKPOINT_SHA256:
        parser.error('checkpoint weights differ from the selected BF16 revision')
    print(json.dumps({'checkpoint_sha256': digest, 'verified': True}), flush=True)
    if not args.verify_only:
        root = Path(__file__).resolve().parents[1]
        environment = {**os.environ, 'MODEL_CHECKPOINT': str(checkpoint),
                       'MODEL_UID': str(os.getuid()), 'MODEL_GID': str(os.getgid())}
        subprocess.run(['docker', 'compose', '-f', str(root / 'deploy/model.compose.yaml'),
                        'up', '-d', '--wait', '--wait-timeout', '900'], env=environment, check=True)
        # Health reports engine readiness; a real request also verifies first-use
        # kernel compilation and scratch-mount permissions.
        port = int(environment.get('MODEL_PORT', '18770'))
        probe = {'model': 'Nemotron-Deciffusion-8B-v2.1',
                 'state': {'project': 'We build image decoders.'},
                 'questions': {'relevance': {'type': 'noul',
                     'instructions': 'Does this project build image decoders?'}}}
        with urlopen(Request(f'http://127.0.0.1:{port}/v1/systemone',
                             data=json.dumps(probe).encode(),
                             headers={'Content-Type': 'application/json'}), timeout=180) as response:
            answer = json.load(response)['answers']['relevance']
        value = answer['noul']
        if (answer['type'] != 'noul' or type(value) not in (int, float) or
                not math.isfinite(value) or not 0 <= value <= 1):
            raise SystemExit('Model started but did not return a valid typed probability')
        print(json.dumps({'ready': True, 'typed_inference': True}), flush=True)


if __name__ == '__main__':
    main()
