#!/usr/bin/env python3
"""Independent roadmap acceptance through public A2A/HTTP interfaces."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, secrets, sys, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
sys.path.insert(0, str(Path.cwd() / 'tests'))
from hub_acceptance import Hub, ModelFixture, domain_code
import httpx

class EvaluatorFixture:
    def __init__(self):
        self.mode = 'normal'
        self.calls = []
        self.answers = {}
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.calls.append(request)
                if fixture.mode == 'error':
                    self.send_response(503); self.end_headers(); return
                if fixture.mode == 'slow': time.sleep(2)
                context = json.loads(request['messages'][-1]['content'])
                result = {'outcome':'no_evidence','answer':'No supporting evidence is known.',
                    'facts':[],'evidence':[],'uncertainties':[],
                    'requires_exhaustive':False,'complete':False,'coverage':{}}
                question=context.get('question','')
                if question in fixture.answers: result.update(fixture.answers[question])
                if fixture.mode == 'forged':
                    result.update(outcome='supported', facts=[{'statement':'fabricated',
                        'publication_ids':['private-or-forged-id']}], evidence=[{
                        'publication_id':'private-or-forged-id','excerpt':'fabricated','stance':'supports'}])
                if fixture.mode == 'malformed': result={'not':'the contract'}
                response={'model':'independent-fixture','choices':[{'message':{'role':'assistant',
                    'content':json.dumps(result)},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':10,'completion_tokens':20}}
                data=json.dumps(response).encode()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)));self.end_headers()
                try: self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1/chat/completions'
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)

async def wait_query(agent, query_id, expected=('done','partial','failed','cancelled'), timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=await agent.call({'op':'query_result','query_id':query_id})
        if result['query']['status'] in expected: return result
        await asyncio.sleep(.1)
    raise AssertionError('Query failed to reach a terminal/partial state')

async def admin(hub, command):
    async with httpx.AsyncClient() as client:
        return await client.post(hub.base+'/admin/api',json=command,
            headers={'Authorization':'Bearer '+hub.config['admin_token']})

async def checks(command, root, record):
    model=ModelFixture(); evaluator=EvaluatorFixture()
    hub=Hub(command,root/'roadmap',model.url)
    hub.config.update(admin_token=secrets.token_urlsafe(32),evaluator={
        'url':evaluator.url,'model':'independent-fixture','version':'acceptance-v1'},
        retrieval={'audit_ppm':1000000,'candidate_limit':2,'semantic_pool':100})
    hub.config_file.write_text(json.dumps(hub.config));hub.start()
    a=await hub.agent('agent-a');b=await hub.agent('agent-b')
    try:
        question=(await a.call({'op':'publish','text':'Is there a bird in that tree?',
            'context':{'subject':'tree-42','conversation_id':'bird-observation'}}))['publication']
        yes_command={'op':'publish','text':'Yes','context':{'question':'Is there a bird in that tree?',
            'subject':'tree-42','reply_to':question['id'],
            'references':[{'publication_id':question['id'],'relation':'question'}],
            'snapshots':[{'uri':'https://example.invalid/observations','text':'Tree 42 observation context'}]},
            'source':{'kind':'agent','id':'agent-a','item_id':'context-event-1'}}
        yes=(await a.call(yes_command))['publication']
        assert yes['text']=='Yes' and yes['context']==yes_command['context']
        assert len(yes['content_identity'])==64
        assert (await a.call(yes_command))['publication']==yes
        correction=(await a.call({'op':'publish','text':'Actually, that was a leaf.',
            'context':{'references':[{'publication_id':yes['id'],'relation':'corrects'}]}}))['publication']
        assert (await b.call({'op':'get','publication_id':yes['id']}))['publication']==yes
        assert yes in (await b.call({'op':'search','query':'tree-42'}))['publications']
        private=(await a.call({'op':'send','recipient_id':'agent-b','text':'Private bird observation'}))['delivery']
        denied=await hub.raw('agent-a',{'op':'publish','text':'public leak',
            'context':{'reply_to':private['id']}})
        assert domain_code(denied)=='NOT_FOUND'
        for context in [{'unknown':True},{'references':[{'publication_id':yes['id'],'relation':'invented'}]},
                        {'question':' '},{'snapshots':[{'uri':'file:///secret','text':'x'}]}]:
            response=await hub.raw('agent-a',{'op':'publish','text':'invalid','context':context})
            assert 'error' in response.json()
        record('context-roundtrip-immutable-correction-source-retry-and-privacy')

        q='What is known about the tree?'
        evaluator.answers[q]={'outcome':'supported','answer':'The latest report calls it a leaf.',
            'facts':[{'statement':'Agent A later reported a leaf.','publication_ids':[correction['id']]}],
            'evidence':[{'publication_id':correction['id'],'excerpt':'Actually, that was a leaf.','stance':'supports'},
                        {'publication_id':yes['id'],'excerpt':'Yes','stance':'contradicts'}]}
        command_q={'op':'query','question':q,'mode':'scan'}
        submitted=await a.call(command_q,message_id='independent-query-retry')
        assert await a.call(command_q,message_id='independent-query-retry')==submitted
        query_id=submitted['query']['id']
        result=await wait_query(a,query_id)
        assert result['query']['status']=='done',result
        assert result['result']['outcome']=='supported' and result['result']['complete']
        assert result['query']['remaining_records']==0
        assert {e['publication_id'] for e in result['result']['evidence']}=={yes['id'],correction['id']}
        assert domain_code(await hub.raw('agent-b',{'op':'query_result','query_id':query_id}))=='FORBIDDEN'
        assert not (await b.call({'op':'search','query':q}))['publications']
        attempts=await a.call({'op':'query_attempts','query_id':query_id})
        assert attempts['attempts']
        replay=await a.call({'op':'query_replay','query_id':query_id})
        assert replay['replay_of']==query_id
        later=(await a.call({'op':'publish','text':'A new unrelated report after the snapshot.'}))['publication']
        replay_result=await wait_query(a,replay['query']['id'])
        assert replay_result['query']['snapshot_identity']==result['query']['snapshot_identity']
        assert later['id'] not in {e['publication_id'] for e in replay_result['result']['evidence']}
        record('grounded-query-jobs-ownership-attempt-isolation-and-snapshot-replay')

        partial=await a.call({'op':'query','question':'Read all observations.','mode':'scan',
            'budget':{'max_records':1,'max_calls':100,'timeout_ms':30000}})
        partial_result=await wait_query(a,partial['query']['id'])
        assert partial_result['query']['status']=='partial',partial_result
        assert not partial_result['result']['complete'] if partial_result['result'] else True
        hub.stop(hard=True);hub.start()
        continued=await a.call({'op':'query_continue','query_id':partial['query']['id']})
        final=await wait_query(a,partial['query']['id'])
        assert final['query']['status']=='done',final
        assert final['query']['snapshot_identity']==partial_result['query']['snapshot_identity']
        record('budget-continuation-and-query-checkpoint-hard-restart')

        evaluator.mode='slow'
        pending=await a.call({'op':'query','question':'cancel this independent query','mode':'scan'})
        cancelled=await a.call({'op':'query_cancel','query_id':pending['query']['id']})
        await asyncio.sleep(2.2)
        assert (await a.call({'op':'query_status','query_id':pending['query']['id']}))['query']['status']=='cancelled'
        evaluator.mode='normal'
        record('query-cancellation-discards-stale-inflight-results')

        for mode in ['forged','malformed','error']:
            evaluator.mode=mode
            invalid=await a.call({'op':'query','question':'Check invalid evaluation '+mode,'mode':'scan'})
            failed=await wait_query(a,invalid['query']['id'])
            assert failed['query']['status'] in ('failed','partial'),failed
            assert not failed.get('result') or not failed['result']['complete']
            assert (await b.call({'op':'get','publication_id':yes['id']}))['publication']['text']=='Yes'
        evaluator.mode='normal'
        record('malformed-ungrounded-and-unavailable-evaluator-never-fabricate-success')

        q2='Audit the observed tree state.'
        evaluator.answers[q2]=evaluator.answers[q]
        audit=await a.call({'op':'query','question':q2,'view':'history'})
        audited=await wait_query(a,audit['query']['id'])
        assert audited['query']['status']=='done',audited
        assert any('scan' in str(p) for p in audited['query']['execution_path']),audited
        indexes=await admin(hub,{'op':'indexes'})
        assert indexes.status_code==200 and indexes.json()['items']
        metadata=await admin(hub,{'op':'query_jobs'})
        assert metadata.status_code==200 and q not in metadata.text
        rebuild=await admin(hub,{'op':'rebuild_index','confirm':True,'message_id':'independent-rebuild'})
        assert rebuild.status_code==200,rebuild.text
        retry=await admin(hub,{'op':'rebuild_index','confirm':True,'message_id':'independent-rebuild'})
        assert retry.json()==rebuild.json()
        limited=await a.call({'op':'retrieve','question':'What is known about the tree?','limit':1})
        limited_result=await wait_query(a,limited['query']['id'])
        assert limited_result['query']['status']=='done' and len(limited_result['candidates'])==1,limited_result
        record('search-to-scan-audit-index-observation-and-idempotent-rebuild')
        hub.stop(hard=True)
        store=Path(hub.config['store_path']);journal=Path(str(store)+'.journal')
        assert journal.exists() and journal.stat().st_mode & 0o777==0o600
        committed=journal.read_bytes()
        store.write_bytes(b'unclean working image')
        hub.start()
        assert (await b.call({'op':'get','publication_id':yes['id']}))['publication']==yes
        hub.stop();journal.write_bytes(committed[:-1]+bytes([committed[-1]^1]))
        try:hub.start()
        except AssertionError:pass
        else:raise AssertionError('corrupt authoritative journal accepted')
        journal.write_bytes(committed);hub.start()
        assert (await b.call({'op':'get','publication_id':yes['id']}))['publication']==yes
        record('journal-recovers-unclean-image-and-rejects-checksum-corruption-without-history-loss')

    finally:
        await a.close();await b.close();hub.stop();evaluator.close();model.close()

async def live_checks(command,root,config_path,record):
    config=json.loads(Path(config_path).read_text())
    model=ModelFixture();hub=Hub(command,root/'live-evaluator',model.url)
    hub.config['evaluator']=config
    hub.config_file.write_text(json.dumps(hub.config));hub.start()
    a=await hub.agent('agent-a');b=await hub.agent('agent-b')
    try:
        start=(await a.call({'op':'publish','text':"I am working on branch 'foo' on project 'baz'.",'occurred_at':'2026-10-19T12:00:00Z'}))['publication']
        done=(await a.call({'op':'publish','text':"I am done with branch 'foo' on project 'baz'.",'occurred_at':'2026-10-19T13:00:00Z'}))['publication']
        bar=(await a.call({'op':'publish','text':"I am working on branch 'bar' on project 'baz'.",'occurred_at':'2026-10-19T13:01:00Z'}))['publication']
        await a.call({'op':'publish','text':"I am working on branch 'foo' on project 'baz'.",'occurred_at':'2026-10-19T11:00:00Z'})
        outcomes=[]
        for q in ["What is agent-a doing on project baz?", "Who is currently working on branch 'foo' on project 'baz'?"]:
            submitted=await b.call({'op':'query','question':q,'mode':'scan','budget':{'timeout_ms':120000}})
            response=await wait_query(b,submitted['query']['id'],timeout=120)
            assert response['query']['status']=='done',response
            assert response['result']['complete'],response
            outcomes.append(response['result'])
        # Independent assertions inspect grounded claims, not a generated native oracle.
        current=' '.join([f['statement'] for f in outcomes[0]['facts']]).lower()
        assert 'bar' in current,current
        assert not any('foo' in f['statement'].lower() and 'working' in f['statement'].lower()
            and not any(word in f['statement'].lower() for word in ['not','completed','done','no longer'])
            for f in outcomes[0]['facts']),outcomes[0]
        reverse=outcomes[1]['answer'].lower()
        assert any(word in reverse for word in ['no ','none','not ','completed','done','unknown']),reverse
        assert (await b.call({'op':'get','publication_id':start['id']}))['publication']==start
        assert (await b.call({'op':'get','publication_id':done['id']}))['publication']==done
        record('real-generative-current-facts-completion-late-report-independent-activity-and-history')
        subject='acceptance-tree-42'
        question=(await a.call({'op':'publish','information_type':'observation','text':'Is there a bird in that tree?','context':{'subject':subject}}))['publication']
        yes=(await a.call({'op':'publish','information_type':'observation','text':'Yes','context':{'question':'Is there a bird in that tree?','subject':subject,'reply_to':question['id']}}))['publication']
        presence=await b.call({'op':'query','question':'Do the reports establish bird presence in acceptance-tree-42?', 'scope':{'information_type':'observation'},'mode':'scan','budget':{'timeout_ms':120000}})
        presence_result=await wait_query(b,presence['query']['id'],timeout=150)
        assert presence_result['query']['status']=='done' and presence_result['result']['outcome']=='supported',presence_result
        assert yes['id'] in {e['publication_id'] for e in presence_result['result']['evidence']},presence_result
        cardinal=(await a.call({'op':'publish','information_type':'observation','text':'I see a cardinal in that tree.','context':{'subject':subject,'reply_to':question['id']}}))['publication']
        red=(await b.call({'op':'publish','information_type':'observation','text':'There is a red bird on the branch of that same tree.','context':{'subject':subject,'reply_to':question['id']}}))['publication']
        bird_results=[]
        for question_text,scope in [
            ('What bird species was explicitly reported for acceptance-tree-42?',{'information_type':'observation'}),
            ('What color was explicitly reported for a bird in acceptance-tree-42?',{'information_type':'observation'}),
            ('What color did agent-a explicitly report for the cardinal?',{'information_type':'observation','source_kind':'agent','source_id':'agent-a'}),
            ('How many distinct birds can be concluded from these reports about acceptance-tree-42?',{'information_type':'observation'})]:
            submitted=await b.call({'op':'query','question':question_text,'scope':scope,'mode':'scan','budget':{'timeout_ms':120000}})
            result=await wait_query(b,submitted['query']['id'],timeout=150)
            assert result['query']['status']=='done' and result['result']['complete'],result
            bird_results.append(result['result'])
        assert 'cardinal' in bird_results[0]['answer'].lower(),bird_results[0]
        assert cardinal['id'] in {e['publication_id'] for e in bird_results[0]['evidence']},bird_results[0]
        assert 'red' in bird_results[1]['answer'].lower() and red['id'] in {e['publication_id'] for e in bird_results[1]['evidence']},bird_results[1]
        assert bird_results[2]['outcome'] in ('unknown','no_evidence') or any(word in bird_results[2]['answer'].lower() for word in ['not','unspecified','unknown']),bird_results[2]
        assert bird_results[3]['uncertainties'] or any(word in bird_results[3]['answer'].lower() for word in ['uncertain','cannot','same bird','not enough','at least','unknown']),bird_results[3]
        record('real-generative-contextual-yes-explicit-species-color-and-uncertain-distinct-count')
        return {'model':config['model'],'results':outcomes,'bird_results':bird_results}
    finally:
        await a.close();await b.close();hub.stop();model.close()

async def retrieval_model_checks(command,root,matcher_url,record):
    evaluator=EvaluatorFixture();hub=Hub(command,root/'real-retrieval',matcher_url)
    hub.config.update(evaluator={'url':evaluator.url,'model':'independent-fixture'},retrieval={'audit_ppm':0,'candidate_limit':1,'semantic_pool':100})
    hub.config_file.write_text(json.dumps(hub.config));hub.start();a=await hub.agent('agent-a')
    try:
        target=(await a.call({'op':'publish','text':'The baz API changed. Clients must now supply the deployment revision.'}))['publication']
        await a.call({'op':'publish','text':'The office lunch menu contains soup.'})
        await a.call({'op':'publish','text':'There is a cardinal in the tree.'})
        await asyncio.sleep(1)
        question='Which software interface now requires a version parameter?'
        evaluator.answers[question]={'outcome':'supported','answer':'The baz API requires a deployment revision.',
            'facts':[{'statement':'The baz API requires a deployment revision.','publication_ids':[target['id']]}],
            'evidence':[{'publication_id':target['id'],'excerpt':target['text'],'stance':'supports'}]}
        q=await a.call({'op':'retrieve','question':question,'limit':1})
        result=await wait_query(a,q['query']['id'],timeout=60)
        assert result['query']['status']=='done',result
        assert [c['publication_id'] for c in result['candidates']]==[target['id']],result
        record('real-nemotron-contextual-paraphrase-candidate-ranking-and-caller-limit')
        return {'model':hub.config['matcher']['model'],'candidates':result['candidates']}
    finally:await a.close();hub.stop();evaluator.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--command',required=True);p.add_argument('--work-dir',default='_build/tests/roadmap')
    p.add_argument('--report',default='verification/roadmap-acceptance.json')
    p.add_argument('--evaluator-config');p.add_argument('--matcher-url')
    args=p.parse_args();command=json.loads(args.command)
    root=Path(args.work_dir).resolve()/str(uuid4());root.mkdir(parents=True)
    cases=[]
    def record(name): cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    async def run():
        await checks(command,root,record)
        retrieval=await retrieval_model_checks(command,root,args.matcher_url,record) if args.matcher_url else None
        generative=await live_checks(command,root,args.evaluator_config,record) if args.evaluator_config else None
        return {'generative':generative,'retrieval':retrieval}
    live=asyncio.run(run())
    report={'schema':'adhd/roadmap-acceptance@1','passed':True,'cases':cases,'live_evaluator':live}
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
