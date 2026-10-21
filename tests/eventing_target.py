"""Independent native/Docker target binding for Hub-based eventing fixtures."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from federation_acceptance import Hub


def add_target_arguments(parser):
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--command',help='JSON native executable argv before serve payload')
    target.add_argument('--image',help='Locally available immutable reviewed Docker image')
    parser.add_argument('--image-manifest',type=Path,help='Exact reviewed container context manifest.json')


class RuntimeTarget:
    def __init__(self,args):
        self.lifecycle=[];self.image=None;self.manifest=None;self.artifact=None
        if args.image:
            if not args.image_manifest:raise ValueError('--image requires --image-manifest')
            self.manifest=args.image_manifest.read_bytes();parsed=json.loads(self.manifest)
            self.artifact=parsed['files']['hub.exs']
            assert re.fullmatch(r'[0-9a-f]{64}',self.artifact),'Invalid reviewed artifact digest'
            self.image=json.loads(subprocess.check_output(['docker','image','inspect',args.image],text=True))[0]['Id']
            assert re.fullmatch(r'sha256:[0-9a-f]{64}',self.image),'Docker returned no immutable config identity'
            self.command=[]
        else:
            if args.image_manifest:raise ValueError('--image-manifest requires --image')
            self.command=json.loads(args.command)
            assert isinstance(self.command,list) and self.command and all(isinstance(v,str) for v in self.command)
            path=Path(self.command[-1])
            if path.is_file():self.artifact=hashlib.sha256(path.read_bytes()).hexdigest()

    def hub(self,root,identity,matcher):
        if not self.image:return Hub(self.command,root,identity,matcher)
        fixture=ImageHub(self.command,root,identity,matcher)
        fixture.image=self.image;fixture.target=self
        return fixture

    def report(self):
        if not self.image:return {'runtime':{'kind':'native'},**({'artifact_sha256':self.artifact} if self.artifact else {})}
        return {'runtime':{'kind':'docker','image_config_identity':self.image,
            'canonical_manifest_sha256':hashlib.sha256(self.manifest).hexdigest(),
            'artifact_sha256':self.artifact,'network_mode':'host',
            'container_lifecycle':self.lifecycle},'artifact_sha256':self.artifact}


class ImageHub(Hub):
    def start(self):
        super().start()
        if not self.image:return  # Explicit native legacy seed on this same backend.
        try:
            observed=json.loads(subprocess.check_output(['docker','inspect',self.container],text=True))[0]
            assert observed['Image']==self.target.image,'Container image identity changed'
            assert observed['HostConfig']['ReadonlyRootfs'] and observed['HostConfig']['NetworkMode']=='host'
            manifest=subprocess.check_output(['docker','exec',self.container,'cat','/app/manifest.json'])
            assert manifest==self.target.manifest,'Actual container manifest differs from reviewed context'
            artifact=subprocess.check_output(['docker','exec',self.container,'sha256sum','/app/hub.exs'],text=True).split()[0]
            assert artifact==self.target.artifact,'Actual container artifact differs from reviewed manifest'
            self.target.lifecycle.append({'action':'started','container_id':observed['Id'],
                'image_config_identity':observed['Image'],'artifact_sha256':artifact})
        except BaseException:
            self.stop(hard=True)
            raise

    def stop(self,hard=False):
        observed=None
        if self.image and self.container:
            result=subprocess.run(['docker','inspect',self.container],text=True,capture_output=True)
            if result.returncode==0:observed=json.loads(result.stdout)[0]['Id']
        super().stop(hard=hard)
        if observed:
            absent=subprocess.run(['docker','inspect',observed],capture_output=True).returncode!=0
            assert absent,'Owned fixture container still exists after stop/removal'
            self.target.lifecycle.append({'action':'hard-killed' if hard else 'stopped',
                'container_id':observed,'observed_absent':absent})
