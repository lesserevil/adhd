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
