import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import adhd_setup as setup
import adhd_skill_update as skills


def record():
    return dict(schema='adhd.setup/1', kind='readiness', record_id='r1', subject='compiler',
                activity='build', platform='linux', project_revision='abc', observed_at='2026-11-03T00:00:00Z',
                state='verified', evidence=['compiler --version exited 0'], related=[], supersedes=[],
                details={'checks': ['compiler executable works'], 'limitations': ['build untested']})


def release(sequence=1, minimum=1, revoked=()):
    m = {'schema': 'adhd.skills/1', 'sequence': sequence, 'min_bootstrap': minimum, 'channel': 'stable',
         'notes': 'fixture', 'revoked': list(revoked), 'files': {}}
    for name in skills.FILES:
        text = name + str(sequence)
        m['files'][name] = {'text': text, 'sha256': skills.hashlib.sha256(text.encode()).hexdigest()}
    m['revision'] = skills.digest(m)
    return m


class Hub:
    def __init__(self):
        self.releases = [release()]
        self.author = 'publisher'
        self.project = 'p'
        self.fail = False
        self.messages = {}
        self.demo = {'id': 'demo', 'author_id': 'worker', 'project_id': 'p', 'information_type': 'adhd.setup', 'data': record()}

    def __call__(self, cmd, mid=None):
        if self.fail: raise RuntimeError('offline')
        if cmd['op'] == 'search':
            return {'publications': [dict(id='pub'+str(m['sequence']), author_id=self.author,
                                         project_id=self.project, information_type='adhd.skills.release', data=m) for m in self.releases]}
        if cmd['op'] == 'get': return {'publication': self.demo}
        if mid in self.messages:
            assert self.messages[mid] == cmd
        self.messages[mid] = copy.deepcopy(cmd)
        return {'publication': {'id': mid}}


class SkillUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name); self.hub = Hub()
        skills.atomic(self.home/'adhd-skills/policy.json', dict(project_id='p', publisher_id='publisher',
                       agent_id='worker', runtime='test', channel='stable', mode='auto', helper=['unused']))
        self.u = skills.Updater(self.home, self.hub)

    def reload(self): return skills.Updater(self.home, self.hub)

    def test_install_is_not_activation_and_repeated_delivery_is_idempotent(self):
        self.u.sync(); rev = self.u.state['installed']
        self.assertEqual(self.u.state['status'], 'activation_pending')
        self.assertNotIn('sessions', self.u.state)
        count = len(self.hub.messages); self.u.sync()
        self.assertEqual(len(self.hub.messages), count)
        self.assertEqual(self.u.read()['revision'], rev)
        ev = dict(session_id='fresh', revision=rev, answers=skills.ANSWERS, demonstration={'publication_id':'demo'})
        self.u.activate(ev)
        self.assertEqual(self.u.state['sessions']['fresh']['revision'], rev)
        count = len(self.hub.messages)
        self.u.activate(dict(ev, session_id='repeat'))
        self.assertEqual(len(self.hub.messages), count)
        self.assertNotIn('repeat', self.u.state['sessions'])
        self.hub.releases.append(release(2)); self.u.sync()
        self.assertEqual(self.u.state['status'], 'activation_pending')
        self.assertEqual(self.u.state['sessions']['fresh']['revision'], rev)

    def test_trust_project_digest_and_path_validation(self):
        for attr, value in [('author', 'peer'), ('project', 'other')]:
            previous = getattr(self.hub, attr); setattr(self.hub, attr, value)
            with self.assertRaises(ValueError): self.u.sync()
            setattr(self.hub, attr, previous)
        bad = copy.deepcopy(self.hub.releases[0]); bad['files']['coordination.md']['text'] += 'tamper'
        with self.assertRaises(ValueError): skills.validate_release(bad)
        bad = release(); bad['files']['../escape'] = bad['files'].pop('coordination.md')
        bad['revision'] = skills.digest({k:v for k,v in bad.items() if k != 'revision'})
        with self.assertRaises(ValueError): skills.validate_release(bad)

    def test_local_edits_and_credentials_preserved(self):
        secret = self.home/'private.json'; secret.write_text('preserve')
        self.u.sync(); rev = self.u.state['installed']
        edited = self.home/'adhd-skills/releases'/rev/'participation.md'; edited.write_text('local edit')
        self.hub.releases.append(release(2))
        with self.assertRaises(ValueError): self.u.sync()
        self.assertEqual(edited.read_text(), 'local edit'); self.assertEqual(secret.read_text(), 'preserve')
        self.assertEqual(skills.read_json(self.home/'adhd-skills/current.json')['revision'], rev)

    def test_pin_manual_incompatible_and_rollback(self):
        self.u.sync(); first = self.u.state['installed']
        self.hub.releases.append(release(2)); self.u.sync()
        self.u.rollback(first); self.u = self.reload(); self.u.sync()
        self.assertEqual(self.u.state['status'], 'pinned')
        self.assertEqual(self.u.read()['revision'], first)
        self.u.policy.pop('pin'); self.u.policy['mode'] = 'manual'; self.u.sync()
        self.assertEqual(self.u.state['status'], 'approval_required')
        self.u.sync(approved=True); self.assertNotEqual(self.u.state['installed'], first)
        self.hub.releases.append(release(3, minimum=999)); self.u.sync()
        self.assertEqual(self.u.state['status'], 'incompatible')

    def test_offline_outbox_retry_and_late_join(self):
        self.u.sync(); self.hub.fail = True
        self.u.state['status'] = 'test-outage'
        with self.assertRaises(RuntimeError): self.u.report()
        pending = list((self.home/'adhd-skills/outbox').glob('*.json')); self.assertEqual(len(pending), 1)
        original = skills.read_json(pending[0])
        self.hub.fail = False; self.reload().flush()
        self.assertEqual(self.hub.messages[original['message_id']], original['command'])
        self.assertFalse(list((self.home/'adhd-skills/outbox').glob('*.json')))
        self.hub.releases.append(release(2)); self.reload().sync()
        self.assertEqual(self.reload().read()['sequence'], 2)

    def test_revocation_and_sequence_conflict(self):
        self.u.sync(); old = self.u.state['installed']
        self.hub.releases.append(release(2, revoked=[old])); self.u.sync()
        with self.assertRaises(ValueError): self.u.rollback(old)
        self.hub.releases = [release(1)]
        with self.assertRaises(ValueError): self.u.sync()
        self.hub.releases = [release(3), release(3, minimum=2)]
        with self.assertRaises(ValueError): self.u.sync()

    def test_interrupted_pointer_switch_keeps_readable_prior_version(self):
        self.u.sync(); old = self.u.read()['revision']; self.hub.releases.append(release(2))
        original = skills.atomic
        def crash(path, value):
            if path.name == 'current.json': raise OSError('simulated crash')
            return original(path, value)
        with patch.object(skills, 'atomic', crash):
            with self.assertRaises(OSError): self.u.sync()
        self.assertEqual(self.reload().read()['revision'], old)
        self.reload().sync(); self.assertEqual(self.reload().read()['sequence'], 2)

    def test_crash_after_selection_recovers_without_downgrade(self):
        self.u.sync(); self.hub.releases.append(release(2))
        with patch.object(self.u, 'save', side_effect=OSError('crash after selection')):
            with self.assertRaises(OSError): self.u.sync()
        recovered = self.reload()
        self.assertEqual(recovered.state['installed'], release(2)['revision'])
        self.assertEqual(recovered.state['status'], 'activation_pending')
        self.hub.releases = [release(1)]
        with self.assertRaises(ValueError): recovered.sync()

    def test_cannot_attest_wrong_session_revision_or_peer_demo(self):
        self.u.sync(); ev = dict(session_id='one', revision=self.u.state['installed'], answers=skills.ANSWERS,
                                demonstration={'publication_id':'demo'})
        self.hub.demo['author_id'] = 'peer'
        with self.assertRaises(ValueError): self.u.activate(ev)
        self.hub.demo['author_id'] = 'worker'; ev['revision'] = 'old'
        with self.assertRaises(ValueError): self.u.activate(ev)


class SetupTest(unittest.TestCase):
    def test_evidence_and_authoritative_fields(self):
        r = record(); cmd = setup.publication(r, 'p', 'worker')
        self.assertEqual(cmd['source']['item_id'], r['record_id'])
        r['evidence'] = []
        with self.assertRaises(ValueError): setup.validate(r)
        r['state'] = 'blocked'; setup.validate(r)
        r['observed_at'] = '2026-11-03T00:00:00'
        with self.assertRaises(ValueError): setup.validate(r)

if __name__ == '__main__': unittest.main()
