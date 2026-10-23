#!/usr/bin/env python3
"""Prepare accepted-target ACME deployment gates, then execute once under root GO.

--template emits a target-null request only. No request, prepare or verify action
starts a daemon, container, cluster, listener, ACME request or generated code.
"""
import argparse
import fcntl
import hashlib
import json
import ipaddress
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
import time
from uuid import uuid4


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path,limit=128*1024*1024):
 path=Path(path).absolute();assert path.resolve(strict=True)==path and not path.is_symlink()
 info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=limit
 return path


def dump(path,value):
 with Path(path).open('x') as output:json.dump(value,output,indent=2);output.write('\n')
 Path(path).chmod(0o600)


def tree(path):
 path=Path(path).absolute();assert path.resolve(strict=True)==path
 files={}
 for p in path.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():files[str(p.relative_to(path))]=sha(regular(p))
  else:assert p.is_dir()
 return files


def verify_tree(path,expected):
 assert tree(path)==expected,'Input SET/hash changed'
 directories={str(p.relative_to(path)) for p in Path(path).rglob('*') if p.is_dir()}
 wanted={str(parent) for name in expected for parent in Path(name).parents if str(parent)!='.'}
 assert directories==wanted,'Input directory SET changed'


def private_port(value):
 assert type(value) is int and 1024<=value<=65535
 assert value not in {8080,8443,8766,18082,18085,18088,18089,18443,18770,19100,19101,19102,19103,19104,19153},'Reserved service port'
 return value


def private_port_preflight(value):
 port=private_port(value);probe=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
 try:probe.bind(('127.0.0.1',port))
 finally:probe.close()


def validate_request(request):
 assert set(request)=={'schema','target','toolchain','daemon','networks','ownership','ca','protected'}
 assert request['schema']=='adhd/acme-platform-request@1'
 target=request['target'];assert isinstance(target,dict),'Accepted target required; template is not executable'
 assert set(target)=={'image','image_reference','artifact_sha256','context','admission','admission_sha256','source_admission_sha256'}
 assert re.fullmatch('sha256:[a-f0-9]{64}',target['image'])
 assert re.fullmatch('[a-f0-9]{64}',target['artifact_sha256']) and re.fullmatch('[a-f0-9]{64}',target['admission_sha256'])
 assert re.fullmatch('[a-f0-9]{64}',target['source_admission_sha256'])
 assert re.fullmatch('[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9._-]+',target['image_reference'])
 assert set(request['networks'])=={'compose','kind'}
 for platform,row in request['networks'].items():
  assert set(row)=={'name','subnet','gateway','nonce'} and re.fullmatch('[a-f0-9]{32}',row['nonce'])
  assert re.fullmatch('adhd-acme-[a-z0-9_-]+',row['name'])
  subnet=ipaddress.ip_network(row['subnet'],strict=True);gateway=ipaddress.ip_address(row['gateway'])
  assert subnet.version==4 and any(subnet.subnet_of(ipaddress.ip_network(v)) for v in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']) and 16<=subnet.prefixlen<=28
  assert gateway in subnet and gateway not in (subnet.network_address,subnet.broadcast_address) and not gateway.is_loopback
 assert not ipaddress.ip_network(request['networks']['compose']['subnet']).overlaps(ipaddress.ip_network(request['networks']['kind']['subnet']))
 assert request['networks']['compose']['name']!=request['networks']['kind']['name']
 owner=request['ownership'];assert set(owner)-{'private_http_port'}=={'compose_project','kind_cluster','kind_namespace','node_image','node_config_identity','relay_lock'}
 private_port(owner.get('private_http_port',18766))
 for name in ['compose_project','kind_cluster']:assert re.fullmatch('adhd-acme-[a-z0-9-]{1,40}',owner[name])
 assert owner['compose_project']!=owner['kind_cluster']
 assert owner['kind_namespace']=='adhd-final-'+owner['kind_cluster']
 assert request['networks']['compose']['name']==owner['compose_project']+'_default'
 assert re.fullmatch('[a-z0-9./_:-]+@sha256:[a-f0-9]{64}',owner['node_image'])
 assert re.fullmatch('sha256:[a-f0-9]{64}',owner['node_config_identity'])
 assert set(request['toolchain'])=={'python','docker','compose_plugin','kind','kubectl','host_closure','host_closure_sha256'}
 assert set(request['daemon'])=={'id','socket_path','socket_identity'} and isinstance(request['daemon']['id'],str) and request['daemon']['id']
 assert len(request['daemon']['socket_identity'])==2 and all(type(v)is int for v in request['daemon']['socket_identity'])
 assert set(request['ca'])=={'manifest','sha256','minimum_remaining_seconds'} and request['ca']['minimum_remaining_seconds']==1200
 assert set(request['protected'])=={'path','sha256'}
 for value in [request['toolchain']['host_closure_sha256'],request['ca']['sha256'],request['protected']['sha256']]:assert isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value)
 for value in [target['context'],target['admission'],request['ca']['manifest'],request['protected']['path'],owner['relay_lock'],request['daemon']['socket_path'],*[v for k,v in request['toolchain'].items() if k!='host_closure_sha256']]:
  assert isinstance(value,str) and Path(value).is_absolute() and not any(c in value for c in ',\n\0')
 return request


def template():
 return {'schema':'adhd/acme-platform-request@1','target':None,
  'toolchain':None,'daemon':None,'networks':None,'ownership':None,'ca':None,'protected':None,
  'instruction':'Fill only actual admitted image/context/receipt-backed admission and actual tool/daemon/network facts. Remove this instruction key before --prepare. Target-null templates cannot prepare/execute.'}


def work_binding(work,plan):
 assert work.is_absolute() and work.resolve(strict=True)==work and str(work)==plan['work'],'Execution root changed'


def bootstrap(work,plan):
 work_binding(work,plan)
 assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
 assert sys.pycache_prefix==str(work/'parent-pycache') and not list((work/'parent-pycache').iterdir())
 assert Path(__file__).name=='driver.py' and sha(regular(__file__))==plan['driver_sha256']
 verify_tree(work/'frozen',plan['frozen'])
 assert sha(work/'frozen/tests/acme_platform_matrix.py')==plan['driver_sha256'],'Logical driver differs'
 sys.path.insert(0,str(work/'frozen/tests'))
 import image_host_dependencies as host
 closure=json.loads((work/'bound/host-closure.json').read_bytes());host.verify(closure)
 assert str(Path(sys.executable).absolute())==closure['python_executable']
 venv=Path(closure['python_executable']).parent.parent
 sites=list(venv.glob('lib/python*/site-packages'));assert len(sites)==1
 sys.path.insert(1,str(sites[0]))


def platform_order(value=None):
 if value is None:return ['compose','kind']
 assert type(value) is list and value and all(type(v) is str and v in ('compose','kind') for v in value)
 assert len(value)==len(set(value)),'Duplicate platform'
 return [v for v in ['compose','kind'] if v in value]


def prepare(args):
 order=platform_order(getattr(args,'platforms',None))
 request=validate_request(json.loads(regular(args.request).read_bytes()))
 root=Path(args.repo_root).absolute();assert root.resolve(strict=True)==root
 assert Path(request['ownership']['relay_lock'])==root/'_build/acme/http01.lane.lock'
 assert sha(root/'tests/acme_platform_matrix.py')==sha(__file__),'Prepare with actual current own driver'
 work=Path(args.work).absolute();assert work.resolve()==work and not work.exists()
 # Pure helper imports only; host hashing and staged archive validation never run app code.
 sys.path.insert(0,str(root/'tests'))
 import image_host_dependencies as host
 from image_qualification_inputs import reviewed_payload,freeze_inputs
 from image_compiled_inputs import compiled_admission
 from image_compiled_admission import source_binding
 from acme_platform_plan import ca_binding
 from acme_platform_commands import ticks
 closure_path=regular(request['toolchain']['host_closure'])
 assert sha(closure_path)==request['toolchain']['host_closure_sha256']
 closure=json.loads(closure_path.read_bytes());host.verify(closure)
 assert request['toolchain']['python']==closure['python_executable']==str(Path(sys.executable).absolute())
 target=request['target'];context=Path(target['context']).absolute();admission=regular(target['admission'])
 selected=reviewed_payload(context/'manifest.json',admission,target['admission_sha256'],target['image'],target['artifact_sha256'])
 compiled=compiled_admission(context,admission,target['admission_sha256'],target['image'],target['artifact_sha256'],required=True)
 assert len(compiled['acme_files'])==8,'Managed tools/cache schema2 target required'
 admitted=json.loads(admission.read_bytes())
 source=source_binding((admission.parent/'source-admission.json').read_bytes(),target['source_admission_sha256'],
    (admission.parent/'receipt.json').read_bytes(),(admission.parent/'rebuild.json').read_bytes(),target['artifact_sha256'])
 assert admitted['prior_source_admission_sha256']==target['source_admission_sha256']
 for key in ['component_lock_identity','base_authority_identity','rebuild_authority_identity','receipt_identity','framework_distribution_identity']:assert admitted[key]==source[key]
 ca=ca_binding(request['ca']['manifest'],request['ca']['sha256'])
 ca_owner_start=ticks(ca['owner_pid']);assert ca_owner_start and ca_owner_start.isdigit()
 assert sha(regular(request['protected']['path']))==request['protected']['sha256']
 tools={name:host.path_binding(request['toolchain'][name]) for name in ['python','docker','compose_plugin','kind','kubectl']}
 for row in tools.values():assert os.access(row['realpath'],os.X_OK),'Tool must be executable'
 for name in ['compose_plugin','kind','kubectl']:
  assert host.elf_inputs(tools[name]['realpath'])=={'interpreter':None,'needed':[],'search':[]},'New Go tool requires closed static ELF'
 work.mkdir(parents=True,mode=0o700);(work/'bound').mkdir(mode=0o700);(work/'runtime').mkdir(mode=0o700)
 (work/'parent-pycache').mkdir(mode=0o700)
 for directory,origin in [('context',context),('admission',admission.parent)]:
  (work/'bound'/directory).mkdir()
  for name in (tree(origin) if directory=='context' else {'manifest.json':None,**admitted['files']}):
   assert Path(name).name==name
   original=regular(origin/name)
   if directory=='admission' and name!='manifest.json':assert sha(original)==admitted['files'][name]
   shutil.copyfile(original,work/'bound'/directory/name)
 shutil.copyfile(closure_path,work/'bound/host-closure.json')
 shutil.copyfile(request['protected']['path'],work/'bound/protected.json')
 shutil.copyfile(request['ca']['manifest'],work/'bound/ca.json')
 actual_ca=json.loads((work/'bound/ca.json').read_bytes())
 for name in ['frontend_root','issuer_root']:
  assert sha(regular(actual_ca[name]))==actual_ca[name+'_sha256']
  shutil.copyfile(actual_ca[name],work/'bound'/(name+'.pem'))
 frozen=work/'frozen';frozen.mkdir()
 inventory,_=freeze_inputs(root,frozen,selected['specifications'])
 # Full deploy tree, including non-code manifests/certificates, never silently follow aliases.
 for path in (root/'deploy').rglob('*'):
  assert not path.is_symlink()
  if path.is_file():
   name=path.relative_to(root);destination=frozen/name;destination.parent.mkdir(parents=True,exist_ok=True)
   shutil.copyfile(regular(path),destination);inventory[str(name)]=sha(destination)
 shutil.copyfile(__file__,work/'driver.py')
 client=work/'runtime/docker-config';(client/'cli-plugins').mkdir(parents=True,mode=0o700)
 dump(client/'config.json',{})
 shutil.copyfile(tools['compose_plugin']['realpath'],client/'cli-plugins/docker-compose');(client/'cli-plugins/docker-compose').chmod(0o755)
 (work/'runtime/home').mkdir(mode=0o700)
 plan={'schema':'adhd/acme-platform-once-plan@1','target':target,'request':request,'execution_ready':True,
       'root_GO_required':True,'work':str(work),'driver_sha256':sha(work/'driver.py'),'frozen':inventory,
       'bound':tree(work/'bound'),'client':tree(client),'tools':tools,'ca_generation':ca,'ca_owner_start_ticks':ca_owner_start,
       'selection':order,'order':order,'automatic_retries':0,'relay_owners':1,'provider_calls':0,'public_ca_calls':0,
       'scope':'Actual ACME-only packaged Compose/Kind; no broker/model/CNI/providerLoadBalancer qualification',
       'owned_allowlist':{'compose_project':request['ownership']['compose_project'],'kind_cluster':request['ownership']['kind_cluster'],
        'kind_namespace':request['ownership']['kind_namespace'],'networks':request['networks'],
        'probe_prefix':'adhd-accept-probe-','maximum_compose_probes':4,'pod_probe_prefix':'acme-state-',
        'relay_bind':'127.0.0.1:8080','issuer_gateway_port':19104,'private_http':'127.0.0.1:'+str(request['ownership'].get('private_http_port',18766)),'public_bind':'127.0.0.2:80/443'},
       'bootstrap_argv':[tools['python']['path'],'-I','-S','-B','-X','pycache_prefix='+str(work/'parent-pycache'),str(work/'driver.py'),'--execute','--work',str(work),'--plan-sha256','<ACTUAL_PLAN_SHA256>']}
 dump(work/'plan.json',plan)
 print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json')}))


def verify(work,plan):
 work_binding(work,plan)
 assert plan['schema']=='adhd/acme-platform-once-plan@1' and plan['execution_ready'] is True
 validate_request(plan['request']);assert plan['target']==plan['request']['target']
 assert plan['order']==platform_order(plan['selection']) and plan['selection']==plan['order']
 assert plan['automatic_retries']==0 and plan['relay_owners']==1
 verify_tree(work/'frozen',plan['frozen']);verify_tree(work/'bound',plan['bound'])
 verify_tree(work/'runtime/docker-config',plan['client'])
 assert sha(regular(__file__))==plan['driver_sha256']
 import image_host_dependencies as host
 closure=json.loads((work/'bound/host-closure.json').read_bytes());host.verify(closure)
 assert plan['tools']['python']['path']==closure['python_executable']==str(Path(sys.executable).absolute())
 for row in plan['tools'].values():host.verify_path(row)
 sock=Path(plan['request']['daemon']['socket_path']);assert sock.resolve(strict=True)==sock
 info=sock.stat();assert stat.S_ISSOCK(info.st_mode) and [info.st_dev,info.st_ino]==plan['request']['daemon']['socket_identity']


def claim(work):
 fd=os.open(work/'execution.started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as output:output.write(b'one attempt only\n');output.flush();os.fsync(output.fileno())
 descriptor=os.open(work,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(descriptor)
 finally:os.close(descriptor)


def protected(command,expected):
 from acme_platform_commands import ticks
 assert set(expected)=={'containers','networks','processes'} and expected['containers'] and expected['networks']
 for row in expected['containers']:
  assert set(row)=={'id','image','started_at','name'} and re.fullmatch('[a-f0-9]{64}',row['id']) and re.fullmatch('sha256:[a-f0-9]{64}',row['image'])
  current=json.loads(command(['docker','inspect',row['id']],capture=True,sensitive=True).stdout)[0]
  assert (current['Id'],current['Image'],current['State']['StartedAt'],current['Name'])==(row['id'],row['image'],row['started_at'],row['name'])
 for row in expected['networks']:
  assert set(row)=={'id','name','members'} and re.fullmatch('[a-f0-9]{64}',row['id'])
  assert row['members']==sorted(set(row['members'])) and all(re.fullmatch('[a-f0-9]{64}',v) for v in row['members'])
  current=json.loads(command(['docker','network','inspect',row['id']],capture=True,sensitive=True).stdout)[0]
  assert current['Id']==row['id'] and current['Name']==row['name'] and sorted(current['Containers'])==row['members']
 for row in expected['processes']:
  assert set(row)=={'pid','start_ticks'} and type(row['pid']) is int and row['pid']>0 and isinstance(row['start_ticks'],str) and row['start_ticks'].isdigit() and ticks(row['pid'])==row['start_ticks']


def check_ca(plan):
 from acme_platform_plan import ca_binding
 from acme_platform_commands import ticks
 request=plan['request'];manifest=json.loads(regular(request['ca']['manifest']).read_bytes())
 assert ca_binding(request['ca']['manifest'],request['ca']['sha256'])==plan['ca_generation']
 for process in manifest['processes']:assert ticks(process['pid'])==process['start_ticks'],'CA generation/process changed'
 owner=ticks(manifest['owner_pid']);assert owner==plan['ca_owner_start_ticks']
 deadline=int(owner)/os.sysconf('SC_CLK_TCK')+manifest['lifetime_seconds']
 assert deadline-time.monotonic()>=request['ca']['minimum_remaining_seconds'],'CA lease too short; no midflow replacement'
 return manifest


def network_subnets(existing):
 ipam=existing['IPAM'];assert type(ipam) is dict,'Malformed Docker IPAM'
 config=ipam.get('Config');assert config is None or type(config) is list,'Malformed Docker IPAM.Config'
 result=[]
 for address in config or []:
  assert type(address) is dict,'Malformed Docker IPAM address'
  subnet=address.get('Subnet')
  if subnet is not None:
   assert type(subnet) is str and subnet,'Malformed Docker subnet'
   result.append(ipaddress.ip_network(subnet,strict=True))
 return result


def scan_networks(command,proposed):
 observations=[]
 for identifier in command(['docker','network','ls','-q','--no-trunc'],capture=True).stdout.decode().split():
  assert re.fullmatch('[a-f0-9]{64}',identifier)
  rows=json.loads(command(['docker','network','inspect',identifier],capture=True).stdout);assert len(rows)==1
  existing=rows[0];assert existing['Id']==identifier
  for subnet in network_subnets(existing):
   assert subnet.version!=4 or not proposed.overlaps(subnet),'Owned subnet overlaps existing network'
  observations.append({'id':identifier,'driver':existing['Driver'],'null_config':existing['IPAM'].get('Config') is None})
 return observations


def network(command,spec,owner,ledger):
 from acme_platform_adapters import resource_absent
 p=command(['docker','network','inspect',spec['name']],capture=True,check=False)
 assert resource_absent(p,spec['name'],'network'),'Never adopt existing network'
 scan_networks(command,ipaddress.ip_network(spec['subnet'],strict=True))
 ledger['issued']=True
 argv=['docker','network','create','--driver','bridge','--subnet',spec['subnet'],'--gateway',spec['gateway'],
       '--label','adhd.acme.owner='+owner,'--label','adhd.acme.nonce='+spec['nonce']]
 if spec['name']==owner+'_default':argv+=['--label','com.docker.compose.project='+owner,'--label','com.docker.compose.network=default']
 command([*argv,spec['name']])
 value=json.loads(command(['docker','network','inspect',spec['name']],capture=True).stdout)[0]
 assert value['Name']==spec['name'] and value['Driver']=='bridge'
 assert value['Labels']['adhd.acme.owner']==owner and value['Labels']['adhd.acme.nonce']==spec['nonce']
 assert re.fullmatch('[a-f0-9]{64}',value['Id']) and not value['Containers']
 ledger['id']=value['Id']
 assert value['IPAM']['Config'][0]['Subnet']==spec['subnet'] and value['IPAM']['Config'][0]['Gateway']==spec['gateway']
 return value['Id']


def close_network(command,spec,owner,identifier):
 from acme_platform_adapters import resource_absent
 p=command(['docker','network','inspect',identifier or spec['name']],capture=True,check=False)
 if not resource_absent(p,identifier or spec['name'],'network'):
  assert p.returncode==0;row=json.loads(p.stdout)[0]
  assert row['Name']==spec['name'] and row['Labels']['adhd.acme.owner']==owner and row['Labels']['adhd.acme.nonce']==spec['nonce']
  assert not row['Containers'] and identifier in (None,row['Id']);identifier=row['Id']
  command(['docker','network','rm',identifier])
 for key in set([identifier,spec['name']])-{None}:
  assert resource_absent(command(['docker','network','inspect',key],capture=True,check=False),key,'network')


def release_lease(descriptor,report,primary):
 errors=[]
 for action in [lambda:fcntl.flock(descriptor,fcntl.LOCK_UN),lambda:os.close(descriptor)]:
  try:action()
  except BaseException as error:
   errors.append(type(error).__name__)
   if primary:primary.add_note('Relay lease release failed: '+type(error).__name__)
 report['relay_lease_released']=not errors
 report['cleanup_errors'].extend(errors)


def seed_evidence(row,probe):
 if probe is not None:
  row['seed_probe']=list(probe.probe_events)
  row['seed_probe_cleanup_blocked']=probe.probe_cleanup_blocked


def initialize_seed(row,probe):
 try:probe.initialize()
 finally:seed_evidence(row,probe)


def execute(work,plan):
 from acme_platform_commands import Commands
 from acme_platform_adapters import Compose,Kind,SeedProbe
 from acme_issuer_gateway import IssuerGateway
 from acme_challenge_relay import ChallengeRelay
 from acme_runtime import PublicClient
 from acme_acceptance import initialize
 from acme_acceptance_fixtures import certificate_facts
 from acme_platform_scenario import run,wait,private_bootstrap_client
 from acme_platform_plan import recipe
 from kafka_oauth_custody import NamespaceLease
 verify(work,plan);request=plan['request'];target=plan['target'];ca=check_ca(plan)
 lock=Path(request['ownership']['relay_lock']).absolute();assert lock.parent.resolve(strict=True)==lock.parent and not lock.is_symlink()
 parent=lock.parent.stat();assert stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.getuid() and not parent.st_mode&0o022
 descriptor=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
 try:
  info=os.fstat(descriptor);assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600
  fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BaseException:os.close(descriptor);raise
 env={'PATH':'/usr/bin:/bin','HOME':str(work/'runtime/home'),'DOCKER_HOST':'unix://'+request['daemon']['socket_path'],
      'DOCKER_CONFIG':str(work/'runtime/docker-config'),'KUBECONFIG':str(work/'runtime/unused-kubeconfig'),'LANG':'C.UTF-8'}
 try:command=Commands({k:plan['tools'][k]['path'] for k in ['docker','kind','kubectl']},env,work/'runtime')
 except BaseException:
  os.close(descriptor);raise
 report={'schema':'adhd/acme-platform-result@1','passed':False,'platforms':[],'unrun':list(plan['order']),'unselected':[v for v in ['compose','kind'] if v not in plan['order']],'requested_platforms':list(plan['order']),'cleanup_errors':[]}
 primary=None
 try:
  claim(work)
  private_port_preflight(request['ownership'].get('private_http_port',18766))
  assert json.loads(command(['docker','info','--format','{{json .ID}}'],capture=True).stdout)==request['daemon']['id']
  image=json.loads(command(['docker','image','inspect',target['image_reference']],capture=True).stdout)[0]
  assert image['Id']==target['image'] and image['Config']['User']=='10001:10001'
  assert image['Config']['Entrypoint']==['elixir','/runtime/adhd/boot.exs','/app/hub.exs'] and image['Config']['Cmd']==['["serve","/config/hub.json"]']
  before=json.loads((work/'bound/protected.json').read_bytes());protected(command,before)
  for platform in plan['order']:
   verify(work,plan);ca=check_ca(plan);private_port_preflight(request['ownership'].get('private_http_port',18766))
   adapter=gateway=relay=seed_probe=None;netid=None;phase_error=None;cleanup=[];netledger={'issued':False,'id':None}
   row={'platform':platform,'passed':False,'cleanup_errors':cleanup};report['platforms'].append(row);report['unrun'].remove(platform)
   local=work/'runtime'/platform;local.mkdir(mode=0o700)
   owner=request['ownership']['compose_project' if platform=='compose' else 'kind_cluster'];spec=request['networks'][platform]
   try:
    netid=network(command,spec,owner,netledger)
    seed={'server_id':uuid4().hex,'project_id':'default','projects':[{'id':'default','name':'Default','status':'active','description':'Owned ACME fixture','settings':{}}],
          'host':'0.0.0.0','port':8766,'public_url':'http://127.0.0.1:'+str(request['ownership'].get('private_http_port',18766)),'store_path':'/data/hub.dets','agents':{},'matcher':None,'eventing':{'enabled':False}}
    trust=regular(work/'bound/frontend_root.pem').read_text()
    if platform=='compose':
     (local/'seed').mkdir(mode=0o700);(local/'state').mkdir(mode=0o700)
     dump(local/'seed/hub.json',seed);(local/'seed/directory-root.pem').write_text(trust);(local/'seed/directory-root.pem').chmod(0o600)
     seed_probe=SeedProbe(command,target['image'],local/'seed',local/'state');initialize_seed(row,seed_probe)
     adapter=Compose(command,work/'frozen',local,target['image'],owner,local/'seed',local/'state',spec['gateway'],request['ownership'].get('private_http_port',18766))
    else:
     adapter=Kind(command,work/'frozen',local,target['image'],owner,request['ownership']['node_image'],spec['gateway'],netid,spec['name'],
        {'hub.json':json.dumps(seed),'directory-root.pem':trust},target['image_reference'],request['ownership']['node_config_identity'],request['ownership'].get('private_http_port',18766))
     adapter.lease=NamespaceLease(request['ownership']['kind_namespace'],spec['nonce'],prefix='adhd-final-')
    adapter.start()
    gateway=IssuerGateway(spec['gateway'],spec['subnet'],[adapter.client_ip()]);gateway.start()
    relay=ChallengeRelay(upstreams={'one.acme.test':('127.0.0.2',80)});relay.start()
    admin=private_bootstrap_client(PublicClient,'http://127.0.0.1:'+str(request['ownership'].get('private_http_port',18766)))
    assert wait(lambda: __import__('acme_platform_scenario').private_startup_health(admin),45,'Private Admin startup')
    password=adapter.exec(['/bin/cat','/config/initial-admin-password.txt'],sensitive=True).decode()
    password=re.search(r'^Password: (.+)$',password,re.M)[1];admin.login('admin',password)
    secure=PublicClient('https://one.acme.test',trust=work/'bound/issuer_root.pem',connect_ip='127.0.0.2')
    row['replacement_readiness']={'events':[],'pending_count':0,'ready_monotonic':None}
    row['scenario']=run(adapter,admin,secure,relay,recipe(platform,request['ownership'].get('private_http_port',18766))['tls_public_patch'],'https://one.acme.test',initialize,password,certificate_facts,replacement_readiness=row['replacement_readiness'])
    row['passed']=row['scenario']['passed']
   except BaseException as error:
    phase_error=error;row['failure_type']=type(error).__name__
    if isinstance(adapter,Kind):
     try:row['failure_diagnostics']=adapter.failure_diagnostics()
     except BaseException as diagnostic_error:
      row['failure_diagnostics']={'collector_failure_type':type(diagnostic_error).__name__}
      error.add_note('Private Kind diagnostics failed: '+type(diagnostic_error).__name__)
    raise
   finally:
    for name,close in [('relay',relay.close if relay else lambda:None),('gateway',gateway.close if gateway else lambda:None),
                       ('adapter',adapter.close if adapter else lambda:None),('network',lambda:close_network(command,spec,owner,netledger['id']) if netledger['issued'] else None),
                       ('protected',lambda:protected(command,before)),('inputs',lambda:verify(work,plan))]:
     try:close()
     except BaseException as error:
      cleanup.append({'resource':name,'failure_type':type(error).__name__})
      if phase_error:phase_error.add_note('Owned '+name+' cleanup failed: '+type(error).__name__)
    seed_evidence(row,seed_probe)
    row['network_ownership']=dict(netledger)
    if gateway:row['gateway']=gateway.evidence()
    if relay:row['relay']=relay.snapshot()
    if adapter:
     row['runtime_custody']=getattr(adapter,'ledger',getattr(adapter,'pods',[]))
     if isinstance(adapter,Kind):row['kind_ownership']={'node_id':adapter.node_id,'node_config':adapter.node_config,'kube_node_uid':adapter.kube_node_uid,'node_readiness':adapter.node_readiness,'node_readiness_count':adapter.node_readiness_count,'node_readiness_last':adapter.node_readiness_last,'node_readiness_successes':adapter.node_readiness_successes,'volume_proofs':adapter.volume_proofs,'namespace':adapter.lease.evidence(),'api_endpoint':adapter.api_endpoint,'kubeconfig_sha256':adapter.kubeconfig_sha,'image_proofs':adapter.image_proofs}
     row['state_probes']=getattr(getattr(adapter,'state_probe',None),'probe_events',getattr(adapter,'probes',[]))
     if getattr(adapter,'state_probe',None) is not None:
      row['state_probe_cleanup_blocked']=adapter.state_probe.probe_cleanup_blocked
      row['state_preflight_proven']=adapter.state_probe.preflight_proven
    if cleanup:row['passed']=False
    if cleanup and phase_error is None:raise AssertionError('Owned platform cleanup incomplete')
  report['passed']=len(report['platforms'])==len(plan['order']) and all(r['passed'] for r in report['platforms']) and not report['unrun']
 except BaseException as error:primary=error;report['failure_type']=type(error).__name__
 finally:
  try:command.close()
  except BaseException as error:report['cleanup_errors'].append(type(error).__name__)
  report['commands']=command.evidence()
  try:verify(work,plan);report['inputs_unchanged']=True
  except BaseException as error:report['inputs_unchanged']=False;report['final_input_error']=type(error).__name__
  release_lease(descriptor,report,primary)
  report['passed']=report['passed'] and primary is None and not report['cleanup_errors'] and report['inputs_unchanged'] and report['commands']['all_closed']
  try:dump(work/'result.json',report)
  except BaseException as error:
   if primary:primary.add_note('Final report write failed: '+type(error).__name__)
   else:raise
 if primary:raise primary
 assert report['passed'],'ACME platform qualification failed'


def main():
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
 for flag in ['template','prepare','execute','verify-only']:mode.add_argument('--'+flag,action='store_true')
 parser.add_argument('--work',type=Path,required=True);parser.add_argument('--repo-root',type=Path);parser.add_argument('--request',type=Path);parser.add_argument('--plan-sha256');parser.add_argument('--platforms',nargs='+')
 args=parser.parse_args()
 assert args.prepare or args.platforms is None,'Platform selection belongs to new preparation only'
 if args.template:
  assert not args.work.exists();args.work.mkdir(parents=True,mode=0o700);dump(args.work/'request-template.json',template());return
 if args.prepare:prepare(args);return
 work=args.work.absolute();raw=regular(work/'plan.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==args.plan_sha256
 plan=json.loads(raw);assert plan.get('target') is not None
 bootstrap(work,plan)
 if args.verify_only:verify(work,plan)
 else:execute(work,plan)


if __name__=='__main__':main()
