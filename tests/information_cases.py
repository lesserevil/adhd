"""Independent information-archive scenarios shared by host and container tests."""
import asyncio
import shutil
from uuid import uuid4

import hub_acceptance as acceptance


async def information_checks(command, root, record):
    fixture = acceptance.ModelFixture()
    hub = acceptance.Hub(command, root / 'information', fixture.url)
    a = b = None
    try:
        hub.start()
        a, b = await hub.agent('agent-a'), await hub.agent('agent-b')
        old = (await a.call({'op': 'publish', 'text': 'earlier archive message'}))['publication']
        assert old['information_type'] == 'message'
        assert old['source'] == {'kind': 'agent', 'id': 'agent-a'}
        assert old['occurred_at'] == old['created_at']
        assert (await b.call({'op': 'get', 'publication_id': old['id']}))['publication'] == old
        assert (await b.call({'op': 'search', 'query': 'earlier archive'}))['publications'] == [old]
        assert not (await b.call({'op': 'list_subscriptions'}))['subscriptions']
        record('archive-default-envelope-and-retrieval-without-subscription')

        status = {'op': 'publish', 'information_type': 'status', 'text': 'decoder integration blocked',
                  'data': {'state': 'blocked', 'dependencies': ['schema'], 'progress': 17},
                  'source': {'kind': 'agent', 'id': 'agent-a', 'item_id': 'task-17-status-1'},
                  'occurred_at': '2026-10-18T09:00:00-05:00'}
        first_result = await a.call(status)
        first = first_result['publication']
        assert first['author_id'] == 'agent-a' and first['information_type'] == 'status'
        assert first['occurred_at'] == '2026-10-18T14:00:00Z'
        second = (await a.call({'op': 'publish', 'information_type': 'status',
            'text': 'decoder integration ready', 'data': {'state': 'ready'},
            'occurred_at': '2025-01-01T00:00:00Z'}))['publication']
        history = (await b.call({'op': 'search', 'information_type': 'status',
            'source_kind': 'agent', 'source_id': 'agent-a'}))['publications']
        assert [p['id'] for p in history] == [second['id'], first['id']]
        assert (await b.call({'op': 'search', 'query': 'BLOCKED', 'information_type': 'status'}))['publications'] == [first]
        assert not (await b.call({'op': 'search', 'information_type': 'status', 'source_kind': 'email'}))['publications']
        assert first in (await b.call({'op': 'search', 'query': 'task-17-status-1'}))['publications']
        record('status-history-source-type-filters-and-ingestion-order')

        for value in [None, False, 42, 'a scalar message', [1, {'nested': [True, None, 2.5]}]]:
            pub = (await a.call({'op': 'publish', 'information_type': 'artifact', 'data': value}))['publication']
            assert pub['data'] == value
            assert (await b.call({'op': 'get', 'publication_id': pub['id']}))['publication']['data'] == value
        record('archive-arbitrary-json-values')

        for invalid in [
            {'op': 'publish', 'text': 'x', 'source': []},
            {'op': 'publish', 'text': 'x', 'source': {'kind': 'email', 'id': 'inbox', 'extra': 'x'}},
            {'op': 'publish', 'text': 'x', 'source': {'kind': 'email', 'id': 'inbox', 'uri': 'file:///secret'}},
            {'op': 'publish', 'text': 'x', 'information_type': ''},
            {'op': 'publish', 'text': 'x', 'occurred_at': '2026-10-18T09:00:00'},
            {'op': 'publish', 'text': 'x', 'created_at': '2026-10-18T09:00:00Z'},
            {'op': 'publish', 'text': 'x', 'source': {'kind': 'email', 'id': 'x', 'item_id': 'x' * 513}},
            {'op': 'search'}, {'op': 'search', 'query': '', 'information_type': 'message'},
            {'op': 'get', 'publication_id': ''},
        ]:
            response = await hub.raw('agent-a', invalid)
            assert response.json()['error']['code'] == -32602, response.text
        response = await hub.raw('agent-a', {'op': 'publish', 'text': 'spoofed agent',
            'source': {'kind': 'agent', 'id': 'agent-b'}})
        assert acceptance.domain_code(response) == 'FORBIDDEN'
        direct = (await a.call({'op': 'send', 'recipient_id': 'agent-b', 'text': 'private archive secret'}))['delivery']
        for agent in ['agent-a', 'agent-b']:
            assert acceptance.domain_code(await hub.raw(agent, {'op': 'get', 'publication_id': direct['id']})) == 'NOT_FOUND'
        assert not (await b.call({'op': 'search', 'query': 'private archive secret'}))['publications']
        await b.call({'op': 'ack', 'delivery_ids': [direct['id']]})
        record('archive-schema-validation-and-private-message-isolation')

        await b.call({'op': 'subscribe', 'description': 'Status changes and external messages affecting decoder integration'})
        publication_command = {'op': 'publish', 'information_type': 'status',
            'text': 'decoder integration requires the new status field', 'data': ['queued', {'task': 17}],
            'source': {'kind': 'agent', 'id': 'agent-a', 'item_id': 'status-semantic-1'}}
        publication_result = await a.call(publication_command)
        publication = publication_result['publication']
        deliveries = await acceptance.wait_deliveries(b, lambda ds: any(d.get('publication_id') == publication['id'] for d in ds))
        delivery = next(d for d in deliveries if d.get('publication_id') == publication['id'])
        for field in ['information_type', 'source', 'occurred_at', 'data']:
            assert delivery[field] == publication[field]
        request = next(r for r in fixture.requests if r['state']['publication']['id'] == publication['id'])
        assert request['state']['publication'] == publication
        await b.call({'op': 'ack', 'delivery_ids': [delivery['id']]})
        assert (await b.call({'op': 'get', 'publication_id': publication['id']}))['publication'] == publication
        retry = dict(reversed(list(publication_command.items())))
        retry['project_id'] = hub.config['project_id']
        assert await a.call(retry) == publication_result
        response = await hub.raw('agent-a', {**publication_command, 'text': 'changed content'})
        assert acceptance.domain_code(response) == 'SOURCE_CONFLICT'
        assert await a.call(dict(reversed(list(status.items())))) == first_result
        await asyncio.sleep(.25)
        assert not (await b.call({'op': 'poll'}))['deliveries']
        record('metadata-matching-delivery-retention-and-source-item-deduplication')

        external_command = {'op': 'publish', 'text': 'external decoder rollout decision',
            'information_type': 'message', 'data': {'thread': '17', 'labels': ['release']},
            'source': {'kind': 'slack', 'id': 'workspace/channel', 'item_id': 'source-event-17',
                       'uri': 'https://example.invalid/messages/17'},
            'occurred_at': '2026-10-18T14:30:00Z'}
        external_result = await a.call(external_command)
        external = external_result['publication']
        assert external['author_id'] == 'agent-a' and external['source'] == external_command['source']
        ds = await acceptance.wait_deliveries(b, lambda ds: any(d.get('publication_id') == external['id'] for d in ds))
        assert any(d['source']['kind'] == 'slack' for d in ds)
        assert (await b.call({'op': 'search', 'source_kind': 'slack', 'source_id': 'workspace/channel'}))['publications'] == [external]
        record('synthetic-external-information-uses-shared-storage-search-and-subscriptions')

        hub.stop(hard=True)
        hub.start()
        assert await a.call(publication_command) == publication_result
        assert await a.call(external_command) == external_result
        assert (await b.call({'op': 'get', 'publication_id': first['id']}))['publication'] == first
        assert (await b.call({'op': 'search', 'information_type': 'status'}))['publications']
        remaining = (await b.call({'op': 'poll'}))['deliveries']
        assert not any(d['id'] == delivery['id'] for d in remaining)
        assert len([d for d in remaining if d.get('publication_id') == external['id']]) == 1
        record('archive-and-source-dedup-survive-hard-restart-and-acknowledgement')
    finally:
        if a:
            await a.close()
        if b:
            await b.close()
        hub.stop()
        fixture.close()


async def legacy_upgrade_checks(old_command, new_command, root, record):
    fixture = acceptance.ModelFixture()
    hub = acceptance.Hub(old_command, root / 'legacy-upgrade', fixture.url)
    a = b = None
    try:
        hub.start()
        a, b = await hub.agent('agent-a'), await hub.agent('agent-b')
        await b.call({'op': 'subscribe', 'description': 'Legacy schema updates'})
        original_command = {'op': 'publish', 'text': 'legacy accepted publication', 'data': {'revision': 1}}
        key = str(uuid4())
        original = await a.call(original_command, key)
        pub = original['publication']
        ds = await acceptance.wait_deliveries(b, lambda ds: any(d.get('publication_id') == pub['id'] for d in ds))
        delivery = next(d for d in ds if d.get('publication_id') == pub['id'])
        await b.call({'op': 'ack', 'delivery_ids': [delivery['id']]})
        direct = (await a.call({'op': 'send', 'recipient_id': 'agent-b', 'text': 'legacy private pending message'}))['delivery']
        fixture.mode = 'error'
        pending = (await a.call({'op': 'publish', 'text': 'legacy pending inference'}))['publication']
        hub.stop()
        shutil.copy2(hub.root / 'hub.dets', hub.root / 'pre-upgrade.dets')
        hub.command = new_command
        hub.start()
        assert await a.call(original_command, key) == original
        upgraded = (await b.call({'op': 'get', 'publication_id': pub['id']}))['publication']
        assert upgraded['id'] == pub['id'] and upgraded['information_type'] == 'message'
        assert upgraded['source'] == {'kind': 'agent', 'id': 'agent-a'}
        assert upgraded['occurred_at'] == pub['created_at']
        current = (await b.call({'op': 'poll'}))['deliveries']
        assert direct in current and not any(d['id'] == delivery['id'] for d in current)
        assert (await b.call({'op': 'list_subscriptions'}))['subscriptions']
        fixture.mode = 'match'
        await acceptance.wait_deliveries(b, lambda ds: any(d.get('publication_id') == pending['id'] for d in ds))
        await a.call({'op': 'publish', 'information_type': 'status', 'data': ['post-upgrade']})
        hub.stop(hard=True)
        hub.start()
        assert await a.call(original_command, key) == original
        assert (await b.call({'op': 'search', 'information_type': 'status'}))['publications']
        record('real-schema-one-upgrade-preserves-history-inboxes-acks-pending-jobs-and-idempotency')
    finally:
        if a:
            await a.close()
        if b:
            await b.close()
        hub.stop()
        fixture.close()
