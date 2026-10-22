#!/usr/bin/env python3
"""Pure custody/selection refusals. No hub/container/compiler/provider starts."""
import tempfile
import unittest
from subprocess import CompletedProcess
from types import SimpleNamespace
import json
import os
import stat
import hashlib
import importlib.util
from unittest.mock import patch
from pathlib import Path
from controlled_image_runtime import Custody,audit_models,regular,runtime_app_files,authoritative_absence as runtime_absent
from controlled_image_matrix import fileset,durable_once_marker,authoritative_absence as driver_absent

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
                         'Error response from daemon: No such container: owned-name\n','error: no such object: owned-name\n']:
                self.assertTrue(check(CompletedProcess([],1,b'[]\n',text.encode()),'owned-name'))
            self.assertFalse(check(CompletedProcess([],0,b'present',b''),'owned-name'))
    def test_foreign_mixed_daemon_or_nonexact_absence_refused(self):
        good=b'Error: No such object: owned-name\n'
        cases=[(2,b'[]\n',good),(125,b'',good),(1,b'[]\n',b'Error: No such object: other-name\n'),
               (1,b'[]\n',good+b'Cannot connect to the Docker daemon\n'),
               (1,b'[]\n',b'Cannot connect: no such socket\n'),(1,b'[]\n',good.rstrip()),
               (1,b'[]\n',b'Warning\n'+good),(1,b'not-json',good),(1,b'[]\n',b'error: no such object: OWNED-NAME\n')]
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

    def test_once_marker_fsyncs_file_then_parent_and_never_rewrites(self):
        with tempfile.TemporaryDirectory() as text:
            path=Path(text)/'started.json';calls=[];real=os.fsync
            def record(fd):
                calls.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
                return real(fd)
            with patch('controlled_image_matrix.os.fsync',side_effect=record):durable_once_marker(path,{'attempt':'one'})
            self.assertEqual(calls,['file','directory']);original=path.read_bytes()
            with self.assertRaises(FileExistsError):durable_once_marker(path,{'attempt':'two'})
            self.assertEqual(path.read_bytes(),original)
    def test_actual_execute_reentry_refuses_before_compiler_or_child(self):
        with tempfile.TemporaryDirectory() as text:
            root=Path(text).resolve();(root/'frozen').mkdir()
            driver=root/'run.py';driver.write_bytes(Path(__file__).with_name('controlled_image_matrix.py').read_bytes())
            spec=importlib.util.spec_from_file_location('test_owned_driver',driver)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            plan={'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),'frozen_inputs':{},'externals':{},'bound_inputs':{},
                  'runtime_cwd':str(root/'runtime'),'planned_suites':list(module.SUITES),
                  'jobs':[{'name':name,'expected_groups':count} for name,count in module.SUITES.items()]}
            (root/'plan.json').write_text(json.dumps(plan));expected=module.sha(root/'plan.json')
            marker=root/'started.json';durable_once_marker(marker,{'plan_sha256':expected});before=marker.read_bytes()
            with patch.object(module.subprocess,'run',side_effect=AssertionError('No compiler or child may be attempted')) as launch:
                with self.assertRaises(FileExistsError):module.execute(root,expected)
                launch.assert_not_called()
            self.assertEqual(marker.read_bytes(),before);self.assertFalse((root/'runtime').exists())

    def test_actual_custody_hash_argv_has_exact59_app_files(self):
        with tempfile.TemporaryDirectory() as text:
            custody=Custody.__new__(Custody);custody.image='sha256:expected';custody.plan={'expected_app_files':59}
            app={**{f'file{n}':'a'*64 for n in range(57)},'hub.exs':'b'*64,'LICENSE':'c'*64}
            custody.manifest={'files':{'Dockerfile':'d'*64,**app}};custody.manifest_bytes=json.dumps(custody.manifest).encode()
            custody.launches=[{'name':'owned-name'}];custody.ledger=Path(text)/'ledger.json';custody.name=lambda obj:'owned-name'
            row={'Id':'known-id','Image':custody.image,'State':{'Running':True,'Pid':123},
                 'HostConfig':{'PidMode':'','NetworkMode':'host','ReadonlyRootfs':True}}
            calls=[]
            def observe(*args,**kwargs):
                calls.append(args)
                if args==('inspect','owned-name'):raw=json.dumps([row]).encode()
                elif args==('exec','owned-name','cat','/app/manifest.json'):raw=custody.manifest_bytes
                elif args[:3]==('exec','owned-name','sha256sum'):
                    self.assertEqual(list(args[3:]),['/app/'+key for key in app])
                    raw=''.join(f'{value}  /app/{key}\n' for key,value in app.items()).encode()
                elif args==('exec','owned-name','readlink','/proc/1/exe'):raw=b'/runtime/beam.smp\n'
                elif args==('exec','owned-name','cat','/proc/1/status'):raw=b'Pid:\t1\n'
                elif args==('exec','owned-name','cat','/proc/1/cmdline'):raw=b'beam\0'
                else:self.fail('Unexpected custody command '+repr(args))
                return CompletedProcess([],0,raw,b'')
            custody.docker=observe;event={};custody.inspect_image(SimpleNamespace(),event)
            self.assertEqual(event['full_payload_files_verified'],59)
            self.assertFalse(any('/app/Dockerfile' in call for call in calls))
            self.assertEqual(runtime_app_files(custody.manifest,59),app)
            with self.assertRaises(AssertionError):runtime_app_files(custody.manifest,60)
    def test_staged_dockerfile_bytes_are_bound_without_starting_runtime(self):
        with tempfile.TemporaryDirectory() as text:
            root=Path(text);dockerfile=root/'staged-Dockerfile';dockerfile.write_bytes(b'actual staged build input')
            digest=hashlib.sha256(dockerfile.read_bytes()).hexdigest()
            manifest={'files':{'Dockerfile':digest,'hub.exs':'b'*64,**{f'file{n}':'a'*64 for n in range(58)}}}
            path=root/'manifest.json';path.write_text(json.dumps(manifest))
            plan={'image_config_identity':'sha256:expected','manifest':str(path),'fence_library':str(root/'fence.so'),
                  'staged_dockerfile':str(dockerfile),'bound_inputs':{dockerfile.name:digest},'expected_app_files':59}
            Custody(plan,{'launch_ledger':str(root/'launches.json')},root/'report.json')
            dockerfile.write_bytes(b'wrong build input')
            with self.assertRaisesRegex(AssertionError,'Staged Dockerfile'):Custody(plan,{'launch_ledger':str(root/'launches.json')},root/'report.json')

    def test_file_links_refused_before_start(self):
        with tempfile.TemporaryDirectory() as text:
            root=Path(text);(root/'a').write_bytes(b'a');(root/'symlink').symlink_to(root/'a')
            with self.assertRaises(AssertionError):fileset(root)
            with self.assertRaises(AssertionError):regular(root/'symlink')
            (root/'symlink').unlink();(root/'hardlink').hardlink_to(root/'a')
            with self.assertRaises(AssertionError):fileset(root)
            with self.assertRaises(AssertionError):regular(root/'a')


if __name__=='__main__':unittest.main()
