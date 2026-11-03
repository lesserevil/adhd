#!/usr/bin/env python3
"""Publish a reviewed shared skill release under the configured release identity."""
import argparse
import json
from pathlib import Path
from adhd_skill_update import Updater, atomic, build, read_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, required=True)
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--sequence', type=int, required=True)
    p.add_argument('--notes', required=True)
    p.add_argument('--revoke', action='append', default=[])
    args = p.parse_args()
    updater = Updater(args.home)
    if updater.policy['agent_id'] != updater.policy['publisher_id']:
        raise SystemExit('This profile is not the configured release publisher')
    result = updater.transport({'op': 'search', 'project_id': updater.policy['project_id'],
                                'information_type': 'adhd.skills.release', 'source_kind': 'agent',
                                'source_id': updater.policy['publisher_id'], 'limit': 100})
    trusted = [p for p in result['publications'] if p.get('author_id') == updater.policy['publisher_id']
               and p.get('project_id') == updater.policy['project_id']
               and p.get('data', {}).get('channel') == updater.policy['channel']]
    latest = max(trusted, key=lambda p: p['data']['sequence']) if trusted else None
    if latest and args.sequence < latest['data']['sequence']:
        raise SystemExit('Release sequence must not regress')
    revoked = set(updater.state.get('revoked', [])) | set(args.revoke)
    if latest:
        revoked.update(latest['data'].get('revoked', []))
    manifest = build(args.sequence, args.root, args.notes, sorted(revoked))
    if latest and args.sequence == latest['data']['sequence']:
        if manifest['revision'] != latest['data']['revision']:
            raise SystemExit('Release sequence already binds different content')
        print(json.dumps({'publication_id': latest['id'], 'revision': manifest['revision'], 'sequence': args.sequence}))
        return
    item = 'skill-release-' + manifest['revision']
    command = {'op': 'publish', 'project_id': updater.policy['project_id'],
               'information_type': 'adhd.skills.release', 'text': manifest['notes'], 'data': manifest,
               'source': {'kind': 'agent', 'id': updater.policy['agent_id'], 'item_id': item}}
    saved = updater.root / 'published' / (item + '.json')
    previous = read_json(saved)
    if previous and previous != command:
        raise SystemExit('Saved release identity conflicts with payload')
    atomic(saved, command)
    response = updater.transport(command, item)
    publication = response.get('publication', {})
    if not publication.get('id'):
        raise SystemExit('Release was not accepted')
    print(json.dumps({'publication_id': publication['id'], 'revision': manifest['revision'], 'sequence': args.sequence}))


if __name__ == '__main__':
    main()
