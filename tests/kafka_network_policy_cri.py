"""Failure-only reads of one already-owned Kind Pod/container cgroup; no scans."""
import hashlib,json,os,re,stat
from pathlib import Path

FILES=('memory.events','memory.events.local','memory.current','memory.max','memory.peak','pids.current','pids.max','pids.events','cpu.max','cpu.stat','cgroup.events')
# Positional paths have already matched the exact Pod UID/container ID grammar.
CGROUP_SCRIPT='''set -eu
for root in "$@"; do
  printf '\\nCGROUP %s\\n' "$root"
  if [ ! -d "$root" ]; then printf 'UNAVAILABLE\\n'; continue; fi
  [ "$(realpath -e "$root")" = "$root" ] || exit 73
  for file in memory.events memory.events.local memory.current memory.max memory.peak pids.current pids.max pids.events cpu.max cpu.stat cgroup.events; do
    printf 'FILE %s\\n' "$file"
    if [ ! -e "$root/$file" ]; then printf 'UNAVAILABLE\\n'; continue; fi
    [ -f "$root/$file" ] && [ ! -L "$root/$file" ] || exit 74
    size=$(wc -c < "$root/$file"); [ "$size" -le 65536 ] || exit 75
    cat "$root/$file"
  done
done
'''

def paths(raw,uid,cid):
 assert re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',uid)and re.fullmatch('[a-f0-9]{64}',cid)
 # Known kubelet cgroupfs and systemd slice encodings only; never discover by scan.
 for qos in ('','burstable/','besteffort/'):
  parent='/kubepods/'+qos+'pod'+uid
  if raw==parent+'/'+cid:return ['/sys/fs/cgroup'+parent,'/sys/fs/cgroup'+raw]
 for qos in ('','burstable','besteffort'):
  prefix='kubepods'+('-'+qos if qos else '')
  pod=prefix+'-pod'+uid.replace('-','_')+'.slice'
  parent='/kubepods.slice'+('/'+prefix+'.slice'if qos else '')+'/'+pod
  container=parent+'/cri-containerd-'+cid+'.scope'
  if raw in (pod+':cri-containerd:'+cid,container):return ['/sys/fs/cgroup'+parent,'/sys/fs/cgroup'+container]
 # Exact observed Kind kubelet-rooted burstable slice (no arbitrary prefix).
 pod='kubelet-kubepods-burstable-pod'+uid.replace('-','_')+'.slice'
 parent='/kubelet.slice/kubelet-kubepods.slice/kubelet-kubepods-burstable.slice/'+pod
 container=parent+'/cri-containerd-'+cid+'.scope'
 if raw in (pod+':cri-containerd:'+cid,container):return ['/sys/fs/cgroup'+parent,'/sys/fs/cgroup'+container]
 return None

def context():
 name=os.environ.get('ADHD_POLICY_NODE_CONTEXT');digest=os.environ.get('ADHD_POLICY_NODE_CONTEXT_SHA256')
 if name is None:return None
 p=Path(name).absolute();s=p.lstat();assert p.resolve(strict=True)==p and stat.S_ISREG(s.st_mode)and s.st_nlink==1 and s.st_uid==os.getuid()and stat.S_IMODE(s.st_mode)==0o600 and s.st_size<=16384
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  seen=os.fstat(fd);identity=lambda v:(v.st_dev,v.st_ino,v.st_size,v.st_uid,v.st_mode,v.st_nlink,v.st_mtime_ns,v.st_ctime_ns)
  assert identity(seen)==identity(s)
  raw=os.read(fd,16385);assert len(raw)<=16384 and os.read(fd,1)==b''
  assert identity(os.fstat(fd))==identity(s)==identity(p.lstat())
 finally:os.close(fd)
 assert hashlib.sha256(raw).hexdigest()==digest;value=json.loads(raw)
 assert value['schema']=='adhd/policy-owned-node-observer@1'
 for n in ('node_id','network_id'):assert re.fullmatch('[a-f0-9]{64}',value[n])
 assert re.fullmatch('[a-f0-9]{32}',value['owner_nonce'])and value['cluster']=='adhd-netpol-qa40'and value['node_name']==value['cluster']+'-control-plane'
 assert value['network_name']==value['cluster']+'-net'and value['node_ip']=='10.240.240.2'
 t=value['docker'];assert str(Path(t['path']).resolve(strict=True))==t['realpath']and hashlib.sha256(Path(t['realpath']).read_bytes()).hexdigest()==t['sha256']
 sock=Path(value['socket']['path']);info=sock.stat();assert stat.S_ISSOCK(info.st_mode)and [info.st_dev,info.st_ino]==value['socket']['identity']
 cfg=Path(value['docker_config']).absolute();assert cfg.resolve(strict=True)==cfg and not cfg.is_symlink();f=cfg/'config.json';assert not f.is_symlink()and f.read_bytes()==b'{}'
 return value

def owned_node(x,c):
 assert x['Id']==c['node_id']and x['Name']=='/'+c['node_name']and x['Image']==c['node_image']and x['State']['Running']
 labels=x['Config']['Labels'];assert labels['io.x-k8s.kind.cluster']==c['cluster']and labels['io.x-k8s.kind.role']=='control-plane'
 n=x['NetworkSettings']['Networks'][c['network_name']];assert n['NetworkID']==c['network_id']and n['IPAddress']==c['node_ip']

def owned_network(x,c):
 assert x['Id']==c['network_id']and x['Name']==c['network_name']and x['Driver']=='bridge'and x['Labels']['adhd-policy-owner']==c['owner_nonce']
 assert set(x['Containers'])=={c['node_id']}and x['Containers'][c['node_id']]['Name']==c['node_name']

def container_info(x,pod):
 candidates=[v for v in pod['status']['containerStatuses']if v['name']=='fixture'];assert len(candidates)==1
 ref=candidates[0]['containerID'];assert re.fullmatch('containerd://[a-f0-9]{64}',ref);cid=ref.split('://')[1]
 declared=pod['spec']['containers'][0]
 assert declared['env']==[{'name':'ERL_FLAGS','value':'+S 1:1'}]and declared['resources']['limits']=={'cpu':'1','memory':'192Mi'}
 s=x['status'];assert s['id']==cid and s['metadata']['name']=='fixture'
 labels=s['labels'];assert labels['io.kubernetes.pod.uid']==pod['metadata']['uid']and labels['io.kubernetes.pod.name']==pod['metadata']['name']and labels['io.kubernetes.pod.namespace']==pod['metadata']['namespace']
 assert s['imageRef']==candidates[0]['imageID'].removeprefix('docker-pullable://')
 spec=x['info']['runtimeSpec'];assert spec['process']['args']==pod['spec']['containers'][0]['command']
 assert spec['process']['user']['uid']==1000 and spec['process']['user']['gid']==1000
 assert spec['linux']['resources']['memory']['limit']==201326592
 return cid,s,spec['linux']['cgroupsPath']

def observe(capture):
 c=context()
 if c is None:return {'enabled':False}
 assert c['node_name']==capture.node
 capture.fence('cri-before');pod=capture.pod_value
 # Do not query arbitrary runtimes if the exact failed fixture has no container ID.
 statuses=pod.get('status',{}).get('containerStatuses',[]);matches=[v for v in statuses if v['name']=='fixture']
 if len(matches)!=1 or not re.fullmatch('containerd://[a-f0-9]{64}',matches[0].get('containerID','')):return {'enabled':True,'available':False,'reason':'exact-container-ID-unavailable'}
 cid=matches[0]['containerID'].split('://')[1];environment={k:v for k,v in os.environ.items()if not k.startswith(('DOCKER_','PYTHON','LD_','DYLD_'))}
 environment.update(DOCKER_HOST='unix://'+c['socket']['path'],DOCKER_CONFIG=c['docker_config'],PATH='/usr/bin:/bin')
 def command(name,args,cap):return capture.external(name,[c['docker']['path']]+args,cap,environment)
 def fence(tag):
  nr=command('node-'+tag,['inspect',c['node_id']],524288);assert nr[1]==0;rows=json.loads(nr[2]);assert len(rows)==1;owned_node(rows[0],c)
  net=command('network-'+tag,['network','inspect',c['network_id']],524288);assert net[1]==0;rows=json.loads(net[2]);assert len(rows)==1;owned_network(rows[0],c)
  capture.save(nr);capture.save(net)
 fence('before')
 cri=command('cri-container',['exec',c['node_id'],'crictl','inspect',cid],524288);assert cri[1]==0
 value=json.loads(cri[2]);cid,status,path=container_info(value,pod);capture.save(cri)
 routes=paths(path,pod['metadata']['uid'],cid)
 result={'enabled':True,'available':True,'container_id':cid,'pod_uid':pod['metadata']['uid'],'cri_state':{k:status.get(k)for k in ('state','reason','exitCode','createdAt','startedAt','finishedAt')},'cgroup_layout_supported':routes is not None,'cgroup_paths':routes,'container_parent_order':'Exact Pod parent first; preserve its counters even if container cgroup is destroyed.'}
 if routes:
  cg=command('cri-cgroup',['exec',c['node_id'],'sh','-eu','-c',CGROUP_SCRIPT,'adhd-owned-cgroup',*routes],1048576)
  result['cgroup_read_returncode']=cg[1];capture.save(cg)
 else:result['cgroup_unavailable']='unsupported-closed-layout; no scan attempted'
 fence('after');capture.fence('cri-after')
 return result
