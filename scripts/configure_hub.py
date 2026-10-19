#!/usr/bin/env python3
"""Configure Agentic Distributed Harness Depot (ADHD) with private server, administrator and per-agent files."""
import argparse
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
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    root = Path(args.directory)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700, exist_ok=False)
    (root / 'data').mkdir(mode=0o700)
    agents = {name: secrets.token_urlsafe(32) for name in ('agent-a', 'agent-b')}
    public_url = args.public_url or f'http://127.0.0.1:{args.port}'
    admin_token = secrets.token_urlsafe(32)
    fd = os.open(root / 'admin-token.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(admin_token + '\n')
    write_private(root / 'hub.json', {
        'admin_token': admin_token,
        'project_id': args.project_id, 'host': '127.0.0.1', 'port': args.port,
        'public_url': public_url, 'store_path': '/data/hub.dets', 'agents': agents,
        'threshold_ppm': 900000, 'matcher': {
            'url': args.matcher_url, 'model': 'Nemotron-Deciffusion-8B-v2.1',
            'timeout_ms': 3000, 'retry_ms': 1000}})
    for name, token in agents.items():
        write_private(root / f'{name}.json', {'public_url': public_url, 'agents': {name: token}})
    print(f'Created private server and per-agent configurations in {root}; tokens are not displayed.')


if __name__ == '__main__':
    main()
