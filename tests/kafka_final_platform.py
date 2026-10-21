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
import tarfile
import time

import httpx

from multi_support import Evidence, Fixture, MEMBERSHIPS, PROJECTS, poll_until, reject, scoped


BROKER_OLD='confluentinc/cp-kafka@sha256:a94c13ba5e60501dbd82effb4df7056552e3a6c5d077c6b39adbec725f87a23e'
BROKER_NEW='confluentinc/cp-kafka@sha256:23b7aed3099df6c95e31e8c4bf3b20682e360edbf9867bc2eac978e32c89cf7f'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def main(args):
    repo=Path(__file__).resolve().parents[1]
    if args.broker_patch_upgrade and args.platform!='compose':
        raise ValueError('Broker patch upgrade is a Compose-only qualification')
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
    def group_offset(topic, expected):
        # Delivery materialization can precede the asynchronous broker commit.
        # Observe the actual checkpoint, bounded, instead of assuming simultaneity.
        argv=['kafka-consumer-groups','--bootstrap-server','localhost:9092','--describe','--group',topic+'.fanout']
        deadline=time.monotonic()+30
        while True:
            output=command(compose+['exec','-T','kafka']+argv,capture=True) if args.platform=='compose' else kn(['exec','kafka-0','--']+argv,capture=True)
            for line in output.decode().splitlines():
                fields=line.split()
                if len(fields)>=4 and fields[0]==topic+'.fanout' and fields[1]==topic and fields[2]=='0' and fields[3].isdigit():
                    observed=int(fields[3])
                    if observed>=expected:
                        return observed
            assert time.monotonic()<deadline,'Actual broker group checkpoint deadline exceeded'
            time.sleep(.3)
    def broker_end(topic):
        argv=['kafka-get-offsets','--bootstrap-server','localhost:9092','--topic',topic,'--time','-1']
        output=command(compose+['exec','-T','kafka']+argv,capture=True) if args.platform=='compose' else kn(['exec','kafka-0','--']+argv,capture=True)
        rows=[line.split(':') for line in output.decode().splitlines() if line.startswith(topic+':0:')]
        assert len(rows)==1
        return int(rows[0][2])
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
    async def offline():
        nonlocal fixture
        if fixture:
            await fixture.close();fixture=None
        stop_forward()
        if args.platform=='compose':
            for service in ['hub','kafka-rest','kafka']:
                command(compose+['stop',service],timeout=120)
            for service in ['hub','kafka-rest','kafka']:
                cid=command(compose+['ps','-aq',service],capture=True).decode().strip()
                assert not json.loads(command(['docker','inspect',cid],capture=True))[0]['State']['Running']
        else:
            for resource,label in [('deployment/hub','hub'),('deployment/kafka-rest','kafka-rest'),('statefulset/kafka','kafka')]:
                kn(['scale',resource,'--replicas=0'])
                kn(['wait','--for=delete','pod','-l','app='+label,'--timeout=120s'],timeout=140)
            assert not obj(['get','pods'])['items']

    async def online():
        if args.platform=='compose':
            command(compose+['up','-d','--wait','--wait-timeout','180'],timeout=220)
        else:
            for resource in ['statefulset/kafka','deployment/kafka-rest','deployment/hub']:
                kn(['scale',resource,'--replicas=1'])
                kn(['rollout','status',resource,'--timeout=180s'],timeout=210)
            await start_forward()
        await ready()

    def cold_transfer(restore=False):
        helper='cold-backup'
        if args.platform=='compose':
            cid=command(compose+['ps','-aq','kafka'],capture=True).decode().strip()
            mounts=json.loads(command(['docker','inspect',cid],capture=True))[0]['Mounts']
            kafka_volume=next(row['Name'] for row in mounts if row['Destination']=='/var/lib/kafka/data')
            argv=['docker','run','--rm','-i','--network','none','--read-only','--user','0:0',
                '--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER','--cap-add','FSETID',
                '--security-opt','no-new-privileges:true','--memory','256m','--cpus','1','--pids-limit','64',
                '--mount','type=bind,source='+str(config_dir)+',target=/hub/config',
                '--mount','type=bind,source='+str(data_dir)+',target=/hub/data',
                '--mount','type=volume,source='+kafka_volume+',target=/kafka',
                '--entrypoint','sh',args.image,'-ec']
        else:
            payload={'apiVersion':'v1','kind':'Pod','metadata':{'name':helper,'namespace':args.name},
                'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'enableServiceLinks':False,
                    'nodeSelector':{'kubernetes.io/arch':'amd64'},
                    'containers':[{'name':'copy','image':args.cluster_image,'imagePullPolicy':'IfNotPresent',
                        'command':['sh','-ec','sleep 3600'],
                        'securityContext':{'runAsUser':0,'runAsGroup':0,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,
                            'capabilities':{'drop':['ALL'],'add':['CHOWN','DAC_OVERRIDE','FOWNER','FSETID']}},
                        'resources':{'requests':{'cpu':'100m','memory':'64Mi'},'limits':{'cpu':'1','memory':'256Mi'}},
                        'volumeMounts':[{'name':'hub','mountPath':'/hub'},{'name':'kafka','mountPath':'/kafka'}]}],
                    'volumes':[{'name':'hub','persistentVolumeClaim':{'claimName':'hub-data'}},
                               {'name':'kafka','persistentVolumeClaim':{'claimName':'data-kafka-0'}}]}}
            k(['apply','-f','-'],data=json.dumps(payload).encode())
            kn(['wait','--for=condition=Ready','pod/'+helper,'--timeout=90s'],timeout=110)
            argv=kubectl+['-n',args.name,'exec','-i',helper,'--','sh','-ec']
        try:
            for name,target in [('hub-state.tgz','/hub'),('kafka-state.tgz','/kafka')]:
                path=root/name
                if restore:
                    # Archives are produced from this stopped fixture only;
                    # reject links/escaping paths before extracting as root.
                    with tarfile.open(path,'r:gz') as archive:
                        for member in archive:
                            assert member.isfile() or member.isdir()
                            assert not member.issym() and not member.islnk()
                            assert not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
                    clear_targets=['/hub/config','/hub/data'] if args.platform=='compose' and target=='/hub' else [target]
                    clear='; '.join('rm -rf '+directory+'/* '+directory+'/.[!.]* '+directory+'/..?*' for directory in clear_targets)
                    with path.open('rb') as stream:
                        subprocess.run(argv+[clear+'; exec tar -xzpf - -C '+target],stdin=stream,stdout=operations,
                            stderr=operations,env=env,timeout=240,check=True)
                else:
                    with path.open('xb') as stream:
                        path.chmod(0o600)
                        subprocess.run(argv+['exec tar -czpf - -C '+target+' .'],stdout=stream,
                            stderr=operations,env=env,timeout=240,check=True)
        finally:
            if args.platform=='k8s':
                kn(['delete','pod',helper,'--wait=true','--timeout=90s'],timeout=110)

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
        mode_report=root/'helper-mode-probe.json'
        command([sys.executable,str(repo/'tests/kafka_backup_modes.py'),'--image',args.image,'--work',str(root/'helper-mode-probe'),'--report',str(mode_report)],timeout=90)
        mode_result=json.loads(mode_report.read_text());assert mode_result['passed'] and mode_result['image_config_digest']==args.image
        evidence.value['offline_helper_mode_probe']={'passed':True,'report_sha256':sha(mode_report)}
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
            if args.broker_patch_upgrade:
                # Merge inside the include, before importing its resources. A
                # top-level override would conflict with Compose include rules.
                broker_override=root/'broker-upgrade.json'
                broker_override.write_text(json.dumps({'services':{'kafka':{'image':BROKER_OLD}}}))
                wrapper=root/'app-upgrade.yaml'
                original_compose=(repo/'deploy/app.compose.yaml').read_text()
                assert original_compose.startswith('include:\n  - events.compose.yaml\n')
                include='include: '+json.dumps([{'path':[str(repo/'deploy/events.compose.yaml'),str(broker_override)],'project_directory':str(repo/'deploy')}])
                wrapper.write_text(include+'\n'+original_compose.split('  - events.compose.yaml\n',1)[1])
                compose=['docker','compose','-p',args.name,'-f',str(wrapper)]
                upgrade_configs={pin:json.loads(command(['docker','image','inspect',pin],capture=True))[0]['Id'] for pin in [BROKER_OLD,BROKER_NEW]}
                assert upgrade_configs[BROKER_OLD]!=upgrade_configs[BROKER_NEW]
                rendered=json.loads(command(compose+['config','--format','json'],capture=True))
                assert rendered['services']['kafka']['image']==BROKER_OLD
                evidence.value['broker_upgrade_inputs']={'from':BROKER_OLD,'to':BROKER_NEW,'image_configs':upgrade_configs,'wrapper_sha256':sha(wrapper),'initial_override_sha256':sha(broker_override)}
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
            command(kubectl+['-n',args.name,'cp',obj(['get','pods','-l','app=hub'])['items'][0]['metadata']['name']+':/config/initial-admin-password.txt',str(config_dir/'initial-admin-password.txt')])
            command(kubectl+['-n',args.name,'cp',obj(['get','pods','-l','app=hub'])['items'][0]['metadata']['name']+':/app/manifest.json',str(root/'running-manifest.json')])
            assert json.loads((root/'running-manifest.json').read_text())==manifest
            evidence.value['runtime_image_ids']={name:obj(['get','pods','-l','app='+name])['items'][0]['status']['containerStatuses'][0]['imageID'] for name in ['hub','kafka','kafka-rest']}
            if not args.kind_node:
                raise ValueError('Kind qualification requires explicit --kind-node for immutable runtime-image verification')
            runtime_id=evidence.value['runtime_image_ids']['hub']
            if '@' in runtime_id:
                runtime_digest=runtime_id.rsplit('@',1)[1]
                manifest_bytes=command(['docker','exec',args.kind_node,'ctr','-n','k8s.io','content','get',runtime_digest],capture=True)
                assert 'sha256:'+hashlib.sha256(manifest_bytes).hexdigest()==runtime_digest
                runtime_config=json.loads(manifest_bytes)['config']['digest']
            else:
                # Imported Docker images may expose the config identity directly.
                runtime_config=runtime_id
                observed=json.loads(command(['docker','exec',args.kind_node,'crictl','inspecti',runtime_id],capture=True))
                assert observed['status']['id']==runtime_config
            assert runtime_config==args.image
            evidence.value['runtime_hub_image_config_digest']=runtime_config
        await ready()
        password=re.search(r'^Password: (.+)$',(config_dir/'initial-admin-password.txt').read_text(),re.M)[1]
        credentials=root/'credentials.json';credentials.write_text(json.dumps({'agents':tokens,'admin':{'username':'admin','password':password}}));credentials.chmod(0o600)
        args.rest_url=base;args.credentials=credentials;args.with_model=False;args.keep_work=root/'client'
        fixture=Fixture(argparse.Namespace(**{**vars(args), "image":None}));await fixture.start()
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
        assert offset>=1 and group_offset(status['topic'],offset)==offset
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
        await fixture.close();fixture=Fixture(argparse.Namespace(**{**vars(args), "image":None}));await fixture.start()
        admin=fixture.admin();a,b=await fixture.agent('red-a'),await fixture.agent('red-b')
        assert admin.call({'op':'config_get'})['config']['server_id']==config['server_id']
        assert await a.call(publication_command,mid)==result
        assert (await a.call(scoped('project-red','get',publication_id=original['id'])))['publication']==original
        rows=await poll_until(b,'project-red',{original['id']},45)
        assert [row for row in rows if row.get('publication_id')==original['id']]==delivery
        assert (await a.call(scoped('project-red','search',query=original['text'])))['publications']==[original]
        assert admin.call({'op':'resource_status'})['lanes']['model']['grants']==0
        assert group_offset(status['topic'],offset)==offset
        reject(await fixture.raw('blue-a',scoped('project-red','get',publication_id=original['id'])))
        await b.call(scoped('project-red','ack',delivery_ids=[delivery[0]['id']]))
        await b.call(scoped('project-red','ack',delivery_ids=[delivery[0]['id']]))
        assert not any(row.get('publication_id')==original['id'] for row in (await b.call(scoped('project-red','poll')))['deliveries'])
        new=(await a.call(scoped('project-red','publish',text='Final retained deployment new progress')))['publication']
        await poll_until(b,'project-red',{new['id']},45)
        final=admin.call(scoped('project-red','eventing_status'))['next_offset']
        assert final>offset and group_offset(status['topic'],final)==final
        evidence.record('hub-broker-proxy-replacements-preserve-server-original-retry-delivery-and-checkpoint-then-advance',before=offset,after=final)
        if args.broker_patch_upgrade:
            upgrade_before=identities()
            broker_before=json.loads(command(['docker','inspect',upgrade_before['kafka']],capture=True))[0]
            volume_before=next(row['Name'] for row in broker_before['Mounts'] if row['Destination']=='/var/lib/kafka/data')
            assert broker_before['Image']==upgrade_configs[BROKER_OLD]
            pending_before=[row for row in (await b.call(scoped('project-red','poll')))['deliveries'] if row.get('publication_id')==new['id']]
            assert len(pending_before)==1
            command(compose+['stop','kafka'],timeout=120)
            stopped=json.loads(command(['docker','inspect',upgrade_before['kafka']],capture=True))[0]
            assert not stopped['State']['Running']
            async with httpx.AsyncClient() as http:
                assert (await http.get(base+'/health',timeout=3)).status_code==200
            outage=(await a.call(scoped('project-red','publish',text='Accepted while actual broker is stopped')))['publication']
            assert (await a.call(scoped('project-red','get',publication_id=outage['id'])))['publication']==outage
            assert not any(row.get('publication_id')==outage['id'] for row in (await b.call(scoped('project-red','poll')))['deliveries'])
            broker_override.write_text(json.dumps({'services':{'kafka':{'image':BROKER_NEW}}}))
            command(compose+['up','-d','--no-deps','--wait','--wait-timeout','180','kafka'],timeout=220)
            upgrade_after=identities()
            broker_after=json.loads(command(['docker','inspect',upgrade_after['kafka']],capture=True))[0]
            assert broker_after['Image']==upgrade_configs[BROKER_NEW]
            assert next(row['Name'] for row in broker_after['Mounts'] if row['Destination']=='/var/lib/kafka/data')==volume_before
            assert all(upgrade_before[name]==upgrade_after[name] for name in ['hub','kafka-rest'])
            rows=await poll_until(b,'project-red',{new['id'],outage['id']},60)
            assert [row for row in rows if row.get('publication_id')==new['id']]==pending_before
            assert len([row for row in rows if row.get('publication_id')==outage['id']])==1
            assert not any(row.get('publication_id')==original['id'] for row in rows)
            assert await a.call(publication_command,mid)==result
            assert (await a.call(scoped('project-red','get',publication_id=original['id'])))['publication']==original
            assert admin.call({'op':'resource_status'})['lanes']['model']['grants']==0
            upgraded_offset=admin.call(scoped('project-red','eventing_status'))['next_offset']
            assert upgraded_offset>final and group_offset(status['topic'],upgraded_offset)==upgraded_offset
            evidence.record('real-8.3.1-to-8.3.2-same-volume-broker-upgrade-preserves-a2a-originals-acks-unacked-identities-and-cursor-with-outage-acceptance',before=final,after=upgraded_offset,volume=volume_before,hub_and_proxy_unrestarted=True,override_sha256=sha(broker_override))
            final=upgraded_offset
        blue_a,blue_b=await fixture.agent('blue-a'),await fixture.agent('blue-b')
        await blue_b.call(scoped('project-blue','subscribe',mode='raw'))
        blue=(await blue_a.call(scoped('project-blue','publish',text='Cold recovery second project fact')))['publication']
        blue_rows=await poll_until(blue_b,'project-blue',{blue['id']},45)
        blue_status=admin.call(scoped('project-blue','eventing_status'))
        blue_offset=blue_status['next_offset']
        assert blue_offset>=1 and group_offset(blue_status['topic'],blue_offset)==blue_offset
        config_before_backup=admin.call({'op':'config_get'})['config']
        red_rows=[row for row in (await b.call(scoped('project-red','poll')))['deliveries'] if row.get('publication_id')==new['id']]
        assert len(red_rows)==1
        assert broker_end(status['topic'])==final and broker_end(blue_status['topic'])==blue_offset
        await offline()
        cold_transfer()
        archives={name:sha(root/name) for name in ['hub-state.tgz','kafka-state.tgz']}
        recovery={'schema':'adhd/private-cold-recovery-set@1','image_config_digest':args.image,'artifact_sha256':expected,
            'server_id':config['server_id'],'project_ids':[row['id'] for row in config['projects']],
            'configuration_revision':config_before_backup['config_revision'],'archives_sha256':archives,
            'project_next_offsets':{'project-red':final,'project-blue':blue_offset}}
        recovery_file=root/'recovery-set.json';recovery_file.write_text(json.dumps(recovery,indent=2)+'\n');recovery_file.chmod(0o600)
        evidence.record('consistent-offline-config-all-project-stores-and-kafka-recovery-set-created',archives_sha256=archives,recovery_manifest_sha256=sha(recovery_file))
        await online()
        fixture=Fixture(argparse.Namespace(**{**vars(args), "image":None}));await fixture.start()
        admin=fixture.admin();a,b=await fixture.agent('red-a'),await fixture.agent('red-b')
        sentinel=(await a.call(scoped('project-red','publish',text='Intentional post-backup rollback sentinel')))['publication']
        await poll_until(b,'project-red',{sentinel['id']},45)
        assert admin.call(scoped('project-red','eventing_status'))['next_offset']>final
        different=512 if config_before_backup['resources']['max_waiters']!=512 else 513
        admin.call({'op':'config_update','patch':{'resources':{'max_waiters':different}}},mutation=True)
        await offline()
        assert all(sha(root/name)==value for name,value in archives.items())
        cold_transfer(restore=True)
        await online()
        fixture=Fixture(argparse.Namespace(**{**vars(args), "image":None}));await fixture.start()
        admin=fixture.admin();a,b=await fixture.agent('red-a'),await fixture.agent('red-b')
        blue_a,blue_b=await fixture.agent('blue-a'),await fixture.agent('blue-b')
        restored=admin.call({'op':'config_get'})['config']
        assert restored==config_before_backup
        assert await a.call(publication_command,mid)==result
        assert (await a.call(scoped('project-red','get',publication_id=original['id'])))['publication']==original
        assert (await blue_a.call(scoped('project-blue','get',publication_id=blue['id'])))['publication']==blue
        assert (await a.call(scoped('project-red','search',query=original['text'])))['publications']==[original]
        red_restored=(await b.call(scoped('project-red','poll')))['deliveries']
        assert not any(row.get('publication_id')==original['id'] for row in red_restored)
        assert [row for row in red_restored if row.get('publication_id')==new['id']]==red_rows
        assert (await blue_b.call(scoped('project-blue','poll')))['deliveries']==blue_rows
        reject(await fixture.raw('red-a',scoped('project-blue','get',publication_id=blue['id'])))
        reject(await fixture.raw('blue-a',scoped('project-red','get',publication_id=original['id'])))
        response=await fixture.raw('red-a',scoped('project-red','get',publication_id=sentinel['id']))
        reject(response,code='NOT_FOUND')
        assert admin.call(scoped('project-red','eventing_status'))['next_offset']==final
        assert admin.call(scoped('project-blue','eventing_status'))['next_offset']==blue_offset
        assert group_offset(status['topic'],final)==final and group_offset(blue_status['topic'],blue_offset)==blue_offset
        assert broker_end(status['topic'])==final and broker_end(blue_status['topic'])==blue_offset
        after_restore=(await a.call(scoped('project-red','publish',text='Actual restored image advances from recovery point')))['publication']
        await poll_until(b,'project-red',{after_restore['id']},45)
        assert admin.call(scoped('project-red','eventing_status'))['next_offset']>final
        evidence.record('actual-cold-restore-recovers-both-projects-config-credentials-acks-delivery-identities-and-broker-cursors-then-advances',red_offset=final,blue_offset=blue_offset,intentional_postbackup_sentinel_absent=True)
        if args.model_url:
            if args.model_window_file:
                (root/'waiting-model-window').touch(mode=0o600)
                deadline=time.monotonic()+1800
                while not args.model_window_file.is_file():
                    assert time.monotonic()<deadline,'Exclusive live-model window not granted within30minutes'
                    await asyncio.sleep(1)
            if not args.gateway_report or not args.gateway_report.is_file():
                raise ValueError('Optional live model qualification requires the owned bounded gateway report')
            child_path=root/'optional-model.json'
            command([sys.executable,str(repo/'tests/kafka_platform_model.py'),'--rest-url',base,
                '--credentials',str(credentials),'--model-url',args.model_url,
                '--gateway-report',str(args.gateway_report.resolve()),'--with-backend-queries',
                '--report',str(child_path)],timeout=240)
            child=json.loads(child_path.read_text())
            assert child['passed'] and child['backend_query']['positive_original_cited']
            assert child['hot_model_enable_and_disable'] and child['model_free_second_project_zero_inference']
            assert child['artifact_sha256'] is None  # External child has no artifact authority.
            gateway_snapshot=args.gateway_report.read_bytes()
            assert hashlib.sha256(gateway_snapshot).hexdigest()==child['gateway_report_sha256']
            (root/'optional-model-gateway.json').write_bytes(gateway_snapshot)
            (root/'optional-model-gateway.json').chmod(0o600)
            assert admin.call({'op':'config_get'})['config']['matcher'] is None
            evidence.value['optional_model']={'passed':True,'report_sha256':sha(child_path),
                'harness_sha256':sha(repo/'tests/kafka_platform_model.py'),
                'gateway_harness_sha256':sha(repo/'tests/kafka_platform_gateway.py'),
                'gateway_report_sha256':child['gateway_report_sha256'],
                'artifact_sha256':expected,'image_config_digest':args.image,
                'binding':'Parent verifies the owned deployment image and supplies its private credentials; child external artifact field is deliberately null.'}
            evidence.record('actual-accepted-image-hot-model-enable-filter-match-nonmatch-semantic-history-citations-independent-blue-raw-and-disable')
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
    p.add_argument('--model-url',help='Optional live short-response endpoint reachable by this deployed hub')
    p.add_argument('--model-window-file',type=Path,help='Optional owned coordination file; wait at most30minutes before live model child')
    p.add_argument('--gateway-report',type=Path,help='Private report from the bounded owned model relay')
    p.add_argument('--kind-node',help='Explicit owned Kind Docker node for read-only runtime config identity verification')
    p.add_argument('--cluster-image',help='Unique immutable-derived local name for the previously loaded verified hub image')
    p.add_argument('--broker-patch-upgrade',action='store_true',help='Compose: start pinned8.3.1 then qualify actual8.3.2 rollout on same volume')
    p.add_argument('--broker-image',default='confluentinc/cp-kafka@sha256:23b7aed3099df6c95e31e8c4bf3b20682e360edbf9867bc2eac978e32c89cf7f')
    p.add_argument('--proxy-image',default='confluentinc/cp-kafka-rest@sha256:85f286aa0b8b6cfc1977d81bdb9b5eb3ece4942563afd49862e14d5e92ac7058')
    asyncio.run(main(p.parse_args()))
