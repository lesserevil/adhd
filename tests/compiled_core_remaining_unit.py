"""Pure continuation guards; no Docker, VM or provider invocation."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import compiled_core_remaining as driver


class Guards(unittest.TestCase):
    def test_only_three_whole_prefix_programs_removed(self):
        names = ['foundation', 'wire', 'multi', 'store-move', 'move-no-default', 'hot']
        jobs = [{'name': n, 'arguments': [n]} for n in names]
        self.assertEqual(driver.rows({'jobs': jobs}), [jobs[2], jobs[4], jobs[5]])

    def test_workspace_retarget_preserves_other_arguments(self):
        self.assertEqual(driver.replace('/old/root/multi-work', '/old/root', '/new/root'), '/new/root/multi-work')
        for value in ['--deadline', '20', 'sha256:' + 'a' * 64, '/external/producer']:
            self.assertEqual(driver.replace(value, '/old/root', '/new/root'), value)

    def test_handles_only_actual_lifecycle_and_probe_records(self):
        cid = 'a' * 64
        report = {'publication': {'container_id': 'not-a-runtime'},
                  'runtime': {'container_lifecycle': [{'action': 'started', 'container_id': cid}],
                              'payload_probe_lifecycle': [{'owned_name': 'adhd-accept-probe-' + 'b' * 16,
                                                           'container_id': None}]}}
        self.assertEqual(driver.runtime_handles(report), [cid, 'adhd-accept-probe-' + 'b' * 16])

    def test_strict_absence_rejects_foreign_mixed_and_transport_failures(self):
        identifier = 'a' * 64
        env = {'DOCKER_HOST': 'unix:///reviewed/docker.sock', 'DOCKER_CONFIG': '/private/reviewed/config'}
        good = subprocess.CompletedProcess([], 1, b'[]\n', ('Error: No such object: ' + identifier + '\n').encode())
        with patch.object(driver.subprocess, 'run', return_value=good) as run, patch.dict('os.environ',
                {'DOCKER_HOST': 'tcp://untrusted.invalid:2375', 'DOCKER_CONTEXT': 'foreign'}):
            self.assertEqual(driver.absence(identifier, env)['identifier'], identifier)
            self.assertEqual(run.call_args.kwargs['env'], env)
            self.assertNotIn('DOCKER_CONTEXT', run.call_args.kwargs['env'])
        for code, err in [(0, good.stderr), (2, good.stderr),
                          (1, b'Cannot connect to daemon: No such object: ' + identifier.encode()),
                          (1, good.stderr + b'additional daemon failure'),
                          (1, b'Error: No such object: foreign')]:
            with patch.object(driver.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, b'[]', err)):
                with self.assertRaises(AssertionError): driver.absence(identifier, env)

    def test_changed_driver_rejected_before_loading_or_child(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp); (work / 'run.py').write_bytes(b'changed')
            with patch.object(driver, 'load') as load, patch.object(driver.subprocess, 'Popen') as child:
                with self.assertRaises(AssertionError): driver.verify(work, {'driver_sha256': '0' * 64})
                load.assert_not_called(); child.assert_not_called()

    def test_durable_once_marker_reentry_refused_before_child(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            body = json.dumps({'parent_guard': str(work)}).encode()
            (work / 'plan.json').write_bytes(body)
            (work / 'execution.started').write_bytes(b'original-once-marker')
            def exclusive(path, data):
                with path.open('xb') as stream: stream.write(data)
            args = SimpleNamespace(work=work, plan_sha256=hashlib.sha256(body).hexdigest())
            with patch.object(driver, '__file__', str(work / 'run.py')), patch.object(driver.sys, 'flags', SimpleNamespace(isolated=1)), \
                 patch.object(driver, 'verify', return_value=True), patch.object(driver, 'load', return_value=SimpleNamespace(write=exclusive)), \
                 patch.object(driver.subprocess, 'Popen') as child:
                with self.assertRaises(FileExistsError): driver.execute(args)
                child.assert_not_called()
            self.assertEqual((work / 'execution.started').read_bytes(), b'original-once-marker')


if __name__ == '__main__': unittest.main()
