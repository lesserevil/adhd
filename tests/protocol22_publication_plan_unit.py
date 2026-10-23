"""Pure preparation/receipt/history guards; no runtime or export invocation."""
import argparse
import ast
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('publication',Path(__file__).with_name('protocol22_publication_plan.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Guards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
    def args(self, **kw):
        return argparse.Namespace(**{**dict.fromkeys(m.TARGET_ARGS),**kw})
    def target(self):
        artifact=self.root/'artifact';artifact.write_bytes(b'actual accepted fixture bytes')
        receipt={'schema':'urn:literate-ai:schema:v1:project-test-receipt-finalized-candidate',
                 'receipt':{'schema':'urn:literate-ai:schema:v1:project-test-receipt','result':'sha256:result','project_revision':'sha256:authority'},'lifecycle_request_identity':'sha256:request'}
        receipt['receipt_identity']='sha256:'+m.sha(m.canonical(receipt['receipt']))
        build={'command':'rebuild','ok':True,'result':{'artifact':str(artifact),'passed':True,'receipt_committed':True,
               'receipt_identity':receipt['receipt_identity'],'receipt_update':{'updated':True,'identity':receipt['receipt_identity']},
               'lifecycle_request_identity':'sha256:request','lifecycle_result_identity':'sha256:result','project_revision_identity':'sha256:authority'}}
        args=self.args(accepted_artifact=str(artifact),artifact_sha256=m.sha(artifact.read_bytes()),receipt=str(self.root/'receipt.json'),rebuild=str(self.root/'rebuild.json'))
        self.write_target(args,receipt,build);return args,receipt,build
    def write_target(self,args,receipt,build):
        for key,value in [('receipt',receipt),('rebuild',build)]:
            raw=m.canonical(value);Path(getattr(args,key)).write_bytes(raw);setattr(args,key+'_sha256',m.sha(raw))
    def test_null_target_and_partial_rejected_before_read(self):
        self.assertIsNone(m.target_binding(self.args()))
        with patch.object(m,'read',side_effect=AssertionError('Must not read')) as read:
            with self.assertRaisesRegex(AssertionError,'must be complete'):m.target_binding(self.args(artifact_sha256='a'*64))
            read.assert_not_called()
    def test_actual_target_receipt_chain_no_export_claim(self):
        args,_,_=self.target();target=m.target_binding(args)
        self.assertEqual(target['artifact_sha256'],args.artifact_sha256)
        self.assertFalse(target['profile22_export_verified'])
    def test_receipt_failures_not_declared_accepted(self):
        args,receipt,build=self.target()
        changes=[lambda b:b['result'].update(passed=1),lambda b:b['result'].update(receipt_committed=False),
                 lambda b:b['result']['receipt_update'].update(updated=False),lambda b:b['result'].update(lifecycle_result_identity='wrong'),
                 lambda b:b['result'].update(receipt_identity='wrong')]
        for change in changes:
            bad=copy.deepcopy(build);change(bad);self.write_target(args,receipt,bad)
            with self.assertRaises(AssertionError):m.target_binding(args)
        self.write_target(args,receipt,build);args.receipt_sha256='0'*64
        with self.assertRaises(AssertionError):m.target_binding(args)
    def test_formal_artifact_bytes_must_equal_selected(self):
        args,receipt,build=self.target();other=self.root/'other';other.write_bytes(b'wrong')
        build['result']['artifact']=str(other);self.write_target(args,receipt,build)
        with self.assertRaises(AssertionError):m.target_binding(args)
    def test_scope_inventory_only_three_globals_and_minor_version(self):
        before={'schema':'adhd/operation-scopes@1','application_profile':'2.1.0','agent':{'x':'project'},'admin':{'y':'project'},'configuration':{'z':'global'},'project_settings':{'q':'local'},'peer':{'old':['unchanged','order']}}
        after=m.scopes22(m.canonical(before));self.assertEqual(after['application_profile'],'2.2.0')
        self.assertEqual(after['admin'].pop('tls_status'),'server');self.assertEqual(after['admin'].pop('tls_renew'),'server')
        self.assertEqual(after['configuration'].pop('tls'),'server');after['application_profile']='2.1.0'
        self.assertEqual(after,before)
    def test_fresh_preparation_preserves_history_no_execution_mode(self):
        root=self.root/'repo';root.mkdir();docs=root/'docs/protocol';docs.mkdir(parents=True)
        original={'schema.json':b'{"$id":"urn:adhd:protocol:2.1"}', 'openapi.json':b'{"info":{"version":"2.1.0"}}',
                  'scopes.json':m.canonical({'schema':'adhd/operation-scopes@1','application_profile':'2.1.0','admin':{},'configuration':{},'project_settings':{}}),
                  'v2.0/schema.json':b'IMMUTABLE OLD V20', 'README.md':b'historical index'}
        for name,raw in original.items():p=docs/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        for name in m.HELPERS:p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'bound helper only')
        baseline={}
        for name in ('schema','openapi'):
            path=root/(name+'-baseline.json');raw=m.canonical({'$defs':{'D'+str(i):{} for i in range(426)}} if name=='schema' else {})
            path.write_bytes(raw);baseline[name]=(path.name,m.sha(raw))
        work=self.root/'work';args=self.args(repo_root=root,work=work)
        with patch.object(m,'BASELINE',baseline):
            result=m.prepare(args)
            with self.assertRaises(AssertionError):m.prepare(args)
        self.assertFalse(result['execution_ready']);plan=json.loads((work/'plan.json').read_bytes());self.assertIsNone(plan['target'])
        for name,raw in original.items():
            self.assertEqual((docs/name).read_bytes(),raw);self.assertEqual((work/'historical/docs/protocol'/name).read_bytes(),raw)
        self.assertIn('["protocol-openapi"]',str(plan['commands']));self.assertNotIn('["protocol-scopes"]',str(plan['commands']))
        self.assertEqual(plan['conservation']['unchanged_old_definitions'],421)
        tree=ast.parse(Path(m.__file__).read_text());self.assertFalse(any(isinstance(n,(ast.Import,ast.ImportFrom)) and 'subprocess' in ast.unparse(n) for n in ast.walk(tree)))
    def test_redirected_file_rejected(self):
        actual=self.root/'real';actual.write_bytes(b'bytes');link=self.root/'link';link.symlink_to(actual)
        with self.assertRaises(AssertionError):m.read(link)

if __name__=='__main__':unittest.main()
