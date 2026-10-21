#!/usr/bin/env python3
"""Qualify an already staged accepted hub image on an isolated real platform.

No image is built or published here. Requires exact image config identity and the
current retained-source independent acceptance report. Creates only an owned
adhd-final-* Compose project or fresh Kubernetes namespace; removes owned data.
"""
import argparse
import asyncio
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

import httpx

from multi_support import Evidence, Fixture, MEMBERSHIPS, PROJECTS, poll_until, reject, scoped


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def main(args):
    repo=Path(__file__).resolve().parents[1]
    root=args.work.resolve()
    if root.exists() or not args.name.startswith('adhd-final-'):
        raise ValueError('Fresh work directory and owned adhd-final-* name required')
    root.mkdir(parents=True,mode=0o700)
    operations=(root/'operations.log').open('ab')
    evidence=Evidence(args.report,'adhd/accepted-kafka-platform@1')
    evidence.value.update(platform=args.platform,release_qualified=False,
        limitations=['One broker and one hub; no replicated availability qualification.',
                    'Baseline private network, no OAuth/SASL qualification in this probe.',
                    'Kubernetes CNI NetworkPolicy enforcement requires a separate enforcing-cluster gate.'])
    evidence.value['harness_dependencies_sha256']={name+'.py': hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest() for name in ['multi_support','foundation_acceptance','hub_acceptance']}
    env={**os.environ}; owned=False; fixture=forward=None
    image_check=None; completed=False
    context=args.context.resolve()
    manifest=json.loads((context/'manifest.json').read_text())
    acceptance=json.loads(args.acceptance_report.read_text())
    expected=manifest['files']['hub.exs']
    if acceptance.get('passed') is not True or acceptance.get('artifact_sha256')!=expected:
        raise ValueError('Independent passing acceptance must bind the staged artifact')
    def command(argv, *, data=None, capture=False, timeout=180):
        return subprocess.run(argv,input=data,env=env,stdout=subprocess.PIPE if capture else operations,
            stderr=operations,check=True,timeout=timeout).stdout
    compose=['docker','compose','-p',args.name,'-f',str(repo/'deploy/app.compose.yaml')]
    kubectl=[str(args.kubectl.resolve()),'--kubeconfig',str(args.kubeconfig.resolve())] if args.platform=='k8s' else None
    def k(argv,**kwargs):
        return command(kubectl+argv,**kwargs)
    def kn(argv,**kwargs):
        return k(['-n',args.name]+argv,**kwargs)
    def obj(argv):
        return json.loads(kn(argv+['-o','json'],capture=True))
    def identities():
        if args.platform=='compose':
            return {name:command(compose+['ps','-q',name],capture=True).decode().strip() for name in ['hub','kafka','kafka-rest']}
        return {name:obj(['get','pods','-l','app='+name])['items'][0]['metadata']['uid'] for name in ['hub','kafka','kafka-rest']}
    def group_offset(topic):
        argv=['kafka-consumer-groups','--bootstrap-server','localhost:9092','--describe','--group',topic+'.fanout']
        output=command(compose+['exec','-T','kafka']+argv,capture=True) if args.platform=='compose' else kn(['exec','kafka-0','--']+argv,capture=True)
        for line in output.decode().splitlines():
            fields=line.split()
            if len(fields)>=4 and fields[0]==topic+'.fanout' and fields[1]==topic and fields[2]=='0':
                return int(fields[3])
        raise AssertionError('Actual broker group checkpoint unavailable')
    def stop_forward():
        nonlocal forward
        if forward:
            forward.terminate()
            try: forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                forward.kill();forward.wait(timeout=5)
            forward=None
    async def ready():
        deadline=time.monotonic()+180
        async with httpx.AsyncClient() as http:
            while time.monotonic()<deadline:
                try:
                    if (await http.get(base+'/health',timeout=2)).status_code==200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.5)
        raise AssertionError('Full app readiness deadline exceeded')
    async def start_forward():
        nonlocal forward
        stop_forward()
        forward=subprocess.Popen(kubectl+['-n',args.name,'port-forward','service/hub',str(args.port)+':8766','--address','127.0.0.1'],stdout=operations,stderr=operations)
        await ready()
    try:
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',args.image):
            raise ValueError('--image must be exact local immutable image config ID')
        inspected=json.loads(command(['docker','image','inspect',args.image],capture=True))[0]
        assert inspected['Id']==args.image
        # Read the packaged image without starting generated application code.
        image_check=command(['docker','create',args.image],capture=True).decode().strip()
        command(['docker','cp',image_check+':/app',str(root/'image-app')])
        actual=json.loads((root/'image-app/manifest.json').read_text())
        assert actual==manifest
        for name,digest in manifest['files'].items():
            path=context/'Dockerfile' if name=='Dockerfile' else root/'image-app'/name
            assert path.is_file() and not path.is_symlink() and sha(path)==digest,name
        command(['docker','rm',image_check]);image_check=None
        evidence.value.update(artifact_sha256=expected,image_config_digest=args.image,
            acceptance_sha256=sha(args.acceptance_report),
            staging_sha256={name:sha(context/name) for name in ['manifest.json','payload.tar','Dockerfile']},
            input_sha256={str(path.relative_to(repo)):sha(path) for path in [Path(__file__),repo/'deploy/app.compose.yaml',repo/'deploy/events.compose.yaml',repo/'deploy/k8s/events.yaml',repo/'deploy/k8s/hub.yaml',repo/'deploy/init-config.py']})
        evidence.record('actual-image-payload-and-complete-specification-manifest-match-accepted-staging-inputs')
        config_dir=root/'config';data_dir=root/'data';data_dir.mkdir(mode=0o700)
        base='http://127.0.0.1:'+str(args.port)
        command(['python3',str(repo/'deploy/init-config.py'),str(config_dir),'--project-id','project-red','--public-url',base])
        config_file=config_dir/'hub.json';config=json.loads(config_file.read_text())
        tokens={name:secrets.token_urlsafe(32) for name in MEMBERSHIPS}
        config.update(projects=PROJECTS,agents=tokens,agent_projects=MEMBERSHIPS)
        config_file.write_text(json.dumps(config));config_file.chmod(0o600)
        if args.platform=='k8s':
            assert args.cluster_image and json.loads(command(['docker','image','inspect',args.cluster_image],capture=True))[0]['Id']==args.image
        if args.platform=='compose':
            existing=command(['docker','ps','-aq','--filter','label=com.docker.compose.project='+args.name],capture=True).strip()
            assert not existing,'Never adopt existing Compose resources'
            env.update(ADHD_HUB_IMAGE=args.image,ADHD_CONFIG_DIR=str(config_dir),ADHD_DATA_DIR=str(data_dir),
                ADHD_UID=str(os.getuid()),ADHD_GID=str(os.getgid()),ADHD_PORT=str(args.port))
            owned=True
            command(compose+['up','-d','--wait','--wait-timeout','180'],timeout=220)
        else:
            assert args.kubectl and args.kubeconfig
            namespaces=json.loads(k(['get','namespaces','-o','json'],capture=True))['items']
            assert all(row['metadata']['name']!=args.name for row in namespaces),'Never adopt an existing namespace'
            k(['create','namespace',args.name]);owned=True
            kn(['create','secret','generic','hub-seed','--from-file=hub.json='+str(config_file)])
            stage=root/'kustomize';stage.mkdir(mode=0o700)
            for name in ['events.yaml','hub.yaml']:
                (stage/name).write_bytes((repo/'deploy/k8s'/name).read_bytes())
            # The caller loads this exact config-ID image into the cluster first;
            # unique immutable-derived local name avoids a registry publication.
            if not args.cluster_image:
                raise ValueError('Kubernetes requires --cluster-image for the verified imported hub')
            images=[{'name':'adhd-hub','newName':args.cluster_image.split(':')[0], 'newTag':args.cluster_image.rsplit(':',1)[1]}]
            for name,image in [('confluentinc/cp-kafka',args.broker_image),('confluentinc/cp-kafka-rest',args.proxy_image)]:
                if '@sha256:' not in image: raise ValueError('Immutable broker/proxy digests required')
                new_name,digest=image.rsplit('@',1);images.append({'name':name,'newName':new_name,'digest':digest})
            (stage/'kustomization.yaml').write_text(json.dumps({'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization',
                'namespace':args.name,'resources':['events.yaml','hub.yaml'],'images':images}))
            rendered=k(['kustomize',str(stage)],capture=True)
            evidence.value['rendered_sha256']=hashlib.sha256(rendered).hexdigest()
            k(['apply','-f','-'],data=rendered)
            for resource in ['statefulset/kafka','deployment/kafka-rest','deployment/hub']:
                kn(['rollout','status',resource,'--timeout=180s'],timeout=210)
            await start_forward()
            pvcs=obj(['get','pvc'])['items']
            assert len(pvcs)==2 and all(row['status']['phase']=='Bound' for row in pvcs)
            volume_claims={row['metadata']['name']:row['metadata']['uid'] for row in pvcs}
            for row in pvcs:
                pv=json.loads(k(['get','pv',row['spec']['volumeName'],'-o','json'],capture=True))
                assert pv['spec']['persistentVolumeReclaimPolicy']=='Delete'
            command(kubectl+['-n',args.name,'cp','deployment/hub:/config/initial-admin-password.txt',str(config_dir/'initial-admin-password.txt')])
            command(kubectl+['-n',args.name,'cp','deployment/hub:/app/manifest.json',str(root/'running-manifest.json')])
            assert json.loads((root/'running-manifest.json').read_text())==manifest
            evidence.value['runtime_image_ids']={name:obj(['get','pods','-l','app='+name])['items'][0]['status']['containerStatuses'][0]['imageID'] for name in ['hub','kafka','kafka-rest']}
        await ready()
        password=re.search(r'^Password: (.+)$',(config_dir/'initial-admin-password.txt').read_text(),re.M)[1]
        credentials=root/'credentials.json';credentials.write_text(json.dumps({'agents':tokens,'admin':{'username':'admin','password':password}}));credentials.chmod(0o600)
        args.rest_url=base;args.credentials=credentials;args.with_model=False;args.keep_work=root/'client'
        fixture=Fixture(args);await fixture.start()
        admin=fixture.admin();a,b=await fixture.agent('red-a'),await fixture.agent('red-b')
        assert admin.call({'op':'config_get'})['config']['matcher'] is None
        await b.call(scoped('project-red','subscribe',mode='raw'))
        mid=secrets.token_hex(16)
        publication_command=scoped('project-red','publish',text='Final retained deployment durability '+mid,source={'kind':'slack','id':'qualification','item_id':mid})
        result=await a.call(publication_command,mid); original=result['publication']
        rows=await poll_until(b,'project-red',{original['id']},45)
        delivery=[row for row in rows if row.get('publication_id')==original['id']]
        assert len(delivery)==1
        assert (await a.call(scoped('project-red','search',query=original['text'])))['publications']==[original]
        assert admin.call({'op':'resource_status'})['lanes']['model']['grants']==0
        status=admin.call(scoped('project-red','eventing_status')); offset=status['next_offset']
        assert offset>=1 and group_offset(status['topic'])==offset
        before=identities()
        evidence.record('full-no-model-image-accepts-a2a-original-source-idempotency-and-durable-unacknowledged-delivery',broker_next_offset=offset)
        if args.platform=='compose':
            command(compose+['up','-d','--force-recreate','--no-deps','kafka','kafka-rest','hub'],timeout=180)
            command(compose+['up','-d','--wait','--wait-timeout','180'],timeout=220)
        else:
            stop_forward()
            kn(['delete','pod','kafka-0','--wait=true'],timeout=150)
            kn(['rollout','restart','deployment/kafka-rest','deployment/hub'])
            for resource in ['statefulset/kafka','deployment/kafka-rest','deployment/hub']:
                kn(['rollout','status',resource,'--timeout=180s'],timeout=210)
            await start_forward()
        await ready()
        after=identities();assert all(before[name]!=after[name] for name in before)
        if args.platform=='k8s':
            assert {row['metadata']['name']:row['metadata']['uid'] for row in obj(['get','pvc'])['items']}==volume_claims
        # Old HTTP connections may have closed during replacement; the public
        # fixture login is reestablished, preserving only durable credentials.
        await fixture.close();fixture=Fixture(args);await fixture.start()
        admin=fixture.admin();a,b=await fixture.agent('red-a'),await fixture.agent('red-b')
        assert admin.call({'op':'config_get'})['config']['server_id']==config['server_id']
        assert await a.call(publication_command,mid)==result
        assert (await a.call(scoped('project-red','get',publication_id=original['id'])))['publication']==original
        rows=await poll_until(b,'project-red',{original['id']},45)
        assert [row for row in rows if row.get('publication_id')==original['id']]==delivery
        assert (await a.call(scoped('project-red','search',query=original['text'])))['publications']==[original]
        assert admin.call({'op':'resource_status'})['lanes']['model']['grants']==0
        assert group_offset(status['topic'])==offset
        reject(await fixture.raw('blue-a',scoped('project-red','get',publication_id=original['id'])))
        await b.call(scoped('project-red','ack',delivery_ids=[delivery[0]['id']]))
        await b.call(scoped('project-red','ack',delivery_ids=[delivery[0]['id']]))
        assert not any(row.get('publication_id')==original['id'] for row in (await b.call(scoped('project-red','poll')))['deliveries'])
        new=(await a.call(scoped('project-red','publish',text='Final retained deployment new progress')))['publication']
        await poll_until(b,'project-red',{new['id']},45)
        final=admin.call(scoped('project-red','eventing_status'))['next_offset']
        assert final>offset and group_offset(status['topic'])==final
        evidence.record('hub-broker-proxy-replacements-preserve-server-original-retry-delivery-and-checkpoint-then-advance',before=offset,after=final)
        # Retain no raw IDs/tokens; input and output identities are digest-bound.
        evidence.value['replaced_resources']=list(before)
        completed=True
    except BaseException as error:
        evidence.finish(error);raise
    finally:
        if fixture: await fixture.close()
        stop_forward()
        if image_check:
            with suppress(Exception):command(['docker','rm',image_check])
        if owned:
            if args.platform=='compose':
                with suppress(Exception):command(compose+['logs','--no-color'])
                with suppress(Exception):command(compose+['down','--volumes','--remove-orphans'],timeout=180)
            else:
                for label in ['hub','kafka','kafka-rest']:
                    with suppress(Exception):kn(['logs','-l','app='+label,'--all-containers=true','--prefix=true'])
                with suppress(Exception):k(['delete','namespace',args.name,'--wait=true','--timeout=120s'],timeout=140)
        if completed:
            if args.platform=='compose':
                for kind in ['container','network','volume']:
                    argv=['docker','ps','-aq'] if kind=='container' else ['docker',kind,'ls','-q']
                    assert not command(argv+['--filter','label=com.docker.compose.project='+args.name],capture=True).strip()
            else:
                assert args.name not in [r['metadata']['name'] for r in json.loads(k(['get','namespaces','-o','json'],capture=True))['items']]
                deadline=time.monotonic()+30
                while True:
                    remaining=json.loads(k(['get','pv','-o','json'],capture=True))['items']
                    if all(row.get('spec',{}).get('claimRef',{}).get('namespace')!=args.name for row in remaining):
                        break
                    assert time.monotonic()<deadline
                    await asyncio.sleep(.3)
            logs=(root/'operations.log').read_bytes()
            assert all(value.encode() not in logs for value in list(tokens.values())+[password])
            evidence.record('owned-platform-services-and-durable-volumes-removed-with-redacted-logs')
            evidence.finish()
        operations.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform',choices=['compose','k8s'],required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--image',required=True,help='Local Docker image config ID sha256:...')
    p.add_argument('--context',type=Path,required=True)
    p.add_argument('--acceptance-report',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--port',type=int,default=18890)
    p.add_argument('--kubectl',type=Path)
    p.add_argument('--kubeconfig',type=Path)
    p.add_argument('--cluster-image',help='Unique immutable-derived local name for the previously loaded verified hub image')
    p.add_argument('--broker-image',default='confluentinc/cp-kafka@sha256:23b7aed3099df6c95e31e8c4bf3b20682e360edbf9867bc2eac978e32c89cf7f')
    p.add_argument('--proxy-image',default='confluentinc/cp-kafka-rest@sha256:85f286aa0b8b6cfc1977d81bdb9b5eb3ece4942563afd49862e14d5e92ac7058')
    asyncio.run(main(p.parse_args()))
