"""Inert exact-image/asset adapter. No image identity is supplied by this file.

Actual image, canonical manifest, binary locations/hashes and Docker daemon must
come from the future reviewed admission/plan. Default product ENTRYPOINT is kept;
this adapter does not load diagnostic source, replace ACME, or compile modules.
"""
import json
import hashlib
import os
from pathlib import Path,PurePosixPath
import re
import subprocess
import time
from container_fixture import OwnedImage
from acme_runtime import regular,sha,ticks


class OwnedACMEImage(OwnedImage):
    def __init__(self, image, manifest, root, *, manifest_sha256, artifact_sha256,
                 assets, docker, docker_sha256, socket_path, docker_config, runtime_files=None):
        root=Path(root).resolve()
        regular(manifest)
        tool=Path(docker).lstat()
        import stat
        assert stat.S_ISREG(tool.st_mode)and tool.st_nlink==1 and tool.st_uid in (0,os.getuid())and not tool.st_mode&0o022
        assert re.fullmatch(r'sha256:[0-9a-f]{64}',image)
        assert sha(manifest)==manifest_sha256 and sha(docker)==docker_sha256
        assert Path(docker).is_absolute() and Path(socket_path).is_absolute()
        assert {'lego','acme-guard'}<=set(assets)
        assert set(assets)<=set(['LICENSE.lego','LICENSE.musl','acme-build.json','acme-bundle.json','acme-guard','acme-pins.json','lego','lego-sbom.json'])
        for value in assets.values():
            assert set(value)=={'path','sha256'}
            p=PurePosixPath(value['path'])
            assert p.is_absolute() and '..'not in p.parts and str(p)==value['path']
            assert re.fullmatch('[0-9a-f]{64}',value['sha256'])
            assert str(p).startswith(('/app/','/runtime/adhd/'))
        super().__init__(image,manifest,root)
        assert self.manifest['files']['hub.exs']==artifact_sha256
        self.assets=assets;self.docker_path=str(docker);self.docker_sha=docker_sha256
        self.expected_image=image;self.expected_manifest=manifest_sha256
        self.env={'PATH':'/usr/bin:/bin','HOME':str(root),'LC_ALL':'C',
                  'DOCKER_HOST':'unix://'+str(socket_path),'DOCKER_CONFIG':str(Path(docker_config).resolve())}
        self.assets_verified=False;self.runtime_rows=[]
        self.runtime_files=dict(runtime_files or {})
        assert all(PurePosixPath(p).is_absolute()and str(PurePosixPath(p))==p and p.startswith('/runtime/adhd/')and '..'not in PurePosixPath(p).parts and re.fullmatch('[0-9a-f]{64}',v)for p,v in self.runtime_files.items())
        self.expected_cmd=None;self.expected_network='host';self.last_exit_code=None

    def docker(self,*args,check=True):
        assert sha(self.docker_path)==self.docker_sha
        if args and args[0]=='run' and '--entrypoint'in args:
            args=(args[0],'--no-healthcheck',*args[1:])
        return subprocess.run([self.docker_path,*args],capture_output=True,check=check,timeout=30,env=self.env)

    def verify(self):
        super().verify()
        assert self.image_id==self.expected_image
        assert sha(self.manifest_path)==self.expected_manifest
        if not self.assets_verified:
            expected={('/app/'+name):digest for name,digest in self.manifest['files'].items() if name!='Dockerfile'}
            assert expected and len(expected)<=256
            for path in expected:
                p=PurePosixPath(path)
                assert '..'not in p.parts and str(p)==path
            raw=self.probe('sha256sum',*sorted(expected))
            assert len(raw)<=131072
            actual={}
            for line in raw.decode().splitlines():
                digest,path=line.split('  ',1)
                assert path not in actual
                actual[path]=digest
            assert actual==expected,'Complete runtime payload differs from canonical manifest'
            self.image_config=json.loads(self.docker('image','inspect',self.expected_image).stdout)[0]['Config']
            files={**self.runtime_files,**{v['path']:v['sha256']for v in self.assets.values()}}
            raw=self.probe('sha256sum',*sorted(files))
            self.check_hash_output(raw,files)
            self.assets_verified=True

    def argv(self,config_file):
        # Original security/resource/mounts/default ENTRYPOINT stay authoritative.
        result=super().argv(config_file)
        result[0]=self.docker_path
        result.remove('--rm')
        config_file=Path(config_file).absolute()
        assert config_file==config_file.resolve(strict=True)and config_file.is_relative_to(self.root)
        self.config_file=str(config_file)
        if self.expected_cmd is None:self.expected_cmd=[json.dumps(['serve',self.config_file])]
        assert len(self.expected_cmd)==1 and isinstance(self.expected_cmd[0],str)
        public=json.loads(self.expected_cmd[0])
        assert isinstance(public,list)and len(public)==2 and public[0]in ('serve','rebind-storage')
        if public[0]=='serve':assert public[1]==self.config_file
        self.public_command=public[0]
        # Retain normal product ENTRYPOINT; only the supported public command
        # supplies the actual absolute mounted configuration or offline request.
        return result+self.expected_cmd

    def checked_row(self):
        value=self.docker('inspect',self.name,check=False)
        if self.probe_absence(value,self.name):return None
        assert value.returncode==0,'Container inspection did not prove owned object or absence'
        rows=json.loads(value.stdout);assert len(rows)==1
        row=rows[0]
        assert row['Name']=='/'+self.name and row['Image']==self.expected_image
        assert re.fullmatch('[0-9a-f]{64}',row['Id'])
        if self.container_id is not None:assert row['Id']==self.container_id,'Owned name now refers to a different container'
        return row

    def observe(self):
        row=self.checked_row();assert row is not None and row['State']['Running']is True
        super().observe()
        assert row['Config']['Entrypoint']==self.image_config['Entrypoint']
        assert row['Config']['Cmd']==(self.expected_cmd if self.expected_cmd is not None else self.image_config['Cmd'])
        assert row['HostConfig']['PidMode']in ('','private')
        assert row['HostConfig']['NetworkMode']==self.expected_network
        assert row['HostConfig']['Privileged']is False and row['HostConfig']['ReadonlyRootfs']is True
        assert 'ALL'in row['HostConfig']['CapDrop']
        assert 'no-new-privileges'in row['HostConfig']['SecurityOpt']
        assert any(m['Type']=='bind'and m['Source']==str(self.root)and m['Destination']==str(self.root)for m in row['Mounts'])
        assert ('ADHD_CONFIG_FILE='+self.config_file) in row['Config']['Env']
        pid=row['State']['Pid'];start=ticks(pid)
        assert type(pid)is int and pid>0 and start is not None
        assert Path(os.readlink('/proc/'+str(pid)+'/exe')).name=='beam.smp','Inspected process is not actual BEAM VM'
        namespace=os.readlink('/proc/'+str(pid)+'/ns/pid')
        assert namespace!=os.readlink('/proc/self/ns/pid')
        if not self.runtime_rows or self.runtime_rows[-1]['container_id']!=row['Id']:
            self.runtime_rows.append({'container_id':row['Id'],'container_name':self.name,
              'host_vm_pid':pid,'host_vm_start_ticks':start,'pid_namespace':namespace,'image':row['Image'],
              'assets_sha256':{k:v['sha256']for k,v in self.assets.items()},
              'default_entrypoint':True,'default_command':False,'public_command':self.public_command,
              'command_sha256':hashlib.sha256(json.dumps(self.expected_cmd,separators=(',',':')).encode()).hexdigest(),'payload_verified':self.verified,'assets_verified':self.assets_verified})
            files={**self.runtime_files,**{v['path']:v['sha256']for v in self.assets.values()}}
            self.check_hash_output(self.docker('exec',row['Id'],'sha256sum',*sorted(files)).stdout,files)
            again=self.checked_row()
            assert again['Id']==row['Id']and again['State']['Pid']==pid and ticks(pid)==start
            self.runtime_rows[-1]['live_runtime_files_verified']=len(files)
        else:
            actual=self.runtime_rows[-1]
            assert (actual['host_vm_pid'],actual['host_vm_start_ticks'])==(pid,start)

    def absent(self):
        return self.checked_row()is None

    @staticmethod
    def check_hash_output(raw,expected):
        assert len(raw)<=131072
        observed={}
        for line in raw.decode().splitlines():
            digest,path=line.split('  ',1)
            assert path not in observed
            observed[path]=digest
        assert observed==expected,'Actual runtime/cache/client file hashes differ'

    def stop(self,hard=False):
        if self.name is None:return
        row=self.checked_row()
        identifier=row['Id']if row else self.container_id
        if row:
            self.container_id=row['Id']
            if row['State']['Running']:
                if hard:self.docker('kill','--signal','KILL',identifier)
                else:self.docker('stop','--time','8',identifier)
            row=self.checked_row();assert row is not None and row['State']['Running']is False
            self.last_exit_code=row['State']['ExitCode']
            assert self.checked_row()['Id']==identifier
            self.docker('rm',identifier)
        deadline=time.monotonic()+15
        while not self.absent():
            assert time.monotonic()<deadline,'Owned image absence deadline'
            time.sleep(.05)
        for item in self.runtime_rows:
            if item['container_id']==identifier:
                item['original_vm_identity_absent']=ticks(item['host_vm_pid'])!=item['host_vm_start_ticks']
                assert item['original_vm_identity_absent']
        self.events.append({'action':'observed-absent','container_id':identifier,'observed_absent':True,'exit_code':self.last_exit_code})
        self.name=self.container_id=None
