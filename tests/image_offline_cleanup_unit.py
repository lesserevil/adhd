"""Mocked codec cleanup: no image, executable, application or container starts."""
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from image_eventing_runtime import EventingFaultImage
from image_filesystem_runtime import FilesystemRuntime


def result(code=0,stdout=b'',stderr=b''):
    return SimpleNamespace(returncode=code,stdout=stdout,stderr=stderr)


def run_case(root,mode,primary=None):
    calls=[];attempts=[]
    def transport(*args,check=True):
        calls.append(args);name=args[-1]
        if args[0]=='rm':
            if mode=='rm-error':raise OSError('Synthetic removal transport failure')
            return result()
        if mode in ('unknown','primary-unknown'):return result(1,stderr=b'Cannot connect to Docker daemon')
        if mode=='mixed':return result(1,stderr=('Cannot connect to Docker daemon\nError: No such object: '+name).encode())
        return result(1,stdout=b'[]\n',stderr=('error: no such object: '+name+'\n').encode())
    target=SimpleNamespace(name=None,image_id='sha256:'+'a'*64,cleanup_blocked=False,
        verify=lambda:None,docker=transport,authoritative_absence=EventingFaultImage.authoritative_absence)
    fixture=object.__new__(FilesystemRuntime);fixture.root=root;fixture.target=target
    fixture.offline_helpers=[];fixture.offline_helper_name=None
    def codec(command,**kwargs):
        assert kwargs['check'] is True and kwargs['timeout']==60
        assert '--network' in command and command[command.index('--network')+1]=='none'
        if primary is not None:raise primary
        return subprocess.CompletedProcess(command,0,'synthetic codec result','')
    def forbidden(*a,**k):attempts.append('attempt');raise AssertionError('No process permitted')
    caught=None
    with patch('subprocess.run',codec),patch('subprocess.Popen',forbidden):
        try:value=fixture.offline_elixir('IO.puts("synthetic")',root/'state.snapshot')
        except BaseException as error:caught=error;value=None
    assert len(calls)==2 and calls[0][0]=='rm' and calls[1][0]=='inspect'
    assert fixture.offline_helper_name is None and attempts==[]
    if mode in ('unknown','primary-unknown','mixed'):
        assert caught is not None and target.cleanup_blocked
        assert fixture.offline_helpers[-1]['observed_absent'] is False
    else:
        assert fixture.offline_helpers[-1]['observed_absent'] is True and not target.cleanup_blocked
    if primary is not None:assert caught is primary
    elif mode=='absent':assert caught is None and value.returncode==0
    else:assert caught is not None
    if primary is not None and mode=='primary-unknown':
        assert any('cleanup failures' in note for note in primary.__notes__)
    return fixture


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve()
        run_case(root,'absent')
        run_case(root,'mixed')
        run_case(root,'unknown')
        run_case(root,'rm-error')
        run_case(root,'absent',subprocess.CalledProcessError(7,['synthetic-codec'],output='fixture',stderr='fixture-error'))
        run_case(root,'primary-unknown',subprocess.TimeoutExpired(['synthetic-codec'],60))
    print('PASS offline codec cleanup6: real-format absence, mixed denial, daemon unknown, independent rm-failure inspection, original codec failure, original timeout plus unknown cleanup; process attempts0')


if __name__=='__main__':main()
