"""Launch/header observations and narrow failures without starting a process."""
import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from urllib.error import URLError
import unittest

spec=importlib.util.spec_from_file_location('retention_scenario',Path(__file__).with_name('eventing_retention_recovery.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def fixture():
    f=m.TrackedFixture.__new__(m.TrackedFixture);f.retention_identities=[];f.retention_process_keys={};f.retention_health=[];f.image_runtime=None
    return f
class Launch(unittest.TestCase):
    def test_identity_recorded_on_assignment_without_startup(self):
        f=fixture();process=object();identity={'pid':123,'start_ticks':456,'command_sha256':'synthetic'}
        with patch.object(m,'owned_native_identity',return_value=identity)as observe:
            f.process=process
            self.assertIs(f.process,process);self.assertEqual(f.retention_identities,[identity]);observe.assert_called_once_with(process)
        self.assertEqual(f.retention_process_keys[process],(123,456))
    def test_image_cli_key_is_not_a_native_vm_identity(self):
        f=fixture();f.image_runtime=object()
        with patch.object(m,'owned_native_identity',return_value={'pid':123,'start_ticks':456}):f.process=object()
        self.assertEqual(f.retention_identities,[]);self.assertEqual(list(f.retention_process_keys.values()),[(123,456)])
    def test_header_observer_preserves_original_start_calls(self):
        f=fixture();f.base='http://127.0.0.1:12345';f.process=None;calls=[]
        class Client:
            def __init__(self,*args,**kwargs):self.hooks=kwargs['event_hooks'];calls.append((args,kwargs))
        async def original_start(self):
            client=m.multi_support.httpx.AsyncClient(timeout=1)
            for hook in client.hooks['response']:
                await hook(SimpleNamespace(request=SimpleNamespace(url=self.base+'/health'),status_code=200))
        with patch.object(m.multi_support.httpx,'AsyncClient',Client),patch.object(m.Fixture,'start',original_start):asyncio.run(f.start())
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][1]['timeout'],1);self.assertEqual(len(f.retention_health),1)
    def test_unexpected_assertion_and_transport_errors_propagate(self):
        for error in (AssertionError('programming'),ValueError('bad JSON'),URLError('unknown'),TimeoutError('deadline')):
            client=SimpleNamespace(request=lambda *args,e=error:(_ for _ in()).throw(e))
            with self.assertRaises(type(error))as observed:m.faulted_update(client,{})
            self.assertIs(observed.exception,error)
    def test_fault_request_keeps_exact_message_and_revision(self):
        command={'op':'config_update','message_id':'fixed-mid','expected_revision':7};seen=[]
        def request(path,body):
            seen.append((path,body));return 500,{'error':{'code':'INTERNAL','message':'Request failed'}},{}
        m.faulted_update(SimpleNamespace(request=request),command)
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][0],'/admin/api');self.assertIs(seen[0][1],command)
        self.assertEqual(command['message_id'],'fixed-mid');self.assertEqual(command['expected_revision'],7)
    def test_only_known_error_envelope_or_disconnect_is_accepted(self):
        client=SimpleNamespace(request=lambda *args:(500,{'error':{'code':'INTERNAL','message':'Request failed'}},{}))
        self.assertEqual(m.faulted_update(client,{})['http_status'],500)
        for status,body in ((200,{}),(500,{'error':{'code':'OTHER','message':'Request failed'}}),(403,{})):
            client=SimpleNamespace(request=lambda *args,s=status,b=body:(s,b,{}))
            with self.assertRaises(AssertionError):m.faulted_update(client,{})
        client=SimpleNamespace(request=lambda *args:(_ for _ in()).throw(m.RemoteDisconnected('closed')))
        self.assertEqual(m.faulted_update(client,{})['transport_failure_type'],'RemoteDisconnected')
if __name__=='__main__':unittest.main()
