"""Execute the authored external-edit block without a hub, network, or real sleeps."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).with_name('foundation_acceptance.py')
RECORD = 'atomic-external-file-reload-and-invalid-update-retains-last-good'


def external_block():
    tree = ast.parse(SOURCE.read_text())
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if not isinstance(body, list):
            continue
        for end, statement in enumerate(body):
            if (isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Call)
                    and isinstance(statement.value.func, ast.Name)
                    and statement.value.func.id == 'record'
                    and statement.value.args
                    and isinstance(statement.value.args[0], ast.Constant)
                    and statement.value.args[0].value == RECORD):
                start = next(i for i in range(end - 1, -1, -1)
                             if ast.unparse(body[i]) == 'cfg = runtime.config')
                # The last assignment is the repair; include the earlier edit too.
                start = next(i for i in range(start - 1, -1, -1)
                             if ast.unparse(body[i]) == 'cfg = runtime.config')
                return copy.deepcopy(body[start:end + 1])
    raise AssertionError('Actual external-edit block missing')


class ReloadSchedule:
    def __init__(self, root):
        self.root = root
        self.file = root / 'hub.json'
        self.live = {'config_revision': 17, 'threshold_ppm': 875000,
                     'auth': {'mode': 'local'}}
        self.file.write_text(json.dumps(self.live))
        self.now = 0.0
        self.calls = []
        self.accepted = []
        self.invalid = 0
        self.observed_pending = False

    @property
    def config(self):
        return json.loads(self.file.read_text())

    def reconcile(self):
        candidate = self.config
        if type(candidate['threshold_ppm']) is not int:
            self.invalid += 1
            return
        if candidate != self.live:
            candidate['config_revision'] = self.live['config_revision'] + 1
            candidate['normalized'] = {'accepted': True}
            self.live = candidate
            self.file.write_text(json.dumps(candidate))
            self.accepted.append(copy.deepcopy(candidate))

    def api(self, command):
        self.calls.append(copy.deepcopy(command))
        assert command == {'op': 'config_get'}
        # First observation races the asynchronous reload, exactly as the loop allows.
        if not self.observed_pending:
            self.observed_pending = True
        else:
            self.reconcile()
        return {'config': copy.deepcopy(self.live)}

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration
        self.reconcile()


def execute(block):
    with tempfile.TemporaryDirectory() as directory:
        runtime = ReloadSchedule(Path(directory))
        records = []
        module = ast.fix_missing_locations(ast.Module(body=block, type_ignores=[]))
        exec(compile(module, str(SOURCE), 'exec'),
             {'runtime': runtime, 'admin': runtime, 'time': runtime,
              'json': json, 'record': records.append})
        runtime.final_file = runtime.config
        return runtime, records


class ExternalReloadFixtureTest(unittest.TestCase):
    def test_actual_block_restores_accepted_full_snapshot(self):
        runtime, records = execute(external_block())
        self.assertEqual(records, [RECORD])
        self.assertEqual(runtime.live['config_revision'], 18)
        self.assertEqual(runtime.live['normalized'], {'accepted': True})
        self.assertEqual(runtime.final_file, runtime.live)
        self.assertEqual(len(runtime.accepted), 1)
        self.assertGreater(runtime.invalid, 0)
        self.assertEqual(runtime.calls, [{'op': 'config_get'}] * 3)
        self.assertAlmostEqual(runtime.now, 1.5)

    def test_predecessor_restores_stale_snapshot_and_advances_revision(self):
        block = external_block()
        refreshes = [i for i, node in enumerate(block)
                     if ast.unparse(node) == 'cfg = runtime.config']
        self.assertEqual(len(refreshes), 2)
        predecessor = copy.deepcopy(block)
        del predecessor[refreshes[-1]]
        # The amendment changes no original assertion, loop, deadline, or sleep.
        for kind in (ast.Assert, ast.While, ast.Call):
            def selected(nodes):
                return [ast.dump(n) for s in nodes for n in ast.walk(s)
                        if isinstance(n, kind)]
            self.assertEqual(selected(block), selected(predecessor))
        runtime, records = execute(predecessor)
        self.assertEqual(records, [RECORD])  # Original threshold assertion still passes.
        self.assertEqual(runtime.live['config_revision'], 19)
        self.assertEqual(len(runtime.accepted), 2)
        self.assertEqual(runtime.accepted[0]['config_revision'], 18)
        self.assertGreater(runtime.invalid, 0)


if __name__ == '__main__':
    unittest.main()
