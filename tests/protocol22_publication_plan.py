#!/usr/bin/env python3
"""Prepare an inert protocol2.2 publication recipe; never export or publish.

No subprocess facility or execution mode exists. Historical snapshots and source
helpers are copied only into a fresh private ignored work directory. A real target
is optional until receipt success; all six binding arguments are then mandatory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

BASELINE = {
    'schema': ('_build/cache41-compiled01/protocol-schema.stdout', '826a4763f524249fac76605a78aa195c5073163d5c81d8bf30ad1da164c71bd3'),
    'openapi': ('_build/cache41-compiled01/protocol-openapi.stdout', 'c81e2a670bdf89ceefc719f53a61e04c6c1a2ee7071355520d4f522e32f35fba'),
}
HELPERS = ('tests/acme_protocol_contracts.py','tests/protocol_acceptance.py',
           'tests/foundation_acceptance.py','tests/protocol_scope.py',
           'components/hub/acme/interface.schema.json')
TARGET_ARGS = ('accepted_artifact','artifact_sha256','receipt','receipt_sha256','rebuild','rebuild_sha256')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def read(path, maximum=32*1024*1024):
    path=Path(path).absolute()
    assert path.resolve(strict=True)==path
    before=path.lstat()
    assert stat.S_ISREG(before.st_mode) and 0<=before.st_size<=maximum
    same=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        assert same(os.fstat(stream.fileno()))==same(before)
        raw=stream.read(maximum+1);assert len(raw)==before.st_size
        assert same(os.fstat(stream.fileno()))==same(before)
    assert same(path.lstat())==same(before)
    return raw


def target_binding(args):
    values=[getattr(args,k,None) for k in TARGET_ARGS]
    if not any(v is not None for v in values):return None
    assert all(v is not None for v in values),'Actual artifact/hash/receipt/rebuild bindings must be complete'
    for key in ('artifact_sha256','receipt_sha256','rebuild_sha256'):
        assert re.fullmatch('[a-f0-9]{64}',getattr(args,key))
    artifact=read(args.accepted_artifact);receipt_raw=read(args.receipt,8*1024*1024);build_raw=read(args.rebuild,8*1024*1024)
    assert sha(artifact)==args.artifact_sha256
    assert sha(receipt_raw)==args.receipt_sha256 and sha(build_raw)==args.rebuild_sha256
    receipt=json.loads(receipt_raw);build=json.loads(build_raw)
    assert receipt['schema']=='urn:literate-ai:schema:v1:project-test-receipt-finalized-candidate'
    assert receipt['receipt']['schema']=='urn:literate-ai:schema:v1:project-test-receipt'
    rid='sha256:'+sha(canonical(receipt['receipt']))
    assert receipt['receipt_identity']==rid
    assert build['command']=='rebuild' and build['ok'] is True
    result=build['result']
    assert result['passed'] is True and result['receipt_committed'] is True
    assert result['receipt_update']['updated'] is True
    assert result['receipt_identity']==result['receipt_update']['identity']==rid
    assert result['lifecycle_request_identity']==receipt['lifecycle_request_identity']
    assert result['lifecycle_result_identity']==receipt['receipt']['result']
    assert result['project_revision_identity']==receipt['receipt']['project_revision']
    assert sha(read(result['artifact']))==args.artifact_sha256
    return {'artifact':str(Path(args.accepted_artifact).absolute()),'artifact_sha256':args.artifact_sha256,
            'formal_artifact':result['artifact'],'receipt':str(Path(args.receipt).absolute()),
            'receipt_sha256':args.receipt_sha256,'receipt_identity':rid,
            'rebuild':str(Path(args.rebuild).absolute()),'rebuild_sha256':args.rebuild_sha256,
            'authority':result['project_revision_identity'],'profile22_export_verified':False}


def scopes22(raw):
    value=json.loads(raw)
    assert value['schema']=='adhd/operation-scopes@1' and value['application_profile']=='2.1.0'
    assert all(op not in value['admin'] for op in ('tls_status','tls_renew')) and 'tls' not in value['configuration']
    value['application_profile']='2.2.0'
    value['admin'].update(tls_status='server',tls_renew='server')
    value['configuration']['tls']='server'
    assert 'tls' not in value['project_settings']
    return value


def issue(path, raw):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def prepare(args):
    root=Path(args.repo_root).absolute();work=Path(args.work).absolute()
    assert root.resolve(strict=True)==root and root.is_dir()
    assert work.resolve()==work and not work.exists()
    target=target_binding(args)
    docs=root/'docs/protocol';historical={}
    for path in sorted(docs.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir():continue
        historical[str(path.relative_to(root))]=read(path)
    assert json.loads(historical['docs/protocol/schema.json'])['$id']=='urn:adhd:protocol:2.1'
    assert json.loads(historical['docs/protocol/openapi.json'])['info']['version']=='2.1.0'
    assert not (docs/'v2.1').exists(),'Publication baseline already moved; re-review recipe'
    baseline={}
    for key,(name,expected) in BASELINE.items():
        raw=read(root/name);assert sha(raw)==expected;baseline[key]=raw
    old=json.loads(baseline['schema']);assert len(old['$defs'])-5==421
    helpers={name:read(root/name) for name in HELPERS}
    candidate=json.dumps(scopes22(historical['docs/protocol/scopes.json']),indent=2).encode()+b'\n'
    # No source/API is evaluated. Even a target-bound recipe is not executable.
    commands=[
        {'name':'actual-schema-export','argv_template':['<PINNED_ELIXIR>','<ACTUAL_ACCEPTED_ARTIFACT>','["protocol-schema"]'],'stdout':'exports/protocol-schema.stdout'},
        {'name':'actual-openapi-export','argv_template':['<PINNED_ELIXIR>','<ACTUAL_ACCEPTED_ARTIFACT>','["protocol-openapi"]'],'stdout':'exports/protocol-openapi.stdout'},
        {'name':'schema-conservation26','argv_template':['<PINNED_PYTHON>','frozen/tests/acme_protocol_contracts.py','--schema','exports/protocol-schema.stdout','--baseline','baseline/schema.json','--openapi','exports/protocol-openapi.stdout','--baseline-openapi','baseline/openapi.json','--authority','frozen/components/hub/acme/interface.schema.json','--report','conservation.json']},
        {'name':'complete-scopes','argv_template':['<PINNED_PYTHON>','frozen/tests/protocol_scope.py','--schema','exports/protocol-schema.stdout','--inventory','scopes-candidate.json']},
        {'name':'actual-wire8','argv_template':['<PINNED_PYTHON>','frozen/tests/protocol_acceptance.py','--command','<JSON_PINNED_ELIXIR_AND_ACTUAL_ARTIFACT>','--profile-version','2.2.0','--published-schema','exports/protocol-schema.stdout','--published-openapi','exports/protocol-openapi.stdout','--eventing-rest-url','<REVIEWED_OWNED_KAFKA_REST>','--port-lock','<SHARED_ABSOLUTE_FOUNDATION_LOCK>','--report','wire.json']},
    ]
    plan={'schema':'adhd/protocol22-inert-publication-plan@1','execution_ready':False,'execution_supported':False,
          'target':target,'runtime_exports':0,'published_writes':0,'authority_mutations':0,
          'historical':{k:sha(v) for k,v in historical.items()},'D41_actual_baseline':{k:sha(v) for k,v in baseline.items()},
          'frozen_helpers':{k:sha(v) for k,v in helpers.items()},'scopes_candidate_sha256':sha(candidate),
          'future_export_environment':{'ERL_FLAGS':'+S 2:2','PATH':'/home/horde/src/adhd/_build/federation/native/elixir/bin:/home/horde/src/adhd/_build/federation/native/erlang/bin:/usr/bin:/bin'},
          'commands':commands,'conservation':{'unchanged_old_definitions':421,'only_changed_old_definitions':['AdminCommand','AdminResult','PublicConfig','MergePatch','Error'],'actual_schema_vectors':26,'actual_wire_groups':8},
          'publication_after_all_actual_gates':['Create NEW docs/protocol/v2.1 containing old schema/openapi/scopes exact bytes; retain current2.1 README provenance in historical evidence and author corrected relative index.','Keep existing v2.0 tree, legacy1.7 examples and all historical verification bytes unchanged.','Replace current schema/openapi ONLY with exact actual accepted CLI stdout; do not generate them from authority or reformat them.','Publish reviewed scopes candidate only after complete operation/config inventory check against actual exported schema. No scopes CLI operation exists.','Update current/historical indexes and separate2.2 ACME examples with actual qualification/receipt links; root coordinates authority and final proper receipt bridge.'],
          'required_before_any_execution':['Actual accepted artifact+hash+proper receipt+rebuild complete binding.','Root review and fresh closed execution driver (full transitive fixture/tool/socket/owned Kafka/input closure, exclusive once, cleanup); this plan has no executor.','Actual2.2 schema/OpenAPI checks and no unexpected421-definition or old-route changes; no arbitrary array sorting to hide differences.'],
          'driver_sha256':sha(read(__file__))}
    work.mkdir(mode=0o700)
    for name,raw in historical.items():issue(work/'historical'/name,raw)
    for name,raw in helpers.items():issue(work/'frozen'/name,raw)
    for name,raw in baseline.items():issue(work/'baseline'/(name+'.json'),raw)
    issue(work/'scopes-candidate.json',candidate)
    issue(work/'plan.json',json.dumps(plan,indent=2,sort_keys=True).encode()+b'\n')
    return {'prepared':True,'execution_ready':False,'target_bound':target is not None,'plan_sha256':sha(read(work/'plan.json'))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',required=True,type=Path);parser.add_argument('--work',required=True,type=Path)
    for name in TARGET_ARGS:parser.add_argument('--'+name.replace('_','-'))
    args=parser.parse_args();print(json.dumps(prepare(args)))

if __name__=='__main__':main()
