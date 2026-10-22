"""Read-only full52 transformation checks; no executable plan or runtimes."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
from image_recovery_remaining_layout import layout,HTTP,TRANSPORT,CALLBACKS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--original-plan',type=Path,required=True);args=parser.parse_args()
    original=json.loads(args.original_plan.read_text());before=copy.deepcopy(original)
    with patch('subprocess.run',side_effect=AssertionError('No process')),patch('subprocess.Popen',side_effect=AssertionError('No process')):
        value=layout(original)
    assert original==before and value['execution_implemented'] is False and not value['runtime_ready']
    assert value['planned_rows']==value['unrun_rows']==42 and value['executed_rows']==0
    assert value['families']=={'http':7,'learned':1,'crash':15,'component':17,'rebind':2}
    assert {r['name'] for r in value['separate_dependencies']}==set(TRANSPORT+CALLBACKS)
    rows={r['name']:r for r in value['selected_rows']}
    for name,row in rows.items():
        assert row['original']==next(r for r in original['serial_lane'] if r['name']==name)
        assert row['outer_timeout_seconds']==row['original']['outer_timeout_seconds']
        if row['family']=='component':
            job=row['component_job'];assert job['application_integration_claim'] is False and job['cwd']==original['cwd']
            assert job['script']==row['original']['argv'][1] and len(job['arguments'])==len(row['original']['argv'])-2
            for old,new in zip(row['original']['argv'][2:],job['arguments']):
                if old==original['artifact']['path']:assert new=='/app/hub.exs'
                elif old.startswith(original['results_root']+'/'):assert new.startswith(job['work']+'/')
                else:assert new==old
            if 'report' in job:assert job['report'].startswith(job['work']+'/')
        else:
            argv=row['harness_arguments'];assert '--image' in argv and '--image-manifest' in argv and '--hub' not in argv and '--command' not in argv
            assert row['entry_wrapper']['timeout']==row['outer_timeout_seconds']
            for flag in ['--crash-at','--deadline','--producer-command','--producer-root','--producer-report']:
                if flag in row['original']['argv']:assert argv[argv.index(flag)+1]==row['original']['argv'][row['original']['argv'].index(flag)+1]
            for flag in ['--no-default','--archived','--damage-stage']:
                assert (flag in argv)==(flag in row['original']['argv'])
    assert rows['mixed']['outer_timeout_seconds']==5400 and rows['learned']['outer_timeout_seconds']==1800
    assert all(rows[n]['outer_timeout_seconds']==2400 for n in ('rebind','rebind-hostile'))
    assert len(rows['primitive-journal']['component_job']['readonly_mounts'])==3
    for corrupt in ['missing','duplicate']:
        bad=copy.deepcopy(original)
        if corrupt=='missing':bad['serial_lane'].pop()
        else:bad['serial_lane'][-1]=bad['serial_lane'][0]
        try:layout(bad)
        except AssertionError:pass
        else:raise AssertionError('Incomplete/duplicate full52 accepted')
    print('PASS remaining layout pure8: full52 identity+42 partition, all original cases/bounds/variant flags and producer command, original image payload, owned component outputs, full journal mounts, missing/duplicate denial; runtime/process calls0')


if __name__=='__main__':main()
