"""Pure synthetic archive/metadata and mocked Docker checks. No image is run."""
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tarfile

import image_payload_audit as audit
import image_compiled_admission as admission

IMAGE='sha256:'+'1'*64
CID='2'*64
NAME='adhd-image-audit-unit'


def archive(rows):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w')as tar:
        for name,body,mode,kind in rows:
            item=tarfile.TarInfo(name);item.uid=item.gid=0;item.mode=mode;item.mtime=0;item.type=kind
            item.size=len(body)if item.isfile()else 0
            if item.issym():item.linkname='outside'
            tar.addfile(item,io.BytesIO(body)if item.isfile()else None)
    return output.getvalue()


class Fixture:
    def __init__(self,root):
        self.context=root/'context';self.context.mkdir();self.helpers=root/'helpers';self.helpers.mkdir()
        self.source=('\n'.join('defmodule Unit.N'+str(i)+' do\nend'for i in range(59))+'\n').encode()
        self.source_sha=audit.digest(self.source)
        self.app={'hub.exs':self.source,**{'specification/s'+str(i)+'.json':b'{}'for i in range(33)},**{'f'+str(i):b'fixture'for i in range(25)}}
        assert len(self.app)==59
        (self.context/'Dockerfile').write_bytes(b'unit Dockerfile')
        self.manifest={'schema':'adhd/container-inputs@1','files':{n:audit.digest(v)for n,v in self.app.items()}}
        self.manifest['files']['Dockerfile']=audit.digest(b'unit Dockerfile')
        self.manifest_bytes=json.dumps(self.manifest).encode();(self.context/'manifest.json').write_bytes(self.manifest_bytes)
        self.context_sha=audit.digest(self.manifest_bytes)
        for n in ('boot','build'):(self.helpers/(n+'.exs')).write_bytes((n+' fixture').encode())
        self.inputs=b'{"synthetic":"never executed"}';(self.context/'compiler-inputs.json').write_bytes(self.inputs)
        self.names=['Elixir.Unit.N'+str(i)for i in range(59)]
        self.cache={'adhd':None,'adhd/ebin':None,'adhd/inputs.json':self.inputs,
                    **{'adhd/'+n+'.exs':(self.helpers/(n+'.exs')).read_bytes()for n in ('boot','build')},
                    **{'adhd/ebin/'+n+'.beam':('not a BEAM: '+n).encode()for n in self.names}}
        self.cm={'source_sha256':self.source_sha,'payload_manifest_sha256':self.context_sha,'modules':self.names,
                 'beams':{n+'.beam':audit.digest(self.cache['adhd/ebin/'+n+'.beam'])for n in self.names},
                 'inputs_sha256':audit.digest(self.inputs),**{n+'_sha256':audit.digest(self.cache['adhd/'+n+'.exs'])for n in ('boot','build')}}
        self.cache['adhd/manifest.json']=json.dumps(self.cm).encode()
        self.binding={'compiler_inputs_sha256':audit.digest(self.inputs),'packaging_files_sha256':{n+'.exs':self.cm[n+'_sha256']for n in ('boot','build')}}
    def app_archive(self):return archive([(n,b,0o644,tarfile.REGTYPE)for n,b in {**self.app,'manifest.json':self.manifest_bytes}.items()])
    def cache_archive(self):return archive([(n,b or b'',0o555 if b is None else 0o444,tarfile.DIRTYPE if b is None else tarfile.REGTYPE)for n,b in self.cache.items()])
    def runtime_archive(self):return archive([('runtime',b'',0o755,tarfile.DIRTYPE)])
    def inspect(self):
        with patch.object(audit,'compiled_context',return_value=self.binding):
            return audit.inspect_payload(self.app_archive(),self.cache_archive(),self.runtime_archive(),self.context,self.source_sha,self.helpers)


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.f=Fixture(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_complete_byte_graph_and_modes(self):
        result=self.f.inspect();self.assertEqual((result['actual_app_files'],result['canonical_specifications'],result['cache_modules'],result['cache_entries']),(59,33,59,65))
        self.assertEqual(len(result['cache_metadata']),66)
    def test_wrong_expected_source_rejects(self):
        with self.assertRaises(AssertionError),patch.object(audit,'compiled_context',return_value=self.f.binding):audit.inspect_payload(self.f.app_archive(),self.f.cache_archive(),self.f.runtime_archive(),self.f.context,'f'*64,self.f.helpers)
    def test_app_symlink_rejects(self):
        body=archive([('foreign',b'',0o644,tarfile.SYMTYPE)])
        with self.assertRaises(AssertionError),patch.object(audit,'compiled_context',return_value=self.f.binding):audit.inspect_payload(body,self.f.cache_archive(),self.f.runtime_archive(),self.f.context,self.f.source_sha,self.f.helpers)
    def test_duplicate_cache_member_rejects(self):
        body=archive([('adhd',b'',0o555,tarfile.DIRTYPE)]*2)
        with self.assertRaises(AssertionError),patch.object(audit,'compiled_context',return_value=self.f.binding):audit.inspect_payload(self.f.app_archive(),body,self.f.runtime_archive(),self.f.context,self.f.source_sha,self.f.helpers)
    def test_changed_beam_rejects(self):
        self.f.cache['adhd/ebin/'+self.f.names[0]+'.beam']=b'drift'
        with self.assertRaises(AssertionError):self.f.inspect()
    def test_changed_helper_rejects(self):
        (self.f.helpers/'boot.exs').write_bytes(b'drift')
        with self.assertRaises(AssertionError):self.f.inspect()
    def test_cache_writable_mode_rejects(self):
        body=archive([('adhd',b'',0o755,tarfile.DIRTYPE)])
        with self.assertRaises(AssertionError),patch.object(audit,'compiled_context',return_value=self.f.binding):audit.inspect_payload(self.f.app_archive(),body,self.f.runtime_archive(),self.f.context,self.f.source_sha,self.f.helpers)
    def test_regular_denies_symlink(self):
        p=self.root/'redirect';p.symlink_to(self.f.context/'manifest.json')
        with self.assertRaises(AssertionError):audit.regular(p)
    def test_execute_primary_survives_cleanup_failure(self):
        args=SimpleNamespace(image=IMAGE,artifact_sha256=self.f.source_sha,context_sha256=self.f.context_sha,context=self.f.context,runtime_helpers=self.f.helpers,output=self.root/'out')
        error=ValueError('primary')
        class Fake:
            def checked(self,argv):raise error
        with patch.object(audit,'compiled_context',return_value=self.f.binding),patch.object(audit,'cleanup',return_value={'observed_absent':False,'failure_types':['daemon']}):
            with self.assertRaises(ValueError)as caught:audit.execute(args,Fake())
        self.assertIs(caught.exception,error);report=json.loads((args.output/'image-payload.json').read_bytes());self.assertFalse(report['passed']);self.assertEqual(report['failure_type'],'ValueError')
    def test_malformed_create_id_uses_issued_name_cleanup_only(self):
        args=SimpleNamespace(image=IMAGE,artifact_sha256=self.f.source_sha,context_sha256=self.f.context_sha,context=self.f.context,runtime_helpers=self.f.helpers,output=self.root/'out')
        calls=[]
        class Fake:
            def checked(self,argv):
                assert argv[0]=='create'
                return b'malformed-container-id\n'
            def run(self,argv):
                calls.append(argv)
                assert argv[0]=='inspect' and argv[-1].startswith('adhd-image-audit-')
                return subprocess.CompletedProcess(argv,1,b'[]',('Error: No such object: '+argv[-1]).encode())
        with patch.object(audit,'compiled_context',return_value=self.f.binding):
            with self.assertRaisesRegex(AssertionError,'Malformed create container ID'):
                audit.execute(args,Fake())
        report=json.loads((args.output/'image-payload.json').read_bytes())
        self.assertFalse(report['passed']);self.assertTrue(report['owned_container_absent'])
        self.assertEqual(report['failure_type'],'AssertionError');self.assertNotIn('audit_container_id',report)
        self.assertIsNone(report['cleanup']['container_id']);self.assertTrue(calls)
        self.assertFalse(any('malformed-container-id'in v for call in calls for v in call))
    def test_execute_synthetic_valid_archive_cleanup_failure_is_false(self):
        f=self.f
        class Fake:
            def checked(self,argv):
                if argv[0]=='create':return CID.encode()
                if argv[0]=='inspect':return json.dumps([{'Image':IMAGE,'Name':'/'+audit_name[0],'Id':CID,'State':{'Status':'created','Running':False}}]).encode()
                return {'/app/.':f.app_archive(),'/runtime/adhd':f.cache_archive(),'/runtime':f.runtime_archive()}[argv[1].split(':',1)[1]]
        args=SimpleNamespace(image=IMAGE,artifact_sha256=f.source_sha,context_sha256=f.context_sha,context=f.context,runtime_helpers=f.helpers,output=self.root/'out')
        audit_name=['adhd-image-audit-'+'a'*16]
        with patch.object(audit,'uuid4',return_value=SimpleNamespace(hex='a'*32)),patch.object(audit,'compiled_context',return_value=f.binding),patch.object(audit,'cleanup',return_value={'observed_absent':True,'failure_types':['unknown']}):
            with self.assertRaises(AssertionError):audit.execute(args,Fake())
        self.assertFalse(json.loads((args.output/'image-payload.json').read_bytes())['passed'])


class CleanupTests(unittest.TestCase):
    def test_absent_before_create(self):
        class Fake:
            def run(self,argv):return subprocess.CompletedProcess(argv,1,b'[]',('Error: No such object: '+argv[-1]).encode())
        r=audit.cleanup(Fake(),IMAGE,NAME,None);self.assertTrue(r['observed_absent']);self.assertFalse(r['failure_types'])
    def test_daemon_error_independent_known_id_cleanup_still_false(self):
        calls=[]
        class Fake:
            def run(self,argv):
                calls.append(argv)
                if len(calls)==1:return subprocess.CompletedProcess(argv,1,b'',b'daemon unavailable')
                if argv[0]=='rm':return subprocess.CompletedProcess(argv,0,b'',b'')
                return subprocess.CompletedProcess(argv,1,b'',('Error: No such object: '+argv[-1]).encode())
        r=audit.cleanup(Fake(),IMAGE,NAME,CID);self.assertTrue(r['observed_absent']);self.assertTrue(r['failure_types']);self.assertIn(['rm','--force',CID],calls)
    def test_foreign_identity_never_removed(self):
        calls=[]
        class Fake:
            def run(self,argv):
                calls.append(argv);return subprocess.CompletedProcess(argv,0,json.dumps([{'Image':'foreign','Name':'/'+NAME,'Id':CID}]).encode(),b'')
        r=audit.cleanup(Fake(),IMAGE,NAME,CID);self.assertTrue(r['foreign_identity']);self.assertFalse(any(v[0]=='rm'for v in calls))


def source_fixture(artifact):
    identity='sha256:'+'a'*64
    receipt={'receipt_identity':identity,'lifecycle_request_identity':'request','receipt':{'result':'result'}}
    rebuild={'command':'rebuild','ok':True,'result':{'passed':True,'specification':'components/hub','receipt_identity':identity,'lifecycle_result_identity':'result','lifecycle_request_identity':'request'}}
    rb=json.dumps(receipt).encode();bb=json.dumps(rebuild).encode()
    source={'passed':True,'artifact_sha256':artifact,'files':{'receipt.json':audit.digest(rb),'rebuild.json':audit.digest(bb)},**{k:identity for k in admission.PROVENANCE}}
    sb=json.dumps(source).encode();return sb,rb,bb


class AdmissionTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.f=Fixture(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_actual_receipt_and_rebuild_crossbinding(self):
        s,r,b=source_fixture(self.f.source_sha);self.assertTrue(admission.source_binding(s,audit.digest(s),r,b,self.f.source_sha)['passed'])
    def test_stale_receipt_refused(self):
        s,r,b=source_fixture(self.f.source_sha)
        with self.assertRaises(AssertionError):admission.source_binding(s,audit.digest(s),r+b' ',b,self.f.source_sha)
    def test_wrong_rebuild_lifecycle_refused_even_with_updated_file_hash(self):
        s,r,b=source_fixture(self.f.source_sha);source=json.loads(s);body=json.loads(b);body['result']['lifecycle_result_identity']='wrong';b=json.dumps(body).encode();source['files']['rebuild.json']=audit.digest(b);s=json.dumps(source).encode()
        with self.assertRaises(AssertionError):admission.source_binding(s,audit.digest(s),r,b,self.f.source_sha)
    def test_wrong_source_admission_hash_refused(self):
        s,r,b=source_fixture(self.f.source_sha)
        with self.assertRaises(AssertionError):admission.source_binding(s,'f'*64,r,b,self.f.source_sha)
    def cache(self):
        values=self.f.inspect();report={'passed':True,'image_id':IMAGE,'container_started':False,'owned_container_absent':True,**{k:v for k,v in values.items()if k not in ('cache_manifest','cache_metadata')}}
        raw=json.dumps(report).encode();return raw,values['cache_manifest'],json.dumps(values['cache_metadata']).encode()
    def test_cache_metadata_helper_beam_graph_complete(self):
        a,c,m=self.cache()
        with patch.object(admission,'compiled_context',return_value=self.f.binding):self.assertTrue(admission.cache_binding(self.f.context,IMAGE,self.f.source_sha,self.f.context_sha,a,audit.digest(a),c,m)[0]['passed'])
    def test_extra_metadata_refused(self):
        a,c,m=self.cache();d=json.loads(m);d['foreign']={};m=json.dumps(d).encode()
        with self.assertRaises(AssertionError),patch.object(admission,'compiled_context',return_value=self.f.binding):admission.cache_binding(self.f.context,IMAGE,self.f.source_sha,self.f.context_sha,a,audit.digest(a),c,m)
    def test_changed_beam_metadata_refused(self):
        a,c,m=self.cache();d=json.loads(m);d['adhd/ebin/'+self.f.names[0]+'.beam']['sha256']='0'*64;m=json.dumps(d).encode()
        with self.assertRaises(AssertionError),patch.object(admission,'compiled_context',return_value=self.f.binding):admission.cache_binding(self.f.context,IMAGE,self.f.source_sha,self.f.context_sha,a,audit.digest(a),c,m)
    def test_old_image_refused(self):
        a,c,m=self.cache()
        with self.assertRaises(AssertionError),patch.object(admission,'compiled_context',return_value=self.f.binding):admission.cache_binding(self.f.context,'sha256:'+'f'*64,self.f.source_sha,self.f.context_sha,a,audit.digest(a),c,m)
    def capture_fixture(self):
        source,receipt,rebuild=source_fixture(self.f.source_sha)
        for name,body in [('source.json',source),('receipt.json',receipt),('rebuild.json',rebuild),('build.log',b'synthetic compiler RUN log')]:
            (self.root/name).write_bytes(body)
        audit_body,cache,metadata=self.cache();directory=self.root/'audit';directory.mkdir()
        for name,body in [('image-payload.json',audit_body),('cache-manifest.json',cache),('cache-metadata.json',metadata)]:
            (directory/name).write_bytes(body)
        args=SimpleNamespace(image=IMAGE,artifact_sha256=self.f.source_sha,context_sha256=self.f.context_sha,source_admission_sha256=audit.digest(source),payload_audit_sha256=audit.digest(audit_body),source_admission=self.root/'source.json',receipt=self.root/'receipt.json',rebuild=self.root/'rebuild.json',context=self.f.context,audit_directory=directory,build_log=self.root/'build.log',output=self.root/'admission')
        class Fake:
            def checked(self,argv):
                assert argv==['image','inspect',IMAGE]
                return json.dumps([{'Id':IMAGE,'Config':{'Entrypoint':['elixir','/runtime/adhd/boot.exs','/app/hub.exs'],'User':'10001:10001','Cmd':['["serve","/config/hub.json"]']}}]).encode()
        return args,Fake()
    def test_capture_actual_parameters_and_sibling_validator(self):
        args,docker=self.capture_fixture();before=args.receipt.read_bytes()
        with patch.object(admission,'compiled_context',return_value=self.f.binding),patch.object(admission,'compiled_admission',return_value={})as validator,patch('sys.stdout',io.StringIO()):
            report=admission.capture(args,docker)
        self.assertTrue(report['passed']);self.assertFalse(report['qualification_complete']);self.assertEqual(args.receipt.read_bytes(),before)
        self.assertEqual(validator.call_args.args[3:],(IMAGE,self.f.source_sha));self.assertTrue(validator.call_args.kwargs['required'])
        self.assertTrue((args.output/'manifest.json').is_file());self.assertFalse((args.output/'manifest.json.pending').exists())
        self.assertEqual((args.output/'receipt.json').read_bytes(),before)
    def test_failed_final_validation_has_no_passing_manifest(self):
        args,docker=self.capture_fixture()
        with self.assertRaises(ValueError),patch.object(admission,'compiled_context',return_value=self.f.binding),patch.object(admission,'compiled_admission',side_effect=ValueError('validator')):
            admission.capture(args,docker)
        self.assertFalse((args.output/'manifest.json').exists());self.assertFalse(json.loads((args.output/'manifest.json.pending').read_bytes())['passed'])
    def test_existing_output_rejected_before_docker(self):
        args,_=self.capture_fixture();args.output.mkdir()
        class Never:
            def checked(self,argv):raise RuntimeError('Docker must not be called')
        with self.assertRaises(AssertionError),patch.object(admission,'compiled_context',return_value=self.f.binding):admission.capture(args,Never())
    def test_required_parameters_do_not_assign_old_target(self):
        for parser in (audit.parser(),admission.parser()):
            with self.assertRaises(SystemExit),patch('sys.stderr',io.StringIO()):parser.parse_args(['--execute'])
        self.assertNotIn('c635c242',Path(admission.__file__).read_text());self.assertNotIn('4bcdbc7e',Path(audit.__file__).read_text())


if __name__=='__main__':unittest.main()
