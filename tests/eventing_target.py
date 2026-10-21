"""Independent native/Docker target binding for Hub-based eventing fixtures."""
import hashlib
import json
import os
import time
from uuid import uuid4
from pathlib import Path
import re
import subprocess

from federation_acceptance import Hub, request


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
        if not self.image:return super().start()
        path=self.root/'config.json';path.write_text(json.dumps(self.config));path.chmod(0o600)
        self.handles=[(self.root/name).open('ab') for name in ('stdout','stderr')]
        self.container='adhd-eventing-image-'+uuid4().hex[:12]
        # Deliberately no --rm: exit status is witnessed before explicit removal.
        command=['docker','run','--name',self.container,'--network','host',
            '--user',f'{os.getuid()}:{os.getgid()}','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--pids-limit','128','--memory','512m','--cpus','2',
            '--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--mount',f'type=bind,src={self.root},dst={self.root}',
            '--env',f'ADHD_CONFIG_FILE={path}',self.image,json.dumps(['serve',str(path)])]
        self.process=subprocess.Popen(command,stdout=self.handles[0],stderr=self.handles[1],start_new_session=True)
        try:
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if self.process.poll() is not None:raise AssertionError('Image hub exited during startup')
                try:
                    if request(self.base,'/health')[0]==200:break
                except (OSError,TimeoutError):pass
                time.sleep(.1)
            else:raise AssertionError('Image hub readiness timeout')
            observed=self.inspect(self.container)
            assert observed and observed['Image']==self.target.image,'Container image identity changed'
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

    @staticmethod
    def inspect(identity):
        result=subprocess.run(['docker','inspect',identity],text=True,capture_output=True)
        if result.returncode==0:
            rows=json.loads(result.stdout);assert len(rows)==1;return rows[0]
        assert result.returncode==1 and result.stdout.strip()=='[]' and 'no such object' in result.stderr.lower(), \
            'Docker inspection failed without proving absence: '+result.stderr
        return None

    def stop(self,hard=False):
        if not self.image:return super().stop(hard=hard)
        if not self.container:return
        observed=self.inspect(self.container)
        assert observed is not None,'Owned tracked container vanished before exit could be witnessed'
        identity=observed['Id'];running=observed['State']['Running']
        if not running and observed['State']['Status']=='created':
            subprocess.run(['docker','rm',identity],text=True,capture_output=True,check=True,timeout=30)
            assert self.inspect(identity) is None
            self.finish_client()
            self.target.lifecycle.append({'action':'startup-not-started','container_id':identity,
                'wait_observed':False,'observed_absent':True})
            return
        action='already-exited'
        if running:
            command=['docker','kill','--signal','KILL',identity] if hard else ['docker','stop','--time','10',identity]
            result=subprocess.run(command,text=True,capture_output=True,check=True,timeout=30)
            assert result.stdout.strip()==identity,'Docker did not confirm requested signal target'
            action='hard-killed' if hard else 'stopped'
        result=subprocess.run(['docker','wait',identity],text=True,capture_output=True,check=True,timeout=30)
        exit_code=int(result.stdout.strip());state=self.inspect(identity)
        assert state and not state['State']['Running'] and state['State']['ExitCode']==exit_code
        assert state['State']['FinishedAt'] and not state['State']['FinishedAt'].startswith('0001-')
        if running and hard:assert exit_code==137,'Requested KILL did not produce observed exit137'
        subprocess.run(['docker','rm',identity],text=True,capture_output=True,check=True,timeout=30)
        assert self.inspect(identity) is None,'Owned container still exists after successful removal'
        self.finish_client()
        self.target.lifecycle.append({'action':action,'container_id':identity,'exit_code':exit_code,
            'wait_observed':True,'observed_absent':True})

    def finish_client(self):
        if self.process:
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=5)
        for handle in self.handles:handle.close()
        self.handles=[];self.container=None
