"""Static command/content checks; no Elixir/Docker process starts."""
import importlib.util
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('cache_probe',Path(__file__).with_name('recovery_observer_cache_probe.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ProbeGuards(unittest.TestCase):
    def test_only_bound_observer_is_compiled(self):
        code=m.script(b'# test only\n','a'*64)
        self.assertIn('Code.eval_string(Base.decode64!("IyB0ZXN0IG9ubHkK")',code)
        self.assertIn(':code.load_binary(module, String.to_charlist(path), bytes)',code)
        self.assertIn('map_size(cache["beams"]) == 59',code)
        self.assertIn('"a'+'a'*63+'"',code)
        for forbidden in ['Code.eval_file','/runtime/adhd/boot.exs','["serve"','Application.ensure_all_started','ADHD.Server','http://']:
            self.assertNotIn(forbidden,code)
    def test_network_none_readonly_no_healthcheck_command(self):
        image='sha256:'+'a'*64
        args=('run','--rm','--network','none','--read-only',image,'-e','test')
        adapted=m.probe_options(args,image)
        self.assertIn('--no-healthcheck',adapted)
        self.assertEqual(adapted[-3:],(image,'-e','test'))
        with self.assertRaises(AssertionError):m.probe_options(('run','--network','host','--read-only',image),image)
        with self.assertRaises(AssertionError):m.probe_options(('run','--network','none','--read-only','--pid=host',image),image)
    def test_required_patterns_are_not_silently_optional(self):
        text=Path(__file__).with_name('recovery_phase_observer.exs').read_text()
        self.assertIn('true = is_integer(count) and count > 0',text)
        self.assertIn('emit(fd, ["pattern", inspect(m)',text)
        self.assertIn('safe_class(class) | Process.get(:phase_setup',text)
        self.assertIn('bytes <= 65536',text)

class ProfileCopy(unittest.TestCase):
    def prepare(self,drift=False):
        import tempfile,json,sys,io
        from unittest.mock import patch
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        phase=root/'phase';phase.mkdir();original=root/'original';original.mkdir()
        observed=b'# source-bound nineteen-pattern observer fixture; never compiled\n'
        (phase/'observer.exs').write_bytes(observed)
        (phase/'driver.py').write_text('# not executed')
        (phase/'plan.json').write_text(json.dumps({'original_work':str(original),'observer_sha256':'f'*64 if drift else m.sha(phase/'observer.exs')}))
        parent={'compiled_binding':{'compiled_cache':{'manifest_sha256':'a'*64}},'image_config_identity':'sha256:'+'b'*64,'artifact_sha256':'c'*64,'canonical_manifest_sha256':'d'*64,'admission_manifest_sha256':'e'*64,'env':{'PATH':'testpath','DOCKER_HOST':'testsocket','DOCKER_CONFIG':'testconfig'}}
        (original/'plan.json').write_text(json.dumps(parent));work=root/'work'
        with patch.object(sys,'argv',['probe','--prepare','--work',str(work),'--phase-work',str(phase)]),patch('sys.stdout',io.StringIO()):m.main()
        return work,observed
    def test_prepare_copies_phase_render_not_authored_legacy_template(self):
        import json
        work,observed=self.prepare();self.assertEqual((work/'observer.exs').read_bytes(),observed)
        self.assertEqual(json.loads((work/'plan.json').read_bytes())['observer_sha256'],m.sha(work/'observer.exs'))
    def test_prepare_rejects_phase_observer_hash_drift(self):
        with self.assertRaises(AssertionError):self.prepare(True)

if __name__=='__main__':unittest.main()
