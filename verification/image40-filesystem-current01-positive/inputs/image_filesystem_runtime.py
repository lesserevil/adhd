"""Foundation Runtime adapter for retained exact-image filesystem fault tests."""
import hashlib
import os
from uuid import uuid4
from pathlib import Path
import subprocess

from foundation_acceptance import Runtime
from image_filesystem_fault import RetainedImage, fault_image


class FilesystemRuntime(Runtime):
    def __init__(self,root,args,source=None,environment=None,mount_root=None):
        # Keep Runtime's complete readiness/public Admin admission behavior.
        # Its image branch is bypassed solely so this adapter owns Docker custody.
        super().__init__(root,[])
        self.offline_helpers=[]
        self.offline_helper_name=None
        self.target=(fault_image(args,mount_root or root,source,environment) if source else
                     RetainedImage(args.image,args.image_manifest,mount_root or root))

    def start(self):
        self.command=self.target.argv(self.file)
        super().start()
        self.target.observe()

    def stop(self,hard=False):
        try:
            self.target.stop(hard=hard)
            if self.process:self.process.wait(timeout=15)
        finally:
            # The target helper kills/waits/removes the actual container first;
            # this remaining process is only the owned Docker client.
            super().stop(hard=hard)

    def offline_elixir(self,source,path):
        """Bounded codec/DETS inspection under the same immutable image runtime."""
        assert self.target.name is None, 'Offline helper must not race a writer'
        assert not getattr(self.target,'cleanup_blocked',False), 'Prior owned cleanup remains unconfirmed'
        assert getattr(self,'offline_helper_name',None) is None, 'Offline helper already active'
        self.target.verify()
        name='adhd-fs-codec-'+uuid4().hex[:16]
        command=['docker','run','--rm','--name',name,'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--user',f'{os.getuid()}:{os.getgid()}',
            '--memory','256m','--cpus','1','--pids-limit','64',
            '--mount',f'type=bind,src={self.root},dst={self.root}',
            '--entrypoint','elixir',self.target.image_id,'-e',source,str(Path(path))]
        result=None;primary_error=None;cleanup_errors=[];absent=False
        self.offline_helper_name=name
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=60,check=True)
            return result
        except BaseException as error:
            primary_error=error
            raise
        finally:
            # Both cleanup actions are independent, so a daemon error from rm
            # never suppresses the subsequent attempt to establish actual absence.
            try:
                removed=self.target.docker('rm','--force',name,check=False)
                if removed.returncode and not self.target.authoritative_absence(removed,name):
                    raise subprocess.CalledProcessError(removed.returncode,['docker','rm','--force',name],
                        output=removed.stdout,stderr=removed.stderr)
            except BaseException as error:cleanup_errors.append(error)
            try:
                inspected=self.target.docker('inspect',name,check=False)
                absent=self.target.authoritative_absence(inspected,name)
                assert absent, 'Offline codec helper absence remains unconfirmed'
            except BaseException as error:cleanup_errors.append(error)
            self.offline_helper_name=None
            self.target.cleanup_blocked=not absent
            self.offline_helpers.append({'kind':'offline-codec-only','owned_name':name,
                'image_config_identity':self.target.image_id,'network':'none',
                'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'exit_code':result.returncode if result else getattr(primary_error,'returncode',None),
                'codec_failure_type':type(primary_error).__name__ if primary_error else None,
                'cleanup_failure_types':[type(error).__name__ for error in cleanup_errors],
                'observed_absent':absent})
            if cleanup_errors:
                if primary_error is not None:
                    primary_error.add_note('Offline helper cleanup failures: '+','.join(type(error).__name__ for error in cleanup_errors))
                else:raise cleanup_errors[0]
