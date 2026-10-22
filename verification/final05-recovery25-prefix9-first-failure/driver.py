"""Freeze then explicitly execute the complete remaining42 image recovery rows.

Preparation never starts a process. A diagnostic38 plan is execution-denied;
corrected successors require their own admitted image, source and ABI proofs.
"""
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
import importlib.util
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
import image_host_dependencies as host_dependencies
from image_filesystem_fault import validate_observer
from image_recovery_remaining_layout import layout,epoch_fixture_overlay
from multi_image_core_matrix import claim_execution

BASELINE='sha256:b12e75c09ccd213f06739f7fdd998d675670491c31677143fecaceab7823e0f0'


def tree(path):
    path=Path(path).absolute();assert path.resolve(strict=True)==path and path.is_dir()
    values={}
    for item in sorted(path.rglob('*')):
        info=item.lstat();assert not stat.S_ISLNK(info.st_mode)
        if stat.S_ISDIR(info.st_mode):continue
        assert stat.S_ISREG(info.st_mode);values[str(item.relative_to(path))]=sha(item)
    verify_frozen_inputs(path,values);return values


def verify_original(origin,inventory):
    """Original native runs may write _build outside six declared inputs trees."""
    origin=Path(origin).absolute();assert origin.resolve(strict=True)==origin
    files={n:r['sha256'] for n,r in inventory['files'].items()};trees=[Path(n) for n in inventory['trees']]
    assert trees and len(set(trees))==len(trees)
    for name in trees:
        assert not name.is_absolute() and '..' not in name.parts
        assert not any(name!=other and (name.is_relative_to(other) or other.is_relative_to(name)) for other in trees)
        selected={str(Path(n).relative_to(name)):h for n,h in files.items() if Path(n).is_relative_to(name)}
        assert selected;verify_frozen_inputs(origin/name,selected)
    assert all(any(Path(name).is_relative_to(t) for t in trees) for name in files)
    return trees


def assembly(source):
    source=Path(source);recipe=(source/'tools/assemble.exs').read_text()
    names=re.search(r'files = ~w\((.*?)\)',recipe,re.S).group(1).split()
    assert len(names)==len(set(names)) and names
    for name in names:assert not Path(name).is_absolute() and '..' not in Path(name).parts
    return b'\n'.join((source/name).read_bytes() for name in names),names


def resolve(value,tokens):
    if isinstance(value,str):
        for key,replacement in tokens.items():value=value.replace('${'+key+'}',replacement)
        assert '${' not in value,'Unresolved template: '+value
        return value
    if isinstance(value,list):return [resolve(v,tokens) for v in value]
    if isinstance(value,dict):return {k:resolve(v,tokens) for k,v in value.items()}
    return value


def verify_empty_cache(path,required):
    path=Path(path)
    try:info=path.lstat()
    except FileNotFoundError:
        assert not required;return True
    assert stat.S_ISDIR(info.st_mode) and not path.is_symlink() and info.st_uid==os.getuid() and info.st_mode & 0o077==0
    assert path.resolve(strict=True)==path and not list(path.iterdir()), 'Stale/redirected bytecode cache rejected'
    return True


def remainder_names(basis,matrix,artifact,image):
    names=[job['name'] for job in basis['jobs']]
    assert len(names) in (42,34,19) and len(set(names))==len(names)
    assert matrix['passed'] is False and matrix['artifact_sha256']==artifact and matrix['image_config_identity']==image
    whole={42:8,34:15,19:1}[len(names)]
    failed={42:'crash-damaged-after-install-snapshot',34:'primitive-allocator',19:'primitive-epoch'}[len(names)]
    rows=matrix['rows'];assert len(rows)==whole+1 and matrix['planned']==len(names)
    assert [row['name'] for row in rows]==names[:whole+1]
    assert all(row['passed'] is True and row['exit_code']==0 and row['started'] for row in rows[:whole])
    assert rows[-1]['name']==failed and rows[-1]['passed'] is False and rows[-1]['exit_code']==1 and rows[-1]['started']
    if len(names)==34:assert all(name.startswith('crash-') for name in names[:15])
    if len(names)==19:assert names[:2]==['primitive-allocator','primitive-epoch']
    assert matrix['unrun']==names[whole+1:] and matrix['executed']==names[:whole+1] and matrix['attempted']==names[:whole+1]
    return names[whole:]



def full_app_rows(descriptor):
    rows=[r for r in descriptor['selected_rows']if r['family']!='component']
    assert len(rows)==25 and [r['name']for r in rows[:8]]==['admission','rejections','private','agent-admission','uninitialized-move','mixed','federation-errors','learned']
    assert sum(r['family']=='crash'for r in rows)==15 and [r['name']for r in rows[-2:]]==['rebind','rebind-hostile']
    return rows


def load_compiled_helper(frozen):
    spec=importlib.util.spec_from_file_location('reviewed_recovery_compiled_binding',frozen/'tests/controlled_sdk_matrix.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);return helper


def verify(work,plan):
    assert sha(Path(__file__))==sha(work/'driver.py')==plan['driver_sha256']
    for key,directory in [('frozen_inputs','frozen'),('component_inputs','component'),('context_inputs','context')]:
        verify_frozen_inputs(work/directory,plan[key])
    assert all(sha(work/name)==digest for name,digest in plan['bound_inputs'].items())
    verify_frozen_inputs(work/'bound',{str(Path(name).relative_to('bound')):digest for name,digest in plan['bound_inputs'].items()})
    verify_empty_cache(work/'parent-cache',required=True)
    verify_empty_cache(work/'results/pycache',required=False)
    host_dependencies.verify(json.loads((work/'bound/host-dependencies.json').read_text()))
    for name,row in plan['external_inputs'].items():
        p=Path(name);assert p.resolve(strict=True)==Path(row['realpath']) and sha(p)==row['sha256']
    assert Path(sys.executable).resolve(strict=True)==Path(plan['python']['realpath']) and sha(plan['python']['realpath'])==plan['python']['sha256']
    sock=Path(plan['docker_socket']['path']).stat()
    assert stat.S_ISSOCK(sock.st_mode) and [sock.st_dev,sock.st_ino]==plan['docker_socket']['identity']
    expected=42
    if plan.get('full_app_only'):
        assert not plan.get('resume_basis')
        original=json.loads((work/'bound/original-plan.json').read_text())
        assert [j['name']for j in plan['jobs']]==[r['name']for r in full_app_rows(layout(original))]
        expected=25
    if plan.get('compiled_binding'):
        assert json.loads((work/'bound/compiled-binding.json').read_text())==plan['compiled_binding']
        admission=json.loads((work/'bound/admission.json').read_text())
        compiled=load_compiled_helper(work/'frozen').compiled_cache_binding(work/'bound/cache-manifest.json',admission,plan['image_config_identity'],plan['artifact_sha256'],plan['canonical_manifest_sha256'])
        assert compiled==plan['compiled_binding']['compiled_cache']
    if plan.get('resume_basis'):
        prior=json.loads((work/'bound/prior-plan.json').read_text());matrix=json.loads((work/'bound/prior-matrix.json').read_text())
        names=remainder_names(prior,matrix,plan['artifact_sha256'],plan['image_config_identity'])
        assert [job['name'] for job in plan['jobs']]==names and len(names) in (34,19,18)
        expected=len(names)
    assert len(plan['jobs'])==expected and len({j['name'] for j in plan['jobs']})==expected
    assert sha(work/'frozen/tests/image_recovery_remaining_matrix.py')==plan['driver_sha256']
    return True


def prepare(args):
    assert all(getattr(args,n) for n in ('helper_root','original_plan','original_sha256','source_root','context','admission_manifest','admission_sha256','image','project_library','project_proof','rebind_library','rebind_proof'))
    work=args.work.absolute();assert not work.exists() and work.parent.resolve(strict=True)==work.parent
    original_raw=args.original_plan.read_bytes();assert hashlib.sha256(original_raw).hexdigest()==args.original_sha256
    original=json.loads(original_raw);original_inputs=Path(original['inputs_manifest'])
    assert sha(original_inputs)==original['inputs_manifest_sha256'];inventory=json.loads(original_inputs.read_text())
    origin=Path(original['cwd']);original_map={n:r['sha256'] for n,r in inventory['files'].items()}
    original_trees=verify_original(origin,inventory)
    selected_manifest=json.loads((args.context/'manifest.json').read_text());artifact=selected_manifest['files']['hub.exs']
    selected=reviewed_payload(args.context/'manifest.json',args.admission_manifest,args.admission_sha256,args.image,artifact)
    source_bytes,names=assembly(args.source_root);assert source_bytes==selected['artifact_bytes']
    if args.execution_ready:assert args.image!=BASELINE,'Known ownership-defective38 is diagnostic-only'
    for library,proof,family in ((args.project_library,args.project_proof,'project_recovery_fault.c'),(args.rebind_library,args.rebind_proof,'rebind_fault.c')):
        _,abi=validate_observer(args.image,library,proof,family)
        assert abi['artifact_sha256']==artifact and abi['canonical_manifest_sha256']==sha(args.context/'manifest.json')
    descriptor=layout(original)
    work.mkdir(mode=0o700);frozen=work/'frozen';frozen.mkdir(mode=0o700)
    inputs,drift=freeze_inputs(args.helper_root,frozen,selected['specifications'])
    for name in ('image_recovery_remaining_matrix.py','image_recovery_remaining_matrix_unit.py','image_recovery_entry.py','image_recovery_cache.py','image_recovery_cache_unit.py'):
        shutil.copyfile(Path(__file__).with_name(name),frozen/'tests'/name)
    shutil.copytree(origin/'fixtures',frozen/'fixtures',copy_function=shutil.copy2)
    # Complete original component fixtures are copied without modifying their
    # source directory, and mounted later at that original absolute path.
    component=work/'component';component.mkdir(mode=0o700)
    for relative in original_trees:
        target=component/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(origin/relative,target,copy_function=shutil.copy2)
    verify_frozen_inputs(component,original_map)
    epoch=component/'tests/project_epoch_fences.exs';epoch.write_bytes(epoch_fixture_overlay(epoch.read_bytes()))
    source_target=component/'source38';shutil.rmtree(source_target);source_target.mkdir()
    for name in names+['tools/assemble.exs','tools/clean.exs','Makefile']:
        src=args.source_root/name;assert src.resolve(strict=True)==src
        dst=source_target/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    for name,body in selected['specifications'].items():
        dst=component/'components/hub'/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(body)
    # All seventeen vector programs retain original bytes except reviewed one
    # Storage-load token. Assertion changes cannot hide in a helper overlay.
    component_scripts={Path(r['original']['argv'][1]).relative_to(origin) for r in descriptor['selected_rows'] if r['family']=='component'}
    for relative in component_scripts:
        old=(origin/relative).read_bytes();new=(component/relative).read_bytes()
        assert new==(epoch_fixture_overlay(old) if relative==Path('tests/project_epoch_fences.exs') else old)
    assert assembly(source_target)[0]==selected['artifact_bytes']
    shutil.copytree(args.context,work/'context',copy_function=shutil.copy2)
    bound=work/'bound';bound.mkdir(mode=0o700)
    (bound/'artifact.exs').write_bytes(selected['artifact_bytes'])
    shutil.copy2(args.admission_manifest,bound/'admission.json');shutil.copy2(args.original_plan,bound/'original-plan.json')
    shutil.copy2(original_inputs,bound/'original-inputs.json')
    compiled_binding=None
    admission=json.loads((bound/'admission.json').read_text())
    cache_path=getattr(args,'compiled_cache_manifest',None)
    assert cache_path is not None or 'compiled_runtime_audit'not in admission,'Compiled image requires explicit cache binding'
    if cache_path is not None:
        assert cache_path.absolute()==args.admission_manifest.parent/'cache-manifest.json'
        for name,digest in admission['files'].items():
            assert Path(name).name==name and name not in ('.','..')
            source=args.admission_manifest.parent/name;assert source.resolve(strict=True)==source.absolute()and source.stat().st_nlink==1 and sha(source)==digest
            assert not(bound/name).exists();shutil.copy2(source,bound/name)
        compiled=load_compiled_helper(frozen).compiled_cache_binding(bound/'cache-manifest.json',admission,args.image,artifact,sha(args.context/'manifest.json'))
        compiled_binding={'image_config_identity':args.image,'compiled_cache':compiled,'source_manifest_sha256':sha(args.context/'manifest.json'),'scope':'Immutable readonly image cache probes; not in-VM67. Original app entrypoint/observer kernel custody retained separately.'}
        dump(bound/'compiled-binding.json',compiled_binding)
    external={}
    for name,row in inventory['external'].items():
        src=Path(name);assert sha(src)==row['sha256']
        external[name]={'realpath':str(src.resolve(strict=True)),'sha256':row['sha256']}
    # The journal component reads only these exact immutable copies; it never
    # mounts the owning fixture's writable directory into a vector container.
    journal=Path(next(r['original']['argv'][-1] for r in descriptor['selected_rows'] if r['name']=='primitive-journal'))
    shutil.copy2(journal,bound/'journal-config');shutil.copy2(str(journal)+'.recovery',bound/'journal-recovery')
    for name,library,proof in [('project_recovery_fault',args.project_library,args.project_proof),('rebind_fault',args.rebind_library,args.rebind_proof)]:
        shutil.copy2(library,bound/(name+'.so'));shutil.copy2(proof,bound/(name+'.proof.json'))
    (work/'results').mkdir(mode=0o700)
    (work/'parent-cache').mkdir(mode=0o700)
    verify_empty_cache(work/'results/pycache',required=False)
    dump(bound/'config.json',{})
    dependencies=host_dependencies.capture(args.python,original['env']['PATH'])
    dump(bound/'host-dependencies.json',dependencies)
    resume_basis=None;selected_names=None
    full_app_only=getattr(args,'full_app_only',False)
    if full_app_only:
        assert not args.resume_work
        selected_names=[r['name']for r in full_app_rows(descriptor)]
    if args.resume_work:
        prior=args.resume_work.absolute();assert args.resume_plan_sha256 and sha(prior/'plan.json')==args.resume_plan_sha256
        basis=json.loads((prior/'plan.json').read_text());matrix=json.loads((prior/'matrix.json').read_text())
        assert matrix['plan_sha256']==args.resume_plan_sha256
        for key,directory in [('frozen_inputs','frozen'),('component_inputs','component'),('context_inputs','context')]:verify_frozen_inputs(prior/directory,basis[key])
        verify_frozen_inputs(prior/'bound',{str(Path(name).relative_to('bound')):digest for name,digest in basis['bound_inputs'].items()})
        host_dependencies.verify(json.loads((prior/'bound/host-dependencies.json').read_text()))
        for name,row in basis['external_inputs'].items():
            assert Path(name).resolve(strict=True)==Path(row['realpath']) and sha(name)==row['sha256']
        selected_names=remainder_names(basis,matrix,artifact,args.image)
        full_names=[row['name'] for row in descriptor['selected_rows']]
        assert [job['name'] for job in basis['jobs']] in (full_names,full_names[8:],full_names[23:])
        if len(basis['jobs'])==34:
            from image_recovery_component import qualify_output
            failed=prior/'results/primitive-allocator-capsule-work/stdout.log'
            result=json.loads((prior/'results/primitive-allocator.json').read_text())
            assert result['runtime']['sessions'][0]['client_exit_code']==0
            assert qualify_output({'kind':'exunit','expected_tests':5},subprocess.CompletedProcess([],0,failed.read_bytes(),b''))['tests']==5
            shutil.copyfile(failed,bound/'prior-primitive-allocator-actual-vm.stdout')
        if len(basis['jobs'])==19:
            failed=prior/'results/primitive-epoch-capsule-work'
            assert (failed/'component-runtime.txt').read_text().splitlines()==['1','29','1.20.4']
            assert not (failed/'component-release').exists() and not (failed/'component-release').is_symlink()
            failed_result=json.loads((prior/'results/primitive-epoch.json').read_text())
            assert failed_result['runtime']['sessions'][0]['actual_vm_custody'] is None and not failed_result['checks']
            shutil.copyfile(failed/'component-runtime.txt',bound/'prior-primitive-epoch-unreleased-capsule.txt')
        for name in ('plan.json','matrix.json'):shutil.copyfile(prior/name,bound/('prior-'+name))
        for row in matrix['rows']:
            for suffix,key in [('.json','report_sha256'),('-cleanup.json','cleanup_report_sha256')]:
                file=prior/'results'/(row['name']+suffix);assert sha(file)==row[key]
                value=json.loads(file.read_text())
                if suffix=='.json':assert value['passed']==row['passed'] and value['artifact_sha256']==artifact
                else:
                    assert value['owned_native_processes_absent'] and not value['cleanup_failure_types'] and all(image['closed'] for image in value['images'])
                    assert value['passed']==row['passed']
                shutil.copyfile(file,bound/('prior-'+row['name']+suffix))
        resume_basis={'original_plan_sha256':args.resume_plan_sha256,'original_matrix_sha256':sha(prior/'matrix.json'),'previous_whole_passes':[row['name'] for row in matrix['rows'] if row['passed']],'selected_failed_and_unrun':selected_names,'original_aggregate_stays_false':True}
    jobs=[]
    for row in descriptor['selected_rows']:
        if selected_names is not None and row['name'] not in selected_names:continue
        name=row['name'];tokens={'FROZEN':str(frozen),'RESULTS':str(work/'results'),'ARTIFACT':str(bound/'artifact.exs'),
            'IMAGE':args.image,'MANIFEST':str(work/'context/manifest.json'),'COMPONENT_SNAPSHOT':str(component),
            'JOURNAL_CONFIG_COPY':str(bound/'journal-config'),'JOURNAL_RECOVERY_COPY':str(bound/'journal-recovery'),
            'PROJECT_RECOVERY_FAULT_LIBRARY':str(bound/'project_recovery_fault.so'),'PROJECT_RECOVERY_FAULT_PROOF':str(bound/'project_recovery_fault.proof.json'),
            'REBIND_FAULT_LIBRARY':str(bound/'rebind_fault.so'),'REBIND_FAULT_PROOF':str(bound/'rebind_fault.proof.json')}
        harness=Path(resolve(row['harness'],tokens));report=work/'results'/(name+'.json')
        if row['family']=='component':
            job=resolve(row['component_job'],tokens);job['work']=str(work/'results'/(name+'-capsule-work'))
            jobfile=bound/(name+'-component.json');dump(jobfile,job)
            argv=['--image',args.image,'--image-manifest',str(work/'context/manifest.json'),'--artifact',str(bound/'artifact.exs'),
                '--job',str(jobfile),'--job-sha256',sha(jobfile),'--work',job['work'],'--report',str(report)]
        else:argv=resolve(row['harness_arguments'],tokens)
        wrapper=work/'results'/(name+'-cleanup.json')
        command=[str(args.python),'-s','-B',str(frozen/'tests/image_recovery_entry.py'),'--script',str(harness),'--script-sha256',sha(harness),
            '--timeout',str(row['outer_timeout_seconds']),'--cleanup-report',str(wrapper),'--',*argv]
        if compiled_binding:
            command[command.index('--'):command.index('--')]=['--compiled-binding',str(bound/'compiled-binding.json'),'--compiled-binding-sha256',sha(bound/'compiled-binding.json')]
        jobs.append({'name':name,'family':row['family'],'argv':command,'report':str(report),'cleanup_report':str(wrapper),
            'outer_timeout_seconds':row['outer_timeout_seconds'],'original':row['original']})
    shutil.copy2(__file__,work/'driver.py')
    # Bind actual host tools without invoking them. Native learned producer is
    # deliberately retained and additionally fenced by its authored fixture.
    for executable in [args.python,Path(shutil.which('docker')),Path(shutil.which('gcc')),Path(shutil.which('cc')),
                       Path(original['env']['PATH'].split(':')[0])/'erl',Path(original['env']['PATH'].split(':')[1])/'elixir']:
        real=executable.resolve(strict=True);assert os.access(real,os.X_OK)
        external[str(executable)]={'realpath':str(real),'sha256':sha(real)}
    socket=args.docker_socket.stat();assert stat.S_ISSOCK(socket.st_mode)
    plan={'schema':'adhd/image-recovery42-plan@1','execution_ready':args.execution_ready,'execution_started':False,
        'full_app_only':full_app_only,'compiled_binding':compiled_binding,
        'scope':('Original full-app25/128 subset; source-only17/181 and callback5/28 remain separately scoped.'if full_app_only else 'Failed+unrun'+str(len(selected_names))+' of original recovery42; prior whole passes remain separate preserved evidence.' if resume_basis else 'Actual-image remaining recovery42 only; five transport rows and completed five callbacks remain separate evidence.'),'resume_basis':resume_basis,
        'known38_ownership_gap':args.image==BASELINE,'image_config_identity':args.image,'artifact_sha256':artifact,
        'admission_manifest_sha256':args.admission_sha256,'canonical_manifest_sha256':sha(work/'context/manifest.json'),
        'payload_tar_sha256':selected['payload_sha256'],'original_plan_sha256':args.original_sha256,
        'driver_sha256':sha(work/'driver.py'),'driver_python_flags':['-I','-S','-B','-X','pycache_prefix='+str(work/'parent-cache')],
        'parent_pycache_prefix':str(work/'parent-cache'),'jobs':jobs,'parallelism':1,'runs_per_suite':1,'fail_fast':True,
        'original_input_trees':[str(n) for n in original_trees],
        'excluded_original_outputs':'Original native runtime _build is outside declared six input trees and is not copied; each authoritative tree exactSET verified.',
        'fixture_amendments':descriptor['fixture_amendments'],'separate_dependencies':descriptor['separate_dependencies'],
        'frozen_inputs':tree(frozen),'component_inputs':tree(component),'context_inputs':tree(work/'context'),
        'bound_inputs':{str(p.relative_to(work)):sha(p) for p in bound.iterdir()},'external_inputs':external,
        'python':{'path':str(args.python),'realpath':str(args.python.resolve()),'sha256':sha(args.python.resolve())},
        'docker_socket':{'path':str(args.docker_socket),'identity':[socket.st_dev,socket.st_ino]},
        'env':host_dependencies.child_environment(original['env'],dependencies,bound,work/'results/pycache',args.docker_socket),'runtime_cwd':str(work/'results'),'live_specification_drift':drift,
        'source_files':{n:sha(source_target/n) for n in names},'component_scripts':{str(n):sha(component/n) for n in component_scripts},
        'deadline_policy':'Exact original per-row main deadline; BaseException unwind before disarmed cleanup. Known audited scripts only; no arbitrary infinite-catch guarantee.',
        'preparation_only':not args.execution_ready}
    dump(work/'plan.json',plan)
    print('PREPARED remaining42; no runtimes. Plan '+sha(work/'plan.json'))
    return plan


def wait_owned_child(process):
    """Parent interruption must let the reviewed child unwind owned cleanup."""
    try:return process.wait()
    except BaseException as primary:
        if process.poll() is None:
            try:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=90)
            except BaseException as cleanup:
                primary.add_note('Qualification child cleanup unconfirmed: '+type(cleanup).__name__)
        raise


def execute(work,expected):
    plan=json.loads((work/'plan.json').read_text());assert sha(work/'plan.json')==expected
    verify(work,plan);assert plan['execution_ready'] and not plan['known38_ownership_gap']
    claim_execution(work,expected,plan['driver_sha256'])
    rows=[];primary=None;env=dict(plan['env']);env['PYTHONDONTWRITEBYTECODE']='1'
    matrix={'schema':'adhd/image-recovery42-matrix@1','passed':False,'plan_sha256':expected,
        'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],'planned':len(plan['jobs']),
        'attempted':[],'executed':[],'unrun':[j['name'] for j in plan['jobs']],'rows':rows}
    try:
        for job in plan['jobs']:
            verify(work,plan)
            row={'name':job['name'],'attempted':True,'started':False,'passed':False,'exit_code':None};rows.append(row)
            matrix['attempted'].append(job['name']);start=time.monotonic()
            try:
                with (work/'results'/(job['name']+'.stdout')).open('xb') as stdout,(work/'results'/(job['name']+'.stderr')).open('xb') as stderr:
                    process=subprocess.Popen(job['argv'],stdout=stdout,stderr=stderr,cwd=plan['runtime_cwd'],env=env,start_new_session=True)
                    row.update(started=True,child_pid=process.pid);matrix['executed'].append(job['name']);matrix['unrun'].remove(job['name'])
                    row['exit_code']=wait_owned_child(process)
                row['elapsed_seconds']=time.monotonic()-start
                child=json.loads(Path(job['report']).read_text());cleanup=json.loads(Path(job['cleanup_report']).read_text())
                row.update(report_sha256=sha(job['report']),cleanup_report_sha256=sha(job['cleanup_report']))
                assert row['exit_code']==0 and child['passed'] is True and cleanup['passed'] is True
                assert child['artifact_sha256']==plan['artifact_sha256']
                # Every owned image callback/session must close before evidence
                # passes; wrapper additionally enforces fallback native closure.
                assert all(r['closed'] for r in cleanup['images']) and cleanup['owned_native_processes_absent']
                if plan.get('compiled_binding'):
                    for image in cleanup['images']:
                        starts={v['container_id']for v in image['events']if v['action']=='started'}
                        if starts:
                            evidence=image['static_compiled_cache'];assert evidence['cache_modules']==59 and evidence['cache_files']==62 and evidence['source_files']==59 and evidence['static_toolchain_anchors']==4 and evidence['dynamic_VM_anchor_observed_here']is False
                            assert starts<={v['container_id']for v in image['compiled_launches']}
                            assert all(v['observed_absent']for v in image['payload_probe_lifecycle'])
                verify(work,plan);row['passed']=True
            except BaseException as error:
                row['failure_type']=type(error).__name__;raise
            finally:
                if row['started'] and row['exit_code'] is None:
                    observed=process.poll()
                    if observed is not None:row['exit_code']=observed
                row['elapsed_seconds']=time.monotonic()-start;dump(work/'matrix.json',matrix)
        verify(work,plan);assert len(rows)==len(plan['jobs']) and not matrix['unrun'];matrix['passed']=True
    except BaseException as error:primary=error;matrix['failure_type']=type(error).__name__;raise
    finally:
        try:dump(work/'matrix.json',matrix)
        except BaseException as error:
            if primary is not None:primary.add_note('Matrix report write failure: '+type(error).__name__)
            else:raise
    return matrix


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--plan-sha256')
    for name in ['helper-root','original-plan','source-root','context','admission-manifest','project-library','project-proof','rebind-library','rebind-proof']:
        parser.add_argument('--'+name,type=Path)
    for name in ['original-sha256','admission-sha256','image']:parser.add_argument('--'+name)
    parser.add_argument('--python',type=Path,default=Path(sys.executable).absolute());parser.add_argument('--docker-socket',type=Path,default=Path('/var/run/docker.sock'))
    parser.add_argument('--execution-ready',action='store_true');parser.add_argument('--full-app-only',action='store_true');parser.add_argument('--compiled-cache-manifest',type=Path)
    parser.add_argument('--resume-work',type=Path);parser.add_argument('--resume-plan-sha256')
    args=parser.parse_args()
    if args.prepare:prepare(args)
    else:assert args.plan_sha256;execute(args.work.absolute(),args.plan_sha256)


if __name__=='__main__':main()
