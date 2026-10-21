#!/usr/bin/env python3
"""Backend feature model configuration remains independent of event matching."""
import asyncio
from pathlib import Path
import time

from multi_support import Evidence, Fixture, arguments, poll_until, reject, scoped


async def main(args):
    if not args.with_model or args.rest_url:
        raise ValueError('Use a disposable --hub and --with-model controlled HTTP fixture')
    f=Fixture(args)
    f.config['matcher']=None
    feature={'url':f.model.url,'model':'configured-backend-fixture','timeout_ms':400}
    for name in ('history','retrieval','archive'):
        f.config[name]=feature.copy()
    evidence=Evidence(args.report,'adhd/independent-backend-models@1')
    import hashlib
    evidence.value.update(artifact_sha256=hashlib.sha256(args.hub.read_bytes()).hexdigest(),
                          harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        await f.start()
        a,b=await f.agent('red-a'),await f.agent('red-b')
        admin=f.admin()
        await b.call(scoped('project-red','subscribe',mode='raw'))
        pub=(await a.call(scoped('project-red','publish',text='Explicit backend model supports archive evidence')))['publication']
        await poll_until(b,'project-red',{pub['id']},args.deadline)
        reject(await f.raw('red-b',scoped('project-red','subscribe',mode='filtered',filter='API changes')),code='MODEL_UNAVAILABLE')
        evidence.record('raw-kafka-works-and-filtered-mode-rejects-missing-matcher-with-backend-models-configured')
        for op in ('query_history','retrieve','query_archive'):
            before=f.model.calls
            result=await a.call(scoped('project-red',op,question='Which backend evidence was reported?'))
            assert 'query' in result
            end=time.monotonic()+args.deadline
            while f.model.calls<=before and time.monotonic()<end:
                await asyncio.sleep(.05)
            assert f.model.calls>before,'Configured owning model endpoint must observe an actual query attempt'
        evidence.record('history-retrieval-and-archive-use-own-effective-model-without-subscription-matcher',actual_provider_attempts_observed=True)
        admin.call({'op':'config_update','patch':{'history':{'url':None,'model':None}}},mutation=True)
        reject(await f.raw('red-a',scoped('project-red','query_history',question='Unavailable history')),code='MODEL_UNAVAILABLE')
        assert 'query' in await a.call(scoped('project-red','retrieve',question='Independent retrieval'))
        assert 'query' in await a.call(scoped('project-red','query_archive',question='Independent archive'))
        evidence.record('removing-history-endpoint-does-not-disable-explicit-retrieval-or-archive')
        replay=scoped('project-red','replay_retrieval',attempt_id='nonexistent-attempt',candidate_recipe={})
        # With both owning feature models available, lookup reaches its normal
        # NOT_FOUND result. This does not claim a fabricated replay was run.
        reject(await f.raw('red-a',replay),code='NOT_FOUND')
        admin.call({'op':'config_update','patch':{'retrieval':{'url':None,'model':None}}},mutation=True)
        reject(await f.raw('red-a',replay),code='MODEL_UNAVAILABLE')
        admin.call({'op':'config_update','patch':{'retrieval':feature,'archive':{'url':None,'model':None}}},mutation=True)
        reject(await f.raw('red-a',replay),code='MODEL_UNAVAILABLE')
        admin.call({'op':'config_update','patch':{'history':feature}},mutation=True)
        assert 'query' in await a.call(scoped('project-red','query_archive',question='Inherited explicit history endpoint'))
        reject(await f.raw('red-a',replay),code='NOT_FOUND')
        evidence.record('replay-checks-both-retrieval-and-effective-archive-and-archive-inherits-history-independently')
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()


if __name__=='__main__':
    asyncio.run(main(arguments(__doc__).parse_args()))
