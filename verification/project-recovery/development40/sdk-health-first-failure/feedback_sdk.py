#!/usr/bin/env python3
"""Official A2A feedback/replay calls and actual earlier-store producer upgrades."""
import argparse,asyncio,hashlib,json,tempfile
from pathlib import Path
import httpx,jsonschema
from hub_acceptance import Hub,domain_code,wait_deliveries
from archive_support import ArchiveFixture
from protocol_acceptance import ByteValidator


async def run(args):
    command=json.loads(args.command);parent=Path('_build/roadmap/feedback-sdk').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=ArchiveFixture();cases=[]
    async def wait(call,predicate=lambda q:q['status']!='pending'):
        for _ in range(600):
            value=await call()
            if predicate(value):return value
            await asyncio.sleep(.05)
        raise AssertionError('Feedback SDK deadline '+str(root))
    async def flow(h,producer,index):
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b');before=None
        try:
            sub=await b.call({'op':'subscribe','description':'SDK original evidence'})
            original=(await a.call({'op':'publish','text':'The sample SDK Unicode result λ passed.'}))['publication']
            delivery=await wait_deliveries(b,lambda xs:bool(xs));await b.call({'op':'ack','delivery_ids':[x['id'] for x in delivery]})
            await a.call({'op':'send','recipient_id':'agent-b','text':'PRIVATE_FEEDBACK_SDK_SENTINEL'})
            if 'agent_query_archive' in httpx.get(h.base+'/protocol/schema').json().get('$defs',{}):
                before=(await a.call({'op':'query_archive','question':'Which sample SDK result passed?','mode':'scan'}))['query']
                before=await wait(lambda:a.call({'op':'get_archive_query','query_id':before['id']}),lambda v:v['query']['status']!='pending');before=before['query']
        finally:await a.close();await b.close();h.stop()
        h.command=command
        if args.image:
            from container_acceptance import ContainerHub
            ContainerHub.image=args.image;h=ContainerHub.adopt(h)
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            actual=(await a.call({'op':'get','publication_id':original['id']}))['publication'];assert all(actual.get(k)==v for k,v in original.items())
            queued=(await b.call({'op':'poll'}))['deliveries'];assert len(queued)==1 and queued[0]['text']=='PRIVATE_FEEDBACK_SDK_SENTINEL';await b.call({'op':'ack','delivery_ids':[queued[0]['id']]})
            if before:
                assert (await a.call({'op':'get_archive_query','query_id':before['id']}))['query']==before
                captures=await wait(lambda:a.call({'op':'list_retrieval_attempts'}),lambda v:any(x['archive_query_id']==before['id'] for x in v['items']));assert any(x['recipe'] is None for x in captures['items'] if x['archive_query_id']==before['id'])
            q=(await a.call({'op':'query_archive','question':'Which sample SDK Unicode result was recorded?'}))['query'];q=(await wait(lambda:a.call({'op':'get_archive_query','query_id':q['id']}),lambda v:v['query']['status']!='pending'))['query'];assert q['status']=='completed'
            captured=await wait(lambda:a.call({'op':'list_retrieval_attempts'}),lambda v:any(x['archive_query_id']==q['id'] for x in v['items']));attempt=next(x for x in captured['items'] if x['archive_query_id']==q['id'])
            detail=(await a.call({'op':'get_retrieval_attempt','attempt_id':attempt['id']}))['attempt'];assert detail['labels']==[] and detail['adjudicated_diagnosis'] is None
            assert domain_code(await h.raw('agent-b',{'op':'get_retrieval_attempt','attempt_id':attempt['id']}))=='NOT_FOUND'
            cmd={'op':'replay_retrieval','attempt_id':attempt['id'],'candidate_recipe':{'context_depth':2},'budget':{'calls':1}}
            r=(await a.call(cmd,'sdk-paired-replay'))['query'];assert (await a.call(cmd,'sdk-paired-replay'))['query']==r
            r=(await wait(lambda:a.call({'op':'get_retrieval_replay','query_id':r['id']}),lambda v:v['query']['status']!='pending'))['query'];assert r['status']=='partial' and r['error']['code']=='BUDGET_CALLS'
            assert domain_code(await h.raw('agent-b',{'op':'get_retrieval_replay','query_id':r['id']}))=='NOT_FOUND'
            r=(await a.call({'op':'continue_retrieval_replay','query_id':r['id'],'budget':{'calls':16}},'sdk-replay-resume'))['query'];r=(await wait(lambda:a.call({'op':'get_retrieval_replay','query_id':r['id']}),lambda v:v['query']['status']!='pending'))['query'];assert r['status']=='completed' and r['run']==2 and r['comparison']['reason']=='unlabeled'
            assert (await a.call({'op':'get_retrieval_replay','query_id':r['id'],'run':1}))['query']['status']=='partial'
            schema=httpx.get(h.base+'/protocol/schema').json();wire=(await h.raw('agent-a',{'op':'get_retrieval_replay','query_id':r['id']})).json()['result']['message']['parts'][0]['data']['query'];assert wire==r
            ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/ReplayQuery'},format_checker=jsonschema.FormatChecker()).validate(wire)
            assert 'PRIVATE_FEEDBACK_SDK_SENTINEL' not in json.dumps(r)
            cancelled=(await a.call({'op':'replay_retrieval','attempt_id':attempt['id'],'candidate_recipe':{}},'sdk-cancel-create'))['query'];cancelled=(await a.call({'op':'cancel_retrieval_replay','query_id':cancelled['id']},'sdk-cancel-replay'))['query'];assert cancelled['status']=='cancelled'
        finally:await a.close();await b.close();h.stop(hard=True)
        h.start();a=await h.agent('agent-a');b=await h.agent('agent-b')
        try:
            assert (await a.call({'op':'get_retrieval_replay','query_id':r['id']}))['query']==r
            assert (await b.call({'op':'poll'}))['deliveries']==[]
            assert (await b.call({'op':'list_subscriptions'}))['subscriptions'][0]['id']==sub['subscription']['id']
        finally:await a.close();await b.close();h.stop()
        cases.append({'case':'official-sdk-feedback-and-actual-producer-'+str(index),'producer_sha256':hashlib.sha256(Path(producer[-1]).read_bytes()).hexdigest(),'passed':True});print('PASS',cases[-1]['case'],flush=True)
    try:
        for i,producer in enumerate([command]+[json.loads(x) for x in args.legacy_command]):await flow(Hub(producer,root/('hub-'+str(i)),model.url),producer,i)
    finally:model.close()
    Path(args.report).write_text(json.dumps({'schema':'adhd/feedback-sdk@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'image':args.image,'cases':cases},indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True);p.add_argument('--image');p.add_argument('--legacy-command',action='append',default=[]);p.add_argument('--report',default='verification/feedback-sdk.json');asyncio.run(run(p.parse_args()))
if __name__=='__main__':main()
