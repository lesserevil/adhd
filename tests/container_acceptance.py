#!/usr/bin/env python3
"""Run independent hub acceptance in hardened Linux Docker containers.

Execute on the Docker host with the SDK test environment. All containers and
data are isolated from the deployed service. No existing container is removed.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

import hub_acceptance as acceptance


class ContainerHub(acceptance.Hub):
    image = None

    def __init__(self, command, root, matcher_url):
        super().__init__(command, root, matcher_url)
        self.name = 'adhd-test-' + uuid4().hex[:12]
        self.command = ['docker', 'run', '--rm', '--name', self.name,
            '--network', 'host', '--user', f'{os.getuid()}:{os.getgid()}',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '128', '--memory', '512m', '--cpus', '2',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=64m',
            '--mount', f'type=bind,src={self.root},dst={self.root}',
            '--mount', f'type=bind,src={self.config_file},dst=/config/hub.json,readonly',
            self.image]

    def stop(self, hard=False):
        subprocess.run(['docker', 'kill' if hard else 'stop', self.name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        super().stop(hard=hard)
        # Auto-removal may finish after the CLI exits; wait for removal before reuse.
        subprocess.run(['docker', 'rm', '-f', self.name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        for _ in range(100):
            if subprocess.run(['docker', 'inspect', self.name],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                break
            time.sleep(.1)
        else:
            raise AssertionError('Test container did not finish removal')


async def recovery_checks(root, matcher_url, record):
    """Use the exact documented runner, default image command and /data path."""
    import httpx
    container = 'adhd-ops-' + uuid4().hex[:12]
    config_dir = root / 'operations'
    subprocess.run(['python3', 'scripts/configure_hub.py', '--directory', str(config_dir),
                    '--port', str(acceptance.free_port()), '--matcher-url', matcher_url], check=True)
    config = json.loads((config_dir / 'hub.json').read_text())
    base = config['public_url']
    data = config_dir / 'data'

    def docker(*args):
        return subprocess.check_output(['docker', *args], text=True).strip()

    async def start():
        subprocess.run(['sh', 'deploy/run.sh', str(config_dir / 'hub.json'), str(data),
                        container, ContainerHub.image], check=True, stdout=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if httpx.get(base + '/health', timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.1)
        raise AssertionError('Documented service runner did not become ready')

    async def call(agent, command):
        async with httpx.AsyncClient() as http:
            result = await http.post(base + '/a2a', json={
                'jsonrpc': '2.0', 'id': str(uuid4()), 'method': 'SendMessage',
                'params': {'message': {'messageId': str(uuid4()), 'role': 'ROLE_USER',
                    'parts': [{'data': command}]}}},
                headers={'Authorization': 'Bearer ' + config['agents'][agent]})
            body = result.json()
            assert 'error' not in body, body
            return body['result']['message']['parts'][0]['data']

    try:
        await start()
        delivered = (await call('agent-a', {'op': 'send', 'recipient_id': 'agent-b',
                                           'text': 'recover this delivery'}))['delivery']
        docker('exec', container, 'elixir', '/app/health.exs')
        inspection = json.loads(docker('inspect', container))[0]
        assert inspection['HostConfig']['ReadonlyRootfs']
        assert inspection['HostConfig']['NetworkMode'] == 'host'
        assert inspection['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
        assert inspection['HostConfig']['CapDrop'] == ['ALL']
        record('documented-startup-and-health-with-private-mounts')

        docker('stop', container)
        backup = config_dir / 'backup'
        backup.mkdir(mode=0o700)
        shutil.copy2(data / 'hub.dets', backup / 'hub.dets')
        shutil.copy2(config_dir / 'hub.json', backup / 'hub.json')
        backup_hash = hashlib.sha256((backup / 'hub.dets').read_bytes()).hexdigest()
        docker('rm', container)
        await start()
        assert delivered['id'] in [d['id'] for d in (await call('agent-b', {'op': 'poll'}))['deliveries']]
        await call('agent-b', {'op': 'ack', 'delivery_ids': [delivered['id']]})
        docker('stop', container)
        docker('rm', container)
        await start()
        assert (await call('agent-b', {'op': 'poll'}))['deliveries'] == []
        record('container-replacement-preserves-pending-and-acknowledged-deliveries')

        docker('stop', container)
        docker('rm', container)
        data.rename(config_dir / 'data-before-restore')
        data.mkdir(mode=0o700)
        shutil.copy2(backup / 'hub.dets', data / 'hub.dets')
        assert hashlib.sha256((data / 'hub.dets').read_bytes()).hexdigest() == backup_hash
        await start()
        assert delivered['id'] in [d['id'] for d in (await call('agent-b', {'op': 'poll'}))['deliveries']]
        record('offline-backup-restore-recovers-the-backup-point')
        # Rollback restores acknowledged state from before the restore.
        docker('stop', container)
        docker('rm', container)
        data.rename(config_dir / 'data-restored-test')
        (config_dir / 'data-before-restore').rename(data)
        await start()
        assert (await call('agent-b', {'op': 'poll'}))['deliveries'] == []
        record('rollback-preserves-pre-restore-store')
    finally:
        subprocess.run(['docker', 'rm', '-f', container], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='adhd-hub:local')
    parser.add_argument('--matcher-url', default='http://127.0.0.1:18770/v1/systemone')
    parser.add_argument('--report', default='verification/container-acceptance.json')
    args = parser.parse_args()
    ContainerHub.image = args.image
    acceptance.Hub = ContainerHub
    parent = Path('_build/tests/container').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    passed = []

    def record(name):
        passed.append({'case': name, 'passed': True})
        print('PASS', name, flush=True)

    async def run():
        from information_cases import information_checks
        await acceptance.fixture_checks([], root, record)
        await information_checks([], root, record)
        from admin_cases import admin_checks
        await admin_checks([], root, record)
        live = await acceptance.live_checks([], root, args.matcher_url, record)
        await recovery_checks(root, args.matcher_url, record)
        return live

    live = asyncio.run(run())
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image], text=True))[0]
    manifest = json.loads(subprocess.check_output([
        'docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'cat', args.image,
        '/app/manifest.json'], text=True))
    report = {'schema': 'adhd/container-acceptance@1', 'passed': True, 'cases': passed,
              'image_id': image['Id'], 'architecture': image['Architecture'],
              'inputs': manifest, 'live_model': live, 'sdk_version': acceptance.version('a2a-sdk')}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
