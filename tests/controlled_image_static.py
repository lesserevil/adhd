#!/usr/bin/env python3
"""Pure custody/selection refusals. No hub/container/compiler/provider starts."""
import tempfile
import unittest
from pathlib import Path
from controlled_image_runtime import audit_models,regular
from controlled_image_matrix import fileset

URL='http://127.0.0.1:19001/v1/systemone'


class Preparation(unittest.TestCase):
    def test_nested_effective_model_selection(self):
        config={'matcher':{'url':URL,'model':'typed'},'projects':[{'settings':{'archive':{'assessment':{'url':URL}}}}]}
        result=audit_models(config,{URL})
        self.assertEqual(len(result),2)
        self.assertEqual(result[1]['path'],['projects','0','settings','archive','assessment','url'])
    def test_external_alias_redirect_and_provider_refusals(self):
        for value in ['http://127.0.0.1:18770/v1/systemone','http://localhost:19001/v1/systemone',
                      'http://other.example/v1/systemone','https://127.0.0.1:19001/v1/systemone',
                      URL+'?redirect=18770',URL+'#alias','http://user:pass@127.0.0.1:19001/v1/systemone']:
            for key in ['url','endpoint','base_url','model_url','endpoint_url','unknown_alias']:
                with self.subTest(value=value,key=key),self.assertRaises(AssertionError):
                    audit_models({'projects':[{'settings':{'history':{key:value}}}]},{URL,value})
    def test_inactive_or_unregistered_fixture_refused(self):
        with self.assertRaises(AssertionError):audit_models({'matcher':{'url':URL}},set())
        with self.assertRaises(AssertionError):audit_models({'matcher':{'url':URL.replace('19001','19002')}},{URL})
    def test_full_fileset_catches_extra_and_changed_files(self):
        with tempfile.TemporaryDirectory() as text:
            root=Path(text);(root/'a').write_bytes(b'a');first=fileset(root)
            (root/'b').write_bytes(b'b');self.assertNotEqual(fileset(root),first)
            (root/'b').unlink();(root/'a').write_bytes(b'changed');self.assertNotEqual(fileset(root),first)
    def test_file_links_refused_before_start(self):
        with tempfile.TemporaryDirectory() as text:
            root=Path(text);(root/'a').write_bytes(b'a');(root/'symlink').symlink_to(root/'a')
            with self.assertRaises(AssertionError):fileset(root)
            with self.assertRaises(AssertionError):regular(root/'symlink')
            (root/'symlink').unlink();(root/'hardlink').hardlink_to(root/'a')
            with self.assertRaises(AssertionError):fileset(root)
            with self.assertRaises(AssertionError):regular(root/'a')


if __name__=='__main__':unittest.main()
