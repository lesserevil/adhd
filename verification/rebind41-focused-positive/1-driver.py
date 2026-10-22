"""Closed, once-only two-case rebind diagnostic; preparation never starts children."""
import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def plain(path):
    path=Path(path).absolute();s=path.lstat()
    assert path.resolve(strict=True)==path and stat.S_ISREG(s.st_mode) and s.st_nlink==1
    return path

def inventory(root):
    assert root.resolve(strict=True)==root and not root.is_symlink()
    files={};dirs=[]
    for path in sorted(root.rglob('*')):
        s=path.lstat();assert not stat.S_ISLNK(s.st_mode)
        if stat.S_ISDIR(s.st_mode):dirs.append(str(path.relative_to(root)))
        else:plain(path);files[str(path.relative_to(root))]=sha(path)
    return {'files':files,'directories':dirs}

def durable(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def verify_parent(plan):
    parent=Path(plan['parent_work']);basis=json.loads(plain(parent/'plan.json').read_text())
    assert sha(parent/'plan.json')==plan['parent_plan_sha256']
    assert sha(plain(parent/'matrix.json'))==plan['parent_false_matrix_sha256']
    for key,directory in [('frozen_inputs','frozen'),('component_inputs','component'),('context_inputs','context')]:
        assert inventory(parent/directory)['files']==basis[key]
    assert inventory(parent/'bound')['files']=={str(Path(n).relative_to('bound')):v for n,v in basis['bound_inputs'].items()}
    helper=parent/'frozen/tests/image_recovery_remaining_matrix.py'
    assert sha(helper)==sha(plain(parent/'driver.py'))==basis['driver_sha256']
    sys.path.insert(0,str(helper.parent))
    try:
        spec=importlib.util.spec_from_file_location('verified_rebind_parent',helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        assert module.verify(parent,basis)
        return module
    finally:sys.path.pop(0)

def verify(work,plan):
    assert sha(plain(__file__))==sha(plain(work/'driver.py'))==plan['driver_sha256']
    assert [row['name'] for row in plan['cases']]==['rebind','rebind-hostile']
    for directory,expected in plan['shared_inputs'].items():
        assert inventory(Path(plan['metadata_root'])/directory)==expected
    for row in plan['cases']:
        assert sha(plain(work/row['plan_file']))==row['plan_sha256']
        child=json.loads((work/row['plan_file']).read_text());assert child['job']==row['job']
        assert child['env']==row['env'] and child['runtime_cwd']==row['runtime_cwd']
        for key in ['image_config_identity','artifact_sha256','admission_manifest_sha256','canonical_manifest_sha256']:
            assert child[key]==plan[key]
    return verify_parent(plan)

def preflight(work,expected,unstarted=True):
    assert sha(plain(work/'plan.json'))==expected
    plan=json.loads((work/'plan.json').read_text());module=verify(work,plan)
    if unstarted:
        assert not (work/'execution.started').exists() and not (work/'result.json').exists()
        for row in plan['cases']:assert not list(Path(row['runtime_cwd']).iterdir())
    return plan,module

def prepare(args):
    root=args.metadata_root.absolute();work=args.work.absolute();assert not work.exists()
    cases=[json.loads(plain(root/name/'plan.json').read_text()) for name in ['rebind','rebind-hostile']]
    for case in cases:
        for directory,expected in case['shared_inputs'].items():assert inventory(root/directory)['files']==expected
        assert not list(Path(case['runtime_cwd']).iterdir())
    # Validate parent before creating the prepared controller directory.
    parent_module=verify_parent(cases[0])
    work.mkdir(mode=0o700);shutil.copyfile(__file__,work/'driver.py')
    rows=[]
    for case in cases:
        name=case['job']['name'];target=work/(name+'-plan.json');shutil.copyfile(root/name/'plan.json',target)
        rows.append({'name':name,'plan_file':target.name,'plan_sha256':sha(target),
                     'job':case['job'],'env':case['env'],'runtime_cwd':case['runtime_cwd']})
    plan={k:cases[0][k] for k in ['parent_work','parent_plan_sha256','parent_false_matrix_sha256','image_config_identity','artifact_sha256','admission_manifest_sha256','canonical_manifest_sha256']}
    plan.update(schema='adhd/rebind-diagnostic-once@1',prepared=True,execution_started=False,
        driver_sha256=sha(work/'driver.py'),metadata_root=str(root),cases=rows,
        shared_inputs={n:inventory(root/n) for n in cases[0]['shared_inputs']},
        scope='Two original full rebind scenarios; no23-prefix borrowing or full25 claim.',
        serial=True,fail_fast=True,automatic_retries=0,root_GO_required=True)
    durable(work/'plan.json',plan)
    print(json.dumps({'prepared':True,'executed':False,'plan_sha256':sha(work/'plan.json')}))

def execute(work,expected):
    assert Path(__file__).name=='driver.py' and sys.flags.isolated and sys.flags.dont_write_bytecode
    plan,module=preflight(work,expected)
    durable(work/'execution.started',{'plan_sha256':expected,'driver_sha256':plan['driver_sha256']})
    result={'passed':False,'scope':plan['scope'],'plan_sha256':expected,'rows':[],
            'unrun':[row['name']for row in plan['cases']]};primary=None
    try:
        for case in plan['cases']:
            verify(work,plan);job=case['job'];row={'name':case['name'],'passed':False,'started':False};result['rows'].append(row)
            start=time.monotonic()
            try:
                with (work/(case['name']+'.stdout')).open('xb')as out,(work/(case['name']+'.stderr')).open('xb')as err:
                    process=subprocess.Popen(job['argv'],cwd=case['runtime_cwd'],env=case['env'],stdout=out,stderr=err,start_new_session=True)
                    row.update(started=True,child_pid=process.pid);result['unrun'].remove(case['name'])
                    row['exit_code']=module.wait_owned_child(process)
                # Preserve exit and all available evidence even when the child failed before writing a report.
                for key in ['report','cleanup_report']:
                    path=Path(job[key]);row[key+'_sha256']=sha(path)if path.exists()else None
                assert row['exit_code']==0,'Child failed; inspect original stderr before absent report'
                child=json.loads(Path(job['report']).read_text());cleanup=json.loads(Path(job['cleanup_report']).read_text())
                assert child['passed']is True and cleanup['passed']is True
                assert child['artifact_sha256']==plan['artifact_sha256']
                assert all(image['closed']for image in cleanup['images'])and cleanup['owned_native_processes_absent']
                for image in cleanup['images']:
                    starts={v['container_id']for v in image['events']if v['action']=='started'}
                    if starts:
                        e=image['static_compiled_cache'];assert e['cache_modules']==59 and e['cache_files']==62 and e['source_files']==59 and e['static_toolchain_anchors']==4 and e['dynamic_VM_anchor_observed_here']is False
                        assert starts<={v['container_id']for v in image['compiled_launches']}
                        assert all(v['observed_absent']for v in image['payload_probe_lifecycle'])
                verify(work,plan);row['passed']=True
            except BaseException as error:row['failure_type']=type(error).__name__;raise
            finally:row['elapsed_seconds']=time.monotonic()-start
        assert not result['unrun'];result['passed']=True
    except BaseException as error:primary=error;result['failure_type']=type(error).__name__;raise
    finally:
        try:durable(work/'result.json',result)
        except BaseException as error:
            if primary is not None:primary.add_note('Diagnostic evidence failure: '+type(error).__name__)
            else:raise

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for name in ['prepare','verify-only','execute']:g.add_argument('--'+name,action='store_true')
    p.add_argument('--work',type=Path,required=True);p.add_argument('--metadata-root',type=Path);p.add_argument('--plan-sha256');a=p.parse_args()
    if a.prepare:prepare(a)
    elif a.verify_only:preflight(a.work.absolute(),a.plan_sha256);print('VERIFIED; no runtime')
    else:execute(a.work.absolute(),a.plan_sha256)
if __name__=='__main__':main()
