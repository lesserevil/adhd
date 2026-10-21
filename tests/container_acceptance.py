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
        self.configure_container()

    @classmethod
    def adopt(cls, stopped_hub):
        """Consume an actual native producer's store and configuration unchanged."""
        assert stopped_hub.process is None or stopped_hub.process.poll() is not None
        hub = cls.__new__(cls)
        hub.__dict__.update(stopped_hub.__dict__)
        hub.configure_container()
        return hub

    def configure_container(self):
        self.name = 'adhd-test-' + uuid4().hex[:12]
        self.command = ['docker', 'run', '--rm', '--name', self.name,
            '--network', 'host', '--user', f'{os.getuid()}:{os.getgid()}',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '128', '--memory', '512m', '--cpus', '2',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=64m',
            '--mount', f'type=bind,src={self.root},dst={self.root}',
            '--env', f'ADHD_CONFIG_FILE={self.config_file}',
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

    startup_times = []

    async def start():
        started = time.monotonic()
        subprocess.run(['sh', 'deploy/run.sh', str(config_dir / 'hub.json'), str(data),
                        container, ContainerHub.image], check=True, stdout=subprocess.DEVNULL)
        # Keep readiness bounded in wall time, including cold compilation.
        deadline = started + 45
        while time.monotonic() < deadline:
            try:
                if httpx.get(base + '/health', timeout=1).status_code == 200:
                    startup_times.append(time.monotonic() - started)
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
        assert inspection['Config']['Labels']['org.opencontainers.image.licenses']=='Apache-2.0'
        assert inspection['HostConfig']['ReadonlyRootfs']
        assert inspection['HostConfig']['NetworkMode'] == 'host'
        assert inspection['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
        assert inspection['HostConfig']['CapDrop'] == ['ALL']
        assert any(m['Destination']=='/config' and m['RW'] for m in inspection['Mounts'])
        initial_password_file = (config_dir / 'initial-admin-password.txt').read_bytes()
        initial_password = initial_password_file.decode().split('Password: ')[1].strip()
        rotated_password = 'container-replacement-keeps-this-rotated-password'
        with httpx.Client(base_url=base, timeout=15) as console:
            assert console.post('/admin/login', json={'username':'admin','password':initial_password}, headers={'Origin':base}).status_code == 200
            session = console.get('/admin/session').json()
            headers = {'Origin':base,'X-CSRF-Token':session['csrf']}
            revision = json.loads((config_dir / 'hub.json').read_text())['config_revision']
            changed = console.post('/admin/api', headers=headers, json={'op':'update_profile',
                'name':'Container Administrator','email':'container@example.invalid',
                'current_password':initial_password,'password':rotated_password,
                'expected_revision':revision,'message_id':str(uuid4()),'confirm':True})
            assert changed.status_code == 200, changed.status_code
            assert console.get('/admin/session').json()['authenticated'] is False
            assert console.post('/admin/login', json={'username':'admin','password':rotated_password}, headers={'Origin':base}).status_code == 200
            headers['X-CSRF-Token'] = console.get('/admin/session').json()['csrf']
            revision = json.loads((config_dir / 'hub.json').read_text())['config_revision']
            new_port = acceptance.free_port()
            changed = console.post('/admin/api', headers=headers, json={'op':'config_update',
                'patch':{'port':new_port,'threshold_ppm':880000},'expected_revision':revision,
                'message_id':str(uuid4()),'confirm':True})
            assert changed.status_code == 200, changed.status_code
        base = 'http://127.0.0.1:' + str(new_port)
        config = json.loads((config_dir / 'hub.json').read_text())
        assert config['port']==new_port and config['threshold_ppm']==880000
        assert json.loads(docker('inspect',container))[0]['State']['Pid']==inspection['State']['Pid']
        assert httpx.get(base+'/health').status_code == 200
        docker('exec',container,'elixir','/app/health.exs')
        record('documented-runner-private-writable-mount-hot-port-and-dynamic-health')

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
        with httpx.Client(base_url=base, timeout=15) as console:
            assert console.post('/admin/login',json={'username':'admin','password':initial_password},headers={'Origin':base}).status_code==401
            assert console.post('/admin/login',json={'username':'admin','password':rotated_password},headers={'Origin':base}).status_code==200
        assert (config_dir/'initial-admin-password.txt').read_bytes()==initial_password_file
        record('container-replacement-retains-rotated-password-and-original-bootstrap-file')

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
    return {'deadline_seconds':45,'startup_seconds':startup_times}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='adhd-hub:local')
    parser.add_argument('--matcher-url', default='http://127.0.0.1:18770/v1/systemone')
    parser.add_argument('--fixture-only', action='store_true',
                        help='Run deterministic container regression without claiming live model integration')
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
        live = ({'state': 'not-run', 'reason': 'Explicit fixture-only regression run'}
                if args.fixture_only else
                await acceptance.live_checks([], root, args.matcher_url, record))
        readiness = await recovery_checks(root, args.matcher_url, record)
        return live, readiness

    live, readiness = asyncio.run(run())
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image], text=True))[0]
    manifest = json.loads(subprocess.check_output([
        'docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'cat', args.image,
        '/app/manifest.json'], text=True))
    report = {'schema': 'adhd/container-acceptance@1', 'passed': True, 'cases': passed,
              'image_id': image['Id'], 'architecture': image['Architecture'],
              'inputs': manifest, 'live_model': live, 'documented_runner_readiness': readiness, 'sdk_version': acceptance.version('a2a-sdk')}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
