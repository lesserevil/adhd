"""No-startup guards for the source-unchanged causal observer adapter."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('phase_diagnostic',Path(__file__).with_name('r25_phase_diagnostic.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Guards(unittest.TestCase):
    def test_exact_entry_tail_and_no_pid_host(self):
        base=['docker','run','--network','host','sha256:'+'a'*64]
        result,path=m.instrument(base,base[-1],Path('/observer.exs'),Path('/private'),Path('/private/armed'),0,'b'*32)
        self.assertEqual(result[-5:],[base[-1],'-r','/adhd-test/recovery-phase.exs','/runtime/adhd/boot.exs','/app/hub.exs'])
        self.assertEqual(path,Path('/private/phase-0.log'));self.assertEqual(base,['docker','run','--network','host',base[-1]])
        for changed in [base[:-1]+['--pid=host',base[-1]],base[:-1]+['--entrypoint','sh',base[-1]]]:
            with self.assertRaises(AssertionError):m.instrument(changed,base[-1],Path('/observer.exs'),Path('/private'),Path('/private/armed'),0,'b'*32)
    def test_existing_log_is_not_reused(self):
        with tempfile.TemporaryDirectory()as t:
            root=Path(t);(root/'phase-0.log').write_text('existing')
            with self.assertRaises(AssertionError):m.instrument(['docker','run','sha256:'+'a'*64],'sha256:'+'a'*64,root/'observer',root,root/'armed',0,'b'*32)
    def test_original_guarded_boot_and_mount_identity(self):
        with tempfile.TemporaryDirectory()as t:
            f=Path(t)/'observer';f.write_text('test')
            target=type('Target',(),dict(config_file=Path('/private/hub.json'),phase_observer_path=str(f),phase_observer_sha256=m.sha(f),phase_trace_paths=['/private/phase-0.log']))()
            row={'Config':{'Entrypoint':['elixir'],'Cmd':['-r','/adhd-test/recovery-phase.exs','/runtime/adhd/boot.exs','/app/hub.exs',json.dumps(['serve','/private/hub.json'])]},'Mounts':[{'Destination':'/adhd-test/recovery-phase.exs','Source':str(f),'Type':'bind','RW':False}]}
            calls=[]
            def original(r,*_):calls.append(r);return {'readonly_rootfs':True}
            proof=m.inspected(row,target,{'reviewed_runtime_audit':{'entrypoint':['elixir','/runtime/adhd/boot.exs','/app/hub.exs']}},original)
            self.assertEqual(proof['execution_scope'],'source-unchanged-compiled-boot-with-diagnostic-mfa-observer');self.assertEqual(row['Config']['Entrypoint'],['elixir']);self.assertEqual(len(calls),1)
            for key,value in [('Type','volume'),('RW',True),('Source','/foreign')]:
                changed=copy.deepcopy(row);changed['Mounts'][0][key]=value
                with self.assertRaises(AssertionError):m.inspected(changed,target,{},original)
    def test_marker_is_durable_exclusive_and_blocks_reentry(self):
        with tempfile.TemporaryDirectory()as t:
            p=Path(t);m.claim(p)
            with self.assertRaises(FileExistsError):m.claim(p)
            self.assertEqual((p/'started.json').stat().st_mode&0o777,0o600)
    def test_observer_static_no_raw_serialization_or_source_loading(self):
        text=Path(__file__).with_name('recovery_phase_observer.exs').read_text()
        for forbidden in ['Code.compile','Code.eval','ensure_loaded','inspect(reason)','inspect(result)','term_to_binary','IO.inspect']:
            self.assertNotIn(forbidden,text)
        for required in [':arity',':exception_trace',':return_trace','count > 0',':code.is_loaded','safe_status(m, f, result)','BROKER_REQUEST_FAILED','TOPIC_CREATE_FAILED','ADHD_TEST_PHASE_ARM','count < 256','byte_size(line) <= 240']:
            self.assertIn(required,text)

if __name__=='__main__':unittest.main()
