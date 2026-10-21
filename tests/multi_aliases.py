#!/usr/bin/env python3
"""Migrate historical aliases authored by a real previous single-project runtime."""
import asyncio
import copy
import hashlib
import json
import secrets
from pathlib import Path
from uuid import uuid4

from multi_support import Admin, Evidence, Fixture, arguments, reject, scoped
from foundation_acceptance import Client


OLD, CURRENT, OTHER='historical-project','project-red','project-blue'


async def main(args):
    if not args.hub or not args.with_model:
        raise ValueError('Requires owned --hub, --legacy-hub and --with-model')
    previous=copy.copy(args)
    previous.hub=args.legacy_hub
    f=Fixture(previous)
    f.config['project_id']=OLD
    legacy_token=secrets.token_urlsafe(32)
    f.config['admin_token']=legacy_token
    for key in ('projects','agent_projects','eventing'):
        f.config.pop(key)
    evidence=Evidence(args.report,'adhd/historical-project-aliases@1')
    evidence.value.update(artifact_sha256=hashlib.sha256(args.hub.read_bytes()).hexdigest(),
        legacy_artifact_sha256=hashlib.sha256(args.legacy_hub.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        await f.start()
        a=await f.agent('red-a')
        command=scoped(OLD,'publish',text='Original preceding a real project rename')
        mid=uuid4().hex
        original=await a.call(command,mid)
        admin=Admin(Client(f,legacy_token),f)
        admin.call({'op':'config_update','patch':{'project_id':CURRENT}},mutation=True)
        assert admin.call({'op':'config_get'})['config']['project_id']==CURRENT
        f.hard_stop()
        evidence.record('previous-qualified-runtime-created-original-and-real-project-rename')
        f.args=args
        await f.start()
        admin=Admin(Client(f,legacy_token),f)
        config=admin.call({'op':'config_get'})['config']
        projects=config['projects']+[{'id':OTHER,'name':'Other project','status':'active','description':'','settings':{}}]
        grants={**config['agent_projects'],'red-a':[CURRENT],'blue-a':[OTHER],'bridge':[CURRENT,OTHER]}
        admin.call({'op':'config_update','patch':{'projects':projects,'agent_projects':grants}},mutation=True)
        assert await a.call(command,mid)==original
        assert (await a.call(scoped(OLD,'whoami')))['project_id']==CURRENT
        assert (await a.call(scoped(OLD,'get',publication_id=original['publication']['id'])))['publication']['project_id']==CURRENT
        alias_command=scoped(OLD,'publish',text='New publication addressed through admitted historical alias')
        alias_mid=uuid4().hex
        newer=await a.call(alias_command,alias_mid)
        assert newer['publication']['project_id']==CURRENT
        assert await a.call(alias_command,alias_mid)==newer
        evidence.record('admitted-alias-resolves-canonical-project-and-original-command-retry-result-stays-verbatim')
        for requested in (OLD,'unknown-project',CURRENT):
            reject(await f.raw('blue-a',scoped(requested,'whoami')),code='PROJECT_NOT_FOUND')
        bridge=await f.agent('bridge')
        assert (await bridge.call(scoped(OLD,'whoami')))['project_id']==CURRENT
        evidence.record('aliases-do-not-grant-admission-and-multi-project-agent-resolves-unambiguous-canonical-project')
        before=admin.call({'op':'config_get'})['config']
        collision=before['projects']+[{'id':OLD,'name':'Must not redefine alias','settings':{}}]
        admin.call({'op':'config_validate','patch':{'projects':collision},'expected_revision':before['config_revision']},expected=409)
        admin.call({'op':'config_update','patch':{'projects':collision}},mutation=True,expected=409)
        assert admin.call({'op':'config_get'})['config']==before
        evidence.record('dry-validation-and-update-reject-historical-alias-as-new-project-without-mutation')
        f.hard_stop()
        await f.start()
        assert await a.call(command,mid)==original
        assert await a.call(alias_command,alias_mid)==newer
        evidence.record('alias-resolution-and-both-retry-identities-survive-hard-restart')
        f.hard_stop()
        valid=f.file.read_bytes()
        damaged=json.loads(valid)
        damaged['projects']=collision
        f.file.write_text(json.dumps(damaged))
        try:
            try:
                await f.start()
            except AssertionError:
                assert f.process.poll() is not None,'A timeout is not startup refusal'
            else:
                raise AssertionError('Conflicting historical alias became publicly ready')
        finally:
            if f.process and f.process.poll() is None:
                f.hard_stop()
            f.file.write_bytes(valid)
        evidence.record('cold-start-with-redefined-historical-alias-fails-before-public-readiness')
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        f.args=args
        await f.close()


if __name__=='__main__':
    parser=arguments(__doc__)
    parser.add_argument('--legacy-hub',type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
