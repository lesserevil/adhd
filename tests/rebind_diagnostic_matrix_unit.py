"""Failure guards execute no processes and preserve the once marker."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import rebind_diagnostic_matrix as m


class GuardTests(unittest.TestCase):
    def test_missing_or_modified_plan_rejects_before_import_or_start(self):
        with tempfile.TemporaryDirectory()as d:
            work=Path(d)
            with patch.object(m,'verify')as verify,patch.object(m.subprocess,'Popen')as popen:
                with self.assertRaises(FileNotFoundError):m.preflight(work,'0'*64)
                (work/'plan.json').write_text('{}')
                with self.assertRaises(AssertionError):m.preflight(work,'0'*64)
                verify.assert_not_called();popen.assert_not_called()

    def test_changed_binding_rejects_before_parent_import_or_start(self):
        with tempfile.TemporaryDirectory()as d:
            work=Path(d);(work/'driver.py').write_bytes(Path(m.__file__).read_bytes())
            (work/'rebind-plan.json').write_text('{}')
            plan={'driver_sha256':m.sha(work/'driver.py'),'metadata_root':str(work),
                  'shared_inputs':{},'cases':[{'name':'rebind','plan_file':'rebind-plan.json','plan_sha256':'0'*64},{'name':'rebind-hostile'}]}
            with patch.object(m,'verify_parent')as parent,patch.object(m.subprocess,'Popen')as popen:
                with self.assertRaises(AssertionError):m.verify(work,plan)
                parent.assert_not_called();popen.assert_not_called()

    def test_existing_once_refuses_without_child(self):
        with tempfile.TemporaryDirectory()as d:
            work=Path(d);(work/'plan.json').write_text('{}');m.durable(work/'execution.started',{'original':True})
            original=(work/'execution.started').read_bytes()
            with patch.object(m,'verify',return_value=object()),patch.object(m.subprocess,'Popen')as popen:
                with self.assertRaises(AssertionError):m.preflight(work,m.sha(work/'plan.json'))
                with self.assertRaises(FileExistsError):m.durable(work/'execution.started',{})
                popen.assert_not_called()
            self.assertEqual(original,(work/'execution.started').read_bytes())


if __name__=='__main__':unittest.main()
