import ast
import copy
import json
from pathlib import Path
import unittest
import image_kafka_matrix as target


class DiagnosticSelector(unittest.TestCase):
    def test_original_default_and_federation_contract(self):
        self.assertEqual(len(target.NAMES), 14)
        self.assertEqual(sum(target.COUNTS.values()), 68)
        self.assertEqual(target.COUNTS['federation'], 14)
        plan = json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/kafka41-compiled01/plan.json').read_text())
        native=json.loads(Path('/home/horde/src/adhd/.worktrees/deployment/_build/kafka41-compiled01/bound/native-plan.json').read_text())
        full=target.complete_jobs(native)
        selected=[r for r in full if r['name']=='federation']
        self.assertEqual(len(selected),1)
        original=next(j for j in plan['jobs'] if j['name']=='federation')
        self.assertEqual(selected[0]['arguments'],original['native_basis_arguments'])
        args=target.private_rest_arguments(selected[0]['arguments'],18089)
        self.assertEqual(json.loads(args[args.index('--eventing-rest-urls')+1]),
            ['http://127.0.0.1:18082','http://127.0.0.1:18085','http://127.0.0.1:18089'])

    def test_closed_selector_and_full_verify_preserved(self):
        self.assertEqual(target.diagnostic_names(True), ['federation'])
        self.assertEqual(target.diagnostic_names(False), target.NAMES)
        for bad in (1, 0, 'federation', [], None):
            with self.assertRaises(AssertionError):target.diagnostic_names(bad)
        tree=ast.parse(Path(target.__file__).read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify')
        fragment=ast.get_source_segment(Path(target.__file__).read_text(),fn)
        self.assertIn("[COUNTS[n] for n in names]",fragment)
        for call in ('check_tree', 'tool_tree', 'target_bindings'):
            self.assertIn(call,fragment)

if __name__=='__main__':unittest.main()
