#!/usr/bin/env python3
"""Read-only evidence adapter; no imports of runtime helpers or subprocesses."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    assert path.resolve()==path and path.is_file()and not path.is_symlink()
    return json.loads(path.read_text())


def derive(repo,work):
    retained=repo/'verification/ownedMULTI008/source41-image-abi-positive'
    audit=read(retained/'audit.json');plan=read(work/'plan.json');result=read(work/'result.json')
    assert audit['passed']is result['passed']is True
    assert audit['plan_sha256']==result['plan_sha256']==sha(work/'plan.json')
    assert audit['result_sha256']==sha(work/'result.json')==sha(retained/'result.json')
    assert audit['image_config_identity']==result['image_config_identity']==plan['image_config_identity']
    assert audit['artifact_sha256']==result['artifact_sha256']==plan['artifact_sha256']
    assert result['application_started']is False and result['provider_calls']==result['broker_calls']==0
    assert result['rows']and[row['case']for row in result['rows']]==plan['cases']
    assert len(result['rows'])==audit['cases']==19 and audit['rows_exact_original_order']is True
    assert audit['case_json_caller_trace_equal']is True and audit['all_case_exit_codes']==137
    assert audit['full_inventory_verified_before_after']is True
    assert len({row['container_id']for row in result['rows']})==19
    actual_ids={row['container_id']for row in result['rows']}
    absence=audit['actual_known_cid_absence']
    assert {row['container_id']for row in absence}==actual_ids and all(row['strict_current_absence']is True for row in absence)
    assert audit['all_recorded_host_pids_currently_absent']is True
    assert audit['abi_name_prefix_census_empty']is True
    caller=plan['caller']['audit']
    assert sha(Path(plan['caller']['library']))==caller['library_sha256']
    assert sha(work/'inputs/image_filesystem_abi_caller.c')==caller['source_sha256']
    rows=[];proofs={}
    for source,build in plan['observer_builds'].items():
        proofpath=work/(source+'.proof.json');proof=read(proofpath)
        assert sha(proofpath)==sha(retained/proofpath.name)==audit['source_proofs'][source]['proof_sha256']
        assert proof['schema']=='adhd/image-filesystem-observer-probe@1'and proof['passed']is True
        assert proof['image_config_identity']==plan['image_config_identity']
        assert proof['artifact_sha256']==plan['artifact_sha256']and proof['canonical_manifest_sha256']==plan['canonical_manifest_sha256']
        assert proof['application_started']is False and proof['owned_container_absent']is True and proof['exit_code']==137
        assert proof['actual_musl_loader']=='/lib/ld-musl-x86_64.so.1'
        observer=proof['observer'];assert observer==build['audit']
        assert sha(Path(build['library']))==observer['library_sha256']==audit['source_proofs'][source]['library_sha256']
        assert sha(work/'inputs'/source)==observer['source_sha256']==audit['source_proofs'][source]['source_sha256']
        selected=[row for row in result['rows']if row['case']['source']==source]
        assert sorted(row['case']['op']for row in selected)==proof['successful_abi_cases']==sorted(observer['exported_symbols'])
        assert proof['cases']==selected
        proofs[source]={'proof_sha256':sha(proofpath),'source_sha256':observer['source_sha256'],
                        'library_sha256':observer['library_sha256'],'successful_abi_cases':proof['successful_abi_cases'],
                        'retained_proof':'verification/ownedMULTI008/source41-image-abi-positive/'+proofpath.name}
    assert len(proofs)==6
    for row in result['rows']:
        assert row['passed']is True and row['exit_code']==137 and row['owned_container_absent']is True
        assert row['physical']['verified']is True
        assert row['caller_library_sha256']==caller['library_sha256']
        assert row['caller']['op']==row['case']['op']and row['caller']['unarmed_success']is True and row['caller']['wrapper_resolved']is True
        custody=row['process_custody'];assert custody['kernel_state']=='stopped'and custody['signal_method']=='ancestor-pidfd-SIGSTOP'
        assert custody['observer_library_sha256']==row['observer_library_sha256']==proofs[row['case']['source']]['library_sha256']
        rows.append({'case':row['case'],'container_id':row['container_id'],'exit_code':row['exit_code'],
                     'caller':row['caller'],'physical':row['physical'],'process_custody':custody,
                     'recorded_owned_container_absent':row['owned_container_absent']})
    return {'schema':'adhd/source41-abi-callback-compatible-summary@1','passed':True,
            # Compatibility aliases are derived only from the actual fields.
            'actual_cases':len(rows),'image':result['image_config_identity'],'artifact_sha256':result['artifact_sha256'],
            'canonical_manifest_sha256':plan['canonical_manifest_sha256'],
            'bindings':{'plan_sha256':sha(work/'plan.json'),'result_sha256':sha(work/'result.json'),
                        'driver_sha256':audit['driver_sha256'],'independent_audit_sha256':sha(retained/'audit.json'),
                        'independent_audit':'verification/ownedMULTI008/source41-image-abi-positive/audit.json'},
            'caller':{'source_sha256':caller['source_sha256'],'library_sha256':caller['library_sha256']},
            'source_proofs':proofs,'ordered_rows':rows,
            'cleanup_scope':{'evidence':'Bound original independent audit; this adapter performs no fresh Docker inspection.',
                             'actual_CIDs_independently_audited_absent':len(absence),
                             'recorded_host_pids_independently_audited_absent':True,
                             'issued_name_limitation':audit['issued_name_limitation'],
                             'scoped_name_prefix_census_empty_at_independent_audit':True},
            'scope':'Standalone actual source41 observer forwarding/physical effects/musl loader/STOP-KILL137 custody only; no application callback or recovery-durability execution claim.',
            'application_started':False,'provider_calls':0,'broker_calls':0,'adapter_resource_starts':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();value=derive(args.repo.absolute(),args.work.absolute())
    assert not args.output.exists();args.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'passed':True,'actual_cases':value['actual_cases'],'summary_sha256':sha(args.output)}))
