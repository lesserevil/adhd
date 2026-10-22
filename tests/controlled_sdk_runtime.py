#!/usr/bin/env python3
"""Custody adapter with bounded observations after an original SDK startup failure.

The unchanged entrypoint owns its30s deadline. Diagnostics happen only after
that original exception and preserve it, without another health request/start.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import inspect
import httpx
import re
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import controlled_image_runtime as base


def bounded(argv,deadline,limit=131072):
    """Absolute collection deadline plus at most3s to kill/reap our client."""
    process=None;selection=selectors.DefaultSelector();streams={};primary=None;cleanup=None;value=None
    client={'pid':None,'starttime':None,'reaped':False,'forced_kill':False,'maximum_reap_grace_seconds':3}
    try:
        process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        client['pid']=getattr(process,'pid',None)
        if client['pid'] is not None:client['starttime']=base.proc_identity(process.pid)
        for stream in [process.stdout,process.stderr]:
            os.set_blocking(stream.fileno(),False);selection.register(stream,selectors.EVENT_READ);streams[stream]=bytearray()
        while selection.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Diagnostic client deadline')
            for key,_ in selection.select(min(remaining,.1)):
                body=os.read(key.fileobj.fileno(),min(8192,limit-sum(map(len,streams.values()))+1))
                if not body:selection.unregister(key.fileobj)
                else:
                    streams[key.fileobj].extend(body)
                    if sum(map(len,streams.values()))>limit:raise ValueError('Diagnostic output limit')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Diagnostic client deadline')
        code=process.wait(timeout=remaining)
        value={'returncode':code,'stdout':bytes(streams[process.stdout]),'stderr':bytes(streams[process.stderr])}
    except BaseException as error:primary=error
    finally:
        try:
            if process and process.poll() is None:
                client['forced_kill']=True;process.kill();process.wait(timeout=3)
            if process:client['reaped']=process.poll() is not None
        except BaseException as error:cleanup=error;client['cleanup_failure_type']=type(error).__name__
        finally:
            selection.close()
            if process:
                for stream in [process.stdout,process.stderr]:
                    if stream:stream.close()
    if primary is not None:
        primary.owned_diagnostic_client=client
        raise primary
    if cleanup is not None:
        cleanup.owned_diagnostic_client=client
        raise cleanup
    value['client_process']=client
    return value


def startup_diagnostics(custody,obj,reader=bounded):
    started=time.monotonic();deadline=started+15;result={'scope':'Read-only after original startup exception; no health retry or deadline extension','owned_identity_verified':False,'collection_deadline_seconds':15,'maximum_client_reap_grace_seconds':3,'maximum_collection_and_reap_seconds':18,'observations':{},'unavailable':[]}
    secret_values=list(getattr(obj,'tokens',{}).values())
    def scrub(value):
        text=value.decode(errors='replace') if isinstance(value,bytes) else value
        for secret in secret_values:
            if isinstance(secret,str) and secret:text=text.replace(secret,'<redacted-fixture-credential>')
        return text
    def request(label,args):
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Overall diagnostic deadline')
            row=reader(['docker',*args],min(deadline,time.monotonic()+3))
            result['observations'][label]={'returncode':row['returncode'],'stdout':scrub(row['stdout']),'stderr':scrub(row['stderr']),'client_process':row.get('client_process')}
            return row
        except BaseException as error:result['unavailable'].append({'observation':label,'failure_type':type(error).__name__,'client_process':getattr(error,'owned_diagnostic_client',None)});return None
    try:
        name=custody.name(obj);assert custody.is_image(obj) and name
        row=request('owned_inspect',['inspect',name]);assert row and row['returncode']==0
        values=json.loads(row['stdout']);assert len(values)==1;actual=values[0]
        assert actual['Image']==custody.image and actual['Name']=='/'+name
        assert any(m['Type']=='bind' and Path(m['Source'])==Path(obj.root) and Path(m['Destination'])==Path(obj.root) for m in actual['Mounts'])
        event=getattr(obj,'_controlled_custody_attempt',{})
        if event.get('container_id'):assert event['container_id']==actual['Id']
        identifier=actual['Id'];assert len(identifier)==64 and all(c in '0123456789abcdef' for c in identifier)
        result.update(owned_identity_verified=True,container_id=identifier,container_name=name,image_config_identity=actual['Image'],state={k:actual['State'].get(k) for k in ['Status','Running','Pid','ExitCode','OOMKilled','Error','StartedAt','FinishedAt']})
        # Raw inspect may include environment data. Keep only selected custody
        # fields above; credentials/configuration are never diagnostic output.
        result['owned_inspection_client']=result['observations']['owned_inspect'].get('client_process')
        del result['observations']['owned_inspect']
        request('container_logs',['logs','--timestamps','--tail','80',identifier])
        if actual['State']['Running']:
            assert actual['State']['Pid']>0 and actual['HostConfig']['PidMode']!='host'
            result['pid_namespace_mode']=actual['HostConfig']['PidMode']
            vm=request('namespace_vm',['exec',identifier,'sh','-c','readlink /proc/1/exe; cat /proc/1/status; cat /proc/1/cmdline'])
            result['actual_beam_pid1_observed']=bool(vm and vm['returncode']==0 and vm['stdout'].splitlines()[0].endswith(b'/beam.smp') and re.search(rb'^Pid:\s+1$',vm['stdout'],re.M))
            request('passive_namespace_listeners',['exec',identifier,'sh','-c','cat /proc/1/net/tcp /proc/1/net/tcp6; ls -l /proc/1/fd'])
            manifest=request('canonical_manifest',['exec',identifier,'cat','/app/manifest.json'])
            result['actual_canonical_manifest_matched']=bool(manifest and manifest['returncode']==0 and manifest['stdout']==custody.manifest_bytes)
            files=base.runtime_app_files(custody.manifest,custody.plan['expected_app_files'])
            hashes=request('actual_app_hashes',['exec',identifier,'sha256sum',*['/app/'+name for name in files]])
            result['all59_actual_app_hashes_matched']=False
            if hashes and hashes['returncode']==0:
                parsed={path.removeprefix('/app/'):digest for digest,path in (line.split() for line in hashes['stdout'].decode().splitlines())}
                result['all59_actual_app_hashes_matched']=parsed==files
    except BaseException as error:
        result['unavailable'].append({'observation':'owned_startup_custody','failure_type':type(error).__name__})
        # No log or exec is issued after an unverified/foreign inspection.
        inspection=result['observations'].pop('owned_inspect',None)
        if inspection:result['owned_inspection_client']=inspection.get('client_process')
    result['elapsed_seconds']=time.monotonic()-started
    return result


class OriginalHealthCalls:
    """Observe only calls issued directly by the unchanged Hub.start body."""
    def __init__(self,original,obj):
        self.code=original.__code__;self.url=getattr(obj,'base','')+'/health'
        self.rows=[];self.observation_errors=[];self.started=time.monotonic()
    def __enter__(self):
        self.previous=httpx.get
        def observed(*args,**kwargs):
            caller=inspect.currentframe().f_back
            selected=(caller.f_code is self.code and args==(self.url,) and kwargs=={'timeout':1})
            if not selected:return self.previous(*args,**kwargs)
            began=time.monotonic();row={'elapsed_seconds':began-self.started,'timeout_seconds':1}
            try:
                response=self.previous(*args,**kwargs)
            except BaseException as error:
                row['exception_type']=type(error).__name__
                self.record(row,began)
                raise
            try:
                # httpx.get has already buffered this response. Never consume a
                # stream, call json(), request again, or alter the same object.
                body=response.content
                row.update(status_code=response.status_code,body_bytes=len(body),body_prefix_hex=body[:1024].hex(),body_truncated=len(body)>1024)
            except BaseException as error:self.observation_errors.append(type(error).__name__)
            self.record(row,began)
            return response
        httpx.get=observed
        return self
    def record(self,row,began):
        row['request_seconds']=time.monotonic()-began
        if len(self.rows)<512:self.rows.append(row)
        elif 'ObservationRowsBound' not in self.observation_errors:self.observation_errors.append('ObservationRowsBound')
    def __exit__(self,*exception):httpx.get=self.previous
    def evidence(self):
        return {'scope':'Only original direct Hub.start health calls; original30s/timeout1/sleeps/request-response-exception semantics unchanged',
                'maximum_rows':512,'maximum_body_prefix_bytes':1024,'calls':self.rows,'observation_error_types':self.observation_errors}


class SDKCustody(base.Custody):
    def inspect_image(self,obj,event):
        # The unchanged Hub.start has already completed its original health
        # measurement. These read-only custody checks issue no health/warmup.
        super().inspect_image(obj,event)
        compiled=self.plan.get('compiled_cache')
        if not compiled:return
        value=compiled['manifest'];name=self.name(obj)
        raw=self.docker('exec',name,'cat','/runtime/adhd/manifest.json').stdout
        assert hashlib.sha256(raw).hexdigest()==compiled['manifest_sha256'] and json.loads(raw)==value
        files={'/runtime/adhd/boot.exs':value['boot_sha256'],'/runtime/adhd/build.exs':value['build_sha256'],
               '/runtime/adhd/inputs.json':value['inputs_sha256'],
               **{'/runtime/adhd/ebin/'+k:v for k,v in value['beams'].items()},
               **{('/proc/1/exe' if k=='/proc/self/exe' else k):v for k,v in value['toolchain']['anchors'].items()}}
        actual=self.docker('exec',name,'sha256sum',*files).stdout.decode().splitlines()
        observed={line.split(None,1)[1].strip():line.split(None,1)[0] for line in actual}
        assert observed==files,'Actual compiled helpers/BEAMs/toolchain differ'
        row=json.loads(self.docker('inspect',name).stdout)[0]
        assert row['Id']==event['container_id'] and row['State']['Pid']==event['host_vm_pid'] and row['State']['Running']
        assert row['Config']['Entrypoint']==compiled['reviewed_runtime_audit']['entrypoint']
        event['compiled_cache']={'manifest_sha256':compiled['manifest_sha256'],'modules':len(value['modules']),
              'cache_and_toolchain_files_verified':len(files),'entrypoint':row['Config']['Entrypoint'],
              'custody_after_original_health_only':True,'extra_health_or_warmup_requests':0}
    def start(self,original,obj,*args,**kwargs):
        def observed(instance,*a,**kw):
            recorder=OriginalHealthCalls(original,instance)
            try:
                with recorder:return original(instance,*a,**kw)
            except BaseException:
                if self.is_image(instance):
                    try:diagnostic=startup_diagnostics(self,instance)
                    except BaseException as error:diagnostic={'unavailable':[{'failure_type':type(error).__name__}]}
                    instance._controlled_custody_attempt['startup_failure_diagnostics']=diagnostic
                raise
            finally:
                instance._controlled_custody_attempt['original_health_calls']=recorder.evidence()
        return super().start(observed,obj,*args,**kwargs)


if __name__=='__main__':
    path=Path(sys.argv[sys.argv.index('--plan')+1]);plan=json.loads(path.read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==plan['frozen_inputs']['tests/controlled_sdk_runtime.py']
    base.Custody=SDKCustody
    base.main()
