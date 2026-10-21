#!/usr/bin/env python3
"""Real optional Enterprise/trial TLS/OAuth Kubernetes rollout qualification.

Creates a fresh adhd-oauth-* namespace only. Requires a disposable cluster with
cached immutable broker/proxy images and dynamically provisioned Delete PVCs.
Private fixture material and raw logs remain under --work, never in the report.
"""
import argparse
import asyncio
from contextlib import suppress
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import time
from uuid import uuid4

from cryptography import x509
import httpx

from kafka_oauth_provider import Issuer, private
from multi_support import Evidence, Fixture, poll_until, scoped


async def main(args):
    repo = Path(__file__).resolve().parents[1]
    root = args.work.resolve()
    if root.exists() or not args.namespace.startswith('adhd-oauth-'):
        raise ValueError('Fresh private work directory and adhd-oauth-* namespace required')
    for image in (args.broker_image, args.proxy_image):
        if '@sha256:' not in image:
            raise ValueError('Use exact immutable image digests')
    root.mkdir(parents=True, mode=0o700)
    kubectl = [str(args.kubectl.resolve()), '--kubeconfig', str(args.kubeconfig.resolve())]
    log = (root / 'operations.log').open('ab')
    evidence = Evidence(args.report, 'adhd/kafka-kubernetes-native-oauth@1')
    evidence.value.update(lifecycle_qualified=False, production_entitlement_qualified=False,
        license_scope='Confluent Enterprise or documented permitted trial',
        limitations=['Diagnostic native hub; final retained image lifecycle is a separate gate.',
                    'Single broker, private plaintext proxy-to-broker lane; no SASL_SSL qualification.',
                    'NetworkPolicy enforcement is not qualified by this probe.'],
        requested_images={'kafka': args.broker_image, 'kafka-rest': args.proxy_image},
        artifact_sha256=hashlib.sha256(args.hub.read_bytes()).hexdigest(),
        input_sha256={str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__), repo/'tests/kafka_oauth_provider.py',
                         repo/'deploy/k8s/events.yaml', repo/'deploy/k8s/oauth.patch.yaml',
                         repo/'deploy/security/kafka-rest.oauth.properties.example']})
    evidence.value['harness_dependencies_sha256']={name+'.py': hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest() for name in ['multi_support','foundation_acceptance','hub_acceptance']}
    issuer = hub = http = forward = None
    owned = completed = False
    tokens = []
    sensitive = []
    def run(argv, *, data=None, capture=False, timeout=180):
        return subprocess.run(kubectl + argv, input=data, stdout=subprocess.PIPE if capture else log,
            stderr=log, timeout=timeout, check=True).stdout
    def obj(argv):
        return json.loads(run(argv + ['-o', 'json'], capture=True))
    def ns(argv):
        return ['-n', args.namespace] + argv
    def stop_forward():
        nonlocal forward
        if forward is not None:
            forward.terminate()
            try:
                forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                forward.kill(); forward.wait(timeout=5)
            forward = None
    async def start_forward():
        nonlocal forward
        stop_forward()
        forward = subprocess.Popen(kubectl + ns(['port-forward', 'service/kafka-rest',
            str(args.port)+':8082', '--address', '127.0.0.1']), stdout=log, stderr=log)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if forward.poll() is not None:
                raise AssertionError('Owned port-forward exited')
            try:
                if http.get(url+'/brokers', headers={'Authorization':'Bearer '+tokens[-1]}).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.2)
        raise AssertionError('Authenticated REST port-forward readiness failed')
    def pod(label):
        rows = obj(ns(['get','pods','-l','app='+label]))['items']
        rows = [row for row in rows if not row['metadata'].get('deletionTimestamp')]
        assert len(rows) == 1
        return rows[0]
    def secret():
        return obj(ns(['get','secret','adhd-kafka-oauth']))
    def update_secret():
        payload = run(ns(['create','secret','generic','adhd-kafka-oauth',
            '--from-file=kafka-rest.properties='+str(issuer.root/'kafka-rest.properties'),
            '--from-file=rest.p12='+str(issuer.root/'rest.p12'),
            '--from-file=issuer-trust.p12='+str(issuer.root/'issuer-trust.p12'),
            '--from-file=java-options='+str(issuer.root/'java-options'),
            '--dry-run=client','-o','json']),capture=True)
        run(['apply','-f','-'],data=payload)
    def properties():
        text=(repo/'deploy/security/kafka-rest.oauth.properties.example').read_text()
        text=text.replace('https://ISSUER/.well-known/jwks.json',issuer.issuer+'/jwks').replace('https://ISSUER',issuer.issuer)
        text=text.replace('ADHD_EVENT_SERVICE','adhd-event-service')
        text=text.replace('REPLACE_WITH_PRIVATE_KEYSTORE_PASSWORD',issuer.password).replace('REPLACE_WITH_PRIVATE_TRUSTSTORE_PASSWORD',issuer.password)
        private(issuer.root/'kafka-rest.properties',text.encode())
        private(issuer.root/'java-options',('-Dorg.apache.kafka.sasl.oauthbearer.allowed.urls='+issuer.issuer+'/jwks').encode())
    async def checkpoint(topic, token, expected):
        group=topic+'.fanout'; name='k8s-observer-'+uuid4().hex
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/vnd.kafka.v2+json','Accept':'application/vnd.kafka.v2+json'}
        response=http.post(url+'/consumers/'+group,headers=headers,json={'name':name,'format':'json','auto.commit.enable':'false'})
        assert response.status_code==200
        path='/consumers/'+group+'/instances/'+name
        try:
            assert http.post(url+path+'/assignments',headers=headers,json={'partitions':[{'topic':topic,'partition':0}]}).status_code==204
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                response=http.request('GET',url+path+'/offsets',headers=headers,json={'partitions':[{'topic':topic,'partition':0}]})
                assert response.status_code==200
                rows=response.json()['offsets']; value=rows[0]['offset'] if rows else -1
                if value>=expected:
                    return value
                await asyncio.sleep(.15)
            raise AssertionError('Broker checkpoint deadline exceeded')
        finally:
            assert http.delete(url+path,headers=headers).status_code==204
    try:
        existing=obj(['get','namespaces'])['items']
        if any(row['metadata']['name']==args.namespace for row in existing):
            raise ValueError('Never adopt an existing namespace')
        run(['create','namespace',args.namespace]); owned=True
        issuer=Issuer(root/'security',args.issuer_bind)
        issuer.java_truststore(); sensitive.append(issuer.password)
        properties(); update_secret()
        stage=root/'render'; stage.mkdir(mode=0o700)
        for name in ('events.yaml','oauth.patch.yaml'):
            (stage/name).write_bytes((repo/'deploy/k8s'/name).read_bytes())
        # The image override permits offline imported manifests, whose config/layer
        # equivalence must be recorded separately from original registry identities.
        images=[]
        for name, image in [('confluentinc/cp-kafka',args.broker_image),('confluentinc/cp-kafka-rest',args.proxy_image)]:
            new_name,digest=image.rsplit('@',1)
            images.append({'name':name,'newName':new_name,'digest':digest})
        (stage/'kustomization.yaml').write_text(json.dumps({'apiVersion':'kustomize.config.k8s.io/v1beta1',
            'kind':'Kustomization','namespace':args.namespace,'resources':['events.yaml'],
            'patches':[{'path':'oauth.patch.yaml'}],'images':images}))
        rendered=run(['kustomize',str(stage)],capture=True)
        evidence.value['rendered_sha256']=hashlib.sha256(rendered).hexdigest()
        private(root/'rendered.yaml',rendered)
        run(['apply','-f','-'],data=rendered)
        run(ns(['rollout','status','statefulset/kafka','--timeout=180s']),timeout=200)
        run(ns(['rollout','status','deployment/kafka-rest','--timeout=180s']),timeout=200)
        pvc=obj(ns(['get','pvc','data-kafka-0']))
        assert pvc['status']['phase']=='Bound'
        pv=obj(['get','pv',pvc['spec']['volumeName']])
        assert pv['spec']['persistentVolumeReclaimPolicy']=='Delete'
        evidence.value['persistent_volume_reclaim_policy']='Delete'
        evidence.value['runtime_image_ids']={name:pod(name)['status']['containerStatuses'][0]['imageID'] for name in ['kafka','kafka-rest']}
        first=issuer.token(exp=int(time.time())+900); second=issuer.token('second',exp=int(time.time())+900)
        tokens.extend([first,second])
        url='https://127.0.0.1:'+str(args.port)
        http=httpx.Client(verify=ssl.create_default_context(cafile=str(issuer.root/'ca.pem')),timeout=15)
        await start_forward()
        def get(token=None):
            return http.get(url+'/v3/clusters',headers={} if token is None else {'Authorization':'Bearer '+token})
        cluster=get(first).json()['data'][0]['cluster_id']
        assert get(None).status_code in (401,403)
        for token in ['invalid-bearer-value-00000000',issuer.token(exp=int(time.time())-3600),
                      issuer.token(aud='wrong-audience'),issuer.token(iss='https://wrong.invalid')]:
            tokens.append(token); assert get(token).status_code in (401,403)
        # Restore current valid token for subsequent port-forward readiness checks.
        tokens.append(second)
        evidence.record('live-secret-mounted-native-https-oauth-protects-real-kubernetes-broker')
        args.command=None; args.rest_url=None; args.credentials=None
        args.keep_work=root/'hub'; args.with_model=False; args.eventing_rest_url=url; args.deadline=45
        hub=Fixture(args)
        hub.config['eventing'].update(bearer_token=first,tls_ca_pem=issuer.ca_pem.decode())
        await hub.start()
        a,b=await hub.agent('red-a'),await hub.agent('red-b')
        admin=hub.admin(); pid=hub.process.pid
        await b.call(scoped('project-red','subscribe',mode='raw'))
        original=(await a.call(scoped('project-red','publish',text='Kubernetes secured cursor before Secret rotation')))['publication']
        rows=await poll_until(b,'project-red',{original['id']},45)
        await b.call(scoped('project-red','ack',delivery_ids=[rows[0]['id']]))
        status=admin.call(scoped('project-red','eventing_status')); before=status['next_offset']
        assert before>=1 and await checkpoint(status['topic'],first,before)==before
        admin.call({'op':'config_update','patch':{'eventing':{'bearer_token':second}}},mutation=True)
        current=admin.call({'op':'config_get'})['config']
        for patch in [{'tls_ca_pem':None},{'bearer_token':issuer.token(exp=int(time.time())-3600)}]:
            admin.call({'op':'config_update','patch':{'eventing':patch}},mutation=True,expected=409)
            assert admin.call({'op':'config_get'})['config']==current
        issuer.retire('first')
        deadline=time.monotonic()+30
        while get(first).status_code not in (401,403):
            assert time.monotonic()<deadline
            await asyncio.sleep(.2)
        evidence.record('hot-admin-token-rotation-and-retired-jwks-key-denial-preserve-hub-pid-and-committed-cursor',broker_next_offset=before)
        # Replace actual private PKCS12 credentials and TLS server certificate in
        # the Kubernetes Secret, then recreate REST pod to activate mounted data.
        old_secret=secret(); old_rest=pod('kafka-rest')['metadata']['uid']
        issuer.password=secrets.token_urlsafe(24); sensitive.append(issuer.password)
        private(issuer.root/'password.txt',issuer.password.encode())
        issuer.cert('rest',[x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('localhost'),x509.DNSName('kafka-rest')])
        (issuer.root/'issuer-trust.p12').unlink(); issuer.java_truststore()
        properties(); update_secret()
        new_secret=secret()
        assert new_secret['metadata']['uid']==old_secret['metadata']['uid']
        assert new_secret['metadata']['resourceVersion']!=old_secret['metadata']['resourceVersion']
        assert new_secret['data']['rest.p12']!=old_secret['data']['rest.p12']
        stop_forward()
        run(ns(['rollout','restart','deployment/kafka-rest']))
        run(ns(['rollout','status','deployment/kafka-rest','--timeout=180s']),timeout=200)
        assert pod('kafka-rest')['metadata']['uid']!=old_rest
        await start_forward()
        assert get(second).status_code==200 and get(first).status_code in (401,403)
        assert get(second).json()['data'][0]['cluster_id']==cluster
        assert await checkpoint(status['topic'],second,before)==before
        assert hub.process.pid==pid and hub.process.poll() is None
        evidence.record('live-secret-keystore-password-and-certificate-rotation-plus-rest-pod-replacement-preserve-data-and-cursor')
        old_broker=pod('kafka')['metadata']['uid']; old_pvc=pvc['metadata']['uid']
        run(ns(['delete','pod','kafka-0','--wait=true']),timeout=150)
        run(ns(['rollout','status','statefulset/kafka','--timeout=180s']),timeout=200)
        assert pod('kafka')['metadata']['uid']!=old_broker
        assert obj(ns(['get','pvc','data-kafka-0']))['metadata']['uid']==old_pvc
        deadline=time.monotonic()+40
        while True:
            try:
                assert get(second).status_code==200
                assert await checkpoint(status['topic'],second,before)==before
                break
            except (httpx.HTTPError,AssertionError):
                assert time.monotonic()<deadline
                await asyncio.sleep(.5)
        assert get(second).json()['data'][0]['cluster_id']==cluster
        assert (await a.call(scoped('project-red','get',publication_id=original['id'])))['publication']==original
        after=(await a.call(scoped('project-red','publish',text='Kubernetes secured cursor after both pod replacements')))['publication']
        rows=await poll_until(b,'project-red',{after['id']},45)
        assert all(row.get('publication_id')!=original['id'] for row in rows)
        end=admin.call(scoped('project-red','eventing_status'))['next_offset']
        assert end>before and await checkpoint(status['topic'],second,end)==end
        assert hub.process.pid==pid and hub.process.poll() is None
        evidence.record('broker-pod-replacement-retains-pvc-cluster-original-ack-and-group-checkpoint-with-new-a2a-progress',before=before,after=end)
        evidence.value['jwks_fetches']=issuer.requests
        completed=True
    except BaseException as error:
        evidence.finish(error)
        raise
    finally:
        if hub:
            await hub.close()
        if owned:
            for name in ('kafka','kafka-rest'):
                with suppress(Exception):
                    run(ns(['logs','-l','app='+name,'--all-containers=true','--prefix=true']))
            stop_forward()
            with suppress(Exception):
                run(['delete','namespace',args.namespace,'--wait=true','--timeout=120s'],timeout=140)
        if http:
            http.close()
        if issuer:
            issuer.close()
        if completed:
            try:
                remaining=obj(['get','namespaces'])['items']
                assert all(row['metadata']['name']!=args.namespace for row in remaining)
                deadline=time.monotonic()+30
                while True:
                    remaining=obj(['get','pv'])['items']
                    if all(row.get('spec',{}).get('claimRef',{}).get('namespace')!=args.namespace for row in remaining):
                        break
                    assert time.monotonic()<deadline
                    await asyncio.sleep(.3)
                logs=(root/'operations.log').read_bytes()
                if hub:
                    logs+=(hub.root/'stdout.log').read_bytes()+(hub.root/'stderr.log').read_bytes()
                assert all(value.encode() not in logs for value in tokens+sensitive+['-----BEGIN PRIVATE KEY-----'])
                evidence.record('owned-namespace-pvcs-pvs-and-forward-cleaned-and-runtime-logs-redact-all-credentials')
                evidence.finish()
            except BaseException as error:
                evidence.finish(error)
                raise
        log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kubectl',type=Path,required=True)
    p.add_argument('--kubeconfig',type=Path,required=True)
    p.add_argument('--namespace',default='adhd-oauth-k8s-qual')
    p.add_argument('--issuer-bind',required=True,help='Private host bridge address reachable by cluster pods')
    p.add_argument('--broker-image',required=True)
    p.add_argument('--proxy-image',required=True)
    p.add_argument('--hub',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--port',type=int,default=18887)
    asyncio.run(main(p.parse_args()))
