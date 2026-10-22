#!/usr/bin/env python3
"""Exercise the shipped ingress policies on an explicitly provided cluster.

The fresh namespace contains TCP fixtures, not a Kafka or ADHD deployment.
Pre-policy reachability is mandatory; a non-enforcing CNI fails this test.
Cluster/CNI installation is deliberately outside this entrypoint.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
import subprocess
import time

import yaml

from image_qualification_inputs import reviewed_payload
from kafka_platform_matrix import kube_endpoint


SERVE = '''
for port <- [8082, 9092, 9093] do
  spawn_link(fn ->
    {:ok, socket} = :gen_tcp.listen(port, [:binary, active: false, reuseaddr: true])
    Stream.repeatedly(fn ->
      {:ok, client} = :gen_tcp.accept(socket)
      :gen_tcp.send(client, "adhd-policy-v1\\n")
      :gen_tcp.close(client)
    end) |> Stream.run()
  end)
end
Process.sleep(:infinity)
'''
PROBE = '''
[host, raw_port] = System.argv()
case :gen_tcp.connect(String.to_charlist(host), String.to_integer(raw_port),
                     [:binary, active: false], 1000) do
  {:ok, socket} ->
    result = :gen_tcp.recv(socket, byte_size("adhd-policy-v1\\n"), 1000)
    :gen_tcp.close(socket)
    if result == {:ok, "adhd-policy-v1\\n"}, do: IO.puts("REACHABLE"), else: System.halt(2)
  {:error, reason} when reason in [:timeout, :ehostunreach, :enetunreach, :econnrefused] ->
    IO.puts("DENIED")
  _ -> System.halt(3)
end
'''
PODS = {'broker': 'kafka', 'rest': 'kafka-rest', 'hub': 'hub',
        'broker-peer': 'kafka', 'rest-peer': 'kafka-rest', 'outsider': 'policy-outsider'}
PEERS = {'peer-hub': 'hub', 'peer-rest': 'kafka-rest', 'peer-broker': 'kafka'}
CROSS_ROUTES = [('peer-hub', 'rest', 8082, False), ('peer-rest', 'broker', 9092, False),
                ('peer-rest', 'broker', 9093, False), ('peer-broker', 'broker', 9092, False),
                ('peer-broker', 'broker', 9093, False)]
# Each denial has its own successful before-policy control, including ports
# which have a listening fixture but are deliberately absent from the policy.
ROUTES = [
    ('hub', 'rest', 8082, True),
    ('rest', 'broker', 9092, True),
    ('rest', 'broker', 9093, True),
    ('broker-peer', 'broker', 9092, True),
    ('broker-peer', 'broker', 9093, True),
    ('outsider', 'rest', 8082, False),
    ('outsider', 'broker', 9092, False),
    ('outsider', 'broker', 9093, False),
    ('hub', 'broker', 9092, False),
    ('hub', 'broker', 9093, False),
    ('rest-peer', 'rest', 8082, False),
    ('hub', 'rest', 9092, False),
    ('rest', 'broker', 8082, False),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policies(path, namespace):
    values = list(yaml.safe_load_all(Path(path).read_text()))
    assert len(values) == 2 and {v['metadata']['name'] for v in values} == {'kafka', 'kafka-rest'}
    for value in values:
        assert value['apiVersion'] == 'networking.k8s.io/v1' and value['kind'] == 'NetworkPolicy'
        assert value['metadata']['namespace'] == 'adhd'
        value['metadata']['namespace'] = namespace
    return values


def pod(name, label, namespace, image):
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
        'name': name, 'namespace': namespace, 'labels': {'app': label}}, 'spec': {
        'restartPolicy': 'Never', 'terminationGracePeriodSeconds': 1,
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000, 'runAsGroup': 1000},
        'containers': [{'name': 'fixture', 'image': image, 'imagePullPolicy': 'Never',
            'command': ['elixir', '-e', SERVE], 'env': [{'name': 'ERL_FLAGS', 'value': '+S 1:1'}],
            'readinessProbe': {'tcpSocket': {'port': 8082}, 'periodSeconds': 1,
                               'failureThreshold': 25},
            'resources': {'requests': {'cpu': '50m', 'memory': '48Mi'},
                          'limits': {'cpu': '1', 'memory': '192Mi'}},
            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                'capabilities': {'drop': ['ALL']}}}]}}


def probe_result(result):
    assert result.returncode == 0, 'Probe execution failed; this is not an observed policy denial'
    assert not result.stderr.strip(), 'Unexpected probe diagnostics'
    text = result.stdout.decode().strip()
    assert text in ('REACHABLE', 'DENIED'), 'Unexpected probe output'
    return text == 'REACHABLE'


def namespace_delete(namespace, uid):
    """Raw DELETE accepts a DeleteOptions body; ordinary name deletion has no UID fence."""
    assert re.fullmatch(r'adhd-netpol-[a-z0-9]+(?:-[a-z0-9]+)*', namespace)
    assert isinstance(uid, str) and uid
    return (['delete', '--raw', '/api/v1/namespaces/' + namespace, '-f', '-'],
            json.dumps({'apiVersion': 'v1', 'kind': 'DeleteOptions',
                        'preconditions': {'uid': uid}}).encode())


def main(args):
    root = args.work.absolute()
    assert root.resolve() == root and not root.exists()
    assert re.fullmatch(r'adhd-netpol-[a-z0-9]+(?:-[a-z0-9]+)*', args.namespace) and len(args.namespace) <= 55
    assert re.fullmatch(r'sha256:[a-f0-9]{64}', args.image)
    assert args.kind_node == args.kind_cluster + '-control-plane'
    endpoint = kube_endpoint(args.kubeconfig, args.kind_cluster)
    node = json.loads(subprocess.check_output(['docker', 'inspect', args.kind_node], timeout=30))[0]
    assert node['State']['Running'] and node['Config']['Labels']['io.x-k8s.kind.cluster'] == args.kind_cluster
    assert node['Name'] == '/' + args.kind_node
    published = node['NetworkSettings']['Ports']['6443/tcp']
    assert len(published) == 1 and published[0]['HostIp'] == endpoint['host']
    assert int(published[0]['HostPort']) == endpoint['port']
    manifest = json.loads((args.context / 'manifest.json').read_text())
    reviewed_payload(args.context / 'manifest.json', args.admission_manifest,
                     args.admission_sha256, args.image, manifest['files']['hub.exs'])
    assert json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.cluster_image], timeout=30))[0]['Id'] == args.image
    cached = json.loads(subprocess.check_output(['docker', 'exec', args.kind_node, 'crictl',
                                                'inspecti', args.cluster_image], timeout=30))
    assert cached['status']['id'] == args.image
    root.mkdir(mode=0o700)
    kubectl = [str(args.kubectl.resolve()), '--kubeconfig', str(args.kubeconfig.resolve())]
    owner = secrets.token_hex(16)
    created = {}
    report = {'schema': 'adhd/kubernetes-ingress-policy@1', 'passed': False,
              'scope': 'TCP fixtures qualify exact shipped NetworkPolicy enforcement only; no Kafka, hub, OAuth, HA or application qualification.',
              'policy_sha256': sha(args.policy), 'image_config_identity': args.image,
              'cluster_endpoint': endpoint['server'], 'before': [], 'after': [],
              'fixture_runtime_images': [], 'owned_namespace_cleanup': [], 'error_type': None}
    log = (root / 'kubectl.log').open('xb')

    def run(argv, data=None, timeout=40):
        return subprocess.run(kubectl + argv, input=data, capture_output=True, timeout=timeout)

    def checked(argv, data=None):
        result = run(argv, data)
        log.write(result.stderr); log.flush()
        assert result.returncode == 0, 'Owned Kubernetes operation failed'
        return result.stdout

    def read(argv):
        body = checked(argv + ['-o', 'json'])
        return json.loads(body) if body.strip() else None

    primary = None
    try:
        for namespace in (args.namespace, args.namespace + '-peer'):
            assert read(['get', 'namespace', namespace, '--ignore-not-found']) is None, 'Never adopt an existing namespace'
            body = {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {
                'name': namespace, 'labels': {'adhd-policy-owner': owner}}}
            # A failed create may still have committed. Retain the issued name
            # before sending it and use the secret nonce to establish ownership.
            created[namespace] = None
            checked(['create', '-f', '-'], json.dumps(body).encode())
            actual = read(['get', 'namespace', namespace])
            assert actual['metadata']['labels']['adhd-policy-owner'] == owner
            created[namespace] = actual['metadata']['uid']
        for name, label in PODS.items():
            checked(['create', '-f', '-'], json.dumps(pod(name, label, args.namespace, args.cluster_image)).encode())
        for name, label in PEERS.items():
            checked(['create', '-f', '-'], json.dumps(pod(name, label, args.namespace + '-peer', args.cluster_image)).encode())
        addresses = {}
        for namespace, names in [(args.namespace, PODS), (args.namespace + '-peer', PEERS)]:
            for name, role in names.items():
                try:
                    checked(['-n', namespace, 'wait', '--for=condition=Ready', 'pod/' + name, '--timeout=30s'])
                except (AssertionError, subprocess.TimeoutExpired) as readiness_error:
                    try:
                        from kafka_network_policy_readiness import capture
                        report['readiness_diagnostics'] = capture(root / 'readiness-private', kubectl, namespace, created[namespace], owner, name, role, args.cluster_image, args.kind_node)
                    except BaseException as diagnostic_error:
                        report['readiness_diagnostics_error_type'] = type(diagnostic_error).__name__
                        readiness_error.add_note('Owned readiness diagnostics failed: ' + type(diagnostic_error).__name__)
                    raise
                actual = read(['-n', namespace, 'get', 'pod', name])
                assert actual['metadata']['namespace'] == namespace and actual['metadata']['labels']['app'] == role
                statuses = actual['status']['containerStatuses']
                assert len(statuses) == 1 and statuses[0]['ready'] and statuses[0]['restartCount'] == 0
                observed_image = statuses[0]['imageID'].removeprefix('docker-pullable://')
                actual_image = json.loads(subprocess.check_output(['docker', 'exec', args.kind_node,
                                                                  'crictl', 'inspecti', observed_image], timeout=30))
                assert actual_image['status']['id'] == args.image
                report['fixture_runtime_images'].append({'namespace': namespace, 'pod': name,
                    'pod_uid': actual['metadata']['uid'], 'runtime_image_id': observed_image,
                    'image_config_identity': actual_image['status']['id'], 'role': role})
                ipaddress.ip_address(actual['status']['podIP'])
                addresses[name] = actual['status']['podIP']
        routes = ROUTES + CROSS_ROUTES

        def probe(source, target, port, deadline=None):
            namespace = args.namespace + '-peer' if source in PEERS else args.namespace
            remaining = 40 if deadline is None else deadline - time.monotonic()
            assert remaining > 0, 'Policy convergence deadline'
            result = probe_result(run(['-n', namespace, 'exec', source, '--', 'elixir', '-e',
                                       PROBE, '--', addresses[target], str(port)], timeout=min(40, remaining)))
            assert deadline is None or time.monotonic() <= deadline, 'Policy convergence deadline'
            return result

        for source, target, port, allowed in routes:
            assert probe(source, target, port), 'Before-policy control unreachable'
            report['before'].append({'source': source, 'target': target, 'port': port, 'reachable': True})
        rendered = policies(args.policy, args.namespace)
        checked(['create', '-f', '-'], json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': rendered}).encode())
        # CNI updates are asynchronous. Require every allowed and denied route
        # together; a denial never substitutes for a successful baseline.
        deadline = time.monotonic() + 60
        while True:
            rows = []
            for source, target, port, allowed in routes:
                reachable = probe(source, target, port, deadline)
                rows.append({'source': source, 'target': target, 'port': port,
                             'expected_reachable': allowed, 'reachable': reachable})
            report['after'] = rows
            if all(r['reachable'] == r['expected_reachable'] for r in rows):
                break
            assert time.monotonic() < deadline, 'Shipped ingress policy not enforced'
            time.sleep(.2)
        for recorded in report['fixture_runtime_images']:
            actual = read(['-n', recorded['namespace'], 'get', 'pod', recorded['pod']])
            assert actual['metadata']['uid'] == recorded['pod_uid']
            assert actual['metadata']['namespace'] == recorded['namespace']
            assert actual['metadata']['labels']['app'] == recorded['role']
            status = actual['status']['containerStatuses'][0]
            assert status['ready'] and status['restartCount'] == 0 and 'running' in status['state']
        report['traffic_checks_passed'] = True
    except BaseException as error:
        primary = error
        report['error_type'] = type(error).__name__
        raise
    finally:
        errors = []
        for namespace, uid in reversed(list(created.items())):
            row = {'namespace': namespace, 'observed_absent': False}
            try:
                actual = read(['get', 'namespace', namespace, '--ignore-not-found'])
                if actual is not None:
                    assert actual['metadata']['labels'].get('adhd-policy-owner') == owner
                    assert uid is None or actual['metadata']['uid'] == uid, 'Refuse replacement namespace cleanup'
                    row['uid'] = actual['metadata']['uid']
                    argv, body = namespace_delete(namespace, row['uid'])
                    checked(argv, body)
                    deadline = time.monotonic() + 30
                    while read(['get', 'namespace', namespace, '--ignore-not-found']) is not None:
                        assert time.monotonic() < deadline, 'Owned namespace removal unconfirmed'
                        time.sleep(.2)
                assert read(['get', 'namespace', namespace, '--ignore-not-found']) is None
                row['observed_absent'] = True
            except BaseException as error:
                row['error_type'] = type(error).__name__; errors.append(error)
            report['owned_namespace_cleanup'].append(row)
        try:
            log.close()
        except BaseException as error:
            errors.append(error)
        report['passed'] = primary is None and not errors and report.get('traffic_checks_passed', False)
        try:
            args.report.write_text(json.dumps(report, indent=2) + '\n')
        except BaseException as error:
            errors.append(error)
        if errors:
            if primary is not None:
                primary.add_note('Owned policy fixture cleanup unconfirmed: ' + ','.join(type(e).__name__ for e in errors))
            else:
                raise errors[0]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('kubectl', 'kubeconfig', 'context', 'admission-manifest', 'work', 'report'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('namespace', 'image', 'cluster-image', 'kind-cluster', 'kind-node', 'admission-sha256'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--policy', type=Path, default=Path(__file__).resolve().parents[1] / 'deploy/k8s/private.yaml')
    main(p.parse_args())
