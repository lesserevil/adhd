"""Pure wrapper/closure guards. No VM, Docker, Kafka, HTTP or model starts."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

incoming_path=list(sys.path)
m=load('readiness_compiled_matrix','eventing_readiness_compiled_matrix.py')

sys.path[:]=incoming_path

class Guards(unittest.TestCase):
    def test_full23_original_scope_and_no_deadline_override(self):
        argv=m.scenario_argv(Path('/synthetic'),'/python','sha256:synthetic','http://127.0.0.1:18082')
        self.assertEqual(len(m.CHECKS),23)
        self.assertNotIn('--deadline',argv);self.assertNotIn('--with-model',argv);self.assertNotIn('--cases',argv)
        self.assertIn('/synthetic/frozen/tests/eventing_readiness_compiled.py',argv)
    def test_false_row_is_not_whole_positive(self):
        with tempfile.TemporaryDirectory()as name:
            work=Path(name);(work/'results').mkdir();(work/'results/report.json').write_text(json.dumps({
                'suite':'adhd/eventing-readiness-faults@2','planned_cases':m.CHECKS,'checks':[{'name':m.CHECKS[0],'passed':False}]}))
            with self.assertRaises(AssertionError):m.observations(work,{})
    def test_partial_failure_retains_prefix_and_unrun(self):
        with tempfile.TemporaryDirectory()as name:
            work=Path(name);(work/'results').mkdir();proxy=lambda case:{'case':case,'handlers':0,'thread_alive':False,'failures':[],'cleanup_failure_types':[]}
            (work/'results/report.json').write_text(json.dumps({'suite':'adhd/eventing-readiness-faults@2','planned_cases':m.CHECKS,
                'checks':[{'name':m.CHECKS[0],'passed':True}],'proxy_cleanup':[proxy(x)for x in m.CHECKS[:2]]}))
            result=m.observations(work,{})
            self.assertEqual(result['whole_passed'],m.CHECKS[:1]);self.assertEqual(result['failed_case'],m.CHECKS[1]);self.assertEqual(result['unrun'],m.CHECKS[2:])
    def test_changed_frozen_helper_is_denied_before_import(self):
        with tempfile.TemporaryDirectory()as name:
            work=Path(name);driver=work/'driver.py';driver.write_bytes(Path(m.__file__).read_bytes())
            folder=work/'frozen/tests';folder.mkdir(parents=True);marker=work/'IMPORTED'
            helper=folder/'eventing_readiness_matrix.py';helper.write_text('from pathlib import Path;Path('+repr(str(marker))+').touch()')
            (work/'plan.json').write_text(json.dumps({'schema':m.SCHEMA,'driver_sha256':m.sha(driver),'frozen':{
                'files':{'tests/eventing_readiness_matrix.py':'0'*64},'directories':['tests']}}))
            child=subprocess.run([sys.executable,'-I','-B',str(driver),'verify','--work',str(work)],capture_output=True)
            self.assertNotEqual(child.returncode,0);self.assertFalse(marker.exists());self.assertIn(b'AssertionError',child.stderr)

class Entry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.entry=load('readiness_compiled_entry','eventing_readiness_compiled.py')
    def test_patched_fixture_runs_original_class_once(self):
        e=self.entry;calls=[]
        class Original:
            async def start(self):calls.append('original')
        class Custody:
            starts=[]
            def image_class(self):return object
            def observe(self,image):calls.append(image);self.starts.append({})
            def save(self):calls.append('save')
        custody=Custody()
        with patch.object(e.scenario,'Fixture',Original):
            hooks=e.install(custody)
            with hooks[0],hooks[1]:
                selected=e.scenario.Fixture();selected.root=Path('/fixtures/lag');selected.image_runtime='actual-image-placeholder'
                asyncio.run(selected.start())
            self.assertIs(e.scenario.Fixture,Original)
        self.assertEqual(calls,['original','actual-image-placeholder','save']);self.assertEqual(custody.starts,[{'case':'lag'}])
    def test_start_failure_preserved_without_custody_warmup(self):
        e=self.entry;failure=ValueError('synthetic startup failure');observed=[]
        class Original:
            async def start(self):raise failure
        custody=SimpleNamespace(image_class=lambda:object,observe=lambda *args:observed.append(args),save=lambda:None)
        with patch.object(e.scenario,'Fixture',Original):
            hooks=e.install(custody)
            with hooks[0],hooks[1]:
                with self.assertRaises(ValueError)as caught:asyncio.run(e.scenario.Fixture().start())
                self.assertIs(caught.exception,failure)
        self.assertEqual(observed,[])
if __name__=='__main__':unittest.main()
