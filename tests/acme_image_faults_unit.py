"""No runtime/network starts: guard real fault inputs, owned kill, partial cleanup."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from acme_image_faults import floor,kill_owned,owned_child
from acme_image_provision import OwnedProvision
import acme_image_fault_flow


class FaultGuards(unittest.TestCase):
    def test_real_floor_shape_and_future_integer_not_arbitrary_private_state(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'acme').mkdir();path=root/'acme'/'issuer-retry.json'
            good={'code':'ACME_RATE_LIMIT','retry_at':int(time.time()*1000)+120000}
            for value in [good,{**good,'retry_at':True},{**good,'retry_at':float(good['retry_at'])},
                          {**good,'retry_at':0},{**good,'code':'private-error-string'},{**good,'secret':'forbidden'}]:
                path.write_text(json.dumps(value));path.chmod(0o600)
                if value==good and type(value['retry_at'])is int:self.assertEqual(floor(root),good)
                else:
                    with self.assertRaises(AssertionError):floor(root)

    def test_changed_owned_pid_never_signalled_and_descriptor_closed(self):
        with patch('acme_image_faults.os.pidfd_open',return_value=17),\
             patch('acme_image_faults.ticks',return_value='new'),\
             patch('acme_image_faults.signal.pidfd_send_signal')as send,\
             patch('acme_image_faults.os.close')as close:
            with self.assertRaisesRegex(AssertionError,'changed'):kill_owned({'pid':123,'start_ticks':'old'})
            send.assert_not_called();close.assert_called_once_with(17)

    def test_foreign_executable_hash_never_becomes_owned_kill_target(self):
        runtime=SimpleNamespace(observer=SimpleNamespace(evidence=lambda:{'rows':[{
          'pid':123,'start_ticks':'old','executable_basename':'lego'}]}))
        with patch('acme_image_faults.ticks',return_value='old'),patch('acme_image_faults.sha',return_value='bad'):
            with self.assertRaises(AssertionError):owned_child(runtime,'lego','expected')

    def test_provision_constructor_inert_close_attempts_every_partial_resource(self):
        target=Mock();item=OwnedProvision({},target,Path('/unstarted-owned-fixture'))
        target.assert_not_called();self.assertIsNone(item.runtime)
        primary=OSError('owned stop error')
        item.runtime=SimpleNamespace(stop=Mock(side_effect=primary))
        item.challenge=SimpleNamespace(close=Mock());item.issuer=SimpleNamespace(close=Mock())
        with self.assertRaises(OSError)as caught:item.close()
        self.assertIs(caught.exception,primary)
        item.challenge.close.assert_called_once();item.issuer.close.assert_called_once()
        self.assertEqual(item.cleanup_errors,['OSError'])

    def test_context_partial_start_preserves_programming_error_while_unwinding(self):
        item=OwnedProvision({},Mock(),Path('/unstarted-owned-fixture'))
        primary=AssertionError('exact original failed startup')
        def partial():
            item.issuer=SimpleNamespace(close=Mock(side_effect=OSError('owned close failure')))
            item.challenge=SimpleNamespace(close=Mock())
            raise primary
        with patch.object(item,'start',side_effect=partial):
            with self.assertRaises(AssertionError)as caught:
                with item:raise AssertionError('must not enter')
        self.assertIs(caught.exception,primary);item.challenge.close.assert_called_once()
        self.assertEqual(item.cleanup_errors,['OSError'])

    def test_missing_accepted_target_refuses_before_import_or_resource(self):
        with tempfile.TemporaryDirectory()as directory:
            driver=Path(acme_image_fault_flow.__file__).absolute();path=Path(directory)/'plan.json'
            plan={'schema':'adhd/acme-image-fault-flow@1','driver':str(driver),
              'driver_sha256':acme_image_fault_flow.digest(driver),'target':None}
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(AssertionError,'Actual accepted'):acme_image_fault_flow.verify(path,acme_image_fault_flow.digest(path))
            self.assertEqual([p.name for p in Path(directory).iterdir()],['plan.json'])

    def test_active_cancellation_happens_after_durable_floor_before_settlement(self):
        from acme_image_faults import floor_phase
        from datetime import datetime,timedelta,timezone
        now=datetime.now(timezone.utc)
        before={'https_state':'ready','certificate':{'sha256':'leaf','not_after':(now+timedelta(seconds=90)).isoformat()},
          'last_error':None,'last_attempt_at':'actual'}
        issuer=SimpleNamespace(snapshot=Mock(return_value={'active':0,'events':[], 'requests':1}),set_fault=Mock())
        # Fault evidence must be actual directory error headers; wrong route or
        # absent event fails before a cancellation command can be sent.
        admin=Mock();admin.api.return_value=before;admin.mutate.return_value=({'config_revision':2},{})
        secure=Mock()
        with patch('acme_image_faults.floor',return_value={'code':'ACME_PROCESS','retry_at':int(time.time()*1000)+121000}),\
             patch('acme_image_faults.wait',side_effect=lambda test,*args:test()),\
             patch('acme_image_faults.lock_busy',return_value=True):
            with self.assertRaises(AssertionError):
                floor_phase('issuer-floor-cancel',admin=admin,secure=secure,runtime=Mock(),hub='/unused',
                  issuer=issuer,issuer_root='/unused',password='unused')
        self.assertEqual(admin.mutate.call_count,1)
        secure.request.assert_not_called()

    def test_expiry_does_not_accept_unrelated_transport_timeout_as_tls_failure(self):
        from acme_image_faults import expiry_phase
        from datetime import datetime,timedelta,timezone
        from urllib.error import URLError
        before={'https_state':'ready','certificate':{'not_after':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}}
        expired={'https_state':'expired','active_domains':[]}
        admin=Mock();admin.api.side_effect=[before,expired]
        secure=Mock();secure.request.side_effect=URLError(TimeoutError('not certificate rejection'))
        with patch('acme_image_faults.remaining',return_value=45),\
             patch('acme_image_faults.floor',return_value={'retry_at':int(time.time()*1000)+121000}):
            with self.assertRaisesRegex(AssertionError,'certificate/handshake'):
                expiry_phase(admin=admin,secure=secure,hub='/unused',issuer=Mock())

    def test_asynchronous_floor_only_missing_file_is_pending_not_malformed_data(self):
        from acme_image_faults import pending_floor,wait
        good={'code':'ACME_PROCESS','retry_at':int(time.time()*1000)+120000}
        with patch('acme_image_faults.floor',side_effect=[FileNotFoundError(),good]),\
             patch('acme_image_faults.time.sleep'):
            self.assertEqual(wait(lambda:pending_floor('/unused'),1,'bounded floor'),good)
        for failure in [json.JSONDecodeError('malformed','{',0),AssertionError('wrong private shape'),PermissionError()]:
            with patch('acme_image_faults.floor',side_effect=failure):
                with self.assertRaises(type(failure))as caught:pending_floor('/unused')
                self.assertIs(caught.exception,failure)

    def test_public_due_truncation_accepts_issuer_second_but_rejects_local_reset(self):
        from acme_image_faults import public_floor_due
        minimum=120987
        status={'enabled':True,'acme_state':'backoff','next_attempt_at':'1970-01-01T00:02:00Z'}
        observed=public_floor_due(status,minimum)
        self.assertEqual(observed['public_due_unix_ms'],120000)
        self.assertEqual(observed['private_issuer_floor_unix_ms'],minimum)
        # Offset representation is the same instant, not a local-time shortcut.
        public_floor_due({**status,'next_attempt_at':'1970-01-01T01:02:00+01:00'},minimum)
        for value in ['1970-01-01T00:00:30Z','1970-01-01T00:00:31Z','1970-01-01T00:01:59Z',None,
                      '1970-01-01T00:02:00']:
            with self.subTest(value=value),self.assertRaises(AssertionError):
                public_floor_due({**status,'next_attempt_at':value},minimum)
        for patch_value in [{'enabled':False},{'acme_state':'ordering'}]:
            with self.assertRaises(AssertionError):public_floor_due({**status,**patch_value},minimum)
