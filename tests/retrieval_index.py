#!/usr/bin/env python3
"""Black-box native BM25 oracle, derived resource failure and interrupted rebuild."""
import argparse,hashlib,json,math,re,secrets,tempfile,time
from pathlib import Path
from foundation_acceptance import Runtime,Client,free_port
from retrieval_support import NoulFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--command');m.add_argument('--image');p.add_argument('--report',default='verification/retrieval-index.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/retrieval-index-tests').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=NoulFixture();cases=[]
    config={'project_id':'index-fixture','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'},'retrieval':{'recipe':{'semantic':False,'include_context':False},'build_batch':1}}
    h.file.write_text(json.dumps(config));h.file.chmod(0o600)
    def wait(fn,message='Index deadline',seconds=45):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            v=fn()
            if v:return v
            time.sleep(.01)
        raise AssertionError(message)
    def rpc(body):return Client(h).rpc(body,h.config['agents']['alice'])
    def index():return rpc({'op':'retrieval_index'})['index']
    def ready():return wait(lambda:(v if (v:=index())['status'] in ('ready','partial') and v['building'] is None else None))
    def update(patch):return Client(h,h.config['admin_token']).api({'op':'config_update','patch':{'retrieval':patch}},mutation=True)
    def publish(text,kind='oracle'):return rpc({'op':'publish_record','text':text,'information_type':kind,'source':{'kind':'test','id':str(secrets.token_hex(8))}})['record']['publication']
    def finish(q):return wait(lambda:(v if (v:=rpc({'op':'get_retrieval','query_id':q['id']})['query'])['status']!='pending' else None))
    def query(scope,question='alpha beta'):return finish(rpc({'op':'retrieve','question':question,'scope':scope,'limit':64})['query'])
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    try:
        h.start();a=publish('alpha alpha beta');b=publish('beta gamma gamma gamma');publish('alpha '*30,'outside');ready()
        q=query({'information_type':'oracle'});assert q['status']=='completed' and q['usage']['calls']==0
        # Independently reconstruct every indexed field from public original records.
        documents=[]
        for pub in [a,b]:
            values=[pub['text'],json.dumps(pub['data'],ensure_ascii=False,sort_keys=True,separators=(',',':')),pub['information_type']]
            values += [pub.get('source',{}).get(k) for k in ('kind','id','item_id','uri')]
            values += [pub.get(k) for k in ('author_id','created_at','occurred_at')]
            terms=re.findall(r'\w+',' '.join(v for v in values if isinstance(v,str)).lower());documents.append(terms)
        mean=sum(map(len,documents))/2
        for pub,terms in zip([a,b],documents):
            score=0
            for word in ('alpha','beta'):
                tf=terms.count(word);df=sum(word in d for d in documents)
                if tf:score+=math.log(1+(2-df+.5)/(df+.5))*tf*2.2/(tf+1.2*(.25+.75*len(terms)/mean))
            expected=math.floor(1_000_000*score/(1+score)+.5);candidate=next(c for c in q['candidates'] if c['publication_id']==pub['id'])
            assert candidate['lexical_ppm']==expected and candidate['score_ppm']==expected and candidate['semantic_ppm'] is None,(candidate,expected)
        record('independent-bm25-scope-statistics-normalization-and-lexical-only-no-model')
        original=ready()['active'];pid=h.pid;update({'max_records':1});limited=ready();assert limited['status']=='partial' and limited['active']['indexed']==1 and limited['active']['excluded']==2
        one=query({'source_id':a['source']['id']});assert one['status']=='completed' and one['coverage']['indexed']==1
        missing=query({'source_id':b['source']['id']});assert missing['status']=='partial' and missing['error']['code']=='INDEX_STALE' and not missing['evaluations']
        # Continue a real unavailable scope through the declared run cap; every
        # run preserves its old error and evidence rather than fabricating results.
        for run in range(2,17):
            missing=finish(rpc({'op':'continue_retrieval','query_id':missing['id']} )['query'])
            assert missing['run']==run and missing['status']=='partial' and missing['error']['code']=='INDEX_STALE'
        import uuid
        raw={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':uuid.uuid4().hex,'role':'ROLE_USER','parts':[{'data':{'op':'continue_retrieval','query_id':missing['id']}}]}}}
        status,value,_=Client(h).request('/a2a',raw,{'Authorization':'Bearer '+h.config['agents']['alice']})
        assert status==200 and value['error']['data'][0]['reason']=='RESOURCE_EXHAUSTED',value
        assert rpc({'op':'get_retrieval','query_id':missing['id'],'run':1})['query']['error']['code']=='INDEX_STALE'
        record('sixteen-durable-runs-retain-prior-errors-and-reject-unbounded-continuation')
        update({'max_records':10000});ready();assert h.pid==pid
        record('hot-primary-index-cap-reports-exclusions-without-certifying-missing-scope')
        # Ingestion remains durable while indexing is off; a one-row batch setting
        # makes observable build progress independent of any test-only hub hooks.
        update({'enabled':False})
        publications=[publish(('alpha λ beta '*1800)+str(i),'bulk') for i in range(36)]
        assert index()['status']=='disabled'
        update({'enabled':True,'max_index_bytes':1048576})
        failed=wait(lambda:(v if (v:=index())['error'] and v['error']['code']=='RESOURCE_LIMIT' else None))
        assert failed['active']['id']!=None and failed['active']['indexed']>=3
        for pub in publications:assert rpc({'op':'get_record','publication_id':pub['id']})['record']['publication']==pub
        new=publish('Publication accepted while derived index has no space.','after-failure')
        assert rpc({'op':'get_record','publication_id':new['id']})['record']['publication']['text']==new['text']
        record('derived-space-exhaustion-preserves-active-index-originals-and-live-ingestion')
        update({'max_index_bytes':33554432});recovered=ready();assert recovered['active']['indexed']==40 and recovered['active']['excluded']==0
        before=recovered['active']['id'];Client(h,h.config['admin_token']).api({'op':'rebuild_index'},mutation=True)
        building=wait(lambda:(v if (v:=index())['building'] and v['building']['build_processed']>0 and v['building']['build_processed']<v['building']['build_total'] else None))
        build_id=building['building']['id'];processed=building['building']['build_processed'];h.stop(hard=True);h.start()
        # Snapshot recovery retains the exact generation, not an invented fresh build.
        first=index();assert any(m and m['id']==build_id for m in [first['active'],first['building']]),(first,build_id)
        during=publish('A concurrent late Unicode correction.','during-rebuild');final=ready()
        assert final['active']['id']==build_id and final['active']['indexed']==41 and final['active']['watermark']==final['publication_watermark']
        assert final['previous']['id']==before and final['active']['build_processed']>=processed
        assert rpc({'op':'get_record','publication_id':during['id']})['record']['publication']['text']==during['text']
        record('real-hard-kill-resumes-same-committed-build-catches-up-and-switches-atomically')
        all_bulk=query({'information_type':'bulk'},question='alpha');assert all_bulk['status']=='completed' and all_bulk['coverage']['indexed']==36
        assert len(all_bulk['candidates'])==36 and len({v['publication_id'] for v in all_bulk['candidates']})==36
        record('recovered-derived-index-returns-all-eligible-originals-without-duplicates')
        report={'passed':True,'command':command,'image':args.image,'cases':cases}
        if command and Path(command[-1]).is_file():report['artifact_sha256']=hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
