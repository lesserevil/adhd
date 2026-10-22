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
if __name__=='__main__':unittest.main()
