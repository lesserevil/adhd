"""Premise guards only; no runtime/proxy/socket starts."""
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import Mock,patch
from acme_fault_cases import prior_valid,wait_failure


def status():
    return {'https_state':'ready','certificate':{'sha256':'a'*64,'not_after':(datetime.now(timezone.utc)+timedelta(seconds=80)).isoformat()},
            'last_error':None,'last_attempt_at':'old','config_revision':7}


class FaultChecks(unittest.TestCase):
    def test_prior_certificate_premise_not_silently_waived(self):
        good=status();self.assertEqual(prior_valid(good),'a'*64)
        for bad in ({**good,'https_state':'expired'}, {**good,'last_error':{'code':'ACME_PROCESS'}},
                    {**good,'certificate':{**good['certificate'],'not_after':datetime.now(timezone.utc).isoformat()}}):
            with self.assertRaises(AssertionError):prior_valid(bad)

    def test_failure_requires_actual_new_attempt_typed_error_and_same_leaf(self):
        before=status();after={**before,'last_attempt_at':'old','last_error':{'code':'ACME_AUTHORIZATION'},
                               'config_revision':8,'acme_state':'backoff','next_attempt_at':'future'}
        admin=Mock();admin.api.return_value=after
        self.assertEqual(wait_failure(admin,before,'ACME_AUTHORIZATION',8),after)
        for bad in ({**after,'last_error':{'code':'ACME_PROCESS'}},
                    {**after,'certificate':{**before['certificate'],'sha256':'b'*64}},
                    {**after,'config_revision':7}):
            admin.api.return_value=bad
            with self.assertRaises(AssertionError):wait_failure(admin,before,'ACME_AUTHORIZATION',8)


if __name__=='__main__':unittest.main()
