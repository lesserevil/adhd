#!/usr/bin/env python3
"""Capture actual ACME lifecycle source admission; never run or issue a receipt.

Read-only by default. --write permits only a fresh evidence directory. Finalized
candidate receipts qualify exact successful artifacts; current project receipt,
image, real issuer and deployed-runtime qualification remain separate gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


def sha(raw):return hashlib.sha256(raw).hexdigest()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def decode(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            assert key not in value,'Duplicate evidence key'
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique)


def read(path,maximum=32*1024*1024):
    path=Path(path).absolute();assert path.resolve(strict=True)==path
    info=path.lstat()
    identity=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
    assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=maximum
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        assert identity(os.fstat(stream.fileno()))==identity(info)
        raw=stream.read(maximum+1);assert len(raw)==info.st_size
        assert identity(os.fstat(stream.fileno()))==identity(info)
    assert identity(path.lstat())==identity(info)
    return raw


def uri(value):
    assert isinstance(value,str) and re.fullmatch('sha256:[a-f0-9]{64}',value)
    return value


def identity(value):
    assert value['algorithm']=='sha256'
    return uri('sha256:'+value['digest'])


def source_files(root,freeze):
    root=Path(root).absolute();assert root.resolve(strict=True)==root and root.is_dir()
    expected=freeze.get('files',freeze)
    assert isinstance(expected,dict) and expected
    files={};directories=set()
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        name=str(path.relative_to(root))
        if path.is_dir():directories.add(name)
        else:
            assert path.is_file();files[name]=read(path)
            files[name].decode('utf-8')
    for name,value in expected.items():
        p=PurePosixPath(name)
        assert not p.is_absolute() and '..' not in p.parts and str(p)==name
        assert re.fullmatch('[a-f0-9]{64}',value)
    assert {name:sha(body)for name,body in files.items()}==expected,'Retained file SET/hash changed'
    wanted={str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent)!='.'}
    assert directories==wanted,'Retained directory SET changed'
    return files


def tree_identity(files):
    # RetainedSourceInput._read prefixes logical paths with source/ before the
    # Standard contracts/source_index.py canonical path/size/digest manifest.
    rows=[{'path':'source/'+name,'size':len(body),'digest':'sha256:'+sha(body)}for name,body in sorted(files.items())]
    return 'sha256:'+sha(canonical(rows))


def assembled(files):
    source=files['tools/assemble.exs'].decode()
    groups=re.findall(r'^files = ~w\(([^\n()]*)\)$',source,re.M);assert len(groups)==1
    names=groups[0].split();assert names and len(names)==len(set(names))
    assert 'body = Enum.map_join(files, "\\n", &File.read!(Path.join(root,&1)))' in source
    assert 'File.write!(temp,body)' in source
    make=re.findall(r'^SRCS := (.*)$',files['Makefile'].decode(),re.M)
    assert len(make)==1 and make[0].split()==names,'Build/assembler source order differs'
    assert all(name in files for name in names)
    return b'\n'.join(files[name]for name in names)


def derive(plan,envelope,receipt,files,oracle,artifact):
    assert plan['command']=='rebuild' and plan['ok'] is True
    review=plan['result'];assert review['admitted'] is False
    selected=review['input'];assert selected['origin']=='operator-retained-source'
    assert identity(selected['tree_identity'])==tree_identity(files)
    assert envelope['command']=='rebuild' and envelope['ok'] is True
    result=envelope['result'];assert result['passed'] is True and result['specification']=='components/hub'
    assert result['coding_cli']=='operator-retained-source' and result['target']==selected['target']
    assert receipt['schema']=='urn:literate-ai:schema:v1:project-test-receipt-finalized-candidate'
    assert receipt['receipt']['schema']=='urn:literate-ai:schema:v1:project-test-receipt'
    rid='sha256:'+sha(canonical(receipt['receipt']))
    assert result['receipt_identity']==receipt['receipt_identity']==rid
    assert result['lifecycle_request_identity']==receipt['lifecycle_request_identity']
    assert result['lifecycle_result_identity']==receipt['receipt']['result']
    assert result['project_revision_identity']==result['validated_project_authority_identity']==receipt['receipt']['project_revision']
    assert result['component_lock_identity']==identity(selected['component_lock_identity'])
    assert type(result['receipt_committed']) is bool
    if result['receipt_committed']:
        assert result['receipt_update']['updated'] is True and result['receipt_update']['identity']==rid
    else:assert result.get('receipt_update') is None
    native=result['test_summary'];assert native=={'failed':0,'passed':8,'skipped':0,'total':8}
    assert all(type(v)is int for v in native.values())
    suite=decode(files['tests/manifest.json'])
    assert suite['schema']=='urn:literate-ai:schema:v1:generated-test-suite' and len(suite['cases'])==8
    assert oracle['schema']=='literate-ai/component-acceptance-oracle@1' and oracle['component']=='hub'
    assert len(oracle['cases'])==114
    specset=uri(oracle['specification_set_identity'])
    assert sha(assembled(files))==sha(artifact),'Actual export differs from raw retained assembly'
    return {'component_lock_identity':uri(result['component_lock_identity']),
      'base_authority_identity':identity(selected['project_authority_identity']),
      'rebuild_authority_identity':uri(result['project_revision_identity']),
      'receipt_identity':uri(rid),'framework_distribution_identity':uri(result['framework_distribution_identity']),
      'retained_tree_identity':tree_identity(files),'native_test_summary':native,
      'configured_acceptance':{'oracle_schema':oracle['schema'],'cases':len(oracle['cases']),
        'specification_set_identity':specset,'retained_executed_case_array':False,
        'scope':'Configured oracle inventory only. Successful CLI lifecycle is bound separately; no 114-row execution report synthesized.'}}


def capture(args):
    raw={}
    for name in ('plan','receipt','rebuild','source_freeze','oracle'):
        raw[name]=read(getattr(args,name))
        assert sha(raw[name])==getattr(args,name+'_sha256')
    values={name:decode(body)for name,body in raw.items()}
    files=source_files(args.retained_source,values['source_freeze'])
    result=values['rebuild']['result'];artifact=read(result['artifact'])
    assert sha(artifact)==args.artifact_sha256
    provenance=derive(values['plan'],values['rebuild'],values['receipt'],files,values['oracle'],artifact)
    if not result['receipt_committed']:
        assert sha(read(result['candidate_receipt']))==sha(raw['receipt'])
    retained={'retained-plan.json':raw['plan'],'receipt.json':raw['receipt'],'rebuild.json':raw['rebuild'],
      'source-freeze.json':raw['source_freeze'],'configured-oracle.json':raw['oracle']}
    report={**provenance,'schema':'adhd/acme-source-lifecycle-admission@1','passed':True,
      'artifact_sha256':args.artifact_sha256,'raw_assembly_sha256':sha(assembled(files)),
      'retained_source_file_count':len(files),'receipt_committed_at_rebuild':result['receipt_committed'],
      'project_current_receipt_verified':False,'image_built_here':False,'runtime_started_here':False,
      'scope':'Actual successful proper source lifecycle/finalized candidate/artifact capture only. Cached native10 real-issuer diagnostics, packaged runtime, public issuer and deployment are separate qualification scopes.',
      'source_cache_cli_fields':{k:result[k]for k in ('source_cache_lifecycle_identity','source_cache_published_entry_identities')if k in result},
      'physical_source_cache_retention_verified':False,
      'files':{name:sha(body)for name,body in retained.items()}}
    encoded=json.dumps(report,indent=2).encode()+b'\n'
    if args.write:
        output=Path(args.output).absolute();assert output.parent.resolve(strict=True)==output.parent and not output.exists()
        output.mkdir(mode=0o700)
        for name,body in {**retained,'manifest.json':encoded}.items():
            fd=os.open(output/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb')as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
        fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return {'passed':True,'written':args.write,'source_admission_sha256':sha(encoded),'provenance':provenance}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','receipt','rebuild','source-freeze','oracle'):
        p.add_argument('--'+name,required=True,type=Path);p.add_argument('--'+name+'-sha256',required=True)
    p.add_argument('--retained-source',required=True,type=Path);p.add_argument('--artifact-sha256',required=True)
    p.add_argument('--write',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args();assert args.output if args.write else True
    print(json.dumps(capture(args),indent=2))


if __name__=='__main__':main()
