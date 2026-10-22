#!/usr/bin/env python3
"""Probe a real SystemOne service using independent typed relevance questions."""
import argparse
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18770/v1/systemone')
    parser.add_argument('--report', default='verification/model-service.json')
    args = parser.parse_args()
    base = args.url.removesuffix('/v1/systemone')
    with urlopen(base + '/health', timeout=10) as response:
        health = json.load(response)
    assert health.get('ready') is True, health
    request = {
        'model': 'Nemotron-Deciffusion-8B-v2.1',
        'state': {'project': {'description': 'We build image decoders and maintain PNG and JPEG libraries.'}},
        'questions': {
            'images': {'type': 'noul', 'instructions': 'Does this project build image decoding software?'},
            'finance': {'type': 'noul', 'instructions': 'Does this project build financial reporting tools?'}}}
    with urlopen(Request(args.url, data=json.dumps(request).encode(),
                         headers={'Content-Type': 'application/json'}), timeout=120) as response:
        result = json.load(response)
    scores = {}
    for name in request['questions']:
        answer = result['answers'][name]
        value = answer['noul']
        assert answer['type'] == 'noul' and type(value) in (int, float)
        assert math.isfinite(value) and 0 <= value <= 1
        scores[name] = value
    assert scores['images'] >= .9 and scores['finance'] < .9, scores
    report = {'schema': 'adhd/model-service-acceptance@1', 'passed': True,
              'model': request['model'], 'probabilities': scores,
              'expected_image': 'ghcr.io/pst2154/nemotron-deciffusion@sha256:494aac2d7af43b7a70234792623a510bf29045a45b3aa893bc3170108ded9cea',
              'expected_checkpoint_sha256': 'f892562cfd1dcd0ac7d245e1790edf7ea0f3e78bd3427ced5468b8bd874eb1fc'}
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print('PASS real SystemOne typed relevance and nonmatch')


if __name__ == '__main__':
    main()
