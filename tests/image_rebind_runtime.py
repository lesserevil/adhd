"""Inert exact-image adapter for public offline rebind and its actual VM faults.

Constructors only read reviewed inputs. Runtime/probes occur solely on explicit
start/run. No generated application source or product metadata is rewritten.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from image_filesystem_fault import FilesystemFaultImage, RetainedImage, sha, validate_observer


class RebindFaultImage(FilesystemFaultImage):
    def __init__(self,args,root,environment,command):
        assert command[0]=='rebind-storage' and isinstance(command[1],dict)
        self.public_command=copy.deepcopy(command)
        super().__init__(args.image,args.image_manifest,root,'rebind_fault.c',args.image_fault_library,args.image_fault_proof,environment)

    def expected_public_command(self):return self.public_command


def command_config(command,root):
    assert isinstance(command,list) and len(command)==2
    if command[0]=='serve':path=Path(command[1])
    else:
        assert command[0]=='rebind-storage'
        # Invalid request vectors still exercise the public CLI. They have no
        # config location; this owned placeholder is only the launch env value.
        request=command[1]
        path=Path(request['config_file']) if isinstance(request,dict) and isinstance(request.get('config_file'),str) else root/'invalid-request-config.json'
    assert path.is_absolute() and path.is_relative_to(root) and '..' not in path.parts
    return path


def rebind_argv(base,serialized,offline):
    assert base[:2]==['docker','run'] and '--rm' not in base
    assert base[base.index('--network')+1]=='host'
    result=list(base)
    if offline:result[result.index('--network')+1]='none'
    return result+[serialized]


class ImageRebindRuntime:
    def __init__(self,args,root):
        assert args.image and args.image_manifest and args.artifact
        self.args=args;self.root=Path(root).absolute()
        assert self.root.resolve(strict=True)==self.root
        self.manifest=json.loads(Path(args.image_manifest).read_text())
        assert sha(args.artifact)==self.manifest['files']['hub.exs']
        if getattr(args,'image_fault_library',None) or getattr(args,'image_fault_proof',None):
            assert args.image_fault_library and args.image_fault_proof
            _,proof=validate_observer(args.image,args.image_fault_library,args.image_fault_proof,'rebind_fault.c')
            assert proof['canonical_manifest_sha256']==sha(args.image_manifest) and proof['artifact_sha256']==self.manifest['files']['hub.exs']
        self.sessions=[];self.active=None;self.cleanup_blocked=False

    def start(self,command,*,stdout,stderr,deadline,environment=None):
        assert self.active is None and not self.cleanup_blocked
        config=command_config(command,self.root);serialized=json.dumps(command)
        target=(RebindFaultImage(self.args,self.root,environment,command) if environment else
            RetainedImage(self.args.image,self.args.image_manifest,self.root))
        process=None
        session={'target':target,'process':None,'command_kind':command[0],'serialized':serialized,'offline':command[0]!='serve','custody':None}
        self.active=session;self.sessions.append(session)
        try:
            argv=rebind_argv(target.argv(config),serialized,command[0]!='serve')
            process=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            session['process']=process;process._adhd_image_rebind=(self,session)
            self.observe_vm(session,deadline)
            return process
        except BaseException as error:
            try:self.stop_session(session,hard=session['custody'] is not None)
            except BaseException as cleanup:error.add_note('Owned image CLI cleanup failure: '+type(cleanup).__name__)
            raise

    def observe_vm(self,session,deadline):
        target=session['target'];process=session['process']
        while time.monotonic()<deadline:
            assert process.poll() is None,'Image CLI exited before actual VM custody'
            result=target.docker('inspect',target.name,check=False)
            if result.returncode:
                # Only an authoritative not-yet-created object is a readiness
                # observation. Daemon failures never become successful absence.
                assert target.authoritative_absence(result,target.name)
                time.sleep(.02);continue
            row=json.loads(result.stdout)[0]
            assert row['Image']==target.image_id and row['Name']=='/'+target.name
            if not row['State']['Running']:raise AssertionError('CLI ended before VM observation')
            pid=row['State']['Pid']
            if not pid:time.sleep(.02);continue
            assert row['Config']['User']==f'{os.getuid()}:{os.getgid()}'
            assert row['HostConfig']['PidMode'] in ('','private') and not row['HostConfig']['Privileged']
            assert row['HostConfig']['NetworkMode']==('none' if session['offline'] else 'host')
            try:
                executable=Path(os.readlink('/proc/'+str(pid)+'/exe'))
                cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes()
                namespace=os.readlink('/proc/'+str(pid)+'/ns/pid')
                start_time=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
            except FileNotFoundError:time.sleep(.02);continue
            if executable.name not in ('beam.smp','beam'):time.sleep(.02);continue
            assert b'/app/hub.exs' in cmdline.split(b'\0') and session['serialized'].encode() in cmdline.split(b'\0')
            assert namespace!=os.readlink('/proc/self/ns/pid')
            target.observe()
            again=json.loads(target.docker('inspect',target.name).stdout)[0]
            assert again['Id']==row['Id'] and again['State']['Pid']==pid and again['Image']==row['Image']
            assert Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]==start_time
            assert os.readlink('/proc/'+str(pid)+'/exe')==str(executable)
            assert os.readlink('/proc/'+str(pid)+'/ns/pid')==namespace
            assert Path('/proc/'+str(pid)+'/cmdline').read_bytes()==cmdline
            session['custody']={'container_id':row['Id'],'image_config_identity':row['Image'],'host_vm_pid':pid,
                'namespace_pid':1,'executable_basename':executable.name,'pid_namespace':namespace,
                'vm_cmdline_sha256':hashlib.sha256(cmdline).hexdigest(),'network_mode':row['HostConfig']['NetworkMode'],
                'vm_start_time_ticks':start_time,
                'user':row['Config']['User'],'command_kind':session['command_kind']}
            return
        raise AssertionError('Actual image CLI VM custody deadline exceeded')

    def stop_session(self,session,hard=False):
        target=session['target'];process=session['process'];errors=[]
        try:target.stop(hard=hard)
        except BaseException as error:errors.append(error)
        if process:
            try:process.wait(timeout=15)
            except BaseException as error:errors.append(error)
        session['closed']=not getattr(target,'cleanup_blocked',False) and target.name is None
        self.cleanup_blocked=not session['closed']
        self.active=None
        if errors:raise errors[0]

    def run(self,command,timeout=150):
        deadline=time.monotonic()+timeout;session=None;primary=None
        try:
            process=self.start(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,deadline=deadline)
            session=self.active
            stdout,stderr=process.communicate(timeout=max(.001,deadline-time.monotonic()))
            session['client_exit_code']=process.returncode
            return subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
        except BaseException as error:primary=error;raise
        finally:
            if session:
                try:
                    self.stop_session(session,hard=primary is not None)
                    if primary is None:assert session['target'].last_exit_code==session['client_exit_code']
                except BaseException as cleanup:
                    if primary is not None:primary.add_note('Owned image CLI cleanup failure: '+type(cleanup).__name__)
                    else:raise

    def evidence(self):
        return {'image_config_identity':self.args.image,'artifact_sha256':self.manifest['files']['hub.exs'],
            'canonical_manifest_sha256':sha(self.args.image_manifest),'runtime_helper_sha256':sha(__file__),
            'cleanup_blocked':self.cleanup_blocked,'sessions':[{'command_kind':s['command_kind'],'actual_vm_custody':s['custody'],
                'client_exit_code':s.get('client_exit_code'),'closed':s.get('closed',False),'runtime':s['target'].identity()} for s in self.sessions]}


def stop_image_process(process,hard=False):
    owner,session=process._adhd_image_rebind
    owner.stop_session(session,hard=hard)


def stop_image_boundary(process,witness):
    owner,session=process._adhd_image_rebind;target=session['target']
    assert isinstance(target,RebindFaultImage) and witness['directory_fsync_result']==0
    target.stop_at_observed_boundary(witness)
    owner.stop_session(session,hard=True)
    assert process.returncode==137 and target.last_exit_code==137
