"""Transparent process/VM custody for the unchanged native UI entrypoints."""
import argparse
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys

from controlled_image_runtime import native_vm
from image_ui_runtime import descendants, rig_processes, same, kill_known, run_original
from native_core_remaining import ChildLedger


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Custody:
    def __init__(self,plan,job,work):
        self.plan,self.job,self.work=plan,job,work
        self.instances=[];self.servers=[];self.browsers=[];self.rigs=[];self.vm=[];self.errors=[]
        self.original_module=self.original_rigs=None
    def save(self):
        Path(self.job['launch_ledger']).write_text(json.dumps({'vm':self.vm,'browser_processes':self.browsers,'rigs':self.rigs,
            'cleanup_errors':self.errors},indent=2)+'\n')
    def audit(self,config):
        from controlled_image_runtime import audit_models
        allowed={'http://127.0.0.1:'+str(server.server_address[1])+'/v1/systemone'
            for server,_ in self.servers if server.fileno()>=0 and server.server_address[0]=='127.0.0.1'}
        selected={key:config[key]for key in ['matcher','models','history','retrieval','archive','feedback','optimization']if key in config}
        selected['projects']=[{'settings':{key:value for key,value in (project.get('settings') or {}).items()
            if key in ['matcher','models','history','retrieval','archive','feedback','optimization']}}for project in config.get('projects',[])]
        return audit_models(selected,allowed)
    def observe(self,obj,phase):
        process=obj.process
        assert process is not None and process.poll() is None
        assert sha(self.plan['artifact'])==self.plan['artifact_sha256']
        selected=self.audit(json.loads(obj.file.read_text()))
        values=native_vm(process,Path(self.plan['fence_library']));assert len(values)==1
        row=values[0];assert row['executable_sha256']==self.plan['native_beam_sha256']
        command=Path('/proc',str(row['pid']),'cmdline').read_bytes()
        assert os.fsencode(self.plan['artifact']) in command.split(b'\0'),'Actual native VM must execute the admitted source'
        self.vm.append({'phase':phase,'root':str(obj.root),'artifact_sha256':self.plan['artifact_sha256'],
            'artifact_path':self.plan['artifact'],'cmdline_sha256':hashlib.sha256(command).hexdigest(),
            'selected_models':selected,**row});self.save()
    def install(self):
        from multi_support import Fixture
        from multi_workflow_upgrade import UpgradeRuntime
        from http.server import ThreadingHTTPServer
        from playwright.async_api import BrowserType
        from playwright.sync_api import BrowserType as SyncBrowserType
        custody=self;server_init=ThreadingHTTPServer.__init__
        def server_construct(obj,address,handler,*args,**kwargs):
            server_init(obj,address,handler,*args,**kwargs)
            source=Path(inspect.getsourcefile(handler)).absolute()
            assert source.is_relative_to(Path(custody.plan['frozen'])/'tests')
            assert sha(source)==custody.plan['frozen_inputs'][str(source.relative_to(Path(custody.plan['frozen'])))]
            custody.servers.append((obj,str(source)))
        ThreadingHTTPServer.__init__=server_construct
        start,close,hard=Fixture.start,Fixture.close,Fixture.hard_stop
        async def fixture_start(obj,*args,**kwargs):
            assert obj.image_runtime is None and not obj.args.rest_url
            if obj not in custody.instances:custody.instances.append(obj)
            custody.audit(json.loads(obj.file.read_text()) if obj.file.exists() else obj.config)
            result=await start(obj,*args,**kwargs);custody.observe(obj,'after-original-readiness');return result
        async def fixture_close(obj,*args,**kwargs):
            error=None
            try:
                if obj.process and obj.process.poll() is None:custody.observe(obj,'before-original-close')
            except BaseException as caught:error=caught
            result=await close(obj,*args,**kwargs)
            if error:raise error
            return result
        def fixture_hard(obj,*args,**kwargs):
            if obj.process and obj.process.poll() is None:custody.observe(obj,'before-original-hard-stop')
            return hard(obj,*args,**kwargs)
        Fixture.start,Fixture.close,Fixture.hard_stop=fixture_start,fixture_close,fixture_hard
        runtime_start,runtime_stop=UpgradeRuntime.start,UpgradeRuntime.stop
        def upgrade_start(obj,*args,**kwargs):
            assert obj.owned_image is None and obj.image is None
            if obj not in custody.instances:custody.instances.append(obj)
            custody.audit(json.loads(obj.file.read_text()) if obj.file.exists() else {})
            result=runtime_start(obj,*args,**kwargs);custody.observe(obj,'after-original-readiness');return result
        def upgrade_stop(obj,*args,**kwargs):
            error=None
            try:
                if obj.process and obj.process.poll() is None:custody.observe(obj,'before-original-close')
            except BaseException as caught:error=caught
            result=runtime_stop(obj,*args,**kwargs)
            if error:raise error
            return result
        UpgradeRuntime.start,UpgradeRuntime.stop=upgrade_start,upgrade_stop
        launch=BrowserType.launch;sync_launch=SyncBrowserType.launch
        def record_browsers():
            for row in descendants(os.getpid()):
                if any(name in row['executable']for name in ['chromium','chrome']):custody.browsers.append(row)
            custody.save()
        async def browser_launch(obj,*args,**kwargs):
            try:return await launch(obj,*args,**kwargs)
            finally:record_browsers()
        def sync_browser_launch(obj,*args,**kwargs):
            try:return sync_launch(obj,*args,**kwargs)
            finally:record_browsers()
        BrowserType.launch,SyncBrowserType.launch=browser_launch,sync_browser_launch
        if self.job['name']=='openrig':
            import openrig_acceptance
            self.original_module=openrig_acceptance;self.original_rigs=openrig_acceptance.Rigs
            rigs_launch,rigs_close=openrig_acceptance.Rigs.launch,openrig_acceptance.Rigs.close
            def launch_rigs(obj,*args,**kwargs):
                obj.env.update(PYTHONDONTWRITEBYTECODE='1',NODE_DISABLE_COMPILE_CACHE='1',
                    ADHD_NATIVE_CORE_RUN_NONCE=os.environ['ADHD_NATIVE_CORE_RUN_NONCE'])
                row={'home':str(obj.home),'mux':str(obj.mux),'processes':[],'terminal_seat_count':0};custody.rigs.append(row);custody.save()
                try:
                    result=rigs_launch(obj,*args,**kwargs);row['terminal_seat_count']=len(obj.entries)
                    assert rig_processes(obj.home,obj.mux);return result
                finally:row['processes']=rig_processes(obj.home,obj.mux);custody.save()
            def close_rigs(obj,*args,**kwargs):
                try:return rigs_close(obj,*args,**kwargs)
                finally:
                    for row in custody.rigs:
                        if row['home']==str(obj.home):row['after_original_close']=rig_processes(obj.home,obj.mux)
                    custody.save()
            openrig_acceptance.Rigs.launch,openrig_acceptance.Rigs.close=launch_rigs,close_rigs
    def finish(self):
        for obj in reversed(self.instances):
            if obj.process and obj.process.poll() is None:
                try:
                    if hasattr(obj,'hard_stop'):obj.hard_stop()
                    else:obj.stop(hard=True)
                except BaseException as error:self.errors.append(type(error).__name__)
                self.errors.append('NativeHubSurvivedOriginalClose')
        for row in self.browsers:
            if same(row) and kill_known(row):self.errors.append('BrowserSurvivedOriginalClose')
        for rig in self.rigs:
            for row in rig_processes(rig['home'],rig['mux']):
                if same(row) and kill_known(row):self.errors.append('RigSurvivedOriginalClose')
            assert not rig_processes(rig['home'],rig['mux'])
        for server,_ in self.servers:
            if server.fileno()>=0:server.server_close();self.errors.append('FixtureServerSurvivedOriginalClose')
        assert self.vm,'No actual native VM observed'
        if self.job['name']=='openrig':
            assert len(self.rigs)==1 and self.rigs[0]['terminal_seat_count']==2
            starts=[row for row in self.vm if row['phase']=='after-original-readiness']
            roots={str(Path(self.plan['openrig_root'])),str(Path(self.plan['openrig_root'])/'peer')}
            assert {row['root']for row in starts}==roots and len(starts)==4
            assert all(sum(row['root']==root for row in starts)==2 for root in roots)
            assert len({(row['pid'],row['starttime'])for row in starts})==4
        self.save();assert not self.errors,self.errors


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--job',required=True);parser.add_argument('--reviewed-plan-sha256',required=True);args=parser.parse_args()
    assert sha(args.plan)==args.reviewed_plan_sha256;plan=json.loads(args.plan.read_text());work=args.plan.parent
    assert sha(__file__)==plan['frozen_inputs']['tests/native_ui_runtime.py']
    assert json.loads((work/'started.json').read_text())['plan_sha256']==args.reviewed_plan_sha256
    job=next(row for row in plan['jobs']if row['name']==args.job);custody=Custody(plan,job,work)
    ledger=ChildLedger(job['process_ledger']);error=cleanup=None;ledger_live=[]
    try:
        ledger.install();custody.install();run_original(job,custody.original_module,custody.original_rigs)
    except BaseException as caught:error=caught
    finally:
        try:custody.finish()
        except BaseException as caught:cleanup=caught
        try:ledger_live=ledger.close()
        except BaseException as caught:cleanup=cleanup or caught
        Path(job['custody_report']).write_text(json.dumps({'schema':'adhd/native-ui-custody@1','passed':not error and not cleanup and not ledger_live,
            'kind':'native','artifact_sha256':plan['artifact_sha256'],'original_exception':type(error).__name__ if error else None,
            'cleanup_exception':type(cleanup).__name__ if cleanup else None,'unexpected_live_Popen_handles':ledger_live,
            'native_vm_observations':custody.vm,'browser_processes':custody.browsers,'rigs':custody.rigs,'cleanup_errors':custody.errors,
            'scope':'Original native source execution and unchanged browser/terminal scenarios; no image or live semantic quality claim.'},indent=2)+'\n')
    if error:raise error
    if cleanup:raise cleanup
    assert not ledger_live


if __name__=='__main__':main()
