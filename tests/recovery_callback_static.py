"""Pure callback preparation/custody checks. No hub, container or provider starts."""
import copy
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

import recovery_callback_matrix as matrix
import recovery_compiled_callbacks as runtime


class CallbackGuards(unittest.TestCase):
    def test_changed_driver_is_rejected_before_helper_import_or_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);driver=work/'run.py';driver.write_text('changed driver')
            with patch.object(matrix,'__file__',str(driver)),patch.object(matrix,'load',side_effect=AssertionError('No helper load')) as loaded:
                with self.assertRaises(AssertionError):matrix.verify({'driver_sha256':hashlib.sha256(b'original').hexdigest()},work)
                loaded.assert_not_called()
    def test_full_scope_and_original_watcher_body_are_exact(self):
        original=Path(__file__).with_name('project_recovery_live_loss.exs').read_text()
        generated=runtime.compiled_observer(original)
        body=original.split('defmodule RecoveryLiveLoss do\n')[1].split('\n["serve", config]')[0]
        self.assertIn('defmodule RecoveryLiveLoss do\n'+body,generated)
        self.assertNotIn('Code.compile_string',generated)
        self.assertTrue(generated.endswith('System.argv([artifact, payload])\nCode.eval_file("/runtime/adhd/boot.exs")\n'))
        self.assertEqual(list(matrix.CASES.values()),[4,5,8,7,4]);self.assertEqual(sum(matrix.CASES.values()),28)
        self.assertIn('Process.sleep(20)',generated);self.assertIn('5000 ->',generated)
    def test_observer_refuses_unreviewed_source_tail(self):
        original=Path(__file__).with_name('project_recovery_live_loss.exs').read_text()
        with self.assertRaises(AssertionError):runtime.compiled_observer(original+'# changed entry\n')
    def test_each_peer_needs_two_distinct_actual_runtimes(self):
        plan={'image_config_identity':'image','artifact_sha256':'artifact','canonical_manifest_sha256':'manifest',
            'bound_inputs':{'compiled-observer.exs':'observer'}}
        def value(identifier):return {'kind':'docker','payload_verified':True,'image_config_identity':'image','artifact_sha256':'artifact',
            'canonical_manifest_sha256':'manifest','observer_sha256':'observer','owned_container_absent':True,'owned_docker_client_exited':True,
            'cleanup_failure_types':[],'startup_seconds':150,'watched_vm_observations':[{'image_config_identity':'image','namespace_vm_pid':1}],
            'container_lifecycle':[{'action':'started','container_id':identifier},{'action':'stopped','container_id':identifier,'observed_absent':True}],
            'payload_probe_lifecycle':[{'observed_absent':True}]}
        self.assertIsNone(matrix.runtime_proof({'runtime_origin':value('a'),'runtime_peer':value('b')},plan,'queries'))
        for broken in [{'runtime_origin':value('a')},{'runtime_origin':value('a'),'runtime_peer':value('a')}]:
            with self.assertRaises(AssertionError):matrix.runtime_proof(broken,plan,'queries')
    def test_strict_absence_rejects_wrong_identity_daemon_and_status(self):
        from controlled_image_runtime import authoritative_absence
        good=SimpleNamespace(returncode=1,stdout=b'[]\n',stderr=b'error: no such object: owned\n')
        self.assertTrue(authoritative_absence(good,'owned'))
        for field,value in [('returncode',2),('stderr',b'error: no such object: foreign\n'),
                            ('stderr',b'Cannot contact daemon; no such object: owned\n'),('stdout',b'foreign')]:
            broken=copy.copy(good);setattr(broken,field,value)
            with self.assertRaises(AssertionError):authoritative_absence(broken,'owned')
    def test_optional_adapter_install_has_zero_startup_and_uses_strict_base_probe(self):
        import recovery_image_runtime as recovery
        import subprocess
        from http.server import ThreadingHTTPServer
        from container_fixture import OwnedImage
        custody=runtime.Custody.__new__(runtime.Custody)
        with patch.object(recovery,'ObserverImage',recovery.ObserverImage),patch.object(recovery.RecoveryImageRuntime,'start',recovery.RecoveryImageRuntime.start),\
             patch.object(recovery.RecoveryImageRuntime,'hard_stop',recovery.RecoveryImageRuntime.hard_stop),\
             patch.object(ThreadingHTTPServer,'__init__',ThreadingHTTPServer.__init__),\
             patch.object(subprocess,'Popen',side_effect=AssertionError('Startup forbidden')) as popen,\
             patch.object(subprocess,'run',side_effect=AssertionError('Docker forbidden')) as run:
            custody.install();self.assertIs(recovery.ObserverImage.probe,OwnedImage.probe)
            popen.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
