#!/usr/bin/env python3
"""Closed one-shot actual protocol exports/conservation/wire qualification.

The original tests own readiness and request deadlines. No outer timeout,
automatic retry, source substitution, public snapshot write or broker mutation
is introduced here. The operator reviews a complete plan before --execute.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import socket
import stat
import subprocess
import sys
from urllib.request import urlopen


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x')as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def inventory(root):
    root=Path(root);assert root.resolve(strict=True)==root and root.is_dir()
    files={};dirs=[]
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir():dirs.append(str(path.relative_to(root)))
        else:
            st=path.lstat();assert stat.S_ISREG(st.st_mode) and st.st_nlink==1
            files[str(path.relative_to(root))]=sha(path)
    return {'files':files,'directories':dirs}


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def bootstrap(work,expected):
    assert work.resolve(strict=True)==work and sha(work/'plan.json')==expected
    plan=json.loads((work/'plan.json').read_bytes())
    assert plan['schema']=='adhd/protocol22-qualification@1' and plan['work']==str(work)
    assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
    cache=work/'python-cache';assert sys.pycache_prefix==str(cache) and cache.resolve(strict=True)==cache and not list(cache.iterdir())
    assert Path(__file__).resolve()==Path(__file__).absolute() and sha(__file__)==plan['driver_sha256']
    for name in ('frozen','bound'):assert inventory(work/name)==plan[name]
    sys.path.insert(0,str(work/'frozen/tests'))
    import image_host_dependencies as host
    closure=json.loads((work/'bound/host-closure.json').read_bytes());host.verify(closure)
    assert str(Path(sys.executable).absolute())==closure['python_executable']
    sites=list(Path(closure['python_executable']).parent.parent.glob('lib/python*/site-packages'))
    assert len(sites)==1 and any(sites[0].is_relative_to(Path(p))for p in closure['roots'])
    sys.path.insert(1,str(sites[0]))
    return plan,closure,host


def verify(work,plan,host,closure):
    for name in ('frozen','bound'):assert inventory(work/name)==plan[name]
    assert sha(__file__)==plan['driver_sha256']
    host.verify(closure)
    for name,expected in plan['externals'].items():assert sha(name)==expected
    assert inventory(work/'runtime/docs')==plan['runtime_docs']
    assert inventory(work/'runtime/scripts')==plan['runtime_scripts']
    assert plan['automatic_retries']==0 and plan['parallelism']==1 and plan['outer_timeout'] is None
    assert plan['artifact_sha256']=='ffb14b231c59c44a517e0553d320ffaed7fc2c8ffe1682a19d356f6f82dc6d2a'
    from protocol22_publication_plan import target_binding
    target=target_binding(argparse.Namespace(**plan['target_arguments']))
    assert target==plan['source_binding']
    socket_path=Path(plan['docker_socket']);assert socket_path.resolve(strict=True)==socket_path
    st=socket_path.stat();assert stat.S_ISSOCK(st.st_mode) and [st.st_dev,st.st_ino]==plan['docker_socket_identity']
    if 'qualified_export_prefix' in plan:verify_export_prefix(work,plan)


def verify_export_prefix(work,plan):
    prefix=plan['qualified_export_prefix']
    assert sha(work/'bound/prior-plan.json')==prefix['prior_plan_sha256']
    assert sha(work/'bound/prior-result.json')==prefix['prior_false_result_sha256']
    before=json.loads((work/'bound/prior-plan.json').read_bytes())
    result=json.loads((work/'bound/prior-result.json').read_bytes())
    assert result['passed'] is False and result['plan_sha256']==prefix['prior_plan_sha256']
    assert result['artifact_sha256']==before['artifact_sha256']==plan['artifact_sha256']
    assert [r['name']for r in result['stages']if r['passed'] is True]==['export-schema','export-openapi']
    assert not result['cleanup_errors']
    assert [r['name']for r in plan['stages']]==['conservation26','scope-inventory','wire8']
    for index,name in enumerate(('schema.json','openapi.json')):
        original=before['stages'][index]
        assert original['kind']=='export' and original['name']==result['stages'][index]['name'] and result['stages'][index]['exit_code']==0
        assert sha(original['stdout'])==sha(work/'bound/exports'/name)==prefix['exports'][name]


def broker(plan):
    for expected in plan['broker_containers']:
        rows=json.loads(subprocess.check_output([plan['docker'],'inspect',expected['Id']]))
        assert len(rows)==1;row=rows[0]
        fields={k:row[k]for k in ('Id','Name','Image','RestartCount')}
        fields['StartedAt']=row['State']['StartedAt'];fields['Running']=row['State']['Running']
        fields['Networks']=row['NetworkSettings']['Networks'];fields['Ports']=row['NetworkSettings']['Ports']
        fields['Labels']=row['Config']['Labels']
        assert fields==expected and fields['Running'] is True
        assert fields['Labels']['com.docker.compose.project']=='adhd-event-qual'
    with urlopen(plan['rest_url']+'/v3/clusters',timeout=5)as response:value=json.load(response)
    assert value['data'][0]['cluster_id']==plan['cluster_id']


def execute(work,plan,host,closure):
    verify(work,plan,host,closure)
    from acme_image_flow import claim_once
    claim_once(work/'execution.started',sha(work/'plan.json'))
    assert not (work/'result.json').exists()
    os.environ.clear();os.environ.update(plan['environment'])
    custody=load(work/'bound/custody.py','protocol_custody');ledger=custody.ChildLedger(work/'custody.json');ledger.install()
    result={'schema':'adhd/protocol22-qualification-result@1','passed':False,'stages':[],'unrun':[s['name']for s in plan['stages']]}
    primary=None;previous=os.getcwd();os.chdir(work/'runtime')
    try:
        broker(plan)
        # Original test itself owns the shared absolute foundation flock.
        with socket.socket()as probe:probe.bind(('127.0.0.1',8766))
        for stage in plan['stages']:
            verify(work,plan,host,closure)
            row={'name':stage['name'],'passed':False};result['stages'].append(row);result['unrun'].remove(stage['name'])
            try:
                if stage['kind']=='export':
                    with Path(stage['stdout']).open('xb')as out,Path(stage['stderr']).open('xb')as err:
                        child=subprocess.run(stage['argv'],stdout=out,stderr=err,check=False)
                    row['exit_code']=child.returncode;assert child.returncode==0
                    json.loads(Path(stage['stdout']).read_bytes())
                else:
                    old=sys.argv;sys.argv=[stage['script'],*stage['arguments']]
                    try:runpy.run_path(stage['script'],run_name='__main__')
                    finally:sys.argv=old
                if stage.get('report'):
                    report=json.loads(Path(stage['report']).read_bytes());assert report['passed'] is True
                    checks=report.get('actual_vectors',report.get('cases'));assert len(checks)==stage['checks'] and all(r['passed']is True for r in checks)
                    row['report_sha256']=sha(stage['report']);row['checks']=len(checks)
                row['passed']=True
            except BaseException as error:row['failure_type']=type(error).__name__;raise
        result['passed']=not result['unrun'] and all(row['passed']for row in result['stages'])
    except BaseException as error:primary=error;result['failure_type']=type(error).__name__;raise
    finally:
        os.chdir(previous);cleanup=[]
        for name,action in [('broker',lambda:broker(plan)),('inputs',lambda:verify(work,plan,host,closure)),('children',ledger.close),('nonce',lambda:custody.close_nonce_processes(plan['nonce']))]:
            try:
                value=action()
                if name in ('children','nonce'):assert not value,'Unexpected surviving owned processes'
            except BaseException as error:
                cleanup.append({'scope':name,'type':type(error).__name__})
                if primary:primary.add_note('Protocol cleanup '+name+': '+type(error).__name__)
        result['cleanup_errors']=cleanup;result['passed']=result['passed'] and not cleanup
        result['plan_sha256']=sha(work/'plan.json');result['artifact_sha256']=plan['artifact_sha256']
        result['custody_sha256']=sha(work/'custody.json')if(work/'custody.json').exists()else None
        result['scope']='Actual accepted source exports26 conservation vectors/full8 wiregroups/scope inventory. No published JSON writes, ACME listeners, image or public-issuer qualification.'
        try:write(work/'result.json',result)
        except BaseException as error:
            if primary:primary.add_note('Protocol evidence: '+type(error).__name__)
            else:raise
        if cleanup and primary is None:raise AssertionError('Protocol cleanup/input custody failed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',required=True,type=Path);p.add_argument('--plan-sha256',required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--verify-only',action='store_true');mode.add_argument('--execute',action='store_true')
    args=p.parse_args();work=args.work.absolute();plan,closure,host=bootstrap(work,args.plan_sha256)
    verify(work,plan,host,closure)
    if args.execute:execute(work,plan,host,closure)
    else:print(json.dumps({'verified':True,'executed':False,'stages':len(plan['stages'])}))


if __name__=='__main__':main()
