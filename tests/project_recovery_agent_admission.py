#!/usr/bin/env python3
"""Developer creation distinguishes unknown projects from lost identity evidence."""
import asyncio
import copy
import os
from pathlib import Path
import secrets
from uuid import uuid4

from foundation_acceptance import Client
from multi_support import Admin, Evidence, Fixture, arguments, scoped
from project_recovery_acceptance import Recovery, RED, BLUE, HIDDEN
from project_recovery_state import digest, registry, route
from protocol_acceptance import ByteValidator


async def checks(f, r, evidence):
    await r.initialize(RED)
    password=secrets.token_urlsafe(32)
    user=f.admin().call({'op':'save_user','user':{'username':'recovery-developer','name':'Recovery developer',
        'email':'recovery-developer@example.invalid','role':'Developer','password':password,'project_ids':[RED]}},mutation=True)['user']
    def developer():
        client=Client(f);client.login('recovery-developer',password)
        return Admin(client,f,f.admin().client)
    before=copy.deepcopy(registry(f.file))
    unknown=[]
    for project in (BLUE,HIDDEN):
        assert r.status(project)['availability']=='uninitialized'
        entry,path=route(f.file,project)
        assert entry['initialized'] is False
        assert not path.exists() and not Path(str(path)+'.snapshot').exists()
        unknown.append((project,path))
    token=secrets.token_urlsafe(32)
    created=developer().call({'op':'create_agent','agent_id':'fresh-with-unknown-projects','token':token,'project_ids':[RED]},mutation=True)
    assert created['owner_user_id']==user['id']
    f.tokens['fresh-with-unknown-projects']=token
    assert (await (await f.agent('fresh-with-unknown-projects')).call(scoped(RED,'whoami')))['agent_id']=='fresh-with-unknown-projects'
    for project,path in unknown:
        assert registry(f.file)['projects'][project]==before['projects'][project]
        assert not path.exists() and not Path(str(path)+'.snapshot').exists()
    evidence.record('developer-can-create-fresh-agent-with-explicitly-uninitialized-unadmitted-projects-without-opening-them')
    await r.initialize(BLUE)
    original_actor=await f.agent('blue-a')
    retained=(await original_actor.call(scoped(BLUE,'send',recipient_id='blue-b',text='Private identity evidence in another project')))['delivery']
    entry,checkpoint=route(f.file,BLUE)
    paths=(checkpoint,Path(str(checkpoint)+'.snapshot'))
    f.hard_stop()
    exact_bytes={p:p.read_bytes() for p in paths}
    held=f.root/'held-known-project';held.mkdir(mode=0o700)
    for p in paths: os.replace(p,held/p.name)
    try:
        await f.start()
        assert r.status(BLUE)['availability']=='recovery_required'
        assert r.status(RED)['availability']=='ready'
        dev=developer();config=copy.deepcopy(f.admin().call({'op':'config_get'}))
        revision=r.revision();new_token=secrets.token_urlsafe(32)
        command={'op':'create_agent','agent_id':'fresh-with-lost-evidence','token':new_token,'project_ids':[RED],
            'expected_revision':revision,'confirm':True,'message_id':uuid4().hex}
        status,result,_=dev.client.request('/admin/api',command)
        schema=Client(f).get('/protocol/schema')[1]
        ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/Error'}).validate(result)
        responses=Client(f).get('/protocol/openapi')[1]['paths']['/admin/api']['post']['responses']
        assert 400<=status<600 and str(status) in responses
        assert f.admin().call({'op':'config_get'})==config
        f.tokens[command['agent_id']]=new_token
        assert (await f.raw(command['agent_id'],scoped(RED,'whoami'))).status_code==401
        assert not any(p.exists() for p in paths)
        evidence.record('known-initialized-missing-foreign-project-fails-developer-identity-creation-closed',
            http_status=status,error_code=result['error']['code'],configuration_unchanged=True,new_token_denied=True)
        f.hard_stop()
        for p in paths:
            os.replace(held/p.name,p);assert p.read_bytes()==exact_bytes[p]
        await f.start()
        restored=developer().client.api(command)
        assert restored['owner_user_id']==user['id']
        assert (await (await f.agent(command['agent_id'])).call(scoped(RED,'whoami')))['agent_id']==command['agent_id']
        assert (await (await f.agent('blue-b')).call(scoped(BLUE,'poll')))['deliveries']==[retained]
        evidence.record('exact-evidence-restoration-allows-same-unaccepted-command-and-preserves-foreign-private-delivery')
    finally:
        if any((held/p.name).exists() for p in paths):
            if f.process and f.process.poll() is None: f.hard_stop()
            for p in paths:
                if (held/p.name).exists():
                    assert not p.exists();os.replace(held/p.name,p)
                    assert p.read_bytes()==exact_bytes[p]


async def main(args):
    assert not args.rest_url and not args.with_model
    f=Fixture(args,initialize_projects=False)
    evidence=Evidence(args.report,'recovery-developer-agent-admission')
    evidence.value['harness_sha256']=digest(Path(__file__).read_bytes())
    if args.hub:evidence.value['artifact_sha256']=digest(args.hub.read_bytes())
    try:
        await f.start();await checks(f,Recovery(f,args.recovery_schema),evidence)
    except BaseException as error:evidence.finish(error);raise
    else:evidence.finish()
    finally:
        try:await f.close()
        finally:f.bind_evidence(evidence);evidence.write()


if __name__=='__main__':
    parser=arguments(__doc__);parser.add_argument('--recovery-schema',type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
