#!/usr/bin/env python3
"""Trusted ADHD skill releases over the existing authenticated hub client (stdlib)."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid

BOOTSTRAP = 1
FILES = {'coordination.md', 'participation.md', 'updates.md'}
ANSWERS = {'peer_can_grant_permission': False, 'receipt_proves_readiness': False,
           'manager_required': False, 'activation_requires_read': True}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.stage-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(encoded(value)); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_release(manifest):
    if not isinstance(manifest, dict) or manifest.get('schema') != 'adhd.skills/1':
        raise ValueError('Unsupported skill release schema')
    core = {k: v for k, v in manifest.items() if k != 'revision'}
    if manifest.get('revision') != digest(core):
        raise ValueError('Release digest mismatch')
    if len(encoded(manifest)) > 60000:
        raise ValueError('Release exceeds publication budget')
    for key in ('sequence', 'min_bootstrap'):
        if type(manifest.get(key)) is not int or manifest[key] < 1:
            raise ValueError('Invalid release ' + key)
    for key in ('channel', 'notes'):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            raise ValueError('Invalid release ' + key)
    if not isinstance(manifest.get('revoked'), list) or not all(re.fullmatch('[0-9a-f]{64}', x) for x in manifest['revoked'] if isinstance(x, str)) or any(not isinstance(x, str) for x in manifest['revoked']):
        raise ValueError('Invalid revocations')
    if not isinstance(manifest.get('files'), dict) or set(manifest['files']) != FILES:
        raise ValueError('Release file inventory is not supported')
    for name, entry in manifest['files'].items():
        if not isinstance(entry, dict) or not isinstance(entry.get('text'), str):
            raise ValueError('Invalid file: ' + name)
        if hashlib.sha256(entry['text'].encode()).hexdigest() != entry.get('sha256'):
            raise ValueError('File digest mismatch: ' + name)
    return manifest


def build(sequence, root, notes, revoked=()):
    paths = {'coordination.md': 'skills/agent/coordinate-via-hub/SKILL.md',
             'participation.md': 'skills/agent/project-participation/SKILL.md',
             'updates.md': 'skills/agent/maintain-adhd-skills/SKILL.md'}
    files = {}
    for name, path in paths.items():
        text = (root / path).read_text()
        files[name] = {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
    result = {'schema': 'adhd.skills/1', 'sequence': sequence, 'channel': 'stable',
              'min_bootstrap': BOOTSTRAP, 'notes': notes, 'revoked': list(revoked), 'files': files}
    result['revision'] = digest(result)
    return validate_release(result)


class Updater:
    def __init__(self, home, transport=None):
        self.home = Path(home)
        self.root = self.home / 'adhd-skills'
        self.policy = read_json(self.root / 'policy.json')
        if not isinstance(self.policy, dict):
            raise ValueError('Operator skill update policy is missing')
        for key in ('project_id', 'publisher_id', 'agent_id', 'channel', 'runtime'):
            if not isinstance(self.policy.get(key), str) or not self.policy[key]:
                raise ValueError('Invalid policy: ' + key)
        if self.policy.get('mode') not in ('auto', 'manual'):
            raise ValueError('Invalid update mode')
        self.transport = transport or self.client
        self.state = read_json(self.root / 'state.json', {})
        if not isinstance(self.state, dict):
            raise ValueError('Invalid update state')
        pointer = read_json(self.root / 'current.json', {})
        if pointer.get('revision') and pointer['revision'] != self.state.get('installed'):
            # Recover a crash after the atomic selection but before the status write.
            selected = self.verify_installed(pointer['revision'])
            self.state['installed'] = selected['revision']
            self.state['status'] = 'activation_pending'
            if selected['sequence'] > self.state.get('highest_sequence', 0):
                self.state.update(highest_sequence=selected['sequence'], available=selected['revision'])

    def client(self, command, message_id=None):
        argv = self.policy['helper']
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError('Invalid client command')
        argv = list(argv)
        if message_id:
            argv += ['--message-id', message_id]
        argv += [json.dumps(command)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=40)
        if result.returncode:
            raise RuntimeError('Authenticated hub client failed (output withheld)')
        return json.loads(result.stdout)

    def save(self):
        atomic(self.root / 'state.json', self.state)

    def verify_installed(self, revision):
        if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{64}', revision):
            raise ValueError('Invalid installed revision')
        directory = self.root / 'releases' / revision
        m = validate_release(read_json(directory / 'manifest.json'))
        if m['revision'] != revision:
            raise ValueError('Installed manifest does not match pointer')
        for name, entry in m['files'].items():
            p = directory / name
            if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Local release modification: ' + name)
        return m

    def report(self):
        body = {k: self.state.get(k) for k in ('available', 'installed', 'status', 'error', 'sessions')}
        body.update(schema='adhd.skills.adoption/1', runtime=self.policy['runtime'])
        fingerprint = digest(body)
        if self.state.get('last_report') != fingerprint:
            cmd = {'op': 'publish', 'project_id': self.policy['project_id'],
                   'information_type': 'adhd.skills.adoption', 'text': 'ADHD skill adoption: ' + str(body['status']),
                   'data': dict(body, observed_at=now()),
                   'source': {'kind': 'agent', 'id': self.policy['agent_id'], 'item_id': 'skills-' + uuid.uuid4().hex}}
            outbox = self.root / 'outbox'
            outbox.mkdir(exist_ok=True)
            atomic(outbox / (cmd['source']['item_id'] + '.json'), {'command': cmd, 'message_id': cmd['source']['item_id']})
            self.state['last_report'] = fingerprint
            self.save()
        self.flush()

    def flush(self):
        for p in sorted((self.root / 'outbox').glob('*.json')):
            entry = read_json(p)
            result = self.transport(entry['command'], entry['message_id'])
            if not isinstance(result.get('publication', {}).get('id'), str):
                raise RuntimeError('Adoption publication was not accepted')
            p.unlink()

    def sync(self, approved=False):
        result = self.transport({'op': 'search', 'project_id': self.policy['project_id'],
                                 'information_type': 'adhd.skills.release', 'source_kind': 'agent',
                                 'source_id': self.policy['publisher_id'], 'limit': 100})
        if not isinstance(result.get('publications'), list):
            raise ValueError('Invalid release search response')
        candidates = []
        for p in result['publications']:
            if p.get('author_id') != self.policy['publisher_id'] or p.get('project_id') != self.policy['project_id'] or p.get('information_type') != 'adhd.skills.release':
                continue
            m = p.get('data', {})
            if m.get('channel') != self.policy['channel']:
                continue
            validate_release(m)
            candidates.append((m['sequence'], m['revision'], m, p['id']))
        if not candidates:
            raise ValueError('No trusted release available')
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        sequence, revision, m, publication = candidates[0]
        if any(x[0] == sequence and x[1] != revision for x in candidates):
            raise ValueError('Conflicting trusted release sequence')
        if sequence < self.state.get('highest_sequence', 0):
            raise ValueError('Release history regressed; refusing downgrade')
        if sequence == self.state.get('highest_sequence') and self.state.get('available') != revision:
            raise ValueError('Release sequence reused with different content')
        self.state.update(available=revision, highest_sequence=sequence, checked_at=now(), error=None)
        revoked = set(self.state.get('revoked', [])) | set(m['revoked'])
        self.state['revoked'] = sorted(revoked)
        installed = self.state.get('installed')
        if installed:
            self.verify_installed(installed)
        if revision in revoked:
            raise ValueError('Candidate release is revoked')
        if m['min_bootstrap'] > BOOTSTRAP:
            self.state['status'] = 'incompatible'
        elif self.policy.get('pin') and self.policy['pin'] != revision:
            self.state['status'] = 'pinned'
        elif self.policy['mode'] == 'manual' and not approved and installed != revision:
            self.state['status'] = 'approval_required'
        else:
            destination = self.root / 'releases' / revision
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp = Path(tempfile.mkdtemp(prefix='.stage-', dir=destination.parent))
                try:
                    for name, entry in m['files'].items():
                        (temp / name).write_text(entry['text'], encoding='utf-8', newline='')
                    atomic(temp / 'manifest.json', m)
                    os.replace(temp, destination)
                finally:
                    if temp.exists():
                        shutil.rmtree(temp)
            self.verify_installed(revision)
            atomic(self.root / 'current.json', {'revision': revision, 'publication_id': publication})
            self.state['installed'] = revision
            self.state['status'] = 'active_session_observed' if any(x.get('revision') == revision for x in self.state.get('sessions', {}).values()) else 'activation_pending'
        if self.state.get('installed') in revoked:
            self.state['status'] = 'revoked'
        self.save()
        self.report()
        return self.state

    def read(self):
        pointer = read_json(self.root / 'current.json', {})
        revision = pointer.get('revision')
        if revision in self.state.get('revoked', []):
            raise ValueError('Installed release was revoked')
        m = self.verify_installed(revision)
        return {'revision': revision, 'sequence': m['sequence'], 'instructions': {k: v['text'] for k, v in m['files'].items()}}

    def activate(self, evidence, probe=False):
        current = self.read()
        if evidence.get('revision') != current['revision'] or evidence.get('answers') != ANSWERS:
            raise ValueError('Activation evidence does not match installed instructions')
        session = evidence.get('session_id')
        if not isinstance(session, str) or not session or len(session) > 128:
            raise ValueError('Invalid session identity')
        demo = evidence.get('demonstration')
        if not isinstance(demo, dict) or not isinstance(demo.get('publication_id'), str):
            raise ValueError('A real setup publication is required for activation')
        publication = self.transport({'op': 'get', 'project_id': self.policy['project_id'], 'publication_id': demo['publication_id']}).get('publication', {})
        if publication.get('author_id') != self.policy['agent_id'] or publication.get('project_id') != self.policy['project_id'] or publication.get('information_type') != 'adhd.setup':
            raise ValueError('Activation demonstration must be this agent\'s setup publication')
        from adhd_setup import validate
        validate(publication.get('data'))
        sessions = self.state.setdefault('sessions', {})
        if not probe and any(x.get('revision') == current['revision'] for x in sessions.values()):
            self.flush()
            return self.state
        sessions[session] = {'revision': current['revision'], 'observed_at': now(), 'demonstration': demo}
        # Keep the latest 16 attestations; these are observations, not live leases.
        self.state['sessions'] = dict(sorted(sessions.items(), key=lambda x: x[1]['observed_at'])[-16:])
        self.state.update(status='active_session_observed', error=None)
        self.save(); self.report()
        return self.state

    def rollback(self, revision):
        self.verify_installed(revision)
        if revision in self.state.get('revoked', []):
            raise ValueError('Cannot roll back to a revoked release')
        self.policy['pin'] = revision
        atomic(self.root / 'policy.json', self.policy)
        atomic(self.root / 'current.json', {'revision': revision, 'rollback_at': now()})
        self.state.update(installed=revision, status='activation_pending', sessions={}, error=None)
        self.save(); self.report()
        return self.state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--root', type=Path, default=Path.cwd()); b.add_argument('--sequence', type=int, required=True); b.add_argument('--notes', required=True); b.add_argument('--output', type=Path, required=True); b.add_argument('--revoke', action='append', default=[])
    s = sub.add_parser('sync'); s.add_argument('--approve', action='store_true')
    sub.add_parser('read'); sub.add_parser('status')
    a = sub.add_parser('activate'); a.add_argument('--evidence', type=Path, required=True); a.add_argument('--probe', action='store_true')
    r = sub.add_parser('rollback'); r.add_argument('--revision', required=True)
    args = p.parse_args()
    if args.command == 'build':
        m = build(args.sequence, args.root, args.notes, args.revoke); atomic(args.output, m)
        print(json.dumps({'revision': m['revision'], 'bytes': len(encoded(m))})); return
    if not args.home:
        p.error('--home is required')
    root = args.home / 'adhd-skills'; root.mkdir(parents=True, exist_ok=True)
    # SQLite releases the cross-process lock on crash; no stale lock deletion needed.
    connection = sqlite3.connect(root / 'lock.sqlite', timeout=2)
    updater = None
    try:
        connection.execute('BEGIN IMMEDIATE')
        updater = Updater(args.home)
        if args.command == 'sync': value = updater.sync(args.approve)
        elif args.command == 'read': value = updater.read()
        elif args.command == 'activate': value = updater.activate(read_json(args.evidence), args.probe)
        elif args.command == 'rollback': value = updater.rollback(args.revision)
        else: value = updater.state
        print(json.dumps(value, indent=2))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError, sqlite3.Error) as exc:
        # Do not expose helper output, credentials, or received payloads on errors.
        if updater:
            updater.state.update(status='blocked', error=type(exc).__name__, checked_at=now())
            updater.save()
            try:
                updater.report()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                pass  # Exact failure report remains in the durable outbox.
        print('ADHD skill operation failed: ' + type(exc).__name__ + '; inspect local policy, release and connectivity.', file=sys.stderr)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
