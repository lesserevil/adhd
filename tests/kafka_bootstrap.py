#!/usr/bin/env python3
"""Independent broker identity, exact ConfigMap mirror, and real fresh-volume probes.

Never adopts existing Compose projects. Run in the existing pinned test env.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import time

import httpx
import yaml

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'deploy/kafka-bootstrap.py'
LOADER=importlib.util.spec_from_file_location('broker_bootstrap',SOURCE)
BOOT=importlib.util.module_from_spec(LOADER);LOADER.loader.exec_module(BOOT)
LEGACY='MkU3OEVBNTcwNTJENDM2Qk'
OTHER='q1Sh9ISiazwGINzRvyQ999'


def main(args):
    root=args.work.resolve()
    if root.exists():raise ValueError('Fresh private work directory required')
    root.mkdir(parents=True,mode=0o700)
    report={'suite':'adhd/kafka-durable-installation-identity@1','passed':False,'checks':[],
        'lifecycle_qualified':False,'limits':['Single broker Compose identity qualification; no new hub runtime claim.'],
        'inputs_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),SOURCE,ROOT/'deploy/events.compose.yaml',ROOT/'deploy/k8s/events.yaml']}}
    def record(name,**values):
        report['checks'].append({'name':name,'passed':True,**values})
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    local=root/'local';local.mkdir()
    def fixture(name):
        directory=local/name;directory.mkdir();return directory
    def select(directory,**overrides):
        env={'KAFKA_NODE_ID':'1','CLUSTER_ID':LEGACY,**overrides}
        selected,lock=BOOT.identity(directory,env);os.close(lock);return selected
    def denied(directory,**overrides):
        try:select(directory,**overrides)
        except (ValueError,OSError,UnicodeError):return
        raise AssertionError('Invalid identity input was admitted')
    rows=list(yaml.safe_load_all((ROOT/'deploy/k8s/events.yaml').read_text()))
    config=next(row for row in rows if row['kind']=='ConfigMap' and row['metadata']['name']=='kafka-bootstrap')
    assert config['data']['kafka-bootstrap.py'].encode()==SOURCE.read_bytes()
    kafka=next(row for row in rows if row['kind']=='StatefulSet')
    container=kafka['spec']['template']['spec']['containers'][0]
    assert container['command']==['/usr/bin/python3','/opt/adhd/kafka-bootstrap.py']
    assert not any(e['name']=='CLUSTER_ID' for e in container['env'])
    record('kubernetes-configmap-exactly-mirrors-readonly-bootstrap-and-no-shared-cluster-id')
    d=fixture('resume');assert select(d)==LEGACY;assert select(d)==LEGACY
    assert stat.S_IMODE((d/BOOT.SEED).stat().st_mode)==0o600
    denied(d,CLUSTER_ID=OTHER)
    record('exclusive-private-seed-resumes-and-explicit-mismatch-fails')
    d=fixture('old-metadata');logs=d/'logs';logs.mkdir()
    meta=logs/'meta.properties';raw=('version=1\nnode.id=1\ncluster.id='+LEGACY+'\n').encode();meta.write_bytes(raw)
    assert select(d,CLUSTER_ID='')==LEGACY and meta.read_bytes()==raw
    denied(d,CLUSTER_ID=OTHER)
    record('existing-legacy-metadata-adopted-without-rewrite-and-conflicting-explicit-id-rejected')
    d=fixture('seed-meta-conflict');(d/BOOT.SEED).write_text(OTHER+'\n');(d/'logs').mkdir();(d/'logs/meta.properties').write_bytes(raw)
    denied(d)
    d=fixture('bad-node');(d/'logs').mkdir();(d/'logs/meta.properties').write_bytes(raw.replace(b'node.id=1',b'node.id=2'));denied(d)
    record('seed-metadata-and-node-identity-mismatches-rejected')
    for name in ['symlink-seed','symlink-meta','symlink-dir','traversal','unidentified-data','duplicate-meta']:
        d=fixture(name)
        if name=='symlink-seed':(d/BOOT.SEED).symlink_to(meta)
        elif name=='symlink-meta':(d/'logs').mkdir();(d/'logs/meta.properties').symlink_to(meta)
        elif name=='symlink-dir':(d/'logs').symlink_to(logs,target_is_directory=True)
        elif name=='traversal':denied(d,KAFKA_LOG_DIRS=str(d/'logs/../../outside'));continue
        elif name=='unidentified-data':(d/'logs').mkdir();(d/'logs/record').write_bytes(b'not an empty volume')
        else:(d/'logs').mkdir();(d/'logs/meta.properties').write_bytes(raw+b'cluster.id='+OTHER.encode()+b'\n')
        denied(d)
    record('symlink-seed-meta-directories-traversal-unidentified-data-and-duplicate-metadata-fail-closed')
    if args.local_only:
        report['passed']=True;args.report.write_text(json.dumps(report,indent=2)+'\n');return
    log=(root/'services.log').open('ab');projects=[]
    def command(argv,env=None,capture=False,check=True):
        return subprocess.run(argv,env=env,stdout=subprocess.PIPE if capture else log,stderr=log,timeout=200,check=check)
    try:
        cluster_ids=[]
        for index in range(3):
            name=args.project+'-'+str(index)
            if not name.startswith('adhd-bootstrap-'):raise ValueError('Dedicated adhd-bootstrap-* project required')
            assert not subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project='+name]).strip()
            env={**os.environ,'ADHD_KAFKA_TEST_PORT':str(args.port+index)}
            compose=['docker','compose','-p',name,'-f',str(ROOT/'deploy/events.compose.yaml'),'-f',str(ROOT/'deploy/events.test.compose.yaml')]
            projects.append((compose,env,name))
            initial=compose
            if index==2:
                old=root/'legacy.compose.json';old.write_text(json.dumps({'services':{'kafka':{'entrypoint':['/etc/confluent/docker/run'],'environment':{'CLUSTER_ID':LEGACY}}}}))
                initial=compose+['-f',str(old)]
            command(initial+['up','-d','--wait','--wait-timeout','150'],env)
            url='http://127.0.0.1:'+str(args.port+index)
            with httpx.Client(timeout=10) as http:
                cid=http.get(url+'/v3/clusters').json()['data'][0]['cluster_id']
            if index<2:cluster_ids.append(cid)
            else:assert cid==LEGACY
            topic='adhd.bootstrap.identity.fixture'
            with httpx.Client(timeout=10) as http:
                response=http.post(url+'/v3/clusters/'+cid+'/topics',json={'topic_name':topic,'partitions_count':1,'replication_factor':1})
                assert response.status_code in (200,201)
                response=http.post(url+'/topics/'+topic,headers={'Content-Type':'application/vnd.kafka.json.v2+json','Accept':'application/vnd.kafka.v2+json'},json={'records':[{'key':'identity','value':{'fixture':'preserved through identity adoption'}}]})
                assert response.status_code==200 and response.json()['offsets'][0]['error_code'] in (0,None)
            if index<2:
                seed=command(compose+['exec','-T','kafka','cat','/var/lib/kafka/data/'+BOOT.SEED],env,capture=True).stdout.decode().strip()
                assert seed==cid and len(cid)==22
            command(compose+['stop','kafka-rest','kafka'],env)
            # A new process against an existing volume must reject a different
            # explicit assertion before reaching Confluent formatting/startup.
            wrong=OTHER if cid!=OTHER else LEGACY
            log.flush();position=log.tell()
            rejected=command(compose+['run','--rm','--no-deps','-e','CLUSTER_ID='+wrong,'kafka','--identity-only'],env,capture=True,check=False)
            log.flush()
            assert rejected.returncode!=0 and b'cluster identity mismatch' in (root/'services.log').read_bytes()[position:]
            # Simulate adoption of an installation created before this seed was
            # introduced: only remove our seed, never Kafka's identity metadata.
            if index<2:
                command(compose+['run','--rm','--no-deps','--entrypoint','/usr/bin/python3','kafka','-c',
                    'import os; os.unlink("/var/lib/kafka/data/.adhd-cluster-id")'],env)
            adopted=command(compose+['run','--rm','--no-deps','kafka','--identity-only'],env,capture=True).stdout.decode().strip()
            assert adopted==cid
            command(compose+['up','-d','--wait','--wait-timeout','150'],env)
            with httpx.Client(timeout=10) as http:
                assert http.get(url+'/v3/clusters').json()['data'][0]['cluster_id']==cid
                headers={'Content-Type':'application/vnd.kafka.v2+json','Accept':'application/vnd.kafka.v2+json'}
                response=http.post(url+'/consumers/adhd.bootstrap.identity.check',headers=headers,json={'name':'identity-reader','format':'json','auto.commit.enable':'false'})
                assert response.status_code==200
                path='/consumers/adhd.bootstrap.identity.check/instances/identity-reader'
                try:
                    assert http.post(url+path+'/assignments',headers=headers,json={'partitions':[{'topic':topic,'partition':0}]}).status_code==204
                    assert http.post(url+path+'/positions',headers=headers,json={'offsets':[{'topic':topic,'partition':0,'offset':0}]}).status_code==204
                    deadline=time.monotonic()+20
                    while True:
                        response=http.get(url+path+'/records?timeout=1000&max_bytes=262144',headers={'Accept':'application/vnd.kafka.json.v2+json'})
                        assert response.status_code==200
                        records=response.json()
                        if records:break
                        assert time.monotonic()<deadline
                    assert records[0]['offset']==0 and records[0]['value']=={'fixture':'preserved through identity adoption'}
                finally:
                    assert http.delete(url+path,headers=headers).status_code==204
            record('real-fresh-volume-'+str(index)+'-permissions-random-id-restart-adoption-and-mismatch-rejection')
        assert len(set(cluster_ids))==2
        record('two-real-fresh-installations-publish-distinct-kraft-cluster-identities',distinct_cluster_ids=2)
        report['runtime']='Pinned CP8.3.2 existing Python3; no additional image or hub dependency'
    finally:
        for compose,env,name in reversed(projects):
            command(compose+['logs','--no-color'],env,check=False)
            command(compose+['down','--volumes','--remove-orphans'],env)
            for argv in [['docker','ps','-aq'],['docker','network','ls','-q'],['docker','volume','ls','-q']]:
                assert not subprocess.check_output(argv+['--filter','label=com.docker.compose.project='+name]).strip()
        log.close()
    record('all-owned-containers-networks-volumes-cleaned')
    report['passed']=True;args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS broker identity local and real fresh-volume checks')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--project',default='adhd-bootstrap-qual')
    parser.add_argument('--port',type=int,default=18920)
    parser.add_argument('--local-only',action='store_true')
    main(parser.parse_args())
