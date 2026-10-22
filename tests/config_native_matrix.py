"""Prepare native configuration crash3 with exact host/tool closure; execution needs reviewed GO."""
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
from image_recovery_remaining_matrix import tree,assembly,verify_empty_cache,wait_owned_child
from multi_image_core_matrix import claim_execution
import image_host_dependencies as host_dependencies


def verify(work,plan):
    assert Path(__file__).absolute()==work/'driver.py' and Path(__file__).resolve()==work/'driver.py'
    assert sha(__file__)==plan['driver_sha256']
    verify_frozen_inputs(work/'frozen',plan['frozen_inputs'])
    verify_frozen_inputs(work/'bound',plan['bound_inputs'])
    verify_empty_cache(work/'parent-cache',True)
    verify_empty_cache(work/'results/pycache',False)
    host_dependencies.verify(json.loads((work/'bound/host-dependencies.json').read_text()))
    assert sha(work/'bound/target.exs')==plan['artifact_sha256']
    assert plan['boundaries']==['transaction','config','journal'] and plan['outer_timeout'] is None
    assert plan['original_deadlines']=={'readiness':45,'mutation':25,'client_join':16,'strace_rename_delay_exit':2}
    assert plan['protocol_version']==2 and plan['automatic_retries']==0
    return True


def prepare(a):
    work=a.work.absolute();assert not work.exists() and work.parent.resolve(strict=True)==work.parent
    context=a.context.absolute();admission=a.admission.absolute()
    manifest=json.loads((context/'manifest.json').read_text());artifact=manifest['files']['hub.exs']
    selected=reviewed_payload(context/'manifest.json',admission,a.admission_sha256,a.image,artifact)
    joined,names=assembly(a.source_root);assert joined==selected['artifact_bytes']
    work.mkdir(mode=0o700)
    for name in ['frozen','bound','results','parent-cache']:(work/name).mkdir(mode=0o700)
    inputs,drift=freeze_inputs(a.repo_root,work/'frozen',selected['specifications'])
    # This authored driver and the additive closure helper are the only overlays.
    shutil.copyfile(__file__,work/'driver.py')
    shutil.copyfile(Path(__file__).parent/'image_host_dependencies.py',work/'frozen/tests/image_host_dependencies.py')
    (work/'bound/target.exs').write_bytes(joined)
    shutil.copyfile(admission,work/'bound/admission.json')
    shutil.copyfile(context/'manifest.json',work/'bound/image-manifest.json')
    original=json.loads(a.original_plan.read_text())
    dependencies=host_dependencies.capture(a.python,original['env']['PATH'],extra_tools=('strace',))
    dump(work/'bound/host-dependencies.json',dependencies)
    env=host_dependencies.child_environment(original['env'],dependencies,work/'bound',work/'results/pycache',Path('/var/run/docker.sock'))
    # No container service is used by this lane; retain explicit sanitized env.
    env.pop('DOCKER_HOST');env.pop('DOCKER_CONFIG')
    command=[str(Path(dependencies['native_path'].split(':')[1])/'elixir'),str(work/'bound/target.exs')]
    argv=[str(a.python),'-s','-B',str(work/'frozen/tests/config_recovery.py'),'--command',json.dumps(command),'--protocol-version','2','--report',str(work/'result.json')]
    plan={'schema':'adhd/native-config-three-plan@1','status':'UNSTARTED_ROOT_REVIEW_REQUIRED','artifact_sha256':artifact,
        'admission_sha256':a.admission_sha256,'canonical_manifest_sha256':sha(context/'manifest.json'),
        'driver_sha256':sha(work/'driver.py'),'parent_pycache_prefix':str(work/'parent-cache'),
        'frozen_inputs':tree(work/'frozen'),'bound_inputs':tree(work/'bound'),'live_specification_drift':drift,
        'source_assembly':{n:sha(a.source_root/n) for n in names},'original_recovery_env_basis_sha256':sha(a.original_plan),
        'boundaries':['transaction','config','journal'],'original_deadlines':{'readiness':45,'mutation':25,'client_join':16,'strace_rename_delay_exit':2},
        'protocol_version':2,'outer_timeout':None,'automatic_retries':0,'parallelism':1,'test_argv':argv,'env':env,
        'root_entrypoint_sha256':sha(a.repo_root/'tests/config_recovery.py'),'native_trace_witness':'Current b562 fixture observes rename only after trace_offset captured AFTER explicit admission and baseline publication.',
        'provider_calls_authorized':0,'broker_calls_authorized':0,'scope':'Actual native40 config crash3 only; separate from image40 config3 and recovery42. No actual app/VM/compiler starts during preparation; readonly host metadata queries only.'}
    dump(work/'plan.json',plan)
    print(json.dumps({'plan':str(work/'plan.json'),'sha256':sha(work/'plan.json'),'frozen_files':len(plan['frozen_inputs']),'bound_files':len(plan['bound_inputs'])}))


def execute(work,expected):
    assert sha(work/'plan.json')==expected;plan=json.loads((work/'plan.json').read_text());verify(work,plan)
    claim_execution(work,expected,plan['driver_sha256'])
    result={'schema':'adhd/native-config-three-execution@1','passed':False,'attempted':True,'started':False,'exit_code':None,'plan_sha256':expected,'artifact_sha256':plan['artifact_sha256']}
    primary=None
    try:
        with (work/'stdout').open('xb') as out,(work/'stderr').open('xb') as err:
            process=subprocess.Popen(plan['test_argv'],cwd=work/'results',env=plan['env'],stdout=out,stderr=err,start_new_session=True)
            result.update(started=True,child_pid=process.pid)
            result['exit_code']=wait_owned_child(process)
        verify(work,plan)
        child=json.loads((work/'result.json').read_text())
        assert result['exit_code']==0 and child['passed'] is True and child['artifact_sha256']==plan['artifact_sha256']
        assert [r['case'] for r in child['cases']]==['kill-at-'+name+'-rename' for name in plan['boundaries']]
        assert all(r['passed'] and r['mutation_trace_offset']>0 for r in child['cases'])
        result.update(passed=True,report_sha256=sha(work/'result.json'))
    except BaseException as error:primary=error;result['failure_type']=type(error).__name__;raise
    finally:
        try:dump(work/'execution.json',result)
        except BaseException as error:
            if primary is not None:primary.add_note('Native config execution report failure: '+type(error).__name__)
            else:raise


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare',action='store_true');m.add_argument('--execute',action='store_true')
    p.add_argument('--work',type=Path,required=True);p.add_argument('--plan-sha256')
    for n in ['repo-root','source-root','context','admission','original-plan']:p.add_argument('--'+n,type=Path)
    for n in ['image','admission-sha256']:p.add_argument('--'+n)
    p.add_argument('--python',type=Path,default=Path(sys.executable).absolute())
    a=p.parse_args()
    if a.prepare:prepare(a)
    else:assert a.plan_sha256;execute(a.work.absolute(),a.plan_sha256)


if __name__=='__main__':main()
