"""Pure component capsule argv/qualification and retained cleanup dispatch."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from image_recovery_component import component_argv,CAPSULE,ImageComponentRuntime,qualify_output,validate_job,write_report


def main():
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.run',side_effect=AssertionError('No compiler or process')),patch('subprocess.Popen',side_effect=AssertionError('No actual process')):
        root=Path(directory).resolve();source=root/'readonly';source.mkdir();out=root/'output';out.mkdir()
        script=Path('/original/frozen/tests/vector.exs');args=['/app/hub.exs','/original/frozen/source38',str(out/'result.json')]
        base=['docker','run','--network','host','--read-only','sha256:'+'a'*64]
        argv=component_argv(base,script,args,[(str(source),'/original/frozen')],out/'runtime.txt',out/'release',600,'/original/frozen')
        assert argv[argv.index('--network')+1]=='none' and '--rm' not in argv
        assert 'type=bind,src='+str(source)+',dst=/original/frozen,readonly' in argv
        assert argv[argv.index('--workdir')+1]=='/original/frozen' and argv[-3:]==args and base[3]=='host'
        assert 'System.argv(args)' in CAPSULE and 'Code.require_file(script)' in CAPSULE and 'File.rename!(temporary,metadata)' in CAPSULE
        try:component_argv(base,script,args,[(str(source),'/app')],out/'m',out/'r',600,'/original/frozen')
        except AssertionError:pass
        else:raise AssertionError('Payload-overriding mount admitted')
        for destination in ['/', '/original/frozen/../app', str(out)]:
            try:component_argv(base,script,args,[(str(source),destination)],out/'m',out/'r',600,'/original/frozen')
            except AssertionError:pass
            else:raise AssertionError('Unsafe mount accepted: '+destination)
        validate_job({'application_integration_claim':False,'kind':'json','outer_timeout_seconds':900,'report':str(out/'result.json')},out)
        for destination in [str(root/'foreign.json'),str(out/'..'/'foreign.json')]:
            try:validate_job({'application_integration_claim':False,'kind':'json','outer_timeout_seconds':900,'report':destination},out)
            except AssertionError:pass
            else:raise AssertionError('Unowned child report admitted')
        child=out/'result.json';child.write_text('{"passed":true}')
        assert qualify_output({'kind':'json','report':str(child)},SimpleNamespace(returncode=0))['child_report_sha256']
        primary=RuntimeError('preserved primary')
        with patch.object(Path,'write_text',side_effect=OSError('mocked report failure')):
            write_report(out/'failed.json',{'passed':False},primary)
            assert any('Component report failure: OSError' in note for note in primary.__notes__)
            try:write_report(out/'failed.json',{'passed':True},None)
            except OSError:pass
            else:raise AssertionError('Successful qualification masked report failure')
        assert qualify_output({'kind':'exunit','expected_tests':12},SimpleNamespace(returncode=0,stdout=b'Finished\n12 tests, 0 failures\n'))['tests']==12
        for raw in [b'0 tests, 0 failures',b'12 tests, 1 failures',b'PASS',b'Result: 12 passed, 1 failed',b'Result: 12 passed, 1 skipped',b'Result: 12 passed, 1 pending',b'Result: 0 passed',b'Result: 11 passed',b'Result: 12 passed\nResult: 12 passed',b'12 tests, 0 failures\nResult: 12 passed',b'Result: 12 passed extra']:
            try:qualify_output({'kind':'exunit','expected_tests':12},SimpleNamespace(returncode=0,stdout=raw))
            except AssertionError:pass
            else:raise AssertionError('Invalid test outcome accepted')
        assert qualify_output({'kind':'exunit','expected_tests':5},SimpleNamespace(returncode=0,stdout=b'Running ExUnit\n.....\nResult: 5 passed\n'))['tests']==5
        try:qualify_output({'kind':'exunit','expected_tests':5},SimpleNamespace(returncode=1,stdout=b'Result: 5 passed\n'))
        except AssertionError:pass
        else:raise AssertionError('Nonzero child with passing-looking summary accepted')
        validate_job({'application_integration_claim':False,'kind':'exunit','name':'primitive-allocator','expected_tests':5,'outer_timeout_seconds':600},out)
        try:validate_job({'application_integration_claim':False,'kind':'exunit','name':'primitive-allocator','expected_tests':4,'outer_timeout_seconds':600},out)
        except AssertionError:pass
        else:raise AssertionError('Original vector count changed')
        runtime=object.__new__(ImageComponentRuntime);runtime.args=SimpleNamespace(image='sha256:'+'a'*64,image_manifest=root/'manifest.json');runtime.root=out
        runtime.active=None;runtime.cleanup_blocked=False;runtime.sessions=[]
        target=SimpleNamespace(argv=lambda _:base,last_exit_code=0,name='synthetic-owned',cleanup_blocked=False)
        actions=[]
        def stop(hard=False):actions.append(hard);target.name=None
        target.stop=stop
        process=SimpleNamespace(returncode=0,poll=lambda:None,wait=lambda **kw:0,
            communicate=lambda **kw:(b'2 tests, 0 failures\n',b''))
        def observed(session,deadline):
            session['custody']={'namespace_pid':1};p=out/'component-runtime.txt';p.write_text('1\n29\n1.19.0\n');p.chmod(0o600)
        runtime.observe_vm=observed
        with patch('image_recovery_component.RetainedImage',return_value=target),patch('subprocess.Popen',return_value=process):
            result=runtime.run_component(script,args,[(str(source),'/original/frozen')],600,'/original/frozen')
        assert result.returncode==0 and actions==[False] and (out/'component-release').is_file()
        assert runtime.sessions[0]['runtime_version']['otp_release']=='29' and runtime.active is None
    print('PASS image component preparation10: readonly original paths/cwd, networknone, immutable payload mount denial, actual-PID1 capsule barrier shape, strict test outcomes, retained closure, mount ancestor/traversal and output containment, actual child JSON, report-primary preservation; compiler/app/process attempts0')


if __name__=='__main__':main()
