#!/usr/bin/env python3
"""Publish a reviewed updater executable using the operator-selected release identity."""
import argparse
import hashlib
import json
from pathlib import Path
from adhd_skill_update import Updater, BOOTSTRAP, atomic, digest, validate_bootstrap


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, required=True)
    p.add_argument('--sequence', type=int, required=True)
    p.add_argument('--predecessor', action='append', required=True)
    p.add_argument('--file', type=Path, default=Path(__file__).with_name('adhd_skill_update.py'))
    args = p.parse_args()
    u = Updater(args.home)
    if u.policy['agent_id'] != u.policy['publisher_id']:
        raise SystemExit('Profile is not the trusted publisher')
    text = args.file.read_text()
    m = dict(schema='adhd.bootstrap/1', sequence=args.sequence, version=BOOTSTRAP,
             channel=u.policy['channel'], text=text,
             sha256=hashlib.sha256(text.encode()).hexdigest(), predecessors=sorted(set(args.predecessor)))
    m['revision'] = digest(m); validate_bootstrap(m)
    old = u.transport({'op':'search', 'project_id':u.policy['project_id'],
                      'information_type':'adhd.bootstrap.release', 'source_kind':'agent',
                      'source_id':u.policy['publisher_id'], 'limit':100})
    for pub in old.get('publications', []):
        if pub.get('author_id') != u.policy['publisher_id'] or pub.get('project_id') != u.policy['project_id']:
            continue
        previous = pub.get('data', {})
        if previous.get('channel') != m['channel']: continue
        if previous['sequence'] > m['sequence'] or (previous['sequence'] == m['sequence'] and previous['revision'] != m['revision']):
            raise SystemExit('Sequence must advance without conflict')
        if previous['revision'] == m['revision']:
            print(json.dumps({'publication_id':pub['id'], 'sha256':m['sha256']})); return
    item = 'bootstrap-' + m['revision']
    cmd = dict(op='publish', project_id=u.policy['project_id'], information_type='adhd.bootstrap.release',
               text='Reviewed ADHD bootstrap update ' + str(args.sequence), data=m,
               source=dict(kind='agent', id=u.policy['agent_id'], item_id=item))
    atomic(u.root/'published'/(item+'.json'), cmd)
    result = u.transport(cmd, item)
    print(json.dumps({'publication_id':result['publication']['id'], 'sha256':m['sha256']}))

if __name__ == '__main__': main()
