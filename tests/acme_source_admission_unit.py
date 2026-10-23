"""Pure actual-input joins and rejection guards; no lifecycle/runtime starts."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest

import acme_source_admission as m


def ident(char):return {'algorithm':'sha256','digest':char*64}


class AdmissionGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.files={'a.exs':b'# exact UTF8 retained source\n',
          'Makefile':b'SRCS := a.exs\n',
          'tools/assemble.exs':b'files = ~w(a.exs)\nbody = Enum.map_join(files, "\\n", &File.read!(Path.join(root,&1)))\nFile.write!(temp,body)\n',
          'tests/manifest.json':m.canonical({'schema':'urn:literate-ai:schema:v1:generated-test-suite','cases':[{'case_id':str(i)}for i in range(8)]})}
        source=self.root/'source';source.mkdir()
        for name,body in self.files.items():
            p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
        self.source=source;self.artifact=self.root/'artifact';self.artifact.write_bytes(m.assembled(self.files))
        self.plan={'command':'rebuild','ok':True,'result':{'admitted':False,'input':{
          'origin':'operator-retained-source','target':'host','tree_identity':{'algorithm':'sha256','digest':m.tree_identity(self.files)[7:]},
          'component_lock_identity':ident('a'),'project_authority_identity':ident('b')}}}
        self.receipt={'schema':'urn:literate-ai:schema:v1:project-test-receipt-finalized-candidate',
          'lifecycle_request_identity':'sha256:'+'c'*64,'receipt':{
          'schema':'urn:literate-ai:schema:v1:project-test-receipt','result':'sha256:'+'d'*64,'project_revision':'sha256:'+'e'*64}}
        rid='sha256:'+m.sha(m.canonical(self.receipt['receipt']));self.receipt['receipt_identity']=rid
        self.build={'command':'rebuild','ok':True,'result':{'passed':True,'specification':'components/hub',
          'coding_cli':'operator-retained-source','target':'host','component_lock_identity':'sha256:'+'a'*64,
          'project_revision_identity':'sha256:'+'e'*64,'validated_project_authority_identity':'sha256:'+'e'*64,
          'framework_distribution_identity':'sha256:'+'f'*64,'receipt_identity':rid,'receipt_committed':False,
          'receipt_update':None,'candidate_receipt':str(self.root/'receipt.json'),
          'lifecycle_request_identity':self.receipt['lifecycle_request_identity'],'lifecycle_result_identity':self.receipt['receipt']['result'],
          'test_summary':{'failed':0,'passed':8,'skipped':0,'total':8},'artifact':str(self.artifact)}}
        self.oracle={'schema':'literate-ai/component-acceptance-oracle@1','component':'hub',
          'specification_set_identity':'sha256:'+'1'*64,'cases':[{'id':str(i)}for i in range(114)]}
        self.freeze={name:m.sha(body)for name,body in self.files.items()}

    def derive(self,**changes):
        return m.derive(changes.get('plan',self.plan),changes.get('build',self.build),changes.get('receipt',self.receipt),
          changes.get('files',self.files),changes.get('oracle',self.oracle),changes.get('artifact',self.artifact.read_bytes()))

    def test_candidate_provenance_and_configured_inventory_are_distinct(self):
        report=self.derive()
        self.assertEqual(report['receipt_identity'],self.receipt['receipt_identity'])
        self.assertEqual(report['base_authority_identity'],'sha256:'+'b'*64)
        self.assertEqual(report['configured_acceptance']['cases'],114)
        self.assertFalse(report['configured_acceptance']['retained_executed_case_array'])
        self.assertEqual(report['native_test_summary']['passed'],8)

    def test_identity_or_boolean_mismatch_cannot_qualify(self):
        for field in ('receipt_identity','component_lock_identity','project_revision_identity','lifecycle_result_identity','lifecycle_request_identity'):
            bad=copy.deepcopy(self.build);bad['result'][field]='sha256:'+'2'*64
            with self.assertRaises(AssertionError,msg=field):self.derive(build=bad)
        bad=copy.deepcopy(self.build);bad['result']['passed']=1
        with self.assertRaises(AssertionError):self.derive(build=bad)
        bad=copy.deepcopy(self.receipt);bad['receipt']['unjoined']='new'
        with self.assertRaises(AssertionError):self.derive(receipt=bad)

    def test_tree_and_raw_assembly_are_both_verified(self):
        logical=[{'path':'source/'+name,'size':len(body),'digest':'sha256:'+m.sha(body)}for name,body in sorted(self.files.items())]
        self.assertEqual(m.tree_identity(self.files),'sha256:'+m.sha(m.canonical(logical)))
        bad=dict(self.files);bad['a.exs']=b'changed'
        with self.assertRaises(AssertionError):self.derive(files=bad)
        with self.assertRaises(AssertionError):self.derive(artifact=b'different formal output')
        bad=dict(self.files);bad['Makefile']=b'SRCS := different.exs\n'
        with self.assertRaises(AssertionError):m.assembled(bad)

    def test_native_and_oracle_counts_not_invented_or_borrowed(self):
        for count in (7,18):
            bad=copy.deepcopy(self.build);bad['result']['test_summary'].update(passed=count,total=count)
            with self.assertRaises(AssertionError):self.derive(build=bad)
        bad=copy.deepcopy(self.oracle);bad['cases'].pop()
        with self.assertRaises(AssertionError):self.derive(oracle=bad)

    def test_source_exact_file_and_directory_sets_and_redirects(self):
        self.assertEqual(m.source_files(self.source,self.freeze),self.files)
        (self.source/'empty').mkdir()
        with self.assertRaises(AssertionError):m.source_files(self.source,self.freeze)
        (self.source/'empty').rmdir();(self.source/'a.exs').unlink();(self.source/'a.exs').symlink_to(self.artifact)
        with self.assertRaises(AssertionError):m.source_files(self.source,self.freeze)

    def args(self):
        args=argparse.Namespace(retained_source=self.source,artifact_sha256=m.sha(self.artifact.read_bytes()),write=False,output=self.root/'evidence')
        for name,value in [('plan',self.plan),('receipt',self.receipt),('rebuild',self.build),('source_freeze',self.freeze),('oracle',self.oracle)]:
            body=m.canonical(value);path=self.root/(name+'.json');path.write_bytes(body)
            setattr(args,name,path);setattr(args,name+'_sha256',m.sha(body))
        # Rebuild points to the actual receipt path written above.
        return args

    def test_readonly_then_fresh_capture_and_downstream_source_shape(self):
        args=self.args();out=m.capture(args);self.assertTrue(out['passed']);self.assertFalse(args.output.exists())
        args.write=True;m.capture(args)
        report=m.decode((args.output/'manifest.json').read_bytes())
        self.assertFalse(report['runtime_started_here']);self.assertFalse(report['project_current_receipt_verified'])
        self.assertEqual(set(report['files']),{'retained-plan.json','receipt.json','rebuild.json','source-freeze.json','configured-oracle.json'})
        for name,digest in report['files'].items():self.assertEqual(m.sha((args.output/name).read_bytes()),digest)
        self.assertEqual(report['artifact_sha256'],args.artifact_sha256)
        from image_compiled_admission import source_binding
        encoded=(args.output/'manifest.json').read_bytes()
        bound=source_binding(encoded,m.sha(encoded),(args.output/'receipt.json').read_bytes(),
          (args.output/'rebuild.json').read_bytes(),args.artifact_sha256)
        self.assertEqual(bound['receipt_identity'],self.receipt['receipt_identity'])
        with self.assertRaises(AssertionError):m.capture(args)

    def test_candidate_file_and_committed_update_must_be_truthful(self):
        args=self.args();self.build['result']['candidate_receipt']=str(self.root/'different')
        (self.root/'different').write_bytes(b'{}');args=self.args()
        with self.assertRaises(AssertionError):m.capture(args)
        bad=copy.deepcopy(self.build);bad['result'].update(receipt_committed=True,receipt_update={'updated':True,'identity':self.receipt['receipt_identity']})
        self.derive(build=bad)
        bad['result']['receipt_update']['identity']='sha256:'+'3'*64
        with self.assertRaises(AssertionError):self.derive(build=bad)


if __name__=='__main__':unittest.main()
