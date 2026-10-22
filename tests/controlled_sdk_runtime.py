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
import re
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import controlled_image_runtime as base


def bounded(argv,deadline,limit=131072):
    """Bound both Docker client output and elapsed time; always reap our client."""
    process=None;selection=selectors.DefaultSelector();streams={};failure=None
    try:
        process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
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
        return {'returncode':code,'stdout':bytes(streams[process.stdout]),'stderr':bytes(streams[process.stderr])}
    finally:
        if process and process.poll() is None:process.kill();process.wait(timeout=3)
        selection.close()
        if process:
            for stream in [process.stdout,process.stderr]:
                if stream:stream.close()


def startup_diagnostics(custody,obj,reader=bounded):
    started=time.monotonic();deadline=started+15;result={'scope':'Read-only after original startup exception; no health retry or deadline extension','owned_identity_verified':False,'observations':{},'unavailable':[]}
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
            result['observations'][label]={'returncode':row['returncode'],'stdout':scrub(row['stdout']),'stderr':scrub(row['stderr'])}
            return row
        except BaseException as error:result['unavailable'].append({'observation':label,'failure_type':type(error).__name__});return None
    try:
        name=custody.name(obj);assert custody.is_image(obj) and name
        row=request('owned_inspect',['inspect',name]);assert row and row['returncode']==0
        values=json.loads(row['stdout']);assert len(values)==1;actual=values[0]
        assert actual['Image']==custody.image and actual['Name']=='/'+name
        assert any(Path(m['Source'])==Path(obj.root) and Path(m['Destination'])==Path(obj.root) for m in actual['Mounts'])
        event=getattr(obj,'_controlled_custody_attempt',{})
        if event.get('container_id'):assert event['container_id']==actual['Id']
        identifier=actual['Id'];assert len(identifier)==64 and all(c in '0123456789abcdef' for c in identifier)
        result.update(owned_identity_verified=True,container_id=identifier,container_name=name,image_config_identity=actual['Image'],state={k:actual['State'].get(k) for k in ['Status','Running','Pid','ExitCode','OOMKilled','Error','StartedAt','FinishedAt']})
        # Raw inspect may include environment data. Keep only selected custody
        # fields above; credentials/configuration are never diagnostic output.
        del result['observations']['owned_inspect']
        request('container_logs',['logs','--timestamps','--tail','80',identifier])
        if actual['State']['Running']:
            assert actual['State']['Pid']>0 and actual['HostConfig']['PidMode']!='host'
            result['pid_namespace_mode']=actual['HostConfig']['PidMode']
            vm=request('namespace_vm',['exec',identifier,'sh','-c','readlink /proc/1/exe; cat /proc/1/status; cat /proc/1/cmdline'])
            result['actual_beam_pid1_observed']=bool(vm and vm['returncode']==0 and vm['stdout'].splitlines()[0].endswith(b'/beam.smp') and re.search(rb'^Pid:\s+1$',vm['stdout'],re.M))
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
        result['observations'].pop('owned_inspect',None)
    result['elapsed_seconds']=time.monotonic()-started
    return result


class SDKCustody(base.Custody):
    def start(self,original,obj,*args,**kwargs):
        def observed(instance,*a,**kw):
            try:return original(instance,*a,**kw)
            except BaseException:
                if self.is_image(instance):
                    try:diagnostic=startup_diagnostics(self,instance)
                    except BaseException as error:diagnostic={'unavailable':[{'failure_type':type(error).__name__}]}
                    instance._controlled_custody_attempt['startup_failure_diagnostics']=diagnostic
                raise
        return super().start(observed,obj,*args,**kwargs)


if __name__=='__main__':
    path=Path(sys.argv[sys.argv.index('--plan')+1]);plan=json.loads(path.read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==plan['frozen_inputs']['tests/controlled_sdk_runtime.py']
    base.Custody=SDKCustody
    base.main()
