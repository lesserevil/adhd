"""Concrete image runtime for unchanged ACME scenarios; inert until start/run.

Uses admitted default ENTRYPOINT and actual inspected BEAM PID. Popen.pid remains
its real Docker-client PID; it is never disguised as the VM. No native cache or
module replacement is used, including the offline public rebind CLI.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
from acme_runtime import PublicClient,regular,sha,ticks
from acme_process_observer import Descendants


def runtime_class(target,mount_root):
    mount_root=Path(mount_root).absolute()
    class ImageRuntime:
        image_mode=True
        qualification_scope='Actual admitted compiled image/default ENTRYPOINT with real local issuer. Runtime proof only after all original cases and custody pass; no public CA/browser qualification inferred.'
        def __init__(self,root,source,cache,elixir,cache_manifest_sha256,*,erlang,peer_trust=None,peer_hosts=()):
            assert source is cache is elixir is erlang is cache_manifest_sha256 is None,'Image mode must not use native cache/launcher'
            self.root=Path(root).absolute();assert self.root==self.root.resolve()and self.root.is_relative_to(mount_root)
            self.file=self.root/'hub.json';self.identities=[];self.process=None;self.image=None;self.logs=[];self.log_ids=[]
            self.peer_trust=peer_trust;self.peer_hosts=tuple(peer_hosts);self.pid_ticks=None
            self.offline_sessions=[];self.observer=None

        @staticmethod
        def binary_pair(args):
            pair={name:target.assets[name]['sha256']for name in ['lego','acme-guard']}
            assert args.lego_sha256==pair['lego']and args.guardian_sha256==pair['acme-guard']
            return pair

        def verify(self):return target.evidence()

        def _logs(self):
            for name in ['stdout.log','stderr.log']:
                path=self.root/name;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
                stream=os.fdopen(fd,'ab',buffering=0);self.logs.append(stream)
                entry=os.fstat(fd);assert stat.S_ISREG(entry.st_mode)and entry.st_uid==os.getuid()and entry.st_nlink==1
                self.log_ids.append((path,entry.st_dev,entry.st_ino))

        def _peer_environment(self,argv):
            flags='+S 2:2'
            if self.peer_trust:
                original=Path(self.peer_trust);regular(original)
                copied=self.root/'owned-peer-root.pem'
                if copied.exists():regular(copied);assert copied.read_bytes()==original.read_bytes()
                else:
                    fd=os.open(copied,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'wb')as stream:stream.write(original.read_bytes())
                assert re.fullmatch('[A-Za-z0-9_./-]+',str(copied))
                flags+=' -public_key cacerts_path '+"'"+json.dumps(str(copied))+"'"
            if self.peer_hosts:
                assert set(self.peer_hosts)<={'one.acme.test','two.acme.test'}
                inetrc=self.root/'owned-peer.inetrc'
                text='{lookup, [file]}.\n'+''.join('{host, {127,0,0,1}, ['+json.dumps(x)+']}.\n'for x in self.peer_hosts)
                if inetrc.exists():regular(inetrc);assert inetrc.read_text()==text
                else:
                    fd=os.open(inetrc,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'w')as stream:stream.write(text)
                assert re.fullmatch('[A-Za-z0-9_./-]+',str(inetrc))
                flags+=' -kernel inetrc '+"'"+json.dumps(str(inetrc))+"'"
            return argv[:-1]+['--env','ERL_FLAGS='+flags]+argv[-1:]

        def _observe(self,image,process,deadline):
            while time.monotonic()<deadline:
                row=image.checked_row()
                if row is not None and row['State'].get('Running')and row['State'].get('Pid'):
                    pid=row['State']['Pid']
                    try:exe=Path(os.readlink('/proc/'+str(pid)+'/exe')).name
                    except FileNotFoundError:exe=None
                    if exe=='beam.smp':image.observe();return image.runtime_rows[-1]
                assert process.poll()is None,'Actual image client exited before VM custody'
                time.sleep(.02)
            raise AssertionError('Original45s image VM/readiness bound')

        def start(self):
            assert self.process is None and self.image is None
            regular(self.file)
            self.base='http://127.0.0.1:'+str(json.loads(self.file.read_text())['port'])
            self.image=target.image(mount_root)
            self.image.verify()
            row={'kind':'compiled-image','binding':target.evidence(),'pid':None,'start_ticks':None,
                 'reaped':False,'config_path_sha256':hashlib.sha256(str(self.file).encode()).hexdigest()}
            self.identities.append(row)
            try:
                self._logs();argv=self._peer_environment(self.image.argv(self.file))
                row['started_monotonic']=time.monotonic();deadline=row['started_monotonic']+45
                self.process=subprocess.Popen(argv,stdout=self.logs[0],stderr=self.logs[1],start_new_session=True,env=self.image.env)
                self.pid_ticks=ticks(self.process.pid);assert self.pid_ticks is not None
                row.update(client_pid=self.process.pid,client_start_ticks=self.pid_ticks)
                vm=self._observe(self.image,self.process,deadline)
                row.update(pid=vm['host_vm_pid'],start_ticks=vm['host_vm_start_ticks'],actual_vm=vm)
                self.observer=Descendants(row['pid'],row['start_ticks']).start()
                while time.monotonic()<deadline:
                    assert self.process.poll()is None,'Image exited before readiness'
                    try:
                        if PublicClient(self.base).request('/health',timeout=1)[0]==200:
                            self.checkpoint('initial-ready');row['first_health_monotonic']=time.monotonic();return self
                    except (OSError,TimeoutError):pass
                    time.sleep(.1)
                raise AssertionError('Original45s readiness bound')
            except BaseException as error:
                try:self.stop()
                except BaseException as cleanup:error.add_note('Owned image startup cleanup: '+type(cleanup).__name__)
                raise

        def checkpoint(self,name):
            if self.image is None:return
            self.image.observe()
            row=self.identities[-1];vm=self.image.runtime_rows[-1]
            assert (vm['host_vm_pid'],vm['host_vm_start_ticks'])==(row['pid'],row['start_ticks'])
            row.setdefault('checkpoints',[]).append(name)

        def stop(self,hard=False):
            primary=None
            try:
                if self.image:self.image.stop(hard=hard)
            except BaseException as error:primary=error
            try:
                if self.process:
                    try:self.process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        assert ticks(self.process.pid)==self.pid_ticks
                        os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=5)
                        raise AssertionError('Owned Docker client required fallback kill')
                    if self.identities:
                        row=self.identities[-1]
                        row.update(reaped=True,exit_code=self.process.returncode,
                          client_original_identity_absent=ticks(self.process.pid)!=self.pid_ticks,
                          original_identity_absent=row['pid']is None or ticks(row['pid'])!=row['start_ticks'])
                        assert row['client_original_identity_absent']and row['original_identity_absent']
            except BaseException as error:
                if primary:primary.add_note('Owned Docker client cleanup: '+type(error).__name__)
                else:primary=error
            finally:
                if self.observer:
                    try:self.observer.close()
                    except BaseException as error:
                        if primary:primary.add_note('Image descendants: '+type(error).__name__)
                        else:primary=error
                    finally:
                        self.identities[-1]['observed_descendants']=self.observer.evidence();self.observer=None
                if self.image and self.identities:
                    self.identities[-1]['container_lifecycle']=list(self.image.events)
                    self.identities[-1]['runtime_custody']=list(self.image.runtime_rows)
                if self.image is not None and self.image.name is None:self.image=None
                if self.process is not None and self.process.poll()is not None:self.process=None
                for stream in self.logs:stream.close()
                self.logs=[]
                for path,dev,ino in self.log_ids:
                    entry=regular(path);assert(entry.st_dev,entry.st_ino)==(dev,ino)
                self.log_ids=[]
            if primary:raise primary

        def offline_rebind(self,request,stdout,stderr,timeout=150):
            image=target.image(mount_root);process=None;primary=None
            identity={'kind':'image-offline-cli','pid':None,'start_ticks':None,'reaped':False}
            self.offline_sessions.append(identity)
            deadline=None
            try:
                serialized=json.dumps(['rebind-storage',request])
                image.expected_cmd=[serialized];image.expected_network='none'
                argv=image.argv(self.file);argv[argv.index('--network')+1]='none';argv.append(serialized)
                with Path(stdout).open('xb')as out,Path(stderr).open('xb')as err:
                    Path(stdout).chmod(0o600);Path(stderr).chmod(0o600)
                    deadline=time.monotonic()+timeout
                    process=subprocess.Popen(argv,stdout=out,stderr=err,start_new_session=True,env=image.env)
                    identity.update(pid=process.pid,start_ticks=ticks(process.pid))
                    assert identity['start_ticks']is not None
                    identity['actual_vm']=self._observe(image,process,deadline)
                    process.wait(timeout=max(.001,deadline-time.monotonic()))
                    identity['exit_code']=process.returncode
                return subprocess.CompletedProcess(['rebind-storage'],process.returncode),identity
            except BaseException as error:primary=error;raise
            finally:
                try:
                    image.stop(hard=primary is not None)
                    if process:
                        process.wait(timeout=15)
                        identity.update(reaped=True,original_identity_absent=ticks(process.pid)!=identity['start_ticks'])
                        assert identity['original_identity_absent']
                    identity['container_lifecycle']=list(image.events);identity['runtime_custody']=list(image.runtime_rows)
                except BaseException as error:
                    if primary:primary.add_note('Owned image rebind cleanup: '+type(error).__name__)
                    else:raise
    return ImageRuntime
