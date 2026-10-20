#!/usr/bin/env python3
"""Independent retrieval-gap replay, candidate qualification and promotion checks."""
from __future__ import annotations
import argparse, asyncio, json, secrets, sys, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
from hub_acceptance import Hub
import httpx

class Services:
    def __init__(self):
        self.target=None;self.responses=[];self.questions=[];self.regress=False
        service=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,value):
                data=json.dumps(value).encode();self.send_response(200)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
                self.end_headers();self.wfile.write(data)
            def do_GET(self):self.reply({'ready':True})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/v1/systemone':
                    is_target='An observer saw a cardinal.' in json.dumps(body.get('state'))
                    self.reply({'model':body['model'],'answers':{key:{'type':'noul','noul':.99 if is_target else .01}
                        for key in body['questions']}});return
                context=json.loads(body['messages'][-1]['content']);service.questions.append(context)
                present=False
                def inspect(value):
                    nonlocal present
                    if isinstance(value,dict):
                        if value.get('text')=='An observer saw a cardinal.':present=True
                        if value.get('excerpt')=='An observer saw a cardinal.':present=True
                        for item in value.values():inspect(item)
                    elif isinstance(value,list):
                        for item in value:inspect(item)
                inspect(context)
                if 'ostrich' in context.get('question','').lower() or (service.regress and context.get('question')=='Was a cardinal reported?'): present=False
                result={'outcome':'supported' if present else 'no_evidence',
                    'answer':'A cardinal was reported.' if present else 'No supporting evidence.',
                    'facts':[{'statement':'A cardinal was reported.','publication_ids':[service.target]}] if present else [],
                    'evidence':[{'publication_id':service.target,'excerpt':'An observer saw a cardinal.','stance':'supports'}] if present else [],
                    'uncertainties':[],'requires_exhaustive':False,'complete':False,'coverage':{}}
                service.responses.append(result)
                self.reply({'model':'independent-evaluator','choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.base=f'http://127.0.0.1:{self.server.server_port}';self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)

async def wait(agent,qid,timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=await agent.call({'op':'query_result','query_id':qid})
        if value['query']['status'] in ('done','failed','partial','cancelled'):return value
        await asyncio.sleep(.1)
    raise AssertionError('query timeout')

async def admin(hub,op,**fields):
    command={'op':op,**fields}
    if op not in ('indexes','index_jobs','query_jobs'):
        command.update(confirm=True,message_id=fields.get('message_id',str(uuid4())))
    async with httpx.AsyncClient() as client:
        return await client.post(hub.base+'/admin/api',json=command,
            headers={'Authorization':'Bearer '+hub.config['admin_token']},timeout=10)

async def wait_index(hub,iid,states=('ready','active','rejected','failed'),timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        response=await admin(hub,'indexes',limit=100);assert response.status_code==200,response.text
        rows=response.json()['items']
        row=next((r for r in rows if r.get('id',r.get('index_id'))==iid),None)
        if row and row.get('state',row.get('status')) in states:return row
        await asyncio.sleep(.1)
    raise AssertionError('index timeout')

async def checks(command,root,record):
    services=Services();hub=Hub(command,root/'adaptation',services.base+'/v1/systemone')
    hub.config.update(admin_token=secrets.token_urlsafe(32),
        evaluator={'url':services.base+'/v1/chat/completions','model':'independent-evaluator'},
        retrieval={'candidate_limit':1,'semantic_pool':1,'context_depth':0,'audit_ppm':0},
        adaptation={'enabled':False,'recurrence':2,'min_training':1,'min_heldout':1,'min_regression':1,'cooldown_ms':1000})
    hub.config_file.write_text(json.dumps(hub.config));hub.start();a=await hub.agent('agent-a')
    try:
        insufficient=await admin(hub,'propose_index')
        assert insufficient.status_code==409,insufficient.text
        record('insufficient-feedback-leaves-active-index-unchanged')
        await a.call({'op':'publish','text':'Meeting notes about deadlines.'})
        target=(await a.call({'op':'publish','text':'An observer saw a cardinal.'}))['publication']
        services.target=target['id']
        # Ensure initial index has caught up before measuring a miss.
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            rows=(await admin(hub,'indexes')).json()['items']
            active=next((r for r in rows if r.get('state',r.get('status'))=='active'),None)
            if active and active.get('indexed_records',0)>=2:break
            await asyncio.sleep(.1)
        assert active,rows
        previous_id=active.get('id',active.get('index_id'))
        query_ids=[]
        for question in ['Was a cardinal reported?', 'Was an ostrich reported?']:
            q=await a.call({'op':'query','question':question,'view':'history','mode':'scan' if 'reported?' in question else 'search_then_scan'})
            result=await wait(a,q['query']['id'])
            assert result['query']['status']=='done',result
        for i in range(8):
            q=await a.call({'op':'query','question':'What wildlife appeared?','view':'history'})
            result=await wait(a,q['query']['id']);assert result['query']['status']=='done',result
            assert target['id'] in {e['publication_id'] for e in result['result']['evidence']},result
            query_ids.append(q['query']['id'])
        attempts=(await a.call({'op':'query_attempts','limit':100}))['attempts']
        assert any('retrieval_gap' in json.dumps(row) for row in attempts),attempts
        record('reproducible-search-miss-scan-recovery-and-durable-gap-classification')
        bad=await admin(hub,'propose_index',recipe={'context_depth':0,'chunk_bytes':2048,'bigrams':True,'semantic_pool':1})
        bad_id=bad.json()['index']['id'];await wait_index(hub,bad_id)
        assert (await admin(hub,'qualify_index',index_id=bad_id)).status_code==200
        rejected=await wait_index(hub,bad_id,states=('rejected',))
        assert not rejected['evaluation']['passed']
        assert next(r for r in (await admin(hub,'indexes')).json()['items'] if r['state']=='active')['id']==previous_id
        record('unimproved-candidate-rejected-without-changing-active-index')
        services.regress=True
        regression=await admin(hub,'propose_index',recipe={'context_depth':0,'chunk_bytes':2048,'bigrams':False,'semantic_pool':3})
        regression_id=regression.json()['index']['id'];await wait_index(hub,regression_id)
        await admin(hub,'qualify_index',index_id=regression_id)
        regression_result=await wait_index(hub,regression_id,states=('rejected',))
        assert regression_result['evaluation']['regressions']>0,regression_result
        services.regress=False
        record('successful-query-regression-rejects-otherwise-recovering-candidate')
        recipe={'context_depth':0,'chunk_bytes':2048,'bigrams':False,'semantic_pool':2}
        proposed=await admin(hub,'propose_index',recipe=recipe,message_id='independent-candidate-proposal')
        assert proposed.status_code==200,proposed.text
        assert (await admin(hub,'propose_index',recipe=recipe,message_id='independent-candidate-proposal')).json()==proposed.json()
        candidate=proposed.json()['index'];iid=candidate.get('id',candidate.get('index_id'))
        built=await wait_index(hub,iid,states=('ready','active','rejected','failed'))
        qualified=await admin(hub,'qualify_index',index_id=iid)
        assert qualified.status_code==200,qualified.text
        reviewed=await wait_index(hub,iid)
        assert reviewed.get('state',reviewed.get('status'))=='ready',reviewed
        assert any(key in json.dumps(reviewed) for key in ['heldout','evaluation']),reviewed
        record('declarative-candidate-build-and-disjoint-heldout-regression-qualification')
        extra=(await a.call({'op':'publish','text':'A concurrent observation during candidate catch-up.'}))['publication']
        promoted=await admin(hub,'promote_index',index_id=iid)
        assert promoted.status_code==200,promoted.text
        active=await wait_index(hub,iid,states=('active',))
        hub.stop(hard=True);hub.start()
        assert (await wait_index(hub,iid,states=('active',)))
        replay=await a.call({'op':'query_replay','query_id':query_ids[0],'index_id':iid})
        replayed=await wait(a,replay['query']['id'])
        original=await a.call({'op':'query_status','query_id':query_ids[0]})
        assert replayed['query']['snapshot_identity']==original['query']['snapshot_identity']
        assert extra['id'] not in {e['publication_id'] for e in replayed['result']['evidence']}
        record('qualified-promotion-catchup-hard-restart-and-same-snapshot-replay')
        rollback=await admin(hub,'rollback_index',index_id=previous_id)
        assert rollback.status_code==200,rollback.text
        await wait_index(hub,previous_id,states=('active',))
        refused=await admin(hub,'retire_index',index_id=previous_id)
        assert refused.status_code==409,refused.text
        retired=await admin(hub,'retire_index',index_id=iid)
        assert retired.status_code==200,retired.text
        assert (await a.call({'op':'get','publication_id':target['id']}))['publication']==target
        record('index-rollback-active-retirement-protection-and-original-evidence-retention')
        rejected=await admin(hub,'propose_index',recipe={'sql':'DROP TABLE publications'})
        assert rejected.status_code==400,rejected.text
        assert not (await a.call({'op':'search','query':'What wildlife appeared?'}))['publications']
        record('recipes-cannot-execute-code-and-feedback-cannot-become-source-evidence')
        await a.call({'op':'publish','text':'Resource-bound evidence '+('x'*4000)})
        hub.stop();hub.config['adaptation'].update(max_size_bytes=1024,max_build_retries=0)
        hub.config_file.write_text(json.dumps(hub.config));hub.start()
        resource=await admin(hub,'propose_index',recipe={'context_depth':0,'chunk_bytes':256,'bigrams':False,'semantic_pool':4})
        resource_id=resource.json()['index']['id']
        await wait_index(hub,resource_id,states=('failed',))
        assert (await admin(hub,'promote_index',index_id=resource_id)).status_code==409
        assert (await a.call({'op':'get','publication_id':target['id']}))['publication']==target
        record('resource-limited-build-cannot-promote-or-remove-original-evidence')
    finally:await a.close();hub.stop();services.close()


async def automatic_checks(command,root,record):
    services=Services();hub=Hub(command,root/'automatic',services.base+'/v1/systemone')
    hub.config.update(admin_token=secrets.token_urlsafe(32),
        evaluator={'url':services.base+'/v1/chat/completions','model':'independent-evaluator'},
        retrieval={'candidate_limit':1,'semantic_pool':1,'context_depth':0,'audit_ppm':0},
        adaptation={'enabled':False,'promotion':'automatic','recurrence':2,'min_training':1,'min_heldout':1,'min_regression':1,'cooldown_ms':1000})
    hub.config_file.write_text(json.dumps(hub.config));hub.start();a=await hub.agent('agent-a')
    try:
        await a.call({'op':'publish','text':'Meeting notes about deadlines.'})
        services.target=(await a.call({'op':'publish','text':'An observer saw a cardinal.'}))['publication']['id']
        await asyncio.sleep(1)
        original=next(r for r in (await admin(hub,'indexes')).json()['items'] if r['state']=='active')['id']
        for question in ['Was a cardinal reported?','Was an ostrich reported?']+['What wildlife appeared?']*8:
            q=await a.call({'op':'query','question':question,'view':'history','mode':'scan' if 'reported?' in question else 'search_then_scan'})
            assert (await wait(a,q['query']['id']))['query']['status']=='done'
        hub.stop();hub.config['adaptation']['enabled']=True
        hub.config_file.write_text(json.dumps(hub.config));hub.start()
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            rows=(await admin(hub,'indexes')).json()['items']
            active=next(r for r in rows if r['state']=='active')
            if active['id']!=original:break
            await asyncio.sleep(.2)
        assert active['id']!=original and active['evaluation']['passed'],rows
        assert active['recipe']['semantic_pool']==2
        assert active['evaluation']['heldout_recovery_ppm']==1000000
        await asyncio.sleep(2)
        assert len((await admin(hub,'indexes')).json()['items'])==2
        record('bounded-automatic-proposal-qualification-promotion-and-no-repeat-after-recovery')
    finally:await a.close();hub.stop();services.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True)
    p.add_argument('--work-dir',default='_build/tests/adaptation');p.add_argument('--report',default='verification/adaptation-acceptance.json')
    args=p.parse_args();root=Path(args.work_dir).resolve()/str(uuid4());root.mkdir(parents=True)
    cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    asyncio.run(checks(json.loads(args.command),root,record))
    asyncio.run(automatic_checks(json.loads(args.command),root,record))
    Path(args.report).write_text(json.dumps({'schema':'adhd/adaptation-acceptance@1','passed':True,'cases':cases},indent=2)+'\n')
if __name__=='__main__':main()
