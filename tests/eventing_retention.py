#!/usr/bin/env python3
"""Real Kafka DeleteRecords loss/reconstruction and immutable publication receipts.

Requires an explicitly owned disposable broker; never use a shared Kafka service.
Only successful real broker replies are forwarded. Fetch failures are injected
before upstream access, allowing actual appended records to expire unobserved.
"""
import argparse
import hashlib
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
import httpx
from federation_acceptance import Hub, Model, request
from federation_multi import wait


class Gateway:
    def __init__(self,upstream):
        self.block_fetch=False;self.produces=[];self.upstream=upstream;fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):self.forward()
            def do_GET(self):self.forward()
            def do_DELETE(self):self.forward()
            def forward(self):
                if fixture.block_fetch and self.command=='GET' and '/records?' in self.path:
                    self.send_error(503);return
                body=self.rfile.read(int(self.headers.get('Content-Length',0)))
                headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','content-length','connection','accept-encoding'}}
                try:
                    with httpx.Client(trust_env=False,timeout=10) as client:
                        r=client.request(self.command,fixture.upstream+self.path,content=body,headers=headers)
                except httpx.HTTPError:self.send_error(502);return
                if self.command=='POST' and self.path.startswith('/topics/') and r.is_success:
                    fixture.produces.append({'body':json.loads(body),'ack':r.json()})
                self.send_response(r.status_code);self.send_header('Content-Type',r.headers.get('Content-Type','application/json'))
                self.send_header('Content-Length',str(len(r.content)));self.end_headers()
                try:self.wfile.write(r.content)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True)
    p.add_argument('--work',required=True,type=Path);p.add_argument('--report',required=True,type=Path)
    p.add_argument('--eventing-rest-url',required=True);p.add_argument('--owned-broker-container',required=True)
    a=p.parse_args();a.work=a.work.resolve();a.work.mkdir(parents=True,exist_ok=True)
    model=Model();gate=Gateway(a.eventing_rest_url);h=Hub(json.loads(a.command),a.work/'hub','p',model.url)
    h.config.update(server_id=uuid4().hex,matcher=None,projects=[{'id':'p','name':'P'}],
        agent_projects={x:['p'] for x in ('alice','bob')},eventing={'enabled':True,'rest_url':gate.url,'retry_ms':100})
    report={'schema':'adhd/physical-retention@1','passed':False,'checks':[],
            'artifact_sha256':hashlib.sha256(Path(json.loads(a.command)[-1]).read_bytes()).hexdigest(),
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limitations':['DeleteRecords advances actual Kafka log start; this does not claim a wall-clock retention expiry wait.',
                           'One real broker; no replicated durability or semantic model claim.']}
    def record(name,**details):report['checks'].append({'name':name,'passed':True,**details});print('PASS',name,flush=True)
    def admin(op,**fields):
        code,r=request(h.base,'/admin/api',{'op':op,**fields},h.config['admin_token']);assert code==200,(code,r);return r
    def patch(value):
        admin('config_update',expected_revision=admin('config_get')['config_revision'],patch=value,message_id=uuid4().hex,confirm=True)
        h.config=json.loads((h.root/'config.json').read_text())
    def call(op,agent='alice',key=None,**fields):return h.call({'op':op,'project_id':'p',**fields},agent=agent,key=key)
    def rows():return call('poll','bob')['deliveries']
    def status():return admin('eventing_status',project_id='p')
    def receive(ids):return wait(lambda:ids<={r['publication_id'] for r in rows()},'Retained originals did not materialize',60)
    def offsets(topic):
        with httpx.Client(trust_env=False,timeout=5) as c:
            r=c.get(a.eventing_rest_url+'/topics/'+topic+'/partitions/0/offsets');r.raise_for_status();return r.json()
    try:
        h.start();call('subscribe','bob',mode='raw');all_ids=set();legacy=[]
        for op in ('publish','publish_record'):
            fields={'text':'Enabled receipt '+op,'source':{'kind':'slack','id':'receipts','item_id':uuid4().hex}}
            key=uuid4().hex;first=call(op,key=key,**fields)
            publication=first['publication'] if op=='publish' else first['record']['publication'];all_ids.add(publication['id'])
            assert first['eventing']=={'event_id':publication['id'],'project_sequence':first['eventing']['project_sequence'],'state':'pending'}
            assert type(first['eventing']['project_sequence']) is int
            assert call(op,key=key,**fields)==first
            again=call(op,**fields);assert again['eventing']==first['eventing']
        patch({'eventing':{'enabled':False}})
        for op in ('publish','publish_record'):
            fields={'text':'Legacy disabled receipt '+op,'source':{'kind':'slack','id':'receipts','item_id':uuid4().hex}}
            key=uuid4().hex;first=call(op,key=key,**fields);assert 'eventing' not in first
            publication=first['publication'] if op=='publish' else first['record']['publication'];all_ids.add(publication['id'])
            legacy.append((op,fields,key,first))
        patch({'eventing':{'enabled':True}})
        for op,fields,key,first in legacy:
            assert call(op,key=key,**fields)==first
            again=call(op,**fields);assert 'eventing' not in again
        receive(all_ids);acked={r['id'] for r in rows()};call('ack','bob',delivery_ids=list(acked))
        record('publish-and-publish-record-preserve-new-acceptance-message-source-retry-and-disabled-legacy-receipts')
        gate.block_fetch=True;pending=[]
        for i in range(2):pending.append(call('publish',text='Physical retention original '+str(i))['publication'])
        ids={r['id'] for r in pending};topic=status()['topic']
        wait(lambda:len([r for r in gate.produces if r['body']['records'][0]['value']['publication_id'] in ids])==2,'Accepted originals not actually appended',45)
        before=offsets(topic);checkpoint=status()['next_offset'];assert before['end_offset']>checkpoint
        assert not rows();h.stop(hard=True)
        payload={'partitions':[{'topic':topic,'partition':0,'offset':before['end_offset']}],'version':1}
        deleted=subprocess.run(['docker','exec','-i',a.owned_broker_container,'kafka-delete-records',
            '--bootstrap-server','localhost:9092','--offset-json-file','/dev/stdin'],input=json.dumps(payload),
            text=True,capture_output=True,check=True,timeout=30)
        assert 'low_watermark' in deleted.stdout,deleted.stdout
        after=offsets(topic);assert after['beginning_offset']==before['end_offset'],(before,after)
        gate.block_fetch=False;h.start();receive(ids)
        s=wait(lambda:(lambda x:x if x['gap'] and x['gap']['status']=='reconciled' else None)(status()),'Gap reconstruction not explicitly reconciled',45)
        assert s['gap']['reason']=='RETENTION_GAP' and set(s['gap']['missing_event_ids'])==ids,s
        assert s['gap']['from_offset']==checkpoint and s['gap']['to_offset']==after['beginning_offset']
        got=rows();assert {r['publication_id'] for r in got}==ids and len(got)==2
        assert not acked.intersection(r['id'] for r in got)
        assert {r['id'] for r in call('search',query='Physical retention original')['publications']}==ids
        for publication in pending:assert call('get',publication_id=publication['id'])['publication']==publication
        produced=[r['body']['records'][0]['value'] for r in gate.produces if r['body']['records'][0]['value']['publication_id'] in ids]
        assert len(produced)>=4
        for identity in ids:
            copies=[r for r in produced if r['publication_id']==identity];assert len(copies)>=2 and all(r==copies[0] for r in copies)
        call('ack','bob',delivery_ids=[r['id'] for r in got]);h.stop(hard=True);h.start();assert not rows()
        record('actual-delete-records-log-start-advancement-reconstructs-missing-originals-with-search-and-ack-preservation',
               physical_operation='Kafka Admin DeleteRecords via kafka-delete-records',
               previous_checkpoint=checkpoint,log_start_before=before['beginning_offset'],log_start_after=after['beginning_offset'],
               reconstructed_originals=len(ids))
        report['passed']=True
    finally:
        h.stop();gate.close();model.close();a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
