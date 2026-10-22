"""Run one unchanged pure/component vector program under the exact image OTP.

Preparation is inert. This qualifies component-runtime behavior, never a deployed
hub or lifecycle admission. Read-only fixtures retain their absolute path binds.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from image_recovery_remaining_layout import EXUNIT_CASE_COUNTS
from image_filesystem_fault import RetainedImage
from image_rebind_runtime import ImageRebindRuntime

CAPSULE='''
[script,metadata,release,bound|args]=System.argv()
temporary=metadata<>".new"
File.open!(temporary,[:write,:exclusive],fn io->IO.write(io,System.pid()<>"\\n"<>to_string(:erlang.system_info(:otp_release))<>"\\n"<>System.version()<>"\\n") end)
File.chmod!(temporary,0o600)
File.rename!(temporary,metadata)
deadline=System.monotonic_time(:millisecond)+String.to_integer(bound)
wait=fn again->
  cond do
    File.regular?(release)->:ok
    System.monotonic_time(:millisecond)>=deadline->raise "Component custody barrier expired"
    true->Process.sleep(10);again.(again)
  end
end
wait.(wait)
System.argv(args)
Code.require_file(script)
'''


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def component_argv(base,script,arguments,mounts,metadata,release,timeout,cwd):
    assert base[:2]==['docker','run'] and '--rm' not in base
    assert base[base.index('--network')+1]=='host'
    result=list(base);result[result.index('--network')+1]='none'
    additions=[];destinations=[]
    for source,destination in mounts:
        source=Path(source).absolute();destination=Path(destination)
        assert source.resolve(strict=True)==source and destination.is_absolute() and '..' not in destination.parts
        protected=[Path(p) for p in ['/app','/proc','/sys','/dev','/tmp']]+[Path(metadata).parent]
        assert not any(destination==p or destination.is_relative_to(p) or p.is_relative_to(destination) for p in protected)
        assert not any(destination==p or destination.is_relative_to(p) or p.is_relative_to(destination) for p in destinations)
        destinations.append(destination)
        assert ',' not in str(source) and ',' not in str(destination)
        additions+=['--mount',f'type=bind,src={source},dst={destination},readonly']
    assert Path(script).is_absolute() and all(isinstance(value,str) and '\0' not in value for value in arguments)
    assert Path(metadata).is_absolute() and Path(release).is_absolute() and timeout>0
    assert Path(cwd).is_absolute() and '..' not in Path(cwd).parts
    assert any(Path(script).is_relative_to(p) and Path(script)!=p for p in destinations)
    assert any(Path(cwd)==p or Path(cwd).is_relative_to(p) for p in destinations)
    return result[:-1]+additions+['--workdir',str(cwd),'--entrypoint','elixir',result[-1],'-e',CAPSULE,'--',str(script),str(metadata),str(release),str(int(timeout*1000)),*arguments]


class ImageComponentRuntime(ImageRebindRuntime):
    def run_component(self,script,arguments,mounts,timeout,cwd):
        assert self.active is None and not self.cleanup_blocked
        target=RetainedImage(self.args.image,self.args.image_manifest,self.root)
        session={'target':target,'process':None,'command_kind':'component','serialized':'','offline':True,'custody':None,
            'component_argv':[str(script),*arguments]}
        self.active=session;self.sessions.append(session);primary=None;deadline=time.monotonic()+timeout
        metadata=self.root/'component-runtime.txt';release=self.root/'component-release'
        assert not metadata.exists() and not release.exists()
        try:
            argv=component_argv(target.argv(self.root/'unused-component-config.json'),script,arguments,mounts,metadata,release,timeout,cwd)
            process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            session['process']=process
            self.observe_vm(session,deadline)
            # The actual PID1 interpreter pauses BEFORE unchanged vectors load,
            # avoiding an exit race and a separate-VM version inference.
            while not metadata.exists() and time.monotonic()<deadline:
                assert process.poll() is None;time.sleep(.01)
            info=metadata.lstat()
            assert metadata.is_file() and not metadata.is_symlink() and info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size<=1024
            assert info.st_mode & 0o077==0
            version=metadata.read_text().splitlines();assert len(version)==3 and version[:2]==['1','29']
            session['runtime_version']={'namespace_pid':1,'otp_release':version[1],'elixir_version':version[2],
                'actual_pid1_metadata_sha256':sha(metadata),'capsule_sha256':hashlib.sha256(CAPSULE.encode()).hexdigest()}
            descriptor=os.open(release,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_CLOEXEC,0o600)
            with os.fdopen(descriptor,'w') as gate:gate.write('owned VM verified\n')
            stdout,stderr=process.communicate(timeout=max(.001,deadline-time.monotonic()))
            session['client_exit_code']=process.returncode
            return subprocess.CompletedProcess(argv,process.returncode,stdout,stderr)
        except BaseException as error:primary=error;raise
        finally:
            try:
                self.stop_session(session,hard=primary is not None and session['custody'] is not None)
                if primary is None:assert target.last_exit_code==session['client_exit_code']
            except BaseException as cleanup:
                if primary is not None:primary.add_note('Component image cleanup failure: '+type(cleanup).__name__)
                else:raise


def qualify_output(job,result):
    assert result.returncode==0,'Component image exited unsuccessfully'
    if job['kind']=='exunit':
        expected=job['expected_tests']
        assert type(expected) is int and expected>0
        text=result.stdout.decode('utf-8')
        summaries=[line.strip() for line in text.splitlines() if re.match(r'^\s*(?:Result:|[0-9]+ tests?\b)',line)]
        assert len(summaries)==1,'Missing or multiple ExUnit summaries'
        summary=summaries[0]
        legacy=re.fullmatch(r'(\d+) tests?, (\d+) failures?',summary)
        modern=re.fullmatch(r'Result: (\d+) passed',summary)
        assert legacy or modern,'Failed/skipped/pending/unknown ExUnit summary'
        count=int((legacy or modern).group(1))
        assert count==expected and (legacy is None or int(legacy.group(2))==0)
        return {'tests':count,'failures':0,'expected_tests':expected,
                'summary_format':'legacy' if legacy else 'elixir1.20'}
    value=json.loads(Path(job['report']).read_text());assert value['passed'] is True
    return {'child_report_sha256':sha(job['report'])}


def validate_job(job,work):
    assert job['application_integration_claim'] is False and job['kind'] in ('exunit','json')
    assert type(job['outer_timeout_seconds']) is int and 0<job['outer_timeout_seconds']<=900
    if job['kind']=='exunit':
        assert job['name'] in EXUNIT_CASE_COUNTS and job['expected_tests']==EXUNIT_CASE_COUNTS[job['name']]
    if job['kind']=='json':
        report=Path(job['report']);assert report.is_absolute() and '..' not in report.parts
        assert report.is_relative_to(work) and report!=work
    return job


def write_report(path,report,primary):
    try:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')
    except BaseException as error:
        if primary is not None:primary.add_note('Component report failure: '+type(error).__name__)
        else:raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['image','image-manifest','artifact','job','job-sha256','work','report']:
        parser.add_argument('--'+name,required=True,type=Path if name in ['image-manifest','artifact','job','work','report'] else str)
    args=parser.parse_args();assert sha(args.job)==args.job_sha256
    work=args.work.absolute();assert not work.exists() and '..' not in work.parts
    job=validate_job(json.loads(args.job.read_text()),work)
    work.mkdir(parents=True,mode=0o700)
    args.image_fault_library=args.image_fault_proof=None
    runtime=ImageComponentRuntime(args,work);primary=None;result=None;checks={}
    try:
        result=runtime.run_component(job['script'],job['arguments'],job['readonly_mounts'],job['outer_timeout_seconds'],job['cwd'])
        (work/'stdout.log').write_bytes(result.stdout);(work/'stderr.log').write_bytes(result.stderr)
        checks=qualify_output(job,result)
    except BaseException as error:primary=error;raise
    finally:
        report={'schema':'adhd/image-recovery-component@1','passed':primary is None,'application_integration_claim':False,
            'job_sha256':args.job_sha256,'name':job['name'],'artifact_sha256':runtime.manifest['files']['hub.exs'],
            'image_config_identity':args.image,'failure_type':type(primary).__name__ if primary else None,
            'scope':'Unchanged pure/component vectors under exact image OTP29; not a deployed hub or admission claim.',
            'checks':checks,'runtime':runtime.evidence()}
        report['runtime_versions']=[s.get('runtime_version') for s in runtime.sessions]
        write_report(args.report,report,primary)


if __name__=='__main__':main()
