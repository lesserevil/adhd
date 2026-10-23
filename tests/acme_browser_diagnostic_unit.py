"""Pure public normalization and static failure-location privacy guards."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import acme_browser
from acme_image_browser import normalized_tls

class BrowserDiagnosticChecks(unittest.TestCase):
    def fixture(self):
        requested={'enabled':True,'port':18443,'acme':{'enabled':True,'retry_seconds':30,'ca_cert_file':'directory-root.pem'}}
        actual=copy.deepcopy(requested);actual['acme']['ca_cert_file']='/owned/hub/directory-root.pem'
        session=SimpleNamespace(tls=requested,hub=Path('/owned/hub'),admin=SimpleNamespace(api=Mock(return_value={'config':{'tls':actual}})))
        return session,actual

    def test_only_exact_ca_path_normalization_is_allowed(self):
        session,actual=self.fixture();self.assertEqual(normalized_tls(session),actual)
        session.admin.api.assert_called_once_with({'op':'config_get'})
        self.assertEqual(session.tls['acme']['ca_cert_file'],'directory-root.pem')
        for change in [('port',18444),('ca_cert_file','/foreign/root.pem'),('retry_seconds',31)]:
            session,actual=self.fixture();name,value=change
            (actual if name=='port'else actual['acme'])[name]=value
            with self.assertRaises(AssertionError):normalized_tls(session)

    def test_failure_location_retains_line_without_private_error_or_locals(self):
        namespace={};source='def known_hook():\n    private_value="PRIVATE_SECRET"\n    raise AssertionError("PRIVATE_URL_AND_SECRET")\n'
        exec(compile(source,acme_browser.__file__,'exec'),namespace)
        try:namespace['known_hook']()
        except AssertionError as error:rows=acme_browser.failure_locations(error)
        self.assertEqual(rows,[{'function':'known_hook','line':3}])
        raw=json.dumps(rows)
        for secret in ['PRIVATE_SECRET','PRIVATE_URL_AND_SECRET','private_value','AssertionError',acme_browser.__file__]:self.assertNotIn(secret,raw)

if __name__=='__main__':unittest.main()
