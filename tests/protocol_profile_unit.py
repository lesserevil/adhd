"""Pure profile selection/conservation checks; never import or run the wire fixture."""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).with_name('protocol_acceptance.py')

class ProfileSelection(unittest.TestCase):
    def setUp(self):
        self.text = SOURCE.read_text()
        self.tree = ast.parse(self.text)
    def test_choices_and_default(self):
        call = next(n for n in ast.walk(self.tree) if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == '--profile-version')
        values = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
        self.assertEqual(values['choices'], ['1.7.0', '2.0.0', '2.1.0', '2.2.0'])
        self.assertEqual(values['default'], '2.1.0')
    def test_multi_profile_and_legacy_foundations(self):
        multi = next(n.value for n in ast.walk(self.tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'multi_profile' for t in n.targets))
        assertion = next(n for n in ast.walk(self.tree) if isinstance(n, ast.Assert) and ast.unparse(n.test).startswith("fixtures['profile_version'] in"))
        allowed = {'1.7.0': ['1.7.0'], '2.0.0': ['1.7.0','2.0.0'], '2.1.0': ['1.7.0','2.0.0','2.1.0'], '2.2.0': ['1.7.0','2.0.0','2.1.0','2.2.0']}
        for version, foundations in allowed.items():
            env = {'args': SimpleNamespace(profile_version=version)}
            env['multi_profile'] = eval(compile(ast.Expression(multi), str(SOURCE), 'eval'), env)
            self.assertEqual(env['multi_profile'], version != '1.7.0')
            for fixture in list(allowed) + ['3.0.0']:
                env['fixtures'] = {'profile_version': fixture}
                actual = eval(compile(ast.Expression(assertion.test), str(SOURCE), 'eval'), env)
                self.assertEqual(actual, fixture in foundations, (version, fixture))
    def test_recovery_inventory_preserved_in22(self):
        branch = next(n for n in ast.walk(self.tree) if isinstance(n, ast.If) and n.body and isinstance(n.body[0], ast.Assert) and "urn:adhd:protocol:" in ast.unparse(n.body[0]))
        defs = {'ProjectRecoveryRebindCLI': {}, 'AdminCommand': {'oneOf': []}}
        for op in ('project_restore_plan','project_restore_apply','project_restore_status'):
            defs['admin_'+op] = {}; defs['admin_result_'+op] = {}
        for version in ('2.1.0','2.2.0'):
            env = {'args': SimpleNamespace(profile_version=version), 'schema': {'$id': 'urn:adhd:protocol:'+version.rsplit('.',1)[0], '$defs': defs}}
            exec(compile(ast.Module([branch], type_ignores=[]), str(SOURCE), 'exec'), env)
            env['schema']['$id'] = 'urn:adhd:protocol:WRONG'
            with self.assertRaises(AssertionError):
                exec(compile(ast.Module([branch], type_ignores=[]), str(SOURCE), 'exec'), env)
    def test_only_target_selection_changed(self):
        # Undo the separately reviewed method-only PathItem traversal repair.
        tree = ast.parse(self.text)
        helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='validate_operation_security')
        source_lines = self.text.splitlines(keepends=True)
        s = ''.join(source_lines[:helper.lineno-1]+source_lines[helper.end_lineno:])
        s = s.replace('        validate_operation_security(api)', "        for path in api['paths'].values():\n            for operation in path.values():\n                for requirement in operation.get('security',[]):\n                    assert set(requirement)<=set(api['components']['securitySchemes'])")
        # Undo only the five reviewed target-selection edits, then bind the whole
        # original syntax tree: assertions, calls, deadlines, group order stay.
        s = s.replace("choices=['1.7.0','2.0.0','2.1.0','2.2.0']", "choices=['1.7.0','2.0.0','2.1.0']")
        s = s.replace("multi_profile=args.profile_version in ('2.0.0','2.1.0','2.2.0')", "multi_profile=args.profile_version in ('2.0.0','2.1.0')")
        s = s.replace("({'1.7.0','2.0.0','2.1.0','2.2.0'} if args.profile_version=='2.2.0' else ", '(')
        s = s.replace("if args.profile_version in ('2.1.0','2.2.0'):\n            assert schema['$id']=='urn:adhd:protocol:'+args.profile_version.rsplit('.',1)[0]", "if args.profile_version=='2.1.0':\n            assert schema['$id']=='urn:adhd:protocol:2.1'")
        s = s.replace("runtime=Runtime(root/'hub',command,args.image,initialization_schema='urn:adhd:protocol:2.2' if args.profile_version=='2.2.0' else 'urn:adhd:protocol:2.1');model=ModelFixture();cases=[]", "runtime=Runtime(root/'hub',command,args.image);model=ModelFixture();cases=[]")
        self.assertEqual(hashlib.sha256(ast.dump(ast.parse(s)).encode()).hexdigest(), '00a770e42c733590ef88cdea3276d8001404b82ec05746bd635e7189684a8667')
        records = [n for n in ast.walk(self.tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='record']
        self.assertEqual(len(records),8)

if __name__ == '__main__':
    unittest.main()
