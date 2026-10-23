"""Actual public ACME deployment scenario. No work runs on import.

A closed future driver owns the adapter, one ChallengeRelay, one issuer gateway,
PublicClient factory, accepted image binding, and independent final cleanup.
"""
import hashlib
import time
import errno
from urllib.error import URLError


def wait(test,seconds,label):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  value=test()
  if value:return value
  time.sleep(.1)
 raise AssertionError(label)


def managed_health(secure):
 try:return secure.request('/health')[0]==200
 except URLError as error:
  if isinstance(error.reason,OSError) and error.reason.errno==errno.ECONNREFUSED:return False
  raise


def run(adapter,admin,secure,relay,tls_patch,public_url,initialize,password):
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
 check('manual_hot_real_renew_and_exact_receipt_replay_same_vm')
 automatic=wait(lambda:(v if (v:=status())['certificate']['sha256']!=manual['certificate']['sha256'] else None),100,'Real scheduled renewal')
 assert adapter.custody()==initial_vm
 assert secure.request('/health')[0]==200
 assert hashlib.sha256(secure.handshakes[-1]['der']).hexdigest()==automatic['certificate']['sha256']
 check('scheduled_real_renew_without_manual_submission_same_vm')
 revision=admin.api({'op':'config_get'})['config_revision']
 adapter.stop_hub();before_state=adapter.private_state()
 assert before_state
 adapter.replace()
 # Only refused TCP while starting is retried by the parent client readiness helper;
 # TLS trust/name failures or HTTP errors must remain immediate failures.
 restarted=wait(lambda: managed_health(secure),45,'Replacement trusted HTTPS')
 assert restarted
 secure.login('admin',password)
 persisted=status();assert persisted['certificate']['sha256']==automatic['certificate']['sha256']
 assert admin.api({'op':'config_get'})['config_revision']==revision
 replacement=adapter.custody();records.append(replacement)
 assert replacement!=initial_vm
 assert secure.request('/health')[0]==200
 assert hashlib.sha256(secure.handshakes[-1]['der']).hexdigest()==automatic['certificate']['sha256']
 check('replacement_new_runtime_same_leaf_account_https',identity=replacement)
 adapter.stop_hub();after_state=adapter.private_state()
 assert after_state==before_state
 check('same_private_account_generation_owner_bytes_after_replacement',
       private_state_sha256=hashlib.sha256('\n'.join(after_state).encode()).hexdigest())
 return {'passed':True,'checks':checks,'runtime_identities':records,
         'scope':'ACME-only actual deployment. Parent adds shipped-listener/mount/security and strictcleanup/protected-resource checks after closure.'}
