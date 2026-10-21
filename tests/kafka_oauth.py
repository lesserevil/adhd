#!/usr/bin/env python3
"""Isolated real REST OAuth/TLS qualification; optional full-hub hot rotation.

Native Confluent AuthenticationHandler uses its documented Enterprise/trial scope.
No preexisting broker, app or model is changed. Secrets stay in the private fixture.
"""
import argparse
import asyncio
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import time
from uuid import uuid4

import httpx

from kafka_oauth_provider import Issuer, private
from multi_support import Evidence, Fixture, poll_until, scoped


async def main(args):
    repo=Path(__file__).resolve().parents[1]
    root=args.work.resolve()
    if root.exists():
        raise ValueError('Private fixture directory must be fresh')
    root.mkdir(parents=True,mode=0o700)
    args.hub=args.hub.resolve() if args.hub else None
    if not args.project.startswith('adhd-oauth-'):
        raise ValueError('Use a dedicated adhd-oauth-* Compose project')
    active=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project='+args.project],text=True).strip()
    if active:
        raise ValueError('Compose project already exists; never adopt or mutate unknown services')
    env={**os.environ,'ADHD_KAFKA_TEST_PORT':str(args.port)}
    compose=['docker','compose','-p',args.project,'-f',str(repo/'deploy/events.compose.yaml'),
             '-f',str(repo/'deploy/events.test.compose.yaml')]
    log=(root/'services.log').open('ab')
    evidence=Evidence(args.report,'adhd/kafka-native-oauth-tls@1')
    evidence.value.update(lifecycle_qualified=False,license_scope='Confluent Enterprise or documented permitted trial',
        authentication='Native AuthenticationHandler; no Basic/MDS fallback; no principal propagation',
        broker_security='Fresh private single-broker plaintext lane; TLS/SASL broker overlay not qualified by this probe',
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        issuer_harness_sha256=hashlib.sha256(Path(__file__).with_name('kafka_oauth_provider.py').read_bytes()).hexdigest())
    evidence.value['limitations']=['Native single-broker diagnostic; no replicated durability or production entitlement qualification.','No semantic model service is started or called; matcher is absent and pub/sub uses raw selectors.','Private proxy-to-broker plaintext remains separate; broker SASL/TLS and Kubernetes live rollout are not qualified here.']
    issuer=hub=None
    tokens=[]
    http=None
    completed=False
    secrets_to_check=[]
    def run(command,**kwargs):
        return subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=150,**kwargs)
    try:
        run(compose+['up','-d','kafka'])
        network=args.project+'_events'
        gateway=subprocess.check_output(['docker','network','inspect',network,'--format','{{(index .IPAM.Config 0).Gateway}}'],text=True).strip()
        issuer=Issuer(root/'security',gateway,wrong_hostname=True)
        issuer.java_truststore()
        props=(repo/'deploy/security/kafka-rest.oauth.properties.example').read_text()
        props=props.replace('https://ISSUER/.well-known/jwks.json',issuer.issuer+'/jwks').replace('https://ISSUER',issuer.issuer)
        props=props.replace('ADHD_EVENT_SERVICE','adhd-event-service').replace('REPLACE_WITH_PRIVATE_KEYSTORE_PASSWORD',issuer.password).replace('REPLACE_WITH_PRIVATE_TRUSTSTORE_PASSWORD',issuer.password)
        private(issuer.root/'kafka-rest.properties',props.encode())
        env.update(ADHD_KAFKA_SECURITY_UID=str(os.getuid()),ADHD_KAFKA_SECURITY_GID=str(os.getgid()),ADHD_KAFKA_JWKS_URL=issuer.issuer+'/jwks',ADHD_KAFKA_OAUTH_ENTITLEMENT='permitted-trial',ADHD_KAFKA_SECURITY_DIR=str(issuer.root))
        compose+=['-f',str(repo/'deploy/events.oauth.compose.yaml'),'--profile','enterprise-oauth']
        run(compose+['up','-d','--wait','--wait-timeout','120','kafka-rest'])
        url='https://127.0.0.1:'+str(args.port)
        context=ssl.create_default_context(cafile=str(issuer.root/'ca.pem'))
        http=httpx.Client(verify=context,timeout=10)
        first=issuer.token();second=issuer.token('second');tokens.extend([first,second])
        def get(token=None,path='/v3/clusters'):
            return http.get(url+path,headers={} if token is None else {'Authorization':'Bearer '+token})
        async def broker_checkpoint(topic,token,expected):
            group=topic+'.fanout'
            name='oauth-observer-'+uuid4().hex
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/vnd.kafka.v2+json','Accept':'application/vnd.kafka.v2+json'}
            response=http.post(url+'/consumers/'+group,headers=headers,json={'name':name,'format':'json','auto.commit.enable':'false'})
            assert response.status_code==200
            path='/consumers/'+group+'/instances/'+name
            try:
                assert http.post(url+path+'/assignments',headers=headers,json={'partitions':[{'topic':topic,'partition':0}]}).status_code==204
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    response=http.request('GET',url+path+'/offsets',headers=headers,
                        json={'partitions':[{'topic':topic,'partition':0}]})
                    assert response.status_code==200
                    offsets=response.json()['offsets']
                    value=offsets[0]['offset'] if offsets else -1
                    if value>=expected:
                        return value
                    await asyncio.sleep(.1)
                raise AssertionError('Actual broker group checkpoint did not reach durable materialization')
            finally:
                assert http.delete(url+path,headers=headers).status_code==204
        # The issuer initially presents a CA-trusted certificate for the wrong
        # hostname. The actual native JWKS client must refuse authentication.
        first_response=get(first)
        assert first_response.status_code in (401,403)
        assert issuer.requests==0, 'Proxy must reject the mismatching JWKS TLS hostname before HTTP'
        evidence.record('native-jwks-client-rejects-trusted-certificate-with-wrong-hostname')
        issuer.repair_hostname(gateway)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            try:
                response=get(first)
                if response.status_code==200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.2)
        else:
            raise AssertionError('Native authenticated REST readiness failed; inspect private service log')
        for path in ['/v3/clusters','/topics','/brokers']:
            assert get(first,path).status_code==200
            assert get(None,path).status_code in (401,403)
        evidence.record('trusted-https-and-native-valid-bearer-protect-v2-and-v3-real-broker-operations')
        negatives={'wrong-signature':first[:-8]+'AAAAAAAA','wrong-issuer':issuer.token(iss='https://wrong.example.invalid'),
                   'wrong-audience':issuer.token(aud='wrong-audience'),'expired':issuer.token(exp=int(time.time())-3600),
                   'future-not-before':issuer.token(nbf=int(time.time())+3600),'malformed':'malformed-bearer-value-000000000'}
        for name,token in negatives.items():
            tokens.append(token)
            assert get(token).status_code in (401,403),name
        evidence.record('missing-malformed-signature-issuer-audience-expiration-and-not-before-credentials-fail')
        # TLS failures are real certificate failures, never verify=False checks.
        with httpx.Client(timeout=3) as os_trust:
            try:
                os_trust.get(url+'/brokers',headers={'Authorization':'Bearer '+first})
            except httpx.ConnectError:
                pass
            else:
                raise AssertionError('Private CA was unexpectedly accepted by OS roots')
        evidence.record('untrusted-rest-server-certificate-is-rejected-without-trust-bypass')
        if args.hub:
            args.command=None;args.rest_url=None;args.credentials=None;args.keep_work=root/'hub';args.with_model=False
            args.eventing_rest_url=url;args.deadline=25
            hub=Fixture(args)
            hub.config['eventing'].update(bearer_token=first,tls_ca_pem=issuer.ca_pem.decode())
            await hub.start()
            evidence.value['artifact_sha256']=hashlib.sha256(args.hub.read_bytes()).hexdigest()
            a,b=await hub.agent('red-a'),await hub.agent('red-b')
            admin=hub.admin();pid=hub.process.pid
            await b.call(scoped('project-red','subscribe',mode='raw'))
            before=(await a.call(scoped('project-red','publish',text='Authenticated Kafka cursor before rotation')))['publication']
            rows=await poll_until(b,'project-red',{before['id']},25)
            await b.call(scoped('project-red','ack',delivery_ids=[rows[0]['id']]))
            # Invalid proposals must fail preflight with no config activation.
            status=admin.call(scoped('project-red','eventing_status'))
            checkpoint=status['next_offset']
            assert checkpoint>=1
            broker_before=await broker_checkpoint(status['topic'],first,checkpoint)
            assert broker_before==checkpoint
            initial=admin.call({'op':'config_get'})['config']
            for patch in [{'bearer_token':negatives['expired']},{'tls_ca_pem':None}]:
                admin.call({'op':'config_update','patch':{'eventing':patch}},mutation=True,expected=409)
                assert admin.call({'op':'config_get'})['config']==initial
            evidence.record('live-admin-rejects-expired-bearer-and-missing-private-ca-without-activation')
            admin.call({'op':'config_update','patch':{'eventing':{'bearer_token':second}}},mutation=True)
            assert hub.process.pid==pid and hub.process.poll() is None
            assert admin.call(scoped('project-red','eventing_status'))['next_offset']==checkpoint
            assert await broker_checkpoint(status['topic'],second,checkpoint)==broker_before
            issuer.retire('first')
            # An issuer retires its signing key; refreshing JWKS rejects that
            # key's tokens. Merely changing the hub header is not revocation.
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                assert get(second).status_code==200
                if get(first).status_code in (401,403):
                    break
                await asyncio.sleep(.3)
            else:
                raise AssertionError('Retired signing key remained accepted after bounded JWKS refresh')
            current=admin.call({'op':'config_get'})['config']
            unrelated=Issuer(root/'unrelated-trust',gateway)
            wrong_ca=unrelated.ca_pem.decode()
            unrelated.close()
            for patch,expected_status in [({'tls_ca_pem':None},409),({'tls_ca_pem':wrong_ca},409),
                ({'tls_ca_pem':'not a certificate'},400),
                ({'tls_ca_pem':issuer.ca_pem.decode()+(issuer.root/'issuer-key.pem').read_text()},400)]:
                admin.call({'op':'config_update','patch':{'eventing':patch}},mutation=True,expected=expected_status)
                assert admin.call({'op':'config_get'})['config']==current
                assert hub.process.pid==pid and hub.process.poll() is None
            evidence.record('postrotation-missing-wrong-malformed-and-private-key-trust-proposals-fail-without-current-config-change')
            after=(await a.call(scoped('project-red','publish',text='Authenticated Kafka cursor after hot rotation')))['publication']
            after_rows=await poll_until(b,'project-red',{after['id']},25)
            assert all(d.get('publication_id')!=before['id'] for d in after_rows)
            assert (await a.call(scoped('project-red','get',publication_id=before['id'])))['publication']==before
            assert hub.process.pid==pid and hub.process.poll() is None
            after_checkpoint=admin.call(scoped('project-red','eventing_status'))['next_offset']
            assert after_checkpoint>checkpoint
            broker_after=await broker_checkpoint(status['topic'],second,after_checkpoint)
            assert broker_after==after_checkpoint
            evidence.record('hot-admin-bearer-replacement-preserves-pid-original-ack-and-live-kafka-progress-while-retired-key-fails', next_offset_before=checkpoint,next_offset_after=after_checkpoint,broker_group_next_before=broker_before,broker_group_next_after=broker_after)
        else:
            issuer.retire('first')
        # Keep raw container logs private; prove they did not print credentials.
        output=subprocess.check_output(compose+['logs','--no-color','kafka-rest'],env=env)
        secrets_to_check=tokens+[issuer.password,'-----BEGIN PRIVATE KEY-----']
        assert all(value.encode() not in output for value in secrets_to_check)
        if hub:
            assert all(value.encode() not in (hub.root/'stdout.log').read_bytes()+(hub.root/'stderr.log').read_bytes() for value in secrets_to_check)
            redacted=json.dumps(hub.admin().call({'op':'config_get'}))
            assert all(token not in redacted for token in tokens)
        evidence.record('proxy-and-hub-diagnostics-redact-all-synthetic-bearer-values')
        image_ids={}
        for service in ['kafka','kafka-rest']:
            cid=subprocess.check_output(compose+['ps','-q',service],env=env,text=True).strip()
            image_ids[service]=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]['Image']
        evidence.value['image_config_digests']=image_ids
        evidence.value['jwks_fetches']=issuer.requests
        completed=True
    except BaseException as exc:
        evidence.finish(exc)
        raise
    finally:
        if hub:
            await hub.close()
        if http:
            http.close()
        with suppress(Exception):
            run(compose+['stop','kafka-rest'])
        with suppress(Exception):
            run(compose+['logs','--no-color'])
        with suppress(Exception):
            run(compose+['down','--volumes','--remove-orphans'])
        if issuer:
            issuer.close()
        log.close()
        if completed:
            try:
                # Include shutdown logs; no secret-redaction pass is granted
                # before the owned hub and proxy have actually stopped.
                output=(root/'services.log').read_bytes()
                if hub:
                    output+=(hub.root/'stdout.log').read_bytes()+(hub.root/'stderr.log').read_bytes()
                assert all(value.encode() not in output for value in secrets_to_check)
                for command in [['docker','ps','-aq'],['docker','network','ls','-q'],['docker','volume','ls','-q']]:
                    remain=subprocess.check_output(command+['--filter','label=com.docker.compose.project='+args.project],text=True).strip()
                    assert not remain,'Owned disposable resources were not fully cleaned'
                evidence.record('teardown-logs-redact-credentials-and-all-owned-containers-networks-volumes-are-removed')
            except BaseException as exc:
                evidence.finish(exc)
                raise
            evidence.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hub',type=Path)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--project',default='adhd-oauth-qualification')
    p.add_argument('--port',type=int,default=18087)
    asyncio.run(main(p.parse_args()))
