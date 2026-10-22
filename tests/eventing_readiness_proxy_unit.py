"""Pure declared-fault/selection tests; never start HTTP, broker, VM or model."""
import ast
import importlib.util
import json
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('readiness_proxy',Path(__file__).with_name('eventing_readiness_proxy.py'));p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
class Faults(unittest.TestCase):
    def test_exact_topic_only(self):
        self.assertEqual(p.classify('/v3/clusters/x/topics/own/configs','own'),'configs')
        self.assertEqual(p.classify('/topics/own/partitions/0/offsets','own'),'offsets')
        self.assertIsNone(p.classify('/v3/clusters/x/topics/own-other/configs','own'))
        self.assertIsNone(p.classify('/v3/clusters/x/topics/other/configs','own'))
    def test_creation_visibility_has_fixed_end(self):
        for n in [1,2]:self.assertEqual(p.fault_response('lag','configs',200,b'valid',n,True)[0],404)
        self.assertEqual(p.fault_response('lag','configs',200,b'valid',3,True),(200,b'valid',False))
        self.assertEqual(p.fault_response('lag','configs',403,b'denied',1,False),(403,b'denied',False))
    def test_queue_control_same_fixed_lag(self):
        for n in [1,20,21]:self.assertEqual(p.fault_response('queue','configs',200,b'valid',n,True),p.fault_response('queue-control','configs',200,b'valid',n,True))
    def test_nontransient_and_float_fault_bytes(self):
        self.assertEqual(p.fault_response('forbidden','configs',200,b'valid',1,True)[0],403)
        self.assertEqual(p.fault_response('server-error','configs',200,b'valid',1,True)[0],500)
        status,body,changed=p.fault_response('offset-float','offsets',200,b'{}',1,True)
        self.assertEqual(status,200);self.assertTrue(changed);self.assertIs(type(json.loads(body)['beginning_offset']),float)
    def test_wrong_topology_and_cleanup(self):
        _,body,_=p.fault_response('duplicate-bad-topology','metadata',200,b'{"partitions_count":1}',1,True)
        self.assertEqual(json.loads(body)['partitions_count'],2)
        _,body,_=p.fault_response('bad-cleanup','configs',200,b'{"data":[{"name":"cleanup.policy","value":"delete"}]}',1,True)
        self.assertEqual(json.loads(body)['data'][0]['value'],'compact')
    def test_malformed_retention_and_partition_float_are_exact(self):
        original=b'{"data":[{"name":"retention.ms","value":"604800000"},{"name":"cleanup.policy","value":"delete"}]}'
        for mode in ['retention-missing','retention-float','retention-negative','retention-duplicate']:
            status,body,changed=p.fault_response(mode,'configs',200,original,1,True)
            self.assertEqual(status,200);self.assertTrue(changed);self.assertNotEqual(body,original)
        _,body,_=p.fault_response('partitions-float','metadata',200,b'{"partitions_count":1}',1,True)
        self.assertIs(type(json.loads(body)['partitions_count']),float)
    def test_python_sources_parse_without_importing_application_dependencies(self):
        ast.parse(Path(__file__).with_name('eventing_readiness_faults.py').read_text())
        ast.parse(Path(__file__).with_name('eventing_readiness_proxy.py').read_text())
if __name__=='__main__':unittest.main()
