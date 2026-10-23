"""Fresh schema2 guards on synthetic bytes; no compiler/image/CA/process starts."""
import copy
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load(name):
    path=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

cache=load('container_cache_acceptance');abi=load('image_filesystem_abi')
spec=importlib.util.spec_from_file_location('stage',Path(__file__).resolve().parents[1]/'scripts/stage_container.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)


class Guards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.context=self.root/'context'
        self.source=b'defmodule ADHD.ACMEClient do\nend\ndefmodule ADHD.TLS do\nend\n'
        tools={n:b'synthetic pinned metadata' for n in cache.ACME_FILES-{'acme-pins.json','acme-bundle.json'}}
        pins={'runtime_bundle':{'files':{n:cache.sha(b) for n,b in tools.items()}}}
        tools['acme-pins.json']=json.dumps(pins).encode()
        tools['acme-bundle.json']=json.dumps({'schema':'adhd/acme-runtime-bundle@1','platform':'linux_amd64','files':{n:cache.sha(b) for n,b in tools.items()}}).encode()
        stage.write_context({'Dockerfile':b'ENTRYPOINT ["elixir", "/runtime/adhd/boot.exs", "/app/hub.exs"]',
                             'hub.exs':self.source},self.context,{'boot.exs':b'boot','build.exs':b'build',**tools})
        self.artifact=cache.sha(self.source);self.manifest=cache.sha((self.context/'manifest.json').read_bytes())
        self.target,_=cache.target_binding(self.context,self.manifest,self.artifact)
        self.binding,_,_=abi.acme_context(self.context,self.manifest,self.artifact)
        self.image='sha256:'+'a'*64
        self.admission={'schema':'adhd/compiled40-admission-and-image-binding@1','passed':True,
            'image_config_identity':self.image,'artifact_sha256':self.artifact,'canonical_manifest_sha256':self.manifest,
            'compiled_runtime_audit':{'passed':True,'image_id':self.image,'artifact_sha256':self.artifact,
                'canonical_manifest_sha256':self.manifest,'cache_modules':2,'cache_entries':16,'cache_manifest_sha256':'f'*64},
            'files':{'cache-manifest.json':'f'*64}}
        for name in ['run','Popen','check_output']:
            self.addCleanup(patch.stopall)
            patch('subprocess.'+name,side_effect=AssertionError('Processes forbidden')).start()

    def test_context_derives_exact_order_tools_and_validator_bytes(self):
        self.assertEqual(self.target['modules'],['Elixir.ADHD.ACMEClient','Elixir.ADHD.TLS'])
        self.assertEqual(set(self.target['acme']),cache.ACME_FILES)
        self.assertEqual(self.binding['payload_counts']['modules'],self.target['modules'])
        self.assertEqual(cache.target_binding(self.context,self.manifest,self.artifact)[1],
                         Path(cache.__file__).with_name('image_compiled_inputs.py').read_bytes())

    def test_both_new_admissions_reject_historical_counts_and_boolean(self):
        for key,value in [('cache_modules',59),('cache_entries',65),('cache_modules',True),('cache_entries',16.0)]:
            bad=copy.deepcopy(self.admission);bad['compiled_runtime_audit'][key]=value
            with self.subTest(key=key,value=value):
                with self.assertRaises(AssertionError):cache.validate_compiled_admission(bad,self.image,self.artifact,self.manifest,target=self.target)
                with self.assertRaises(AssertionError):abi.validate_compiled_admission(bad,self.image,self.artifact,self.manifest,binding=self.binding)
        for m,kw in [(cache,{'target':self.target}),(abi,{'binding':self.binding})]:
            self.assertEqual(m.validate_compiled_admission(self.admission,self.image,self.artifact,self.manifest,**kw),self.admission['compiled_runtime_audit'])
            with self.assertRaises(AssertionError):m.validate_compiled_admission(self.admission,self.image,self.artifact,self.manifest)

    def test_new_source_binding_rejects_changed_context_not_just_counts(self):
        for filename in ['compiler-inputs.json','packaging.tar','payload.tar']:
            p=self.context/filename;raw=p.read_bytes();p.write_bytes(raw+b'drift' if filename=='compiler-inputs.json' else b'bad archive')
            for m in [cache.target_binding,abi.acme_context]:
                with self.assertRaises((AssertionError,ValueError,tarfile.ReadError)):m(self.context,self.manifest,self.artifact)
            p.write_bytes(raw)

    def test_new_target_requires_full_admission_explicit_native_count_no_prefix(self):
        for admission,prefix,count in [(None,None,8),('given',None,None),('given',None,True),('given','old',8),('given',None,0)]:
            work=self.root/'never-created'
            args=SimpleNamespace(work=work,image=self.image,context=self.context,cache_root_mode=0o555,
                admission_manifest=admission,prefix_work=prefix,native_checks=count)
            with self.assertRaises(AssertionError):cache.prepare(args)
            self.assertFalse(work.exists())

    def test_tool_mutations_only_change_named_member(self):
        files={'adhd/ebin/Elixir.ADHD.TLS.beam':(b'beam',0o444,tarfile.REGTYPE,''),
               'adhd/lego':(b'client',0o555,tarfile.REGTYPE,''),'adhd/acme-guard':(b'guard',0o555,tarfile.REGTYPE,'')}
        for name in cache.ACME_CASES:
            if name.startswith('missing-'):
                with self.assertRaises(AssertionError):cache.mutation(files,name)
            else:
                altered=cache.mutation(files,name)
                changed=[k for k in files if files[k]!=altered[k]]
                self.assertEqual(changed,['adhd/acme-guard' if name=='changed-acme-guard' else 'adhd/lego'])
                if name=='nonexecutable-lego':self.assertEqual(altered['adhd/lego'],(b'client',0o444,tarfile.REGTYPE,''))
        self.assertEqual(files['adhd/lego'][1],0o555)

    def plan(self):
        return {'acme':self.target['acme'],'admission':{'bound':True},'target_validator_sha256':'a'*64,
            'expected_modules':self.target['modules'],'native_checks':8,'native_case_label':'source-native8',
            'cases':list(cache.CASES)+list(cache.ACME_CASES)}

    def test_execute_selection_rejects_subset_prefix_native_count_and_unknown_tool(self):
        plan=self.plan();cache.selection_contract(plan)
        for change in [lambda p:p.update(cases=list(cache.CASES)),lambda p:p.update(prefix={'old':True}),
                       lambda p:p.update(native_checks=True),lambda p:p.update(native_case_label='original-native18'),
                       lambda p:p['acme'].update({'extra':'a'*64}),lambda p:p.update(admission=None)]:
            bad=copy.deepcopy(plan);change(bad)
            with self.assertRaises(AssertionError):cache.selection_contract(bad)

    def test_historical_selection_and_prefix_stay_original(self):
        plan={'expected_modules':['Elixir.M'+str(i) for i in range(59)],'cases':list(cache.CASES)}
        cache.selection_contract(plan)
        plan.update(prefix={'old':True},cases=list(cache.CASES[4:]));cache.selection_contract(plan)
        with self.assertRaises(AssertionError):cache.validate_compiled_admission(self.admission,self.image,self.artifact,self.manifest)
        empty=self.root/'noncompiled';empty.mkdir();self.assertEqual(abi.acme_context(empty,'x','y'),(None,None,None))

    def test_large_limit_only_for_named_acme_executables(self):
        body=b'x'*(8*1024*1024+1)
        for name in ['adhd/lego','adhd/acme-guard','adhd/foreign']:
            data=cache.archive({name:(body,0o555,tarfile.REGTYPE,'')})
            for inspect in [cache.inspect_archive,cache.archive_witness]:
                with self.assertRaises(AssertionError):inspect(data)
                if name=='adhd/foreign':
                    with self.assertRaises(AssertionError):inspect(data,True)
                else:self.assertTrue(inspect(data,True))

    def test_physical_abi_family_cases_are_original_and_optional_19(self):
        self.assertEqual(sum(map(len,abi.selected_families().values())),18)
        all19=abi.selected_families(list(abi.FAMILIES)+['config_rename_fault.c'])
        self.assertEqual(sum(map(len,all19.values())),19)
        self.assertEqual(all19['project_recovery_fault.c'],('rename','fsync','link','unlink'))
        self.assertEqual(all19['rebind_fault.c'],('rename','fsync'))

if __name__=='__main__':unittest.main()
