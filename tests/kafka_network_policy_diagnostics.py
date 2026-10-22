"""Bounded read-only Calico diagnostics for an isolated, already-owned API/node.

No cluster creation, mutations, retries, providers or network policy assertions.
Raw outputs are private files; failed diagnostics never replace a rollout error.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time

class CommandUnavailable(Exception): pass

LIMITS = {'anchor_seconds': 30, 'capture_seconds': 60, 'command_seconds': 10,
          'total_bytes': 8 * 1024 * 1024, 'metadata_bytes': 2 * 1024 * 1024,
          'log_bytes': 65536, 'tail_lines': 200, 'pods': 4, 'containers': 4,
          'log_requests': 16}

def owner(obj, uid, kind):
    return any(x.get('uid') == uid and x.get('kind') == kind and x.get('controller') is True
               for x in obj.get('metadata', {}).get('ownerReferences', []))

def named(obj, name, namespace=None):
    meta = obj['metadata']
    assert meta['name'] == name and isinstance(meta['uid'], str) and meta['uid']
    if namespace is not None: assert meta['namespace'] == namespace
    return meta['uid']

def bounded(argv, env, cwd, timeout, cap):
    """Bound both streams together; kill/join only our process group on failure."""
    child = subprocess.Popen(argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    streams = [bytearray(), bytearray()]; deadline = time.monotonic() + timeout
    primary = None
    try:
        with selectors.DefaultSelector() as selector:
            for i, stream in enumerate((child.stdout, child.stderr)):
                os.set_blocking(stream.fileno(), False); selector.register(stream, selectors.EVENT_READ, i)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError('diagnostic command deadline')
                for key, _ in selector.select(min(remaining, .1)):
                    body = os.read(key.fileobj.fileno(), min(65536, cap - sum(map(len, streams)) + 1))
                    if not body: selector.unregister(key.fileobj); continue
                    available = cap - sum(map(len, streams)); streams[key.data].extend(body[:available])
                    if len(body) > available: raise ValueError('diagnostic output cap')
            code = child.wait(timeout=max(.001, deadline - time.monotonic()))
            return code, bytes(streams[0]), bytes(streams[1])
    except BaseException as error:
        primary = error
        error.diagnostic_partial = (bytes(streams[0]), bytes(streams[1]))
        raise
    finally:
        try:
            if child.poll() is None:
                assert os.getpgid(child.pid) == child.pid
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        except BaseException as cleanup:
            if primary: primary.add_note('Diagnostic CLI cleanup: ' + type(cleanup).__name__)
            else: raise
        finally:
            child.stdout.close(); child.stderr.close()

def observe_rollout(rollout, diagnostic):
    primary = None
    try:
        return rollout()
    except BaseException as error:
        primary = error
        raise
    finally:
        try: diagnostic.summary = diagnostic.capture()
        except BaseException as error:
            diagnostic.capture_error = type(error).__name__
            if primary: primary.add_note('Diagnostic capture failed: ' + type(error).__name__)
            else: raise

class Diagnostics:
    def __init__(self, root, kubectl, env, cwd, node, fence, clock=time.monotonic):
        self.root = Path(root); self.root.mkdir(mode=0o700)
        assert not self.root.is_symlink() and self.root.resolve() == self.root
        self.kubectl, self.env, self.cwd, self.node, self.fence = kubectl, env, cwd, node, fence
        self.clock = clock; self.rows = []; self.used = 0; self.pins = None
    def phase(self, seconds): self.deadline = self.clock() + seconds
    def call(self, label, args, cap=None, parse=True):
        assert re.fullmatch('[a-z0-9-]+', label)
        remaining = self.deadline - self.clock()
        assert remaining > 0
        self.fence(min(remaining, LIMITS['command_seconds']))
        remaining = self.deadline - self.clock()
        assert remaining > 0 and self.used < LIMITS['total_bytes']
        cap = min(cap or LIMITS['metadata_bytes'], LIMITS['total_bytes'] - self.used)
        row = {'name': label, 'argv': self.kubectl + args, 'passed': False}; self.rows.append(row)
        out = err = b''
        try:
            code, out, err = bounded(row['argv'], self.env, self.cwd,
                                    min(remaining, LIMITS['command_seconds']), cap)
            row['returncode'] = code
            assert self.clock() <= self.deadline
            if code != 0: raise CommandUnavailable('diagnostic command exit')
            self.fence(min(self.deadline-self.clock(), LIMITS['command_seconds'])); row['passed'] = True
            return json.loads(out) if parse else out
        except BaseException as error:
            out, err = getattr(error, 'diagnostic_partial', (out, err))
            row['error_type'] = type(error).__name__; raise
        finally:
            self.used += len(out) + len(err)
            for extension, data in [('stdout', out), ('stderr', err)]:
                path = self.root / (str(len(self.rows)).zfill(2) + '-' + label + '.' + extension)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as stream: stream.write(data)
                row[extension] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    def anchor(self):
        self.phase(LIMITS['anchor_seconds'])
        ns = self.call('namespace-pin', ['get', 'namespace', 'kube-system', '-o', 'json'])
        node = self.call('node-pin', ['get', 'node', self.node, '-o', 'json'])
        assert node['metadata']['labels']['kubernetes.io/hostname'] == self.node
        pins = {'namespace': named(ns, 'kube-system'), 'node': named(node, self.node), 'controllers': {}}
        for kind, name in [('daemonset', 'calico-node'), ('deployment', 'calico-kube-controllers')]:
            obj = self.call(name + '-pin', ['-n', 'kube-system', 'get', kind, name, '-o', 'json'])
            uid = named(obj, name, 'kube-system'); assert obj['spec']['selector']['matchLabels'] == {'k8s-app': name}
            pins['controllers'][name] = {'uid': uid, 'kind': kind, 'object_kind': obj['kind'],
                                         'containers': [v['name'] for k in ('initContainers','containers') for v in obj['spec']['template']['spec'].get(k,[])]}
        self.pins = pins
    def capture(self):
        assert self.pins is not None
        self.phase(LIMITS['capture_seconds']); pod_count = logs = 0
        ns = self.call('namespace-check', ['get', 'namespace', 'kube-system', '-o', 'json'])
        assert named(ns, 'kube-system') == self.pins['namespace']
        node = self.call('node-status', ['get', 'node', self.node, '-o', 'json'])
        assert named(node, self.node) == self.pins['node']
        for name, pin in self.pins['controllers'].items():
            controller = self.call(name + '-status', ['-n','kube-system','get',pin['kind'],name,'-o','json'])
            assert named(controller, name, 'kube-system') == pin['uid']
            parents = {pin['uid']}; parent_kind = pin['object_kind']
            if pin['kind'] == 'deployment':
                replicas = self.call('controller-replicas', ['-n','kube-system','get','replicasets','-l','k8s-app='+name,'-o','json'])
                parents = {r['metadata']['uid'] for r in replicas['items'] if owner(r, pin['uid'], 'Deployment')}; parent_kind = 'ReplicaSet'
            pods = self.call(name + '-pods', ['-n','kube-system','get','pods','-l','k8s-app='+name,'-o','json'])
            for pod in pods['items']:
                pod_count += 1; assert pod_count <= LIMITS['pods']
                meta = pod['metadata']; uid = named(pod, meta['name'], 'kube-system')
                assert meta['labels']['k8s-app'] == name and any(owner(pod, p, parent_kind) for p in parents)
                assert pod['spec'].get('nodeName') in (None, '', self.node)
                self.call('pod-events-'+str(pod_count), ['-n','kube-system','get','events','--field-selector','involvedObject.uid='+uid,'-o','json'])
                if pod['spec'].get('nodeName') != self.node: continue
                containers = [v['name'] for k in ('initContainers','containers') for v in pod['spec'].get(k,[])]
                assert len(containers) <= LIMITS['containers'] and set(containers) <= set(pin['containers'])
                statuses = {v['name']:v for k in ('initContainerStatuses','containerStatuses') for v in pod.get('status',{}).get(k,[])}
                for container in containers:
                    for previous in (False, True):
                        if previous and not statuses.get(container,{}).get('restartCount',0): continue
                        logs += 1; assert logs <= LIMITS['log_requests']
                        current = self.call('pod-fence-'+str(logs), ['-n','kube-system','get','pod',meta['name'],'-o','json'])
                        assert named(current,meta['name'],'kube-system') == uid and current['spec']['nodeName'] == self.node
                        args = ['-n','kube-system','logs',meta['name'],'-c',container,'--tail=200','--limit-bytes=65536','--timestamps'] + (['--previous'] if previous else [])
                        try: self.call('container-log-'+str(logs),args,cap=LIMITS['log_bytes'],parse=False)
                        except CommandUnavailable: pass
                        after = self.call('pod-after-'+str(logs), ['-n','kube-system','get','pod',meta['name'],'-o','json'])
                        assert named(after,meta['name'],'kube-system') == uid and after['spec']['nodeName'] == self.node
        return {'pods':pod_count,'log_requests':logs}
