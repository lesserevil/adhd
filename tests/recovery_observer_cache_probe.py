"""Prepare/run a bounded network-none trace-setup diagnostic, never a hub."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def load(p):
    spec=importlib.util.spec_from_file_location('phase_guard',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def script(observer,cache_digest):
    return '''
raw = File.read!("/runtime/adhd/manifest.json")
true = Base.encode16(:crypto.hash(:sha256, raw), case: :lower) == "CACHE_DIGEST"
cache = JSON.decode!(raw)
true = cache["schema"] == "adhd/precompiled-cache@1"
true = map_size(cache["beams"]) == 59
Enum.each(cache["beams"], fn {name, digest} ->
  path = "/runtime/adhd/ebin/" <> name
  bytes = File.read!(path)
  true = Base.encode16(:crypto.hash(:sha256, bytes), case: :lower) == digest
  module = name |> String.trim_trailing(".beam") |> String.to_atom()
  {:module, ^module} = :code.load_binary(module, String.to_charlist(path), bytes)
end)
IO.puts("cache-loaded|59|" <> System.otp_release() <> "|" <> System.version())
System.put_env("ADHD_TEST_PHASE_LOG", "/tmp/phase.log")
System.put_env("ADHD_TEST_PHASE_ARM", "/tmp/never-armed")
System.put_env("ADHD_TEST_PHASE_NONCE", "00000000000000000000000000000001")
Code.eval_string(Base.decode64!("OBSERVER"), [], file: "bound-test-observer.exs")
wait = fn wait, n ->
  text = File.read!("/tmp/phase.log")
  if String.contains?(text, "|ready|") or String.contains?(text, "|observer-failed|") do
    text
  else
    if n == 0, do: raise("Bounded trace setup wait expired")
    Process.sleep(20)
    wait.(wait, n - 1)
  end
end
text = wait.(wait, 250)
IO.write(text)
'''.replace('CACHE_DIGEST',cache_digest).replace('OBSERVER',base64.b64encode(observer).decode())

def probe_options(args,image):
    values=list(args)
    assert values[0]=='run' and values.count(image)==1
    assert '--network'in values and values[values.index('--network')+1]=='none' and '--read-only'in values
    assert not any(x in ['--mount','--volume','--pid','--no-healthcheck']or x.startswith('--pid=')for x in values)
    index=values.index(image)
    values[index:index]=['--no-healthcheck','--tmpfs','/tmp:rw,nosuid,noexec,size=16m','--memory','512m','--cpus','1','--pids-limit','128','--env','ERL_FLAGS=+S 2:2']
    return tuple(values)


def verify(work,plan):
    assert sha(work/'driver.py')==plan['driver_sha256']and sha(work/'observer.exs')==plan['observer_sha256']
    original=Path(plan['phase_work']);assert sha(original/'plan.json')==plan['phase_plan_sha256']and sha(original/'driver.py')==plan['phase_driver_sha256']
    helper=load(original/'driver.py');phase=json.loads((original/'plan.json').read_text());assert helper.verify(original,phase)
    parent=json.loads((Path(phase['original_work'])/'plan.json').read_text())
    for key in ['image_config_identity','artifact_sha256','canonical_manifest_sha256','admission_manifest_sha256']:assert plan[key]==parent[key]
    assert plan['cache_manifest_sha256']==parent['compiled_binding']['compiled_cache']['manifest_sha256']
    assert plan['manifest_path']==str(Path(phase['original_work'])/'context/manifest.json')
    assert plan['daemon_env']=={k:parent['env'][k]for k in ['PATH','DOCKER_HOST','DOCKER_CONFIG']}
    return helper

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--verify-only',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--work',type=Path,required=True);p.add_argument('--phase-work',type=Path);p.add_argument('--plan-sha256');a=p.parse_args();assert sum([a.prepare,a.verify_only,a.execute])==1
    work=a.work.absolute()
    if a.prepare:
        assert not work.exists();work.mkdir(mode=0o700);shutil.copyfile(__file__,work/'driver.py');shutil.copyfile(Path(__file__).with_name('recovery_phase_observer.exs'),work/'observer.exs')
        phase=a.phase_work.absolute();pp=json.loads((phase/'plan.json').read_text());original=Path(pp['original_work']);parent=json.loads((original/'plan.json').read_text());binding=parent['compiled_binding']['compiled_cache']
        plan={'schema':'adhd/recovery-observer-cache-probe@1','driver_sha256':sha(work/'driver.py'),'observer_sha256':sha(work/'observer.exs'),'phase_work':str(phase),'phase_plan_sha256':sha(phase/'plan.json'),'phase_driver_sha256':sha(phase/'driver.py'),'artifact_sha256':parent['artifact_sha256'],'canonical_manifest_sha256':parent['canonical_manifest_sha256'],'admission_manifest_sha256':parent['admission_manifest_sha256'],'image_config_identity':parent['image_config_identity'],'manifest_path':str(original/'context/manifest.json'),'cache_manifest_sha256':binding['manifest_sha256'],'daemon_env':{k:parent['env'][k]for k in ['PATH','DOCKER_HOST','DOCKER_CONFIG']},'scope':'Diagnostic only: network-none/readonly exact image,59 hash-checked cached BEAM loads without boot/dispatcher; only test observer compiled; per-MFA setup output, no hub/model/broker calls.','once':True,'runs':1}
        dump(work/'plan.json',plan);print(sha(work/'plan.json'));return
    assert sha(work/'plan.json')==a.plan_sha256;plan=json.loads((work/'plan.json').read_text());helper=verify(work,plan)
    if a.verify_only:assert not(work/'started.json').exists();print('Verified; no execution');return
    assert Path(__file__).absolute()==work/'driver.py';helper.claim(work)
    from container_fixture import OwnedImage
    class Probe(OwnedImage):
        def docker(self,*args,**kwargs):
            if args and args[0]=='run':
                args=probe_options(args,self.image_id)
            return super().docker(*args,**kwargs)
    for k in list(os.environ):
        if k.startswith('DOCKER_'):del os.environ[k]
    os.environ.update(plan['daemon_env']);target=Probe(plan['image_config_identity'],plan['manifest_path'],work);error=None;output=b''
    try:
        target.verify();output=target.probe('elixir','-e',script((work/'observer.exs').read_bytes(),plan['cache_manifest_sha256']))
        (work/'trace.log').write_bytes(output)
    except BaseException as e:error=type(e).__name__;raise
    finally:
        # probe() owns exact issued-name/full-ID cleanup, including run timeout.
        clean=not getattr(target,'probe_cleanup_blocked',False)and getattr(target,'probe_active_name',None)is None
        dump(work/'result.json',{'diagnostic_only':True,'failure_type':error,'probe_cleanup_confirmed':clean,'payload_verified':target.verified,'observer_ready':b'|ready|'in output,'observer_setup_failed':b'|observer-failed|'in output,'probe_lifecycle':target.probe_events,'trace_sha256':sha(work/'trace.log')if(work/'trace.log').exists()else None})
        assert clean
if __name__=='__main__':main()
