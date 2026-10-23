"""Pure request observer tests: no network, issuer or VM starts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from acme_diagnostic import StatusRecorder

class Checks(unittest.TestCase):
    def test_original_call_result_and_exception_identity_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'requests';rec=StatusRecorder(p)
            client=object();data={'op':'tls_status','private':'never-record'}
            result=(200,{'secret':'never-record'},object());original=Mock(return_value=result)
            self.assertIs(rec.invoke(original,client,'/admin/api',data,timeout=5),result)
            original.assert_called_once_with(client,'/admin/api',data,timeout=5)
            failure=TimeoutError('private original error')
            original=Mock(side_effect=failure)
            with self.assertRaises(TimeoutError) as caught:rec.invoke(original,client,'/admin/api',data)
            self.assertIs(caught.exception,failure);self.assertEqual(original.call_count,1)
            raw=p.read_text();self.assertNotIn('never-record',raw);self.assertNotIn('private original',raw)
            rows=[json.loads(x)for x in raw.splitlines()]
            self.assertEqual([x['event']for x in rows],['start','end','start','end'])
            self.assertEqual(rows[-1]['exception_type'],'TimeoutError')
            rec.close()

    def test_nonstatus_unchanged_and_observer_failure_not_app_failure(self):
        with tempfile.TemporaryDirectory() as d:
            rec=StatusRecorder(Path(d)/'requests');result=(503,{},None);original=Mock(return_value=result)
            self.assertIs(rec.invoke(original,object(),'/health',timeout=1),result)
            self.assertEqual(rec.used,0)
            with patch('acme_diagnostic.os.write',side_effect=OSError('fault')):
                self.assertIs(rec.invoke(original,object(),'/admin/api',{'op':'tls_status'}),result)
            self.assertTrue(rec.failed);rec.close()

    def test_byte_cap_preserves_original_request(self):
        with tempfile.TemporaryDirectory() as d:
            rec=StatusRecorder(Path(d)/'requests');rec.used=1_048_576
            original=Mock(return_value=(200,{},None))
            rec.invoke(original,object(),'/admin/api',{'op':'tls_status'})
            original.assert_called_once();self.assertTrue(rec.failed)
            self.assertEqual((Path(d)/'requests').stat().st_size,0);rec.close()
