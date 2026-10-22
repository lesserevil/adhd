#!/usr/bin/env python3
"""Pure custody/selection refusals. No hub/container/compiler/provider starts."""
import tempfile
import unittest
from subprocess import CompletedProcess
from types import SimpleNamespace
import json
from pathlib import Path
from controlled_image_runtime import Custody,audit_models,regular,authoritative_absence as runtime_absent
from controlled_image_matrix import fileset,authoritative_absence as driver_absent

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
    def test_only_authoritative_exact_missing_object_accepted(self):
        for check in [runtime_absent,driver_absent]:
            for text in ['Error: No such object: owned-name\n','Error: No such container: owned-name\n',
                         'Error response from daemon: No such container: owned-name\n']:
                self.assertTrue(check(CompletedProcess([],1,b'[]\n',text.encode()),'owned-name'))
            self.assertFalse(check(CompletedProcess([],0,b'present',b''),'owned-name'))
    def test_foreign_mixed_daemon_or_nonexact_absence_refused(self):
        good=b'Error: No such object: owned-name\n'
        cases=[(2,b'[]\n',good),(125,b'',good),(1,b'[]\n',b'Error: No such object: other-name\n'),
               (1,b'[]\n',good+b'Cannot connect to the Docker daemon\n'),
               (1,b'[]\n',b'Cannot connect: no such socket\n'),(1,b'[]\n',good.rstrip()),
               (1,b'[]\n',b'Warning\n'+good),(1,b'not-json',good)]
        for check in [runtime_absent,driver_absent]:
            for code,out,err in cases:
                with self.subTest(code=code,err=err),self.assertRaises(AssertionError):
                    check(CompletedProcess([],code,out,err),'owned-name')

    def test_known_container_replacement_refused_before_mutation(self):
        custody=Custody.__new__(Custody);custody.image='sha256:expected'
        custody.is_image=lambda obj:True;custody.name=lambda obj:'owned-name'
        calls=[]
        def inspect_only(*args,**kw):
            calls.append(args)
            self.assertEqual(args,('inspect','owned-name'))
            row={'Id':'foreign-id','Image':'sha256:expected','Mounts':[{'Source':'/owned'}]}
            return CompletedProcess([],0,json.dumps([row]).encode(),b'')
        custody.docker=inspect_only
        obj=SimpleNamespace(root=Path('/owned'),process=None,logs=[],
            _controlled_custody_attempt={'container_name':'owned-name','container_id':'known-id'})
        with self.assertRaisesRegex(AssertionError,'different container'):custody.cleanup_one(obj)
        self.assertEqual(calls,[('inspect','owned-name')])

    def test_file_links_refused_before_start(self):
        with tempfile.TemporaryDirectory() as text:
            root=Path(text);(root/'a').write_bytes(b'a');(root/'symlink').symlink_to(root/'a')
            with self.assertRaises(AssertionError):fileset(root)
            with self.assertRaises(AssertionError):regular(root/'symlink')
            (root/'symlink').unlink();(root/'hardlink').hardlink_to(root/'a')
            with self.assertRaises(AssertionError):fileset(root)
            with self.assertRaises(AssertionError):regular(root/'a')


if __name__=='__main__':unittest.main()
