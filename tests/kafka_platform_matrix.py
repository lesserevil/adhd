"""Prepare/review, then explicitly execute Compose and Kind qualification serially.

Provisioning Kind, loading/tagging images, model relays and credentials are owned
by the operator. A historical image38 binding plan is always execution-denied.
"""
import sys
sys.dont_write_bytecode=True
_STAGED=__file__.rsplit('/',1)[-1]=='driver.py'
if _STAGED:
    assert sys.flags.isolated, 'Run the frozen driver with python -I'
elif __name__=='__main__':
    assert '--execute' not in sys.argv, 'Execute only the reviewed frozen driver.py with python -I'
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from urllib.parse import urlsplit


def staged_imports(path,expected):
    """Authenticate the adjacent full helper tree before importing its code."""
    driver=Path(path).absolute();work=driver.parent;plan_file=work/'plan.json'
    assert driver.resolve(strict=True)==driver and not driver.is_symlink()
    assert plan_file.is_file() and not plan_file.is_symlink() and plan_file.stat().st_size<=1048576
    assert hashlib.sha256(plan_file.read_bytes()).hexdigest()==expected
    plan=json.loads(plan_file.read_bytes())
    assert hashlib.sha256(driver.read_bytes()).hexdigest()==plan['driver_sha256']
    frozen=work/'frozen';assert frozen.resolve(strict=True)==frozen and frozen.is_dir()
    files=set();directories=set();expected_dirs=set()
    for name in plan['frozen_inputs']:
        relative=Path(name);assert not relative.is_absolute() and str(relative)==name and '..' not in relative.parts
        expected_dirs.update(str(p) for p in relative.parents if str(p)!='.')
    for member in frozen.rglob('*'):
        info=member.lstat();assert not stat.S_ISLNK(info.st_mode)
        name=str(member.relative_to(frozen))
        if stat.S_ISDIR(info.st_mode):directories.add(name)
        else:
            assert stat.S_ISREG(info.st_mode);files.add(name)
            assert hashlib.sha256(member.read_bytes()).hexdigest()==plan['frozen_inputs'].get(name)
    assert files==set(plan['frozen_inputs']) and directories==expected_dirs
    return str(frozen/'tests')


if _STAGED:
    assert '--execute' in sys.argv and '--prepare' not in sys.argv and sys.argv.count('--plan-sha256')==1
    _expected=sys.argv[sys.argv.index('--plan-sha256')+1]
    sys.path.insert(0,staged_imports(__file__,_expected))

import yaml

from image_qualification_inputs import reviewed_payload, freeze_inputs, verify_frozen_inputs
from multi_image_core_matrix import claim_execution, report_passed

BASELINE_IMAGE='sha256:b12e75c09ccd213f06739f7fdd998d675670491c31677143fecaceab7823e0f0'
BASELINE_ARTIFACT='1741225b1a276770ec9f6631e63fe8646ee5f22808fad8a5acfe67a8aed11bd7'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def file_tree(path):
    path=Path(path).absolute()
    assert path.resolve(strict=True)==path and path.is_dir() and not path.is_symlink()
    result={}
    for member in sorted(path.rglob('*')):
        info=member.lstat();assert not stat.S_ISLNK(info.st_mode)
        if stat.S_ISDIR(info.st_mode):continue
        assert stat.S_ISREG(info.st_mode)
        result[str(member.relative_to(path))]=sha(member)
    verify_frozen_inputs(path,result)
    return result


def executable(path):
    path=Path(path).absolute();real=path.resolve(strict=True)
    assert real.is_file() and os.access(path,os.X_OK)
    return {'path':str(path),'realpath':str(real),'sha256':sha(real)}


def kube_endpoint(path,cluster):
    path=Path(path);assert not path.is_symlink() and path.stat().st_size<=1048576
    value=yaml.safe_load(path.read_text())
    assert value['kind']=='Config' and value['apiVersion']=='v1'
    assert all(len(value[key])==1 for key in ('clusters','contexts','users'))
    context=value['contexts'][0];selected=value['clusters'][0];user=value['users'][0]
    assert value['current-context']==context['name']
    assert context['context']['cluster']==selected['name']=='kind-'+cluster
    assert context['context']['user']==user['name']
    assert set(user['user'])=={'client-certificate-data','client-key-data'}, 'No external auth executors/files'
    assert all(isinstance(v,str) and v for v in user['user'].values())
    assert selected['cluster'].get('certificate-authority-data')
    assert set(selected['cluster'])=={'server','certificate-authority-data'}, 'No proxy, TLS override or external CA files'
    endpoint=urlsplit(selected['cluster']['server'])
    assert endpoint.scheme=='https' and endpoint.hostname in ('127.0.0.1','::1') and endpoint.port
    assert not endpoint.username and not endpoint.password and not endpoint.path and not endpoint.query and not endpoint.fragment
    return {'server':selected['cluster']['server'],'host':endpoint.hostname,'port':endpoint.port,'cluster':cluster}


def verify(work,plan):
    assert sha(Path(__file__))==sha(work/'driver.py')==plan['driver_sha256'], 'Actual driver differs'
    verify_frozen_inputs(work/'frozen',plan['frozen_inputs'])
    verify_frozen_inputs(Path(plan['original_context']),plan['context_inputs'])
    verify_frozen_inputs(work/'context',plan['context_inputs'])
    assert all(sha(work/name)==digest for name,digest in plan['bound_inputs'].items())
    assert all(Path(row['path']).resolve(strict=True)==Path(row['realpath']) and sha(row['realpath'])==row['sha256'] for row in plan['tools'].values())
    assert Path(sys.executable).absolute()==Path(plan['tools']['python']['path'])
    assert Path('/proc/self/exe').resolve()==Path(plan['tools']['python']['realpath'])
    assert kube_endpoint(work/'bound/kubeconfig',plan['kind_cluster'])==plan['kube_endpoint']
    current=Path(plan['docker_socket']).stat()
    assert stat.S_ISSOCK(current.st_mode) and [current.st_dev,current.st_ino]==plan['docker_socket_identity']
    return True


def prepare(args):
    assert all(getattr(args,key) for key in ('repo_root','context','admission_manifest','acceptance_report',
        'kubeconfig','compose_plugin','kubectl','kind','image','admission_sha256','kind_cluster','kind_node','cluster_image','name'))
    root=args.repo_root.resolve();work=args.work.resolve();assert not work.exists()
    assert re.fullmatch('sha256:[a-f0-9]{64}',args.image)
    assert re.fullmatch('adhd-final-[a-z0-9-]{1,30}',args.name)
    assert re.fullmatch('adhd-[a-z0-9-]{1,35}',args.kind_cluster)
    assert args.kind_node==args.kind_cluster+'-control-plane'
    assert args.compose_port!=args.kind_port
    assert args.cluster_image.startswith('adhd-hub:') and re.fullmatch(r'[a-zA-Z0-9_.:-]+',args.cluster_image)
    context=args.context.resolve();manifest=json.loads((context/'manifest.json').read_text());artifact=manifest['files']['hub.exs']
    selected=reviewed_payload(context/'manifest.json',args.admission_manifest,args.admission_sha256,args.image,artifact)
    acceptance=json.loads(args.acceptance_report.read_text());assert acceptance['passed'] is True and acceptance['artifact_sha256']==artifact
    if args.execution_ready:
        assert args.image!=BASELINE_IMAGE and artifact!=BASELINE_ARTIFACT, 'Historical38 binding cannot authorize execution'
    endpoint=kube_endpoint(args.kubeconfig,args.kind_cluster)
    work.mkdir(parents=True,mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
    helpers=args.helper_root.resolve() if args.helper_root else root
    inputs,drift=freeze_inputs(helpers,frozen,selected['specifications'])
    for source in sorted((helpers/'deploy').rglob('*')):
        assert not source.is_symlink()
        if source.is_dir():continue
        assert source.is_file();target=frozen/source.relative_to(helpers);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target);inputs[str(target.relative_to(frozen))]=sha(target)
    verify_frozen_inputs(frozen,inputs)
    context_inputs=file_tree(context);shutil.copytree(context,work/'context')
    (work/'bound').mkdir(mode=0o700)
    for source,name in ((args.admission_manifest,'admission.json'),(args.acceptance_report,'acceptance.json'),(args.kubeconfig,'kubeconfig')):
        shutil.copyfile(source,work/'bound'/name);(work/'bound'/name).chmod(0o600)
    shutil.copyfile(Path(__file__),work/'driver.py')
    runtime=work/'runtime';runtime.mkdir(mode=0o700)
    config=runtime/'docker-config';(config/'cli-plugins').mkdir(parents=True,mode=0o700)
    dump(config/'config.json',{})
    shutil.copyfile(args.compose_plugin,config/'cli-plugins/docker-compose');(config/'cli-plugins/docker-compose').chmod(0o755)
    tools={name:executable(getattr(args,name.replace('-','_'))) for name in ('python','docker','compose-plugin','kubectl','kind')}
    docker_socket=args.docker_socket.resolve();info=docker_socket.stat();assert stat.S_ISSOCK(info.st_mode)
    jobs=[]
    for platform,port in [('compose',args.compose_port),('k8s',args.kind_port)]:
        assert 1024<=port<=65535
        name=args.name+'-'+('compose' if platform=='compose' else 'kind')
        argv=[tools['python']['path'],str(frozen/'tests/kafka_final_platform.py'),'--platform',platform,'--name',name,
            '--image',args.image,'--context',str(work/'context'),'--acceptance-report',str(work/'bound/acceptance.json'),
            '--work',str(work/(platform+'-work')),'--report',str(work/(platform+'.json')),'--port',str(port),'--selective-recovery']
        if platform=='compose':argv+=['--broker-patch-upgrade']
        else:argv+=['--kubectl',tools['kubectl']['path'],'--kubeconfig',str(work/'bound/kubeconfig'),
            '--kind-node',args.kind_node,'--cluster-image',args.cluster_image]
        jobs.append({'name':platform,'owned_name':name,'argv':argv})
    bound={str(p.relative_to(work)):sha(p) for p in (work/'bound').iterdir()}
    bound.update({str(p.relative_to(work)):sha(p) for p in config.rglob('*') if p.is_file()})
    plan={'schema':'adhd/platform-image-plan@1','execution_allowed':args.execution_ready,'executed':False,
        'scope':'Owned Compose+Kind baseline/replacement/backup/selective restore; no security OAuth, live model, replicated availability, or implicit release qualification',
        'historical_binding_only':not args.execution_ready,'image_config_identity':args.image,'artifact_sha256':artifact,
        'canonical_manifest_sha256':sha(context/'manifest.json'),'admission_sha256':args.admission_sha256,'payload_audit':selected['audit'],
        'target_specifications':{name:hashlib.sha256(body).hexdigest() for name,body in selected['specifications'].items()},
        'live_root_specification_drift':drift,'frozen_inputs':inputs,'original_context':str(context),'context_inputs':context_inputs,
        'bound_inputs':bound,'tools':tools,'kind_node':args.kind_node,'kind_cluster':args.kind_cluster,'cluster_image':args.cluster_image,'kube_endpoint':endpoint,
        'docker_socket':str(docker_socket),'docker_socket_identity':[info.st_dev,info.st_ino],
        'driver_sha256':sha(work/'driver.py'),'jobs':jobs,'parallelism':1,'fail_fast':True,'runs_per_platform':1,
        'runtime_cwd':str(runtime),'outer_child_timeout_seconds':None,'timeout_policy':'Existing harness deadlines only; no driver timeout that could bypass platform cleanup',
        'provision_load_tag_or_relay_operations':False,'live_provider_calls_authorized':False}
    plan['frozen_execute_requires_python_isolated']=True
    dump(work/'plan.json',plan);verify(work,plan)
    print(json.dumps({'prepared':True,'execution_allowed':plan['execution_allowed'],'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json')}))


def environment(work,plan):
    env=os.environ.copy()
    for key in list(env):
        if key.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy') or key in ('DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','DOCKER_CLI_PLUGIN_EXTRA_DIRS'):env.pop(key,None)
    env.update(DOCKER_HOST='unix://'+plan['docker_socket'],DOCKER_CONFIG=str(work/'runtime/docker-config'),
        KUBECONFIG=str(work/'bound/kubeconfig'),PYTHONPATH=str(work/'frozen/tests'),PYTHONDONTWRITEBYTECODE='1',
        PYTHONPYCACHEPREFIX=str(work/'runtime/pycache'),NO_PROXY='127.0.0.1,localhost,::1',
        PATH=str(Path(plan['tools']['python']['path']).parent)+':'+str(Path(plan['tools']['docker']['path']).parent)+':/usr/bin:/bin')
    return env


def preflight(work,plan,env):
    def read(argv):return subprocess.check_output(argv,env=env,stderr=subprocess.PIPE,timeout=30)
    docker=plan['tools']['docker']['path'];node=json.loads(read([docker,'inspect',plan['kind_node']]))[0]
    assert node['State']['Running'] and node['Name']=='/'+plan['kind_node']
    assert node['Config']['Labels']['io.x-k8s.kind.cluster']==plan['kind_cluster']
    ports=node['NetworkSettings']['Ports']['6443/tcp'];endpoint=plan['kube_endpoint']
    assert len(ports)==1 and ports[0]['HostIp']==endpoint['host'] and int(ports[0]['HostPort'])==endpoint['port']
    assert json.loads(read([docker,'image','inspect',plan['image_config_identity']]))[0]['Id']==plan['image_config_identity']
    assert json.loads(read([docker,'image','inspect',plan['cluster_image']]))[0]['Id']==plan['image_config_identity']
    for job in plan['jobs']:
        if job['name']=='compose':
            for kind in ('container','network','volume'):
                command=[docker,'ps','-aq'] if kind=='container' else [docker,kind,'ls','-q']
                assert not read(command+['--filter','label=com.docker.compose.project='+job['owned_name']]).strip()
        else:
            assert not read([plan['tools']['kubectl']['path'],'--kubeconfig',str(work/'bound/kubeconfig'),
                'get','namespace',job['owned_name'],'--ignore-not-found','-o','json']).strip()


def execute(work,expected):
    assert expected and sha(work/'plan.json')==expected
    plan=json.loads((work/'plan.json').read_text())
    assert plan['execution_allowed'] is True and not plan['historical_binding_only'], 'Binding-only historical plan cannot execute'
    assert plan['image_config_identity']!=BASELINE_IMAGE and plan['artifact_sha256']!=BASELINE_ARTIFACT
    verify(work,plan);claim_execution(work,expected,plan['driver_sha256'])
    env=environment(work,plan)
    results=[];failure=None
    try:
        preflight(work,plan,env)
        for job in plan['jobs']:
            verify(work,plan);report=work/(job['name']+'.json');log=work/(job['name']+'.log')
            assert not report.exists() and not log.exists() and not (work/(job['name']+'-work')).exists()
            row={'name':job['name'],'attempted':True,'started':False,'process_exit_code':None,'passed':False,'report_sha256':None,'log_sha256':None}
            results.append(row)
            print('START',job['name'],flush=True)
            with log.open('x') as output:child=subprocess.run(job['argv'],cwd=plan['runtime_cwd'],env=env,stdout=output,stderr=subprocess.STDOUT)
            row['started']=True  # A returned child outcome witnesses actual creation.
            qualified=child.returncode==0 and report_passed(report)
            value=json.loads(report.read_text()) if report_passed(report) else {}
            if qualified:
                qualified=(value['artifact_sha256']==plan['artifact_sha256'] and value['image_config_digest']==plan['image_config_identity']
                    and value['selective_recovery_requested'] is True and value['cleanup']['resources_independently_absent'] is True and not value['cleanup']['failures'])
            row.update(process_exit_code=child.returncode,passed=qualified,
                report_sha256=sha(report) if report.exists() else None,log_sha256=sha(log))
            print('DONE',job['name'],qualified,flush=True)
            if not qualified:break
    except BaseException as error:failure=type(error).__name__;raise
    finally:
        try:verify(work,plan);unchanged=True
        except BaseException:unchanged=False
        for row in results:
            for field,suffix in (('report_sha256','.json'),('log_sha256','.log')):
                path=work/(row['name']+suffix)
                if path.is_file():row[field]=sha(path)
        executed=[row['name'] for row in results if row['started']]
        unrun=[job['name'] for job in plan['jobs'] if job['name'] not in executed]
        dump(work/'matrix.json',{'schema':'adhd/platform-image-matrix@1','passed':not failure and unchanged and not unrun and all(row['passed'] for row in results),
            'scope':plan['scope'],'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],
            'plan_sha256':expected,'frozen_inputs_unchanged':unchanged,'failure_type':failure,'results':results,
            'planned_platforms':[job['name'] for job in plan['jobs']],'attempted_platforms':[row['name'] for row in results],
            'executed_platforms':executed,'unrun_platforms':unrun})
    return 0 if json.loads((work/'matrix.json').read_text())['passed'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    p.add_argument('--work',type=Path,required=True);p.add_argument('--plan-sha256')
    for name in ('repo-root','helper-root','context','admission-manifest','acceptance-report','kubeconfig','compose-plugin','kubectl','kind'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--python',type=Path,default=Path(sys.executable));p.add_argument('--docker',type=Path,default=Path('/usr/bin/docker'))
    p.add_argument('--docker-socket',type=Path,default=Path('/var/run/docker.sock'))
    for name in ('image','admission-sha256','kind-cluster','kind-node','cluster-image','name'):p.add_argument('--'+name)
    p.add_argument('--compose-port',type=int,default=18890);p.add_argument('--kind-port',type=int,default=18891)
    p.add_argument('--execution-ready',action='store_true',help='Only after fresh successor admission and owned Kind provisioning; still requires separate reviewed execute plan digest')
    args=p.parse_args()
    if _STAGED:assert args.work.absolute()==Path(__file__).absolute().parent
    if args.prepare:prepare(args)
    else:sys.exit(execute(args.work.resolve(),args.plan_sha256))


if __name__=='__main__':main()
