"""Exercise actual method-only security checks without importing services."""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).with_name('protocol_acceptance.py')
METHODS=('get','put','post','delete','options','head','patch','trace')

def check(api):
    tree=ast.parse(SOURCE.read_text())
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_operation_security')
    scope={};exec(compile(ast.Module(body=[helper],type_ignores=[]),str(SOURCE),'exec'),scope)
    scope['validate_operation_security'](api)

class PathItemSecurity(unittest.TestCase):
    def api(self):
        metadata={'parameters':[{'name':'token','in':'path','required':True,'schema':{'type':'string'}}],
                  '$ref':'#/components/pathItems/base','summary':'challenge','description':'public HTTP01',
                  'servers':[{'url':'http://localhost:8080'}],'x-adhd-listener':'challenge'}
        return {'paths':{'/challenge':{**metadata,**{m:{'security':[{'session':[]}]} for m in METHODS}}},
                'components':{'securitySchemes':{'session':{}}}}
    def test_path_metadata_is_not_operation(self):check(self.api())
    def test_each_method_security_reference_is_checked(self):
        for method in METHODS:
            with self.subTest(method=method):
                api=self.api();api['paths']['/challenge'][method]['security']=[{'unknown':[]}]
                with self.assertRaises(AssertionError):check(api)
    def test_malformed_actual_operation_not_silently_skipped(self):
        api=self.api();api['paths']['/challenge']['post']=[]
        with self.assertRaises(AttributeError):check(api)

if __name__=='__main__':unittest.main()
