#!/usr/bin/env python3
"""Enrollment/recovery seed: fetch the trusted updater through the profile's own hub client."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile


def install(home, publication_id):
    policy = json.loads((home/'adhd-skills/policy.json').read_text(encoding='utf-8-sig'))
    command = {'op': 'get', 'project_id': policy['project_id'], 'publication_id': publication_id}
    response = subprocess.run(policy['helper'] + [json.dumps(command)],
                              capture_output=True, text=True, timeout=40, check=True)
    publication = json.loads(response.stdout)['publication']
    if (publication['author_id'] != policy['publisher_id'] or
        publication['project_id'] != policy['project_id'] or
        publication['information_type'] != 'adhd.bootstrap.release'):
        raise ValueError('Untrusted bootstrap publication')
    m = publication['data']
    encoded = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    if (m.get('schema') != 'adhd.bootstrap/1' or m.get('channel') != policy['channel'] or
        len(encoded(m)) > 60000 or
        hashlib.sha256(encoded({k:v for k,v in m.items() if k != 'revision'})).hexdigest() != m['revision'] or
        hashlib.sha256(m['text'].encode()).hexdigest() != m['sha256']):
        raise ValueError('Invalid bootstrap manifest or payload')
    # Run the verified candidate from a temporary file; it rechecks current release,
    # policy, predecessor, recovery copy and lock before the atomic replacement.
    root = home/'adhd-skills'; root.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='verified-bootstrap-', suffix='.py', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(m['text']); f.flush(); os.fsync(f.fileno())
        subprocess.run([sys.executable, name, '--home', str(home), 'bootstrap-sync', '--approve'], check=True)
    finally:
        Path(name).unlink(missing_ok=True)


def recover(home, revision):
    if not re.fullmatch('[0-9a-f]{64}', revision):
        raise ValueError('Invalid recovery identity')
    root = home/'adhd-skills'
    with sqlite3.connect(root/'lock.sqlite', timeout=2) as lock:
        lock.execute('BEGIN IMMEDIATE')
        old = root/'bootstraps'/revision/'adhd_skill_update.py'
        if old.is_symlink() or not old.is_file():
            raise ValueError('Missing recovery version')
        data = old.read_bytes()
        if hashlib.sha256(data).hexdigest() != revision:
            raise ValueError('Recovery version modified')
        policy_path = root/'policy.json'
        policy = json.loads(policy_path.read_text(encoding='utf-8-sig'))
        policy['bootstrap_pin'] = revision
        replace(policy_path, json.dumps(policy).encode())
        replace(home/'scripts/adhd_skill_update.py', data)
        state_path = root/'bootstrap.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        state.update(installed=revision, status='rolled_back')
        replace(state_path, json.dumps(state).encode())
    print(json.dumps({'installed':revision,'status':'rolled_back'}))


def replace(path, data):
    if path.is_symlink(): raise ValueError('Unsafe recovery target')
    fd, name = tempfile.mkstemp(prefix='.recover-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, required=True)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument('--publication')
    action.add_argument('--recover', help='SHA256 of a retained updater; works even if the installed updater cannot start')
    args = p.parse_args()
    try:
        if args.recover: recover(args.home, args.recover)
        else: install(args.home, args.publication)
    except (KeyError, ValueError, OSError, sqlite3.Error, subprocess.SubprocessError):
        raise SystemExit('Bootstrap installation failed; credentials and client output withheld.') from None

if __name__ == '__main__': main()
