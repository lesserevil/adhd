"""Inert real-image fault phases, called only with an owned live fixture.

These phases never issue a fake certificate, edit product state or substitute an
entrypoint. A real trusted baseline is required. Separate reports must retain
foundation results, fault premises, and cleanup; none is implied by import.
"""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import time
from uuid import uuid4
from acme_runtime import PublicClient,regular,sha,ticks,wait_managed_https
from acme_account_continuation import account_facts,private_bytes
from acme_acceptance_fixtures import certificate_facts

FLOOR_CASES=('issuer-503-timeout','issuer-429-timeout','issuer-floor-manual-edit',
             'issuer-floor-cancel','issuer-floor-cold','issuer-floor-resume')
POLICY_CASES=('late-domains','hot-disable')
LOSS_CASES=('parent-loss','client-loss','guardian-loss')
BASIC_CASES=('bad-challenge','issuer-refusal','untrusted-issuer')
CASES=FLOOR_CASES+POLICY_CASES+LOSS_CASES+BASIC_CASES+('real-expiry',)


def wait(test,seconds,label):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=test()
        if result:return result
        time.sleep(.05)
    raise AssertionError(label)


def floor(hub):
    value=json.loads(private_bytes(Path(hub)/'acme'/'issuer-retry.json',1024))
    assert set(value)=={'code','retry_at'}
    assert value['code']in ('ACME_PROCESS','ACME_RATE_LIMIT')
    assert type(value['retry_at'])is int and value['retry_at']>int(time.time()*1000)
    return value


def pending_floor(hub):
    try:return floor(hub)
    except FileNotFoundError:return None


def public_floor_due(status,minimum_ms):
    """Compare RFC3339 public seconds with exact private UTC milliseconds.

    Public timestamps intentionally truncate milliseconds. Compare whole UTC
    seconds, so the correct same-second display passes without granting a local
    30/31s reset any part of the separate 120s issuer minimum.
    """
    assert type(minimum_ms)is int and minimum_ms>=0
    assert status['enabled']is True and status['acme_state']!='ordering'
    value=status['next_attempt_at'];assert isinstance(value,str),'Settled future floor must be published'
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    assert date.tzinfo is not None,'Public due time must carry UTC offset'
    delta=date.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
    public_ms=(delta.days*86400+delta.seconds)*1000+delta.microseconds//1000
    assert public_ms//1000>=minimum_ms//1000,'Published retry predates retained issuer floor'
    return {'public_next_attempt_at':value,'public_due_unix_ms':public_ms,
      'private_issuer_floor_unix_ms':minimum_ms,'comparison':'UTC whole seconds; public display truncates milliseconds'}


def remaining(status):
    assert status['https_state']=='ready'and status['certificate']
    end=datetime.fromisoformat(status['certificate']['not_after'].replace('Z','+00:00'))
    return (end-datetime.now(timezone.utc)).total_seconds()


def owned_child(runtime,kind,expected_sha):
    """Observe an actual descendant and bind executable bytes before signalling."""
    assert kind in ('lego','acme-guard')and runtime.observer is not None
    rows=[row for row in runtime.observer.evidence()['rows']
          if row['executable_basename']==kind and ticks(row['pid'])==row['start_ticks']]
    assert len(rows)==1,'Exactly one live owned client/guardian required'
    row=rows[0];assert sha('/proc/'+str(row['pid'])+'/exe')==expected_sha
    assert ticks(row['pid'])==row['start_ticks']
    return {'pid':row['pid'],'start_ticks':row['start_ticks'],'executable_sha256':expected_sha}


def kill_owned(row):
    descriptor=os.pidfd_open(row['pid'])
    try:
        assert ticks(row['pid'])==row['start_ticks'],'Owned process changed before signal'
        signal.pidfd_send_signal(descriptor,signal.SIGKILL)
    finally:os.close(descriptor)


def lock_busy(hub):
    import fcntl
    path=Path(hub)/'acme'/'client.lock';regular(path)
    fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        entry=os.fstat(fd);assert entry.st_ino==path.lstat().st_ino
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        else:fcntl.flock(fd,fcntl.LOCK_UN);return False
    finally:os.close(fd)


def new_leaf(admin,secure,previous,seconds=40):
    def observed():
        status=admin.api({'op':'tls_status'})
        if status['certificate']and status['certificate']['sha256']!=previous:return status
    status=wait(observed,seconds,'Actual new trusted leaf deadline')
    assert secure.request('/health')[0]==200
    facts=certificate_facts(secure.handshakes[-1]['der'],status['active_domains'],datetime.now(timezone.utc))
    assert facts['leaf_der_sha256']==status['certificate']['sha256']
    return status


def floor_phase(case,*,admin,secure,runtime,hub,issuer,issuer_root,password):
    """Real headers persist before order timeout, edits/cancel/restart cannot erase.

    The configured fault order budget is deliberately 5s, shorter than the
    maintained client's 10s HTTP timeout. Foundation's original 30s stays intact.
    Only issuer-floor-resume requires a later real trusted order after the floor.
    """
    assert case in FLOOR_CASES
    before=admin.api({'op':'tls_status'});assert remaining(before)>=45
    assert issuer.snapshot()['active']==0
    issuer.set_fault(429 if case=='issuer-429-timeout'else 503,120)
    events=len(issuer.snapshot()['events']);started=time.monotonic();earliest_ms=int(time.time()*1000)
    accepted,_=admin.mutate('config_update',patch={'tls':{'acme':{'order_timeout_ms':5000}}})
    durable=wait(lambda:pending_floor(hub),5,'Issuer header floor persisted before original fault order timeout')
    assert durable['retry_at']>=earliest_ms+120000,'Full actual issuer minimum must survive, not just some future floor'
    first=wait(lambda:issuer.snapshot()['events'][events:]or None,
      max(.001,started+5-time.monotonic()),'Actual issuer fault headers observed within same5s premise')
    assert first and all(x['directory']and x['fault_status']in (429,503)for x in first)
    # The maintained process must still own its flock after the floor is on disk.
    assert lock_busy(hub),'Header persistence must precede writer release'
    state_path=Path(hub)/'acme'/'state.json'
    admitted=json.loads(private_bytes(state_path,2097152))
    assert admitted.get('ordering')is True,'Cancellation/manual premise is actual live order'
    # Cancel/edit while the real writer is still held by Retry-After, not after
    # its timeout. This proves the persisted floor crosses active retirement.
    if case=='issuer-floor-cancel':
        admin.mutate('config_update',patch={'tls':{'acme':{'email':'cancel-'+uuid4().hex+'@one.acme.test'}}})
    elif case=='issuer-floor-manual-edit':
        first_receipt,first_command=admin.mutate('tls_renew')
        second_receipt,_=admin.mutate('tls_renew')
        assert first_receipt['accepted']is True and second_receipt['accepted']is True
        assert admin.api(first_command)==first_receipt
        admin.mutate('config_update',patch={'tls':{'acme':{'retry_seconds':31}}})
        assert admin.api({'op':'config_get'})['config']['tls']['acme']['retry_seconds']==31
    def settled():
        state=json.loads(private_bytes(state_path,2097152))
        status=admin.api({'op':'tls_status'})
        if state.get('ordering')is not False:return None
        if case not in ('issuer-floor-cancel','issuer-floor-manual-edit')and not status['last_error']:return None
        return status
    failed=wait(settled,15,'Fault attempt settles without widening order budget')
    assert failed['certificate']['sha256']==before['certificate']['sha256']
    if case not in ('issuer-floor-cancel','issuer-floor-manual-edit'):
        assert failed['last_error']['code']=='ACME_ORDER_TIMEOUT'
        # Issuer header classification and local attempt deadline are distinct.
        assert durable['code']==('ACME_RATE_LIMIT'if case=='issuer-429-timeout'else'ACME_PROCESS')
    assert remaining(failed)>0 and secure.request('/health')[0]==200
    count=issuer.snapshot()['requests'];last=failed['last_attempt_at']
    if case=='issuer-floor-cold':
        keys,_=account_facts(hub)
        runtime.stop();runtime.start()
        managed=PublicClient('https://one.acme.test:18443',trust=issuer_root)
        wait_managed_https(managed,runtime)
        admin=managed;admin.login('admin',password)
        assert account_facts(hub)[0]==keys
    due_observations=[]
    def observed_due():
        assert floor(hub)==durable
        value=admin.api({'op':'tls_status'})
        assert value['enabled']is True
        assert value['last_attempt_at']==last
        assert issuer.snapshot()['requests']==count
        assert value['certificate']['sha256']==before['certificate']['sha256']
        # Cancellation may expose the old active job or a pending scheduler
        # tick. Neither is accepted as the settled result; allow at most2s.
        if value['next_attempt_at']is None:
            due_observations.append({'at_monotonic':time.monotonic(),
              'acme_state':value['acme_state'],'public_next_attempt_at':None})
            assert len(due_observations)<=128
            return None
        compared=public_floor_due(value,durable['retry_at'])
        due_observations.append({'at_monotonic':time.monotonic(),'acme_state':value['acme_state'],**compared})
        assert len(due_observations)<=128
        return compared
    wait(observed_due,2,'Enabled settled retry must publish retained issuer floor')
    observe_until=time.monotonic()+3
    while time.monotonic()<observe_until:
        assert observed_due()is not None,'Settled future floor cannot disappear during original3s guard'
        time.sleep(.1)
    assert int(time.time()*1000)<durable['retry_at']
    resumed=None
    if case=='issuer-floor-resume':
        keys,_=account_facts(hub)
        issuer.set_fault(None)
        # Restore the original genuine-order policy while the issuer floor is
        # still binding; this config edit may queue intent, never bypass floor.
        admin.mutate('config_update',patch={'tls':{'acme':{'order_timeout_ms':30000}}})
        while int(time.time()*1000)<durable['retry_at']:
            assert issuer.snapshot()['requests']==count
            assert admin.api({'op':'tls_status'})['last_attempt_at']==last
            time.sleep(.05)
        status=new_leaf(admin,secure,before['certificate']['sha256'],40)
        actual=json.loads(private_bytes(state_path,2097152))
        assert type(actual['last_attempt_at'])is int and actual['last_attempt_at']>=durable['retry_at']
        assert issuer.snapshot()['requests']>count
        assert account_facts(hub)[0]==keys
        resumed={'leaf_sha256':status['certificate']['sha256'],
          'actual_attempt_ms':actual['last_attempt_at'],'issuer_floor_ms':durable['retry_at'],
          'same_account_public_fingerprints':keys}
    return {'case':case,'passed':True,'actual_header_events':first,'durable_floor':durable,
      'header_observed_while_writer_lock_busy':True,'issuer_retry_seconds':120,'request_earliest_wall_ms':earliest_ms,'settled_error':failed['last_error'],
      'accepted_revision':accepted['config_revision'],'elapsed_seconds':time.monotonic()-started,
      'guarded_seconds':3,'public_due_settle_bound_seconds':2,'public_due_observations':due_observations,
      'no_requests_before_floor_during_guard':True,'actual_resumed_order':resumed,
      'scope':'Real post-floor trusted success only for issuer-floor-resume; other cases qualify their selected bounded transition guard'}


def policy_phase(case,*,admin,secure,runtime,hub,challenge,issuer_root):
    assert case in POLICY_CASES
    before=admin.api({'op':'tls_status'});assert remaining(before)>=45
    assert challenge.snapshot()['active']==0
    challenge.set_mode('hold')
    try:
        admin.mutate('config_update',patch={'tls':{'acme':{'email':'fence-'+uuid4().hex+'@one.acme.test'}}})
        assert challenge.held.wait(20),'Actual successful current proof must be held'
        path,host,body=challenge.held_proof
        assert host.split(':')[0]=='one.acme.test'and body
        if case=='hot-disable':
            admin.mutate('config_update',patch={'tls':{'enabled':False}})
            value=admin.api({'op':'tls_status'})
            assert value['enabled']is False and value['https_state']=='disabled'
        else:
            admin.mutate('config_update',patch={'tls':{'acme':{'domains':['two.acme.test']}}})
        # Release only after the actual new policy committed. Old proof is real,
        # but its late completion must never become the active generation.
        challenge.release.set()
        wait(lambda:challenge.snapshot()['active']==0,5,'Held actual validation releases')
        challenge.set_mode('pass')
        if case=='late-domains':
            current=PublicClient('https://two.acme.test:18443',trust=issuer_root)
            value=new_leaf(admin,current,before['certificate']['sha256'])
            assert value['active_domains']==['two.acme.test']
            from acme_acceptance import raw_challenge
            assert raw_challenge(path,host)[0]==404,'Retired challenge token must not remain public'
        else:
            import ssl
            from urllib.error import URLError
            try:secure.request('/health')
            except URLError as error:
                assert isinstance(error.reason,(ConnectionRefusedError,ssl.SSLError)), 'Disable must close TLS, not just hang'
            except ssl.SSLError:pass
            else:raise AssertionError('Disabled HTTPS still accepted a connection')
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                value=admin.api({'op':'tls_status'})
                assert value['https_state']=='disabled'and value['active_domains']==[]
                assert PublicClient(runtime.base).request('/health')[0]==200
                time.sleep(.1)
        return {'case':case,'passed':True,'late_old_proof_released_after_commit':True,
          'proof_bytes':len(body),'current_active_domains':value['active_domains']}
    finally:challenge.release.set()


def loss_phase(case,*,admin,secure,runtime,hub,challenge,issuer_root,password,target):
    assert case in LOSS_CASES
    before=admin.api({'op':'tls_status'});assert remaining(before)>=45
    keys,_=account_facts(hub)
    challenge.set_mode('hold')
    killed=None;paired=None
    try:
        admin.mutate('config_update',patch={'tls':{'acme':{'domains':['two.acme.test']}}})
        assert challenge.held.wait(20),'Real proof for new domain held before selected process loss'
        assert challenge.held_proof[1].split(':')[0]=='two.acme.test'
        assert secure.request('/health')[0]==200,'Prior valid leaf serves during actual new-domain proof'
        assert lock_busy(hub)
        if case=='parent-loss':
            # Exact owned container PID1 termination; namespace children must die
            # without host-wide process signalling. Runtime close verifies them.
            runtime.stop(hard=True)
        else:
            kind='lego'if case=='client-loss'else'acme-guard'
            other='acme-guard'if kind=='lego'else'lego'
            paired=owned_child(runtime,other,target.assets[other]['sha256'])
            killed=owned_child(runtime,kind,target.assets[kind]['sha256'])
            kill_owned(killed)
            wait(lambda:ticks(killed['pid'])!=killed['start_ticks'],5,'Selected owned child exits')
            wait(lambda:ticks(paired['pid'])!=paired['start_ticks'],5,'Other old writer exits without emergency fixture kill')
            assert not lock_busy(hub),'Product must release old writer lock before fixture teardown'
            # Closing is not a success oracle: observed surviving descendants or
            # emergency cleanup cause runtime.stop to fail this whole phase.
            runtime.stop()
        challenge.release.set()
        wait(lambda:challenge.snapshot()['active']==0,5,'Real old challenge completes')
        challenge.set_mode('pass')
        runtime.start()
        # Original private pre-TLS cookie/session remains valid on unchanged
        # files; no new plaintext login or Secure-cookie rewriting is needed.
        assert account_facts(hub)[0]==keys
        receipt,_=admin.mutate('tls_renew');assert receipt['accepted']is True
        managed=PublicClient('https://two.acme.test:18443',trust=issuer_root)
        resumed=new_leaf(admin,managed,before['certificate']['sha256'])
        assert resumed['active_domains']==['two.acme.test']
        assert account_facts(hub)[0]==keys
        return {'case':case,'passed':True,'selected_owned_child':killed,'other_writer_observed_closed_before_teardown':paired,
          'lock_observed_busy':True,'prior_leaf_served_during_new_domain_challenge':True,
          'actual_postrestart_leaf_sha256':resumed['certificate']['sha256'],
          'same_account_public_fingerprints':keys}
    finally:challenge.release.set()


def expiry_phase(*,admin,secure,hub,issuer):
    before=admin.api({'op':'tls_status'});seconds=remaining(before)
    assert 45<=seconds<=95,'Actual short-lived TestCA cert premise'
    issuer.set_fault(503,120)
    earliest_ms=int(time.time()*1000)
    admin.mutate('tls_renew')
    durable=wait(lambda:pending_floor(hub),5,'Actual issuer floor before expiry')
    assert durable['retry_at']>=earliest_ms+120000
    expires=datetime.fromisoformat(before['certificate']['not_after'].replace('Z','+00:00'))
    while datetime.now(timezone.utc)<=expires:
        assert floor(hub)==durable
        time.sleep(.1)
    status=admin.api({'op':'tls_status'})
    assert status['https_state']=='expired'and status['active_domains']==[]
    # Only an actual TLS/certificate validation failure qualifies; successful
    # HTTP, unrelated timeouts and arbitrary assertion errors are not accepted.
    import ssl
    from urllib.error import URLError
    try:secure.request('/health')
    except URLError as error:
        assert isinstance(error.reason,ssl.SSLError),'Expected certificate/handshake failure'
        failure=type(error.reason).__name__
    except ssl.SSLError as error:failure=type(error).__name__
    else:raise AssertionError('Expired leaf accepted by independent TLS client')
    return {'case':'real-expiry','passed':True,'real_not_after':before['certificate']['not_after'],
      'status':status,'tls_failure_type':failure,'durable_issuer_floor':durable,'clock_modified':False}



def basic_phase(case,*,admin,secure,hub,challenge,issuer_root):
    from acme_fault_cases import corrupt_actual_challenge,directory_connection_refusal,wait_failure,prior_valid
    assert case in BASIC_CASES
    if case=='bad-challenge':result=corrupt_actual_challenge(admin,secure,challenge)
    elif case=='issuer-refusal':result=directory_connection_refusal(admin,secure)
    else:
        before=admin.api({'op':'tls_status'});prior_valid(before)
        # Genuine issuer root is a valid CA PEM, but NOT the HTTPS directory's
        # pinned frontend root. This is an actual trust failure, never skipverify.
        wrong=Path(hub)/'unrelated-directory-root.pem'
        fd=os.open(wrong,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as stream:stream.write(Path(issuer_root).read_bytes())
        accepted,_=admin.mutate('config_update',patch={'tls':{'acme':{'ca_cert_file':str(wrong)}}})
        failed=wait_failure(admin,before,'ACME_PROCESS',accepted['config_revision'])
        assert secure.request('/health')[0]==200
        result={'passed':True,'actual_untrusted_directory_root_sha256':sha(wrong),'last_error':failed['last_error']}
    result['case']=case
    return result
