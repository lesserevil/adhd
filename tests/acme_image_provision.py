"""Reusable owned real-image/TestCA session. Import/constructor are inert.

Caller authenticates the complete plan/helper/tool/CA/target closure BEFORE start
and holds the exclusive CA/HTTP01 lease. No admission or success is synthesized.
Use start inside try/finally close, or the context manager. Password stays in
memory and is deliberately excluded from evidence(). No browser is launched.
"""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
from datetime import datetime,timezone
from acme_runtime import PublicClient,regular,sha,ticks
from acme_image_session import runtime_class
from acme_acceptance import initialize
from acme_acceptance_fixtures import certificate_facts,active_private_key_facts
from acme_challenge_relay import ChallengeRelay
from acme_issuer_fault_relay import IssuerFaultRelay


class OwnedProvision:
    def __init__(self,plan,target,work):
        self.plan,self.target,self.work=plan,target,Path(work)
        self.hub=self.work/'hub';self.runtime=self.issuer=self.challenge=None
        self.admin=self.secure=self.ca=self.password=self.certificate=None
        self.cleanup_errors=[];self.baseline=None

    def start(self):
        from jsonschema import Draft202012Validator,FormatChecker
        import time
        assert not self.work.exists(),'Fresh owned image session root required'
        self.work.mkdir(mode=0o700)
        ca_path=Path(self.plan['ca_manifest']);regular(ca_path)
        assert sha(ca_path)==self.plan['files'][str(ca_path)]
        self.ca=ca=json.loads(ca_path.read_text())
        assert ca['ready']and ca['real_validation']and ca['nonce_validation']and ca['public_ca_calls']==0
        for row in ca['processes']:assert ticks(row['pid'])==row['start_ticks'],'Actual CA lease changed'
        for name in ['frontend_root','issuer_root']:regular(ca[name]);assert sha(ca[name])==ca[name+'_sha256']
        schema=json.loads(Path(self.plan['schema_file']).read_text())
        validator=Draft202012Validator({'$ref':'#/$defs/TLSStatus','$defs':schema['$defs']},format_checker=FormatChecker())
        # Assign each resource BEFORE starting it, so partial start is closable.
        self.issuer=IssuerFaultRelay(**self.plan['issuer_relay']);self.issuer.start()
        self.challenge=ChallengeRelay(upstreams={'one.acme.test':('127.0.0.2',8080),'two.acme.test':('127.0.0.2',8080)})
        self.challenge.start()
        with socket.socket()as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        subprocess.run([sys.executable,self.plan['configure'],'--directory',str(self.hub),'--port',str(port),
          '--store-path',str(self.hub/'state.dets')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30)
        config=json.loads((self.hub/'hub.json').read_text());assert config['matcher']is None
        config['eventing']={'enabled':False};(self.hub/'hub.json').write_text(json.dumps(config));(self.hub/'hub.json').chmod(0o600)
        trust=self.hub/'directory-root.pem';trust.write_bytes(Path(ca['frontend_root']).read_bytes());trust.chmod(0o600)
        self.runtime=runtime_class(self.target,self.work)(self.hub,None,None,None,None,erlang=None)
        self.runtime.start()
        self.password=re.search(r'^Password: (.+)$',(self.hub/'initial-admin-password.txt').read_text(),re.M)[1]
        # Retain the actual pre-TLS private HTTP session. No cookie rewriting or
        # new plaintext login after managed HTTPS. Caller can use this for repair
        # or expiry/disable observations while secure transport is unavailable.
        self.admin=PublicClient(self.runtime.base);self.admin.login('admin',self.password);initialize(self.admin)
        self.tls={'enabled':True,'host':'127.0.0.1','port':18443,'challenge_host':'127.0.0.2','challenge_port':8080,
          'acme':{'enabled':True,'directory_url':'https://localhost:19103/dir','email':'operator@one.acme.test',
            'domains':['one.acme.test'],'accept_terms':True,'renew_before_days':1,'retry_seconds':30,
            'order_timeout_ms':30000,'ca_cert_file':'directory-root.pem'}}
        self.admin.mutate('config_update',patch={'tls':self.tls,'public_url':'https://one.acme.test:18443'})
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            status=self.admin.api({'op':'tls_status'});validator.validate(status)
            assert status['last_error']is None,'Genuine baseline issuance failed'
            if status['https_state']=='ready':self.baseline=status;break
            time.sleep(.1)
        assert self.baseline is not None,'Actual trusted baseline issuance40s'
        self.secure=PublicClient('https://one.acme.test:18443',trust=ca['issuer_root'])
        assert self.secure.request('/health')[0]==200
        der=self.secure.handshakes[-1]['der']
        self.certificate=certificate_facts(der,['one.acme.test'],datetime.now(timezone.utc))
        assert self.certificate['leaf_der_sha256']==self.baseline['certificate']['sha256']
        key=active_private_key_facts(self.hub,der)
        assert key['public_key_spki_sha256']==self.certificate['public_key_spki_sha256']
        self.runtime.checkpoint('real-provisioned-baseline')
        return self

    def evidence(self):
        return {'certificate':self.certificate,'baseline':self.baseline,
          'runtime_identities':self.runtime.identities if self.runtime else [],
          'issuer':self.issuer.snapshot()if self.issuer else None,
          'challenge':self.challenge.snapshot()if self.challenge else None,
          'cleanup_errors':list(self.cleanup_errors),
          'scope':'Actual single default-entrypoint image, real issuer proxy+HTTP01, private pre-TLS Admin and independently trusted HTTPS; no browser or full foundation qualification implied'}

    def close(self):
        errors=[]
        for item in [self.runtime,self.challenge,self.issuer]:
            if item is not None:
                try:item.stop()if item is self.runtime else item.close()
                except BaseException as error:errors.append(error)
        self.cleanup_errors.extend(type(error).__name__ for error in errors)
        if errors:
            for error in errors[1:]:errors[0].add_note('Owned provision cleanup: '+type(error).__name__)
            raise errors[0]

    def __enter__(self):
        try:return self.start()
        except BaseException as primary:
            try:self.close()
            except BaseException as error:primary.add_note('Owned provision startup cleanup: '+type(error).__name__)
            raise

    def __exit__(self,kind,primary,traceback):
        try:self.close()
        except BaseException as error:
            if primary:primary.add_note('Owned provision cleanup: '+type(error).__name__)
            else:raise
