"""Executable update integrity, recovery and project isolation acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import adhd_skill_update as s


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.target = self.home/'scripts/adhd_skill_update.py'
        self.original = Path(s.__file__).read_bytes()
        s.write_bytes(self.target, self.original)
        self.old = hashlib.sha256(self.original).hexdigest()
        s.atomic(self.home/'adhd-skills/policy.json', dict(project_id='p', publisher_id='release',
                 agent_id='worker', channel='stable', runtime='test', mode='auto', helper=['unused']))
        text = self.original.decode() + '\n# upgraded fixture\n'
        self.m = dict(schema='adhd.bootstrap/1', sequence=1, version=s.BOOTSTRAP,
                      channel='stable', text=text, sha256=hashlib.sha256(text.encode()).hexdigest(),
                      predecessors=[self.old])
        self.seal()
        self.author = 'release'; self.project = 'p'; self.sent = []; self.fail_project = None
        self.u = s.Updater(self.home, self.hub)

    def seal(self):
        self.m['revision'] = s.digest({k:v for k,v in self.m.items() if k != 'revision'})

    def hub(self, cmd, mid=None):
        if cmd['op'] == 'search':
            return {'publications': [dict(author_id=self.author, project_id=self.project,
                information_type='adhd.bootstrap.release', data=self.m)]}
        if cmd['project_id'] == self.fail_project: raise RuntimeError('offline')
        self.sent.append((cmd, mid)); return {'publication': {'id': mid}}

    def test_upgrade_retry_and_recovery(self):
        result = self.u.bootstrap_sync(True)
        self.assertEqual(result['installed'], self.m['sha256'])
        self.assertEqual(self.u.bootstrap_sync(True)['installed'], result['installed'])
        self.u.bootstrap_recover(self.old)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.u.bootstrap_sync(True)['status'], 'pinned')

    def test_manual_policy_does_not_execute(self):
        self.assertEqual(self.u.bootstrap_sync()['status'], 'approval_required')
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_untrusted_author_and_project(self):
        for author, project in [('attacker','p'),('release','other')]:
            self.author, self.project = author, project
            with self.assertRaises(ValueError): self.u.bootstrap_sync(True)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_corrupt_manifest_and_payload(self):
        self.m['text'] += '# corrupt'
        with self.assertRaises(ValueError): self.u.bootstrap_sync(True)
        self.seal()
        with self.assertRaises(ValueError): self.u.bootstrap_sync(True)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_invalid_python_is_redacted_before_execution(self):
        self.m['text'] = 'invalid private-shaped-payload !'
        self.m['sha256'] = hashlib.sha256(self.m['text'].encode()).hexdigest(); self.seal()
        with self.assertRaises(ValueError) as error: self.u.bootstrap_sync(True)
        self.assertNotIn('private-shaped-payload', str(error.exception))
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_local_edits_preserved(self):
        self.target.write_bytes(self.original + b'# local')
        with self.assertRaises(ValueError): self.u.bootstrap_sync(True)
        self.assertTrue(self.target.read_bytes().endswith(b'# local'))

    def test_failed_probe_keeps_working_version(self):
        self.m['text'] = 'raise SystemExit(7)\n'
        self.m['sha256'] = hashlib.sha256(self.m['text'].encode()).hexdigest(); self.seal()
        with self.assertRaises(ValueError): self.u.bootstrap_sync(True)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse(self.target.with_name('.adhd-updater-stage.py').exists())

    def test_tampered_recovery_is_rejected(self):
        self.u.bootstrap_sync(True)
        (self.home/'adhd-skills/bootstraps'/self.old/'adhd_skill_update.py').write_text('tampered')
        with self.assertRaises(ValueError): self.u.bootstrap_recover(self.old)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), self.m['sha256'])

    def test_seed_recovers_an_unstartable_updater(self):
        import install_adhd_bootstrap as seed
        self.u.bootstrap_sync(True)
        self.target.write_bytes(b'broken Python syntax ?')
        seed.recover(self.home, self.old)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(s.read_json(self.u.root/'policy.json')['bootstrap_pin'], self.old)

    def test_interrupted_after_replace_can_finish(self):
        from unittest.mock import patch
        original_atomic = s.atomic
        def interrupt(path, value):
            if path.name == 'bootstrap.json' and value.get('status') == 'installed':
                raise OSError('simulated power loss after replacement')
            original_atomic(path, value)
        with patch.object(s, 'atomic', side_effect=interrupt):
            with self.assertRaises(OSError): self.u.bootstrap_sync(True)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), self.m['sha256'])
        self.assertEqual(self.u.bootstrap_sync(True)['status'], 'installed')

    def test_sequence_regression(self):
        self.m['sequence'] = 2; self.seal(); self.u.bootstrap_sync(True)
        self.m['sequence'] = 1; self.seal()
        with self.assertRaises(ValueError): self.u.bootstrap_sync(True)

    def test_project_reports_redact_source_demonstrations_and_retry(self):
        self.u.policy['report_projects'] = ['p','q']
        self.u.state = {'installed': 'abc', 'status': 'active_session_observed',
            'sessions': {'turn': {'revision': 'abc', 'observed_at': 'now',
                                 'demonstration': {'publication_id': 'private-to-p'}}}}
        self.fail_project = 'q'
        with self.assertRaises(RuntimeError): self.u.report()
        self.assertEqual(len(self.sent), 1)
        pending = list((self.u.root/'outbox').glob('*.json')); self.assertEqual(len(pending), 1)
        saved = json.loads(pending[0].read_text())
        self.assertNotIn('private-to-p', json.dumps(saved))
        self.fail_project = None; self.u.report()
        self.assertEqual(self.sent[-1][1], saved['message_id'])
        self.assertEqual(len(self.sent), 2)
        self.u.report(); self.assertEqual(len(self.sent), 2)

if __name__ == '__main__': unittest.main()
