"""Pure postdecision selection and actual capacity guards, no runtime startup."""
import importlib.util
import json
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('retention_proxy',Path(__file__).with_name('eventing_readiness_proxy.py'))
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
class RetentionFault(unittest.TestCase):
    def test_only_confirmed_selected_config_readback_fails(self):
        for confirmed in (False,True):
            for category in (None,'metadata','alter','offsets','configs'):
                got=p.retention_recovery_fault('retention-recovery',category,200,b'actual',confirmed)
                self.assertEqual(got[2],confirmed and category=='configs')
                if not got[2]:self.assertEqual(got,(200,b'actual',False))
                else:self.assertEqual(got[0],503)
    def test_existing_modes_and_disabled_pass_exact_bytes(self):
        for mode in (None,'lag','queue','queue-control','existing-retention','never'):
            self.assertEqual(p.retention_recovery_fault(mode,'configs',200,b'actual',True),(200,b'actual',False))
    def test_only_selected_topic_classifies(self):
        self.assertEqual(p.classify('/v3/clusters/own/topics/selected/configs','selected'),'configs')
        self.assertIsNone(p.classify('/v3/clusters/own/topics/foreign/configs','selected'))
    def test_actual_success_and_durable_decision_required(self):
        self.assertTrue(p.confirmed_retention_alter('retention-recovery','alter','POST',204,True))
        with self.assertRaises(AssertionError):p.confirmed_retention_alter('retention-recovery','alter','POST',204,False)
        for status in (200,201,400,403,500):
            self.assertFalse(p.confirmed_retention_alter('retention-recovery','alter','POST',status,True))
        for mode,category,method in ((None,'alter','POST'),('lag','alter','POST'),('retention-recovery',None,'POST'),('retention-recovery','configs','POST'),('retention-recovery','alter','GET')):
            self.assertFalse(p.confirmed_retention_alter(mode,category,method,204,True))
if __name__=='__main__':unittest.main()
