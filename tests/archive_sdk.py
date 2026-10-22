#!/usr/bin/env python3
"""Official A2A archive workflow, exact sample strings and earlier-store upgrades."""
import argparse,asyncio,hashlib,json,tempfile
from pathlib import Path
import jsonschema
from hub_acceptance import Hub,domain_code,wait_deliveries
from archive_support import ArchiveFixture
from protocol_acceptance import ByteValidator

async def run(args):
    command=json.loads(args.command);parent=Path('_build/roadmap/archive-sdk').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=ArchiveFixture();cases=[]
    async def wait(agent,q):
        for _ in range(500):
            result=(await agent.call({'op':'get_archive_query','query_id':q['id']}))['query']
            if result['status']!='pending':return result
            await asyncio.sleep(.05)
        raise AssertionError('Archive SDK deadline')
    async def flow(h,producer,index):
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b');before=None
        try:
            sub=await b.call({'op':'subscribe','description':'SDK original archive evidence'})
            pub=await a.call({'op':'publish','text':'The Unicode SDK revision λ passed.'})
            delivery=await wait_deliveries(b,lambda xs:bool(xs));await b.call({'op':'ack','delivery_ids':[x['id'] for x in delivery]})
            second=await a.call({'op':'publish','text':'A second Unicode SDK revision passed.'})
            delivery=await wait_deliveries(b,lambda xs:bool(xs));await b.call({'op':'ack','delivery_ids':[x['id'] for x in delivery]})
            await a.call({'op':'send','recipient_id':'agent-b','text':'PRIVATE_SDK_ARCHIVE_SENTINEL'})
            if index==0:
                before=(await a.call({'op':'query_archive','question':'Which Unicode revision passed?','mode':'scan'}))['query'];before=await wait(a,before);assert before['status']=='completed'
        finally:await a.close();await b.close();h.stop()
        h.command=command
        if args.image:
            from container_acceptance import ContainerHub
            ContainerHub.image=args.image;h=ContainerHub.adopt(h)
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            original=(await a.call({'op':'get','publication_id':pub['publication']['id']}))['publication'];assert all(original.get(k)==v for k,v in pub['publication'].items())
            queued=(await b.call({'op':'poll'}))['deliveries'];assert len(queued)==1 and queued[0]['kind']=='message';await b.call({'op':'ack','delivery_ids':[queued[0]['id']]})
            if before:assert (await a.call({'op':'get_archive_query','query_id':before['id']}))['query']==before
            q=(await a.call({'op':'query_archive','question':'Which Unicode revision passed?','mode':'scan','budget':{'scan':{'records':1}}},'sdk-archive'))['query']
            assert (await a.call({'op':'query_archive','question':'Which Unicode revision passed?','mode':'scan','budget':{'scan':{'records':1}}},'sdk-archive'))['query']==q
            q=await wait(a,q);assert q['status']=='partial' and q['error']['code']=='BUDGET_RECORDS'
            denied=await h.raw('agent-b',{'op':'get_archive_query','query_id':q['id']});assert domain_code(denied)=='NOT_FOUND'
            plan=q['plan_id'];q=(await a.call({'op':'continue_archive_query','query_id':q['id'],'budget':{'scan':{'records':8}}},'sdk-archive-resume'))['query'];q=await wait(a,q)
            assert q['status']=='completed' and q['coverage']['full_scope_evaluated'] and q['plan_id']==plan
            assert set(q['answer']['support_ids'])=={pub['publication']['id'],second['publication']['id']}
            assert isinstance(q['sample']['probability_denominator'],str) and q['sample']['probability_denominator']==str(1<<256)
            prior=(await a.call({'op':'get_archive_query','query_id':q['id'],'run':1}))['query'];assert prior['status']=='partial'
            import httpx
            schema=httpx.get(h.base+'/protocol/schema').json();wire=(await h.raw('agent-a',{'op':'get_archive_query','query_id':q['id']})).json()['result']['message']['parts'][0]['data']['query'];assert wire==q
            ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/ArchiveQuery'},format_checker=jsonschema.FormatChecker()).validate(wire)
            assert 'PRIVATE_SDK_ARCHIVE_SENTINEL' not in json.dumps(q)
        finally:await a.close();await b.close();h.stop(hard=True)
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            assert (await a.call({'op':'get_archive_query','query_id':q['id']}))['query']==q
            assert (await b.call({'op':'poll'}))['deliveries']==[]
            assert (await b.call({'op':'list_subscriptions'}))['subscriptions'][0]['id']==sub['subscription']['id']
        finally:await a.close();await b.close();h.stop()
        cases.append({'case':'official-sdk-archive-and-actual-producer-'+str(index),'producer_sha256':hashlib.sha256(Path(producer[-1]).read_bytes()).hexdigest(),'passed':True});print('PASS',cases[-1]['case'],flush=True)
    try:
        for i,producer in enumerate([command]+[json.loads(x) for x in args.legacy_command]):await flow(Hub(producer,root/('hub-'+str(i)),model.url),producer,i)
    finally:model.close()
    Path(args.report).write_text(json.dumps({'schema':'adhd/archive-sdk@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'image':args.image,'cases':cases},indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--command',required=True);parser.add_argument('--image');parser.add_argument('--legacy-command',action='append',default=[]);parser.add_argument('--report',default='verification/archive-sdk.json');asyncio.run(run(parser.parse_args()))
if __name__=='__main__':main()
