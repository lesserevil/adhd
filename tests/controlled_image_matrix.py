#!/usr/bin/env python3
"""Prepare/review a once-only serial15-suite controlled image regression ladder.

No preparation branch starts a runtime, container, compiler or model. Execution
requires a separately reviewed plan hash. Historical SDK producers are actual
retained artifacts; entrypoints/assertions/corpus/deadlines remain unchanged.
"""
import argparse
import ast
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import time

IMAGE='sha256:b12e75c09ccd213f06739f7fdd998d675670491c31677143fecaceab7823e0f0'
ARTIFACT='1741225b1a276770ec9f6631e63fe8646ee5f22808fad8a5acfe67a8aed11bd7'
MANIFEST='dce8d0923d530c01cd38d9ce7c6700e838fd79f2f7bb5e50989b311118aadac4'
ADMISSION='2526ad178e88239704f62b9d7437b98c3f4baca71ee9a82b84e635b242896d58'
SUITES={'context_acceptance':8,'history_acceptance':14,'retrieval_index':6,'retrieval_acceptance':9,
        'archive_acceptance':17,'feedback_acceptance':14,'feedback_faults':9,'feedback_bounds':4,
        'feedback_privacy':4,'optimization_faults':9,'optimization_selection':6,
        'feedback_sdk':5,'archive_sdk':4,'history_sdk':4,'retrieval_sdk':4}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def fileset(root):
    found={}
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink(),path
        if path.is_file():
            info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid(),path
            found[str(path.relative_to(root))]=sha(path)
    return found

def prepare(repo,work,bindings):
    assert not work.exists(),'Preparation requires a fresh private directory'
    work.mkdir(parents=True,mode=0o700);work.chmod(0o700)
    frozen=work/'frozen';frozen.mkdir(mode=0o700)
    for subtree in ['tests','components','scripts']:
        for source in sorted((repo/subtree).rglob('*')):
            if '__pycache__' in source.parts:continue
            assert not source.is_symlink(),source
            if not source.is_file() or source.suffix not in ('.py','.c','.exs','.json','.md','.sh'):continue
            target=frozen/source.relative_to(repo);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    # Use the reviewed38 historical receipt, never a newer verification/current.json.
    for name in ['image-manifest.json','admission.json','rebuild.json','receipt.json']:
        source=bindings/name;assert source.is_file() and not source.is_symlink();shutil.copyfile(source,work/name)
    assert sha(work/'image-manifest.json')==MANIFEST and sha(work/'admission.json')==ADMISSION
    admission=json.loads((work/'admission.json').read_text());assert admission['passed'] and admission['receipt_committed']
    assert admission['artifact_sha256']==ARTIFACT and admission['image_config_identity']==IMAGE
    assert admission['canonical_manifest_sha256']==MANIFEST and admission['payload_audit']['actual_app_files']==59
    assert sha(work/'receipt.json')==admission['receipt_file_sha256']
    assert sha(work/'rebuild.json')==admission['official_rebuild_envelope']['sha256']
    manifest=json.loads((work/'image-manifest.json').read_text());assert manifest['files']['hub.exs']==ARTIFACT
    drift={}
    with tarfile.open(repo/'_build/roadmap/final/container-context-38/payload.tar') as archive:
        for path,digest in manifest['files'].items():
            if not path.startswith('specification/'):continue
            relative=Path('components/hub')/path.removeprefix('specification/')
            raw=archive.extractfile('app/'+path).read();assert hashlib.sha256(raw).hexdigest()==digest
            current=sha(frozen/relative)
            if current!=digest:drift[str(relative)]={'current_root_sha256':current,'admitted38_sha256':digest}
            (frozen/relative).write_bytes(raw)
    # New helper bytes are explicitly overlaid; every original test stays root's current bytes.
    for name in ['controlled_image_runtime.py','controlled_image_matrix.py','controlled_image_static.py']:
        shutil.copyfile(Path(__file__).parent/name,frozen/'tests'/name)
    shutil.copyfile(__file__,work/'run.py')
    history=json.loads((repo/'_build/roadmap/final/controlled38/plan.json').read_text())
    assert history['artifact_sha256']==ARTIFACT
    artifact=Path(history['artifact']);assert sha(artifact)==ARTIFACT
    externals={str(artifact):ARTIFACT};proofs={}
    for relative in ['verification/project-recovery/development38/controlled/manifest.json',
                     'verification/project-recovery/development38/context-manifest.json',
                     '_build/roadmap/final/controlled38/plan.json','_build/roadmap/final/history38-second/plan.json']:
        path=repo/relative;externals[str(path)]=sha(path);proofs[relative]=sha(path)
    for name in ['feedback_sdk','archive_sdk','history_sdk','retrieval_sdk']:
        path=repo/f'verification/project-recovery/development38/controlled/{name}.json'
        value=json.loads(path.read_text());assert value['passed']
        expected=[sha(artifact)]+[sha(p) for p in history['legacy_commands'][name]]
        assert [v['producer_sha256'] for v in value['cases']]==expected
        externals[str(path)]=sha(path)
    legacy_context=[repo/'_build/federation/legacy-hub.exs',repo/'_build/federation/previous-hub.exs']
    all_producers=set(legacy_context)
    for name in SUITES:
        all_producers.update(Path(p) for p in history['legacy_commands'].get(name,[]))
    for path in all_producers:externals[str(path)]=sha(path)
    toolchain=repo/'_build/federation/native'
    elixir=toolchain/'elixir/bin/elixir';beam=toolchain/'erlang/erts-15.2.7.2/bin/beam.smp'
    # The actual installed OTP27 tree owns its versioned BEAM path.
    beams=list((toolchain/'erlang').glob('erts-*/bin/beam.smp'));assert len(beams)==1
    beam=beams[0]
    for path in [elixir.resolve(),beam.resolve(),Path(sys.executable).resolve(),Path(shutil.which('cc')).resolve()]:externals[str(path)]=sha(path)
    jobs=[];runtime=work/'runtime'
    for name,count in SUITES.items():
        entry=frozen/'tests'/f'{name}.py'
        tree=ast.parse(entry.read_text())
        imported={(node.module,alias.name) for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) for alias in node.names}
        expected=('hub_acceptance','Hub') if name.endswith('_sdk') else ('foundation_acceptance','Runtime')
        assert expected in imported,('Unsupported fixture branch',name)
        assert '--image' in entry.read_text(),('Missing original image branch',name)
        test_argv=[str(entry),'--image',IMAGE,'--report',str(work/(name+'.json'))]
        if name.endswith('_sdk'):
            test_argv+=['--command',json.dumps([str(elixir),str(artifact)])]
            for path in history['legacy_commands'][name]:test_argv+=['--legacy-command',json.dumps([str(elixir),path])]
        if name=='context_acceptance':
            for path in legacy_context:test_argv+=['--legacy-command',json.dumps([str(elixir),str(path)])]
        jobs.append({'name':name,'expected_groups':count,'test_argv':test_argv,
                     'custody_report':str(work/(name+'-custody.json')),'launch_ledger':str(work/(name+'-launches.json')),'timeout_seconds':1800})
    plan={'schema':'adhd/controlled-image-plan@1','status':'PREPARED_NOT_EXECUTED_REQUIRES_ROOT_REVIEW',
        'image_config_identity':IMAGE,'artifact_sha256':ARTIFACT,'canonical_manifest_sha256':MANIFEST,
        'admission_sha256':ADMISSION,'manifest':str(work/'image-manifest.json'),'frozen':str(frozen),
        'frozen_inputs':fileset(frozen),'externals':externals,'historical_inventory_proofs':proofs,
        'bound_inputs':{name:sha(work/name) for name in ['image-manifest.json','admission.json','rebuild.json','receipt.json']},
        'driver_sha256':sha(work/'run.py'),'python':sys.executable,'compiler':str(Path(shutil.which('cc')).resolve()),
        'native_artifact_sha256':[ARTIFACT]+sorted({sha(p) for p in all_producers}),
        'path_prefix':str(toolchain/'elixir/bin')+':'+str(toolchain/'erlang/bin'),
        'fence_library':str(work/'provider-fence.so'),'fence_audit':str(work/'provider-fence.audit'),
        'runtime_cwd':str(runtime),'jobs':jobs,'planned_suites':list(SUITES),'expected_groups':sum(SUITES.values()),
        'runs_per_suite':1,'parallelism':1,'maximum_owned_hubs':2,'stop_first_failure':True,'automatic_retries':0,
        'admitted_specification_drift':drift,'maximum_suite_seconds':1800,
        'scope':'Exact admitted38 unchanged backend, original15 controlled suites117 groups with actual historical SDK/context producers. Later39/40 presentation/ownership fixes excluded. Known38 ownership defect stays open.',
        'provider_scope':'No live provider selection. Native port18770 connect fence; image hostnetwork exact typed-local endpoints+no redirects, no physical image egress firewall claim.',
        'budgets':'Every original assertion, operation/readiness deadline, corpus and golden expectation unchanged. Outer1800s suite cap only; no retry.'}
    assert plan['expected_groups']==117
    write(work/'plan.json',plan)
    print(json.dumps({'plan':str(work/'plan.json'),'plan_sha256':sha(work/'plan.json'),'driver_sha256':plan['driver_sha256'],
                      'frozen_count':len(plan['frozen_inputs']),'jobs':jobs},indent=2))


def verify(plan,work):
    driver=Path(__file__);assert driver.absolute()==(work/'run.py').absolute() and driver.resolve()==driver.absolute()
    info=driver.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and not driver.is_symlink()
    assert sha(driver)==plan['driver_sha256'],'Actual executable driver drift'
    assert fileset(work/'frozen')==plan['frozen_inputs'],'Exact frozen file SET/hash changed'
    for path,digest in plan['externals'].items():assert not Path(path).is_symlink() and sha(path)==digest,path
    for path,digest in plan['bound_inputs'].items():assert not (work/path).is_symlink() and sha(work/path)==digest,path
    assert plan['planned_suites']==list(SUITES) and [v['name'] for v in plan['jobs']]==list(SUITES)
    assert [v['expected_groups'] for v in plan['jobs']]==list(SUITES.values())


def authoritative_absence(result,identifier):
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',identifier)
    if result.returncode==0:return False
    expected=[f'Error: No such object: {identifier}\n',f'Error: No such container: {identifier}\n',
              f'Error response from daemon: No such container: {identifier}\n']
    assert result.returncode==1 and result.stderr in [v.encode() for v in expected]
    assert result.stdout in (b'',b'[]\n')
    return True


def cleanup_ledger(job,plan):
    """Exact owned launch cleanup even if a child hits its outer deadline."""
    import signal
    ledger=Path(job['launch_ledger']);events=[]
    if not ledger.exists():return events
    assert not ledger.is_symlink()
    for row in json.loads(ledger.read_text()):
        pid=row.get('client_pid');identity=row.get('client_starttime')
        if pid and identity:
            try:
                raw=Path(f'/proc/{pid}/stat').read_text();actual=raw[raw.rfind(')')+2:].split()[19]
                if actual==identity:
                    assert os.getpgid(pid)==pid,'Refuse foreign process group'
                    os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            except FileNotFoundError:pass
        for vm in row.get('native_vms',[]):
            try:
                raw=Path(f"/proc/{vm['pid']}/stat").read_text();actual=raw[raw.rfind(')')+2:].split()[19]
                if actual==vm['starttime']:
                    assert os.getpgid(vm['pid'])==pid,'Observed BEAM left its owned process group'
                    os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            except FileNotFoundError:pass
        if row['kind']=='docker':
            assert row['image']==plan['image_config_identity']
            result=subprocess.run(['docker','inspect',row['name']],capture_output=True,timeout=30)
            if not authoritative_absence(result,row['name']):
                actual=json.loads(result.stdout)[0];assert actual['Image']==row['image']
                if row.get('container_id'):assert actual['Id']==row['container_id'],'Owned name now identifies different container'
                mounts=actual['Mounts'];assert any(Path(m['Source']).is_relative_to(Path(plan['runtime_cwd'])) for m in mounts)
                subprocess.run(['docker','rm','--force',actual['Id']],capture_output=True,check=True,timeout=30)
            result=subprocess.run(['docker','inspect',row['name']],capture_output=True,timeout=30)
            assert authoritative_absence(result,row['name'])
            if row.get('container_id'):
                missing=subprocess.run(['docker','inspect',row['container_id']],capture_output=True,timeout=30)
                assert authoritative_absence(missing,row['container_id'])
        if pid and identity:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                try:
                    raw=Path(f'/proc/{pid}/stat').read_text();parts=raw[raw.rfind(')')+2:].split()
                    if parts[19]!=identity or parts[0]=='Z':break
                except FileNotFoundError:break
                time.sleep(.05)
            else:raise AssertionError('Owned launch process survived cleanup')
        events.append({**row,'observed_absent':True})
    return events


def execute(work,expected):
    assert sha(work/'plan.json')==expected
    plan=json.loads((work/'plan.json').read_text());verify(plan,work)
    assert not Path(plan['runtime_cwd']).exists()
    with (work/'started.json').open('x') as marker:json.dump({'plan_sha256':expected,'started_at':time.time()},marker)
    Path(plan['runtime_cwd']).mkdir(mode=0o700)
    env=dict(os.environ);env['PATH']=plan['path_prefix']+':'+env['PATH'];env['PYTHONDONTWRITEBYTECODE']='1'
    env['LD_PRELOAD']=plan['fence_library'];env['ADHD_RECOVERY_DENY_PROVIDER_PORT']='18770'
    env['ADHD_RECOVERY_PROVIDER_FENCE_AUDIT']=plan['fence_audit'];rows=[];failure=None
    try:
        subprocess.run([plan['compiler'],'-shared','-fPIC','-O2','-o',plan['fence_library'],
                        str(work/'frozen/tests/project_recovery_no_provider.c'),'-ldl'],check=True,timeout=30)
        for job in plan['jobs']:
            verify(plan,work);name=job['name'];report=work/(name+'.json');log=work/(name+'.log')
            assert not report.exists() and not log.exists() and not Path(job['custody_report']).exists()
            argv=[plan['python'],str(work/'frozen/tests/controlled_image_runtime.py'),'--plan',str(work/'plan.json'),'--job',name,'--reviewed-plan-sha256',expected]
            print('START',name,flush=True);began=time.monotonic()
            cleanup=[];returncode=None;child_failure=None;cleanup_failure=None
            try:
                with log.open('x') as output:
                    child=subprocess.run(argv,cwd=plan['runtime_cwd'],env=env,stdout=output,stderr=subprocess.STDOUT,timeout=job['timeout_seconds'])
                returncode=child.returncode
            except BaseException as error:child_failure=type(error).__name__
            finally:
                try:cleanup=cleanup_ledger(job,plan)
                except BaseException as error:cleanup_failure=type(error).__name__
            row={'suite':name,'argv':argv,'exit_code':returncode,'failure_type':child_failure,'cleanup_failure_type':cleanup_failure,'cleanup':cleanup,'passed':False,'elapsed_seconds':time.monotonic()-began,
                 'log_sha256':sha(log),'report_sha256':sha(report) if report.exists() else None,
                 'custody_report_sha256':sha(job['custody_report']) if Path(job['custody_report']).exists() else None}
            rows.append(row)
            if returncode!=0 or child_failure or cleanup_failure:break
            value=json.loads(report.read_text());custody=json.loads(Path(job['custody_report']).read_text())
            assert value['passed'] and len(value['cases'])==job['expected_groups']
            assert custody['passed'] and not custody['blocked_provider_connects'] and not custody['cleanup_failure_types']
            row['passed']=True
            write(work/'matrix.json',{'passed':False,'status':'RUNNING','rows':rows})
            print('PASS',name,flush=True)
    except BaseException as error:failure=type(error).__name__
    finally:
        try:verify(plan,work);unchanged=True
        except BaseException:unchanged=False
        unrun=[name for name in SUITES if name not in {row['suite'] for row in rows}]
        passed=not failure and unchanged and not unrun and all(row['passed'] for row in rows)
        write(work/'matrix.json',{'schema':'adhd/controlled-image-matrix@1','passed':passed,'plan_sha256':expected,
            'driver_sha256':plan['driver_sha256'],'frozen_inputs_unchanged':unchanged,'failure_type':failure,
            'image_config_identity':IMAGE,'artifact_sha256':ARTIFACT,'planned_suites':list(SUITES),
            'executed_suites':[row['suite'] for row in rows],'unrun_suites':unrun,'rows':rows})
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--repo',type=Path);parser.add_argument('--bindings',type=Path);parser.add_argument('--reviewed-plan-sha256')
    args=parser.parse_args();work=args.work.absolute()
    if args.prepare:prepare(args.repo.resolve(),work,args.bindings.resolve())
    else:sys.exit(execute(work,args.reviewed_plan_sha256))
