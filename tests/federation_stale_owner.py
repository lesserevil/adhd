#!/usr/bin/env python3
"""Real v2 owner-cache expiry/outage with a reachable noncanonical copy.

Uses existing independent Hub/RuntimeTarget helpers and transparent bounded HTTP
observers, never generated modules/stores. Controlled model, no external model.
Eventing is disabled; this narrow test does not requalify Kafka or deployments.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from eventing_target import RuntimeTarget, add_target_arguments
from federation_acceptance import Model, request
from federation_multi import SCOPE, wait


class Observer:
    """Bounded transparent local forwarding; never records bearer credentials."""
    def __init__(self, destination):
        self.rows = []
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(4)
        self.destination = urlsplit(destination)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass

            def do_POST(self):
                if not outer.slots.acquire(blocking=False):
                    self.send_error(429); return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    assert 0 < length <= 262144
                    assert self.path == '/federation/v2'
                    body = self.rfile.read(length)
                    payload = json.loads(body)
                    connection = http.client.HTTPConnection(outer.destination.hostname,
                                                            outer.destination.port, timeout=2)
                    try:
                        connection.request('POST', self.path, body=body, headers={
                            'Content-Type': 'application/json',
                            'Authorization': self.headers.get('Authorization', '')})
                        response = connection.getresponse()
                        status, raw = response.status, response.read(262145)
                        assert len(raw) <= 262144
                    except OSError:
                        status, raw = 502, b'{"error":{"code":"OWNER_UNREACHABLE"}}'
                    finally:
                        connection.close()
                    with outer.lock:
                        assert len(outer.rows) < 2048, 'Bounded observer request inventory exceeded'
                        outer.rows.append({'request': payload, 'status': status,
                                           'response': json.loads(raw),
                                           'bearer_present': self.headers.get('Authorization', '').startswith('Bearer ')})
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    try: self.wfile.write(raw)
                    except (BrokenPipeError, ConnectionResetError): pass
                finally:
                    outer.slots.release()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def snapshot(self):
        with self.lock: return json.loads(json.dumps(self.rows))

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_target_arguments(parser)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    target = RuntimeTarget(args)
    root = args.work.resolve()
    assert not root.exists(), 'Fresh private work directory required'
    root.mkdir(parents=True, mode=0o700)
    model, hubs, observers = Model(), [], []
    report = {'schema': 'adhd/federation-v2-stale-canonical-owner@1', 'passed': False,
              'checks': [], 'limitations': ['Controlled model; no semantic quality or external model use.',
                  'Eventing explicitly disabled; Kafka, deployment and lifecycle admission are separate gates.'],
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), **target.report()}
    report['dependency_sha256'] = {name+'.py': hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest()
                                  for name in ['eventing_target', 'federation_acceptance', 'federation_multi']}

    def record(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
        print('PASS', name, flush=True)

    def call(hub, op, **fields):
        return hub.call({'op': op, 'project_id': 'shared', **fields})

    def admin(hub, body, mutation=False):
        if mutation:
            revision = admin(hub, {'op': 'config_get'})['config_revision']
            body = {**body, 'expected_revision': revision, 'message_id': uuid4().hex, 'confirm': True}
        status, result = request(hub.base, '/admin/api', body, hub.config['admin_token'])
        assert status == 200, (status, result)
        if mutation: hub.config = json.loads((hub.root/'config.json').read_text())
        return result

    def query(hub, question):
        initial = call(hub, 'source_query', sources=[SCOPE], question=question, deadline_ms=3000)['query']
        def done():
            q = call(hub, 'get_source_query', query_id=initial['id'])['query']
            return q if q['status'] != 'pending' else None
        return wait(done, 'Source query failed to become terminal', 12)

    try:
        for index in range(3):
            hub = target.hub(root/('server-'+str(index)), 'shared', model.url)
            entries = [] if index == 0 else [{'scope': SCOPE, 'aliases': ['canonical-fixture'],
                'description': 'Canonical image decoders.' if index == 1 else 'Noncanonical image decoders copy.',
                'relationship': 'contained', 'canonical': index == 1, 'export_publication_ids': []}]
            hub.config.update(server_id=uuid4().hex, eventing={'enabled': False},
                agent_projects={'alice': ['shared'] if index == 0 else ['other'], 'bob': ['shared']},
                projects=[{'id': project, 'name': project, 'status': 'active', 'description': 'Fixture',
                    'settings': {'federation': {'description': 'This project builds image decoders.',
                        'catalog': {'visible': True, 'entries': entries if project == 'other' else []}}}}
                    for project in ['shared', 'other', 'hidden']],
                )
            hub.config['federation'].update(share_identities=True,
                catalog={'visible': True, 'entries': []}, peers=[])
            hubs.append(hub)
        a, b, c = hubs
        observers = [Observer(b.base), Observer(c.base)]
        tokens = {(x,y):secrets.token_urlsafe(32) for x,y in [(0,1),(1,0),(0,2),(2,0)]}
        a.config['federation']['peers'] = [{'server_id':hub.config['server_id'],
            'url':observer.url, 'token':tokens[0,index], 'inbound_token':tokens[index,0],
            'project_pairs':[{'local_project_id':'shared','remote_project_id':'other'}]}
            for index,hub,observer in [(1,b,observers[0]),(2,c,observers[1])]]
        for index,hub in [(1,b),(2,c)]:
            hub.config['federation']['peers'] = [{'server_id':a.config['server_id'], 'url':a.base,
                'token':tokens[index,0], 'inbound_token':tokens[0,index],
                'project_pairs':[{'local_project_id':'other','remote_project_id':'shared'}]}]
        for hub in hubs: hub.start()
        roles = ['Developer', 'Admin', 'Viewer']
        users = []
        for index,(hub,role) in enumerate(zip(hubs,roles)):
            admitted = ['shared'] if index==0 else ['other']
            user = admin(hub, {'op':'save_user','user':{'username':'same-person','name':'Same Person',
                'email':'same-person@example.invalid','role':role,'project_ids':admitted,'password':secrets.token_urlsafe(24)}}, True)['user']
            users.append(user)
            admin(hub, {'op':'config_update','patch':{'auth':{'mode':'local','allow_admin_token':True},
                'agent_owners':{'alice':user['id']},'agent_projects':{'alice':admitted}}}, True)
        wait(lambda: all(row['status']=='ready' for row in call(a,'federation_directory')['peers'])
             and len(call(a,'federation_directory')['peers'])==2, 'Paired v2 catalogs did not warm')
        matches = wait(lambda: (lambda v: v if len(v['matches'])==2 else None)(call(a,'identity_matches')),
                       'Same-email minimal v2 identities did not correlate')
        assert all(not any(k in row for k in ['role','groups','oidc']) for row in matches['matches'])
        record('three-real-hubs-explicit-v2-project-pairs-minimal-identities-and-independent-server-roles')
        warm = query(a, 'Warm canonical image decoders owner routing')
        row = warm['results'][0]
        assert warm['status']=='completed' and row['status']=='answered', warm
        assert (row['owner_server_id'],row['owner_project_id'])==(b.config['server_id'],'other')
        assert (row['response']['server_id'],row['response']['project_id'])==(b.config['server_id'],'other')
        model_before = len(model.states)
        source_ops = lambda rows:[row for row in rows if row['request']['op'].startswith('source_')]
        assert source_ops(observers[0].snapshot()) and not source_ops(observers[1].snapshot())
        record('warm-query-pins-canonical-server-project-and-observed-v2-source-wire-only-to-owner')
        b.stop()
        owner_stopped=b.process.poll() is not None
        assert owner_stopped
        snapshots=[row['response'] for row in observers[0].snapshot()
                   if row['status']==200 and row['request']['op']=='catalog' and 'generated_at' in row['response']]
        assert snapshots and all(row['max_age_ms']==10000 for row in snapshots)
        expiry=max(datetime.fromisoformat(row['generated_at'].replace('Z','+00:00')).timestamp()*1000
                   +row['max_age_ms'] for row in snapshots)
        remaining=expiry-time.time()*1000
        assert remaining<=11000
        if remaining>0: time.sleep(remaining/1000+.25)
        assert time.time()*1000>expiry
        directory=wait(lambda:(lambda v:v if any(row['server_id']==b.config['server_id'] and row['status']=='unavailable'
            for row in v['peers']) else None)(call(a,'federation_directory')), 'Owner unavailable observation missing')
        owner=next(row for row in directory['peers'] if row['server_id']==b.config['server_id'])
        copy=next(row for row in directory['peers'] if row['server_id']==c.config['server_id'])
        assert owner['catalog']==[] and copy['status']=='ready' and copy['catalog'][0]['canonical'] is False
        cold=query(a,'Expired owner must never use the reachable noncanonical copy')
        row=cold['results'][0]
        assert cold['status']=='partial' and row['status']=='unavailable' and row['response'] is None, cold
        assert datetime.fromisoformat(cold['created_at'].replace('Z','+00:00')).timestamp()*1000>expiry
        assert (row['owner_server_id'],row['owner_project_id'])==(b.config['server_id'],'other')
        assert any(row['project_id']=='other' and row['status']=='unavailable' for row in cold['coverage'])
        assert not source_ops(observers[1].snapshot()) and len(model.states)==model_before
        record('actual-owner-stopped-catalog-ten-second-ttl-expired-partial-unavailable-never-noncanonical-fallback',
               catalog_ttl_ms=10000, expiry_observed=True, owner_process_stopped=owner_stopped,
               last_catalog_generated_at=max(snapshots,key=lambda item:item['generated_at'])['generated_at'],
               owner_catalog_expiry_ms=int(expiry), directory_observation=directory,
               no_outage_inference=True, query=cold)
        b.start()
        wait(lambda: all(row['status']=='ready' for row in call(a,'federation_directory')['peers']),
             'Recovered owner fresh catalog did not become ready')
        recovered=query(a,'Fresh recovered canonical image decoders owner routing')
        row=recovered['results'][0]
        assert recovered['status']=='completed' and row['status']=='answered', recovered
        assert (row['owner_server_id'],row['owner_project_id'])==(b.config['server_id'],'other')
        assert (row['response']['server_id'],row['response']['project_id'])==(b.config['server_id'],'other')
        assert not source_ops(observers[1].snapshot())
        a.call({'op':'source_query','project_id':'hidden','sources':[SCOPE], 'question':'Forbidden hidden'},error='PROJECT_NOT_FOUND')
        a.call({'op':'source_query','project_id':'shared','project_ids':['hidden'], 'sources':[SCOPE],
                'question':'Forbidden hidden selected project'},error='PROJECT_NOT_FOUND')
        for hub,user,role in zip(hubs,users,roles):
            rows=admin(hub,{'op':'config_get'})['config']['users']
            assert next(row for row in rows if row['id']==user['id'])['role']==role
        all_wire=[row for observer in observers for row in observer.snapshot()]
        assert all(row['request']['protocol_version']==2 and row['bearer_present'] for row in all_wire)
        assert all(row['request']['origin_server_id']==a.config['server_id'] and row['request']['origin_project_id']=='shared'
                   for row in all_wire)
        assert all(row['request'].get('destination_project_id','other')=='other' for row in all_wire)
        assert 'hidden' not in json.dumps(all_wire)
        assert all(not any(key in json.dumps(row['response']) for key in ['"role"','"groups"','"password"','"oidc"']) for row in all_wire)
        report['source_wire']={'canonical':source_ops(observers[0].snapshot()),'noncanonical':source_ops(observers[1].snapshot())}
        record('recovered-fresh-owner-routing-retains-v2-provenance-hidden-project-denial-and-local-roles')
        report['passed']=True
    except BaseException as error:
        report['failure_type']=type(error).__name__
        raise
    finally:
        for hub in hubs: hub.stop()
        for observer in observers: observer.close()
        model.close()
        report['model_requests']=len(model.states)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__': main()
