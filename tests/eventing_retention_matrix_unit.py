"""Metadata and partial cleanup proofs only; never starts an application."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import hashlib
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import eventing_retention_matrix as m

class Guards(unittest.TestCase):
    def test_changed_frozen_base_rejected_before_import(self):
        with tempfile.TemporaryDirectory()as name:
            root=Path(name);driver=root/'driver.py';driver.write_bytes(Path(m.__file__).read_bytes())
            folder=root/'frozen/tests';folder.mkdir(parents=True);marker=root/'IMPORTED'
            selected=folder/'eventing_readiness_matrix.py';selected.write_text('from pathlib import Path;Path('+repr(str(marker))+').touch()')
            plan={'schema':m.SCHEMA,'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),'frozen':{'files':{'tests/eventing_readiness_matrix.py':'0'*64}}}
            (root/'plan.json').write_text(json.dumps(plan))
            child=subprocess.run([sys.executable,'-I','-B',str(driver),'verify','--work',str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(child.returncode,0);self.assertFalse(marker.exists());self.assertIn(b'AssertionError',child.stderr)
    def test_missing_actual_receipt_is_not_an_admission(self):
        with tempfile.TemporaryDirectory()as name:
            p=Path(name);(p/'export').write_bytes(b'candidate')
            with self.assertRaises(FileNotFoundError):m.base.validate_official(p/'export',p/'missing',p/'receipt')
    def test_full_file_set_rejects_extra_or_symlink(self):
        with tempfile.TemporaryDirectory()as name:
            p=Path(name);(p/'a').write_bytes(b'a');expected=m.base.inventory(p)
            (p/'extra').write_bytes(b'changed');self.assertNotEqual(m.base.inventory(p),expected)
            (p/'extra').unlink();(p/'link').symlink_to(p/'a')
            with self.assertRaises(AssertionError):m.base.inventory(p)
    def test_once_marker_is_exclusive(self):
        with tempfile.TemporaryDirectory()as name:
            p=Path(name)/'started.json';m.base.claim(p)
            with self.assertRaises(FileExistsError):m.base.claim(p)
    def test_partial_report_remains_partial_and_identity_checked(self):
        with tempfile.TemporaryDirectory()as name:
            p=Path(name)/'report.json';p.write_text(json.dumps({'suite':'adhd/eventing-retention-recovery@1','checks':[],
                'native_runtime_cases':[{'pid':999999999,'start_ticks':1,'reaped':True}],
                'proxy_cleanup':{'handlers':0,'thread_alive':False,'failures':[]},'cleanup_failure_types':[]}))
            _,r=m.observations(p);self.assertEqual(r['whole_passed'],[]);self.assertEqual(r['unrun'],m.CHECKS)
            self.assertTrue(r['reported_cleanup_verified']);self.assertTrue(r['native_identity_absence'][0]['same_identity_absent'])
    def test_false_named_check_is_not_a_whole_pass(self):
        with tempfile.TemporaryDirectory()as name:
            p=Path(name)/'report.json';p.write_text(json.dumps({'suite':'adhd/eventing-retention-recovery@1','checks':[{'name':m.CHECKS[0],'passed':False}]}))
            with self.assertRaises(AssertionError):m.observations(p)
    def test_report_cannot_skip_to_last_check(self):
        with tempfile.TemporaryDirectory()as name:
            p=Path(name)/'report.json';p.write_text(json.dumps({'suite':'adhd/eventing-retention-recovery@1','checks':[{'name':m.CHECKS[-1]}]}))
            with self.assertRaises(AssertionError):m.observations(p)
if __name__=='__main__':unittest.main()
