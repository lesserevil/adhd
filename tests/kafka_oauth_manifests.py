#!/usr/bin/env python3
"""Read-only optional OAuth Compose and Kubernetes rendering checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml


def main(args):
    repo=Path(__file__).resolve().parents[1]
    args.work.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='oauth-render-',dir=args.work) as tmp:
        root=Path(tmp).resolve()
        for name in ('events.yaml','oauth.patch.yaml'):
            shutil.copyfile(repo/'deploy/k8s'/name,root/name)
        (root/'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources: [events.yaml]\npatches:\n- path: oauth.patch.yaml\n')
        raw=subprocess.check_output([str(args.kubectl.resolve()),'kustomize',str(root)])
        rows=list(yaml.safe_load_all(raw))
        d=next(x for x in rows if x['kind']=='Deployment' and x['metadata']['name']=='kafka-rest')
        c=d['spec']['template']['spec']['containers'][0]
        assert c['command']==['/usr/bin/kafka-rest-start','/run/adhd-security/kafka-rest.properties']
        assert c['readinessProbe']['tcpSocket']['port']==8082 and 'httpGet' not in c['readinessProbe']
        assert c['livenessProbe']['tcpSocket']['port']==8082
        assert any(x['name']=='kafka-oauth' and x['secret']['defaultMode']==0o440 for x in d['spec']['template']['spec']['volumes'])
        assert c['image']=='confluentinc/cp-kafka-rest@sha256:85f286aa0b8b6cfc1977d81bdb9b5eb3ece4942563afd49862e14d5e92ac7058'
        env={**os.environ,'ADHD_KAFKA_SECURITY_DIR':str(root/'private'),'ADHD_KAFKA_JWKS_URL':'https://issuer.example.invalid/jwks',
             'ADHD_KAFKA_OAUTH_ENTITLEMENT':'permitted-trial','ADHD_KAFKA_SECURITY_UID':'1000','ADHD_KAFKA_SECURITY_GID':'1000'}
        rendered=subprocess.check_output(['docker','compose','-f',str(repo/'deploy/events.compose.yaml'),
            '-f',str(repo/'deploy/events.oauth.compose.yaml'),'--profile','enterprise-oauth','config','--format','json'],env=env)
        compose=json.loads(rendered)
        c=compose['services']['kafka-rest']
        assert c['entrypoint']==['/usr/bin/kafka-rest-start','/run/adhd-security/kafka-rest.properties']
        assert c['environment']['KAFKA_REST_LISTENERS']=='https://0.0.0.0:8082'
        assert 'enterprise-oauth' in c['profiles'] and c['user']=='1000:1000'
        assert any(v['target']=='/run/adhd-security' and v['read_only'] for v in c['volumes'])
        assert not c.get('ports')
        inputs=['deploy/events.compose.yaml','deploy/events.oauth.compose.yaml','deploy/k8s/events.yaml','deploy/k8s/oauth.patch.yaml',
                'deploy/security/kafka-rest.oauth.properties.example','deploy/security/kafka-rest.broker-security.properties.example']
        props=(repo/inputs[-2]).read_text()
        assert 'listeners=https://0.0.0.0:8082' in props and 'listeners=http://' not in props
        assert '\nssl.endpoint.identification.algorithm=https\n' in props
        assert 'oauthbearer.expected.issuer=' in props and 'oauthbearer.expected.audience=' in props
        report={'schema':'adhd/oauth-deployment-rendering@1','passed':True,'scope':'Read-only manifest rendering; not Kubernetes runtime or production security qualification',
            'checks':['kubernetes-keeps-pin-private-secret-and-https-only-entrypoint','kubernetes-tcp-probes-do-not-bypass-authentication',
                      'compose-requires-explicit-enterprise-profile-and-private-identity-material','native-jwks-verifier-explicitly-checks-hostname-and-issuer-audience'],
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'input_sha256':{p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in inputs},
            'rendered_kubernetes_sha256':hashlib.sha256(raw).hexdigest(),
            'kubectl':json.loads(subprocess.check_output([str(args.kubectl.resolve()),'version','--client','-o','json']))['clientVersion']['gitVersion']}
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kubectl',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    main(p.parse_args())
