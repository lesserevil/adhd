"""Image-only compiled-boot observer around unchanged recovery scenarios.

The watcher body is copied verbatim from the original source observer. Native
invocations never import this adapter. No application source is rewritten.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time

from image_ui_runtime import Custody as BaseCustody, proc
from controlled_image_runtime import authoritative_absence


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiled_observer(original):
    """Use the exact existing watcher, then the real guarded cache entrypoint."""
    prefix, body=original.split('defmodule RecoveryLiveLoss do\n',1)
    watcher, tail=body.split('\n["serve", config] = ADHD.JSON.decode!(payload)\n',1)
    assert prefix.count('Code.compile_string(prefix, artifact)')==1
    assert tail=='spawn(fn -> RecoveryLiveLoss.watch(config) end)\nCode.eval_string("unless Code.ensure_loaded?(ADHD.CLI) do" <> entry, [], file: artifact)\n'
    return ('# Test-only compiled boot; unchanged actual Store-loss watcher.\n'
        '[artifact, payload] = System.argv()\n'
        '["serve", config] = JSON.decode!(payload)\n'
        'defmodule RecoveryLiveLoss do\n'+watcher+'\n'
        'spawn(fn -> RecoveryLiveLoss.watch(config) end)\n'
        'System.argv([artifact, payload])\n'
        'Code.eval_file("/runtime/adhd/boot.exs")\n')


class Custody(BaseCustody):
    def observe_compiled_cache(self,identifier,row):
        value=self.plan['compiled_cache']['manifest']
        actual=self.docker('exec',identifier,'cat','/runtime/adhd/manifest.json').stdout
        assert hashlib.sha256(actual).hexdigest()==self.plan['compiled_cache']['manifest_sha256']
        assert json.loads(actual)==value
        files={'/runtime/adhd/boot.exs':value['boot_sha256'],'/runtime/adhd/build.exs':value['build_sha256'],
            '/runtime/adhd/inputs.json':value['inputs_sha256'],
            **{'/runtime/adhd/ebin/'+k:v for k,v in value['beams'].items()},
            **{('/proc/1/exe' if k=='/proc/self/exe' else k):v for k,v in value['toolchain']['anchors'].items()}}
        actual=self.docker('exec',identifier,'sha256sum',*files).stdout.decode().splitlines()
        assert {line.split(None,1)[1].strip():line.split(None,1)[0] for line in actual}==files
        assert row['Config']['Entrypoint']==['elixir']
        from recovery_image_runtime import OBSERVER, ARTIFACT
        assert row['Config']['Cmd'][:2]==[OBSERVER,ARTIFACT]
        again=json.loads(self.docker('inspect',identifier).stdout)[0]
        assert again['Id']==identifier and again['State']['Pid']==row['State']['Pid'] and again['State']['Running']
        return {'manifest_sha256':self.plan['compiled_cache']['manifest_sha256'],'modules':59,
            'cache_and_toolchain_files_verified':len(files),'same_actual_VM':True,
            'entrypoint':row['Config']['Entrypoint'],'execution':'instrumented real compiled boot, not default OCI entrypoint',
            'compiled_observer_sha256':sha(self.work/'compiled-observer.exs')}

    def install(self):
        from container_fixture import OwnedImage
        import recovery_image_runtime as recovery
        from http.server import ThreadingHTTPServer
        custody=self;original_image=recovery.ObserverImage;popen=subprocess.Popen
        server_init=ThreadingHTTPServer.__init__
        def server_construct(obj,address,handler,*args,**kwargs):
            server_init(obj,address,handler,*args,**kwargs)
            source=Path(inspect.getsourcefile(handler)).absolute()
            assert source.is_relative_to(Path(custody.plan['frozen'])/'tests')
            assert sha(source)==custody.plan['frozen_inputs'][str(source.relative_to(Path(custody.plan['frozen'])))]
            custody.servers.append((obj,str(source)))
        ThreadingHTTPServer.__init__=server_construct

        class CompiledImage(original_image):
            def __init__(obj,image,manifest,root,observer):
                assert sha(observer)==custody.plan['native_observer_sha256']
                original_image.__init__(obj,image,manifest,root,custody.work/'compiled-observer.exs')
                obj.probe_lifecycle=obj.probe_events
                custody.images.append(obj)
            def argv(obj,config_file):
                obj.config_file=Path(config_file)
                custody.audit_models(json.loads(obj.config_file.read_text()))
                return super().argv(config_file)
            def docker(obj,*args,check=True):
                return subprocess.run([custody.plan['docker']['path'],*args],capture_output=True,check=check,timeout=30)
            probe=OwnedImage.probe
            def absent(obj):
                keys=list(dict.fromkeys(v for v in (obj.container_id,obj.name) if v))
                return all(authoritative_absence(obj.docker('inspect',key,check=False),key) for key in keys)
            def stop(obj,hard=False):
                if obj.name is None:return
                name,identifier=obj.name,obj.container_id
                inspection=obj.docker('inspect',identifier or name,check=False)
                if authoritative_absence(inspection,identifier or name):
                    assert obj.absent();obj.events.append({'action':'observed-exited','container_id':identifier,'observed_absent':True})
                    obj.name=obj.container_id=None
                    assert not hard,'Hard-stop requires a running owned VM'
                    return
                assert inspection.returncode==0
                rows=json.loads(inspection.stdout);assert len(rows)==1;row=rows[0]
                assert row['Image']==obj.image_id and row['Name']=='/'+name
                assert identifier is None or row['Id']==identifier
                assert any(m['Type']=='bind' and m['Source']==str(obj.root) and m['Destination']==str(obj.root) for m in row['Mounts'])
                identifier=row['Id'];obj.container_id=identifier
                for launch in custody.launches:
                    if launch['name']==name:launch['container_id']=identifier
                custody.progress()
                primary=None
                try:
                    if hard:
                        assert row['State']['Running'];obj.docker('kill','--signal','KILL',identifier)
                    elif row['State']['Running']:obj.docker('stop','--timeout','8',identifier)
                    else:obj.docker('rm','--force',identifier)
                except BaseException as error:
                    primary=error;obj.docker('rm','--force',identifier,check=False)
                deadline=time.monotonic()+15
                while not obj.absent():
                    assert time.monotonic()<deadline,'Owned observer VM absence unproven'
                    time.sleep(.05)
                obj.events.append({'action':'hard-killed' if hard else 'stopped','container_id':identifier,'observed_absent':True})
                obj.name=obj.container_id=None
                if primary:raise primary
        recovery.ObserverImage=CompiledImage

        def observed_popen(argv,*args,**kwargs):
            launch=None
            if isinstance(argv,(list,tuple)) and len(argv)>1 and Path(argv[0]).name=='docker' and argv[1]=='run':
                assert '--name' in argv and custody.image in argv and not any(v=='--pid' or v.startswith('--pid=') for v in argv)
                name=argv[argv.index('--name')+1]
                assert re.fullmatch('adhd-(multi-accept|accept-probe)-[a-f0-9]{16}',name)
                launch={'name':name,'kind':'probe' if 'accept-probe-' in name else 'app','image_config_identity':custody.image}
                if launch['kind']=='app':
                    mounts=[argv[i+1] for i,v in enumerate(argv) if v=='--mount']
                    source=next(m for m in mounts if 'dst=/adhd-test/recovery-observer.exs' not in m)
                    fields=dict(part.split('=',1) for part in source.split(','))
                    assert fields['type']=='bind' and fields['src']==fields['dst']
                    launch['private_root']=fields['src']
                custody.launches.append(launch);custody.progress()
            if isinstance(argv,(list,tuple)) and argv and argv[0]=='docker':argv=[custody.plan['docker']['path'],*argv[1:]]
            child=popen(argv,*args,**kwargs);identity=proc(child.pid);custody.clients.append((child,identity))
            if launch:launch.update(client_pid=child.pid,client_identity=identity)
            custody.progress();return child
        subprocess.Popen=observed_popen
        start=recovery.RecoveryImageRuntime.start;hard=recovery.RecoveryImageRuntime.hard_stop
        async def observed_start(obj,*args,**kwargs):
            result=await start(obj,*args,**kwargs);custody.observe_vm(obj.image_runtime,'after-original-ready');return result
        def observed_hard(obj,*args,**kwargs):
            custody.observe_vm(obj.image_runtime,'before-original-hard-stop');return hard(obj,*args,**kwargs)
        recovery.RecoveryImageRuntime.start=observed_start;recovery.RecoveryImageRuntime.hard_stop=observed_hard


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--job',required=True);parser.add_argument('--reviewed-plan-sha256',required=True);args=parser.parse_args()
    assert sha(args.plan)==args.reviewed_plan_sha256;plan=json.loads(args.plan.read_text());work=args.plan.parent
    assert sha(__file__)==plan['frozen_inputs']['tests/recovery_compiled_callbacks.py']
    assert json.loads((work/'started.json').read_text())['plan_sha256']==args.reviewed_plan_sha256
    job=next(v for v in plan['jobs'] if v['name']==args.job);custody=Custody(plan,job,work);error=cleanup=None;absence=[]
    try:
        custody.install();sys.argv=job['test_argv'];runpy.run_path(sys.argv[0],run_name='__main__')
    except BaseException as caught:error=caught
    finally:
        try:absence=custody.finish()
        except BaseException as caught:cleanup=caught
        Path(job['custody_report']).write_text(json.dumps({'passed':error is None and cleanup is None,
            'original_exception':type(error).__name__ if error else None,'cleanup_exception':type(cleanup).__name__ if cleanup else None,
            'actual_vm_observations':custody.vm,'independent_absence':absence,'cleanup_error_types':custody.errors,
            'scope':'Actual compiled boot with unchanged test watcher; original callback scenarios and limits; no external provider'},indent=2)+'\n')
    if error:raise error
    if cleanup:raise cleanup


if __name__=='__main__':main()
