"""Pure unbound-target/once/partial-start guards, no Docker/app/CA/threads."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import acme_image_flow
from acme_image_flow import claim_once,digest,verify
from acme_image_target import AcceptedImageTarget,closed
from acme_image_session import runtime_class

class FlowChecks(unittest.TestCase):
    def test_unbound_target_and_changed_driver_fail_before_import_or_marker(self):
        with tempfile.TemporaryDirectory()as d:
            driver=Path(acme_image_flow.__file__).absolute();plan=Path(d)/'plan.json'
            value={'schema':'adhd/acme-image-flow@1','driver':str(driver),'driver_sha256':digest(driver),'target':None}
            plan.write_text(json.dumps(value))
            with self.assertRaisesRegex(AssertionError,'No accepted'):verify(plan,digest(plan))
            value['driver_sha256']='0'*64;plan.write_text(json.dumps(value))
            with self.assertRaises(AssertionError):verify(plan,digest(plan))
            self.assertEqual({p.name for p in Path(d).iterdir()},{'plan.json'})
            with self.assertRaisesRegex(AssertionError,'Actual accepted'):AcceptedImageTarget({'target':None})
            with self.assertRaisesRegex(AssertionError,'Duplicate'):closed('{"target":null,"target":{}}')

    def test_durable_once_refuses_reentry_without_rewriting(self):
        with tempfile.TemporaryDirectory()as d:
            marker=Path(d)/'started.json';claim_once(marker,'a'*64);original=marker.read_bytes()
            with self.assertRaises(FileExistsError):claim_once(marker,'b'*64)
            self.assertEqual(marker.read_bytes(),original);self.assertEqual(marker.stat().st_mode&0o777,0o600)

    def test_image_constructor_inert_and_native_cache_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);target=Mock();cls=runtime_class(target,root)
            item=cls(root,None,None,None,None,erlang=None)
            self.assertIsNone(item.process);target.image.assert_not_called()
            with self.assertRaisesRegex(AssertionError,'native cache'):cls(root,'source','cache','elixir','digest',erlang='erl')
            target.image.assert_not_called()

    def test_failed_docker_spawn_closes_owned_logs_and_image_without_new_attempt(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);(root/'hub.json').write_text('{"port":18001}')
            image=SimpleNamespace(verify=Mock(),argv=Mock(return_value=['/owned/docker','run','image']),
              env={},name=None,stop=Mock(),events=[],runtime_rows=[])
            target=Mock();target.image.return_value=image;target.evidence.return_value={}
            runtime=runtime_class(target,root)(root,None,None,None,None,erlang=None)
            failure=OSError('owned Popen failed')
            with patch('acme_image_session.subprocess.Popen',side_effect=failure)as popen:
                with self.assertRaises(OSError)as caught:runtime.start()
            self.assertIs(caught.exception,failure);self.assertEqual(popen.call_count,1)
            image.stop.assert_called_once();self.assertEqual(runtime.logs,[]);self.assertIsNone(runtime.image)
            self.assertTrue(all((root/name).stat().st_mode&0o777==0o600 for name in ['stdout.log','stderr.log']))

    def test_tool_owner_policy_keeps_private_evidence_strict(self):
        import os
        import stat
        from acme_image_target import tool_regular
        from acme_runtime import regular
        executable=Path('/usr/bin/docker')
        # Actual root-owned executable, read-only metadata inspection only.
        self.assertEqual(tool_regular(executable).st_uid,0)
        if os.getuid()!=0:
            with self.assertRaises(AssertionError):regular(executable)
        oversized=SimpleNamespace(st_mode=stat.S_IFREG|0o755,st_uid=0,st_nlink=1,st_size=129*1024*1024)
        with patch.object(Path,'lstat',return_value=oversized):
            with self.assertRaisesRegex(AssertionError,'128MiB'):tool_regular(executable)
        for uid,mode in [(os.getuid()+9000,0o755),(0,0o777)]:
            fake=SimpleNamespace(st_mode=stat.S_IFREG|mode,st_uid=uid,st_nlink=1)
            with patch.object(Path,'lstat',return_value=fake):
                with self.assertRaises(AssertionError):tool_regular(executable)

    def test_offline_stop_failure_still_reaps_owned_client_and_retains_primary(self):
        import subprocess
        with tempfile.TemporaryDirectory()as d:
            root=Path(d)
            image=SimpleNamespace(argv=Mock(return_value=['/owned/docker','run','--network','host','image']),
              env={},stop=Mock(side_effect=OSError('daemon unavailable')),events=[{'kind':'issued'}],runtime_rows=[])
            target=Mock();target.image.return_value=image
            runtime=runtime_class(target,root)(root,None,None,None,None,erlang=None)
            process=Mock(pid=99123,returncode=-9)
            process.wait.side_effect=[subprocess.TimeoutExpired('owned',15),-9]
            primary=AssertionError('original custody mismatch')
            with patch('acme_image_session.subprocess.Popen',return_value=process),\
                 patch('acme_image_session.ticks',side_effect=[42,42,None]),\
                 patch('acme_image_session.os.killpg')as kill,\
                 patch.object(runtime,'_observe',side_effect=primary):
                with self.assertRaises(AssertionError)as caught:
                    runtime.offline_rebind({},root/'out',root/'err')
            self.assertIs(caught.exception,primary)
            kill.assert_called_once_with(99123,__import__('signal').SIGKILL)
            self.assertEqual(process.wait.call_count,2)
            row=runtime.offline_sessions[0]
            self.assertTrue(row['reaped']);self.assertTrue(row['original_identity_absent'])
            self.assertEqual(row['cleanup_errors'],[{'scope':'image','type':'OSError'},{'scope':'client','type':'AssertionError'}])
            self.assertEqual(row['container_lifecycle'],image.events)
