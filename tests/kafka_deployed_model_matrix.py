"""Prepare serial deployed Compose/Kind model-only qualification; no automatic execution."""
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

from image_qualification_inputs import reviewed_payload,freeze_inputs,verify_frozen_inputs
from image_recovery_remaining_matrix import tree,verify_empty_cache,wait_owned_child
from multi_image_core_matrix import claim_execution
from image_compiled_inputs import compiled_admission
from kafka_oauth_k8s_matrix import cluster_facts,selected_cluster_image,free_port
from kube_qualification_inputs import validate_kube_endpoint,json_kube_endpoint
import image_host_dependencies as host_dependencies


def own_matrix(work):
    assert sha(work/'driver.py')==sha(work/'frozen/tests/kafka_deployed_model_matrix.py')


def verify(work,plan,preflight=True):
    own_matrix(work)
    assert Path(__file__).absolute()==work/'driver.py' and Path(__file__).resolve()==work/'driver.py' and sha(__file__)==plan['driver_sha256']
    for key,directory in [('frozen_inputs','frozen'),('bound_inputs','bound'),('context_inputs','context')]:verify_frozen_inputs(work/directory,plan[key])
    verify_empty_cache(work/'parent-cache',True);verify_empty_cache(work/'results/pycache',False)
    host_dependencies.verify(json.loads((work/'bound/host-dependencies.json').read_text()))
    for row in plan['tools'].values():host_dependencies.verify_path(row)
    sock=Path(plan['docker_socket']['path']).stat();assert stat.S_ISSOCK(sock.st_mode) and [sock.st_dev,sock.st_ino]==plan['docker_socket']['identity']
    assert compiled_admission(work/'context',work/'bound/admission.json',plan['admission_sha256'],plan['image'],plan['artifact_sha256'],required=True)==plan['compiled_binding']
    assert json_kube_endpoint(work/'bound/kubeconfig',plan['facts']['node']['cluster'])==plan['kube_endpoint']
    if preflight:
        for job in plan['jobs']:
            for port in (job['port'],job['relay_port']):free_port(port)
        assert cluster_facts(plan['tools']['kubectl']['path'],work/'bound/kubeconfig',plan['facts']['node']['name'],plan['cluster_image'],plan['broker_image'],plan['proxy_image'],plan['jobs'][1]['owned_name'])==plan['facts']
        # No owned Compose resources may exist before this new once-only run.
        for kind in ('container','network','volume'):
            argv=['docker','ps','-aq'] if kind=='container' else ['docker',kind,'ls','-q']
            assert not subprocess.check_output(argv+['--filter','label=com.docker.compose.project='+plan['jobs'][0]['owned_name']],env=plan['env'],timeout=30).strip()
    return True


def prepare(a):
    work=a.work.absolute();assert not work.exists() and work.parent.resolve(strict=True)==work.parent
    assert re.fullmatch('adhd-final-[a-z0-9-]{1,30}',a.name)
    assert a.lease_path.is_absolute() and a.lease_path.resolve()==a.lease_path
    ports=[a.compose_port,a.kind_port,a.compose_relay_port,a.kind_relay_port];assert len(set(ports))==4
    for port in ports:free_port(port)
    basis=json.loads(a.platform_plan.read_text());tag=selected_cluster_image(a,basis)
    artifact=json.loads((a.context/'manifest.json').read_text())['files']['hub.exs']
    selected=reviewed_payload(a.context/'manifest.json',a.admission,a.admission_sha256,a.image,artifact)
    compiled=compiled_admission(a.context,a.admission,a.admission_sha256,a.image,artifact,required=True);assert compiled is not None
    work.mkdir(mode=0o700)
    for name in ('frozen','bound','context','parent-cache','results'):(work/name).mkdir(mode=0o700)
    _,drift=freeze_inputs(a.repo_root,work/'frozen',selected['specifications'])
    tree(a.repo_root/'deploy');shutil.copytree(a.repo_root/'deploy',work/'frozen/deploy')
    # Current root helpers plus explicitly authored driver; no ambient imports.
    shutil.copyfile(__file__,work/'frozen/tests/kafka_deployed_model_matrix.py')
    shutil.copyfile(Path(__file__).with_name('kafka_oauth_k8s_matrix.py'),work/'frozen/tests/kafka_oauth_k8s_matrix.py')
    assert (work/'frozen/tests/model_service_lease.py').is_file()
    for p in a.context.iterdir():assert p.is_file() and not p.is_symlink();shutil.copyfile(p,work/'context'/p.name)
    for name in ('cache-manifest.json','cache-metadata.json'):shutil.copyfile(a.admission.parent/name,work/'bound'/name)
    shutil.copyfile(a.admission,work/'bound/admission.json')
    original=json.loads(a.original_plan.read_text());dump(work/'bound/original-plan.json',original)
    import yaml
    raw_kube=Path(a.platform_plan).parent/'bound/kubeconfig';kube=yaml.safe_load(raw_kube.read_text());validate_kube_endpoint(kube,basis['kind_cluster'])
    shutil.copyfile(raw_kube,work/'bound/original-kubeconfig.yaml');dump(work/'bound/kubeconfig',kube)
    for p in (work/'bound').iterdir():p.chmod(0o600)
    dependencies=host_dependencies.capture(a.python,original['env']['PATH']);dump(work/'bound/host-dependencies.json',dependencies)
    tools={name:host_dependencies.path_binding(row['path']) for name,row in basis['tools'].items()}
    assert tools['python']['path']==str(a.python.absolute())
    tool_elf={name:host_dependencies.elf_inputs(row['realpath']) for name,row in tools.items() if name in ('kubectl','kind','compose-plugin')}
    assert all(v['interpreter'] is None and not v['needed'] for v in tool_elf.values())
    sock=Path('/run/docker.sock').stat();assert stat.S_ISSOCK(sock.st_mode)
    facts=cluster_facts(tools['kubectl']['path'],work/'bound/kubeconfig',basis['kind_node'],tag,a.broker_image,a.proxy_image,a.name+'-kind')
    assert facts['selected_images']['hub']['id']==a.image
    config=work/'bound/docker-config';(config/'cli-plugins').mkdir(parents=True,mode=0o700);dump(config/'config.json',{})
    shutil.copyfile(tools['compose-plugin']['path'],config/'cli-plugins/docker-compose');(config/'cli-plugins/docker-compose').chmod(0o755)
    env=host_dependencies.child_environment(original['env'],dependencies,work/'bound',work/'results/pycache',Path('/run/docker.sock'));env['DOCKER_CONFIG']=str(config)
    jobs=[]
    for platform,port,relay in [('compose',a.compose_port,a.compose_relay_port),('k8s',a.kind_port,a.kind_relay_port)]:
        name=a.name+('-compose' if platform=='compose' else '-kind')
        argv=[str(a.python),'-s','-B',str(work/'frozen/tests/kafka_final_platform.py'),'--platform',platform,'--name',name,'--image',a.image,
            '--context',str(work/'context'),'--acceptance-report',str(work/'bound/admission.json'),'--work',str(work/(platform+'-work')),
            '--report',str(work/(platform+'.json')),'--port',str(port),'--model-only','--model-relay-port',str(relay)]
        if platform=='k8s':argv+=['--kubectl',tools['kubectl']['path'],'--kubeconfig',str(work/'bound/kubeconfig'),'--kind-node',basis['kind_node'],
            '--cluster-image',tag,'--broker-image',a.broker_image,'--proxy-image',a.proxy_image]
        jobs.append({'name':platform,'owned_name':name,'port':port,'relay_port':relay,'argv':argv})
    shutil.copyfile(__file__,work/'driver.py');own_matrix(work)
    plan={'schema':'adhd/deployed-model-only-plan@1','status':'UNSTARTED_ROOT_REVIEW_AND_MODEL_HANDOFF_REQUIRED','driver_sha256':sha(work/'driver.py'),
        'parent_pycache_prefix':str(work/'parent-cache'),'artifact_sha256':artifact,'image':a.image,'canonical_manifest_sha256':sha(a.context/'manifest.json'),
        'admission_sha256':a.admission_sha256,'compiled_binding':compiled,'frozen_inputs':tree(work/'frozen'),'bound_inputs':tree(work/'bound'),'context_inputs':tree(work/'context'),
        'tools':tools,'static_tool_elf':tool_elf,'docker_socket':{'path':'/run/docker.sock','identity':[sock.st_dev,sock.st_ino]},'env':env,
        'facts':facts,'kube_endpoint':json_kube_endpoint(work/'bound/kubeconfig',basis['kind_cluster']),'cluster_image':tag,'broker_image':a.broker_image,'proxy_image':a.proxy_image,
        'jobs':jobs,'parallelism':1,'automatic_retries':0,'original_corpus_child_timeout':240,'maximum_upstream_posts_per_platform':12,'maximum_upstream_posts_total':24,
        'lease_path':str(a.lease_path),'expected_model':{'container_id':'190996d1327f998b8f6a50510421800b7cf16f1cba8484baeba0ecd4b94e8cdd','image_config_identity':'sha256:3d8ebe07d1b64ceab33030e09a9076e77754d3ed70a19fb0c36b0168d6b94d6f','name':'/adhd-model-model-1'},
        'live_specification_drift':drift,'cooperative_all_agent_handoff_required':True,'resources_apps_compilers_providers_started_during_preparation':0,
        'scope':'Actual compiled packaged app Compose then Kind: original hot filtered match/nonmatch/offline-resume, backend cited fact query, BLUE raw progress and foreign/private canaries. Separate from baseline21, SDK69, secured TLS, production/HA. Cooperative lease is not egress isolation.'}
    dump(work/'plan.json',plan);print(json.dumps({'plan':str(work/'plan.json'),'sha256':sha(work/'plan.json'),'frozen_files':len(plan['frozen_inputs'])}))


def qualified(child,plan):
    assert child['passed'] is True and child['model_only_requested'] is True
    assert child['artifact_sha256']==plan['artifact_sha256'] and child['image_config_digest']==child['runtime_hub_image_config_digest']==plan['image']
    assert child['cleanup']['resources_independently_absent'] is True and not child['cleanup']['failures']
    model=child['optional_model'];assert model['passed'] and model['same_packaged_vm_before_after_hot_changes']
    assert model['image_config_digest']==plan['image'] and model['artifact_sha256']==plan['artifact_sha256']
    assert model['budget']['upstream_attempts']<=12 and model['cleanup']['listener_independently_absent']
    assert child['model_relay_cleanup']['confirmed'] is True
    return True


def execute(work,expected):
    assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
    from model_service_lease import acquire,inspect_model,regular
    # Root's separate all-agent handoff is still required. Never probe/warmup the model.
    fd=None;inode=None;before=None;after=None;rows=[];primary=None;cleanup=[]
    try:
        fd,inode=acquire(Path(plan['lease_path']));before=inspect_model(plan['expected_model'],plan['tools']['docker']['path'])
        claim_execution(work,expected,plan['driver_sha256'])
        for job in plan['jobs']:
            verify(work,plan,preflight=False);row={'name':job['name'],'attempted':True,'started':False,'exit_code':None,'passed':False};rows.append(row)
            with (work/(job['name']+'.log')).open('xb') as log:
                process=subprocess.Popen(job['argv'],cwd=work/'results',env=plan['env'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                row.update(started=True,child_pid=process.pid);row['exit_code']=wait_owned_child(process)
            assert row['exit_code']==0;child=json.loads((work/(job['name']+'.json')).read_text());qualified(child,plan)
            row.update(passed=True,report_sha256=sha(work/(job['name']+'.json')),log_sha256=sha(work/(job['name']+'.log')))
    except BaseException as error:primary=error;raise
    finally:
        if before:
            try:
                after=inspect_model(plan['expected_model'],plan['tools']['docker']['path']);assert {k:v for k,v in before.items() if k!='metadata_client'}=={k:v for k,v in after.items() if k!='metadata_client'}
            except BaseException as error:cleanup.append(type(error).__name__)
        if fd is not None:
            try:info=regular(Path(plan['lease_path']),True);assert (info.st_dev,info.st_ino)==inode
            except BaseException as error:cleanup.append(type(error).__name__)
            finally:
                try:os.close(fd)
                except BaseException as error:cleanup.append(type(error).__name__)
        try:verify(work,plan,preflight=False);unchanged=True
        except BaseException as error:unchanged=False;cleanup.append(type(error).__name__)
        for row in rows:
            for suffix,key in [('.json','report_sha256'),('.log','log_sha256')]:
                path=work/(row['name']+suffix)
                if path.is_file():row[key]=sha(path)
        unrun=[j['name'] for j in plan['jobs'] if not any(r['name']==j['name'] and r['started'] for r in rows)]
        result={'passed':primary is None and not cleanup and not unrun and all(r['passed'] for r in rows),'plan_sha256':expected,'image':plan['image'],'artifact_sha256':plan['artifact_sha256'],
            'rows':rows,'unrun_platforms':unrun,'failure_type':type(primary).__name__ if primary else None,'cleanup_failures':cleanup,'inputs_unchanged':unchanged,
            'model_before':before,'model_after':after,'lease_acquired':fd is not None,'scope':plan['scope']}
        dump(work/'matrix.json',result)
        if cleanup:
            if primary:primary.add_note('Model matrix cleanup: '+','.join(cleanup))
            else:raise AssertionError('Model matrix cleanup: '+','.join(cleanup))


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--prepare',action='store_true');m.add_argument('--execute',action='store_true')
    p.add_argument('--work',type=Path,required=True);p.add_argument('--plan-sha256')
    for name in ('repo-root','context','admission','original-plan','platform-plan','lease-path'):p.add_argument('--'+name,type=Path)
    for name in ('image','admission-sha256','broker-image','proxy-image','cluster-image','name'):p.add_argument('--'+name)
    p.add_argument('--python',type=Path,default=Path(sys.executable).absolute())
    for name,default in [('compose-port',18970),('kind-port',18971),('compose-relay-port',18972),('kind-relay-port',18973)]:p.add_argument('--'+name,type=int,default=default)
    a=p.parse_args()
    if _STAGED:assert a.work.absolute()==Path(__file__).absolute().parent
    if a.prepare:prepare(a)
    else:assert a.plan_sha256;execute(a.work.absolute(),a.plan_sha256)


if __name__=='__main__':main()
