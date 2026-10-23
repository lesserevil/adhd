"""Pure preparation inventory checks; no target image/CA/process starts."""
import json
from pathlib import Path
import tempfile
import unittest
from acme_image_plan_prepare import inventory,verify_tool_roots,read,write,sha


class PreparationChecks(unittest.TestCase):
    def test_external_root_exact_set_rejects_added_changed_and_symlink_files(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'owned').write_text('original')
            plan={'tool_roots':{str(root):inventory(root)}};verify_tool_roots(plan)
            (root/'added').write_text('new executable')
            with self.assertRaisesRegex(AssertionError,'SET/hash'):verify_tool_roots(plan)
            (root/'added').unlink();(root/'owned').write_text('changed')
            with self.assertRaisesRegex(AssertionError,'SET/hash'):verify_tool_roots(plan)
            (root/'owned').unlink();(root/'owned').symlink_to('/usr/bin/true')
            with self.assertRaises(AssertionError):verify_tool_roots(plan)

    def test_exclusive_output_never_overwrites_old_preparation(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'new'/'plan.json';write(path,b'original')
            with self.assertRaises(FileExistsError):write(path,b'replacement')
            self.assertEqual(read(path),b'original');self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_preparation_read_rejects_alias_without_reading_target(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);actual=root/'original';actual.write_text('private fixture')
            redirected=root/'alias';redirected.symlink_to(actual)
            with self.assertRaisesRegex(AssertionError,'Redirected'):read(redirected)

    def test_generator_seals_all16_unbound_plans_without_inventing_image_or_pair(self):
        from acme_image_plan_prepare import prepare,verify_preparation
        with tempfile.TemporaryDirectory()as directory:
            base=Path(directory);root=base/'project';(root/'tests').mkdir(parents=True)
            required=['acme_image_flow.py','acme_image_fault_flow.py','acme_image_provision.py','acme_image_faults.py',
              'acme_image_plan_prepare.py','image_compiled_admission.py','image_compiled_inputs.py','image_payload_audit.py']
            for name in required:
                raw=(Path(__file__).with_name(name).read_bytes()if name=='acme_image_faults.py'else b'# synthetic unit-only helper input\n')
                (root/'tests'/name).write_bytes(raw)
            (root/'scripts').mkdir();(root/'scripts/configure_hub.py').write_text('# unit fixture only\n')
            (root/'components/hub/acme').mkdir(parents=True)
            (root/'components/hub/acme/interface.schema.json').write_text('{}')
            ca=base/'ca';ca.mkdir()
            for name in ['frontend-root.pem','issuer-root.pem','frontend-cert.pem','frontend-key.pem']:
                (ca/name).write_bytes(b'unit-only static fixture')
            value={'ready':True,'real_validation':True,'nonce_validation':True,'public_ca_calls':0,'validation_http_port':8080}
            for name,filename in [('frontend_root','frontend-root.pem'),('issuer_root','issuer-root.pem')]:
                value[name]=str(ca/filename);value[name+'_sha256']=sha((ca/filename).read_bytes())
            manifest=ca/'manifest.json';manifest.write_text(json.dumps(value))
            source=base/'source';source.mkdir()
            siblings={'receipt.json':b'{}','rebuild.json':b'{}'}
            for name,raw in siblings.items():(source/name).write_bytes(raw)
            admission=source/'manifest.json';admission.write_text(json.dumps({'passed':True,'artifact_sha256':'a'*64,
              'files':{name:sha(raw)for name,raw in siblings.items()}}))
            output=base/'new'
            result=prepare(root,output,manifest,sha(read(manifest)),admission,sha(read(admission)),
              __import__('sys').executable,[])
            self.assertFalse(result['target_bound']);self.assertEqual(len(result['plans']),16)
            foundation=json.loads(read(result['plans'][0]['plan']))
            self.assertIn('--continuity',foundation['program_argv'])
            self.assertNotIn('--lego-sha256',foundation['program_argv']);self.assertIsNone(foundation['target'])
            self.assertFalse(any(Path(row['plan']).with_name('started.json').exists()for row in result['plans']))
            verify_preparation(output/'preparation.json')
            extra=Path(result['frozen']['root'])/'tests/unbound_extra.py';extra.write_text('# unauthorized helper')
            with self.assertRaisesRegex(AssertionError,'Frozen helper SET/hash'):
                verify_preparation(output/'preparation.json')
