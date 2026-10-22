"""Independent public standalone-ID coverage for the recovery lifecycle fixture.

No runtime allocator is imported. Every observed public family is checked even
if it accidentally returns a legacy format. Deterministic lineage is verified
through its actual namespaced parent references, not blanket format exemptions.
SourceQuery/FederatedQuery families require separate federation fixtures.
"""
from __future__ import annotations
import asyncio
import re
import time
from uuid import uuid4
from multi_support import scoped

FORMAT=re.compile(r'[a-z][a-z0-9]{0,15}_([0-9a-f]{32})_([1-9a-z][0-9a-z]*)\Z')


def require(value, epoch):
    assert isinstance(value,str)
    match=FORMAT.fullmatch(value)
    assert match is not None, 'A newly allocated public object returned a legacy/invalid identity'
    assert match.group(1)==epoch, 'A newly allocated public object used another allocation namespace'
    assert 0<int(match.group(2),36)<=9007199254740991


async def rebuild(f, project):
    admin=f.admin()
    before=admin.call(scoped(project,'retrieval_index'))['index']
    old=before['active']['id'] if before['active'] else None
    receipt=admin.call(scoped(project,'rebuild_index'),mutation=True)
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        value=admin.call(scoped(project,'retrieval_index'))['index']
        if value['status']=='ready' and value['active'] and value['active']['id']!=old:
            return {'receipt':receipt,'index':value}
        await asyncio.sleep(.05)
    raise AssertionError('Public index rebuild did not activate a fresh generation within the lifecycle bound')


def public_families(f, project):
    families={}
    def add(kind,identifier):
        assert isinstance(identifier,str)
        families.setdefault(kind,set()).add(identifier)
    queries={}
    for kind in ('history','retrieval','archive','replay','optimization'):
        page=f.admin().call(scoped(project,'query_jobs',kind=kind,limit=100))
        assert type(page['truncated']) is bool
        rows=page['items']
        if page['truncated']:
            # The public response also has a byte bound. Partition by every
            # configured fixture author rather than treating <100 rows as a
            # complete listing. These are the actual principals that the
            # fixture uses; discovery does not read private job dictionaries.
            observed={row['query']['id'] for row in rows}
            complete={}
            for owner in sorted(f.tokens):
                owned=f.admin().call(scoped(project,'query_jobs',kind=kind,agent_id=owner,limit=100))
                assert owned['truncated'] is False, 'Even an owner-filtered public allocator page was truncated'
                for row in owned['items']:
                    identifier=row['query']['id']
                    assert identifier not in complete, 'A query appeared under two fixture owners'
                    complete[identifier]=row
            assert observed<=complete.keys(), 'An observed query has no known fixture-author partition'
            rows=list(complete.values())
        assert rows, 'Public allocator scan was empty; no silent coverage claim'
        for row in rows:
            assert row['kind']==kind
            q=row['query'];add(kind,q['id']);queries[q['id']]=q
            if kind=='archive': add('archive-plan',q['plan_id'])
    # Internal paired jobs retain their real owned identities. Their child IDs
    # must also occur in the complete public Admin listing, not disappear from it.
    for q in queries.values():
        children=q.get('children')
        if isinstance(children,dict):
            for identifier in children.values():
                if isinstance(identifier,str):
                    assert identifier in queries, 'An actual child job was absent from the complete public family scan'
    for key in ('active','previous','building'):
        value=f.admin().call(scoped(project,'retrieval_index'))['index'][key]
        if value is not None:add('index-generation',value['id'])
    return {kind:sorted(values) for kind,values in families.items()}


def verify_new(phase,lost,retained_ids,epoch):
    explicit={
        'publication':[phase['record']['publication']['id']],
        'subscription':[phase['subscription']['id'],phase['eventing']['subscription']['id']],
        'delivery':[phase['acknowledged_delivery']['id'],phase['private_delivery']['id']],
        'event-replay-delivery':[row['id'] for row in phase['eventing']['acknowledged_deliveries']],
        'history':[phase['queries']['query_history']['id']],
        'retrieval':[phase['queries']['retrieve']['id']],
        'archive':[phase['queries']['query_archive']['id']],
        'archive-plan':[phase['queries']['query_archive']['plan_id']],
        'replay':[phase['replay']['id']],
        'proposal':[phase['optimizer']['proposal']['id']],
        'proposal-child-replay':[v['replay_id'] for v in phase['optimizer']['proposal']['children']],
        'event-replay':[phase['eventing']['replay']['replay']['id']],
        'event-audit':[phase['eventing']['repair_retry']['audit_id'],phase['eventing']['repair_reconcile']['audit_id']],
        'index-rebuild':[phase['index_rebuild']['index']['active']['id']]}
    for case in phase['optimizer']['captured']:
        explicit['publication'].extend(case[key]['id'] for key in ('root','middle','leaf'))
    for kind,values in phase['public_ids'].items():
        explicit.setdefault('public-'+kind,[]).extend(v for v in values if v not in retained_ids)
    for kind,values in explicit.items():
        assert values, 'Explicit allocated family was never observed: '+kind
        for identifier in values:require(identifier,epoch)
    attempt=phase['attempt'];archive=phase['queries']['query_archive']
    assert attempt['archive_query_id']==archive['id'] and attempt['plan_id']==archive['plan_id'] and attempt['run']==archive['run']
    assert attempt['id']!=lost['attempt']['id'], 'Derived attempt reused a lost identity despite a different namespaced Archive parent'
    assert phase['replay']['attempt_id']==attempt['id']
    assert attempt['labels'][-1]['evidence_identity']==attempt['evidence_identity']
    assert attempt['labels'][-1]['identity']!=lost['attempt']['labels'][-1]['identity']
    return {kind:len(set(values)) for kind,values in explicit.items()}
