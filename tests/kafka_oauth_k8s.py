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
import re
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import time
from uuid import uuid4

from container_fixture import OwnedImage
from kafka_oauth_custody import KeytoolProbe, unpack_payload, cleanup_all, NamespaceLease, finish_primary_after_cleanup

from cryptography import x509
import httpx
import yaml

from kafka_oauth_provider import Issuer, private, PROXY_IMAGE
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
    artifact_sha=hashlib.sha256(args.hub.read_bytes()).hexdigest() if args.hub else None
    accepted_manifest=None
    if args.image:
        if not all([args.context,args.acceptance_report,args.cluster_image,args.kind_node]):
            raise ValueError('Image mode requires accepted context/report, loaded cluster image and explicit Kind node')
        accepted_manifest=json.loads((args.context/'manifest.json').read_text())
        acceptance=json.loads(args.acceptance_report.read_text())
        artifact_sha=accepted_manifest['files']['hub.exs']
        assert acceptance.get('passed') is True and acceptance.get('artifact_sha256')==artifact_sha
        assert json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]['Id']==args.image
        assert json.loads(subprocess.check_output(['docker','image','inspect',args.cluster_image]))[0]['Id']==args.image
        payload=OwnedImage(args.image,args.context/'manifest.json',root)
        payload.verify()
        unpack_payload(payload.probe('tar','-C','/app','-cf','-','.'),root/'image-app',accepted_manifest)
        assert json.loads((root/'image-app/manifest.json').read_text())==accepted_manifest
        for name,digest in accepted_manifest['files'].items():
            path=args.context/'Dockerfile' if name=='Dockerfile' else root/'image-app'/name
            assert path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest
        evidence.value['payload_probe_custody']=payload.probe_events
    evidence.value.update(lifecycle_qualified=False, release_qualified=False, production_entitlement_qualified=False,
        license_scope='Confluent Enterprise or documented permitted trial',
        limitations=['Actual admitted deployment image verified against staging and independent artifact acceptance; full release lifecycle remains a separate gate.' if args.image else 'Diagnostic native hub; final retained image lifecycle is a separate gate.',
                    'Single broker, private plaintext proxy-to-broker lane; no SASL_SSL qualification.',
                    'NetworkPolicy enforcement is not qualified by this probe.'],
        requested_images={'kafka': args.broker_image, 'kafka-rest': args.proxy_image},
        artifact_sha256=artifact_sha,image_config_digest=args.image,hub_runtime='accepted-container' if args.image else 'native-development',
        input_sha256={str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__), repo/'tests/kafka_oauth_provider.py',
                         repo/'deploy/k8s/events.yaml', repo/'deploy/k8s/oauth.patch.yaml',
                         repo/'deploy/security/kafka-rest.oauth.properties.example', repo/'deploy/kafka-bootstrap.py']})
    evidence.value['harness_dependencies_sha256']={name+'.py': hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest() for name in ['multi_support','foundation_acceptance','hub_acceptance']}
    issuer = hub = http = forward = hub_forward = None
    seed_fixture=None
    log_followers=[]
    owned = completed = False
    namespace_lease=NamespaceLease(args.namespace,uuid4().hex)
    primary = None
    keytool = None
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
                if http.get(url+'/brokers', headers={'Authorization':'Bearer '+second}).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.2)
        raise AssertionError('Authenticated REST port-forward readiness failed')
    def follow(resource):
        log_followers.append(subprocess.Popen(kubectl+ns(['logs','--follow',resource,'--all-containers=true','--prefix=true']),stdout=log,stderr=log))
    def pod(label):
        rows = obj(ns(['get','pods','-l','app='+label]))['items']
        rows = [row for row in rows if not row['metadata'].get('deletionTimestamp')]
        assert len(rows) == 1
        return rows[0]
    def hub_identity():
        if not args.image:
            assert hub.process.poll() is None
            return hub.process.pid
        current=pod('hub')
        status=current['status']['containerStatuses'][0]
        assert status['restartCount']==0 and 'running' in status['state']
        raw=run(ns(['exec','deployment/hub','--','cat','/proc/1/stat']),capture=True).decode()
        assert raw.split(' ',1)[0]=='1'
        started=raw.rsplit(')',1)[1].split()[19]
        return (current['metadata']['uid'],status['containerID'],started)

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
        namespace_document=namespace_lease.document();owned=True
        created=json.loads(run(['create','-f','-','-o','json'],data=json.dumps(namespace_document).encode(),capture=True))
        namespace_lease.observe(created)
        issuer=Issuer(root/'security',args.issuer_bind)
        keytool=KeytoolProbe(PROXY_IMAGE,issuer.root)
        issuer.java_truststore(probe=keytool); sensitive.append(issuer.password)
        properties(); update_secret()
        first=issuer.token(exp=int(time.time())+1200); second=issuer.token('second',exp=int(time.time())+1200)
        tokens.extend([first,second])
        if args.image:
            args.command=None;args.rest_url=None;args.credentials=None;args.keep_work=root/'hub';args.with_model=False
            args.eventing_rest_url='https://kafka-rest:8082';args.deadline=45
            seed_fixture=Fixture(argparse.Namespace(**{**vars(args), "image":None}))
            seed_fixture.config.update(host='0.0.0.0',port=8766,public_url='http://127.0.0.1:'+str(args.hub_port),store_path='/data/hub.dets',server_id=uuid4().hex)
            seed_fixture.config['eventing'].update(bearer_token=first,tls_ca_pem=issuer.ca_pem.decode())
            private(root/'hub-seed.json',json.dumps(seed_fixture.config).encode())
            run(ns(['create','secret','generic','hub-seed','--from-file=hub.json='+str(root/'hub-seed.json')]))
        stage=root/'render'; stage.mkdir(mode=0o700)
        for name in (['events.yaml','oauth.patch.yaml','hub.yaml'] if args.image else ['events.yaml','oauth.patch.yaml']):
            (stage/name).write_bytes((repo/'deploy/k8s'/name).read_bytes())
        # The image override permits offline imported manifests, whose config/layer
        # equivalence must be recorded separately from original registry identities.
        images=[]
        for name, image in [('confluentinc/cp-kafka',args.broker_image),('confluentinc/cp-kafka-rest',args.proxy_image)]:
            new_name,digest=image.rsplit('@',1)
            images.append({'name':name,'newName':new_name,'digest':digest})
        if args.image:
            images.append({'name':'adhd-hub','newName':args.cluster_image.rsplit(':',1)[0],'newTag':args.cluster_image.rsplit(':',1)[1]})
        shipped=list(yaml.safe_load_all((stage/'events.yaml').read_text()))
        bootstrap=next(row for row in shipped if row['kind']=='ConfigMap' and row['metadata']['name']=='kafka-bootstrap')
        assert bootstrap['data']['kafka-bootstrap.py'].encode()==(repo/'deploy/kafka-bootstrap.py').read_bytes()
        broker=next(row for row in shipped if row['kind']=='StatefulSet' and row['metadata']['name']=='kafka')
        assert next(v for v in broker['spec']['template']['spec']['volumes'] if v['name']=='bootstrap')['configMap']['name']=='kafka-bootstrap'
        (stage/'kustomization.yaml').write_text(json.dumps({'apiVersion':'kustomize.config.k8s.io/v1beta1',
            'kind':'Kustomization','namespace':args.namespace,'resources':['events.yaml','hub.yaml'] if args.image else ['events.yaml'],
            'patches':[{'path':'oauth.patch.yaml'}],'images':images}))
        rendered=run(['kustomize',str(stage)],capture=True)
        evidence.value['rendered_sha256']=hashlib.sha256(rendered).hexdigest()
        private(root/'rendered.yaml',rendered)
        run(['apply','-f','-'],data=rendered)
        run(ns(['rollout','status','statefulset/kafka','--timeout=180s']),timeout=200)
        run(ns(['rollout','status','deployment/kafka-rest','--timeout=180s']),timeout=200)
        follow('kafka-0');follow('deployment/kafka-rest')
        pvc=obj(ns(['get','pvc','data-kafka-0']))
        assert pvc['status']['phase']=='Bound'
        pv=obj(['get','pv',pvc['spec']['volumeName']])
        assert pv['spec']['persistentVolumeReclaimPolicy']=='Delete'
        evidence.value['persistent_volume_reclaim_policy']='Delete'
        evidence.value['runtime_image_ids']={name:pod(name)['status']['containerStatuses'][0]['imageID'] for name in ['kafka','kafka-rest']}
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
        if args.image:
            run(ns(['rollout','status','deployment/hub','--timeout=180s']),timeout=200)
            base='http://127.0.0.1:'+str(args.hub_port)
            hub_forward=subprocess.Popen(kubectl+ns(['port-forward','service/hub',str(args.hub_port)+':8766','--address','127.0.0.1']),stdout=log,stderr=log)
            deadline=time.monotonic()+30
            async with httpx.AsyncClient() as client:
                while time.monotonic()<deadline:
                    assert hub_forward.poll() is None
                    try:
                        if (await client.get(base+'/health',timeout=2)).status_code==200:break
                    except httpx.HTTPError:pass
                    await asyncio.sleep(.2)
                else:raise AssertionError('Accepted image readiness failed')
            run(ns(['cp',pod('hub')['metadata']['name']+':/config/initial-admin-password.txt',str(root/'initial-admin-password.txt')]))
            password=re.search(r'^Password: (.+)$',(root/'initial-admin-password.txt').read_text(),re.M)[1]
            private(root/'credentials.json',json.dumps({'agents':seed_fixture.tokens,'admin':{'username':'admin','password':password}}).encode())
            sensitive.extend(list(seed_fixture.tokens.values())+[password])
            args.rest_url=base;args.credentials=root/'credentials.json';args.keep_work=root/'client'
            args.initialize_projects=True
            hub=Fixture(argparse.Namespace(**{**vars(args), "image":None}));await hub.start()
            run(ns(['cp',pod('hub')['metadata']['name']+':/app/manifest.json',str(root/'running-manifest.json')]))
            assert json.loads((root/'running-manifest.json').read_text())==accepted_manifest
            image_id=pod('hub')['status']['containerStatuses'][0]['imageID']
            if '@' in image_id:
                actual=image_id.rsplit('@',1)[1]
                raw=subprocess.check_output(['docker','exec',args.kind_node,'ctr','-n','k8s.io','content','get',actual])
                assert 'sha256:'+hashlib.sha256(raw).hexdigest()==actual
                assert json.loads(raw)['config']['digest']==args.image
            else:
                observed=json.loads(subprocess.check_output(['docker','exec',args.kind_node,'crictl','inspecti',image_id]))
                assert image_id==observed['status']['id']==args.image
            evidence.value['runtime_image_ids']['hub']=image_id
            evidence.value['runtime_hub_image_config_digest']=args.image
            evidence.value['staging_manifest_sha256']=hashlib.sha256((args.context/'manifest.json').read_bytes()).hexdigest()
            evidence.value['acceptance_report_sha256']=hashlib.sha256(args.acceptance_report.read_bytes()).hexdigest()
            follow('deployment/hub')
            evidence.record('actual-kubernetes-hub-image-and-process-runtime-bind-accepted-artifact-and-complete-specification-manifest')
        else:
            args.command=None; args.rest_url=None; args.credentials=None
            args.keep_work=root/'hub'; args.with_model=False; args.eventing_rest_url=url; args.deadline=45
            hub=Fixture(argparse.Namespace(**{**vars(args), "image":None}))
            hub.config['eventing'].update(bearer_token=first,tls_ca_pem=issuer.ca_pem.decode())
            await hub.start()
        a,b=await hub.agent('red-a'),await hub.agent('red-b')
        admin=hub.admin(); pid=hub_identity()
        await b.call(scoped('project-red','subscribe',mode='raw'))
        original=(await a.call(scoped('project-red','publish',text='Kubernetes secured cursor before Secret rotation')))['publication']
        rows=await poll_until(b,'project-red',{original['id']},45)
        await b.call(scoped('project-red','ack',delivery_ids=[rows[0]['id']]))
        status=admin.call(scoped('project-red','eventing_status')); before=status['next_offset']
        assert before>=1 and await checkpoint(status['topic'],first,before)==before
        admin.call({'op':'config_update','patch':{'eventing':{'bearer_token':second}}},mutation=True)
        current=admin.call({'op':'config_get'})['config']
        expired=issuer.token(exp=int(time.time())-3600);tokens.append(expired)
        for patch in [{'tls_ca_pem':None},{'bearer_token':expired}]:
            admin.call({'op':'config_update','patch':{'eventing':patch}},mutation=True,expected=409)
            assert admin.call({'op':'config_get'})['config']==current
        issuer.retire('first')
        deadline=time.monotonic()+30
        while get(first).status_code not in (401,403):
            assert time.monotonic()<deadline
            await asyncio.sleep(.2)
        evidence.record('hot-admin-token-rotation-and-retired-jwks-key-denial-preserve-hub-pid-and-committed-cursor',broker_next_offset=before)
        current=admin.call({'op':'config_get'})['config']
        unrelated=Issuer(root/'wrong-root',args.issuer_bind)
        wrong_ca=unrelated.ca_pem.decode();unrelated.close()
        for patch,status_code in [({'tls_ca_pem':None},409),({'tls_ca_pem':wrong_ca},409),
            ({'tls_ca_pem':'not a CA certificate'},400),
            ({'tls_ca_pem':issuer.ca_pem.decode()+(issuer.root/'issuer-key.pem').read_text()},400)]:
            admin.call({'op':'config_update','patch':{'eventing':patch}},mutation=True,expected=status_code)
            assert admin.call({'op':'config_get'})['config']==current
            assert hub_identity()==pid
        evidence.record('runtime-postrotation-missing-wrong-malformed-and-private-key-ca-updates-fail-without-activation-or-hub-restart')
        # Replace actual private PKCS12 credentials and TLS server certificate in
        # the Kubernetes Secret, then recreate REST pod to activate mounted data.
        old_secret=secret(); old_rest=pod('kafka-rest')['metadata']['uid']
        issuer.password=secrets.token_urlsafe(24); sensitive.append(issuer.password)
        private(issuer.root/'password.txt',issuer.password.encode())
        issuer.cert('rest',[x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('localhost'),x509.DNSName('kafka-rest')])
        (issuer.root/'issuer-trust.p12').unlink(); issuer.java_truststore(probe=keytool)
        properties(); update_secret()
        new_secret=secret()
        assert new_secret['metadata']['uid']==old_secret['metadata']['uid']
        assert new_secret['metadata']['resourceVersion']!=old_secret['metadata']['resourceVersion']
        assert new_secret['data']['rest.p12']!=old_secret['data']['rest.p12']
        stop_forward()
        run(ns(['rollout','restart','deployment/kafka-rest']))
        run(ns(['rollout','status','deployment/kafka-rest','--timeout=180s']),timeout=200)
        assert pod('kafka-rest')['metadata']['uid']!=old_rest
        follow('deployment/kafka-rest')
        await start_forward()
        assert get(second).status_code==200 and get(first).status_code in (401,403)
        assert get(second).json()['data'][0]['cluster_id']==cluster
        assert await checkpoint(status['topic'],second,before)==before
        assert hub_identity()==pid
        evidence.record('live-secret-keystore-password-and-certificate-rotation-plus-rest-pod-replacement-preserve-data-and-cursor')
        old_broker=pod('kafka')['metadata']['uid']; old_pvc=pvc['metadata']['uid']
        run(ns(['delete','pod','kafka-0','--wait=true']),timeout=150)
        run(ns(['rollout','status','statefulset/kafka','--timeout=180s']),timeout=200)
        assert pod('kafka')['metadata']['uid']!=old_broker
        follow('kafka-0')
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
        assert hub_identity()==pid
        evidence.record('broker-pod-replacement-retains-pvc-cluster-original-ack-and-group-checkpoint-with-new-a2a-progress',before=before,after=end)
        evidence.value['jwks_fetches']=issuer.requests
        completed=True
    except BaseException as error:
        primary=error
        evidence.finish(error)
        raise
    finally:
        def stop_process(process):
            if process is not None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        def delete_namespace():
            if owned:
                for name in (['hub','kafka','kafka-rest'] if args.image else ['kafka','kafka-rest']):
                    with suppress(Exception):
                        run(ns(['logs','-l','app='+name,'--all-containers=true','--prefix=true']))
                namespace_lease.cleanup_deadline=time.monotonic()+120
                current=run(['get','namespace',args.namespace,'--ignore-not-found=true','-o','json'],capture=True)
                if current.strip():
                    deletion=namespace_lease.deletion(json.loads(current))
                    run(['delete','--raw','/api/v1/namespaces/'+args.namespace,'-f','-'],data=json.dumps(deletion).encode(),timeout=140)
        async def prove_namespace_absent():
            if owned:
                while True:
                    remaining=obj(['get','namespaces'])['items']
                    if all(row['metadata']['name']!=args.namespace for row in remaining):break
                    assert namespace_lease.cleanup_deadline is not None and time.monotonic()<namespace_lease.cleanup_deadline
                    await asyncio.sleep(.3)
                assert all(row['metadata']['name']!=args.namespace for row in remaining)
                deadline=time.monotonic()+30
                while True:
                    remaining=obj(['get','pv'])['items']
                    if all(row.get('spec',{}).get('claimRef',{}).get('namespace')!=args.namespace for row in remaining):
                        break
                    assert time.monotonic()<deadline
                    await asyncio.sleep(.3)
        steps=[('hub',lambda:hub.close() if hub else None),
            ('hub-forward',lambda:stop_process(hub_forward)),('rest-forward',stop_forward),
            ('namespace-delete',delete_namespace)]
        steps.extend(('log-follower-'+str(i),lambda process=process:stop_process(process)) for i,process in enumerate(log_followers))
        steps.extend([('http',lambda:http.close() if http else None),('issuer',lambda:issuer.close() if issuer else None),
            ('namespace-pv-absence',prove_namespace_absent)])
        outcomes,errors=await cleanup_all(steps)
        evidence.value['cleanup']=outcomes
        evidence.value['namespace_lease']=namespace_lease.evidence()
        if keytool is not None:
            evidence.value['keytool_probe_custody']=keytool.probe_events
            evidence.value['keytool_image_config_digest']=keytool.image_id
            if keytool.probe_cleanup_blocked:
                errors.append(AssertionError('Keytool probe cleanup remains unconfirmed'))
        try:
            if errors:
                if primary is not None:
                    primary.add_note('Independent OAuth fixture cleanup failures: '+','.join(type(e).__name__ for e in errors))
                    evidence.finish(primary)
                else:raise errors[0]
            finish_primary_after_cleanup(evidence,primary)
            if completed and not errors:
                logs=(root/'operations.log').read_bytes()
                if hub and not args.image:
                    logs+=(hub.root/'stdout.log').read_bytes()+(hub.root/'stderr.log').read_bytes()
                assert all(value.encode() not in logs for value in tokens+sensitive+['-----BEGIN PRIVATE KEY-----'])
                evidence.record('owned-namespace-pvcs-pvs-and-forward-cleaned-and-runtime-logs-redact-all-credentials')
                evidence.finish()
        except BaseException as error:
            evidence.finish(error)
            raise
        finally:log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kubectl',type=Path,required=True)
    p.add_argument('--kubeconfig',type=Path,required=True)
    p.add_argument('--namespace',default='adhd-oauth-k8s-qual')
    p.add_argument('--issuer-bind',required=True,help='Private host bridge address reachable by cluster pods')
    p.add_argument('--broker-image',required=True)
    p.add_argument('--proxy-image',required=True)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--hub',type=Path,help='Native diagnostic artifact')
    source.add_argument('--image',help='Actual accepted Docker image config ID')
    p.add_argument('--context',type=Path)
    p.add_argument('--acceptance-report',type=Path)
    p.add_argument('--cluster-image',help='Exact accepted image preloaded under unique immutable-derived tag')
    p.add_argument('--kind-node',help='Explicit owned Kind Docker node for read-only runtime image verification')
    p.add_argument('--hub-port',type=int,default=18930)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--port',type=int,default=18887)
    asyncio.run(main(p.parse_args()))
