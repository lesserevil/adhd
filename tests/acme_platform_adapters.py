"""Concrete ACME-only Compose/Kind adapters. All constructors are inert.

A reviewed parent supplies a closed Command runner and accepted immutable image.
Only explicit start/replace/close methods issue commands. No host-network app,
privileged app, app-entrypoint override, broker or public issuer is used.
"""
import copy
import http.client
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import stat
import time
from uuid import uuid4
import yaml
from container_fixture import OwnedImage
from kafka_oauth_custody import NamespaceLease
import kafka_platform_vm as vm
import network_policy_image_custody as image_custody
from kube_qualification_inputs import validate_kube_endpoint
from acme_platform_plan import private_port


def identity(image):
 assert isinstance(image,str) and re.fullmatch('sha256:[a-f0-9]{64}',image)
 return image


def file(path,body):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 with path.open('xb') as output:output.write(body)
 path.chmod(0o600)


def challenge_get(path):
 assert path.startswith('/') and not path.startswith('//') and not any(c in path for c in '\r\n')
 conn=http.client.HTTPConnection('127.0.0.2',80,timeout=2)
 try:
  conn.request('GET',path,headers={'Host':'one.acme.test:8080','Connection':'close'})
  response=conn.getresponse();assert len(response.read(16385))<=16384
  return response.status
 finally:conn.close()


def owned(state,name,image=None):
 assert state['Name']=='/'+name and re.fullmatch('[a-f0-9]{64}',state['Id'])
 if image:assert state['Image']==image
 return state['Id']


def absent(result,name):return OwnedImage.probe_absence(result,name)


def resource_absent(result,name,kind):
 assert kind in ('network','volume')
 prefix=r'(?i:(?:Error(?: response from daemon)?:\s*)?'
 pattern=(prefix+r'network )'+re.escape(name)+r'(?i: not found)' if kind=='network' else
          prefix+r'get\s+)'+re.escape(name)+r'(?i::\s+no such volume)')
 return result.returncode==1 and result.stdout.strip() in (b'',b'[]') and re.fullmatch(pattern,result.stderr.decode(errors='replace').strip()) is not None


def bridge_gateway(value):
 address=ipaddress.IPv4Address(value)
 assert any(address in ipaddress.ip_network(v) for v in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']) and not address.is_loopback and not address.is_unspecified and not address.is_multicast
 return str(address)


def validate_seed(raw):
 config=json.loads(raw)
 assert config['host']=='0.0.0.0' and config['port']==8766 and config['store_path']=='/data/hub.dets'
 assert config['matcher'] is None and config['eventing']['enabled'] is False
 assert not config.get('tls',{}).get('enabled',False)
 assert all(project.get('settings',{})=={} for project in config['projects'])
 return config


def render_compose(root,work,gateway,private_http_port=18766):
 private_http_port=private_port(private_http_port)
 # Only host-bind addresses change; actual shipped target/listener ports stay80/443→8080/8443.
 bridge_gateway(gateway)
 fixture={'services':{'hub':{'extra_hosts':['pebble:'+gateway]}}}
 text=yaml.safe_dump(fixture)
 text+='    ports: !override '+json.dumps(['127.0.0.1:'+str(private_http_port)+':8766','127.0.0.2:80:8080','127.0.0.2:443:8443'])+'\n'
 file(work/'fixture.compose.yaml',text.encode())
 return ['-f',str(root/'deploy/app.compose.yaml'),'-f',str(root/'deploy/app.acme.compose.yaml'),'-f',str(work/'fixture.compose.yaml')]


def render_kind(root,namespace,image,seed,gateway,reference=None):
 identity(image);bridge_gateway(gateway)
 validate_seed(seed['hub.json'])
 reference=reference or image
 assert re.fullmatch('[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9._-]+',reference) or reference==image
 source=list(yaml.safe_load_all((root/'deploy/k8s/hub.yaml').read_text()))
 deployment=next(row for row in source if row['kind']=='Deployment')
 pvc=next(row for row in source if row['kind']=='PersistentVolumeClaim')
 pub=yaml.safe_load((root/'deploy/k8s/acme/public-service.yaml').read_text())
 patch=yaml.safe_load((root/'deploy/k8s/acme/hub-listeners.yaml').read_text())
 # Match the shipped kustomize strategic merge: named ports appended; original8766 retained.
 hub=deployment['spec']['template']['spec']['containers'][0]
 hub['ports']+=patch['spec']['template']['spec']['containers'][0]['ports']
 for container in deployment['spec']['template']['spec']['initContainers']+[hub]:
  container['image']=reference;container['imagePullPolicy']='Never'
 deployment['spec']['template']['spec']['hostAliases']=[{'ip':gateway,'hostnames':['pebble']}]
 # Frontend-root trust is public testCA material, seeded into same private durable mount.
 init=deployment['spec']['template']['spec']['initContainers'][0]
 init['command'][-1]+='; if [ ! -e /state/config/directory-root.pem ]; then cp /seed/directory-root.pem /state/config/directory-root.pem; chmod 600 /state/config/directory-root.pem; fi'
 for port,number in zip(pub['spec']['ports'],[32080,32443]):port['nodePort']=number
 private=next(row for row in yaml.safe_load_all((root/'deploy/k8s/events.yaml').read_text()) if row['kind']=='Service' and row['metadata']['name']=='hub')
 private['spec'].setdefault('type','ClusterIP')
 secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'hub-seed'},'type':'Opaque',
         'stringData':{'hub.json':seed['hub.json'],'directory-root.pem':seed['directory-root.pem']}}
 docs=[pvc,deployment,pub,private,secret]
 for row in docs:row['metadata']['namespace']=namespace
 assert deployment['spec']['replicas']==1 and deployment['spec']['strategy']['type']=='Recreate'
 assert hub['securityContext']=={'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}}
 assert deployment['spec']['template']['spec']['securityContext']=={'runAsUser':10001,'runAsGroup':10001,'fsGroup':10001}
 assert [p['port'] for p in pub['spec']['ports']]==[80,443] and private['spec']['type']=='ClusterIP'
 return docs


# Hashes only leave the pod/container. Paths and file bodies remain private.
STATE = r'''set -eu
 test -d /config/acme
 find /config/acme -exec sh -ec 'for p do
   test ! -L "$p"; test "$(stat -c %u "$p")" = 10001
   if [ -d "$p" ]; then test "$(stat -c %a "$p")" = 700
   else test -f "$p"; test "$(stat -c %h "$p")" = 1; test "$(stat -c %a "$p")" = 600
     case "$p" in */accounts/*|*/generations/*|*/owner.json)
       printf "%s " "$(printf %s "$p" | sha256sum | cut -d" " -f1)"
       sha256sum "$p" | cut -d" " -f1;; esac
   fi
 done' sh {} +
'''


STATE_PREFLIGHT = r'''set -eu
 test "$(id -u)" = 10001; test "$(id -g)" = 10001
 for p in /state /state/config /state/data; do
   test ! -L "$p"; test -d "$p"
   test "$(stat -c %u:%g:%a "$p")" = 10001:10001:700
 done
 find /state -exec sh -ec 'for p do
   test ! -L "$p"
   if [ -d "$p" ]; then test "$(stat -c %u:%g:%a "$p")" = 10001:10001:700
   else test -f "$p"; test "$(stat -c %u:%g:%a "$p")" = 10001:10001:600
     test "$(stat -c %h "$p")" = 1
   fi
 done' sh {} +
 test -f /state/config/hub.json; test -f /state/config/directory-root.pem
 printf 'ADHD_STATE_PREFLIGHT uid=10001 gid=10001 private=ok\n'
'''


class StateProbe(OwnedImage):
 def __init__(self,command,image,config,state_root=None):
  self.command=command;self.image_id=identity(image);self.config=Path(config)
  self.state_root=Path(state_root) if state_root is not None else None
  self.preflight_proven=False
  if self.state_root is not None:
   assert self.state_root.is_absolute() and self.config==self.state_root/'config'
   assert not any(c in str(self.state_root) for c in ',:\n\0')
  assert self.config.is_absolute() and not any(c in str(self.config) for c in ',:\n\0')
  self.probe_events=[];self.probe_active_name=self.probe_active_id=None;self.probe_cleanup_blocked=False
 def docker(self,*args,check=True):
  if args and args[0]=='run':
   mount='type=bind,src='+str(self.state_root)+',dst=/state,readonly' if self.state_root is not None else 'type=bind,src='+str(self.config)+',dst=/config,readonly'
   args=(args[0],'--user','10001:10001','--memory','64m','--pids-limit','32','--mount',mount,*args[1:])
  return self.command(['docker',*args],capture=True,check=check)
 def preflight(self):
  assert self.state_root is not None and not self.probe_cleanup_blocked
  assert self.state_root.parent.resolve(strict=True)==self.state_root.parent
  info=self.state_root.lstat()
  assert stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==10001 and stat.S_IMODE(info.st_mode)==0o700
  # Never traverse inaccessible private child paths from observer UID1003.
  output=self.probe('/bin/sh','-ec',STATE_PREFLIGHT)
  assert output==b'ADHD_STATE_PREFLIGHT uid=10001 gid=10001 private=ok\n' and not self.probe_cleanup_blocked
  self.preflight_proven=True
 def snapshot(self):
  program=STATE.replace('/config','/state/config') if self.state_root is not None else STATE
  lines=self.probe('/bin/sh','-ec',program).decode().splitlines()
  assert lines and len(lines)<=4096 and all(re.fullmatch('[a-f0-9]{64} [a-f0-9]{64}',line) for line in lines)
  assert len(lines)==len(set(lines));return sorted(lines)



def compose_mounts(row,state):
 """Docker reports bind mounts and HostConfig tmpfs in distinct fields."""
 mounts=row['Mounts'];assert isinstance(mounts,list) and len(mounts)==2
 assert all(isinstance(m,dict) for m in mounts)
 selected={m['Destination']:m for m in mounts}
 assert set(selected)=={'/config','/data'}
 for target,source in [('/config',state/'config'),('/data',state/'data')]:
  assert selected[target]['Type']=='bind' and selected[target]['Source']==str(source) and selected[target]['RW'] is True
 assert row['HostConfig']['Tmpfs']=={'/tmp':'rw,nosuid,noexec,size=64m'}
 return selected


def compose_vm_custody(command,row,image):
 # Production UID10001 host /proc/exe is ptrace-protected from observerUID1003.
 # Read exact container PID1 as the unchanged production UID instead; bind that
 # kernel witness to host PID/startticks and immutable Docker identity twice.
 identifier=owned(row,row['Name'].lstrip('/'),image)
 def declared(value):
  assert value['Id']==identifier and value['Image']==image
  assert value['State']['Running'] and not value['State'].get('Paused') and not value['State'].get('Restarting') and not value['State'].get('Dead')
  assert value['Config']['Entrypoint']==vm.ENTRYPOINT and value['Config']['Cmd']==vm.COMMAND
  assert value['Config']['User']=='10001:10001' and value['HostConfig']['PidMode'] in ('',None)
  assert value['HostConfig']['ReadonlyRootfs'] and value['HostConfig']['CapDrop']==['ALL']
  assert 'no-new-privileges:true' in value['HostConfig']['SecurityOpt'] and value['RestartCount']==0
 declared(row);pid=row['State']['Pid'];assert type(pid) is int and pid>0
 host=Path('/proc')/str(pid);before=(host/'stat').read_bytes();deadline=time.monotonic()+30
 def read(*arguments):
  remaining=deadline-time.monotonic();assert remaining>0,'Compose VM custody deadline'
  return command(['docker','exec','--user','10001:10001',identifier,*arguments],capture=True,timeout=remaining).stdout
 namespace_before=read('/bin/cat','/proc/1/stat')
 cmdline=read('/bin/cat','/proc/1/cmdline');exe=read('/bin/busybox','readlink','/proc/1/exe')
 namespace_after=read('/bin/cat','/proc/1/stat');after=(host/'stat').read_bytes()
 namespace_proof=vm.process_witness(cmdline,exe,namespace_before,namespace_after,1)
 host_proof=vm.process_witness(cmdline,exe,before,after,pid)
 assert namespace_proof['start_ticks']==host_proof['start_ticks'],'Container PID1 and Docker host PID disagree'
 remaining=deadline-time.monotonic();assert remaining>0,'Compose VM custody deadline'
 again=json.loads(command(['docker','inspect',identifier],capture=True,timeout=remaining).stdout)[0];declared(again)
 assert (again['State']['Pid'],again['State']['StartedAt'])==(pid,row['State']['StartedAt'])
 return {'scope':'actual Docker host PID bound to private container PID1, exec UID10001',
   'container_id':identifier,'image':image,'entrypoint':vm.ENTRYPOINT,'process':host_proof,
   'namespace_process':namespace_proof,'pid1_start_equals_host_start':True,'exec_user':'10001:10001',
   'started_at':row['State']['StartedAt'],'restart_count':row['RestartCount']}


class Compose:
 challenge_get=staticmethod(challenge_get)
 def __init__(self,command,root,work,image,name,seed_dir,state_dir,gateway,private_http_port=18766):
  self.private_http_port=private_port(private_http_port)
  self.command=command;self.root=Path(root);self.work=Path(work);self.image=identity(image)
  assert re.fullmatch('adhd-acme-[a-z0-9-]{1,40}',name)
  self.name=name;self.seed=Path(seed_dir);self.state=Path(state_dir);self.gateway=bridge_gateway(gateway)
  self.ids=[];self.ledger=[];self.issued=False;self.networks=[];self.volumes=[];self.options=None;self.state_probe=StateProbe(self.cmd,self.image,self.state/'config',self.state)
  self.env={'ADHD_HUB_IMAGE':image,'ADHD_UID':'10001','ADHD_GID':'10001','ADHD_PORT':str(self.private_http_port),
            'ADHD_CONFIG_DIR':str(self.state/'config'),'ADHD_DATA_DIR':str(self.state/'data')}
 def cmd(self,argv,**kw):return self.command(argv,env=self.env,**kw)
 def dc(self,*args,**kw):
  return self.cmd(['docker','compose','--project-name',self.name,*self.options,*args],**kw)
 def inspect(self,identifier):
  p=self.cmd(['docker','inspect',identifier],capture=True,check=False)
  if absent(p,identifier):return None
  assert p.returncode==0;row=json.loads(p.stdout)[0]
  if re.fullmatch('[a-f0-9]{64}',identifier):assert row['Id']==identifier
  return row
 def start(self):
  assert not self.issued
  assert not self.cmd(['docker','ps','-aq','--no-trunc','--filter','label=com.docker.compose.project='+self.name],capture=True).stdout.strip()
  self.options=render_compose(self.root,self.work,self.gateway,self.private_http_port)
  # Parent creates/configures this complete private state using a separately owned seed probe.
  # Refuse host-owner fallback: actual runtime must always remain productionUID10001.
  self.state_probe.preflight();assert self.state_probe.preflight_proven and not self.state_probe.probe_cleanup_blocked
  self.issued=True
  self.dc('up','-d','--no-deps','hub',timeout=90)
  return self.observe()
 def observe(self):
  ids=self.dc('ps','-q','hub',capture=True).stdout.decode().split();assert len(ids)==1 and re.fullmatch('[a-f0-9]{64}',ids[0])
  row=self.inspect(ids[0]);assert row and row['Image']==self.image
  for name,network in row['NetworkSettings']['Networks'].items():
   actual=json.loads(self.cmd(['docker','network','inspect',network['NetworkID']],capture=True).stdout)[0]
   assert actual['Id']==network['NetworkID'] and actual['Name']==name
   assert actual['Labels']['com.docker.compose.project']==self.name
   record={'id':actual['Id'],'name':name}
   if record not in self.networks:self.networks.append(record)
  assert row['Config']['Labels']['com.docker.compose.project']==self.name
  assert row['Config']['Labels']['com.docker.compose.service']=='hub'
  assert row['Config']['User']=='10001:10001' and row['HostConfig']['ReadonlyRootfs'] and row['RestartCount']==0
  assert row['HostConfig']['CapDrop']==['ALL'] and 'no-new-privileges:true' in row['HostConfig']['SecurityOpt']
  mounts=compose_mounts(row,self.state)
  ports=row['NetworkSettings']['Ports']
  assert ports['8766/tcp']==[{'HostIp':'127.0.0.1','HostPort':str(self.private_http_port)}]
  assert ports['8080/tcp']==[{'HostIp':'127.0.0.2','HostPort':'80'}]
  assert ports['8443/tcp']==[{'HostIp':'127.0.0.2','HostPort':'443'}]
  if row['Id'] not in self.ids:self.ids.append(row['Id'])
  self.ledger.append({'container_id':row['Id'],'state_mounts':{k:mounts[k]['Source'] for k in ['/config','/data']}})
  return row
 def client_ip(self):
  row=self.observe();networks=row['NetworkSettings']['Networks']
  own=next(v for n,v in networks.items() if n==self.name+'_default')
  assert own['IPAddress'] and own['Gateway']==self.gateway;return own['IPAddress']
 def custody(self):
  row=self.observe()
  return compose_vm_custody(self.cmd,row,self.image)
 def exec(self,argv,*,sensitive=False):return self.cmd(['docker','exec',self.observe()['Id'],*argv],capture=True,sensitive=sensitive).stdout
 def private_state(self):return self.state_probe.snapshot()
 def stop_hub(self):self.dc('stop','--timeout','60','hub',timeout=70)
 def replace(self):
  assert not self.state_probe.probe_cleanup_blocked
  old=self.ids[-1];self.dc('up','-d','--no-deps','--force-recreate','hub',timeout=90)
  assert self.observe()['Id']!=old
 def close(self):
  if not self.issued:return
  # Refresh only exact project-owned identities, including ambiguous-create outputs.
  p=self.cmd(['docker','ps','-aq','--no-trunc','--filter','label=com.docker.compose.project='+self.name],capture=True)
  for identifier in p.stdout.decode().split():
   assert re.fullmatch('[a-f0-9]{64}',identifier)
   row=self.inspect(identifier);assert row['Config']['Labels']['com.docker.compose.project']==self.name
   if identifier not in self.ids:self.ids.append(identifier)
  volumes=self.cmd(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+self.name],capture=True).stdout.decode().split()
  for name in volumes:
   info=json.loads(self.cmd(['docker','volume','inspect',name],capture=True).stdout)[0]
   assert info['Name']==name and info['Labels']['com.docker.compose.project']==self.name
   if name not in self.volumes:self.volumes.append(name)
  self.dc('down','--remove-orphans','--timeout','60',timeout=90)
  for name in self.volumes:
   self.cmd(['docker','volume','rm',name])
   assert resource_absent(self.cmd(['docker','volume','inspect',name],capture=True,check=False),name,'volume')
  for network in self.networks:
   for key in [network['id'],network['name']]:
    assert resource_absent(self.cmd(['docker','network','inspect',key],capture=True,check=False),key,'network')
  for identifier in self.ids:assert absent(self.cmd(['docker','inspect',identifier],capture=True,check=False),identifier)
  assert not self.cmd(['docker','ps','-aq','--no-trunc','--filter','label=com.docker.compose.project='+self.name],capture=True).stdout.strip()
  for kind in ('network','volume'):
   # No deletion of protected resources or private retained host state.
   assert not self.cmd(['docker',kind,'ls','-q','--filter','label=com.docker.compose.project='+self.name],capture=True).stdout.strip()


def anonymous_volume_proof(node,volumes,preexisting):
 """Same fresh anonymous/local/no-options predicates as the reviewed CNI gate."""
 assert node['Config'].get('Volumes')=={'/var':{}}
 mounts=[m for m in node['Mounts'] if m['Type']=='volume']
 assert [m['Destination'] for m in mounts]==['/var']
 result=[]
 for mount in mounts:
  name=mount['Name'];assert re.fullmatch('[a-f0-9]{64}',name) and name not in preexisting
  assert mount['Driver']=='local';volume=volumes[name]
  assert volume['Name']==name and volume['Driver']=='local' and volume['Scope']=='local'
  assert volume['CreatedAt'] and volume['Mountpoint']==mount['Source']
  assert volume.get('Labels')=={'com.docker.volume.anonymous':''} and not volume.get('Options')
  result.append({'name':name,'destination':mount['Destination'],'driver':volume['Driver'],'scope':volume['Scope'],
                 'created_at':volume['CreatedAt'],'mountpoint':volume['Mountpoint']})
 return result


class Kind:
 challenge_get=staticmethod(challenge_get)
 def __init__(self,command,root,work,image,name,node_image,gateway,network_id,network_name,seed,image_reference,node_config_identity,private_http_port=18766):
  self.private_http_port=private_port(private_http_port)
  self.command=command;self.root=Path(root);self.work=Path(work);self.image=identity(image)
  assert re.fullmatch('adhd-acme-[a-z0-9-]{1,40}',name)
  assert re.fullmatch('[a-z0-9./_:-]+@sha256:[a-f0-9]{64}',node_image) and re.fullmatch('[a-f0-9]{64}',network_id)
  assert re.fullmatch('[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9._-]+',image_reference)
  self.reference=image_reference;self.image_proofs=[];self.preexisting_volumes=None;self.volume_proofs=None
  self.name=name;self.node=name+'-control-plane';self.node_image=node_image;self.node_config=identity(node_config_identity)
  self.network_id=network_id;self.network_name=network_name;self.gateway=bridge_gateway(gateway);self.seed=seed
  self.kubeconfig=self.work/'kubeconfig';self.lease=NamespaceLease('adhd-final-'+name,uuid4().hex,prefix='adhd-final-')
  self.issued=False;self.node_id=None;self.pods=[];self.pvc_uid=None;self.pv_name=None;self.probes=[];self.volume_names=[];self.forward=None;self.cleanup_deadline=None;self.kubeconfig_sha=None;self.api_endpoint=None;self.kube_node_uid=None;self.node_readiness=[];self.node_readiness_count=0;self.node_readiness_last=None;self.node_readiness_successes=[];self.system_uids={};self.storage_readiness=[];self.storage_readiness_count=0;self.storage_readiness_last=None
 def cmd(self,args,**kw):
  if self.cleanup_deadline is not None:
   remaining=self.cleanup_deadline-time.monotonic();assert remaining>0,'Kind cleanup deadline'
   kw['timeout']=min(kw.get('timeout',30),remaining)
  return self.command(args,**kw)
 def kubectl(self,*args,**kw):
  assert self.kubeconfig_sha and self.kubeconfig.resolve(strict=True)==self.kubeconfig and hashlib.sha256(self.kubeconfig.read_bytes()).hexdigest()==self.kubeconfig_sha
  return self.cmd(['kubectl','--kubeconfig',str(self.kubeconfig),*args],**kw)
 def namespaced(self,*args,**kw):return self.kubectl('-n',self.lease.name,*args,**kw)
 def obj(self,*args):return json.loads(self.namespaced(*args,'-o','json',capture=True).stdout)
 def node_state(self):
  p=self.cmd(['docker','inspect',self.node],capture=True,check=False)
  if absent(p,self.node):return None
  assert p.returncode==0;row=json.loads(p.stdout)[0]
  identifier=owned(row,self.node,self.node_config)
  assert row['Config']['Image']==self.node_image
  assert row['Config']['Labels']['io.x-k8s.kind.role']=='control-plane'
  assert row['Config']['Labels']['io.x-k8s.kind.cluster']==self.name
  assert self.node_id in (None,identifier);self.node_id=identifier
  assert set(row['NetworkSettings']['Networks'])=={self.network_name}
  assert row['NetworkSettings']['Networks'][self.network_name]['NetworkID']==self.network_id
  assert row['HostConfig']['NetworkMode']==self.network_name
  self.volume_names=sorted({m['Name'] for m in row['Mounts'] if m['Type']=='volume'})
  assert self.preexisting_volumes is not None
  details={name:json.loads(self.cmd(['docker','volume','inspect',name],capture=True).stdout)[0] for name in self.volume_names}
  proof=anonymous_volume_proof(row,details,self.preexisting_volumes)
  assert self.volume_proofs is None or proof==self.volume_proofs,'Owned node volume identity changed'
  self.volume_proofs=proof
  return row
 def node_summary(self,value):
  assert self.node_id and value['metadata']['name']==self.node
  uid=value['metadata']['uid'];assert isinstance(uid,str) and re.fullmatch('[a-zA-Z0-9-]{1,128}',uid)
  assert self.kube_node_uid is None or uid==self.kube_node_uid,'Owned Kubernetes Node UID changed'
  self.kube_node_uid=uid
  conditions=[]
  for item in value.get('status',{}).get('conditions',[]):
   if item.get('type') in ('Ready','MemoryPressure','DiskPressure','PIDPressure','NetworkUnavailable'):
    conditions.append({'type':item['type'],'status':item.get('status') if item.get('status') in ('True','False','Unknown') else 'OTHER'})
  taints=[]
  for item in value.get('spec',{}).get('taints') or []:
   key=item.get('key','');known=isinstance(key,str) and re.fullmatch(r'(?:node[.]kubernetes[.]io|node-role[.]kubernetes[.]io|node[.]cloudprovider[.]kubernetes[.]io)/[a-z-]+',key)
   taints.append({'key':key if known else 'OTHER','key_sha256':hashlib.sha256(str(key).encode()).hexdigest(),'effect':item.get('effect') if item.get('effect') in ('NoSchedule','PreferNoSchedule','NoExecute') else 'OTHER'})
  return {'uid':uid,'conditions':conditions,'taints':taints,'unschedulable':value.get('spec',{}).get('unschedulable',False) is not False}
 def ready_node(self,deadline):
  while True:
   remaining=deadline-time.monotonic();assert remaining>0,'Owned node infrastructure deadline'
   response=self.kubectl('get','node',self.node,'-o','json',capture=True,sensitive=True,timeout=min(30,remaining))
   assert len(response.stdout)<=4*1024*1024
   value=json.loads(response.stdout);summary=self.node_summary(value)
   summary['private_json_sha256']=hashlib.sha256(response.stdout).hexdigest()
   self.node_readiness_count+=1
   # Keep bounded private files/safe ledger plus the latest observation/count.
   if len(self.node_readiness)<128:
    path=self.work/('node-readiness-'+str(len(self.node_readiness))+'.json');file(path,response.stdout)
    self.node_readiness.append(summary)
   self.node_readiness_last=summary
   ready=[c for c in summary['conditions'] if c['type']=='Ready']
   if ready==[{'type':'Ready','status':'True'}] and not summary['unschedulable'] and value.get('spec',{}).get('taints',[])==[]:
    assert time.monotonic()<=deadline,'Owned node infrastructure deadline'
    assert len(self.node_readiness_successes)<2
    file(self.work/('node-ready-success-'+str(len(self.node_readiness_successes))+'.json'),response.stdout)
    self.node_readiness_successes.append(summary)
    return summary
   remaining=deadline-time.monotonic();assert remaining>0,'Owned node infrastructure deadline'
   time.sleep(min(.5,remaining))
 def system_identity(self,value,kind,name,namespace=None):
  assert self.node_id and self.kube_node_uid and value['kind']==kind
  metadata=value['metadata'];assert metadata['name']==name
  if namespace is not None:assert metadata['namespace']==namespace
  uid=metadata['uid'];assert isinstance(uid,str) and re.fullmatch('[a-zA-Z0-9-]{1,128}',uid)
  key=(kind,namespace,name)
  if not hasattr(self,'system_uids'):self.system_uids={}
  assert key not in self.system_uids or self.system_uids[key]==uid,'Owned infrastructure UID changed'
  self.system_uids[key]=uid
  assert not metadata.get('deletionTimestamp')
  return uid
 def storage_summary(self,value):
  uid=self.system_identity(value,'Deployment','local-path-provisioner','local-path-storage')
  generation=value['metadata']['generation'];replicas=value['spec'].get('replicas',1);status=value.get('status',{})
  assert type(generation) is int and generation>0 and type(replicas) is int and replicas==1
  observed=status.get('observedGeneration',0)
  assert type(observed) is int and observed>=0 and observed<=generation
  counts={}
  for key in ('replicas','updatedReplicas','readyReplicas','availableReplicas'):
   count=status.get(key,0);assert type(count) is int and count>=0;counts[key]=count
  unavailable=status.get('unavailableReplicas',0);assert type(unavailable) is int and unavailable>=0
  return {'uid':uid,'generation':generation,'observed_generation':observed,**counts,'unavailable_replicas':unavailable,
          'ready':observed==generation and unavailable==0 and all(v==replicas for v in counts.values())}
 def ready_storage(self,deadline):
  # No extra PVC probe: this fences only the shipped controller, not provisioning.
  while True:
   def read(*args):
    remaining=deadline-time.monotonic();assert remaining>0,'Owned storage infrastructure deadline'
    response=self.kubectl(*args,'-o','json',capture=True,sensitive=True,timeout=min(30,remaining))
    assert len(response.stdout)<=4*1024*1024
    return response,json.loads(response.stdout)
   _,namespace=read('get','namespace','local-path-storage')
   self.system_identity(namespace,'Namespace','local-path-storage')
   assert namespace.get('status',{}).get('phase')=='Active','Owned storage namespace unavailable'
   response,deployment=read('-n','local-path-storage','get','deployment','local-path-provisioner')
   summary=self.storage_summary(deployment);summary['private_json_sha256']=hashlib.sha256(response.stdout).hexdigest()
   self.storage_readiness_count+=1;self.storage_readiness_last=summary
   if len(self.storage_readiness)<128:
    file(self.work/('storage-readiness-'+str(len(self.storage_readiness))+'.json'),response.stdout)
    self.storage_readiness.append(summary)
   if summary['ready']:
    _,node=read('get','node',self.node)
    current=self.node_summary(node)
    assert current['conditions'].count({'type':'Ready','status':'True'})==1 and not current['taints'] and not current['unschedulable']
    assert time.monotonic()<=deadline,'Owned storage infrastructure deadline'
    return summary
   remaining=deadline-time.monotonic();assert remaining>0,'Owned storage infrastructure deadline'
   time.sleep(min(.5,remaining))
 def start(self):
  assert not self.issued and self.node_state() is None
  network=json.loads(self.cmd(['docker','network','inspect',self.network_id],capture=True).stdout)[0]
  assert network['Id']==self.network_id and network['Name']==self.network_name
  assert network['Labels']['adhd.acme.owner']==self.name and not network['Containers']
  assert network['IPAM']['Config'][0]['Gateway']==self.gateway
  config={'kind':'Cluster','apiVersion':'kind.x-k8s.io/v1alpha4','nodes':[{'role':'control-plane','image':self.node_image,
   'extraPortMappings':[{'containerPort':32080,'hostPort':80,'listenAddress':'127.0.0.2','protocol':'TCP'},
                       {'containerPort':32443,'hostPort':443,'listenAddress':'127.0.0.2','protocol':'TCP'}]}]}
  original=json.loads(self.cmd(['docker','image','inspect',self.node_image],capture=True).stdout)
  assert len(original)==1 and original[0]['Id']==self.node_config
  self.preexisting_volumes=set(self.cmd(['docker','volume','ls','-q'],capture=True).stdout.decode().split())
  file(self.work/'kind.yaml',yaml.safe_dump(config).encode());self.issued=True
  bootstrap_deadline=time.monotonic()+180
  self.cmd(['kind','create','cluster','--name',self.name,'--config',str(self.work/'kind.yaml'),'--kubeconfig',str(self.kubeconfig),'--wait','60s'],
           env={'KIND_EXPERIMENTAL_DOCKER_NETWORK':self.network_name},timeout=180)
  node=self.node_state();assert node
  assert self.kubeconfig.resolve(strict=True)==self.kubeconfig and not self.kubeconfig.is_symlink()
  self.kubeconfig.chmod(0o600)
  self.api_endpoint=validate_kube_endpoint(yaml.safe_load(self.kubeconfig.read_bytes()),self.name)
  ports=node['NetworkSettings']['Ports']['6443/tcp']
  assert ports==[{'HostIp':self.api_endpoint['host'],'HostPort':str(self.api_endpoint['port'])}]
  self.kubeconfig_sha=hashlib.sha256(self.kubeconfig.read_bytes()).hexdigest()
  self.ready_node(bootstrap_deadline)
  local=json.loads(self.cmd(['docker','image','inspect',self.reference],capture=True).stdout)
  assert len(local)==1 and local[0]['Id']==self.image
  remaining=bootstrap_deadline-time.monotonic();assert remaining>0,'Owned node infrastructure deadline'
  self.cmd(['kind','load','docker-image',self.reference,'--name',self.name],timeout=min(120,remaining))
  cached=json.loads(self.cmd(['docker','exec',self.node_id,'crictl','inspecti',self.reference],capture=True).stdout)
  assert cached['status']['id']==self.image
  self.ready_node(bootstrap_deadline)
  self.ready_storage(bootstrap_deadline)
  document=self.lease.document()
  created=json.loads(self.kubectl('create','-f','-','-o','json',input=json.dumps(document).encode(),capture=True).stdout)
  self.lease.observe(created)
  docs=render_kind(self.root,self.lease.name,self.image,self.seed,self.gateway,self.reference)
  self.namespaced('apply','-f','-',input=yaml.safe_dump_all(docs).encode(),sensitive=True)
  self.namespaced('rollout','status','deployment/hub','--timeout=45s',timeout=50)
  self.start_forward()
  return self.observe()
 def observe(self):
  rows=self.obj('get','pods','-l','app=hub')['items'];assert len(rows)==1
  row=rows[0];assert not row['metadata'].get('deletionTimestamp')
  pod=row['spec'];assert not pod.get('hostNetwork',False) and not pod.get('hostPID',False)
  hub=next(c for c in pod['containers'] if c['name']=='hub')
  assert hub['image']==self.reference and hub['imagePullPolicy']=='Never'
  assert hub['securityContext']['readOnlyRootFilesystem'] and not hub['securityContext']['allowPrivilegeEscalation']
  assert hub['securityContext']['capabilities']['drop']==['ALL']
  assert pod['securityContext']['runAsUser']==pod['securityContext']['runAsGroup']==10001 and not pod['automountServiceAccountToken']
  assert {v['mountPath'] for v in hub['volumeMounts']}=={'/config','/data','/tmp'}
  assert all(v['name']=='state' for v in hub['volumeMounts'] if v['mountPath'] in ('/config','/data'))
  status=next(c for c in row['status']['containerStatuses'] if c['name']=='hub')
  assert status['ready'] and status['restartCount']==0
  pvc=self.obj('get','pvc','hub-data');uid=pvc['metadata']['uid']
  assert self.pvc_uid in (None,uid);self.pvc_uid=uid;self.pv_name=pvc['spec']['volumeName']
  if row['metadata']['uid'] not in self.pods:self.pods.append(row['metadata']['uid'])
  return row
 def start_forward(self):
  assert self.forward is None
  self.forward=self.command.start(['kubectl','--kubeconfig',str(self.kubeconfig),'-n',self.lease.name,
      'port-forward','--address=127.0.0.1','service/hub',str(self.private_http_port)+':8766'])
 def stop_forward(self):
  if self.forward:
   self.command.stop(self.forward);self.forward=None
 def client_ip(self):return self.node_state()['NetworkSettings']['Networks'][self.network_name]['IPAddress']
 def image_identity(self,row):
  status=row['status']['containerStatuses'][0];reference=status['imageID']
  if reference==self.image:
   actual=json.loads(self.cmd(['docker','exec',self.node_id,'crictl','inspecti',self.image],capture=True).stdout)
   assert actual['status']['id']==self.image
   proof={'pod_status_image_ref':reference,'cri_image_config_identity':self.image}
  else:
   def run(argv,deadline):
    remaining=deadline-time.monotonic();assert remaining>0
    return self.cmd(argv,capture=True,timeout=min(30,remaining)).stdout
   _,proof=image_custody.observe(self.node_id,reference,self.image,run=run,
      evidence_dir=self.work/('image-custody-'+uuid4().hex))
  self.image_proofs.append({'pod_uid':row['metadata']['uid'],**proof});return proof
 def custody(self):
  row=self.observe();self.image_identity(row)
  def command(argv,capture=True):return self.cmd(argv,capture=capture).stdout
  return vm.kind(command,self.node_id,row,self.image)
 def exec(self,args,*,sensitive=False):
  return self.namespaced('exec',self.observe()['metadata']['name'],'-c','hub','--',*args,capture=True,sensitive=sensitive).stdout
 def private_state(self):
  assert not self.obj('get','pods','-l','app=hub')['items'],'State probe only after writer stopped'
  name='acme-state-'+uuid4().hex[:16];nonce=uuid4().hex
  row={'name':name,'nonce':nonce,'uid':None,'issued':True,'absent':False};self.probes.append(row)
  pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'annotations':{'adhd.qa/owner':nonce}},
   'spec':{'restartPolicy':'Never','activeDeadlineSeconds':30,'automountServiceAccountToken':False,
    'enableServiceLinks':False,'securityContext':{'runAsUser':10001,'runAsGroup':10001,'fsGroup':10001},
    'containers':[{'name':'reader','image':self.reference,'imagePullPolicy':'Never','command':['/bin/sh','-ec',STATE],
      'securityContext':{'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
      'resources':{'requests':{'memory':'16Mi','cpu':'10m'},'limits':{'memory':'64Mi','cpu':'1'}},
      'volumeMounts':[{'name':'state','mountPath':'/config','subPath':'config','readOnly':True}]}],
    'volumes':[{'name':'state','persistentVolumeClaim':{'claimName':'hub-data','readOnly':True}}]}}
  primary=None
  try:
   made=json.loads(self.namespaced('create','-f','-','-o','json',input=json.dumps(pod).encode(),capture=True).stdout)
   row['uid']=made['metadata']['uid']
   self.namespaced('wait','--for=jsonpath={.status.phase}=Succeeded','pod/'+name,'--timeout=35s',timeout=40)
   actual=self.obj('get','pod',name)
   assert actual['metadata']['uid']==row['uid'] and actual['status']['phase']=='Succeeded'
   self.image_identity(actual)
   lines=self.namespaced('logs',name,capture=True).stdout.decode().splitlines()
   assert lines and len(lines)<=4096 and all(re.fullmatch('[a-f0-9]{64} [a-f0-9]{64}',line) for line in lines)
   assert len(lines)==len(set(lines));return sorted(lines)
  except BaseException as error:
   primary=error;raise
  finally:
   try:self.close_probe(row)
   except BaseException as cleanup:
    if primary:primary.add_note('State probe cleanup failed: '+type(cleanup).__name__)
    else:raise
 def close_probe(self,row):
  p=self.namespaced('get','pod',row['name'],'--ignore-not-found=true','-o','json',capture=True)
  if p.stdout.strip():
   actual=json.loads(p.stdout);metadata=actual['metadata']
   assert metadata['annotations']['adhd.qa/owner']==row['nonce']
   assert row['uid'] in (None,metadata['uid']);row['uid']=metadata['uid']
   deletion={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':row['uid']}}
   self.kubectl('delete','--raw','/api/v1/namespaces/'+self.lease.name+'/pods/'+row['name'],'-f','-',input=json.dumps(deletion).encode())
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   p=self.namespaced('get','pod',row['name'],'--ignore-not-found=true','-o','json',capture=True)
   if not p.stdout.strip():row['absent']=True;return
   assert json.loads(p.stdout)['metadata']['uid']==row['uid'];time.sleep(.1)
  raise AssertionError('Owned state probe remains')
 def stop_hub(self):
  # Graceful Recreate replacement preserves PVC while allowing a stopped hash inventory
  # through the separately owned state-read helper, not concurrent writer access.
  self.stop_forward()
  self.namespaced('scale','deployment/hub','--replicas=0')
  self.namespaced('wait','--for=delete','pod','-l','app=hub','--timeout=60s',timeout=65)
 def replace(self):
  old=self.pods[-1]
  self.namespaced('scale','deployment/hub','--replicas=1')
  self.namespaced('rollout','status','deployment/hub','--timeout=45s',timeout=50)
  assert self.observe()['metadata']['uid']!=old
  self.start_forward()
 def system_diagnostics(self,fetch,result):
  """Only exact dedicated-cluster namespaces; UID-check before dependent reads."""
  result['system']={'pods':[],'event_reasons':[]}
  allowed={'Pending','Running','Succeeded','Failed','Unknown','ContainerCreating','CrashLoopBackOff','OOMKilled',
           'Error','Completed','FailedScheduling','FailedMount','ProvisioningFailed','ExternalProvisioning',
           'WaitForFirstConsumer','Scheduled','Pulling','Pulled','Created','Started','BackOff'}
  def reason(value):return value if type(value) is str and value in allowed else 'OTHER'
  def obj(label,args):
   response=fetch(label,args);assert response.returncode==0
   return json.loads(response.stdout)
  for namespace in ('local-path-storage','kube-system'):
   prefix='storage' if namespace=='local-path-storage' else 'scheduler'
   try:
    ns=obj(prefix+'-namespace',['get','namespace',namespace,'-o','json'])
    self.system_identity(ns,'Namespace',namespace)
    if namespace=='local-path-storage':
     deployment=obj('storage-controller',['-n',namespace,'get','deployment','local-path-provisioner','-o','json'])
     result['system']['controller']=self.storage_summary(deployment)
    # Include provisioner-created helper Pods, whose labels need not match the controller.
    args=['-n',namespace,'get','pods']
    pods=obj(prefix+'-pods',args+['-o','json'])['items'];assert len(pods)<=32
    selected=[]
    for pod in pods:
     name=pod['metadata']['name']
     if namespace=='local-path-storage':
      if not (pod['metadata'].get('labels',{}).get('app')=='local-path-provisioner' or re.fullmatch('helper-pod-[a-zA-Z0-9-]{1,200}',name)):continue
      role='storage-helper' if name.startswith('helper-pod-') else 'storage'
     else:
      labels=pod['metadata'].get('labels',{})
      if labels.get('k8s-app')=='kube-proxy':
       assert re.fullmatch('kube-proxy-[a-z0-9-]{1,100}',name);role='proxy'
      elif labels.get('k8s-app')=='kindnet':
       assert re.fullmatch('kindnet-[a-z0-9-]{1,100}',name);role='kindnet'
      elif name=='kube-scheduler-'+self.node:role='scheduler'
      else:continue
      assert pod['spec'].get('nodeName')==self.node
     uid=self.system_identity(pod,'Pod',name,namespace)
     assert pod['spec'].get('nodeName') in (None,self.node)
     result['system']['pods'].append({'uid':uid,'role':role,'phase':reason(pod.get('status',{}).get('phase'))})
     selected.append((name,uid,pod,role))
    events=obj(prefix+'-events',['-n',namespace,'get','events','-o','json'])
    result['system']['event_reasons'] += [reason(v.get('reason')) for v in events.get('items',[])][:128]
    selected.sort(key=lambda item: {'proxy':0,'kindnet':1,'scheduler':2}.get(item[3],0))
    for index,(name,uid,pod,role) in enumerate(selected[:4]):
     try:
      current=obj(prefix+'-pod-'+str(index),['-n',namespace,'get','pod',name,'-o','json'])
      assert self.system_identity(current,'Pod',name,namespace)==uid
      containers=current['spec']['containers'];assert len(containers)<=4
      for cindex,container in enumerate(containers):
       # Names are validated from the bound Pod, never a shell expression.
       cname=container['name'];assert re.fullmatch('[a-z0-9-]{1,63}',cname)
       log_prefix=role if role in ('proxy','kindnet') else prefix
       args=['-n',namespace,'logs','pod/'+name,'-c',cname,'--tail=80','--timestamps=true']
       fetch(log_prefix+'-log-'+str(index)+'-'+str(cindex),args)
       if role in ('proxy','kindnet'):
        fetch(log_prefix+'-previous-log-'+str(index)+'-'+str(cindex),[*args,'--previous=true'])
      current=obj(prefix+'-pod-after-'+str(index),['-n',namespace,'get','pod',name,'-o','json'])
      assert self.system_identity(current,'Pod',name,namespace)==uid
     except BaseException as error:result['errors'].append({'label':prefix+'-pod-log','failure_type':type(error).__name__})
   except BaseException as error:result['errors'].append({'label':prefix+'-diagnostics','failure_type':type(error).__name__})
 def failure_diagnostics(self):
  """Private bounded reads of only our UID-bound namespace, before deletion."""
  node_observed=bool(getattr(self,'node_id',None) and getattr(self,'kube_node_uid',None) and self.kubeconfig_sha)
  namespace_observed=bool(self.lease.issued and self.kubeconfig_sha)
  if not node_observed and not namespace_observed:return {'attempted':False,'reason':'owned_node_or_namespace_not_observed'}
  directory=self.work/'failure-diagnostics';directory.mkdir(mode=0o700)
  result={'attempted':True,'files':[],'safe_pods':[],'safe_event_reasons':[],'errors':[]}
  deadline=time.monotonic()+20
  def fetch(label,args):
   remaining=deadline-time.monotonic();assert remaining>0,'Diagnostic deadline'
   response=self.kubectl(*args,capture=True,check=False,sensitive=True,timeout=min(4,remaining))
   record={'label':label,'exit_code':response.returncode}
   for key,raw in [('stdout',response.stdout),('stderr',response.stderr)]:
    assert len(raw)<=4*1024*1024
    path=directory/(label+'.'+key);file(path,raw)
    record[key+'_sha256']=hashlib.sha256(raw).hexdigest();record[key+'_bytes']=len(raw)
   result['files'].append(record);return response
  if node_observed:
   response=fetch('node',['get','node',self.node,'-o','json'])
   assert response.returncode==0;result['safe_node']=self.node_summary(json.loads(response.stdout))
  if not namespace_observed:
   if node_observed:self.system_diagnostics(fetch,result)
   return result
  # Never collect a replacement/foreign namespace, even after ambiguous create.
  response=fetch('namespace',['get','namespace',self.lease.name,'-o','json'])
  assert response.returncode==0;self.lease.observe(json.loads(response.stdout))
  allowed={'Pending','Running','Succeeded','Failed','Unknown','ContainerCreating','PodInitializing','CrashLoopBackOff',
   'ImagePullBackOff','ErrImagePull','CreateContainerConfigError','CreateContainerError','RunContainerError','Error',
   'Completed','OOMKilled','StartError','InvalidImageName','Unschedulable','FailedScheduling','FailedMount',
   'ProvisioningFailed','FailedAttachVolume','BackOff','Pulling','Pulled','Created','Started','Scheduled','Provisioning','WaitForFirstConsumer'}
  def reason(value):return value if type(value) is str and value in allowed else 'OTHER'
  queries=[('pods',['get','pods','-o','json']),('pvc',['get','pvc','-o','json']),('events',['get','events','-o','json']),
   ('hub-log',['logs','deployment/hub','-c','hub','--tail=120','--timestamps=true']),
   ('init-log',['logs','deployment/hub','-c','config-seed','--tail=120','--timestamps=true'])]
  for label,args in queries:
   try:
    response=fetch(label,['-n',self.lease.name,*args])
    if response.returncode!=0:continue
    if label=='pods':
     for pod in json.loads(response.stdout).get('items',[]):
      assert pod['metadata']['namespace']==self.lease.name
      status=pod.get('status',{});summary={'uid':pod['metadata']['uid'],'phase':reason(status.get('phase')),'containers':[]}
      for entry in status.get('initContainerStatuses',[])+status.get('containerStatuses',[]):
       for state,facts in entry.get('state',{}).items():
        if state not in ('waiting','running','terminated'):continue
        code=facts.get('exitCode');assert code is None or type(code) is int
        summary['containers'].append({'name':entry['name'] if entry['name'] in ('hub','config-seed') else 'OTHER','state':state,'reason':reason(facts.get('reason')),'exit_code':code})
      result['safe_pods'].append(summary)
    if label=='events':result['safe_event_reasons']=[reason(v.get('reason')) for v in json.loads(response.stdout).get('items',[])][:256]
   except BaseException as error:result['errors'].append({'label':label,'failure_type':type(error).__name__})
  if node_observed:self.system_diagnostics(fetch,result)
  return result
 def close(self):
  self.cleanup_deadline=time.monotonic()+180
  errors=[]
  try:self.stop_forward()
  except BaseException as error:errors.append(error)
  for probe in self.probes:
   if not probe['absent']:
    try:self.close_probe(probe)
    except BaseException as error:errors.append(error)
  if self.lease.issued:
   try:
    p=self.kubectl('get','namespace',self.lease.name,'--ignore-not-found=true','-o','json',capture=True)
    if p.stdout.strip():
     deletion=self.lease.deletion(json.loads(p.stdout))
     self.kubectl('delete','--raw','/api/v1/namespaces/'+self.lease.name,'-f','-',input=json.dumps(deletion).encode(),timeout=120)
    deadline=min(time.monotonic()+120,self.cleanup_deadline)
    while time.monotonic()<deadline:
     p=self.kubectl('get','namespace',self.lease.name,'--ignore-not-found=true','-o','json',capture=True)
     if not p.stdout.strip():break
     self.lease.observe(json.loads(p.stdout));time.sleep(.1)
    else:raise AssertionError('Owned namespace remains')
    if self.pv_name:
     while time.monotonic()<self.cleanup_deadline:
      if not self.kubectl('get','pv',self.pv_name,'--ignore-not-found=true','-o','json',capture=True).stdout.strip():break
      time.sleep(.1)
     else:raise AssertionError('Owned PV remains')
   except BaseException as error:errors.append(error)
  if self.issued:
   try:
    row=self.node_state()
    if row:
     self.cmd(['kind','delete','cluster','--name',self.name],timeout=120)
     for key in [self.node_id,self.node]:assert absent(self.cmd(['docker','inspect',key],capture=True,check=False),key)
     for volume in self.volume_names:
      p=self.cmd(['docker','volume','inspect',volume],capture=True,check=False)
      if p.returncode==0:
       info=json.loads(p.stdout)[0]
       proof=next(v for v in self.volume_proofs if v['name']==volume)
       assert info['Name']==volume and info['Driver']==proof['driver'] and info['Scope']==proof['scope']
       assert info['CreatedAt']==proof['created_at'] and info['Mountpoint']==proof['mountpoint']
       assert info.get('Labels')=={'com.docker.volume.anonymous':''} and not info.get('Options')
       self.cmd(['docker','volume','rm',volume])
      missing=self.cmd(['docker','volume','inspect',volume],capture=True,check=False)
      assert resource_absent(missing,volume,'volume')
   except BaseException as error:errors.append(error)
  try:
   network=json.loads(self.cmd(['docker','network','inspect',self.network_id],capture=True).stdout)[0]
   assert network['Id']==self.network_id and network['Name']==self.network_name
   assert network['Labels']['adhd.acme.owner']==self.name and not network['Containers']
   self.cmd(['docker','network','rm',self.network_id])
   for key in [self.network_id,self.network_name]:
    missing=self.cmd(['docker','network','inspect',key],capture=True,check=False)
    assert resource_absent(missing,key,'network')
  except BaseException as error:errors.append(error)
  if errors:raise BaseExceptionGroup('Owned Kind cleanup incomplete',errors)


class SeedProbe(OwnedImage):
 """Root fixture initializer only; app always starts10001 with original caps dropped."""
 def __init__(self,command,image,seed,state):
  self.command=command;self.image_id=identity(image);self.seed=Path(seed);self.state=Path(state)
  for path in [self.seed,self.state]:
   assert path.is_absolute() and path.resolve(strict=True)==path and path.is_dir()
   assert not any(c in str(path) for c in ',:\n\0')
  self.probe_events=[];self.probe_active_name=self.probe_active_id=None;self.probe_cleanup_blocked=False
 def docker(self,*args,check=True):
  if args and args[0]=='run':
   args=(args[0],'--user','0:0','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--memory','64m','--pids-limit','32',
      '--mount','type=bind,src='+str(self.seed)+',dst=/seed,readonly',
      '--mount','type=bind,src='+str(self.state)+',dst=/state',*args[1:])
  return self.command(['docker',*args],capture=True,check=check,sensitive=True)
 def initialize(self):
  validate_seed((self.seed/'hub.json').read_bytes())
  assert not list(self.state.iterdir()),'Fresh owned state only'
  self.probe('/bin/sh','-ec',
   'set -eu; test ! -e /state/config/hub.json; chown -R 0:0 /state; mkdir -p /state/config /state/data; '
   'cp /seed/hub.json /seed/directory-root.pem /state/config/; '
   'if [ -f /seed/initial-admin-password.txt ]; then cp /seed/initial-admin-password.txt /state/config/; fi; '
   'find /state -type d -exec chmod 700 {} +; find /state -type f -exec chmod 600 {} +; '
   'chown -R 10001:10001 /state')
