"""Bound one reviewed recovery harness while preserving its own finally cleanup."""
import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import signal

from container_fixture import OwnedImage
from foundation_acceptance import Runtime
from image_eventing_runtime import EventingFaultImage
from multi_support import Fixture


# asyncio.Handle explicitly rethrows KeyboardInterrupt/SystemExit; it logs and
# swallows other BaseException subclasses from bare callbacks. This remains
# outside Exception catches without claiming to bound arbitrary catch loops.
class QualificationDeadline(KeyboardInterrupt):pass
class QualificationCleanupFailure(BaseException):pass
_deadline_fired=False


def deadline_handler(*_):
    global _deadline_fired
    _deadline_fired=True
    signal.setitimer(signal.ITIMER_REAL,0)
    raise QualificationDeadline('Owned qualification deadline exceeded')


def close_owned_image(target):
    try:
        target.stop()
        assert not getattr(target,'cleanup_blocked',False) and target.name is None
        return
    except BaseException as original:
        failures=[event for event in target.events if event.get('action')=='failed-owned-cleanup']
        if not failures:raise
        last=failures[-1];identifier=last.get('container_id') or last.get('owned_name')
        assert isinstance(identifier,str) and (re.fullmatch('[a-f0-9]{64}',identifier) or re.fullmatch('adhd-[a-z0-9-]+',identifier))
        inspected=target.docker('inspect',identifier,check=False)
        if not EventingFaultImage.authoritative_absence(inspected,identifier):
            assert inspected.returncode==0
            rows=json.loads(inspected.stdout);assert len(rows)==1;row=rows[0]
            assert row['Image']==target.image_id and (row['Id']==identifier or row['Name']=='/'+identifier)
            assert any(m.get('Type')=='bind' and m.get('Source')==str(target.root) and m.get('Destination')==str(target.root) for m in row['Mounts'])
            target.docker('rm','--force',row['Id'])
            final=target.docker('inspect',row['Id'],check=False)
            assert EventingFaultImage.authoritative_absence(final,row['Id'])
        target.cleanup_blocked=False;target.name=target.container_id=None
        target.events.append({'action':'outer-fallback-absence','container_id':identifier,'observed_absent':True})
        # Closure recovery cannot turn the original failed cleanup into success.
        raise original


def run_script(script,argv,budget,cleanup_report,compiled_binding=None):
    global _deadline_fired
    _deadline_fired=False
    script=Path(script).absolute();assert script.resolve(strict=True)==script and script.is_file()
    assert type(budget) is int and 0<budget<=5400
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'Do not replace another timer'
    images=[];runtimes=[];primary=None;failures=[];cache_hook=None
    if compiled_binding is not None:
        from image_recovery_cache import CacheCustody
        cache_hook=CacheCustody(OwnedImage,compiled_binding);cache_hook.install()
    image_init=OwnedImage.__init__;runtime_init=Runtime.__init__;fixture_close=Fixture.close
    old_handler=signal.getsignal(signal.SIGALRM);old_argv=sys.argv
    def stop_wrapper(stop):
        def owned_stop(*a,**k):
            if sys.exception() is not None:signal.setitimer(signal.ITIMER_REAL,0)
            return stop(*a,**k)
        return owned_stop
    def image(self,*a,**k):
        image_init(self,*a,**k);images.append(self);self.stop=stop_wrapper(self.stop)
    def native(self,*a,**k):
        runtime_init(self,*a,**k);runtimes.append(self);self.stop=stop_wrapper(self.stop)
    async def close(self,*a,**k):
        if sys.exception() is not None:signal.setitimer(signal.ITIMER_REAL,0)
        return await fixture_close(self,*a,**k)
    OwnedImage.__init__=image;Runtime.__init__=native
    Fixture.close=close
    try:
        signal.signal(signal.SIGALRM,deadline_handler);signal.setitimer(signal.ITIMER_REAL,budget)
        sys.argv=[str(script),*argv]
        try:runpy.run_path(str(script),run_name='__main__')
        except SystemExit as error:
            if error.code not in (None,0):primary=error;raise
        except BaseException as error:primary=error;raise
    finally:
        # Disarm before all inner/outer cleanup. Scenario finally clauses run
        # while unwinding the dedicated BaseException as well.
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
        sys.argv=old_argv;OwnedImage.__init__=image_init;Runtime.__init__=runtime_init;Fixture.close=fixture_close
        for target in reversed(images):
            if target.name is not None or getattr(target,'cleanup_blocked',False):
                try:close_owned_image(target)
                except BaseException as error:failures.append(type(error).__name__)
        for runtime in reversed(runtimes):
            process=getattr(runtime,'process',None)
            if process is not None and process.poll() is None:
                try:runtime.stop(hard=True)
                except BaseException as error:failures.append(type(error).__name__)
        if cache_hook is not None:
            cache_hook.restore()
            if any(getattr(obj,'recovery_static_cache_failure',None)for obj in images):failures.append('StaticCacheVerificationFailed')
        native_absent=all(getattr(obj,'process',None) is None or obj.process.poll() is not None for obj in runtimes)
        if not native_absent:failures.append('OwnedNativeProcessStillRunning')
        value={'schema':'adhd/recovery-entry-cleanup@1','passed':primary is None and not failures and not _deadline_fired,
            'deadline_expired':_deadline_fired,
            'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'outer_bound_seconds':budget,
            'failure_type':type(primary).__name__ if primary else None,'cleanup_failure_types':failures,
            'images':[{'image_config_identity':obj.image_id,'closed':obj.name is None and not getattr(obj,'cleanup_blocked',False),
                'events':obj.events,'rebind_argument_observations':getattr(obj,'rebind_argument_observations',[]),'payload_probe_lifecycle':obj.probe_events,'static_compiled_cache':getattr(obj,'recovery_static_cache',None),'compiled_launches':getattr(obj,'recovery_compiled_launches',[]),'static_cache_failure':getattr(obj,'recovery_static_cache_failure',None)} for obj in images],
            'native_owned_runtimes':len(runtimes),'owned_native_processes_absent':native_absent}
        try:Path(cleanup_report).write_text(json.dumps(value,indent=2)+'\n')
        except BaseException as error:
            if primary is not None:primary.add_note('Qualification cleanup report failure: '+type(error).__name__)
            else:raise
        if failures:
            if primary is not None:primary.add_note('Outer owned cleanup failures: '+','.join(failures))
            else:raise QualificationCleanupFailure('Owned cleanup failed')
        if _deadline_fired and primary is None:raise QualificationDeadline('Qualification timeout was swallowed by scenario')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--script',type=Path,required=True)
    parser.add_argument('--script-sha256',required=True);parser.add_argument('--timeout',type=int,required=True)
    parser.add_argument('--cleanup-report',type=Path,required=True);parser.add_argument('arguments',nargs=argparse.REMAINDER)
    parser.add_argument('--compiled-binding',type=Path);parser.add_argument('--compiled-binding-sha256')
    args=parser.parse_args();assert hashlib.sha256(args.script.read_bytes()).hexdigest()==args.script_sha256
    assert not args.cleanup_report.exists()
    argv=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    compiled=None
    if args.compiled_binding is not None:
        assert hashlib.sha256(args.compiled_binding.read_bytes()).hexdigest()==args.compiled_binding_sha256
        compiled=json.loads(args.compiled_binding.read_text())
    run_script(args.script,argv,args.timeout,args.cleanup_report,compiled)


if __name__=='__main__':main()
