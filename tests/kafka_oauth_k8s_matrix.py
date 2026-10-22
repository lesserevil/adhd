"""Prepare/review exact-image secured Kind OAuth scenario; no provisioning or automatic execution."""
import sys
_STAGED=__file__.rsplit('/',1)[-1]=='driver.py'
if _STAGED:
    # Check before importing even non-builtin bootstrap helpers. -B suppresses
    # writes only; explicit -X redirects all reads away from excluded caches.
    assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'Require python -I -S -B -X pycache_prefix=<owned-empty-path>'
    assert __file__.startswith('/')
    _prefix=__file__.rsplit('/',1)[0]+'/parent-cache'
    assert sys._xoptions.get('pycache_prefix')==sys.pycache_prefix==_prefix
    import posix
    _cache=posix.lstat(_prefix)
    assert _cache.st_mode & 0o170000==0o040000 and _cache.st_uid==posix.getuid() and _cache.st_mode & 0o077==0
    assert not posix.listdir(_prefix), 'Parent cache must be owned and empty before imports'
elif __name__=='__main__':assert '--execute' not in sys.argv, 'Execute only reviewed frozen driver.py'
sys.dont_write_bytecode=True
import argparse
import copy
import hashlib
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
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def bootstrap(driver,expected):
    driver=Path(driver).absolute();work=driver.parent
    assert driver.resolve(strict=True)==driver and not driver.is_symlink()
    planfile=work/'plan.json';assert planfile.is_file() and not planfile.is_symlink() and planfile.stat().st_size<=8*1024*1024
    assert sha(planfile)==expected;plan=json.loads(planfile.read_text());assert sha(driver)==plan['driver_sha256']
    if _STAGED:assert plan['parent_pycache_prefix']==sys.pycache_prefix
    frozen=work/'frozen';assert frozen.resolve(strict=True)==frozen and frozen.is_dir()
    found=set();dirs=set();wanted_dirs=set()
    for name in plan['frozen_inputs']:
        p=Path(name);assert not p.is_absolute() and '..' not in p.parts and str(p)==name
        wanted_dirs.update(str(v) for v in p.parents if str(v)!='.')
    for member in frozen.rglob('*'):
        info=member.lstat();assert not stat.S_ISLNK(info.st_mode)
        name=str(member.relative_to(frozen))
        if stat.S_ISDIR(info.st_mode):dirs.add(name)
        else:
            assert stat.S_ISREG(info.st_mode);found.add(name);assert sha(member)==plan['frozen_inputs'].get(name)
    assert found==set(plan['frozen_inputs']) and dirs==wanted_dirs
    return str(frozen/'tests')


if _STAGED:
    assert '--execute' in sys.argv and '--prepare' not in sys.argv and sys.argv.count('--plan-sha256')==1
    sys.path.insert(0,bootstrap(__file__,sys.argv[sys.argv.index('--plan-sha256')+1]))

import ipaddress
import socket
from image_qualification_inputs import reviewed_payload,freeze_inputs,verify_frozen_inputs
from image_recovery_remaining_matrix import tree,verify_empty_cache,wait_owned_child
from kafka_platform_matrix import kube_endpoint
from multi_image_core_matrix import claim_execution
from kafka_oauth_provider import PROXY_IMAGE
import image_host_dependencies as host_dependencies


def readonly(argv):
    return subprocess.check_output(argv,timeout=30)


def free_port(port):
    assert type(port) is int and 1024<=port<=65535
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))


def cluster_facts(kubectl,kubeconfig,node,tag,broker,proxy,namespace):
    raw=json.loads(readonly(['docker','inspect',node]));assert len(raw)==1;row=raw[0]
    assert row['Name']=='/'+node and row['State']['Running'] is True
    cluster=row['Config']['Labels']['io.x-k8s.kind.cluster']
    assert node==cluster+'-control-plane'
    network=json.loads(readonly(['docker','network','inspect','kind']));assert len(network)==1
    addresses=[r['Gateway'] for r in network[0]['IPAM']['Config'] if ipaddress.ip_address(r['Gateway']).version==4]
    assert len(addresses)==1 and ipaddress.ip_address(addresses[0]).is_private
    namespaces=json.loads(readonly([str(kubectl),'--kubeconfig',str(kubeconfig),'get','namespaces','-o','json']))
    assert all(n['metadata']['name']!=namespace for n in namespaces['items'])
    images=json.loads(readonly(['docker','exec',node,'crictl','images','-o','json']))['images']
    selected={}
    for name,requested in [('hub','docker.io/library/'+tag),('broker',broker),('proxy',proxy)]:
        matches=[r for r in images if requested in r.get('repoTags',[])+r.get('repoDigests',[])]
        assert len(matches)==1;selected[name]={'requested':requested,'id':matches[0]['id']}
    original={}
    for name,requested in [('hub',tag),('proxy',PROXY_IMAGE),('broker','confluentinc/cp-kafka@sha256:23b7aed3099df6c95e31e8c4bf3b20682e360edbf9867bc2eac978e32c89cf7f')]:
        info=json.loads(readonly(['docker','image','inspect',requested]));assert len(info)==1
        assert selected[name]['id']==info[0]['Id']
        original[name]={'config_id':info[0]['Id'],'layers':info[0]['RootFS']['Layers']}
        if name!='hub':
            manifest=readonly(['docker','exec',node,'ctr','-n','k8s.io','content','get',selected[name]['requested'].split('@')[1]])
            assert 'sha256:'+hashlib.sha256(manifest).hexdigest()==selected[name]['requested'].split('@')[1]
            descriptor=json.loads(manifest);assert descriptor['config']['digest']==selected[name]['id']
            config=readonly(['docker','exec',node,'ctr','-n','k8s.io','content','get',selected[name]['id']])
            assert 'sha256:'+hashlib.sha256(config).hexdigest()==selected[name]['id']
            assert json.loads(config)['rootfs']['diff_ids']==original[name]['layers']
            selected[name]['manifest_sha256']=hashlib.sha256(manifest).hexdigest()
    return {'node':{'name':node,'id':row['Id'],'image':row['Image'],'pid':row['State']['Pid'],'cluster':cluster},
        'kind_network_id':network[0]['Id'],'issuer_bind':addresses[0],'selected_images':selected,'host_image_equivalence':original}


def verify(work,plan,preflight=True):
    assert Path(__file__).absolute()==work/'driver.py' and Path(__file__).resolve()==work/'driver.py' and sha(__file__)==plan['driver_sha256']
    for key,directory in [('frozen_inputs','frozen'),('bound_inputs','bound'),('context_inputs','context')]:verify_frozen_inputs(work/directory,plan[key])
    verify_empty_cache(work/'parent-cache',True);verify_empty_cache(work/'results/pycache',False)
    host_dependencies.verify(json.loads((work/'bound/host-dependencies.json').read_text()))
    for row in plan['tools'].values():host_dependencies.verify_path(row)
    sock=Path(plan['docker_socket']['path']).stat();assert stat.S_ISSOCK(sock.st_mode) and [sock.st_dev,sock.st_ino]==plan['docker_socket']['identity']
    assert kube_endpoint(work/'bound/kubeconfig',plan['facts']['node']['cluster'])==plan['kube_endpoint']
    if preflight:
        for port in plan['ports'].values():free_port(port)
        assert cluster_facts(plan['tools']['kubectl']['path'],work/'bound/kubeconfig',plan['facts']['node']['name'],plan['cluster_image'],plan['broker_image'],plan['proxy_image'],plan['namespace'])==plan['facts']
    return True


def prepare(a):
    work=a.work.absolute();assert not work.exists() and work.parent.resolve(strict=True)==work.parent
    basis=json.loads(a.platform_plan.read_text());assert re.fullmatch('adhd-oauth-[a-z0-9-]+',a.namespace)
    assert a.port!=a.hub_port
    for port in (a.port,a.hub_port):free_port(port)
    selected=reviewed_payload(a.context/'manifest.json',a.admission,a.admission_sha256,a.image,json.loads((a.context/'manifest.json').read_text())['files']['hub.exs'])
    work.mkdir(mode=0o700)
    for name in ['frozen','bound','context','parent-cache','results']:(work/name).mkdir(mode=0o700)
    _,drift=freeze_inputs(a.repo_root,work/'frozen',selected['specifications'])
    tree(a.repo_root/'deploy')
    shutil.copytree(a.repo_root/'deploy',work/'frozen/deploy')
    overlays=['kafka_oauth_k8s.py','kafka_oauth_provider.py','kafka_oauth_custody.py','kafka_oauth_custody_unit.py','image_host_dependencies.py']
    for name in overlays:shutil.copyfile(Path(__file__).parent/name,work/'frozen/tests'/name)
    for p in a.context.iterdir():
        assert p.is_file() and not p.is_symlink();shutil.copyfile(p,work/'context'/p.name)
    shutil.copyfile(a.admission,work/'bound/admission.json')
    kube=Path(a.platform_plan).parent/'bound/kubeconfig';shutil.copyfile(kube,work/'bound/kubeconfig');(work/'bound/kubeconfig').chmod(0o600)
    original=json.loads(a.original_plan.read_text());dependencies=host_dependencies.capture(a.python,original['env']['PATH']);dump(work/'bound/host-dependencies.json',dependencies)
    tools={name:host_dependencies.path_binding(row['path']) for name,row in basis['tools'].items() if name in ('kubectl','kind','docker','python')}
    tool_elf={name:host_dependencies.elf_inputs(row['realpath']) for name,row in tools.items() if name in ('kubectl','kind')}
    assert all(value['interpreter'] is None and not value['needed'] for value in tool_elf.values()), 'Additional dynamic tool dependency requires closed capture'
    sock=Path('/run/docker.sock').stat();assert stat.S_ISSOCK(sock.st_mode)
    facts=cluster_facts(tools['kubectl']['path'],work/'bound/kubeconfig',basis['kind_node'],basis['cluster_image'],a.broker_image,a.proxy_image,a.namespace)
    assert facts['selected_images']['hub']['id']==a.image
    endpoint=kube_endpoint(work/'bound/kubeconfig',facts['node']['cluster'])
    shutil.copyfile(__file__,work/'driver.py');dump(work/'bound/config.json',{})
    env=host_dependencies.child_environment(original['env'],dependencies,work/'bound',work/'results/pycache',Path('/run/docker.sock'))
    argv=[str(a.python),'-s','-B',str(work/'frozen/tests/kafka_oauth_k8s.py'),'--image',a.image,'--context',str(work/'context'),
        '--acceptance-report',str(work/'bound/admission.json'),'--kubectl',tools['kubectl']['path'],'--kubeconfig',str(work/'bound/kubeconfig'),
        '--kind-node',basis['kind_node'],'--cluster-image',basis['cluster_image'],'--namespace',a.namespace,'--issuer-bind',facts['issuer_bind'],
        '--broker-image',a.broker_image,'--proxy-image',a.proxy_image,'--port',str(a.port),'--hub-port',str(a.hub_port),
        '--work',str(work/'oauth-work'),'--report',str(work/'result.json')]
    plan={'schema':'adhd/secured-kind-oauth-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','driver_sha256':sha(work/'driver.py'),'parent_pycache_prefix':str(work/'parent-cache'),
        'artifact_sha256':json.loads((a.context/'manifest.json').read_text())['files']['hub.exs'],'image':a.image,'canonical_manifest_sha256':sha(a.context/'manifest.json'),'admission_sha256':a.admission_sha256,
        'docker_socket':{'path':'/run/docker.sock','identity':[sock.st_dev,sock.st_ino]},'static_tool_elf':tool_elf,'platform_basis_sha256':sha(a.platform_plan),
        'frozen_inputs':tree(work/'frozen'),'bound_inputs':tree(work/'bound'),'context_inputs':tree(work/'context'),'tools':tools,'facts':facts,'kube_endpoint':endpoint,
        'namespace':a.namespace,'cluster_image':basis['cluster_image'],'broker_image':a.broker_image,'proxy_image':a.proxy_image,'ports':{'rest':a.port,'hub':a.hub_port},'argv':argv,'env':env,
        'automatic_retries':0,'parallelism':1,'outer_timeout':None,'original_assertions':48,'live_specification_drift':drift,'provider_calls_authorized':0,
        'scope':'Optional Confluent Enterprise/permitted trial TLS/OAuth, hottrust/token +Secret/keystore/pod rotations on actual40. Singlebroker/privateplaintextproxybroker. No SASL_SSL/NetworkPolicy-enforcement/production-entitlement/release claim.',
        'original_deadlines':'All original timeouts/assertions retained; fixed keytool probe now uses reviewed bounded30s owned Docker probe.',
        'preparation_resources_apps_compilers_started':0,'metadata_readonly_preflight':True}
    dump(work/'plan.json',plan);print(json.dumps({'plan':str(work/'plan.json'),'sha256':sha(work/'plan.json'),'frozen_files':len(plan['frozen_inputs'])}))


def execute(work,expected):
    assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
    claim_execution(work,expected,plan['driver_sha256']);result={'passed':False,'attempted':True,'started':False,'exit_code':None,'plan_sha256':expected}
    primary=None
    try:
        with (work/'stdout').open('xb') as out,(work/'stderr').open('xb') as err:
            process=subprocess.Popen(plan['argv'],cwd=work/'results',env=plan['env'],stdout=out,stderr=err,start_new_session=True)
            result.update(started=True,child_pid=process.pid);result['exit_code']=wait_owned_child(process)
        verify(work,plan,preflight=False)
        child=json.loads((work/'result.json').read_text());assert result['exit_code']==0 and child['passed'] is True
        assert child['artifact_sha256']==plan['artifact_sha256'] and child['runtime_hub_image_config_digest']==plan['image']
        assert all(row['closed'] for row in child['cleanup']) and all(row['observed_absent'] and not row['cleanup_failure_types'] for row in child['keytool_probe_custody']+child['payload_probe_custody'])
        result.update(passed=True,report_sha256=sha(work/'result.json'))
    except BaseException as error:primary=error;result['failure_type']=type(error).__name__;raise
    finally:
        try:dump(work/'execution.json',result)
        except BaseException as error:
            if primary is not None:primary.add_note('SecuredKind report failure: '+type(error).__name__)
            else:raise


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--prepare',action='store_true');m.add_argument('--execute',action='store_true')
    p.add_argument('--work',type=Path,required=True);p.add_argument('--plan-sha256')
    for n in ['repo-root','context','admission','original-plan','platform-plan']:p.add_argument('--'+n,type=Path)
    for n in ['image','admission-sha256','broker-image','proxy-image']:p.add_argument('--'+n)
    p.add_argument('--namespace',default='adhd-oauth-40');p.add_argument('--port',type=int,default=18940);p.add_argument('--hub-port',type=int,default=18941)
    p.add_argument('--python',type=Path,default=Path(sys.executable).absolute());a=p.parse_args()
    if a.prepare:prepare(a)
    else:assert a.plan_sha256;execute(a.work.absolute(),a.plan_sha256)


if __name__=='__main__':main()
