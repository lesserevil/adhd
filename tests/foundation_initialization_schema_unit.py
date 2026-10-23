"""Mock public project admission; no hub, model, broker, browser or process."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('foundation_fixture',Path(__file__).with_name('foundation_acceptance.py'))
foundation=importlib.util.module_from_spec(spec);spec.loader.exec_module(foundation)

class Initialization(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.calls=[];self.actual_schema='urn:adhd:protocol:2.2';self.availability='uninitialized'
        owner=self
        class PublicClient:
            def __init__(self,runtime,bearer=None):self.bearer=bearer
            def get(self,path):
                owner.calls.append(('get',path));return 200,{'$id':owner.actual_schema},{}
            def api(self,body,**kwargs):
                owner.calls.append(('api',dict(body),kwargs))
                op=body['op']
                if op=='list_projects':return {'projects':[{'id':'red'}]}
                if op=='config_get':return {'config_revision':11}
                if op=='project_restore_status':
                    identity=body.get('operation_id')
                    if not identity:return {'availability':owner.availability}
                    if identity=='plan':return {'operation':{'state':'ready','plan':{'plan_id':'plan-id','plan_sha256':'a'*64}}}
                    if identity=='apply':return {'operation':{'state':'complete','result':{'initialized':True}}}
                if op in ('project_restore_plan','project_restore_apply'):
                    assert body['mode']=='initialize' if op.endswith('plan') else body['plan_id']=='plan-id'
                    assert body['expected_revision']==11 and body['confirm'] is True
                    return {'operation_id':'plan' if op.endswith('plan') else 'apply'}
                raise AssertionError('Unexpected public operation')
        self.addCleanup(patch.stopall)
        patch.object(foundation,'Client',PublicClient).start()
        for name in ('run','Popen','check_output'):
            patch('subprocess.'+name,side_effect=AssertionError('Process forbidden')).start()
    def runtime(self,**kwargs):
        r=foundation.Runtime(Path(self.temp.name)/'fixture',[],**kwargs)
        r.file.write_text(json.dumps({'admin_token':'synthetic-test-token','eventing':{'enabled':False}}))
        return r
    def operations(self):return [r[1]['op'] for r in self.calls if r[0]=='api']
    def test_default21_skips22_unchanged(self):
        r=self.runtime();self.assertEqual(r.initialization_schema,'urn:adhd:protocol:2.1')
        r.initialize_unknown_projects();self.assertEqual(self.operations(),[])
    def test_default21_still_initializes21_publicly(self):
        self.actual_schema='urn:adhd:protocol:2.1';self.runtime().initialize_unknown_projects()
        self.assertEqual(self.operations().count('project_restore_plan'),1)
        self.assertEqual(self.operations().count('project_restore_apply'),1)
    def test_explicit22_initializes_unknown_publicly(self):
        self.runtime(initialization_schema='urn:adhd:protocol:2.2').initialize_unknown_projects()
        self.assertEqual(self.operations(),['list_projects','project_restore_status','config_get','project_restore_plan','project_restore_status','project_restore_apply','project_restore_status','config_get'])
    def test_known_missing_never_initialized(self):
        self.availability='recovery_required';r=self.runtime(initialization_schema='urn:adhd:protocol:2.2')
        with self.assertRaisesRegex(AssertionError,'must not initialize'):r.initialize_unknown_projects()
        self.assertNotIn('project_restore_plan',self.operations());self.assertNotIn('project_restore_apply',self.operations())
    def test_ready_project_skips_initialize(self):
        self.availability='ready';self.runtime(initialization_schema='urn:adhd:protocol:2.2').initialize_unknown_projects()
        self.assertEqual(self.operations(),['list_projects','project_restore_status'])
    def test_explicit_disable_still_skips(self):
        self.runtime(initialize_projects=False,initialization_schema='urn:adhd:protocol:2.2').initialize_unknown_projects()
        self.assertEqual(self.calls,[])
    def test_protocol_only_explicit22_opts_in(self):
        tree=ast.parse(Path(__file__).with_name('protocol_acceptance.py').read_text())
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='Runtime')
        expr=next(k.value for k in call.keywords if k.arg=='initialization_schema')
        for version in ('1.7.0','2.0.0','2.1.0','2.2.0'):
            self.assertEqual(eval(compile(ast.Expression(expr),'protocol','eval'),{'args':SimpleNamespace(profile_version=version)}),'urn:adhd:protocol:2.2' if version=='2.2.0' else 'urn:adhd:protocol:2.1')

if __name__=='__main__':unittest.main()
