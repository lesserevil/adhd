#!/usr/bin/env python3
"""Prepare and review an isolated Calico/Kind network-layer gate; never implicit GO."""
import sys
sys.dont_write_bytecode=True
_STAGED=__file__.rsplit('/',1)[-1]=='driver.py'
if __name__=='__main__' and '--execute' in sys.argv:
 assert _STAGED and sys.flags.isolated,'Execute only reviewed driver.py with python -I'
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def plain(path):
 p=Path(path).absolute();s=p.lstat();assert p.resolve(strict=True)==p and stat.S_ISREG(s.st_mode) and s.st_nlink==1;return p

def inventory(root):
 root=Path(root).absolute();assert root.resolve(strict=True)==root and root.is_dir()
 files={};dirs=[]
 for p in sorted(root.rglob('*')):
  s=p.lstat();assert not stat.S_ISLNK(s.st_mode)
  if stat.S_ISDIR(s.st_mode):dirs.append(str(p.relative_to(root)))
  else:assert stat.S_ISREG(s.st_mode) and s.st_nlink==1;files[str(p.relative_to(root))]=sha(p)
 return {'files':files,'directories':dirs}

def external(path):
 p=Path(path).absolute();r=p.resolve(strict=True);assert r.is_file()
 return {'path':str(p),'realpath':str(r),'sha256':sha(r),'symlink':os.readlink(p) if p.is_symlink() else None}

def tool_tree(root):
 root=Path(root).absolute();assert root.resolve(strict=True)==root and root.is_dir()
 files={};dirs=[]
 for p in sorted(root.rglob('*')):
  if '__pycache__' in p.parts or p.suffix in ('.pyc','.pyo'):continue
  s=p.lstat();name=str(p.relative_to(root))
  if stat.S_ISDIR(s.st_mode):dirs.append(name)
  elif stat.S_ISLNK(s.st_mode) and p.resolve(strict=True).is_dir():
   r=p.resolve(strict=True);assert r.is_relative_to(root);files[name]={'directory_symlink':os.readlink(p),'realpath':str(r)}
  else:files[name]=external(p)
 return {'root':str(root),'files':files,'directories':dirs}

def save(path,value):
 p=Path(path);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.chmod(0o600);tmp.replace(p)

def absent(result,identifier,network=False):
 if result.returncode!=1 or result.stdout.strip() not in (b'',b'[]'):return False
 if network:pattern=r'(?i:(?:Error(?: response from daemon)?:\s*)?(?:network\s+))'+re.escape(identifier)+r'(?i:\s+not found)'
 else:pattern=r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier)
 return re.fullmatch(pattern,result.stderr.decode(errors='replace').strip()) is not None

def volume_absent(result,name):
 return result.returncode==1 and result.stdout.strip() in (b'',b'[]') and re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?get\s+)'+re.escape(name)+r'(?i::\s+no such volume)',result.stderr.decode(errors='replace').strip()) is not None


def verify(work,plan):
 assert work.resolve(strict=True)==work and not work.is_symlink()
 assert sha(plain(__file__))==sha(work/'driver.py')==plan['driver_sha256']
 assert sha(work/'frozen/tests/kafka_network_policy_cluster.py')==plan['driver_sha256']
 for name in ('frozen','bound'):assert inventory(work/name)==plan[name]
 for tree in plan['tool_trees']:assert tool_tree(tree['root'])==tree
 for x in plan['external_inputs']:assert external(x['path'])==x
 assert Path('/proc/self/exe').resolve()==Path(plan['tools']['python']['realpath'])
 assert str(Path(sys.executable).absolute())==plan['tools']['python']['path']
 socket=Path(plan['docker_socket']['path']);s=socket.stat();assert socket.resolve()==socket and stat.S_ISSOCK(s.st_mode) and [s.st_dev,s.st_ino]==plan['docker_socket']['identity']
 assert plan['cluster']=='adhd-netpol-qa40' and plan['network']==plan['cluster']+'-net' and plan['node']==plan['cluster']+'-control-plane'
 assert plan['image']=='sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21'
 assert sha(work/'bound/admission.json')==plan['admission_sha256']
 assert json.loads((work/'bound/image-manifest.json').read_text())['files']['hub.exs']==plan['artifact_sha256']
 return True

def prepare(args):
 root=Path(args.repo_root).absolute();assert root.resolve(strict=True)==root
 source=plain(args.cluster_plan);assert sha(source)==args.cluster_plan_sha256
 base=json.loads(source.read_text());assert base['executed'] is False and base['execution_ready'] is False
 for name,digest in base['inputs'].items():assert sha(plain(source.parent/name))==digest
 actual=inventory(source.parent);assert actual['files']==dict(base['inputs'],**{'plan.json':args.cluster_plan_sha256})
 expected_dirs=sorted({str(parent) for n in actual['files'] for parent in Path(n).parents if str(parent)!='.'});assert actual['directories']==expected_dirs
 work=Path(args.work).absolute();assert not work.exists() and work.resolve()==work;work.mkdir(parents=True,mode=0o700)
 frozen=work/'frozen';frozen.mkdir()
 for tree in ('tests','scripts','deploy'):
  for p in sorted((root/tree).rglob('*')):
   assert not p.is_symlink()
   if p.is_dir() or '__pycache__' in p.parts:continue
   dest=frozen/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(plain(p),dest)
 shutil.copyfile(plain(__file__),frozen/'tests/kafka_network_policy_cluster.py')
 shutil.copyfile(plain(Path(__file__).with_name('kafka_network_policy_oci.py')),frozen/'tests/kafka_network_policy_oci.py')
 bound=work/'bound';bound.mkdir()
 for n in ('calico-pinned.yaml','kind.yaml','images.json','local-preflight.json'):shutil.copyfile(plain(source.parent/n),bound/n)
 shutil.copyfile(source,bound/'research-plan.json');shutil.copytree(source.parent/'downloads',bound/'downloads')
 # OCI archives preserve exact original manifest bytes; no node DNS or digest alias rewrite.
 import importlib.util
 spec=importlib.util.spec_from_file_location('cni_oci_inputs',Path(__file__).with_name('kafka_network_policy_oci.py'));oci=importlib.util.module_from_spec(spec);spec.loader.exec_module(oci)
 oci_source=Path(args.oci_inputs).absolute();images=json.loads((bound/'images.json').read_text())
 oci_report=oci.validate_archives(oci_source,images,bound/'downloads');assert oci_report['images_file_sha256']==sha(bound/'images.json')
 (bound/'oci-archives').mkdir()
 for name in ('manifest.json','0.oci.tar','1.oci.tar','2.oci.tar'):shutil.copyfile(plain(oci_source/name),bound/'oci-archives'/name)
 node_config=plain(args.node_config);images=json.loads((bound/'images.json').read_text());expected_node=next(i for i in images if 'kindest' in i['repository']);assert 'sha256:'+sha(node_config)==expected_node['configuration_digest'];shutil.copyfile(node_config,bound/'node-config.json')
 context=Path(args.context).absolute();inventory(context);admission=plain(args.admission_manifest)
 # Explicitly reviewed payload reader; imports are preparation-only, never an app.
 import importlib.util
 spec=importlib.util.spec_from_file_location('inputs',root/'tests/image_qualification_inputs.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
 image='sha256:e2ca08e98cc9fae67e87dbd4bf578a60b6073f5e6263f11aed18c360032ffa21';artifact='c635c2429c9af646944f740194e841260ed6e102e5e148272a247883ed66ccd3';admission_hash='a78519154311d105ed84ed2e0887490b47d22807141eb2371163fc2c1a0b0f03'
 selected=reader.reviewed_payload(context/'manifest.json',admission,admission_hash,image,artifact)
 shutil.copytree(context,bound/'context');shutil.copyfile(admission,bound/'admission.json');shutil.copyfile(context/'manifest.json',bound/'image-manifest.json')
 for name,body in selected['specifications'].items():
  dest=frozen/'components/hub'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
 (bound/'docker-config').mkdir();(bound/'docker-config/config.json').write_text('{}')
 (work/'runtime').mkdir();shutil.copyfile(plain(__file__),work/'driver.py')
 tools={name:external(p) for name,p in [('python',sys.executable),('kind',root/'.worktrees/deployment/_build/kafka/kind'),('kubectl',root/'.worktrees/deployment/_build/kafka/kubectl'),('docker','/usr/bin/docker'),('ip','/usr/sbin/ip')]}
 for n in ('kind','kubectl','docker'):assert tools[n]['sha256']==base['tools'][n]['sha256']
 images=json.loads((bound/'images.json').read_text());node=next(i for i in images if 'kindest' in i['repository']);cni=[i for i in images if 'calico/' in i['repository']]
 socket=Path('/var/run/docker.sock').resolve(strict=True);s=socket.stat()
 plan={'schema':'adhd/enforcing-cni-kind-executor@1','prepared':True,'executed':False,'root_GO_required':True,'cluster':base['cluster'],'network':base['dedicated_network'],'node':base['node'],'bridge_subnet':base['network_subnet'],'owner_label':'adhd-policy-owner','owner_nonce':os.urandom(16).hex(),'image':image,'artifact_sha256':artifact,'admission_sha256':admission_hash,'canonical_manifest_sha256':sha(bound/'image-manifest.json'),'node_image':node,'node_anonymous_volume_destinations':['/var'],'node_image_declared_volumes':sorted((json.loads(node_config.read_text())['config'].get('Volumes') or {}).keys()),'CNI_images':cni,'CNI_provisioning':'exact-OCI-archive-import','CNI_archives':oci_report['images'],'frozen':inventory(frozen),'bound':inventory(bound),'driver_sha256':sha(work/'driver.py'),'tools':tools,'tool_trees':[tool_tree(root/'.venv'),tool_tree(root/'_build/federation/native/elixir'),tool_tree(root/'_build/federation/native/erlang')],'external_inputs':[external(oci_source/name) for name in ('manifest.json','0.oci.tar','1.oci.tar','2.oci.tar')]+[external(node_config),external(source),external(context/'manifest.json'),external(context/'payload.tar'),external(admission)]+list(tools.values()),'docker_socket':{'path':str(socket),'identity':[s.st_dev,s.st_ino]},'lane_lock':str(root/'_build/roadmap/netpol-kind.lane.lock'),'automatic_retries':0,'parallelism':1,'fixture_pods':9,'routes':18,'scope':'Single disposable Kind node; raw18route shipped NetworkPolicy proof only. No actualKafka/hub/model/HA/application/release qualification.','runtime_starts_during_preparation':0,'execution_status':'UNSTARTED_REVIEW_REQUIRED'}
 save(work/'plan.json',plan);verify(work,plan);print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json'),'work':str(work)}))

class Executor:
 def __init__(self,work,plan):
  self.work,self.plan=work,plan;self.known_node=None;self.known_network=None;self.node_issued=False;self.network_issued=False;self.events=[];self.cleanup=[];self.failure=None;self.preexisting_volumes=None;self.owned_volumes=[];self.volume_candidates=set();self.volumes_verified=False
  self.env={k:v for k,v in os.environ.items() if not k.startswith(('DOCKER_','KIND_','KUBECONFIG','LD_','ERL_','ELIXIR_','PYTHON')) and k.lower() not in ('http_proxy','https_proxy','all_proxy','no_proxy')}
  self.env.update(DOCKER_HOST='unix://'+plan['docker_socket']['path'],DOCKER_CONFIG=str(work/'bound/docker-config'),KUBECONFIG=str(work/'runtime/owned.kubeconfig'),KIND_EXPERIMENTAL_DOCKER_NETWORK=plan['network'],KIND_EXPERIMENTAL_PROVIDER='docker',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(work/'frozen/tests'),NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
  self.env['PATH']=str(Path(plan['tools']['python']['path']).parent)+':/usr/bin:/bin'
 def run(self,name,argv,timeout=40,check=True):
  verify(self.work,self.plan)
  if hasattr(self,'kubeconfig_sha256'):assert sha(plain(self.env['KUBECONFIG']))==self.kubeconfig_sha256
  log=self.work/(f'{len(self.events):02d}-'+name+'.log');assert not log.exists()
  row={'name':name,'argv':argv,'started':False,'returncode':None};self.events.append(row)
  child=None;out=b'';err=b''
  try:
   child=subprocess.Popen(argv,env=self.env,cwd=self.work/'runtime',stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
   row.update(started=True,host_client_pid=child.pid)
   out,err=child.communicate(timeout=timeout);row['returncode']=child.returncode
   result=subprocess.CompletedProcess(argv,child.returncode,out,err)
   if check:assert result.returncode==0,name+' failed'
   return result
  except BaseException as e:
   row['error_type']=type(e).__name__
   if child is not None:
    try:
     if child.poll() is None:
      assert os.getpgid(child.pid)==child.pid
      os.killpg(child.pid,signal.SIGKILL)
     out,err=child.communicate(timeout=15);row['returncode']=child.returncode
     row['owned_client_joined_after_failure']=True
    except BaseException as cleanup_error:
     row['client_cleanup_failure']=type(cleanup_error).__name__;e.add_note('Owned CLI cleanup failed: '+type(cleanup_error).__name__)
   raise
  finally:
   log.write_bytes(out+b'\nSTDERR\n'+err);row['log_sha256']=sha(log)
 def docker(self,name,*args,**kw):return self.run(name,[self.plan['tools']['docker']['path'],*args],**kw)
 def inspect(self,identifier,network=False):
  result=self.docker('inspect',*(['network','inspect',identifier] if network else ['inspect',identifier]),check=False)
  if absent(result,identifier,network):return None
  assert result.returncode==0,'Inspection failed without authoritative absence'
  rows=json.loads(result.stdout);assert len(rows)==1;return rows[0]
 def network_owned(self,row):
  p=self.plan;assert row['Name']==p['network'] and row['Driver']=='bridge' and row['Labels'][p['owner_label']]==p['owner_nonce']
  assert any(v.get('Subnet')==p['bridge_subnet'] for v in row['IPAM']['Config'])
  if self.known_network:assert row['Id']==self.known_network
  return row['Id']
 def node_owned(self,row):
  p=self.plan;assert row['Name']=='/'+p['node'] and row['Image']==p['node_image']['configuration_digest']
  assert row['Config']['Labels']['io.x-k8s.kind.cluster']==p['cluster'] and row['Config']['Labels']['io.x-k8s.kind.role']=='control-plane'
  assert set(row['NetworkSettings']['Networks'])=={p['network']}
  assert row['NetworkSettings']['Networks'][p['network']]['NetworkID']==self.known_network
  if self.known_node:assert row['Id']==self.known_node
  return row['Id']
 def capture_volumes(self,row):
  self.node_owned(row);assert self.preexisting_volumes is not None
  previous=self.owned_volumes if self.volumes_verified else None;self.volumes_verified=False
  # Docker normalizes Kind's `--volume /var` into Config.Volumes, rather
  # than retaining it in HostConfig.Binds. The mounted volume is separately
  # required to be fresh and explicitly labelled anonymous by Docker.
  assert row['Config'].get('Volumes')=={path:{} for path in self.plan['node_anonymous_volume_destinations']},'Kind anonymous volume declaration differs'
  mounts=[m for m in row['Mounts'] if m['Type']=='volume']
  assert sorted(m['Destination'] for m in mounts)==self.plan['node_anonymous_volume_destinations']
  actual=[]
  for mount in mounts:
   name=mount['Name'];assert re.fullmatch('[a-f0-9]{64}',name) and name not in self.preexisting_volumes and mount['Driver']=='local','Never remove preexisting/named/shared volume'
   self.volume_candidates.add(name)
   result=self.docker('inspect-owned-volume','volume','inspect',name);values=json.loads(result.stdout);assert len(values)==1;volume=values[0]
   assert volume['Name']==name and volume['Driver']=='local' and volume['Scope']=='local' and volume['CreatedAt'] and volume['Mountpoint']==mount['Source']
   assert volume.get('Labels')=={'com.docker.volume.anonymous':''} and not volume.get('Options'),'Expected Docker-created anonymous volume without external driver options'
   actual.append({'name':name,'destination':mount['Destination'],'driver':volume['Driver'],'scope':volume['Scope'],'created_at':volume['CreatedAt'],'mountpoint':volume['Mountpoint']})
  actual.sort(key=lambda v:v['name'])
  if previous is not None:assert actual==previous,'Owned anonymous volume lifetime changed'
  self.owned_volumes=actual;self.volumes_verified=True

 def protected(self):
  network=self.inspect('kind',True);result=self.docker('protected-cluster','ps','-a','--no-trunc','--filter','label=io.x-k8s.kind.cluster=adhd-event-qual','--format','{{.ID}}')
  return {'kind_network_id':network['Id'] if network else None,'kind_network_members':sorted((network or {}).get('Containers',{})),'protected_cluster_ids':sorted(result.stdout.decode().split())}
 def preflight(self):
  p=self.plan;assert self.inspect(p['node']) is None and self.inspect(p['network'],True) is None
  ids=self.docker('networks','network','ls','-q').stdout.decode().split();nets=json.loads(self.docker('network-subnets','network','inspect',*ids).stdout) if ids else []
  ranges=[ipaddress.ip_network(c['Subnet']) for n in nets for c in (n.get('IPAM',{}).get('Config') or []) if c.get('Subnet')]
  host=json.loads(self.run('host-routes',[p['tools']['ip']['path'],'-j','-4','route','show','table','main']).stdout)
  ranges += [ipaddress.ip_network(v['dst'],strict=False) for v in host if v.get('dst') not in (None,'default')]
  desired=[ipaddress.ip_network(c) for c in [p['bridge_subnet'],'192.168.0.0/16','10.96.0.0/12']]
  assert all(not d.overlaps(v) for d in desired for v in ranges if v.version==4)
  assert Path('/sys/fs/cgroup/cgroup.controllers').is_file()
  assert os.uname().machine=='x86_64' and tuple(int(v) for v in os.uname().release.split('.')[:2])>=(5,10)
  image=json.loads(self.docker('qa40-image','image','inspect','adhd-hub:qa40').stdout);assert len(image)==1 and image[0]['Id']==p['image']
 def perform(self):
  p=self.plan;before=self.protected();self.protected_before=before;self.preflight()
  self.docker('pull-node','pull','--platform','linux/amd64','kindest/node@'+p['node_image']['index_digest'],timeout=300)
  image=json.loads(self.docker('node-image','image','inspect','kindest/node@'+p['node_image']['index_digest']).stdout);assert image[0]['Id']==p['node_image']['configuration_digest']
  self.network_issued=True
  self.docker('create-network','network','create','--driver','bridge','--subnet',p['bridge_subnet'],'--label',p['owner_label']+'='+p['owner_nonce'],p['network'])
  self.known_network=self.network_owned(self.inspect(p['network'],True))
  self.preexisting_volumes=set(self.docker('volumes-before-create','volume','ls','--format','{{.Name}}').stdout.decode().split());self.node_issued=True
  self.run('create-kind',[p['tools']['kind']['path'],'create','cluster','--name',p['cluster'],'--config',str(self.work/'bound/kind.yaml'),'--kubeconfig',self.env['KUBECONFIG'],'--wait','0s'],timeout=240)
  node_row=self.inspect(p['node']);self.known_node=self.node_owned(node_row);self.capture_volumes(node_row)
  # Verify the generated inline-credential loopback endpoint against our exact node before any kubectl mutation.
  sys.path.insert(0,str(self.work/'frozen/tests'))
  from kafka_platform_matrix import kube_endpoint
  endpoint=kube_endpoint(Path(self.env['KUBECONFIG']),p['cluster']);self.kubeconfig_sha256=sha(plain(self.env['KUBECONFIG']));published=self.inspect(self.known_node)['NetworkSettings']['Ports']['6443/tcp']
  assert len(published)==1 and published[0]['HostIp']==endpoint['host'] and int(published[0]['HostPort'])==endpoint['port']
  # DNS remains untouched. Import and prove original target before any CNI apply.
  from kafka_network_policy_oci import verify_import
  self.docker('node-containerd-version','exec',self.known_node,'ctr','version')
  for i,im in enumerate(p['CNI_images']):
   ref=im['repository']+'@'+im['linux_amd64_digest'];archive=self.work/'bound/oci-archives'/(str(i)+'.oci.tar');remote='/tmp/cni-exact-'+str(i)+'.oci.tar'
   assert sha(archive)==p['CNI_archives'][i]['archive_sha256']
   self.docker('copy-cni-archive'+str(i),'cp',str(archive),self.known_node+':'+remote,timeout=300)
   assert self.docker('archive-cni'+str(i),'exec',self.known_node,'sha256sum',remote).stdout.decode().split()[0]==p['CNI_archives'][i]['archive_sha256']
   self.docker('import-cni'+str(i),'exec',self.known_node,'ctr','--namespace=k8s.io','images','import','--local','--digests','--base-name',im['repository'],'--platform','linux/amd64',remote,timeout=300)
   listing=self.docker('target-cni'+str(i),'exec',self.known_node,'ctr','--namespace=k8s.io','images','list').stdout.decode()
   original_name=im['repository'].removeprefix('quay.io/').replace('/','-')+'-amd64.json'
   observed=self.docker('manifest-cni'+str(i),'exec',self.known_node,'ctr','--namespace=k8s.io','content','get',im['linux_amd64_digest']).stdout
   actual=json.loads(self.docker('inspect-cni'+str(i),'exec',self.known_node,'crictl','inspecti',ref).stdout)
   verify_import(im,listing,observed,(self.work/'bound/downloads'/original_name).read_bytes(),actual)
  k=[p['tools']['kubectl']['path'],'--kubeconfig',self.env['KUBECONFIG']]
  self.run('install-calico',k+['create','-f',str(self.work/'bound/calico-pinned.yaml')],timeout=120)
  for name,target in [('ready-calico','daemonset/calico-node'),('ready-controller','deployment/calico-kube-controllers')]:self.run(name,k+['-n','kube-system','rollout','status',target,'--timeout=300s'],timeout=320)
  self.run('ready-node',k+['wait','--for=condition=Ready','node/'+p['node'],'--timeout=300s'],timeout=320)
  assert json.loads(self.docker('qa40-image-before-load','image','inspect','adhd-hub:qa40').stdout)[0]['Id']==p['image']
  self.run('load-qa40',[p['tools']['kind']['path'],'load','docker-image','adhd-hub:qa40','--name',p['cluster']],timeout=180)
  assert json.loads(self.docker('qa40-image-after-load','image','inspect','adhd-hub:qa40').stdout)[0]['Id']==p['image']
  argv=[p['tools']['python']['path'],str(self.work/'frozen/tests/kafka_network_policy.py'),'--kubectl',p['tools']['kubectl']['path'],'--kubeconfig',self.env['KUBECONFIG'],'--context',str(self.work/'bound/context'),'--admission-manifest',str(self.work/'bound/admission.json'),'--admission-sha256',p['admission_sha256'],'--image',p['image'],'--cluster-image','adhd-hub:qa40','--kind-cluster',p['cluster'],'--kind-node',p['node'],'--namespace','adhd-netpol-gate40','--policy',str(self.work/'frozen/deploy/k8s/private.yaml'),'--work',str(self.work/'runtime/gate'),'--report',str(self.work/'gate-report.json')]
  self.run('network-gate',argv,timeout=None)
  report=json.loads((self.work/'gate-report.json').read_text());assert report['passed'] and report['image_config_identity']==p['image'] and report['policy_sha256']==sha(self.work/'frozen/deploy/k8s/private.yaml')
  assert len(report['before'])==len(report['after'])==18 and all(r['reachable'] for r in report['before'])
  assert all(r['reachable']==r['expected_reachable'] for r in report['after']) and len(report['fixture_runtime_images'])==9
  assert len(report['owned_namespace_cleanup'])==2 and all(r['observed_absent'] for r in report['owned_namespace_cleanup'])
  self.capture_volumes(self.inspect(self.known_node))
  assert self.protected()==before,'Protected existing cluster/network changed'
  return before
 def finish(self):
  p=self.plan;errors=[]
  for kind,issued in [('node',self.node_issued),('network',self.network_issued)]:
   if not issued:continue
   network=kind=='network';name=p[kind];identifier=self.known_network if network else self.known_node
   observed=None;foreign=False;failures=[];exit_code=None
   try:
    observed=self.inspect(identifier or name,network)
    assert observed is not None or identifier is None,'Previously owned object vanished before cleanup witness'
    if observed:
     try:identifier=self.network_owned(observed) if network else self.node_owned(observed)
     except BaseException:foreign=True;raise
     if network:
      assert not observed['Containers'];self.docker('remove-owned-network','network','rm',identifier)
     else:
      self.known_node=identifier;self.capture_volumes(observed)
      if observed['State']['Running']:self.docker('kill-owned-node','kill','--signal','KILL',identifier)
      exit_code=int(self.docker('wait-owned-node','wait',identifier).stdout);state=self.inspect(identifier)
      assert state and not state['State']['Running'] and state['State']['ExitCode']==exit_code
      if observed['State']['Running']:assert exit_code==137
      self.docker('remove-owned-node','rm','--volumes',identifier)
   except BaseException as e:
    failures.append(e)
    # Independent cleanup after an inspection/transport failure: an already
    # recorded immutable ID is safe, while an unknown name requires a fresh
    # positive ownership witness. Never remove a positively foreign object.
    if not foreign:
     try:
      if identifier is None:
       candidate=self.inspect(name,network)
       if candidate:
        identifier=self.network_owned(candidate) if network else self.node_owned(candidate)
        if not network:self.capture_volumes(candidate)
      if identifier:
       if network:self.docker('fallback-remove-network','network','rm',identifier,check=False)
       else:self.docker('fallback-remove-node','rm','--force',*(['--volumes'] if self.volumes_verified else []),identifier,check=False)
     except BaseException as cleanup_error:failures.append(cleanup_error)
   absent_now=False
   try:
    if identifier:assert self.inspect(identifier,network) is None
    assert self.inspect(name,network) is None;absent_now=True
   except BaseException as e:failures.append(e)
   self.cleanup.append({'kind':kind,'known_id':identifier,'issued_name':name,'observed_absent':absent_now,'exit_code':exit_code,'foreign_object_not_removed':foreign,'failure_types':[type(e).__name__ for e in failures]})
   errors.extend(failures)
  for name in sorted(self.volume_candidates):
   try:
    result=self.docker('verify-volume-absence','volume','inspect',name,check=False);assert volume_absent(result,name),'Owned anonymous volume remains or absence unknown'
    self.cleanup.append({'kind':'anonymous-volume','name':name,'observed_absent':True})
   except BaseException as error:
    errors.append(error);self.cleanup.append({'kind':'anonymous-volume','name':name,'observed_absent':False,'failure_type':type(error).__name__})
  return errors


def execute(work,digest):
 assert digest and sha(work/'plan.json')==digest;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
 lane=Path(plan['lane_lock']);lane.parent.mkdir(parents=True,exist_ok=True)
 with lane.open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  fd=os.open(work/'execution.started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'w') as stream:json.dump({'plan_sha256':digest,'driver_sha256':plan['driver_sha256']},stream);stream.flush();os.fsync(stream.fileno())
  fd=os.open(work,os.O_DIRECTORY|os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
  runner=Executor(work,plan);error=None;before=None
  try:before=runner.perform()
  except BaseException as e:error=e
  finally:
   cleanup_errors=runner.finish()
   protected=getattr(runner,'protected_before',before)
   if protected is not None:
    try:assert runner.protected()==protected
    except BaseException as e:cleanup_errors.append(e)
   try:verify(work,plan);unchanged=True
   except BaseException as e:unchanged=False;cleanup_errors.append(e)
   save(work/'result.json',{'schema':'adhd/enforcing-cni-kind-result@1','passed':error is None and not cleanup_errors and unchanged,'plan_sha256':digest,'image':plan['image'],'scope':plan['scope'],'failure_type':type(error).__name__ if error else None,'cleanup_failure_types':[type(e).__name__ for e in cleanup_errors],'cleanup':runner.cleanup,'owned_anonymous_volumes':runner.owned_volumes,'anonymous_volume_candidates':sorted(runner.volume_candidates),'events':runner.events,'inputs_unchanged':unchanged})
  if error:
   if cleanup_errors:error.add_note('Independent cleanup failures: '+','.join(type(e).__name__ for e in cleanup_errors))
   raise error
  if cleanup_errors:raise cleanup_errors[0]
 return 0

def main():
 p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
 p.add_argument('--work',type=Path,required=True);p.add_argument('--plan-sha256')
 for n in ('repo-root','cluster-plan','context','admission-manifest','node-config','oci-inputs'):p.add_argument('--'+n,type=Path)
 p.add_argument('--cluster-plan-sha256');args=p.parse_args()
 if args.prepare:prepare(args)
 else:sys.exit(execute(args.work.absolute(),args.plan_sha256))
if __name__=='__main__':main()
