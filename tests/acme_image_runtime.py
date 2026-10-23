"""Inert exact-image/asset adapter. No image identity is supplied by this file.

Actual image, canonical manifest, binary locations/hashes and Docker daemon must
come from the future reviewed admission/plan. Default product ENTRYPOINT is kept;
this adapter does not load diagnostic source, replace ACME, or compile modules.
"""
import json
import os
from pathlib import Path,PurePosixPath
import re
import subprocess
import time
from container_fixture import OwnedImage
from acme_runtime import regular,sha,ticks


class OwnedACMEImage(OwnedImage):
    def __init__(self, image, manifest, root, *, manifest_sha256, artifact_sha256,
                 assets, docker, docker_sha256, socket_path, docker_config):
        root=Path(root).resolve()
        regular(manifest);regular(docker)
        assert re.fullmatch(r'sha256:[0-9a-f]{64}',image)
        assert sha(manifest)==manifest_sha256 and sha(docker)==docker_sha256
        assert Path(docker).is_absolute() and Path(socket_path).is_absolute()
        assert set(assets)=={'lego','acme-guard'}
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
            for value in self.assets.values():
                raw=self.probe('sha256sum',value['path'])
                assert len(raw)<=8192
                assert raw.decode().strip()==value['sha256']+'  '+value['path'], 'Actual packaged client/guardian hash differs'
            self.assets_verified=True

    def argv(self,config_file):
        # Original security/resource/mounts/default ENTRYPOINT stay authoritative.
        result=super().argv(config_file)
        result[0]=self.docker_path
        self.config_file=str(config_file)
        return result

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
        assert row['Config']['Cmd']==self.image_config['Cmd']
        assert row['HostConfig']['PidMode']!='host'
        assert ('ADHD_CONFIG_FILE='+self.config_file) in row['Config']['Env']
        pid=row['State']['Pid'];start=ticks(pid)
        assert type(pid)is int and pid>0 and start is not None
        assert Path(os.readlink('/proc/'+str(pid)+'/exe')).name=='beam.smp','Inspected process is not actual BEAM VM'
        if not self.runtime_rows or self.runtime_rows[-1]['container_id']!=row['Id']:
            self.runtime_rows.append({'container_id':row['Id'],'container_name':self.name,
              'host_vm_pid':pid,'host_vm_start_ticks':start,'image':row['Image'],
              'assets_sha256':{k:v['sha256']for k,v in self.assets.items()},
              'default_entrypoint':True,'payload_verified':self.verified,'assets_verified':self.assets_verified})
        else:
            actual=self.runtime_rows[-1]
            assert (actual['host_vm_pid'],actual['host_vm_start_ticks'])==(pid,start)

    def absent(self):
        return self.checked_row()is None

    def stop(self,hard=False):
        if self.name is None:return
        row=self.checked_row()
        identifier=row['Id']if row else self.container_id
        if row:
            # Validate actual known ID/name/image BEFORE any mutation. Never
            # remove a foreign or replaced object merely because a name matches.
            self.container_id=row['Id']
            if hard:self.docker('kill','--signal','KILL',identifier)
            else:self.docker('stop','--time','8',identifier)
        deadline=time.monotonic()+15
        while not self.absent():
            assert time.monotonic()<deadline,'Owned image absence deadline'
            time.sleep(.05)
        for item in self.runtime_rows:
            if item['container_id']==identifier:
                item['original_vm_identity_absent']=ticks(item['host_vm_pid'])!=item['host_vm_start_ticks']
                assert item['original_vm_identity_absent']
        self.events.append({'action':'observed-absent','container_id':identifier,'observed_absent':True})
        self.name=self.container_id=None
