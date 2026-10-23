"""Pure terminal qualification guards; no Docker or runtime operations."""
import unittest
from acme_image_capture import qualify,resource_facts


class CaptureChecks(unittest.TestCase):
    def fixture(self):
        target={'image':'sha256:'+'a'*64,'artifact_sha256':'b'*64,'manifest_sha256':'c'*64,
          'admission_sha256':'d'*64,'source_admission_sha256':'e'*64}
        plan={'schema':'adhd/acme-image-flow@1','program_argv':['--continuity'],'target':target}
        binding={'image_config_identity':target['image'],'artifact_sha256':'b'*64,'canonical_manifest_sha256':'c'*64,
          'admission_sha256':'d'*64,'source_admission_sha256':'e'*64}
        vm={'image':target['image'],'default_entrypoint':True,'default_command':False,'public_command':'serve',
          'command_sha256':'f'*64,'original_vm_identity_absent':True}
        result={'passed':True,'cleanup_errors':[],'target':binding,'runtime_sessions':[{
          'name':None,'container_id':None,'payload_verified':True,'assets_verified':True,'probe_cleanup_blocked':False,
          'probes':[{'observed_absent':True,'cleanup_failure_types':[]}],'actual_vms':[vm]}]}
        report={'passed':True,'checks':[{'passed':True}for _ in range(18)],'cleanup_errors':[]}
        return plan,result,report

    def test_partial_report_and_nonzero_terminal_never_qualify(self):
        plan,result,report=self.fixture()
        self.assertTrue(qualify(plan,result,report,0)['structural_passed'])
        report['checks'].pop()
        self.assertFalse(qualify(plan,result,report,0)['structural_passed'])
        report['checks'].append({'passed':True})
        self.assertFalse(qualify(plan,result,report,1)['structural_passed'])
        report['checks'][0]['passed']=False
        self.assertFalse(qualify(plan,result,report,0)['structural_passed'])

    def test_wrong_target_and_default_command_cannot_be_relabelled(self):
        plan,result,report=self.fixture()
        result['target']['admission_sha256']='wrong'
        self.assertFalse(qualify(plan,result,report,0)['structural_passed'])
        plan,result,report=self.fixture();result['runtime_sessions'][0]['actual_vms'][0]['default_command']=True
        self.assertFalse(qualify(plan,result,report,0)['structural_passed'])

    def test_resource_collection_does_not_invent_unrecorded_pids_or_names(self):
        identifiers,pids=resource_facts({'runtime_sessions':[]},{})
        self.assertEqual((identifiers,pids),([],[]))

    def test_recorded_live_pid_is_not_mistaken_for_cleanup(self):
        import os
        from acme_image_capture import ticks
        pid=os.getpid();start=ticks(pid)
        identifiers,pids=resource_facts({'runtime_sessions':[]},{'runtime_identities':[{'pid':pid,'start_ticks':start}]})
        self.assertEqual(identifiers,[]);self.assertEqual(len(pids),1)
        self.assertFalse(pids[0]['original_identity_absent'])

    def test_capture_summary_never_copies_private_report_values_or_issues_commands_by_default(self):
        import tempfile,json,hashlib
        from pathlib import Path
        from unittest.mock import patch
        from acme_image_capture import audit
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);work=root/'work';work.mkdir()
            plan,result,report=self.fixture();cache=root/'cache.json';cache.write_text('{"beams":{},"acme":{}}')
            plan.update(files={},tool_files={},program_argv=['--work',str(work),'--continuity'])
            plan['target']['cache_manifest']=str(cache)
            secret='PRIVATE-KEY-CREDENTIAL-NEVER-IN-SUMMARY'
            report['private_fixture_material']=secret;report['passed']=False
            report_path=work/'report.json';report_path.write_text(json.dumps(report))
            path=root/'plan.json';path.write_text(json.dumps(plan));plan_sha=hashlib.sha256(path.read_bytes()).hexdigest()
            result['plan_sha256']=plan_sha;result['passed']=False
            result['report_sha256']=hashlib.sha256(report_path.read_bytes()).hexdigest()
            result['runtime_sessions']=[]
            (root/'result.json').write_text(json.dumps(result))
            with patch('acme_image_capture.subprocess.run')as command:
                captured=audit(path,plan_sha,1)
            command.assert_not_called()
            self.assertNotIn(secret,json.dumps(captured))
            self.assertFalse(captured['qualification']['runtime_qualified'])

    def test_missing_cleanup_evidence_cannot_qualify_whole_positive(self):
        plan,result,report=self.fixture();del result['cleanup_errors']
        self.assertFalse(qualify(plan,result,report,0)['structural_passed'])
        plan,result,report=self.fixture();result['runtime_sessions'][0]['probes']=[]
        self.assertFalse(qualify(plan,result,report,0)['structural_passed'])
