"""Exact original ExUnit counts and both formatter styles; no runtime starts."""
from types import SimpleNamespace
from pathlib import Path
from image_recovery_component import qualify_output,validate_job
from image_recovery_remaining_layout import EXUNIT_CASE_COUNTS


def denied(fn):
    try:fn()
    except (AssertionError,KeyError):return
    raise AssertionError('Invalid component summary/count admitted')


def main():
    checks=0
    for name,count in EXUNIT_CASE_COUNTS.items():
        job={'application_integration_claim':False,'name':name,'kind':'exunit','expected_tests':count,'outer_timeout_seconds':600}
        validate_job(job,Path('/owned-output'))
        for summary in (f'{count} tests, 0 failures',f'Result: {count} passed'):
            result=qualify_output(job,SimpleNamespace(returncode=0,stdout=('Unchanged vector output\n'+summary+'\n').encode()))
            assert result['tests']==count and result['failures']==0;checks+=1
        bad={**job,'expected_tests':count+1};denied(lambda:validate_job(bad,Path('/owned-output')));checks+=1
    job={'kind':'exunit','expected_tests':5}
    for summary in ['Result: 4 passed','Result: 0 passed','0 tests, 0 failures','5 tests, 1 failure',
        'Result: 4 passed, 1 failed','Result: 5 passed, 1 skipped','Result: 5 passed, 1 pending',
        '5 tests, 0 failures, 1 skipped','Result: 5 passed extra','5 tests, 0 failures\nResult: 5 passed',
        'Result: 5 passed\nResult: 5 passed','no summary']:
        denied(lambda summary=summary:qualify_output(job,SimpleNamespace(returncode=0,stdout=summary.encode())));checks+=1
    denied(lambda:qualify_output(job,SimpleNamespace(returncode=1,stdout=b'Result: 5 passed')));checks+=1
    print('PASS recovery summary pure'+str(checks)+': exact12original ExUnit counts, modern/legacy summary and wrong-count/nonzero/failure/skip/pending/multiple/unknown denial; actual runtimes0')


if __name__=='__main__':main()
