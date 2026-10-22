"""Recovery-only image observer, PID custody and owned cleanup.

No optimizer-pinned helper is changed. The existing observer compiles the exact
immutable /app/hub.exs prefix and evaluates its unchanged entry. This module adds
no product endpoint, source rewrite, model behavior or host PID namespace.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from uuid import uuid4

import httpx

from container_fixture import OwnedImage
from multi_support import Fixture
from optimization_neutral_runtime import safe_append,regular

OBSERVER='/adhd-test/recovery-observer.exs'
ARTIFACT='/app/hub.exs'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def observer_argv(base,host_observer):
    """Pure argv adaptation; callers verify the actual image via OwnedImage."""
    assert base[:2]==['docker','run'] and re.fullmatch(r'sha256:[a-f0-9]{64}',base[-1])
    assert not any(v=='--pid' or v.startswith('--pid=') for v in base)
    assert '--entrypoint' not in base
    host_observer=Path(host_observer)
    assert host_observer.is_absolute() and ',' not in str(host_observer)
    return base[:-1]+['--mount','type=bind,src='+str(host_observer)+',dst='+OBSERVER+',readonly',
        '--entrypoint','elixir',base[-1],OBSERVER,ARTIFACT]


def namespace_pid(status):
    fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.splitlines() if ':' in line}
    assert fields['Pid']=='1' and fields['Name'] in ('beam.smp','beam')
    chain=[int(value) for value in fields['NSpid'].split()]
    assert chain and chain[-1]==1
    return chain[-1]


def inspected_vm(row,status,exe,cmdline,image_id,observer):
    """Bind namespacePID1 BEAM to its inspected owned container host PID."""
    assert re.fullmatch('[a-f0-9]{64}',row['Id']) and row['Image']==image_id
    assert row['State']['Running'] is True and type(row['State']['Pid']) is int and row['State']['Pid']>0
    assert row['HostConfig']['PidMode'] in ('','private') and row['HostConfig']['ReadonlyRootfs'] is True
    mount=next(v for v in row['Mounts'] if v['Destination']==OBSERVER)
    assert mount['Type']=='bind' and mount['Source']==str(observer) and mount['RW'] is False
    assert Path(exe.strip()).name in ('beam.smp','beam')
    argv=cmdline.split(b'\0')
    assert OBSERVER.encode() in argv and ARTIFACT.encode() in argv
    return {'container_id':row['Id'],'image_config_identity':row['Image'],'host_vm_pid':row['State']['Pid'],
        'namespace_vm_pid':namespace_pid(status),'pid_namespace_mode':row['HostConfig']['PidMode'],
        'vm_executable_basename':Path(exe.strip()).name,'proc1_status_sha256':hashlib.sha256(status.encode()).hexdigest(),
        'proc1_cmdline_sha256':hashlib.sha256(cmdline).hexdigest(),'observer_read_only':True}


def same_vm(first,second):
    for key in ('container_id','image_config_identity','host_vm_pid','namespace_vm_pid'):
        assert first[key]==second[key], 'Owned watched VM changed during same-VM restore'


def bind_down(identity,down,nonce,project):
    assert down['nonce']==nonce and down['project_id']==project and down['reason']=='killed'
    assert int(down['vm_pid'])==identity['namespace_vm_pid']


class ObserverImage(OwnedImage):
    def __init__(self,image,manifest,root,observer):
        assert re.fullmatch(r'sha256:[a-f0-9]{64}',image), 'Recovery image target must be an immutable config ID'
        super().__init__(image,manifest,root)
        observer=Path(observer)
        info=observer.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_nlink==1
        self.observer=observer.resolve()
        self.observer_sha256=digest(self.observer);self.probe_lifecycle=[]
    def observer_unchanged(self):
        info=self.observer.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and digest(self.observer)==self.observer_sha256
    def argv(self,config_file):
        self.observer_unchanged()
        base=super().argv(config_file)
        assert self.image_id==self.requested
        return observer_argv(base,self.observer)
    def probe(self,entrypoint,*args):
        # Same immutable-payload verification as OwnedImage, with explicit
        # custody/absence evidence even if a probe fails before app startup.
        name='adhd-recovery-probe-'+uuid4().hex[:16]
        try:
            return self.docker('run','--rm','--name',name,'--network','none','--read-only',
                '--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint',entrypoint,self.image_id,*args).stdout
        finally:
            self.docker('rm','--force',name,check=False)
            absent=self.docker('inspect',name,check=False)
            assert absent.returncode!=0 and b'no such' in absent.stderr.lower(), 'Owned payload probe absence unproven'
            self.probe_lifecycle.append({'name':name,'entrypoint':entrypoint,'observed_absent':True})
    def stop(self,hard=False):
        try:super().stop(hard=hard)
        except BaseException:
            if self.name is not None:
                self.docker('rm','--force',self.name,check=False)
                assert self.absent(), 'Owned observer container absence unproven after failed stop'
                self.events.append({'action':'forced-cleanup-after-stop-error','container_id':self.container_id,
                    'observed_absent':True})
                self.name=self.container_id=None
            raise
    def watched_vm(self):
        self.observer_unchanged();self.observe()
        before=json.loads(self.docker('inspect',self.name).stdout)[0]
        # Direct reads of /proc/1 describe the watched BEAM, not the docker exec
        # reader process or host-side Docker client. No --pid=host is used.
        status=self.docker('exec',self.name,'cat','/proc/1/status').stdout.decode()
        exe=self.docker('exec',self.name,'readlink','/proc/1/exe').stdout.decode()
        cmdline=self.docker('exec',self.name,'cat','/proc/1/cmdline').stdout
        value=inspected_vm(before,status,exe,cmdline,self.image_id,self.observer)
        after=json.loads(self.docker('inspect',self.name).stdout)[0]
        assert after['Id']==before['Id'] and after['State']['Pid']==before['State']['Pid'] and after['State']['Running'] is True
        return value


class RecoveryImageRuntime(Fixture):
    """Existing declared45/150s readiness; real owned image lifecycle."""
    def __init__(self,args,observer,*,startup_seconds=45):
        assert args.image and not args.with_model and not args.hub and not args.command and not args.rest_url
        assert startup_seconds in (45,150)
        self.startup_seconds=startup_seconds
        super().__init__(args,initialize_projects=False)
        self.image_runtime=ObserverImage(args.image,args.image_manifest,self.root,observer)
        self.vm_observations=[];self.log_identities={};self.cleanup_failure_types=[]
    async def start(self):
        try:
            if not self.file.exists():
                with self.file.open('x') as output:json.dump(self.config,output)
                self.file.chmod(0o600)
            regular(self.file)
            self.logs=[]
            for name in ('stdout.log','stderr.log'):
                handle=safe_append(self.root/name);self.logs.append(handle)
                info=os.fstat(handle.fileno());self.log_identities[name]=(info.st_dev,info.st_ino)
            command=self.image_runtime.argv(self.file)
            self.process=subprocess.Popen(command+[json.dumps(['serve',str(self.file)])],
                stdout=self.logs[0],stderr=self.logs[1],start_new_session=True)
            deadline=time.monotonic()+self.startup_seconds
            async with httpx.AsyncClient() as http:
                while time.monotonic()<deadline:
                    assert self.process.poll() is None, 'Owned image exited during startup'
                    try:response=await http.get(self.base+'/health',timeout=1)
                    except httpx.HTTPError:response=None
                    if response is not None and response.status_code==200:
                        self.image_runtime.observe();self.vm_observations.append(self.image_runtime.watched_vm())
                        return
                    await asyncio.sleep(.1)
            raise AssertionError('Hub readiness deadline exceeded')
        except BaseException:
            try:await self.close()
            except BaseException as cleanup:self.cleanup_failure_types.append(type(cleanup).__name__)
            raise
    def watched_vm(self):
        value=self.image_runtime.watched_vm();self.vm_observations.append(value);return value
    def _close_logs(self):
        error=None
        for log in self.logs:
            try:log.close()
            except BaseException as caught:error=error or caught
        self.logs=[]
        for name,expected in self.log_identities.items():
            try:
                info=regular(self.root/name,private=False)
                assert (info.st_dev,info.st_ino)==expected, 'Subprocess log inode changed'
            except BaseException as caught:error=error or caught
        if error:raise error
    def hard_stop(self):
        self.admin_client=None
        try:
            self.image_runtime.stop(hard=True)
            if self.process:self.process.wait(timeout=15)
        finally:self._close_logs()
    async def close(self):
        errors=[]
        for client in self.clients:
            try:await client.close()
            except BaseException as caught:errors.append(caught)
        self.clients=[]
        try:self.image_runtime.stop()
        except BaseException as caught:errors.append(caught)
        if self.process:
            try:self.process.wait(timeout=15)
            except BaseException as caught:errors.append(caught)
        try:self._close_logs()
        except BaseException as caught:errors.append(caught)
        if self.temp and not errors:self.temp.cleanup();self.temp=None
        self.cleanup_failure_types.extend(type(error).__name__ for error in errors)
        if errors:raise errors[0]
    def bind_evidence(self,evidence,key='runtime'):
        if self.image_runtime.verified:
            super().bind_evidence(evidence,key)
        else:
            evidence.value[key]={'kind':'docker','requested_image_config_identity':self.args.image,
                'payload_verified':False,'container_lifecycle':self.image_runtime.events}
        value=evidence.value[key]
        value.update(observer_sha256=self.image_runtime.observer_sha256,observer_mount=OBSERVER,
            recovery_image_helper_sha256=digest(__file__),startup_seconds=self.startup_seconds,watched_vm_observations=self.vm_observations,
            payload_probe_lifecycle=self.image_runtime.probe_lifecycle,cleanup_failure_types=self.cleanup_failure_types,
            docker_client_pid=None if self.process is None else self.process.pid,
            owned_docker_client_exited=self.process is None or self.process.poll() is not None,
            owned_container_absent=self.image_runtime.name is None)


async def finish_callback(f,evidence,error,close_dependent):
    """Keep original failures and attempt both app and controlled endpoint cleanup."""
    try:
        if f:await f.close()
    except BaseException as caught:
        evidence.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
    finally:
        try:close_dependent()
        except BaseException as caught:
            evidence.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
    try:
        if isinstance(f,RecoveryImageRuntime):f.bind_evidence(evidence)
    except BaseException as caught:
        evidence.value.setdefault('cleanup_failure_types',[]).append(type(caught).__name__);error=error or caught
    evidence.finish(error)
    if error:raise error
