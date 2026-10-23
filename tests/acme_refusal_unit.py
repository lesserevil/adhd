"""Actual refusal fixture with mocked sockets: no network or process starts."""
from datetime import datetime,timedelta,timezone
import errno
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import acme_fault_cases as module

class RefusalGuards(unittest.TestCase):
    def exercise(self,refused_errno=errno.ECONNREFUSED):
        events=[]
        class Socket:
            def __init__(self,role):self.role=role
            def __enter__(self):events.append(('enter',self.role));return self
            def __exit__(self,*args):events.append(('close',self.role))
            def bind(self,address):self.address=address
            def getsockname(self):return ('127.0.0.1',19991)
            def getsockopt(self,*args):return 0
            def settimeout(self,value):self.timeout=value
            def connect_ex(self,address):
                assert ('close','reservation')not in events
                self.address=address;events.append(('probe',address));return refused_errno
        reservation=Socket('reservation');first=Socket('first');last=Socket('last')
        before={'https_state':'ready','certificate':{'sha256':'original-public-leaf',
          'not_after':(datetime.now(timezone.utc)+timedelta(seconds=90)).isoformat()},'last_error':None}
        def mutate(op,*,patch):
            self.assertEqual(events[-1],('close','first'))
            self.assertEqual(patch,{'tls':{'acme':{'directory_url':'https://127.0.0.1:19991/dir','order_timeout_ms':5000}}})
            self.assertNotIn(('close','reservation'),events)
            return {'config_revision':9},{}
        admin=SimpleNamespace(api=Mock(return_value=before),mutate=Mock(side_effect=mutate));self.last_admin=admin;secure=Mock()
        secure.request.return_value=(200,{}, {})
        def settle(a,b,expected,revision):
            self.assertEqual(expected,'ACME_ORDER_TIMEOUT');self.assertEqual(revision,9)
            self.assertNotIn(('close','reservation'),events);events.append(('settled',True))
            return {'last_error':{'code':'ACME_ORDER_TIMEOUT'}}
        with patch.object(module.socket,'socket',side_effect=[reservation,first,last]),patch.object(module,'wait_failure',side_effect=settle)as wait:
            result=module.directory_connection_refusal(admin,secure)
        self.assertEqual(result['initial_refusal_errno'],errno.ECONNREFUSED)
        self.assertEqual(result['final_refusal_errno'],errno.ECONNREFUSED)
        self.assertEqual(events[-1],('close','reservation'))
        self.assertEqual(first.address,('127.0.0.1',19991));self.assertEqual(last.address,first.address)
        # No seconds override: actual unchanged wait_failure default remains30.
        self.assertEqual(wait.call_args.kwargs,{})
        return admin

    def test_actual_ipv4_refusal_premise_and5s_order_preserve30s_observation(self):self.exercise()

    def test_nonrefusal_premise_fails_before_any_mutation(self):
        with self.assertRaisesRegex(AssertionError,'must actually refuse'):self.exercise(refused_errno=0)
        self.last_admin.mutate.assert_not_called()

if __name__=='__main__':unittest.main()
