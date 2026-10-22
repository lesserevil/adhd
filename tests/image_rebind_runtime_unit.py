"""Pure actual-image CLI adapter checks; all process/transport boundaries mocked."""
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from image_rebind_runtime import (ImageRebindRuntime, command_config, rebind_argv,
    stop_image_boundary, RebindFaultImage)
from image_filesystem_fault import FilesystemFaultImage


def owner(root):
    value=object.__new__(ImageRebindRuntime);value.root=root;value.sessions=[];value.active=None;value.cleanup_blocked=False
    return value


def returned(root,code=0,primary=None,cleanup=None):
    value=owner(root);actions=[]
    target=SimpleNamespace(last_exit_code=code,name=None,cleanup_blocked=False)
    process=SimpleNamespace(returncode=code)
    def communicate(**kwargs):
        assert 0<kwargs['timeout']<=150
        if primary:raise primary
        return b'{"synthetic":"stdout"}',b'{"synthetic":"stderr"}'
    process.communicate=communicate
    def start(*args,**kwargs):
        assert kwargs['stdout']==subprocess.PIPE and kwargs['stderr']==subprocess.PIPE
        value.active={'target':target,'process':process};return process
    def stop(session,hard=False):
        actions.append(hard);value.active=None
        if cleanup:raise cleanup
    value.start=start;value.stop_session=stop
    caught=None
    try:result=value.run(['rebind-storage',None])
    except BaseException as error:caught=error;result=None
    assert actions==[primary is not None]
    if primary:
        assert caught is primary
        if cleanup:assert any('cleanup failure' in n for n in primary.__notes__)
    elif cleanup:assert caught is cleanup
    else:assert result.returncode==code and result.stdout==b'{"synthetic":"stdout"}'


def start_failure(root):
    value=owner(root);value.args=SimpleNamespace(image='sha256:'+'a'*64,image_manifest=root/'manifest.json');calls=[]
    target=SimpleNamespace(argv=lambda _:['docker','run','--network','host','sha256:'+'a'*64],name='synthetic-owned',cleanup_blocked=False)
    process=SimpleNamespace(wait=lambda **kw:calls.append('wait'))
    def stop(hard=False):calls.append(('stop',hard));target.name=None
    target.stop=stop
    def reject(*args):raise AssertionError('Synthetic VM custody rejection')
    value.observe_vm=reject
    with patch('image_rebind_runtime.RetainedImage',return_value=target),patch('subprocess.Popen',return_value=process):
        try:value.start(['rebind-storage',None],stdout=None,stderr=None,deadline=999999999)
        except AssertionError as error:assert str(error)=='Synthetic VM custody rejection'
        else:raise AssertionError('Unobserved VM accepted')
    assert calls==[('stop',False),'wait'] and value.active is None
    value.cleanup_blocked=True
    with patch('image_rebind_runtime.RetainedImage',side_effect=AssertionError('Must not construct a new target')) as constructor:
        try:value.start(['rebind-storage',None],stdout=None,stderr=None,deadline=999999999)
        except AssertionError:pass
        else:raise AssertionError('Unknown cleanup replacement admitted')
        assert constructor.call_count==0


def boundary(root):
    target=object.__new__(RebindFaultImage);target.last_exit_code=None;calls=[]
    target.public_command=['rebind-storage',{'config_file':str(root/'hub.json')}]
    target.stop_at_observed_boundary=lambda value:calls.append(value)
    process=SimpleNamespace(returncode=None);session={'target':target}
    def stop(value,hard=False):
        assert value is session and hard;process.returncode=137;target.last_exit_code=137;calls.append('hard137')
    process._adhd_image_rebind=(SimpleNamespace(stop_session=stop),session)
    trace={'pid':1,'stage':'registry-durable','directory_fsync_result':0};stop_image_boundary(process,trace)
    assert calls==[trace,'hard137'] and target.expected_public_command()==target.public_command
    base=object.__new__(FilesystemFaultImage);base.config_file=root/'hub.json'
    assert base.expected_public_command()==['serve',str(root/'hub.json')]


def main():
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.run',side_effect=AssertionError('No compiler or process')),patch('subprocess.Popen',side_effect=AssertionError('No actual process')):
        root=Path(directory).resolve()
        artifact=root/'bound.exs';artifact.write_text('synthetic-binding-only')
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'0'*64}}))
        args=SimpleNamespace(image='sha256:'+'a'*64,image_manifest=manifest,artifact=artifact)
        try:ImageRebindRuntime(args,root)
        except AssertionError:pass
        else:raise AssertionError('Unbound artifact admitted')
        manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':hashlib.sha256(artifact.read_bytes()).hexdigest()}}))
        assert ImageRebindRuntime(args,root).sessions==[]
        assert command_config(['serve',str(root/'hub.json')],root)==root/'hub.json'
        assert command_config(['rebind-storage',None],root)==root/'invalid-request-config.json'
        try:command_config(['rebind-storage',{'config_file':'/outside/hub.json'}],root)
        except AssertionError:pass
        else:raise AssertionError('Outside mount command admitted')
        base=['docker','run','--network','host','sha256:'+'a'*64]
        result=rebind_argv(base,'["rebind-storage",null]',True)
        assert result[result.index('--network')+1]=='none' and base[3]=='host'
        assert rebind_argv(base,'["serve","/owned/config"]',False)[3]=='host'
        returned(root);returned(root,1)
        primary=subprocess.TimeoutExpired(['synthetic'],150);returned(root,primary=primary)
        returned(root,primary=RuntimeError('Original codec failure'),cleanup=OSError('Unconfirmed cleanup'))
        returned(root,cleanup=OSError('Unconfirmed cleanup'))
        start_failure(root);boundary(root)
    print('PASS image rebind preparation10: inert artifact binding, owned absolute argv/modes, stdout+stderr+exit, original timeout/errors, independent cleanup denial, rejected VM cleanup, replacement fence, source-bound public command and hard137; compiler/app/process attempts0')


if __name__=='__main__':main()
