"""Additional real-CA fault strata, inert until explicitly invoked by a driver.

No fake signer/client, service shutdown, private-state editing or clock changes.
Fault scopes and observations are separate from successful issuer foundations.
"""
from datetime import datetime, timezone
import socket
import time


def prior_valid(status):
    assert status['https_state']=='ready' and status['certificate'] is not None and status['last_error'] is None
    expiry=datetime.fromisoformat(status['certificate']['not_after'].replace('Z','+00:00'))
    remaining=(expiry-datetime.now(timezone.utc)).total_seconds()
    assert remaining>=35, 'Fresh valid certificate premise required before bounded fault'
    return status['certificate']['sha256']


def wait_failure(admin, before, expected, expected_revision, seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=admin.api({'op':'tls_status'})
        assert value['config_revision']==expected_revision
        if value['last_error'] is not None:
            # Timestamps are second-resolution: two actual attempts may have
            # equal public times. New revision + prior clean state + actual CA
            # proof events establish the new operation without a timing fiction.
            assert before['last_error'] is None and value['last_attempt_at'] is not None
            assert value['last_error']['code']==expected, 'Actual CA failure classification'
            assert value['https_state']=='ready' and value['certificate']['sha256']==before['certificate']['sha256']
            assert value['acme_state']=='backoff' and value['next_attempt_at'] is not None
            expiry=datetime.fromisoformat(before['certificate']['not_after'].replace('Z','+00:00'))
            assert datetime.now(timezone.utc)<expiry
            return value
        time.sleep(.1)
    raise AssertionError('Actual failed order did not settle within original bounded observation')


def corrupt_actual_challenge(admin, secure, relay):
    before=admin.api({'op':'tls_status'})
    leaf=prior_valid(before)
    assert relay.snapshot()['active']==0
    start=len(relay.snapshot()['events'])
    relay.set_mode('corrupt')
    try:
        # A configured new contact gets a real independent account. Previously
        # authorized account/domain reuse must not bypass this challenge case.
        accepted,_=admin.mutate('config_update',patch={'tls':{'acme':{'email':'fault-authorization@one.acme.test'}}})
        failed=wait_failure(admin,before,'ACME_PROCESS',accepted['config_revision'])
        events=relay.snapshot()['events'][start:]
        assert events and all(row['upstream_status']==200 and row['mode']=='corrupt' for row in events)
        assert secure.request('/health')[0]==200
        return {'name':'real corrupted HTTP01 fails authorization while prior valid certificate serves',
                'passed':True,'prior_leaf_sha256':leaf,'actual_validation_requests':len(events),
                'last_error':failed['last_error'],'account_reuse_prevented_by_configured_new_contact':True}
    finally:
        deadline=time.monotonic()+3
        while relay.snapshot()['active'] and time.monotonic()<deadline:
            time.sleep(.05)
        relay.set_mode('pass')


def directory_connection_refusal(admin, secure):
    before=admin.api({'op':'tls_status'})
    leaf=prior_valid(before)
    # Own an unlistened TCP port for deterministic local refusal; never stop the
    # persistent shared TestCA or point the product at a foreign endpoint.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        port=reservation.getsockname()[1]
        accepted,_=admin.mutate('config_update',patch={'tls':{'acme':{'directory_url':f'https://localhost:{port}/dir'}}})
        failed=wait_failure(admin,before,'ACME_PROCESS',accepted['config_revision'])
        assert secure.request('/health')[0]==200
        return {'name':'owned refused directory endpoint preserves prior valid certificate',
                'passed':True,'prior_leaf_sha256':leaf,'last_error':failed['last_error'],
                'persistent_testca_untouched':True}
