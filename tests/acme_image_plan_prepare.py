#!/usr/bin/env python3
"""Freeze ACME image foundation18 and15 fault plans; never start resources.

Without --target-json all plans carry target:null and execution refuses them.
An eventual actual target creates a NEW preparation; old plans are not rebound.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path):
    path=Path(path).absolute();assert path==path.resolve(strict=True),'Redirected input'
    before=path.lstat();assert stat.S_ISREG(before.st_mode)and before.st_nlink==1
    assert before.st_size<=64*1024*1024
    raw=path.read_bytes();after=path.lstat()
    identity=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    assert identity(before)==identity(after)and len(raw)==before.st_size
    return raw


def inventory(root):
    root=Path(root).absolute();assert root==root.resolve(strict=True)and root.is_dir()
    files={};directories=[]
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink(),'Tool/input symlink not admitted implicitly'
        name=str(path.relative_to(root))
        if path.is_dir():directories.append(name)
        else:files[name]=sha(read(path))
    return {'files':files,'directories':directories}


def verify_tool_roots(plan):
    if plan.get('frozen'):
        frozen=plan['frozen']
        assert inventory(frozen['root'])==frozen['inventory'],'Frozen helper SET/hash changed'
    for root,expected in plan.get('tool_roots',{}).items():
        assert inventory(root)==expected,'External tool root SET/hash changed'


def write(path,raw):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def encoded(value):return (json.dumps(value,indent=2)+'\n').encode()


def prepare(root,output,ca_path,ca_sha,source_path,source_sha,python,tools,tool_roots=(),target_path=None,browser_path=None,host_closure_path=None,host_closure_sha=None):
    root=Path(root).absolute();output=Path(output).absolute()
    assert root==root.resolve(strict=True)and output==output.resolve()and not output.exists()
    ca_raw=read(ca_path);assert sha(ca_raw)==ca_sha
    ca=json.loads(ca_raw);assert ca['ready']is True and ca['real_validation']is True and ca['nonce_validation']is True
    assert ca['public_ca_calls']==0 and ca['validation_http_port']==8080
    source_raw=read(source_path);assert sha(source_raw)==source_sha
    source=json.loads(source_raw);assert source['passed']is True and re.fullmatch('[0-9a-f]{64}',source['artifact_sha256'])
    for name in ['receipt.json','rebuild.json']:
        assert sha(read(Path(source_path).with_name(name)))==source['files'][name]
    browser=json.loads(read(browser_path))if browser_path else None
    if browser is not None:
        assert host_closure_path and sha(read(host_closure_path))==host_closure_sha
        assert set(browser)=={'root','executable','inventory_sha256','file_count'}
    target=json.loads(read(target_path))if target_path else None
    if target is not None:
        assert target['source_admission_sha256']==source_sha and target['artifact_sha256']==source['artifact_sha256']
        assert Path(target['source_admission']).absolute()==Path(source_path).absolute()
        sys.path.insert(0,str(root/'tests'))
        from acme_image_target import AcceptedImageTarget
        AcceptedImageTarget({'target':target}) # Read-only actual admission validation; no Docker.
    # Compute inventories BEFORE creating the fresh destination; no original is
    # chmodded/deleted or rewritten. Bytecode caches are not authored helpers.
    inputs={}
    for path in sorted((root/'tests').rglob('*')):
        relative=path.relative_to(root)
        if '__pycache__'in relative.parts or path.suffix in ('.pyc','.pyo'):continue
        assert not path.is_symlink()
        if path.is_file():inputs[str(relative)]=read(path)
    for relative in ['scripts/configure_hub.py','components/hub/acme/interface.schema.json']:
        inputs[relative]=read(root/relative)
    required=['acme_image_flow.py','acme_image_fault_flow.py','acme_image_provision.py','acme_image_faults.py',
      'acme_image_plan_prepare.py','image_compiled_admission.py','image_compiled_inputs.py','image_payload_audit.py']
    assert all('tests/'+name in inputs for name in required)
    # The case order is read only from the hash-bound authored module AST,
    # without importing acceptance dependencies or executing scenario code.
    import ast
    tree=ast.parse(inputs['tests/acme_image_faults.py'])
    constants={}
    for node in tree.body:
        if isinstance(node,ast.Assign)and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            if node.targets[0].id in ('FLOOR_CASES','POLICY_CASES','LOSS_CASES','BASIC_CASES'):
                constants[node.targets[0].id]=ast.literal_eval(node.value)
    cases=sum((constants[name]for name in ['FLOOR_CASES','POLICY_CASES','LOSS_CASES','BASIC_CASES']),())+('real-expiry',)
    assert len(cases)==len(set(cases))==15
    tool_files={str(Path(p).resolve(strict=True)):sha(read(Path(p).resolve(strict=True)))for p in tools}
    python_path=Path(python).absolute();assert python_path.is_file()
    tool_files[str(python_path.resolve(strict=True))]=sha(read(python_path.resolve(strict=True)))
    external_roots={str(Path(p).absolute()):inventory(p)for p in tool_roots}
    external={str(Path(ca_path).absolute()):ca_sha,str(Path(source_path).absolute()):source_sha}
    for name in ['frontend_root','issuer_root']:
        assert sha(read(ca[name]))==ca[name+'_sha256'];external[ca[name]]=ca[name+'_sha256']
    relay={}
    for name,filename in [('cert','frontend-cert.pem'),('key','frontend-key.pem'),('root','frontend-root.pem')]:
        path=Path(ca_path).absolute().with_name(filename);body=read(path)
        relay[name+'_file']=str(path);relay[name+'_sha256']=sha(body);external[str(path)]=sha(body)
    for name,digest in source['files'].items():
        path=Path(source_path).absolute().with_name(name);assert sha(read(path))==digest;external[str(path)]=digest
    if browser is not None:
        for path in [browser_path,host_closure_path]:external[str(Path(path).absolute())]=sha(read(path))
        assert all('tests/'+name in inputs for name in ['acme_browser.py','acme_browser_flow.py','acme_image_browser.py','image_host_dependencies.py'])
    if target is not None:
        external[str(Path(target_path).absolute())]=sha(read(target_path))
        for key in ['manifest','artifact','admission','source_admission','receipt','rebuild','cache_manifest']:
            external[target[key]]=sha(read(target[key]))
    output.mkdir(mode=0o700)
    (output/'runtime').mkdir(mode=0o700)
    frozen=output/'frozen';files={}
    for name,body in inputs.items():
        path=frozen/name;write(path,body);files[str(path)]=sha(body)
    files.update(external)
    ca_copy=output/'inputs'/'ca-manifest.json';write(ca_copy,ca_raw);files[str(ca_copy)]=ca_sha
    source_copy=output/'inputs'/'source-admission.json';write(source_copy,source_raw);files[str(source_copy)]=source_sha
    # Do not rewrite private CA manifest paths or provenance; copy is byte-exact.
    frozen_binding={'root':str(frozen),'inventory':inventory(frozen)}
    common={'frozen':frozen_binding,'target':target,'files':files,'tool_files':tool_files,'tool_roots':external_roots,
      'execution_env':{'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},
      'preparation_scope':'Bound input preparation only; target:null is deliberately non-executable',
      'source_admission_sha256':source_sha,'ca_manifest_sha256':ca_sha}
    schema=frozen/'components/hub/acme/interface.schema.json';configure=frozen/'scripts/configure_hub.py'
    argv=['--execute','--phase','full','--work',str(output/'runtime'/'foundation'),
      '--ca-manifest',str(ca_copy),'--ca-manifest-sha256',ca_sha,'--schema',str(schema),'--configure',str(configure),
      '--rebind','--account-continuation','--continuity']
    if target is not None:
        cache=json.loads(read(target['cache_manifest']))
        argv+=['--lego-sha256',cache['acme']['lego'],'--guardian-sha256',cache['acme']['acme-guard']]
    plans=[]
    entries=[('foundation',None)]+[(name,name)for name in cases]
    if browser is not None:entries.append(('browser','browser'))
    for name,case in entries:
        directory=output/'plans'/name;directory.mkdir(mode=0o700,parents=True)
        driver=frozen/'tests'/('acme_image_flow.py'if case is None else'acme_browser_flow.py'if case=='browser'else'acme_image_fault_flow.py')
        plan={**common,'schema':'adhd/acme-image-flow@1'if case is None else'adhd/acme-image-browser-flow@1'if case=='browser'else'adhd/acme-image-fault-flow@1',
          'driver':str(driver),'driver_sha256':files[str(driver)]}
        if case is None:
            plan.update(python_executable=str(python_path.resolve()),program_argv=argv,once_marker=str(directory/'started.json'),expected_whole_groups=18)
        else:
            plan.update(python=str(python_path.resolve()),case=case,work=str(output/'runtime'/case),budget_seconds=600,
              ca_manifest=str(ca_copy),schema_file=str(schema),configure=str(configure),issuer_relay=relay)
        if case=='browser':
            del plan['case'];plan['browser']=browser;plan['host_closure']=str(Path(host_closure_path).absolute())
            (directory/'python-cache').mkdir(mode=0o700)
        path=directory/'plan.json';raw=encoded(plan);write(path,raw)
        command=['env','PATH=/usr/bin:/bin','PYTHONDONTWRITEBYTECODE=1',str(python_path),'-I','-B',str(driver),
          '--plan',str(path),'--plan-sha256',sha(raw)]
        if case=='browser':
            command=command[:4]+['-I','-S','-B','-X','pycache_prefix='+str(directory/'python-cache'),str(driver),
              '--plan',str(path),'--plan-sha256',sha(raw)]
        plans.append({'name':name,'plan':str(path),'plan_sha256':sha(raw),'verify_argv':command+['--verify-only'],
          'execute_argv':command+['--execute'],'target_bound':target is not None})
    result={'schema':'adhd/acme-image-suite-preparation@1','target_bound':target is not None,'runtime_started':False,
      'foundation_whole_groups':18,'fault_cases':list(cases),'plans':plans,'files':files,'tool_files':tool_files,
      'tool_roots':external_roots,'frozen':frozen_binding,'scope':'Exact declared helper/input/top-executable files; recursive tool closure only for supplied tool_roots. No runtime qualification.'}
    write(output/'preparation.json',encoded(result))
    verify_preparation(output/'preparation.json')
    return result


def verify_preparation(path):
    result=json.loads(read(path))
    for name,digest in {**result['files'],**result['tool_files']}.items():assert sha(read(name))==digest
    verify_tool_roots(result)
    for row in result['plans']:
        assert sha(read(row['plan']))==row['plan_sha256']
        assert not Path(row['plan']).with_name('started.json').exists()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-preparation')
    for name in ['root','output','ca-manifest','ca-manifest-sha256','source-admission','source-admission-sha256','python','target-json','browser-binding','host-closure','host-closure-sha256']:
        parser.add_argument('--'+name)
    parser.add_argument('--tool-file',action='append',default=[]);parser.add_argument('--tool-root',action='append',default=[])
    args=parser.parse_args()
    if args.verify_preparation:result=verify_preparation(args.verify_preparation)
    else:
        assert all(getattr(args,name)for name in ['root','output','ca_manifest','ca_manifest_sha256','source_admission','source_admission_sha256','python'])
        result=prepare(args.root,args.output,args.ca_manifest,args.ca_manifest_sha256,args.source_admission,
          args.source_admission_sha256,args.python,args.tool_file,args.tool_root,args.target_json,args.browser_binding,args.host_closure,args.host_closure_sha256)
    print(json.dumps({'prepared':True,'target_bound':result['target_bound'],'plans':len(result['plans']),'runtime_started':False}))


if __name__=='__main__':main()
