"""Pure recorded-identity cleanup controls; no actual process signals or starts."""
import unittest
from unittest.mock import patch
from acme_process_observer import Descendants


class ObserverChecks(unittest.TestCase):
    def test_reused_pid_is_not_our_process_and_never_signalled(self):
        observer=Descendants(11,'old')
        observer.rows[(22,'known')]={'pid':22,'start_ticks':'known'}
        with patch('acme_process_observer.identity',return_value={'pid':22,'start_ticks':'foreign'}),patch('acme_process_observer.os.kill')as kill:
            observer.close()
        kill.assert_not_called()
        self.assertTrue(observer.evidence()['rows'][0]['original_identity_absent'])

    def test_live_observed_child_failure_stays_failure_after_emergency_cleanup(self):
        observer=Descendants(11,'old')
        observer.rows[(22,'known')]={'pid':22,'start_ticks':'known'}
        clock=iter([0,6,7])
        with patch('acme_process_observer.time.monotonic',side_effect=lambda:next(clock)),patch('acme_process_observer.same',side_effect=[True,True,True,False]),patch('acme_process_observer.os.pidfd_open',return_value=10),patch('acme_process_observer.os.close'),patch('acme_process_observer.signal.pidfd_send_signal')as kill:
            with self.assertRaises(AssertionError):observer.close()
        kill.assert_called_once_with(10,__import__('signal').SIGKILL)
        self.assertTrue(observer.evidence()['rows'][0]['emergency_own_pid_kill'])


if __name__=='__main__':unittest.main()
