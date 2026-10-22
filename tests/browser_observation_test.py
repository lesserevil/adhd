"""Pure observer attribution tests: no browser, hub, socket or provider."""
import unittest
from types import SimpleNamespace

from browser_observation import BrowserObservation


class Page:
    def on(self,event,callback):pass


def request(op='retrieval_index',project='red',**extra):
    return SimpleNamespace(url='http://127.0.0.1:123/admin/api',method='POST',
        post_data_json={'op':op,'project_id':project},failure=None,**extra)


class Observation(unittest.TestCase):
    def observer(self):return BrowserObservation(Page(),'http://127.0.0.1:123')
    def test_exact_observed_denial_and_console(self):
        value=self.observer();actual=request();value.allow(actual,op='retrieval_index',project='red',status=403)
        value.responses=[(actual,403)]
        value.console=[('Failed to load resource: the server responded with a status of 403 (Forbidden)',{'url':actual.url})]
        self.assertEqual(value.check()['expected_http_observed'],1)
    def test_same_url_different_request_never_allowed(self):
        value=self.observer();value.allow(request(),op='retrieval_index',status=403)
        value.responses=[(request(),403)]
        with self.assertRaises(AssertionError):value.check()
    def test_allowance_validates_operation_scope_method_path(self):
        for attribute,bad in [('method','GET'),('url','http://127.0.0.1:123/admin/session')]:
            value=self.observer();actual=request();setattr(actual,attribute,bad)
            with self.assertRaises(AssertionError):value.allow(actual,op='retrieval_index',status=403)
        with self.assertRaises(AssertionError):self.observer().allow(request(),op='config_validate',status=403)
        with self.assertRaises(AssertionError):self.observer().allow(request(),op='retrieval_index',project='blue',status=403)
    def test_abort_requires_exact_request_and_exact_failure(self):
        actual=request();value=self.observer();value.allow(actual,op='retrieval_index',aborted=True)
        value.failed=[(actual,'net::ERR_ABORTED')];self.assertEqual(value.check()['expected_aborts_observed'],1)
        for failed in [(request(),'net::ERR_ABORTED'),(actual,'net::ERR_CONNECTION_REFUSED')]:
            value.failed=[failed]
            with self.assertRaises(AssertionError):value.check()
    def test_unobserved_wrong_url_duplicate_or_other_console_rejected(self):
        for statuses,console in [([], [('Failed to load resource: the server responded with a status of 403 (Forbidden)',{'url':'http://127.0.0.1:123/admin/api'})]),
            ([403],[('Failed to load resource: the server responded with a status of 403 (Forbidden)',{'url':'http://127.0.0.1:123/other'})]),
            ([403],[('Failed to load resource: the server responded with a status of 403 (Forbidden)',{'url':'http://127.0.0.1:123/admin/api'})]*2),
            ([403],[('arbitrary console failure',{'url':'http://127.0.0.1:123/admin/api'})])]:
            actual=request();value=self.observer();value.allow(actual,op='retrieval_index',status=403)
            value.responses=[(actual,status) for status in statuses];value.console=console
            with self.assertRaises(AssertionError):value.check()
    def test_pageerrors_and_wrong_status_rejected(self):
        value=self.observer();actual=request();value.allow(actual,op='retrieval_index',status=403)
        value.responses=[(actual,401)]
        with self.assertRaises(AssertionError):value.check()
        value.responses=[];value.errors=['uncaught']
        with self.assertRaises(AssertionError):value.check()


if __name__=='__main__':unittest.main(verbosity=2)
