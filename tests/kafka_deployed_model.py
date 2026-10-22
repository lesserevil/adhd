"""Optional deployed-image model gate; no model service is started or changed."""
import asyncio
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import httpx


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relay_scope(bind, callers, binding):
    address=ipaddress.IPv4Address(bind)
    assert address.is_private and not address.is_loopback and not address.is_unspecified
    assert callers and len(callers)==len(set(callers))
    for caller in callers:
        ip=ipaddress.IPv4Address(caller);assert ip.is_private and not ip.is_loopback and not ip.is_unspecified
    assert binding
    return {'bind':bind,'allowed_callers':sorted(callers),'resource_binding':binding}


def process_identity(pid):
    raw=Path('/proc/'+str(pid)+'/stat').read_text()
    return {'pid':pid,'start_ticks':raw[raw.rindex(')')+2:].split()[19],
            'cmdline_sha256':hashlib.sha256(Path('/proc/'+str(pid)+'/cmdline').read_bytes()).hexdigest()}


def stop_relay(process, identity, bind, port):
    failures=[]
    try:
        if process.poll() is None:
            assert process_identity(process.pid)==identity
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                assert process_identity(process.pid)==identity
                process.kill();process.wait(timeout=5)
        assert process.poll() is not None
        assert not Path('/proc/'+str(process.pid)).exists(), 'Owned relay PID remains after reap'
    except BaseException as error:failures.append(error)
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as connection:
            connection.settimeout(.5);assert connection.connect_ex((bind,port))!=0, 'Relay listener remains'
    except BaseException as error:failures.append(error)
    if failures:raise failures[0]
    return {'process_exit_code':process.returncode,'listener_independently_absent':True}


async def run(args, *, root, repo, base, credentials, expected, command,
              vm_identity, scope, admin, evidence):
    """Run the original child once, with one owned bounded relay per platform."""
    assert args.model_only and 1024<=args.model_relay_port<=65535
    assert not args.model_url and not args.gateway_report and not args.model_window_file
    before=vm_identity();report=root/'model-relay.json';canaries=root/'model-canaries.json'
    canaries.write_text(json.dumps({'blue':'BLUE foreign project model-canary '+secrets.token_hex(24),
                                   'private':'RED private message model-canary '+secrets.token_hex(24)}));canaries.chmod(0o600)
    argv=[sys.executable,str(repo/'tests/kafka_platform_gateway.py'),'--qualification',
          '--bind',scope['bind'],'--port',str(args.model_relay_port),'--report',str(report),
          '--target','http://127.0.0.1:18770','--max-calls','12','--timeout','10',
          '--privacy-canaries',str(canaries)]
    for caller in scope['allowed_callers']:argv+=['--allowed-caller',caller]
    process=None;identity=None;primary=None;relay_cleanup=None;result=None
    output=(root/'model-relay.log').open('xb')
    try:
        process=subprocess.Popen(argv,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        identity=process_identity(process.pid)
        deadline=time.monotonic()+10
        async with httpx.AsyncClient(trust_env=False) as http:
            while True:
                assert process.poll() is None,'Owned relay exited before corpus'
                try:
                    ready=await http.get('http://'+scope['bind']+':'+str(args.model_relay_port)+'/health',timeout=.5)
                    if ready.status_code==200:break
                except httpx.TransportError:pass
                assert time.monotonic()<deadline,'Owned relay readiness deadline'
                await asyncio.sleep(.05)
        assert json.loads(report.read_text())==[],'Readiness must never call the provider'
        child_path=root/'optional-model.json'
        command([sys.executable,str(repo/'tests/kafka_platform_model.py'),'--rest-url',base,
            '--credentials',str(credentials),'--model-url','http://'+scope['bind']+':'+str(args.model_relay_port)+'/v1/systemone',
            '--gateway-report',str(report),'--privacy-canaries',str(canaries),'--with-backend-queries',
            '--report',str(child_path)],timeout=240)
        child=json.loads(child_path.read_text())
        assert child['passed'] and child['backend_query']['positive_original_cited']
        assert child['hot_model_enable_and_disable'] and child['model_free_second_project_zero_inference']
        assert child['foreign_and_private_canaries_absent_from_red_requests_and_answer']
        assert child['relay_audit']['upstream_attempts']<=12 and child['artifact_sha256'] is None
        assert sha(report)==child['gateway_report_sha256']
        assert not report.with_name(report.name+'.denied').exists()
        assert admin.call({'op':'config_get'})['config']['matcher'] is None
        after=vm_identity();assert after==before,'Hot model changes restarted the actual packaged VM'
        result={'passed':True,'artifact_sha256':expected,'image_config_digest':args.image,
                'report_sha256':sha(child_path),'gateway_report_sha256':sha(report),
                'harness_sha256':sha(repo/'tests/kafka_platform_model.py'),
                'gateway_harness_sha256':sha(repo/'tests/kafka_platform_gateway.py'),
                'same_packaged_vm_before_after_hot_changes':True,'vm_identity':before,
                'relay_process':identity,'relay_scope':scope,'budget':child['relay_audit'],
                'provider_target':'existing localhost18770; no warmup/retry/model-service mutation'}
    except BaseException as error:primary=error;raise
    finally:
        try:
            if process is not None:
                # If identity capture failed, obtain it only for our still-owned
                # unreaped child; never treat an unknown live child as absent.
                if identity is None and process.poll() is None:identity=process_identity(process.pid)
                relay_cleanup=stop_relay(process,identity,scope['bind'],args.model_relay_port)
        except BaseException as cleanup:
            evidence.value['model_relay_cleanup']={'confirmed':False,'error_type':type(cleanup).__name__}
            if primary is not None:primary.add_note('Relay cleanup failed: '+type(cleanup).__name__)
            else:raise
        finally:
            output.close()
            if relay_cleanup:evidence.value['model_relay_cleanup']={'confirmed':True,**relay_cleanup}
    assert result and relay_cleanup
    result['cleanup']=relay_cleanup
    evidence.value['optional_model']=result
    evidence.record('actual-packaged-model-only-hot-filter-match-nonmatch-history-citations-raw-privacy-disable-resume-same-vm-bounded-relay')
