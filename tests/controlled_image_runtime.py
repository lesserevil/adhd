#!/usr/bin/env python3
"""Custody-only child adapter for unchanged controlled regression entrypoints.

Selection isolation: native BEAM uses the scoped port18770 connect fence. Docker
uses the existing host-network runner: exact active typed-loopback URL selection
and no redirects are checked, but this is NOT a Docker network firewall proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def regular(path):
    info=Path(path).lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1,path
    return info

def audit_models(value,allowed,path=()):
    """Audit every root/project override URL, including disabled overrides."""
    found=[]
    if isinstance(value,dict):
        scope=any(x in ('matcher','models','model','history','retrieval','archive','settings') for x in path)
        for key,item in value.items():
            if isinstance(item,str) and (key=='url' and (scope or 'model' in value) or key in ('endpoint','base_url','model_url')):
                parsed=urlsplit(item)
                assert parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port!=18770
                assert not parsed.username and not parsed.password and not parsed.fragment and not parsed.query
                assert item in allowed,('Unregistered controlled endpoint',path+(key,))
                found.append({'path':list(path+(key,)),'url':item})
            found+=audit_models(item,allowed,path+(key,))
    elif isinstance(value,list):
        for index,item in enumerate(value):found+=audit_models(item,allowed,path+(str(index),))
    return found


def proc_identity(pid):
    try:
        text=Path(f'/proc/{pid}/stat').read_text()
        return text[text.rfind(')')+2:].split()[19]
    except FileNotFoundError:return None


def native_vm(process,fence):
    pending=[process.pid];seen=set();rows=[]
    while pending:
        pid=pending.pop()
        if pid in seen:continue
        seen.add(pid)
        try:
            pending += [int(v) for v in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
            exe=os.readlink(f'/proc/{pid}/exe')
            if Path(exe).name=='beam.smp':
                maps=Path(f'/proc/{pid}/maps').read_text()
                assert str(fence) in maps,'Native BEAM does not map the scoped provider fence'
                rows.append({'pid':pid,'starttime':proc_identity(pid),'executable_sha256':sha(exe),
                             'fence_mapped':True,'maps_sha256':hashlib.sha256(maps.encode()).hexdigest()})
        except FileNotFoundError:continue
    assert rows,'Actual native BEAM process not observed'
    return rows


class Custody:
    def __init__(self,plan,job,report):
        self.plan=plan;self.job=job;self.report=report
        self.allowed={};self.fixture_objects={};self.events=[];self.errors=[];self.instances=[];self.busy=set();self.stopping=set()
        self.launches=[];self.ledger=Path(job['launch_ledger'])
        self.image=plan['image_config_identity'];self.manifest_bytes=Path(plan['manifest']).read_bytes()
        self.manifest=json.loads(self.manifest_bytes);self.fence=Path(plan['fence_library'])
    def docker(self,*args,check=True):
        return subprocess.run(['docker',*args],capture_output=True,check=check,timeout=30)
    def absent(self,name):
        result=self.docker('inspect',name,check=False)
        if result.returncode==0:return False
        assert b'no such' in result.stderr.lower(),'Docker absence not proven'
        return True
    def fixture(self,cls):
        original=cls.__init__;custody=self
        def init(obj,*args,**kwargs):
            original(obj,*args,**kwargs)
            url=obj.url;parsed=urlsplit(url)
            assert parsed.hostname=='127.0.0.1' and parsed.port==obj.server.server_port and parsed.port!=18770
            assert obj.server.server_address[0]=='127.0.0.1'
            handler=obj.server.RequestHandlerClass;send=handler.send_response
            def checked_send(request,code,*a,**kw):
                assert not 300<=code<400,'Controlled endpoint must never redirect'
                return send(request,code,*a,**kw)
            handler.send_response=checked_send
            custody.fixture_objects[url]=obj
            custody.allowed[url]={'class':cls.__module__+'.'+cls.__name__,'helper_sha256':sha(sys.modules[cls.__module__].__file__)}
        cls.__init__=init
    def config_path(self,obj):return Path(obj.file if hasattr(obj,'file') else obj.config_file)
    def is_image(self,obj):
        import container_acceptance
        return bool(getattr(obj,'image',None)) or isinstance(obj,container_acceptance.ContainerHub)
    def name(self,obj):return getattr(obj,'container',None) or getattr(obj,'name',None)
    def inspect_image(self,obj,event):
        name=self.name(obj);assert name,'Unsupported image branch without owned name'
        row=json.loads(self.docker('inspect',name).stdout)[0]
        assert row['Image']==self.image and row['State']['Running'] is True
        assert row['HostConfig']['PidMode']!='host' and row['HostConfig']['NetworkMode']=='host'
        assert row['HostConfig']['ReadonlyRootfs'] is True
        event.update(container_name=name,container_id=row['Id'],host_vm_pid=row['State']['Pid'])
        manifest=self.docker('exec',name,'cat','/app/manifest.json').stdout
        assert manifest==self.manifest_bytes,'Actual running payload manifest differs'
        files=self.manifest['files'];paths=['/app/'+key for key in files]
        assert all('..' not in Path(key).parts and not Path(key).is_absolute() for key in files)
        actual=self.docker('exec',name,'sha256sum',*paths).stdout.decode().splitlines()
        expected={('/app/'+key):digest for key,digest in files.items()}
        parsed={line.split(None,1)[1].strip():line.split(None,1)[0] for line in actual}
        assert parsed==expected,'Actual running full app payload differs'
        executable=self.docker('exec',name,'readlink','/proc/1/exe').stdout.decode().strip()
        status=self.docker('exec',name,'cat','/proc/1/status').stdout
        cmdline=self.docker('exec',name,'cat','/proc/1/cmdline').stdout
        assert Path(executable).name=='beam.smp' and b'Pid:\t1\n' in status and b'beam' in cmdline
        again=json.loads(self.docker('inspect',name).stdout)[0]
        assert again['Id']==row['Id'] and again['State']['Pid']==row['State']['Pid'] and again['State']['Running']
        event.update(namespace_vm_pid=1,pid_namespace_mode=row['HostConfig']['PidMode'],
            proc1_status_sha256=hashlib.sha256(status).hexdigest(),proc1_cmdline_sha256=hashlib.sha256(cmdline).hexdigest(),
            full_payload_files_verified=len(files),actual_payload_sha256=hashlib.sha256(json.dumps(parsed,sort_keys=True).encode()).hexdigest())
    def start(self,original,obj,*args,**kwargs):
        if id(obj) in self.busy:return original(obj,*args,**kwargs)
        self.busy.add(id(obj));self.instances.append(obj)
        event={'action':'start','kind':'docker' if self.is_image(obj) else 'native-producer',
               'root':str(obj.root),'config_sha256':None,'completed':False}
        self.events.append(event)
        try:
            config=self.config_path(obj);regular(config)
            assert config.resolve().is_relative_to(Path(self.plan['runtime_cwd']))
            raw=config.read_bytes();event['config_sha256']=hashlib.sha256(raw).hexdigest()
            active={url for url,fixture in self.fixture_objects.items() if fixture.thread.is_alive() and fixture.server.fileno()>=0}
            event['selected_models']=audit_models(json.loads(raw),active)
            assert event['selected_models'],'Unsupported fixture: no controlled model endpoint found'
            result=original(obj,*args,**kwargs)
            if self.is_image(obj):self.inspect_image(obj,event)
            else:
                event['producer_sha256']=sha(obj.command[-1])
                assert event['producer_sha256'] in self.plan['native_artifact_sha256']
                event['native_vms']=native_vm(obj.process,self.fence)
            event['completed']=True;obj._controlled_custody_event=event
            return result
        except BaseException as error:
            event['failure_type']=type(error).__name__
            try:self.cleanup_one(obj)
            except BaseException as cleanup:self.errors.append(type(cleanup).__name__)
            raise
        finally:self.busy.remove(id(obj))
    def cleanup_one(self,obj):
        name=self.name(obj) if self.is_image(obj) else None
        if name:
            row=self.docker('inspect',name,check=False)
            if row.returncode==0:
                actual=json.loads(row.stdout)[0]
                assert actual['Image']==self.image,'Refuse cleanup of foreign container'
                self.docker('rm','--force',name)
            assert self.absent(name)
        process=getattr(obj,'process',None)
        if process and process.poll() is None:
            import signal
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        for log in getattr(obj,'logs',[]):
            if not log.closed:log.close()
    def stop(self,original,obj,*args,**kwargs):
        if id(obj) in self.stopping:return original(obj,*args,**kwargs)
        self.stopping.add(id(obj));event=getattr(obj,'_controlled_custody_event',None)
        name=self.name(obj) if self.is_image(obj) else None
        try:
            result=original(obj,*args,**kwargs)
            if name:assert self.absent(name)
            process=getattr(obj,'process',None)
            assert process is None or process.poll() is not None,'Owned subprocess still running'
            if event:
                for vm in event.get('native_vms',[]):assert proc_identity(vm['pid'])!=vm['starttime'],'Native BEAM survived stop'
                event['observed_absent']=True;event['docker_client_exited']=process is None or process.poll() is not None
            return result
        finally:self.stopping.remove(id(obj))
    def install(self):
        original_popen=subprocess.Popen;custody=self
        def observed_popen(argv,*args,**kwargs):
            is_serve=False
            if custody.busy and isinstance(argv,(list,tuple)) and argv:
                try:is_serve=json.loads(argv[-1])[0]=='serve'
                except (ValueError,TypeError,IndexError):pass
            if not is_serve:return original_popen(argv,*args,**kwargs)
            if argv[:2]==['docker','run']:
                assert '--name' in argv and custody.image in argv
                row={'kind':'docker','name':argv[argv.index('--name')+1],'image':custody.image}
            else:
                assert sha(argv[-2]) in custody.plan['native_artifact_sha256']
                row={'kind':'native-producer','artifact_sha256':sha(argv[-2])}
            assert kwargs.get('start_new_session') is True
            custody.launches.append(row);custody.ledger.write_text(json.dumps(custody.launches,indent=2)+'\n')
            process=original_popen(argv,*args,**kwargs)
            row.update(client_pid=process.pid,client_starttime=proc_identity(process.pid))
            try:custody.ledger.write_text(json.dumps(custody.launches,indent=2)+'\n')
            except BaseException:
                import signal
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10);raise
            return process
        subprocess.Popen=observed_popen
        import foundation_acceptance,hub_acceptance,container_acceptance,history_support,retrieval_support,archive_support
        for cls in [hub_acceptance.ModelFixture,history_support.ChoiceFixture,retrieval_support.NoulFixture,archive_support.ArchiveFixture]:self.fixture(cls)
        for cls,method in [(foundation_acceptance.Runtime,'start'),(foundation_acceptance.Runtime,'stop'),
                           (hub_acceptance.Hub,'start'),(hub_acceptance.Hub,'stop'),(container_acceptance.ContainerHub,'stop')]:
            original=getattr(cls,method);wrapper=self.start if method=='start' else self.stop
            def wrapped(obj,*a,_original=original,_wrapper=wrapper,**kw):return _wrapper(_original,obj,*a,**kw)
            setattr(cls,method,wrapped)
    def finish(self):
        for obj in reversed(self.instances):
            try:self.cleanup_one(obj)
            except BaseException as error:self.errors.append(type(error).__name__)
        starts=[v for v in self.events if v['completed']]
        assert starts and any(v['kind']=='docker' for v in starts),'No image runtime actually qualified'
        assert all(v.get('observed_absent') for v in starts),'Original fixture did not prove all stops'
        assert not self.errors,self.errors


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--job',required=True)
    args=parser.parse_args();plan=json.loads(args.plan.read_text());job=next(v for v in plan['jobs'] if v['name']==args.job)
    sys.path.insert(0,str(Path(plan['frozen'])/'tests'))
    custody=Custody(plan,job,Path(job['custody_report']));failure=None
    try:
        assert os.environ.get('ADHD_RECOVERY_DENY_PROVIDER_PORT')=='18770'
        assert os.environ.get('LD_PRELOAD')==plan['fence_library']
        custody.install();sys.argv=job['test_argv'];runpy.run_path(job['test_argv'][0],run_name='__main__')
    except BaseException as error:failure=error
    finally:
        try:custody.finish()
        except BaseException as cleanup:
            custody.errors.append(type(cleanup).__name__)
            if failure is None:failure=cleanup
        fence_audit=Path(plan['fence_audit']);blocked=fence_audit.read_text().splitlines() if fence_audit.exists() else []
        if blocked and failure is None:failure=AssertionError('Unexpected real provider connection attempted')
        value={'schema':'adhd/controlled-image-custody@1','passed':failure is None,'failure_type':type(failure).__name__ if failure else None,
            'image_config_identity':plan['image_config_identity'],'artifact_sha256':plan['artifact_sha256'],
            'canonical_manifest_sha256':sha(plan['manifest']),'adapter_sha256':sha(__file__),
            'original_helpers_sha256':{key:plan['frozen_inputs']['tests/'+key] for key in ['foundation_acceptance.py','hub_acceptance.py','container_acceptance.py']},
            'controlled_endpoint_whitelist':custody.allowed,'runtime_events':custody.events,'cleanup_failure_types':custody.errors,
            'native_fence_sha256':sha(plan['fence_library']),'blocked_provider_connects':len(blocked),
            'provider_isolation_scope':'Native connect fence mapped; image exact typed-loopback config selection and no redirects. Docker host network has no physical egress firewall; no claim LD_PRELOAD fences image.',
            'all_original_assertions_bounds_corpus':'Original frozen entrypoint run unchanged; wrapper observes custody and cleans owned startup failures only.'}
        Path(job['custody_report']).write_text(json.dumps(value,indent=2)+'\n')
    if failure:raise failure


if __name__=='__main__':main()
