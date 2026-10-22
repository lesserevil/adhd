"""Independent authenticated v2 HTTP recovery failures on owned storage only."""
import asyncio
import os
from pathlib import Path
import secrets
from uuid import uuid4

import httpx
from multi_support import Fixture, Evidence, arguments
from project_recovery_acceptance import Recovery, RED, BLUE, HIDDEN
from project_recovery_state import route


async def main():
    parser = arguments(__doc__)
    parser.add_argument('--recovery-schema', type=Path, required=True)
    args = parser.parse_args()
    assert not args.rest_url and not args.with_model
    f = Fixture(args, initialize_projects=False)
    evidence = Evidence(args.report, 'federation-v2-recovery-http')
    evidence.value.update(lifecycle_admitted=False, scope='Real authenticated v2 HTTP; no Kafka or model; owned unknown and missing targets with healthy peer project')
    evidence.value['limitations'] = ['No semantic, Kafka, crash, or admitted-image qualification.']
    peer_id, token, outbound = uuid4().hex, secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    f.config['eventing']['enabled'] = False
    f.config['federation'] = {'description': 'Recovery HTTP fixture', 'retry_ms': 1000, 'timeout_ms': 1000,
        'peers': [{'server_id': peer_id, 'url': 'http://127.0.0.1:1', 'token': outbound, 'inbound_token': token,
                   'project_pairs': [{'local_project_id': p, 'remote_project_id': 'remote'} for p in (RED, BLUE)]}]}
    async def wire(project, expected, code, credential=token):
        command = {'protocol_version': 2, 'op': 'status', 'origin_server_id': peer_id,
            'origin_project_id': 'remote', 'destination_project_id': project, 'query_id': 'not-created'}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(f.base + '/federation/v2', json=command,
                headers={'Authorization': 'Bearer ' + credential}, timeout=5)
        assert response.status_code == expected, (response.status_code, response.json())
        assert response.json() == {'protocol_version': 2, 'error': {'code': code, 'message': 'Federation request rejected'}}
        if code == 'RECOVERY_REQUIRED':
            assert response.headers.get('retry-after') == '1'
        else:
            assert 'retry-after' not in response.headers
        return {'http_status': response.status_code, 'code': code,
                'retry_after': response.headers.get('retry-after')}
    try:
        await f.start()
        r = Recovery(f, args.recovery_schema)
        evidence.record('authorized-uninitialized-target-is-retryable', response=await wire(RED, 503, 'RECOVERY_REQUIRED'))
        evidence.record('unauthorized-project-pair-remains-hidden', response=await wire(HIDDEN, 403, 'FORBIDDEN'))
        evidence.record('agent-token-cannot-authenticate-as-peer', response=await wire(RED, 401, 'UNAUTHORIZED', f.tokens['bridge']))
        await r.initialize(RED)
        await r.initialize(BLUE)
        evidence.record('initialized-target-retains-ordinary-not-found', response=await wire(RED, 404, 'NOT_FOUND'))
        f.hard_stop()
        _, anchor = route(f.file, RED)
        for path in (anchor, Path(str(anchor) + '.snapshot')):
            os.replace(path, Path(str(path) + '.held'))
        await f.start()
        assert r.status(RED)['availability'] == 'recovery_required'
        config = f.admin().call({'op': 'config_get'})
        evidence.record('authorized-known-missing-target-is-retryable-after-cold-start', response=await wire(RED, 503, 'RECOVERY_REQUIRED'))
        evidence.record('healthy-other-project-and-global-control-remain-available', response=await wire(BLUE, 404, 'NOT_FOUND'))
        assert f.admin().call({'op': 'config_get'}) == config
        f.bind_evidence(evidence)
        evidence.finish()
    except BaseException as error:
        evidence.finish(error)
        raise
    finally:
        await f.close()


if __name__ == '__main__':
    asyncio.run(main())
