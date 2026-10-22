#!/usr/bin/env python3
"""Model-free structural preflight of one fixed neutral lexical optimizer cohort.

Never forwards any model request and never creates an Archive query/proposal.
Successful structural evidence does not establish model quality or promotion.
"""
from __future__ import annotations
import asyncio
import copy
import json
from pathlib import Path
import re
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from multi_support import Evidence,arguments,scoped
from project_recovery_acceptance import Recovery,RED
from project_recovery_queries import NativeFixture,until
from project_recovery_state import digest


class ForbiddenModel:
    def __init__(self):
        self.posts=[];outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                outer.posts.append({'path':self.path,'length':self.headers.get('Content-Length')})
                self.send_response(503);self.send_header('Content-Length','0');self.end_headers()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1/systemone'
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)


def tokens(value):return set(re.findall(r'\w+',value.lower(),re.UNICODE))


async def main():
    parser=arguments(__doc__);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--recovery-schema',type=Path,required=True)
    args=parser.parse_args();assert args.hub and not args.with_model and not args.rest_url and not args.image
    raw=args.manifest.read_bytes();manifest=json.loads(raw)
    assert digest(args.hub.read_bytes())==manifest['target']['artifact_sha256']
    assert manifest['recipe']['semantic'] is False and manifest['recipe']['context_depth']==1
    assert manifest['history']=={'context_depth':2,'context_limit':32,'request_bytes':8192,'min_confidence_ppm':500000}
    training=[c for c in manifest['cases'] if c['cohort']=='training'];assert len(training)==2
    assert manifest['limits']['preflight_provider_posts']==0
    guard=ForbiddenModel();f=NativeFixture(args,initialize_projects=False)
    f.config.update(server_id=manifest['target']['server_id'],matcher={'url':guard.url,'model':'forbidden-preflight-model'},
        retrieval={'recipe':manifest['recipe']},history=manifest['history'],archive=manifest['archive'],
        recovery={'backup_root':str(f.root/'offline-backups')})
    Path(f.config['recovery']['backup_root']).mkdir(mode=0o700)
    e=Evidence(args.report,'neutral-optimizer-model-free-preflight');failure=None
    e.value.update(artifact_sha256=digest(args.hub.read_bytes()),harness_sha256=digest(Path(__file__).read_bytes()),
        manifest_sha256=digest(raw),scope='Only explicit lexical baseline recurrence prerequisites. No provider, Archive attempt, optimizer proposal, semantic quality or promotion.',
        dependency_sha256={str(p):digest(p.read_bytes()) for p in [args.recovery_schema,Path(__file__).with_name('multi_support.py'),Path(__file__).with_name('project_recovery_queries.py')]},
        frozen_manifest=manifest)
    try:
        await f.start()
        admin=f.admin();config=admin.call({'op':'config_get'})
        revision=config['config_revision']
        e.value['config_validation']=admin.call({'op':'config_validate','patch':{},'expected_revision':revision})
        assert e.value['config_validation']['valid'] is True and not guard.posts
        await Recovery(f,args.recovery_schema).initialize(RED);actor=await f.agent(manifest['target']['agent_id'])
        async def call(op,**fields):
            assert not guard.posts,'Model request attempted during forbidden-provider preflight'
            result=await actor.call(scoped(RED,op,**fields))
            assert not guard.posts,'Model request attempted during forbidden-provider preflight'
            return result
        captures={};resolved={}
        for case in training:
            ids={}
            for original in case['records']:
                fields=copy.deepcopy(original);key=fields.pop('key');reply=fields.pop('reply_to')
                if reply is not None:fields['context']={'links':[{'relation':'reply','publication_id':ids[reply]}]}
                record=(await call('publish_record',**fields))['record'];ids[key]=record['publication']['id']
                captures[case['id']+':'+key]=record
            resolved[case['id']]=ids
        e.value['frozen_originals']=captures;e.write()
        async def current():
            index=(await call('retrieval_index'))['index']
            return index if index['status']=='ready' and index['active']['indexed']==6 else None
        index=await until(current,'Exact six-original lexical index did not become ready',90)
        assert index['active']['recipe']==manifest['recipe'];e.value['index']=index
        for case in training:
            ids=resolved[case['id']];leaf=ids['2'];gold={ids[k] for k in case['gold']['support_keys']}
            query=(await call('retrieve',question=case['question'],scope=case['scope'],limit=case['limit']))['query']
            async def complete():
                result=(await call('get_retrieval',query_id=query['id']))['query']
                return result if result['status']!='pending' else None
            query=await until(complete,'Model-free lexical retrieval did not complete',30)
            assert query['status']=='completed' and query['candidates']==[] and query['usage']['calls']==0
            assert query['coverage']['total']==1 and query['evaluations']==[]
            shallow=await call('get_record',publication_id=leaf,max_depth=1,limit=32)
            full=await call('get_record',publication_id=leaf,max_depth=2,limit=32)
            shallow_records=[shallow['record']]+shallow['related'];full_records=[full['record']]+full['related']
            assert ids['0'] not in {r['publication']['id'] for r in shallow_records}
            assert gold<={r['publication']['id'] for r in full_records}
            assert not full['truncated'] and all(g['reason']=='cycle' for g in full['gaps'])
            words=tokens(case['question'])
            for record in shallow_records:
                p=record['publication'];fields=[p['text'],p['information_type'],p['author_id'],p['created_at'],p.get('occurred_at','')]
                fields+=list((p.get('source') or {}).values())
                assert all(not (words & tokens(v)) for v in fields if isinstance(v,str)),'Indexed metadata/content overlaps question'
            assert words & tokens(captures[case['id']+':0']['publication']['text'])
            e.record('fixed-training-baseline-has-zero-candidates-with-complete-gold-original-closure',case=case['id'],
                query=query,depth1=shallow,depth2=full,gold_ids=sorted(gold),provider_posts=0)
        assert not guard.posts;e.value['resolved_policies']=f.admin().call({'op':'config_get'})['config']
    except BaseException as error:failure=error;raise
    finally:
        cleanup=[]
        for close in [guard.close,f.close]:
            try:
                result=close()
                if asyncio.iscoroutine(result):await result
            except BaseException as error:cleanup.append(type(error).__name__)
        e.value.update(forbidden_model_attempts=guard.posts,provider_posts=0,cleanup_failures=cleanup)
        f.bind_evidence(e);e.finish(failure or (RuntimeError('cleanup') if cleanup else None))
        if cleanup and failure is None:raise RuntimeError('Owned preflight cleanup failed')


if __name__=='__main__':asyncio.run(main())
