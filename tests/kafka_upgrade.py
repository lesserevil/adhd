#!/usr/bin/env python3
"""Real broker patch-upgrade handoff probe; operator owns the isolated broker rollout."""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from kafka_service import JSON_V2, V2, request, run, verify_retained


def committed(base, topic):
    marker = topic.split('.')[2]
    group = 'adhd-qualification-' + marker
    path = f'/consumers/{group}/instances/upgrade-checkpoint'
    request(base, 'POST', f'/consumers/{group}', {
        'name': 'upgrade-checkpoint', 'format': 'json',
        'auto.offset.reset': 'earliest', 'auto.commit.enable': 'false'})
    try:
        value = request(base, 'GET', path+'/offsets', {
            'partitions': [{'topic': topic, 'partition': 0}]})
        assert len(value['offsets']) == 1, value
        return value['offsets'][0]['offset']
    finally:
        request(base, 'DELETE', path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.phase == 'before':
        value = run(args.url)
        offset = committed(args.url, value['topic'])
        assert offset == 3, offset
        value['committed_group_next_offset'] = offset
        value['phase'] = 'before-upgrade'
    else:
        if not args.previous:
            parser.error('--phase after requires --previous')
        previous = json.loads(args.previous.read_text())
        value = verify_retained(args.url, previous)
        offset = committed(args.url, previous['topic'])
        assert offset == previous['committed_group_next_offset'] == 3, offset
        event = {'event_id': uuid4().hex, 'project_id': 'qualified', 'sequence': 3}
        produced = request(args.url, 'POST', f'/topics/{previous["topic"]}', {
            'records': [{'partition': 0, 'key': 'qualified', 'value': event}]}, media=JSON_V2, accept=V2)
        assert produced['offsets'] == [{'partition': 0, 'offset': 3, 'error_code': None, 'error': None}], produced
        value.update({'phase': 'after-upgrade', 'committed_group_next_offset_preserved': offset,
                      'new_publication_next_offset': 3, 'new_publication_acked': True})
    value['scope'] = 'real-broker-patch-upgrade-events-and-consumer-checkpoint'
    value['application_a2a_qualified'] = False
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
