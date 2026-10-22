"""Exercise real lifecycle/rearm/argv with mocked Docker, never load observer."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from container_fixture import OwnedImage
from image_filesystem_fault import FilesystemFaultImage


def denied(call):
    try:call()
    except AssertionError:return
    raise AssertionError('Unsafe rearm accepted')


def main():
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.run',side_effect=AssertionError('No processes')):
        root=Path(directory);library=root/'synthetic.so';library.write_bytes(b'unexecutable synthetic fixture')
        obj=FilesystemFaultImage.__new__(FilesystemFaultImage);obj.source_name='project_recovery_fault.c';obj.root=root
        obj.image_id='sha256:'+'a'*64;obj.library=library;obj.library_sha256=hashlib.sha256(library.read_bytes()).hexdigest()
        obj.manifest={'files':{'hub.exs':'b'*64}};obj.manifest_bytes=json.dumps(obj.manifest).encode()
        obj.proof={'canonical_manifest_sha256':hashlib.sha256(obj.manifest_bytes).hexdigest(),'artifact_sha256':'b'*64}
        obj.environment={'ADHD_RECOVERY_FAULT_STAGE':'after-install-snapshot','ADHD_RECOVERY_FAULT_CONFIG':str(root/'hub.json'),
            'ADHD_RECOVERY_FAULT_ROOT':str(root),'ADHD_RECOVERY_FAULT_ARM':str(root/'armed'),'ADHD_RECOVERY_FAULT_SENTINEL':str(root/'sentinel')}
        obj.stage='after-install-snapshot';obj.custody=[];obj.rearm_history=[];obj.events=[];obj.armed=True;obj.cleanup_blocked=False;obj.probe_cleanup_blocked=False
        obj.name=obj.container_id=None;obj.last_exit_code=None;obj.observe=lambda:None
        state={};calls=[]
        def docker(*args,check=True):
            calls.append(args)
            if args[0]=='inspect':
                if not state['exists']:return SimpleNamespace(returncode=1,stdout=b'[]',stderr=('error: no such object: '+args[1]).encode())
                return SimpleNamespace(returncode=0,stdout=json.dumps([{'Id':'f'*64,'Image':obj.image_id,'State':{'Running':state['running'],'ExitCode':137}}]).encode(),stderr=b'')
            if args[0]=='kill':state['running']=False
            if args[0]=='rm':state['exists']=False
            return SimpleNamespace(returncode=0,stdout=b'137\n' if args[0]=='wait' else b'',stderr=b'')
        obj.docker=docker
        def owner():state.update(running=True,exists=True);obj.name='adhd-owned';obj.container_id='f'*64
        for _ in range(2):
            owner();obj.stop(hard=True);assert not obj.armed and obj.name is None and obj.last_exit_code==137
        obj.rearm_for_start();assert obj.armed and len(obj.rearm_history)==1 and not (root/'armed').exists()
        base=['docker','run','--rm','--name','adhd-owned','--read-only',obj.image_id]
        with patch.object(OwnedImage,'argv',return_value=base):
            third=obj.argv(root/'hub.json');assert 'LD_PRELOAD=/adhd-test/filesystem-observer.so' in third
            owner();obj.custody.append({'actualboundary':'witnessed'});obj.stop(hard=True)
            assert not obj.armed and obj.last_exit_code==137
            cold=obj.argv(root/'hub.json');assert not any('LD_PRELOAD=' in v for v in cold)
        denied(obj.rearm_for_start)
        for key,value in [('name','active'),('cleanup_blocked',True),('probe_cleanup_blocked',True),('last_exit_code',0)]:
            candidate=copy.copy(obj);candidate.custody=[];setattr(candidate,key,value);denied(candidate.rearm_for_start)
        candidate=copy.copy(obj);candidate.custody=[];(root/'armed').write_text('already armed');denied(candidate.rearm_for_start)
        assert sum(call[0]=='kill' for call in calls)==3 and sum(call[0]=='wait' for call in calls)==3
    print('PASS recovery rearm pure7: real mocked lifecycle2baselinehardkill137/wait/remove→guardedrearm→instrumentedthirdargv; witnessedboundaryhardkill→uninstrumentedcoldargv; active/unknowncleanup/not137/armedfile/priorboundary denied; actualprocess/observerload/provider starts0')


if __name__=='__main__':main()
