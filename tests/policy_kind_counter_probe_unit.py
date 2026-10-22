"""Pure review of native probe source/expected vectors; never compiles/executes C."""
import hashlib
import json
from pathlib import Path
import re
import unittest

class ProbeSource(unittest.TestCase):
    def test_independent_SHA_golds(self):
        source = Path(__file__).with_name('policy_kind_counter_probe.c').read_text()
        for raw in (b'', b'abc', b'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq', b'a'*1000000):
            self.assertIn(hashlib.sha256(raw).hexdigest(), source)
        self.assertIn('#define main counter19_original_entry', source)
        self.assertIn('#include "policy_kind_counter.c"', source)

    def test_rawENV_witness_is_native_not_shell_or_ELIXIR(self):
        source = Path(__file__).with_name('policy_kind_counter_probe.c').read_text()
        vector = ['HOME=/tmp', 'PATH=/usr/local/bin:/usr/bin:/bin', 'LANG=C',
                  'ERL_FLAGS=+S 2:2', 'ERL_FLAGS=+S 1:1']
        block = re.search(r'probe_environment\[\] = \{(.*?)\};', source, re.S).group(1)
        self.assertEqual(re.findall(r'"([^"]*)"', block), vector)
        self.assertIn('execve(argv[0], argv, probe_environment)', source)
        self.assertIn('environ[index] == NULL', source)
        self.assertIn('!strcmp(environ[index], probe_environment[index])', source)
        for bad in ('setenv(', 'putenv(', 'system(', 'popen(', 'execvp(', 'SIGCONT'):
            self.assertNotIn(bad, source)

    def test_clockfacts_and_executable_are_fixed_readonly(self):
        source = Path(__file__).with_name('policy_kind_counter_probe.c').read_text()
        for good in ('CLOCK_MONOTONIC', 'CLOCK_BOOTTIME', 'time_for_children',
                     '"/usr/local/bin/elixir"', '"/usr/local/lib/elixir/bin/elixir"',
                     'O_RDONLY | O_CLOEXEC | O_NOFOLLOW', 'before.st_uid == 0',
                     '!(before.st_mode & 0022)', 'probe-image-executable-shebang'):
            self.assertIn(good, source)
        self.assertNotIn('O_WRONLY', source)
        self.assertNotIn('O_CREAT', source)
        self.assertNotIn('chmod(', source)

    def test_original_source_freeze_preserved(self):
        root = Path(__file__).parents[1]
        review = json.loads((root/'verification/network-policy-kind40-counter19-source-preparation/review.json').read_bytes())
        raw = Path(__file__).with_name('policy_kind_counter.c').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), review['files']['tests/policy_kind_counter.c'])

if __name__ == '__main__': unittest.main()
