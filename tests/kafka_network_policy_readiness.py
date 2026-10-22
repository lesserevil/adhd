"""Failure-only, bounded, read-only diagnostics for one owned TCP fixture Pod.

Raw API/describe/log bytes remain in the private work root. Nothing is collected
outside the nonce+UID namespace and exact Pod. Original readiness failure wins.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from kafka_network_policy_diagnostics import bounded

LIMITS={'seconds':60,'command_seconds':10,'total_bytes':8*1024*1024,'metadata_bytes':512*1024,'namespace_bytes':65536,'log_bytes':65536,'log_requests':2,'commands':32,'pods':1,'tail_lines':200}
ORIGINAL=b"                checked(['-n', namespace, 'wait', '--for=condition=Ready', 'pod/' + name, '--timeout=30s'])"
REPLACEMENT=b"""                try:
                    checked(['-n', namespace, 'wait', '--for=condition=Ready', 'pod/' + name, '--timeout=30s'])
                except (AssertionError, subprocess.TimeoutExpired) as readiness_error:
                    try:
                        from kafka_network_policy_readiness import capture
                        report['readiness_diagnostics'] = capture(root / 'readiness-private', kubectl, namespace, created[namespace], owner, name, role, args.cluster_image, args.kind_node)
                    except BaseException as diagnostic_error:
                        report['readiness_diagnostics_error_type'] = type(diagnostic_error).__name__
                        readiness_error.add_note('Owned readiness diagnostics failed: ' + type(diagnostic_error).__name__)
                    raise"""


def overlay(raw):
    assert raw.count(ORIGINAL)==1 and REPLACEMENT not in raw
    return raw.replace(ORIGINAL,REPLACEMENT)


class Capture:
    def __init__(self,root,kubectl,namespace,uid,nonce,pod,role,image,node):
        self.root=Path(root).absolute();assert self.root.resolve()==self.root and not self.root.exists()
        assert re.fullmatch('adhd-netpol-[a-z0-9-]+',namespace)and re.fullmatch('[a-f0-9]{32}',nonce)
        assert re.fullmatch('[a-z0-9-]+',pod)and uid and role and image and node
        self.root.mkdir(mode=0o700);self.kubectl=list(kubectl);self.namespace=namespace;self.uid=uid;self.nonce=nonce;self.pod=pod;self.role=role;self.image=image;self.node=node;self.pod_uid=None
        self.deadline=time.monotonic()+LIMITS['seconds'];self.used=0;self.commands=0;self.logs=0;self.rows=[];self.pod_status=None
    def fetch(self,name,argv,cap):
        remaining=self.deadline-time.monotonic();assert remaining>0 and self.commands<LIMITS['commands']
        self.commands+=1;cap=min(cap,LIMITS['total_bytes']-self.used);assert cap>0
        code,out,err=bounded(self.kubectl+argv,dict(os.environ),self.root,min(remaining,LIMITS['command_seconds']),cap)
        assert time.monotonic()<=self.deadline and len(out)+len(err)<=cap
        self.used+=len(out)+len(err)
        return name,code,out,err
    def external(self,name,argv,cap,environment):
        remaining=self.deadline-time.monotonic();assert remaining>0 and self.commands<LIMITS['commands']
        self.commands+=1;cap=min(cap,LIMITS['total_bytes']-self.used);assert cap>0
        code,out,err=bounded(argv,environment,self.root,min(remaining,LIMITS['command_seconds']),cap)
        assert time.monotonic()<=self.deadline and len(out)+len(err)<=cap
        self.used+=len(out)+len(err)
        return name,code,out,err
    def save(self,row):
        name,code,out,err=row;assert re.fullmatch('[a-z0-9-]+',name)
        saved={'name':name,'returncode':code}
        for suffix,data in [('stdout',out),('stderr',err)]:
            path=self.root/(name+'.'+suffix)
            with path.open('xb')as stream:stream.write(data)
            path.chmod(0o600);saved[suffix]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        self.rows.append(saved)
    def fence(self,tag):
        nsrow=self.fetch('namespace-'+tag,['get','namespace',self.namespace,'-o','json','--request-timeout=10s'],LIMITS['namespace_bytes']);assert nsrow[1]==0
        ns=json.loads(nsrow[2]);assert ns['metadata']['name']==self.namespace and ns['metadata']['uid']==self.uid and ns['metadata']['labels']['adhd-policy-owner']==self.nonce
        prow=self.fetch('pod-'+tag,['-n',self.namespace,'get','pod',self.pod,'-o','json','--request-timeout=10s'],LIMITS['metadata_bytes']);assert prow[1]==0
        pod=json.loads(prow[2]);meta=pod['metadata'];assert meta['name']==self.pod and meta['namespace']==self.namespace and meta['labels']['app']==self.role and meta['uid']
        if self.pod_uid is None:self.pod_uid=meta['uid']
        assert meta['uid']==self.pod_uid and not meta.get('ownerReferences')
        assert pod['spec'].get('nodeName')in(None,'',self.node)
        containers=pod['spec']['containers'];assert len(containers)==1 and containers[0]['name']=='fixture'and containers[0]['image']==self.image
        # Do not retain foreign API responses: only write after identity checks.
        self.save(nsrow);self.save(prow);self.pod_status=pod.get('status',{});self.pod_value=pod
        return pod
    def read(self,name,argv,cap):
        self.fence(name+'-before');row=self.fetch(name,argv,cap);self.fence(name+'-after')
        if name=='events'and row[1]==0:
            value=json.loads(row[2]);assert all(v['involvedObject']['uid']==self.pod_uid and v['metadata']['namespace']==self.namespace for v in value['items'])
        self.save(row)
    def collect(self):
        pod=self.fence('initial')
        self.read('events',['-n',self.namespace,'get','events','--field-selector','involvedObject.uid='+self.pod_uid,'-o','json','--request-timeout=10s'],LIMITS['metadata_bytes'])
        self.read('describe',['-n',self.namespace,'describe','pod',self.pod,'--request-timeout=10s'],LIMITS['metadata_bytes'])
        argv=['-n',self.namespace,'logs',self.pod,'-c','fixture','--tail=200','--limit-bytes=65536','--timestamps','--request-timeout=10s']
        self.logs+=1;self.read('log-current',argv,LIMITS['log_bytes'])
        statuses=self.pod_status.get('containerStatuses',[])
        if any(s['name']=='fixture'and s.get('restartCount',0)>0 for s in statuses):
            self.logs+=1;assert self.logs<=LIMITS['log_requests'];self.read('log-previous',argv+['--previous'],LIMITS['log_bytes'])
        if os.environ.get('ADHD_POLICY_NODE_CONTEXT'):
            try:
                from kafka_network_policy_cri import observe
                self.node_observation=observe(self)
            except BaseException as error:self.node_observation={'enabled':True,'failure_type':type(error).__name__,'cause':'unavailable; no inference'}


def capture(root,kubectl,namespace,uid,nonce,pod,role,image,node):
    instance=Capture(root,kubectl,namespace,uid,nonce,pod,role,image,node);failure=None
    try:instance.collect()
    except BaseException as error:failure=type(error).__name__
    summary={'scope':'Failure-only owned fixture Pod diagnostics; readiness/routes remain failed','capture_passed':failure is None,'failure_type':failure,'limits':LIMITS,'namespace_uid':uid,'pod_uid':instance.pod_uid,'pod':pod,'commands':instance.commands,'bytes':instance.used,'log_requests':instance.logs,'records':instance.rows,'raw_private':True,'owned_node_observation':getattr(instance,'node_observation',None)}
    (instance.root/'index.json').write_text(json.dumps(summary,indent=2)+'\n');(instance.root/'index.json').chmod(0o600)
    return summary
