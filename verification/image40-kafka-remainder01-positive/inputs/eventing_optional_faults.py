#!/usr/bin/env python3
"""Run only the two existing deterministic optional filter fault checks.

Reuses eventing_acceptance.filtered_faults unchanged. The real Kafka service
remains healthy; no broker stop, provider endpoint, or historical raw check is
repeated. --with-model selects the in-process deterministic ModelFixture.
"""
import asyncio
from eventing_acceptance import P, filtered_faults
from multi_support import arguments, execute, scoped


async def checks(f, evidence):
    assert f.args.with_model and f.model is not None
    assert not f.args.rest_url, 'Own controlled local model fixture required'
    publisher, subscriber, raw = [await f.agent(name) for name in ('red-a', 'red-b', 'bridge')]
    await raw.call(scoped(P, 'subscribe', mode='raw'))
    await filtered_faults(f, evidence, publisher, subscriber, raw)
    assert f.model.calls > 0 and f.model.requests
    evidence.value['controlled_model_only'] = True
    evidence.value['assertion_source'] = 'eventing_acceptance.filtered_faults + subscription_revisions unchanged'


if __name__ == '__main__':
    args = arguments(__doc__).parse_args()
    assert args.with_model
    asyncio.run(execute(args, 'adhd/eventing-optional-faults@1', checks))
