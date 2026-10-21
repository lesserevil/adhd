#!/usr/bin/env python3
"""Configure Agentic Distributed Harness Depot (ADHD) with private server, administrator and per-agent files."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, indent=2)
        output.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='.adhd/container')
    parser.add_argument('--project-id', default='shared-project')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--public-url', help='URL reachable by the agent clients')
    parser.add_argument('--matcher-url', default='http://127.0.0.1:18770/v1/systemone')
    parser.add_argument('--store-path', default='/data/hub.dets',
                        help='Initial store path as seen by the hub; use an absolute host path for native execution')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    root = Path(args.directory)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700, exist_ok=False)
    (root / 'data').mkdir(mode=0o700)
    agents = {name: secrets.token_urlsafe(32) for name in ('agent-a', 'agent-b')}
    public_url = args.public_url or f'http://127.0.0.1:{args.port}'
    password = secrets.token_urlsafe(32)
    salt = secrets.token_bytes(16)
    password_hash = {
        "algorithm": "PBKDF2-HMAC-SHA256", "iterations": 600000,
        "salt": base64.b64encode(salt).decode(),
        "key": base64.b64encode(hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)).decode()}
    fd = os.open(root / 'initial-admin-password.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write('Username: admin\nPassword: ' + password + '\n')
    write_private(root / 'hub.json', {
        'config_revision': 1,
        'auth': {'mode': 'local', 'allow_admin_token': False, 'session_ttl_ms': 3600000},
        'users': [{'id': secrets.token_hex(16), 'username': 'admin', 'name': 'admin',
                   'email': '', 'role': 'Admin', 'provider': 'local', 'disabled': False,
                   'oidc': None, 'groups': [], 'profile_complete': False, 'built_in': True,
                   'password_hash': password_hash}], 'agent_owners': {},
        'project_id': args.project_id, 'host': '127.0.0.1', 'port': args.port,
        'public_url': public_url, 'store_path': args.store_path, 'agents': agents,
        'threshold_ppm': 900000, 'matcher': {
            'url': args.matcher_url, 'model': 'Nemotron-Deciffusion-8B-v2.1',
            'timeout_ms': 3000, 'retry_ms': 1000}})
    for name, token in agents.items():
        write_private(root / f'{name}.json', {'public_url': public_url, 'agents': {name: token}})
    print(f'Created private server and per-agent configurations in {root}; initial-admin-password.txt contains the initial admin password.')


if __name__ == '__main__':
    main()
