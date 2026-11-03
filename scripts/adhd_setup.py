#!/usr/bin/env python3
"""Validate a peer setup record and produce a stable ADHD publication command."""
import argparse
import datetime
import json
from pathlib import Path

FIELDS = {
    'requirement': {'authority': str, 'requires': list},
    'readiness': {'checks': list, 'limitations': list},
    'need': {'attempts': list, 'requested_help': str, 'grantor': str},
    'finding': {'procedure': list, 'applies_to': list, 'limitations': list},
}
STATES = {'proposed', 'verified', 'blocked', 'resolved', 'unsupported', 'unverified', 'claimed', 'superseded'}


def validate(record):
    if not isinstance(record, dict) or record.get('schema') != 'adhd.setup/1':
        raise ValueError('Expected adhd.setup/1 record')
    for key in ('record_id', 'subject', 'activity', 'platform', 'project_revision', 'observed_at'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError('Missing field: ' + key)
    timestamp = datetime.datetime.fromisoformat(record['observed_at'].replace('Z', '+00:00'))
    if timestamp.utcoffset() != datetime.timedelta(0):
        raise ValueError('observed_at must be UTC')
    if record.get('kind') not in FIELDS or record.get('state') not in STATES:
        raise ValueError('Invalid kind or state')
    for key in ('evidence', 'related', 'supersedes'):
        if not isinstance(record.get(key), list) or not all(isinstance(x, str) and x for x in record[key]):
            raise ValueError('Invalid list: ' + key)
    if record['state'] in ('verified', 'resolved') and not record['evidence']:
        raise ValueError('Verified/resolved records require evidence')
    details = record.get('details')
    if not isinstance(details, dict):
        raise ValueError('details must be an object')
    for key, kind in FIELDS[record['kind']].items():
        value = details.get(key)
        if not isinstance(value, kind) or (kind is str and not value.strip()):
            raise ValueError('Invalid detail: ' + key)
        if kind is list and not all(isinstance(x, str) and x for x in value):
            raise ValueError('Invalid detail list: ' + key)
    return record


def publication(record, project, agent):
    validate(record)
    return {'op': 'publish', 'project_id': project, 'information_type': 'adhd.setup',
            'text': record['kind'] + ': ' + record['subject'] + ' (' + record['state'] + ')',
            'data': record, 'source': {'kind': 'agent', 'id': agent, 'item_id': record['record_id']},
            'occurred_at': record['observed_at']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('record', type=Path)
    p.add_argument('--project', required=True)
    p.add_argument('--agent', required=True)
    args = p.parse_args()
    print(json.dumps(publication(json.loads(args.record.read_text(encoding='utf-8-sig')), args.project, args.agent), indent=2))


if __name__ == '__main__':
    main()
