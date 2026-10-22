"""Derive a non-executable image recovery layout from all52 original rows.

This intentionally cannot freeze or execute a qualification. Root must first
review the shared custody/probe fixes, actual admitted successor and its ABI
proofs. Exact input snapshots and final once-gated driver are a later step.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

TRANSPORT=('schema-export','openapi-export','contract','combined-protocol','wire')
CALLBACKS=('pending-model','pending-kafka','outgoing-queries','incoming-queries','peer-epoch')
HTTP=('admission','rejections','private','agent-admission','uninitialized-move','mixed','federation-errors')


EPOCH_BEFORE=b"~w(domain projects directory project_backup storage_registry config resources store)"
EPOCH_AFTER=b"~w(domain projects directory project_backup storage_registry config resources storage store)"

def epoch_fixture_overlay(raw):
    assert raw.count(EPOCH_BEFORE)==1 and EPOCH_AFTER not in raw
    return raw.replace(EPOCH_BEFORE,EPOCH_AFTER,1)


def replace_option(argv,key,value):
    result=list(argv);index=result.index(key);result[index:index+2]=value;return result


def layout(plan):
    rows=plan['serial_lane'];assert len(rows)==52 and len({r['name'] for r in rows})==52
    origin=Path(plan['cwd']);results=Path(plan['results_root']);artifact=plan['artifact']['path']
    def host_value(value):
        if value==artifact:return '${ARTIFACT}'
        if value==str(origin) or value.startswith(str(origin)+'/'):return '${FROZEN}'+value[len(str(origin)):]
        if value==str(results) or value.startswith(str(results)+'/'):return '${RESULTS}'+value[len(str(results)):]
        return value
    selected=[];dependencies=[]
    epoch=origin/'tests/project_epoch_fences.exs';epoch_raw=epoch.read_bytes();epoch_fixed=epoch_fixture_overlay(epoch_raw)
    amendments=[{'row':'primitive-query-validator','kind':'existing-argument','append':'--fixed-baseline',
        'approved_native_plan_sha256':'c78973b2033a7c991ad9315d7e7a29e39c4ef05aebf4e6971e4b19402fcbdf88',
        'reason':'Current fixed validator expects successful baseline; preserves all14 strict negative vectors.'},
        {'row':'primitive-epoch','kind':'one-token-fixture-overlay','approved_commit':'263f6b4935d78da0b977b45bd8454e25f3033633',
        'path':'tests/project_epoch_fences.exs','original_sha256':hashlib.sha256(epoch_raw).hexdigest(),
        'amended_sha256':hashlib.sha256(epoch_fixed).hexdigest(),
        'reason':'Load actual Storage module required by isolated epoch Store fixture; all assertions and deadlines byte-identical.'}]
    for original in rows:
        row=copy.deepcopy(original);name=row['name'];timeout=row['outer_timeout_seconds']
        if name in TRANSPORT+CALLBACKS:
            dependencies.append({'name':name,'status':'separate-transport-gate' if name in TRANSPORT else 'completed-independent-image5/28','original':row});continue
        assert name in HTTP or name=='learned' or name.startswith(('crash-','primitive-')) or name in ('rebind','rebind-hostile')
        descriptor={'name':name,'original':row,'outer_timeout_seconds':timeout,'executed':False,'runtime_ready':False,
            'entry_wrapper':{'script':'${FROZEN}/tests/image_recovery_entry.py','harness_sha256':'${FROZEN_HARNESS_SHA256}',
                'timeout':timeout,'cleanup_report':'${RESULTS}/'+name+'-cleanup.json'}}
        if name.startswith('primitive-'):
            arguments=[]
            for value in row['argv'][2:]:
                # Original read-only fixture paths/cwd remain exact inside the
                # namespace. Only the actual payload and owned outputs change.
                if value==artifact:value='/app/hub.exs'
                elif value==str(results) or value.startswith(str(results)+'/'):value='${RESULTS}/'+name+'-capsule-work'+value[len(str(results)):]
                arguments.append(value)
            if name=='primitive-query-validator':arguments.append('--fixed-baseline')
            descriptor.update(family='component',harness='${FROZEN}/tests/image_recovery_component.py',component_job={
                'application_integration_claim':False,'name':name,'kind':'exunit' if row['kind']=='exunit' else 'json',
                'script':row['argv'][1],'arguments':arguments,'outer_timeout_seconds':timeout,'cwd':str(origin),
                'readonly_mounts':[['${COMPONENT_SNAPSHOT}',str(origin)]],
                'work':'${RESULTS}/'+name+'-capsule-work'})
            if row.get('report'):descriptor['component_job']['report']='${RESULTS}/'+name+'-capsule-work'+row['report'][len(str(results)):]
            if name=='primitive-journal':
                journal=Path(row['argv'][-1]);descriptor['component_job']['readonly_mounts'] += [
                    ['${JOURNAL_CONFIG_COPY}',str(journal)],['${JOURNAL_RECOVERY_COPY}',str(journal)+'.recovery']]
            descriptor['component_requirements']=[
                'Copy original frozen fixture tree byte-identically and bind read-only at original absolute cwd; no originals rewritten.',
                'Replace only copied target source/spec bytes with exact selected admitted image authority; statically assemble full declared source list to actual /app/hub.exs SHA.',
                'Actual PID1 BEAM/private namespace/immutable image and OTP29 runtime metadata barrier before unchanged vectors; network none; owned output only.',
                'Use source-bound actual image component helper; preserve original timeout and ExUnit/JSON outcomes.']
        else:
            argv=[host_value(v) for v in row['argv'][2:]]
            if '--hub' in argv:argv=replace_option(argv,'--hub',['--image','${IMAGE}','--image-manifest','${MANIFEST}'])
            else:
                assert name in ('rebind','rebind-hostile')
                argv=replace_option(argv,'--command',['--image','${IMAGE}','--image-manifest','${MANIFEST}'])
            if name.startswith('crash-') or name=='rebind':
                family='project_recovery_fault' if name.startswith('crash-') else 'rebind_fault'
                argv += ['--image-fault-library','${'+family.upper()+'_LIBRARY}',
                    '--image-fault-proof','${'+family.upper()+'_PROOF}']
            descriptor.update(family=('http' if name in HTTP else 'learned' if name=='learned' else 'crash' if name.startswith('crash-') else 'rebind'),
                harness='${FROZEN}/tests/'+Path(row['argv'][1]).name,harness_arguments=argv)
            if name=='learned':descriptor['requirements']=[
                'Actual accepted producer report/artifact and six retained source files remain hash-bound before/after; no fabricated selection.',
                'Producer process-local deny fence plus loaded-map and denied-connect audit; all effective root/project routes checked.',
                'Private image network and actual in-namespace refusal of historical loopback provider routes; no provider calls.']
        selected.append(descriptor)
    counts={kind:sum(r['family']==kind for r in selected) for kind in ('http','learned','crash','component','rebind')}
    assert counts=={'http':7,'learned':1,'crash':15,'component':17,'rebind':2} and len(dependencies)==10
    assert all(r['outer_timeout_seconds']==r['original']['outer_timeout_seconds'] for r in selected)
    return {'schema':'adhd/image-recovery-layout-only@1','execution_authorized':False,'execution_implemented':False,
        'runtime_ready':False,'executed':False,'planned_rows':42,'executed_rows':0,'unrun_rows':42,'families':counts,
        'fixture_amendments':amendments,'original_full52_rows':52,'selected_rows':selected,'separate_dependencies':dependencies,
        'constraints':['Descriptor templates only; deliberately not an executable or final frozen plan.',
            'Diagnostic admitted38 has known ownership defect; corrected successor requires fresh admitted image/input/ABI proof binding.',
            'Wait for root custody/probe fixes and full helper review before final snapshot; then full SET/no symlinks/hash/root/input/tool bindings, actual driver hash, exclusive fsynced once gate.',
            'Final execution serial fail-fast, explicit attempted/executed/unrun, no resampling; original bounds/scenarios/assertions unchanged; only two explicit reviewed fixture amendments.',
            'Entry supervisor retains BaseException deadline+finally/owned cleanup; child success needs exit0 and report passedtrue and complete runtime custody after cleanup.',
            'All17 component rows are component-runtime evidence, never additional deployed-hub integration or admission claims.',
            'Completed callback5/28 and first5 transport rows remain separate evidence;42 does not relabel full52 closed.',
            'No app/model/compiler/loader/broker services start during layout derivation.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--original-plan',type=Path,required=True)
    parser.add_argument('--original-sha256',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.original_plan.read_bytes();assert hashlib.sha256(raw).hexdigest()==args.original_sha256
    result=layout(json.loads(raw));result['original_plan_sha256']=args.original_sha256
    assert not args.output.exists();args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:json.dump(result,output,indent=2);output.write('\n')
    print('Prepared non-executable recovery layout42; runtime starts0')


if __name__=='__main__':main()
