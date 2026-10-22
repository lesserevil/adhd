"""Read-only full25 terminal audit. Never starts/stops apps or changes receipts.

Run only after root has confirmed the driver terminal. Docker use is limited to
inspect; publication writes a NEW safe evidence directory after all audit checks.
"""
import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def plain(path):
    path=Path(path).absolute();s=path.lstat()
    assert path.resolve(strict=True)==path and stat.S_ISREG(s.st_mode)and s.st_nlink==1
    return path

def files(root):
    actual={}
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():plain(path);actual[str(path.relative_to(root))]=sha(path)
    return actual

def authoritative_absence(result,identifier):
    forms=['error: no such object: ','Error: No such object: ',
           'Error: No such container: ','Error response from daemon: No such container: ']
    return result.returncode==1 and result.stdout.strip()==b'[]'and result.stderr.strip()in[(p+identifier).encode()for p in forms]

def owned_resources(values):
    ids=set();names=set();processes=set()
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in('container_id','Id')and isinstance(item,str)and re.fullmatch('[a-f0-9]{64}',item):ids.add(item)
                if key in('owned_name','name')and isinstance(item,str)and re.fullmatch('adhd-[a-z0-9-]+',item):names.add(item)
                if key=='Name'and isinstance(item,str)and re.fullmatch('/adhd-[a-z0-9-]+',item):names.add(item[1:])
                if key in('host_vm_pid','host_container_pid','host_process_pid','child_pid')and type(item)is int and item>1:
                    ticks=next((value[k]for k in('vm_start_time_ticks','start_time_ticks','start_ticks')if k in value),None)
                    processes.add((item,str(ticks)if ticks is not None else None))
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    for value in values:walk(value)
    return ids,names,processes

def process_observations(processes):
    result=[]
    for pid,ticks in sorted(processes,key=lambda x:(x[0],x[1]or'')):
        path=Path('/proc',str(pid),'stat')
        try:actual=path.read_text().rsplit(')',1)[1].split()[19]
        except FileNotFoundError:state='pid_absent'
        else:
            if ticks is None:state='present_without_historical_start_record'
            elif ticks!=actual:state='pid_reused_different_start'
            else:raise AssertionError('Recorded owned process identity remains present')
        result.append({'pid':pid,'recorded_start_ticks':ticks,'observation':state})
    return result

def scoped_scan(scopes):
    ancestors=set();pid=os.getpid()
    while pid>0 and pid not in ancestors:
        ancestors.add(pid)
        try:pid=int(Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[1])
        except(FileNotFoundError,ValueError):break
    matches=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit()or int(path.name)in ancestors:continue
        try:cmd=(path/'cmdline').read_bytes()
        except(FileNotFoundError,PermissionError,ProcessLookupError):continue
        if any(str(scope).encode()in cmd for scope in scopes):matches.append(int(path.name))
    assert not matches,'Current owned-path processes remain'
    return matches

def audit(args):
    work=args.work.absolute();raw=plain(work/'plan.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==args.plan_sha256
    plan=json.loads(raw);helper=work/'frozen/tests/image_recovery_remaining_matrix.py'
    assert sha(plain(helper))==sha(plain(work/'driver.py'))==plan['driver_sha256']
    # Authenticate complete frozen inputs before importing the original controller.
    assert files(work/'frozen')==plan['frozen_inputs']
    sys.path.insert(0,str(helper.parent))
    spec=importlib.util.spec_from_file_location('frozen_full25_terminal',helper)
    controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)
    assert controller.verify(work,plan)
    source_admission=json.loads((work/'bound/source-admission.json').read_text())
    assert sha(plain(args.source_freeze))==source_admission['files']['source-freeze.json']
    freeze=json.loads(plain(args.source_freeze).read_text());assert files(args.source_root)==freeze['files']and len(freeze['files'])==58
    assert freeze['raw_assembly_sha256']==plan['artifact_sha256']
    original=json.loads(plain(args.original_work/'plan.json').read_text())
    normalized=lambda value:json.dumps(value).replace(str(work),'WORK').replace(str(args.original_work),'WORK')
    assert normalized(plan['jobs'])==normalized(original['jobs'])and len(plan['jobs'])==25
    for job,old in zip(plan['jobs'],original['jobs']):
        path=Path(job['argv'][job['argv'].index('--script')+1]);prior=Path(old['argv'][old['argv'].index('--script')+1])
        assert path.read_bytes()==prior.read_bytes()
    matrix=json.loads(plain(work/'matrix.json').read_text());assert matrix['plan_sha256']==args.plan_sha256
    inputs=[work/'plan.json',work/'driver.py',work/'matrix.json',args.source_freeze];values=[matrix];rows=[];whole=0
    for row in matrix['rows']:
        job=next(j for j in plan['jobs']if j['name']==row['name']);child=None;cleanup=None
        for key in('report','cleanup_report'):
            path=Path(job[key])
            if path.exists():
                value=json.loads(plain(path).read_text());values.append(value);inputs.append(path)
                if row.get(key+'_sha256')is not None:assert sha(path)==row[key+'_sha256']
                if key=='report':child=value
                else:cleanup=value
        qualified=row.get('passed')is True and row.get('exit_code')==0
        if qualified:
            assert child and cleanup and child['passed']is True and cleanup['passed']is True
            assert child['artifact_sha256']==plan['artifact_sha256']
            assert not cleanup['deadline_expired']and not cleanup['cleanup_failure_types']and cleanup['owned_native_processes_absent']
            assert all(x['closed']for x in cleanup['images'])
            for image in cleanup['images']:
                starts={v['container_id']for v in image['events']if v['action']=='started'}
                if starts:
                    e=image['static_compiled_cache'];assert(e['cache_modules'],e['cache_files'],e['source_files'],e['static_toolchain_anchors'],e['dynamic_VM_anchor_observed_here'])==(59,62,59,4,False)
                    assert starts<={v['container_id']for v in image['compiled_launches']}
                    assert all(v['observed_absent']for v in image['payload_probe_lifecycle'])
            assert all(check['passed']is True for check in child['checks']);whole+=1
        rows.append({'name':row['name'],'whole_passed':qualified,'actual_whole_checks':len(child['checks'])if qualified else 0,
                     'report_present':child is not None,'cleanup_present':cleanup is not None})
    passed=args.root_terminal_exit_code==0 and matrix['passed']is True
    if passed:
        assert whole==25 and not matrix['unrun']and [x['name']for x in matrix['rows']]==[j['name']for j in plan['jobs']]
        assert matrix['attempted']==matrix['executed']==[j['name']for j in plan['jobs']]
    else:assert matrix['passed']is False
    ids,names,processes=owned_resources(values)
    env={k:v for k,v in os.environ.items()if not k.startswith('DOCKER_')};env.update(DOCKER_HOST=plan['env']['DOCKER_HOST'],DOCKER_CONFIG=plan['env']['DOCKER_CONFIG'])
    docker=Path('/usr/bin/docker');assert sha(docker.resolve())==plan['external_inputs'][str(docker)]['sha256']
    for identifier in sorted(ids|names):
        result=subprocess.run([str(docker),'inspect',identifier],env=env,capture_output=True,timeout=15)
        assert authoritative_absence(result,identifier),('Current authoritative absence failed',identifier)
    processes=process_observations(processes);assert controller.verify(work,plan)
    summary={'passed':passed,'scope':'Fresh full25 original whole programs; no prior-prefix borrowing.','root_observed_terminal_exit_code':args.root_terminal_exit_code,
        'plan_sha256':args.plan_sha256,'whole_programs':whole,'whole_checks':sum(r['actual_whole_checks']for r in rows),'rows':rows,
        'unrun':matrix['unrun'],'full_input_closure':True,'source58_exact':True,'artifact_sha256':plan['artifact_sha256'],
        'image_config_identity':plan['image_config_identity'],'admission_manifest_sha256':plan['admission_manifest_sha256'],
        'canonical_manifest_sha256':plan['canonical_manifest_sha256'],'known_ID_absence':len(ids),'known_name_absence':len(names),
        'process_identity_observations':processes,'current_scoped_processes':scoped_scan([work]),
        'runtime_starts_by_auditor':0,'prior_unknown_argv_mismatch_cause':'UNKNOWN; later pass does not explain original failure.',
        'recording_limits':['No invented historical names/startticks; absent exact CIDs and original owner cleanup provide VM closure.','Static source59/cache62/statictoolchain4 probes are not perVM dynamic67 custody. Separate SDK/readiness gates retain that scope.','No global image or broker-service absence claim.']}
    out=args.output.absolute();assert not out.exists();out.mkdir(mode=0o700)
    for index,path in enumerate(inputs):shutil.copyfile(path,out/(str(index)+'-'+path.name))
    summary['files']={str(p.relative_to(out)):sha(p)for p in out.iterdir()}
    (out/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'passed':passed,'whole_programs':whole,'whole_checks':summary['whole_checks']}))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('work','original-work','source-root','source-freeze','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--plan-sha256',required=True);p.add_argument('--root-terminal-exit-code',type=int,required=True)
    audit(p.parse_args())
if __name__=='__main__':main()
