"""Capture a CLI-issued documentation-only source bridge; never builds or issues receipts.

Default checks are read-only. --execute permits only a NEW evidence directory.
Staging remains the official stage_container.py command owned by the operator.
"""
import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat


def digest(body):return hashlib.sha256(body).hexdigest()
def regular(path):
    path=Path(path).absolute();info=path.lstat()
    assert path.resolve(strict=True)==path and stat.S_ISREG(info.st_mode)and info.st_nlink==1
    body=path.read_bytes();after=path.stat()
    assert(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
    return body

def pinned(path,expected):
    body=regular(path);assert digest(body)==expected;return body

def uri(value):
    assert re.fullmatch('sha256:[a-f0-9]{64}',value);return value

def identity(value):
    assert value['algorithm']=='sha256';return uri('sha256:'+value['digest'])

def derive(plan,receipt,envelope,old,artifact):
    assert plan['command']=='rebuild'and plan['ok']is True and plan['result']['admitted']is False
    assert envelope['command']=='rebuild'and envelope['ok']is True
    result=envelope['result'];review=plan['result'];native=result['test_summary']
    assert result['passed']is True and result['receipt_committed']is True and result['specification']=='components/hub'
    assert native=={'failed':0,'passed':18,'skipped':0,'total':18}
    assert old['passed']is True and old['artifact_sha256']==artifact
    assert result['receipt_identity']==receipt['receipt_identity']
    assert result['lifecycle_request_identity']==receipt['lifecycle_request_identity']
    assert result['lifecycle_result_identity']==receipt['receipt']['result']
    assert result['project_revision_identity']==result['validated_project_authority_identity']==receipt['receipt']['project_revision']
    assert result['component_lock_identity']==identity(review['input']['component_lock_identity'])==old['component_lock_identity']
    assert result['framework_distribution_identity']==old['framework_distribution_identity']
    return {'component_lock_identity':uri(result['component_lock_identity']),
        'base_authority_identity':identity(review['input']['project_authority_identity']),
        'rebuild_authority_identity':uri(result['project_revision_identity']),
        'receipt_identity':uri(receipt['receipt_identity']),
        'framework_distribution_identity':uri(result['framework_distribution_identity'])}

def inventory(path):
    path=Path(path).absolute();assert path.resolve(strict=True)==path and path.is_dir()
    result={};directories=[]
    for member in sorted(path.rglob('*')):
        assert not member.is_symlink()
        name=str(member.relative_to(path))
        if member.is_dir():directories.append(name)
        else:result[name]=digest(regular(member))
    return {'files':result,'directories':directories}

def compare_contexts(old,new,expected):
    old=Path(old);new=Path(new)
    assert digest(regular(old/'manifest.json'))==expected
    before=inventory(old);after=inventory(new);assert before==after,'Complete staged file SET/directories or bytes differ'
    manifest=json.loads(regular(new/'manifest.json'))
    assert len(manifest['files'])==60 and len(manifest['files'])-1==59
    return {'passed':True,'scope':'Complete file/directory SET and bytes equal to prior independently audited context; no image runtime started.',
            'canonical_manifest_sha256':expected,'files':before['files'],'directories':before['directories'],'actual_app_file_count':59}

def capture(args):
    raw_plan=pinned(args.plan,args.plan_sha256);raw_rebuild=pinned(args.rebuild,args.rebuild_sha256)
    raw_receipt=pinned(args.receipt,args.receipt_sha256);raw_old=pinned(args.prior_source_admission,args.prior_source_admission_sha256)
    plan=json.loads(raw_plan);rebuild=json.loads(raw_rebuild);receipt=json.loads(raw_receipt);old=json.loads(raw_old)
    provenance=derive(plan,receipt,rebuild,old,args.artifact_sha256)
    assert digest(regular(rebuild['result']['artifact']))==args.artifact_sha256
    assert old['native_readiness23']['passed']is True and old['native_readiness23']['case_count']==23
    assert old['native_retention_companion']['passed']is True and old['native_retention_companion']['whole_checks']==3
    previous={}
    for name,expected in old['files'].items():
        assert Path(name).name==name and name not in('.','..')
        previous[name]=pinned(args.prior_source_admission.parent/name,expected)
    original_review=json.loads(previous['retained-plan.json'])['result']
    for key in('tree_identity','target','origin'):
        assert plan['result']['input'][key]==original_review['input'][key]
    freeze=json.loads(previous['source-freeze.json'])
    assert inventory(args.retained_source)['files']==freeze['files']and len(freeze['files'])==58
    assert freeze['raw_assembly_sha256']==args.artifact_sha256
    files={'receipt.json':raw_receipt,'rebuild.json':raw_rebuild,'retained-plan.json':raw_plan,
           'prior-source-admission.json':raw_old,'source-freeze.json':previous['source-freeze.json'],
           **{'prior-'+name:body for name,body in previous.items()}}
    report={**provenance,'schema':'adhd/source-authority-documentation-bridge@1','passed':True,
        'artifact_sha256':args.artifact_sha256,'native_test_summary':rebuild['result']['test_summary'],
        'native_readiness23':old['native_readiness23'],'native_retention_companion':old['native_retention_companion'],
        'prior_source_admission_sha256':args.prior_source_admission_sha256,
        'scope':'Fresh actual CLI lifecycle and receipt under reviewed documentation authority. Original23+3 native runtime proofs are inherited by exact unchanged58-source/D41 binding; their original receipts remain historical, no rerun or relabeling.',
        'source_only_bridge':True,'image_built_here':False,'runtime_started_here':False,
        'files':{name:digest(body)for name,body in files.items()}}
    # Reuse the downstream public source-binding validator before publishing.
    sys.path.insert(0,str(Path(__file__).absolute().parent))
    from image_compiled_admission import source_binding
    encoded=(json.dumps(report,indent=2)+'\n').encode()
    source_binding(encoded,digest(encoded),raw_receipt,raw_rebuild,args.artifact_sha256)
    if args.execute:
        output=args.output.absolute();assert output.parent.resolve(strict=True)==output.parent and not output.exists()
        output.mkdir(mode=0o700)
        for name,body in files.items():
            with(output/name).open('xb')as stream:stream.write(body)
        with(output/'manifest.json').open('xb')as stream:stream.write(encoded)
    return {'passed':True,'written':args.execute,'source_admission_sha256':digest(encoded),'provenance':provenance}

def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source',action='store_true');mode.add_argument('--contexts',action='store_true')
    p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path)
    for name in('plan','receipt','rebuild','prior-source-admission','retained-source','old-context','new-context'):p.add_argument('--'+name,type=Path)
    for name in('plan-sha256','receipt-sha256','rebuild-sha256','prior-source-admission-sha256','artifact-sha256','context-sha256'):p.add_argument('--'+name)
    a=p.parse_args()
    if a.source:
        assert all(getattr(a,k)for k in('plan','receipt','rebuild','prior_source_admission','retained_source','plan_sha256','receipt_sha256','rebuild_sha256','prior_source_admission_sha256','artifact_sha256'))
        assert a.output if a.execute else True;result=capture(a)
    else:
        result=compare_contexts(a.old_context,a.new_context,a.context_sha256)
        if a.execute:
            assert a.output and not a.output.exists()
            with a.output.open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
