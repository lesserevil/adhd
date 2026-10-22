"""Test-only zero-export custody for retained workflow qualification.

Constructors are inert. Native fencing never contacts the denied service; image
probes execute only after the actual owned application container has started.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from container_fixture import OwnedImage


def model_endpoints(config):
    endpoints = set()
    matcher = config.get('matcher') or {}
    for name in ('matcher', 'history', 'retrieval', 'archive', 'optimization'):
        section = config.get(name) or {}
        url = section.get('url') or matcher.get('url')
        if not url:
            continue
        parsed = urlsplit(url)
        assert parsed.scheme in ('http', 'https')
        assert parsed.hostname in ('127.0.0.1', 'localhost', '::1'), 'Non-loopback model endpoint'
        assert not parsed.username and not parsed.password
        endpoints.add((parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)))
    assert endpoints, 'No model endpoint isolation witness'
    return sorted(endpoints)


class NativeProviderFence:
    def __init__(self, root, config):
        self.endpoints = model_endpoints(config)
        ports = {port for _, port in self.endpoints}
        assert len(ports) == 1, 'Proven single-port fence cannot cover multiple model ports'
        self.port = next(iter(ports))
        self.root = Path(root)
        self.source = Path(__file__).with_name('project_recovery_no_provider.c')
        self.library = self.root / 'workflow-no-provider.so'
        self.audit = self.root / 'workflow-provider-fence.log'
        self.observations = []

    def prepare(self):
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-O2',
                        '-o', str(self.library), str(self.source), '-ldl'], check=True)
        prefix = ['env', 'LD_PRELOAD=' + str(self.library),
                  'ADHD_RECOVERY_DENY_PROVIDER_PORT=' + str(self.port),
                  'ADHD_RECOVERY_PROVIDER_FENCE_AUDIT=' + str(self.audit)]
        probe = ('import socket\ntry: socket.create_connection(("127.0.0.1",' + str(self.port) + '),1)\n'
                 'except ConnectionRefusedError: pass\nelse: raise AssertionError("Provider fence bypassed")\n')
        subprocess.run(prefix + [sys.executable, '-c', probe], check=True)
        assert self.audit.read_text() == 'blocked-provider-connect\n'
        return prefix

    def observe(self, process):
        assert process.poll() is None
        maps = Path('/proc/' + str(process.pid) + '/maps').read_text()
        assert str(self.library) in maps, 'Actual native VM did not load provider fence'
        cmdline = Path('/proc/' + str(process.pid) + '/cmdline').read_bytes()
        assert Path('/proc/' + str(process.pid) + '/exe').resolve().name in ('beam.smp', 'beam')
        self.observations.append({'vm_pid': process.pid, 'maps_sha256': hashlib.sha256(maps.encode()).hexdigest(),
                                  'cmdline_sha256': hashlib.sha256(cmdline).hexdigest(), 'fence_loaded': True})

    def report(self):
        lines = self.audit.read_text().splitlines()
        assert lines and all(line == 'blocked-provider-connect' for line in lines)
        return {'source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
                'library_sha256': hashlib.sha256(self.library.read_bytes()).hexdigest(),
                'denied_port': self.port, 'blocked_connects_including_probe': len(lines),
                'observations': self.observations, 'provider_exports': 0}


def isolated_image_argv(base, config):
    """Pure adaptation: private default bridge and one localhost app mapping."""
    assert base[:2] == ['docker', 'run'] and base[base.index('--network') + 1] == 'host'
    assert config['host'] == '0.0.0.0'
    port = config['port']
    assert type(port) is int and 1024 <= port <= 65535
    assert config['public_url'] == 'http://127.0.0.1:' + str(port)
    assert all(endpoint_port != port for _, endpoint_port in model_endpoints(config))
    result = list(base)
    result[result.index('--network') + 1] = 'bridge'
    return result[:-1] + ['--publish', '127.0.0.1:' + str(port) + ':' + str(port), result[-1]]


class IsolatedWorkflowImage(OwnedImage):
    def __init__(self, image, manifest, root):
        super().__init__(image, manifest, root)
        self.config_file = None
        self.isolation_observations = []

    def argv(self, config_file):
        self.config_file = Path(config_file)
        return isolated_image_argv(super().argv(config_file), json.loads(self.config_file.read_text()))

    def observe(self):
        super().observe()
        config = json.loads(self.config_file.read_text())
        row = json.loads(self.docker('inspect', self.name).stdout)[0]
        assert row['HostConfig']['NetworkMode'] == 'bridge' and set(row['NetworkSettings']['Networks']) == {'bridge'}
        assert row['HostConfig']['PidMode'] in ('', 'private') and not row['HostConfig']['Privileged']
        port = str(config['port'])
        assert row['HostConfig']['PortBindings'] == {port + '/tcp': [{'HostIp': '127.0.0.1', 'HostPort': port}]}
        namespace = self.docker('exec', self.name, 'readlink', '/proc/1/ns/net').stdout.decode().strip()
        assert namespace != os.readlink('/proc/self/ns/net')
        executable = self.docker('exec', self.name, 'readlink', '/proc/1/exe').stdout.decode().strip()
        assert Path(executable).name in ('beam.smp', 'beam')
        assert row['State']['Pid'] > 0
        endpoints = model_endpoints(config)
        probe = ('[host,port]=System.argv(); '
                 'case :gen_tcp.connect(String.to_charlist(host),String.to_integer(port),[:binary,active: false],1000) do '
                 '{:error,:econnrefused}->IO.puts("isolated-model-port-refused"); '
                 'other->raise "Model endpoint unexpectedly reachable: #{inspect(other)}" end')
        for host, endpoint_port in endpoints:
            observed = self.docker('exec', self.name, 'elixir', '-e', probe, host, str(endpoint_port)).stdout
            assert observed == b'isolated-model-port-refused\n'
        self.isolation_observations.append({'container_id': row['Id'], 'host_vm_pid': row['State']['Pid'],
            'image_config_identity': row['Image'], 'network_mode': 'bridge', 'private_network_namespace': namespace,
            'localhost_published_app_port': config['port'], 'model_endpoints_refused_inside_namespace':
            [{'host': host, 'port': endpoint_port} for host, endpoint_port in endpoints], 'provider_exports': 0})

    def identity(self):
        result = super().identity()
        result['model_export_isolation'] = self.isolation_observations
        return result
