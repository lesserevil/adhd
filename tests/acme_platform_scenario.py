"""Actual public ACME deployment scenario. No work runs on import.

A closed future driver owns the adapter, one ChallengeRelay, one issuer gateway,
PublicClient factory, accepted image binding, and independent final cleanup.
"""
import hashlib
from datetime import datetime, timezone
import time
import errno
import re
import ssl
from urllib.error import URLError, HTTPError


def wait(test,seconds,label):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  value=test()
  if value:return value
  time.sleep(.1)
 raise AssertionError(label)


def private_startup_health(client):
 # Only the newly published private plain-HTTP socket has this startup allowance.
 assert re.fullmatch(r'http://127[.]0[.]0[.]1:[1-9][0-9]{0,4}',client.base)
 try:status=client.request('/health')[0]
 except HTTPError:raise
 except (URLError,OSError) as error:
  reason=error.reason if isinstance(error,URLError) else error
  if isinstance(reason,OSError) and not isinstance(reason,ssl.SSLError) and reason.errno in (errno.ECONNREFUSED,errno.ECONNRESET):return False
  raise
 assert status==200,'Private startup health status must be200'
 return True


def managed_health(secure):
 try:return secure.request('/health')[0]==200
 except URLError as error:
  if isinstance(error.reason,OSError) and error.reason.errno==errno.ECONNREFUSED:return False
  raise


def public_certificate_time(value):
 assert isinstance(value,str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})',value)
 parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
 assert parsed.tzinfo is not None and parsed.utcoffset() is not None
 delta=parsed.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
 return delta.days*86400000+delta.seconds*1000+delta.microseconds//1000


def renewal_due_ms(certificate):
 before=public_certificate_time(certificate['not_before'])
 after=public_certificate_time(certificate['not_after'])
 assert after>before
 return after-min(86400000,(after-before)//3)


def run(adapter,admin,secure,relay,tls_patch,public_url,initialize,password,certificate_facts):
 """Adapters/clients are real callers, never an injected ACME/client substitute."""
 checks=[];records=[]
 def check(name,**facts):checks.append({'name':name,'passed':True,**facts})
 def status():return admin.api({'op':'tls_status'})
 initialize(admin)
 initial_vm=adapter.custody();records.append(initial_vm)
 check('actual_admitted_runtime_custody',identity=initial_vm)
 disabled=status();assert disabled['enabled'] is False and disabled['https_state']=='disabled'
 assert admin.request('/health')[0]==200
 check('default_disabled_private_http_public_initialization')
 # Relay and gateway are already owned by the driver before public enable.
 assert relay.server is not None
 admin.mutate('config_update',patch={'tls':tls_patch,'public_url':public_url})
 initial=wait(lambda:(v if (v:=status())['https_state']=='ready' else None),35,'Real platform HTTP01 issuance')
 proofs=relay.snapshot();assert any(e['upstream_status']==200 for e in proofs['events'])
 assert not proofs['errors']
 for path in ['/','/health','/admin/api','/.well-known/acme-challenge/'+('a'*22)]:
  assert adapter.challenge_get(path)==404
 check('real_ca_http01_proof',proofs=proofs)
 assert secure.request('/health')[0]==200
 assert secure.handshakes[-1]['verified_chain_and_hostname']
 assert hashlib.sha256(secure.handshakes[-1]['der']).hexdigest()==initial['certificate']['sha256']
 original_cert=certificate_facts(secure.handshakes[-1]['der'],['one.acme.test'],datetime.now(timezone.utc))
 secure.login('admin',password)
 check('actual_trusted_hostname_verified_https_and_admin')
 # Future state/config reads and all sessions use HTTPS after enabling Secure cookies.
 admin=secure
 before=status();accepted,receipt=admin.mutate('tls_renew');assert accepted['accepted'] is True
 manual=wait(lambda:(v if (v:=status())['certificate']['sha256']!=before['certificate']['sha256'] else None),40,'Real manual renewal')
 assert admin.api(receipt)==accepted
 assert adapter.custody()==initial_vm
 assert secure.request('/health')[0]==200
 assert hashlib.sha256(secure.handshakes[-1]['der']).hexdigest()==manual['certificate']['sha256']
 manual_cert=certificate_facts(secure.handshakes[-1]['der'],['one.acme.test'],datetime.now(timezone.utc))
 for key in ['serial_number_hex','public_key_spki_sha256']:assert manual_cert[key]!=original_cert[key]
 check('manual_hot_real_renew_and_exact_receipt_replay_same_vm')
 automatic=wait(lambda:(v if (v:=status())['certificate']['sha256']!=manual['certificate']['sha256'] else None),100,'Real scheduled renewal')
 assert adapter.custody()==initial_vm
 assert secure.request('/health')[0]==200
 assert hashlib.sha256(secure.handshakes[-1]['der']).hexdigest()==automatic['certificate']['sha256']
 automatic_cert=certificate_facts(secure.handshakes[-1]['der'],['one.acme.test'],datetime.now(timezone.utc))
 for key in ['serial_number_hex','public_key_spki_sha256']:assert automatic_cert[key]!=manual_cert[key]
 check('scheduled_real_renew_without_manual_submission_same_vm')
 revision=admin.api({'op':'config_get'})['config_revision']
 # The90s testCA leaf's next natural rotation must be beyond this shared45s
 # cold-replacement phase; no clock mutation, CA replacement or retry is used.
 certificate=automatic['certificate']
 due=renewal_due_ms(certificate)
 assert due-int(time.time()*1000)>45000,'Fresh scheduled leaf lacks the required replacement window'
 previous_deadline=adapter.command.phase_deadline;deadline=time.monotonic()+45
 adapter.command.phase_deadline=deadline
 try:
  adapter.stop_hub();before_state=adapter.private_state()
  assert before_state
  adapter.replace()
  # Only refused TCP while starting is retried by the parent client readiness helper;
  # TLS trust/name failures or HTTP errors must remain immediate failures.
  restarted=wait(lambda: managed_health(secure),max(0,deadline-time.monotonic()),'Replacement trusted HTTPS')
  assert restarted
  secure.login('admin',password)
  persisted=status();assert persisted['certificate']['sha256']==automatic['certificate']['sha256']
  assert admin.api({'op':'config_get'})['config_revision']==revision
  replacement=adapter.custody();records.append(replacement)
  assert replacement!=initial_vm
  assert secure.request('/health')[0]==200
  assert hashlib.sha256(secure.handshakes[-1]['der']).hexdigest()==automatic['certificate']['sha256']
  assert time.monotonic()<=deadline,'Cold replacement exceeded shared45s'
 finally:adapter.command.phase_deadline=previous_deadline
 check('replacement_new_runtime_same_leaf_account_https',identity=replacement)
 adapter.stop_hub();after_state=adapter.private_state()
 assert after_state==before_state
 check('same_private_account_generation_owner_bytes_after_replacement',
       private_state_sha256=hashlib.sha256('\n'.join(after_state).encode()).hexdigest())
 return {'passed':True,'checks':checks,'runtime_identities':records,
         'scope':'ACME-only actual deployment. Parent adds shipped-listener/mount/security and strictcleanup/protected-resource checks after closure.'}
