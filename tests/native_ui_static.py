"""Pure native UI preparation guards; never start a VM/browser/provider/compiler."""
import asyncio
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_ui_matrix as matrix
import native_ui_runtime as runtime


class NativeUIGuards(unittest.TestCase):
    def test_module_identity_only_supports_narrow_visual_reuse(self):
        names=['Web','Projects']+['M'+str(i)for i in range(57)]
        old=b''.join(('defmodule ADHD.'+name+' do\nend\n').encode()for name in names)
        new=old.replace(b'defmodule ADHD.Projects do\n',b'defmodule ADHD.Projects do\n#guard\n')
        value=matrix.module_identity(old,new);self.assertEqual(value['byte_identical_modules'],58)
        self.assertEqual(value['changed_modules'],['ADHD.Projects'])
        for broken in [old,new.replace(b'defmodule ADHD.Web do\n',b'defmodule ADHD.Web do\n#changed\n')]:
            with self.assertRaises(AssertionError):matrix.module_identity(old,broken)
    def test_original_native_flags_order_deadlines_and_command_are_preserved(self):
        original=['/usr/bin/flock','/original/lock','/python','/old/test.py','--command',json.dumps(['/elixir','/old/hub']),
            '--with-model','--keep-work','/old/root','--report','/old/report','--port-lock','/original/port-lock']
        output=matrix.native_arguments(original,Path('/new/test.py'),Path('/new/hub'),Path('/new/report'),Path('/new/root'),Path('/new/rig.tgz'))
        self.assertEqual(output,['/new/test.py','--command',json.dumps(['/elixir','/new/hub']),'--with-model','--keep-work','/new/root',
            '--report','/new/report','--port-lock','/original/port-lock'])
        self.assertEqual(original[1],'/original/lock')
    def test_changed_driver_rejects_before_helpers_or_any_execution(self):
        with tempfile.TemporaryDirectory()as tmp:
            work=Path(tmp);driver=work/'run.py';driver.write_text('changed')
            with patch.object(matrix,'__file__',str(driver)),patch.object(matrix,'load')as loaded:
                with self.assertRaises(AssertionError):matrix.verify({'driver_sha256':hashlib.sha256(b'original').hexdigest()},work)
                loaded.assert_not_called()
    def test_bootstrap_rejects_changed_helper_before_import_path_is_added(self):
        with tempfile.TemporaryDirectory()as tmp:
            work=Path(tmp);driver=work/'run.py';driver.write_text('owned driver')
            tests=work/'frozen/tests';tests.mkdir(parents=True);helper=tests/'helper.py';helper.write_text('changed helper')
            matrix.write(work/'plan.json',{'driver_sha256':matrix.sha(driver),'frozen_inputs':{'tests/helper.py':hashlib.sha256(b'original').hexdigest()}})
            with patch.object(matrix.sys,'path',[]) as paths:
                with self.assertRaises(AssertionError):matrix.bootstrap_frozen(driver)
                self.assertEqual(paths,[])
    def test_once_refusal_precedes_runtime_fixture_or_compiler(self):
        from controlled_image_matrix import durable_once_marker
        with tempfile.TemporaryDirectory()as tmp:
            work=Path(tmp);plan={'runtime_cwd':str(work/'runtime'),'openrig_root':str(work/'rig'),
                'lane_lock':str(work/'lane.lock'),'driver_sha256':'a'*64}
            matrix.write(work/'plan.json',plan);digest=matrix.sha(work/'plan.json');durable_once_marker(work/'started.json',{'plan_sha256':digest})
            with patch.object(matrix,'verify',return_value=True),patch.object(matrix,'load',return_value=SimpleNamespace(durable_once_marker=durable_once_marker)):
                with self.assertRaises(FileExistsError):matrix.execute(work,digest)
            self.assertFalse((work/'runtime').exists());self.assertFalse((work/'rig').exists())
    def test_models_reject_real_provider_in_root_and_hidden_override(self):
        custody=runtime.Custody({}, {}, Path('/private'));custody.servers=[]
        for config in [{'matcher':{'url':'http://127.0.0.1:18770/v1/systemone'}},
                       {'matcher':None,'projects':[{'settings':{'history':{'model':{'url':'http://127.0.0.1:18770/v1/systemone'}}}}]}]:
            with self.assertRaises(AssertionError):custody.audit(config)
        custody.servers=[(SimpleNamespace(fileno=lambda:3,server_address=('127.0.0.1',1234)),'bound-source')]
        self.assertEqual(len(custody.audit({'matcher':{'url':'http://127.0.0.1:1234/v1/systemone'}})),1)
    def test_native_observation_requires_actual_bound_artifact_argv_and_fence(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);artifact=root/'hub.exs';artifact.write_bytes(b'admitted');config=root/'hub.json';config.write_text('{}')
            custody=runtime.Custody({'artifact':str(artifact),'artifact_sha256':matrix.sha(artifact),'native_beam_sha256':'elf',
                'fence_library':str(root/'fence.so')},{'launch_ledger':str(root/'ledger')},root)
            obj=SimpleNamespace(process=SimpleNamespace(poll=lambda:None),file=config,root=root)
            identity={'pid':123,'starttime':'birth','executable_sha256':'elf','fence_mapped':True}
            original=Path.read_bytes
            for proper in [True,False]:
                def read(path):
                    if str(path)=='/proc/123/cmdline':return b'beam\0'+(str(artifact).encode()if proper else b'/other/source')+b'\0'
                    return original(path)
                with patch.object(runtime,'native_vm',return_value=[identity]),patch.object(Path,'read_bytes',autospec=True,side_effect=read):
                    if proper:custody.observe(obj,'after-original-readiness')
                    else:
                        with self.assertRaises(AssertionError):custody.observe(obj,'after-original-readiness')
            self.assertEqual(len(custody.vm),1)
    def test_image_branch_rejected_before_original_startup(self):
        from multi_support import Fixture
        from multi_workflow_upgrade import UpgradeRuntime
        from http.server import ThreadingHTTPServer
        from playwright.async_api import BrowserType
        from playwright.sync_api import BrowserType as SyncBrowserType
        custody=runtime.Custody({}, {'name':'roles'}, Path('/private'))
        with ExitStack()as stack:
            for cls,names in [(Fixture,['start','close','hard_stop']),(UpgradeRuntime,['start','stop']),
                              (ThreadingHTTPServer,['__init__']),(BrowserType,['launch']),(SyncBrowserType,['launch'])]:
                for name in names:stack.enter_context(patch.object(cls,name,getattr(cls,name)))
            custody.install()
            with self.assertRaises(AssertionError):asyncio.run(Fixture.start(SimpleNamespace(image_runtime=object(),args=SimpleNamespace(rest_url=None))))
            with self.assertRaises(AssertionError):UpgradeRuntime.start(SimpleNamespace(owned_image=object(),image=None))


if __name__=='__main__':
    with patch('subprocess.Popen',side_effect=AssertionError('No VM/browser/provider/compiler starts')):unittest.main()
