#!/usr/bin/env python3
"""Read-only terminal report/input/resource audit; no cleanup or runtime starts.

Root must supply actual terminal exit status. A report or disappearance never
substitutes for that observation. Browser manual visual review remains separate.
Raw screenshots/ARIA and process logs stay private; only their hashes are kept.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    path=Path(path).absolute();assert path==path.resolve(strict=True)
    entry=path.lstat();assert stat.S_ISREG(entry.st_mode)and entry.st_nlink==1 and entry.st_size<=32*1024*1024
    return json.loads(path.read_bytes())


def ticks(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    except FileNotFoundError:return None


def resource_facts(result,report):
    identifiers=set();pids={}
    for session in result.get('runtime_sessions',[]):
        for vm in session['actual_vms']:
            identifiers.update([vm['container_id'],vm['container_name']])
        for event in session['events']:
            if event.get('container_id'):identifiers.add(event['container_id'])
        for probe in session['probes']:
            for key in ['container_id','owned_name']:
                if probe.get(key):identifiers.add(probe[key])
    def walk(value):
        if isinstance(value,dict):
            for pid_key,start_key in [('pid','start_ticks'),('client_pid','client_start_ticks'),('host_vm_pid','host_vm_start_ticks')]:
                pid,start=value.get(pid_key),value.get(start_key)
                if type(pid)is int and isinstance(start,str):pids[(pid,start)]=True
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(result);walk(report)
    assert len(identifiers)<=512 and len(pids)<=4096,'Recorded resource ledger exceeds audit scope'
    for value in identifiers:
        assert re.fullmatch('[a-f0-9]{64}|adhd-(?:multi-accept|accept-probe)-[a-f0-9]{16}',value),'Unrecognized issued container identity'
    return sorted(identifiers),[{'pid':pid,'start_ticks':start,'original_identity_absent':ticks(pid)!=start}for pid,start in sorted(pids)]


def absence(target,identifiers):
    assert digest(target['docker'])==target['docker_sha256']
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','HOME':str(Path(target['docker_config']).parent),
      'DOCKER_HOST':'unix://'+target['socket_path'],'DOCKER_CONFIG':target['docker_config']}
    rows=[]
    for identifier in identifiers:
        reply=subprocess.run([target['docker'],'inspect',identifier],env=env,capture_output=True,timeout=15)
        missing=(reply.returncode==1 and reply.stdout.strip()in (b'',b'[]')and
          re.fullmatch(r'(?i:(?:Error(?: response from daemon)?:\s*)?No such (?:object|container):\s*)'+re.escape(identifier),
            reply.stderr.decode(errors='replace').strip())is not None)
        rows.append({'identifier':identifier,'observed_absent':missing,'exit_code':reply.returncode,
          'stdout_sha256':hashlib.sha256(reply.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(reply.stderr).hexdigest()})
    return rows


def qualify(plan,result,report,terminal_exit,cache=None):
    reasons=[]
    def check(value,reason):
        if not value:reasons.append(reason)
    check(terminal_exit==0,'Actual terminal exit was not0')
    check(result.get('passed')is True,'Outer result is not passed')
    check(report.get('passed')is True,'Original scenario report is not passed')
    check(result.get('cleanup_errors')==[]and report.get('cleanup_errors')==[],'Cleanup errors/missing cleanup evidence retained')
    for key,field in [('image_config_identity','image'),('artifact_sha256','artifact_sha256'),('canonical_manifest_sha256','manifest_sha256'),('admission_sha256','admission_sha256'),('source_admission_sha256','source_admission_sha256')]:
        check(result.get('target',{}).get(key)==plan['target'].get(field),'Result target binding differs: '+key)
    schema=plan['schema'];checks=report.get('checks',report.get('browser',{}).get('checks',[]))
    if schema=='adhd/acme-image-flow@1':
        count=18 if '--continuity'in plan['program_argv']else 16
        check(len(checks)==count and all(row.get('passed')is True for row in checks),'Original full foundation count/flags incomplete')
    elif schema=='adhd/acme-image-fault-flow@1':
        check(result.get('case')==plan['case'],'Fault selection differs')
        check(len(checks)==2 and all(row.get('passed')is True for row in checks)and checks[-1].get('case')==plan['case'],
          'Real baseline+selected fault checks incomplete')
    else:
        check(schema=='adhd/acme-image-browser-flow@1','Unknown qualification schema')
        check(report.get('browser',{}).get('passed')is True and bool(checks)and all(row.get('passed')is True for row in checks),'Original browser hook checks incomplete')
        check(report.get('browser_closed')is True and report.get('playwright_driver_closed')is True,'Browser/tool shutdown incomplete')
        check(result.get('host_inputs_unchanged')is True,'Browser host closure not verified after run')
    vms=[]
    for session in result.get('runtime_sessions',[]):
        check(session['name']is None and session['container_id']is None,'Session container still claimed active')
        check(session['payload_verified']is True and session['assets_verified']is True,'Payload/assets not verified')
        check(session['probe_cleanup_blocked']is False,'Probe cleanup unconfirmed')
        check(bool(session['probes'])and all(row.get('observed_absent')is True and row.get('cleanup_failure_types')==[]for row in session['probes']),
          'Recorded payload probe cleanup incomplete')
        for vm in session['actual_vms']:
            check(vm['image']==plan['target']['image']and vm['default_entrypoint']is True,'VM target/entrypoint differs')
            check(vm.get('default_command')is False and vm.get('public_command')in ('serve','rebind-storage'),
              'Explicit public configuration/CLI command custody incomplete')
            check(re.fullmatch('[0-9a-f]{64}',vm.get('command_sha256',''))is not None,'Exact public command hash missing')
            if cache is not None:
                check(vm.get('live_runtime_files_verified')==len(cache['beams'])+4+len(cache['acme']),'Actual cache/asset file count differs')
                check(vm.get('assets_sha256')==cache['acme'],'Actual packaged asset hashes differ')
            check(vm.get('original_vm_identity_absent')is True,'Recorded VM absence incomplete')
            vms.append(vm)
    check(bool(vms),'No actual VM custody')
    return {'structural_passed':not reasons,'rejections':reasons,'whole_checks_observed':sum(row.get('passed')is True for row in checks),
      'actual_vm_count':len(vms),'browser_manual_visual_review':'separate pending gate'if schema.endswith('browser-flow@1')else'not applicable'}


def audit(plan_path,plan_sha,terminal_exit,audit_resources=False):
    plan_path=Path(plan_path).absolute();assert digest(plan_path)==plan_sha
    plan=load(plan_path)
    # Recheck exact bound bytes; never call an old premain verifier that rejects
    # the correctly consumed once marker or requires an absent runtime directory.
    for name,expected in {**plan['files'],**plan['tool_files']}.items():assert digest(name)==expected,'Bound input changed'
    if plan.get('frozen'):
        root=Path(plan['frozen']['root']);files={};dirs=[]
        for path in sorted(root.rglob('*')):
            assert not path.is_symlink()
            if path.is_dir():dirs.append(str(path.relative_to(root)))
            else:files[str(path.relative_to(root))]=digest(path)
        assert {'files':files,'directories':dirs}==plan['frozen']['inventory'],'Frozen helper SET/hash changed'
    if plan.get('host_closure'):
        import importlib.util
        helper=Path(plan['driver']).with_name('image_host_dependencies.py')
        spec=importlib.util.spec_from_file_location('owned_acme_capture_host',helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.verify(load(plan['host_closure']))
    result_path=plan_path.with_name('result.json');result=load(result_path)
    assert result['plan_sha256']==plan_sha
    if plan['schema']=='adhd/acme-image-flow@1':
        argv=plan['program_argv'];work=Path(argv[argv.index('--work')+1]);report_path=work/'report.json'
    else:
        work=Path(plan['work']);report_path=work/('browser-result.json'if plan['schema']=='adhd/acme-image-browser-flow@1'else'report.json')
    report=load(report_path)if report_path.exists()else{}
    if report:assert digest(report_path)==result['report_sha256']
    qualified=qualify(plan,result,report,terminal_exit,load(plan['target']['cache_manifest']))
    identifiers,pids=resource_facts(result,report)
    observed=absence(plan['target'],identifiers)if audit_resources else[]
    resources_complete=bool(audit_resources and identifiers and pids and all(row['observed_absent']for row in observed)
      and all(row['original_identity_absent']for row in pids))
    captures=[]
    for row in report.get('browser',{}).get('captures',[]):
        for kind in ['png','aria']:
            filename=row[kind];assert Path(filename).name==filename
            path=work/'browser-captures'/filename
            assert digest(path)==row[kind+'_sha256'],'Private diagnostic capture changed'
            captures.append({'kind':kind,'private_path':str(path),'sha256':digest(path),'viewed_here':False})
    qualified.update(resource_audit_performed=audit_resources,resource_audit_passed=resources_complete,
      automatic_runtime_qualified=qualified['structural_passed']and resources_complete,
      runtime_qualified=qualified['structural_passed']and resources_complete and plan['schema']!='adhd/acme-image-browser-flow@1')
    return {'scope':'Terminal source/report/resource audit only; no runtime starts, cleanup mutations or publicCA claim. Browser visual review remains separate.',
      'plan':str(plan_path),'plan_sha256':plan_sha,'actual_terminal_exit_code':terminal_exit,
      'result_path':str(result_path),'result_sha256':digest(result_path),
      'report_path':str(report_path),'report_sha256':digest(report_path)if report else None,
      'input_closure_unchanged':True,'qualification':qualified,'recorded_container_observations':observed,
      'recorded_pid_start_observations':pids,'private_capture_references':captures,'resource_limits':'Only recorded identities; no unrecorded historical PID/name or global ancestor emptiness claim.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--terminal-exit-code',type=int,required=True);parser.add_argument('--audit-resource-absence',action='store_true')
    parser.add_argument('--output',required=True)
    args=parser.parse_args();value=audit(args.plan,args.plan_sha256,args.terminal_exit_code,args.audit_resource_absence)
    output=Path(args.output);assert not output.exists()
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w')as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps(value['qualification']))


if __name__=='__main__':main()
