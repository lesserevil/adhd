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
        self.target.verify()
        name='adhd-fs-codec-'+uuid4().hex[:16]
        command=['docker','run','--rm','--name',name,'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--user',f'{os.getuid()}:{os.getgid()}',
            '--memory','256m','--cpus','1','--pids-limit','64',
            '--mount',f'type=bind,src={self.root},dst={self.root}',
            '--entrypoint','elixir',self.target.image_id,'-e',source,str(Path(path))]
        result=None
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            return result
        finally:
            self.target.docker('rm','--force',name,check=False)
            absent=self.target.docker('inspect',name,check=False)
            assert absent.returncode!=0 and b'no such' in absent.stderr.lower()
            self.offline_helpers.append({'kind':'offline-codec-only','image_config_identity':self.target.image_id,
                'network':'none','source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'exit_code':result.returncode if result else None,'observed_absent':True})
