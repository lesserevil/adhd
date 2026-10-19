"""Independent administrator API scenarios; never import generated application code."""
import asyncio
import json
import secrets
from uuid import uuid4
import httpx
import hub_acceptance as acceptance


async def admin_checks(command, root, record):
    fixture = acceptance.ModelFixture()
    hub = acceptance.Hub(command, root / 'admin', fixture.url)
    token = secrets.token_urlsafe(32)
    a = b = None
    async with httpx.AsyncClient(timeout=6) as client:
        async def request(c, credential=token, **headers):
            return await client.post(hub.base + '/admin/api', json=c,
                headers={'Authorization': 'Bearer ' + credential, **headers})
        async def call(c):
            r = await request(c)
            assert r.status_code == 200, (r.status_code, r.text)
            return r.json()
        try:
            for index, bad_token in enumerate(('short-admin-token', ' ' * 32, hub.tokens['agent-a'])):
                invalid = acceptance.Hub(command, root / ('invalid-admin-' + str(index)), fixture.url)
                if index == 2: bad_token = invalid.tokens['agent-a']
                invalid.config['admin_token'] = bad_token
                invalid.config_file.write_text(json.dumps(invalid.config))
                try:
                    try: invalid.start()
                    except AssertionError:
                        assert invalid.process.poll() is not None
                    else: raise AssertionError('Invalid administrator configuration accepted')
                    logs = ''.join(p.read_text(errors='replace') for p in invalid.root.glob('*.log'))
                    assert bad_token not in logs
                finally: invalid.stop()
            record('admin-invalid-configuration-fails-without-credential-logging')
            hub.start()
            assert (await request({'op': 'overview'})).status_code == 404
            hub.stop()
            hub.config['admin_token'] = token
            hub.config_file.write_text(json.dumps(hub.config))
            hub.start()
            a, b = await hub.agent('agent-a'), await hub.agent('agent-b')
            for credential in ('wrong-token', hub.tokens['agent-a'], hub.tokens['agent-b']):
                assert (await request({'op': 'overview'}, credential)).status_code == 401
            assert (await client.post(hub.base + '/admin/api', json={'op': 'overview'})).status_code == 401
            assert (await client.post(hub.base + '/a2a', json={}, headers={'Authorization':'Bearer '+token})).status_code == 401
            assert (await request({'op': 'overview'}, Origin='https://foreign.example')).status_code == 403
            assert (await request({'op': 'overview'}, Origin=hub.base)).status_code == 200
            for c in ({'op':'deliveries','limit':0}, {'op':'overview','extra':True},
                      {'op':'retry_jobs','message_id':'x'}, {'op':'remove_subscription','subscription_id':'x','confirm':False,'message_id':'x'},
                      {'op':'create_subscription','agent_id':'agent-a','description':'','message_id':'x'}):
                assert (await request(c)).status_code == 400
            record('admin-authentication-origin-validation-and-legacy-disable')
            shell = await client.get(hub.base + '/')
            assert shell.status_code == 200 and 'text/html' in shell.headers['content-type']
            for path, mime in [('app.js','javascript'), ('app.css','text/css')]:
                asset = await client.get(hub.base + '/admin/assets/' + path)
                assert asset.status_code == 200 and mime in asset.headers['content-type']
                assert token not in asset.text and all(t not in asset.text for t in hub.tokens.values())
            assert shell.headers['cache-control'] == 'no-store'
            assert "frame-ancestors 'none'" in shell.headers['content-security-policy']
            assert token not in shell.text and 'acceptance-project' not in shell.text
            record('admin-anonymous-shell-assets-and-security-headers')
            mutation = {'op':'create_subscription','agent_id':'agent-b','description':'API status and progress updates','message_id':str(uuid4())}
            created = await call(mutation)
            assert created == await call(mutation)
            sid = created['subscription']['id']
            changed = {**mutation,'description':'changed'}
            assert (await request(changed)).status_code == 409
            assert (await b.call({'op':'list_subscriptions'}))['subscriptions'][0]['id'] == sid
            private = (await a.call({'op':'send','recipient_id':'agent-b','text':'SECRET-PRIVATE-CONTENT','data':{'secret':'PRIVATE-DATA'}}))['delivery']
            pub = (await a.call({'op':'publish','information_type':'status','text':'API status <img src=x onerror=alert(1)>','data':{'progress':42}}))['publication']
            await acceptance.wait_deliveries(b,lambda ds:any(d.get('publication_id')==pub['id'] for d in ds))
            overview = await call({'op':'overview'})
            assert overview['counts']['agents'] == 2 and overview['counts']['queued_deliveries'] >= 2
            assert overview['matcher']['status'] == 'ready', overview
            assert len((await call({'op':'publications','query':'API','information_type':'status'}))['items']) == 1
            assert (await call({'op':'publication','publication_id':pub['id']}))['publication']['id'] == pub['id']
            assert (await request({'op':'publication','publication_id':private['id']})).status_code == 404
            assert not (await call({'op':'publications','query':'no-such-content'}))['items']
            assert (await call({'op':'subscriptions','agent_id':'agent-b'}))['items'][0]['id'] == sid
            deliveries = await call({'op':'deliveries','agent_id':'agent-b'})
            assert len(deliveries['items']) >= 2
            assert 'SECRET-PRIVATE' not in json.dumps(deliveries) and 'PRIVATE-DATA' not in json.dumps(deliveries)
            assert all(not ({'text','data'} & set(d)) for d in deliveries['items'])
            for c in ({'op':'overview'},{'op':'jobs'},{'op':'deliveries'},{'op':'subscriptions'}):
                response = json.dumps(await call(c))
                assert token not in response and all(t not in response for t in hub.tokens.values())
            assert len((await b.call({'op':'poll'}))['deliveries']) >= 2
            record('admin-two-agent-archive-observation-and-private-visibility')
            fixture.mode = 'error'
            pending = (await a.call({'op':'publish','text':'API status while matcher unavailable'}))['publication']
            await asyncio.sleep(.2)
            for _ in range(60):
                if (await call({'op':'overview'}))['matcher']['status'] == 'unavailable': break
                await asyncio.sleep(.1)
            else: raise AssertionError('Matcher outage was not observed within the probe interval')
            assert any(j['publication_id']==pending['id'] for j in (await call({'op':'jobs','status':'pending'}))['items'])
            retry = {'op':'retry_jobs','confirm':True,'message_id':str(uuid4())}
            retried = await call(retry)
            assert retried['retried'] >= 1 and retried == await call(retry)
            remove = {'op':'remove_subscription','subscription_id':sid,'confirm':True,'message_id':str(uuid4())}
            removed = await call(remove)
            assert removed == {'removed':True,'subscription_id':sid}
            assert len((await b.call({'op':'poll'}))['deliveries']) >= 2
            assert not (await call({'op':'jobs','status':'pending'}))['items']
            record('admin-matcher-outage-confirmed-retry-and-subscription-removal')
            hub.stop(hard=True)
            hub.start()
            assert created == await call(mutation)
            assert removed == await call(remove)
            assert retried == await call(retry)
            assert (await request(changed)).status_code == 409
            assert not (await call({'op':'subscriptions'}))['items']
            state = (hub.root / 'hub.dets').read_bytes()
            logs = ''.join(p.read_text(errors='replace') for p in hub.root.glob('*.log'))
            assert token.encode() not in state and token not in logs
            assert all(t not in logs for t in hub.tokens.values())
            record('admin-durable-mutation-idempotency-restart-and-secret-exclusion')
        finally:
            if a: await a.close()
            if b: await b.close()
            hub.stop()
            fixture.close()
