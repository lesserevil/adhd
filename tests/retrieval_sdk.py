#!/usr/bin/env python3
"""Official A2A retrieval workflow and actual earlier-store/template upgrades."""
import argparse,asyncio,hashlib,json,tempfile,time
from pathlib import Path
import jsonschema
from hub_acceptance import Hub,domain_code,wait_deliveries
from retrieval_support import NoulFixture
from protocol_acceptance import ByteValidator

async def run(args):
    command=json.loads(args.command);parent=Path('_build/roadmap/retrieval-sdk').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=NoulFixture();cases=[]
    async def wait(agent,q):
        for _ in range(200):
            result=(await agent.call({'op':'get_retrieval','query_id':q['id']}))['query']
            if result['status']!='pending':return result
            await asyncio.sleep(.05)
        raise AssertionError('Retrieval SDK deadline')
    async def flow(h,producer,index):
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            sub=await b.call({'op':'subscribe','description':'Original SDK evidence'})
            pub=await a.call({'op':'publish','text':'The archive records approval of revision SDK-'+str(index)+'.'},'sdk-original')
            delivery=(await wait_deliveries(b,lambda xs:any(x['publication_id']==pub['publication']['id'] for x in xs)))[0]
            await b.call({'op':'ack','delivery_ids':[delivery['id']]},'sdk-ack')
            second=await a.call({'op':'publish','text':'A second independent original records completion of SDK-'+str(index)+'.'},'sdk-second-original')
            deliveries=await wait_deliveries(b,lambda xs:any(x['publication_id']==second['publication']['id'] for x in xs))
            await b.call({'op':'ack','delivery_ids':[x['id'] for x in deliveries]})
            private=await a.call({'op':'send','recipient_id':'agent-b','text':'PRIVATE_SDK_RETRIEVAL_SENTINEL'})
        finally:await a.close();await b.close();h.stop()
        h.command=command
        if args.image:
            from container_acceptance import ContainerHub
            ContainerHub.image=args.image;h=ContainerHub.adopt(h)
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            original=(await a.call({'op':'get','publication_id':pub['publication']['id']}))['publication'];assert all(original.get(k)==v for k,v in pub['publication'].items()),(original,pub['publication'])
            queued=(await b.call({'op':'poll'}))['deliveries'];assert len(queued)==1 and queued[0]['kind']=='message'
            await b.call({'op':'ack','delivery_ids':[queued[0]['id']]})
            for _ in range(300):
                index_status=(await a.call({'op':'retrieval_index'}))['index']
                if index_status['status']=='ready':break
                await asyncio.sleep(.05)
            assert index_status['status']=='ready'
            q=(await a.call({'op':'retrieve','question':'Which revision was approved?','budget':{'calls':1}},'sdk-retrieval'))['query']
            assert (await a.call({'op':'retrieve','question':'Which revision was approved?','budget':{'calls':1}},'sdk-retrieval'))['query']==q
            q=await wait(a,q);assert q['status']=='partial' and q['error']['code']=='BUDGET_CALLS'
            denied=await h.raw('agent-b',{'op':'get_retrieval','query_id':q['id']});assert domain_code(denied)=='NOT_FOUND'
            q=(await a.call({'op':'continue_retrieval','query_id':q['id'],'budget':{'calls':4}},'sdk-continue'))['query'];q=await wait(a,q)
            assert q['status']=='completed' and q['coverage']['semantic_examined']==2 and {c['publication_id'] for c in q['candidates']}=={pub['publication']['id'],second['publication']['id']}
            import httpx
            schema=httpx.get(h.base+'/protocol/schema').json()
            # Protobuf Struct normalizes JSON numbers to doubles; validate actual wire tokens.
            wire=(await h.raw('agent-a',{'op':'get_retrieval','query_id':q['id']})).json()['result']['message']['parts'][0]['data']['query']
            assert wire==q
            ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/RetrievalQuery'},format_checker=jsonschema.FormatChecker()).validate(wire)
            assert 'PRIVATE_SDK_RETRIEVAL_SENTINEL' not in json.dumps(q)
            prior=(await a.call({'op':'get_retrieval','query_id':q['id'],'run':1}))['query'];assert prior['status']=='partial'
            cancelled=(await a.call({'op':'cancel_retrieval','query_id':q['id']}))['query'];assert cancelled['status']=='completed'
        finally:await a.close();await b.close();h.stop(hard=True)
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            assert (await a.call({'op':'get_retrieval','query_id':q['id']}))['query']==q
            assert (await b.call({'op':'poll'}))['deliveries']==[]
            assert (await b.call({'op':'list_subscriptions'}))['subscriptions'][0]['id']==sub['subscription']['id']
        finally:await a.close();await b.close();h.stop()
        cases.append({'case':'official-sdk-and-actual-store-producer-'+str(index),'producer_sha256':hashlib.sha256(Path(producer[-1]).read_bytes()).hexdigest(),'passed':True});print('PASS',cases[-1]['case'],flush=True)
    try:
        for i,producer in enumerate([command]+[json.loads(x) for x in args.legacy_command]):
            await flow(Hub(producer,root/('hub-'+str(i)),model.url),producer,i)
    finally:model.close()
    Path(args.report).write_text(json.dumps({'schema':'adhd/retrieval-sdk@1','passed':True,'image':args.image,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'cases':cases},indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True);p.add_argument('--image');p.add_argument('--legacy-command',action='append',default=[]);p.add_argument('--report',default='verification/retrieval-sdk.json');asyncio.run(run(p.parse_args()))
if __name__=='__main__':main()
