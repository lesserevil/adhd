#!/usr/bin/env python3
"""Real REST Proxy/Kafka probe; no in-memory transport, model, or application substitute."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uuid

V2 = 'application/vnd.kafka.v2+json'
JSON_V2 = 'application/vnd.kafka.json.v2+json'


def request(base, method, path, value=None, *, media=V2, accept=None):
    data = None if value is None else json.dumps(value).encode()
    req = Request(base.rstrip('/') + path, data=data, method=method,
                  headers={'Content-Type': media, 'Accept': accept or media})
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as error:
        raise AssertionError(f'{method} {path}: {error.code} {error.read().decode()}') from error


def run(base):
    marker = uuid.uuid4().hex
    topic = f'adhd.qualification.{marker}.events.v1'
    cluster = request(base, 'GET', '/v3/clusters', media='application/json')['data'][0]['cluster_id']
    request(base, 'POST', f'/v3/clusters/{cluster}/topics', {
        'topic_name': topic, 'partitions_count': 1, 'replication_factor': 1,
        'configs': [{'name':'retention.ms','value':'86400000'},
                    {'name':'cleanup.policy','value':'delete'}]}, media='application/json')
    events = [{'event_id':f'{marker}-{i}', 'project_id':'qualified', 'sequence':i} for i in range(3)]
    produced = request(base, 'POST', f'/topics/{topic}', {
        'records':[{'partition':0,'key':'qualified','value':event} for event in events]}, media=JSON_V2,accept=V2)
    assert all(item.get('error_code') is None for item in produced['offsets']), produced
    assert [item['offset'] for item in produced['offsets']] == [0,1,2], produced
    group = f'adhd-qualification-{marker}'
    path = f'/consumers/{group}/instances/probe'
    def create():
        request(base, 'POST', f'/consumers/{group}', {
            'name':'probe','format':'json','auto.offset.reset':'earliest','auto.commit.enable':'false'})
        request(base, 'POST', path+'/assignments', {'partitions':[{'topic':topic,'partition':0}]})
    def fetch(count):
        rows=[]
        until=time.monotonic()+30
        while len(rows)<count and time.monotonic()<until:
            rows.extend(request(base, 'GET',path+'/records?timeout=1000&max_bytes=1048576',accept=JSON_V2))
        return rows
    create()
    rows=fetch(3)
    assert [x['value'] for x in rows]==events, rows
    # A fetched record is not committed: replacement must repeat it.
    request(base,'DELETE',path)
    create()
    replay=fetch(3)
    assert [x['value'] for x in replay]==events, replay
    # REST v2 commits the LAST consumed offset; the broker stores next offset.
    # Commit only after simulated durable application materialization.
    request(base,'POST',path+'/offsets',{'offsets':[{'topic':topic,'partition':0,'offset':2}]})
    saved=request(base,'GET',path+'/offsets',{'partitions':[{'topic':topic,'partition':0}]})
    assert saved['offsets'][0]['offset']==3, saved
    request(base,'DELETE',path)
    create()
    # REST manual assignment does not recover a committed position automatically.
    request(base,'POST',path+'/positions',{'offsets':[{'topic':topic,'partition':0,'offset':3}]})
    after=request(base,'GET',path+'/records?timeout=1000&max_bytes=1048576',accept=JSON_V2)
    assert after==[], after
    request(base,'DELETE',path)
    configs=request(base,'GET',f'/v3/clusters/{cluster}/topics/{topic}/configs',media='application/json')
    retention={x['name']:x['value'] for x in configs['data']}
    assert retention['retention.ms']=='86400000',retention
    return {'passed':True,'scope':'real-kafka-rest-service-only','model_calls':0,
            'topic':topic,'produced':3,'read':3,'uncommitted_replayed':3,'committed_next_offset':3,
            'after_commit_read':0,'retention_ms':86400000,
            'event_digest':hashlib.sha256(json.dumps(events,sort_keys=True).encode()).hexdigest(),
            'application_a2a_qualified':False}


def verify_retained(base, previous):
    topic = previous['topic']
    group = 'adhd-retention-' + uuid.uuid4().hex
    path = f'/consumers/{group}/instances/probe'
    request(base, 'POST', f'/consumers/{group}', {
        'name':'probe', 'format':'json', 'auto.offset.reset':'earliest', 'auto.commit.enable':'false'})
    request(base, 'POST', path+'/assignments', {'partitions':[{'topic':topic,'partition':0}]})
    request(base, 'POST', path+'/positions', {'offsets':[{'topic':topic,'partition':0,'offset':0}]})
    rows=[]
    until=time.monotonic()+30
    while len(rows)<3 and time.monotonic()<until:
        rows.extend(request(base,'GET',path+'/records?timeout=1000&max_bytes=1048576',accept=JSON_V2))
    request(base,'DELETE',path)
    digest=hashlib.sha256(json.dumps([r['value'] for r in rows],sort_keys=True).encode()).hexdigest()
    assert len(rows)==3 and digest==previous['event_digest'], rows
    return {'passed':True,'scope':'real-kafka-retained-records-after-operator-replacement',
            'topic':topic,'retained_records':3,'event_digest':digest,
            'application_a2a_qualified':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:18082')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    result=(verify_retained(args.url,json.loads(args.verify_report.read_text()))
            if args.verify_report else run(args.url))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
