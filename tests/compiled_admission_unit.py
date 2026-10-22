"""No processes: exact compiled admission identity/member binding negatives."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

class Admission(unittest.TestCase):
    def test_both_preparers_reject_cross_image_and_unclosed_members(self):
        image = 'sha256:' + 'a' * 64
        artifact, context, cache = 'b' * 64, 'c' * 64, 'd' * 64
        good = {'schema': 'adhd/compiled40-admission-and-image-binding@1', 'passed': True,
                'image_config_identity': image, 'artifact_sha256': artifact,
                'canonical_manifest_sha256': context,
                'compiled_runtime_audit': {'passed': True, 'image_id': image,
                    'artifact_sha256': artifact, 'canonical_manifest_sha256': context,
                    'cache_modules': 59, 'cache_entries': 65, 'cache_manifest_sha256': cache},
                'files': {'cache-manifest.json': cache}}
        mutations = [lambda x: x.update(passed=False),
                     lambda x: x.update(image_config_identity='sha256:' + 'e' * 64),
                     lambda x: x.update(artifact_sha256='e' * 64),
                     lambda x: x['compiled_runtime_audit'].update(canonical_manifest_sha256='e' * 64),
                     lambda x: x['compiled_runtime_audit'].update(cache_modules=58),
                     lambda x: x['files'].update({'cache-manifest.json': 'e' * 64}),
                     lambda x: x['files'].update({'../escape': cache}),
                     lambda x: x['files'].update({'manifest.json': cache})]
        with patch('subprocess.run', side_effect=AssertionError('process forbidden')), patch('subprocess.Popen', side_effect=AssertionError('process forbidden')):
            for filename in ('container_cache_acceptance.py', 'image_filesystem_abi.py'):
                spec = importlib.util.spec_from_file_location(filename, Path(__file__).with_name(filename))
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                self.assertEqual(module.validate_compiled_admission(good, image, artifact, context), good['compiled_runtime_audit'])
                for i, mutate in enumerate(mutations):
                    bad = copy.deepcopy(good); mutate(bad)
                    with self.subTest(module=filename, negative=i), self.assertRaises(AssertionError):
                        module.validate_compiled_admission(bad, image, artifact, context)

if __name__ == '__main__': unittest.main()
