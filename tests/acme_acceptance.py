#!/usr/bin/env python3
"""Real Pebble/Lego native diagnostic first-cut ACME acceptance.

Explicit --execute is required. This is a scoped diagnostic, not packaged/native
release qualification or proof of the separate OIDC/federation/platform strata.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import signal
import subprocess
import sys
import time
from uuid import uuid4
from urllib.error import URLError

from jsonschema import Draft202012Validator, FormatChecker
from acme_acceptance_fixtures import certificate_facts, challenge_request_vectors, TOKEN, raw_challenge_get
from acme_challenge_relay import ChallengeRelay
from acme_runtime import NativeDiagnostic, PublicClient, sha, regular
from acme_continuity import OIDCContinuity, FederationContinuity


def wait_for(test, seconds, label):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = test()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError(label)


def raw_challenge(path, host='one.acme.test', method='GET'):
    raw = raw_challenge_get(path, host).replace(b'GET ', method.encode() + b' ', 1)
    with socket.create_connection(('127.0.0.1', 18080), timeout=2) as conn:
        conn.settimeout(2)
        conn.sendall(raw)
        body = bytearray()
        while True:
            data = conn.recv(4096)
            if not data:
                break
            body.extend(data)
            assert len(body) <= 16384
    headers, data = bytes(body).split(b'\r\n\r\n', 1)
    status = int(headers.split(b' ', 2)[1])
    return status, headers.lower(), data


def initialize(admin):
    for project in admin.api({'op': 'list_projects'})['projects']:
        fields = {'project_id': project['id']}
        def call(op, **extra):
            return admin.api({'op': op, **fields, **extra})
        availability = call('project_restore_status')['availability']
        if availability == 'ready':
            continue
        assert availability == 'uninitialized', 'Never initialize known unavailable state'
        revision = admin.api({'op': 'config_get'})['config_revision']
        def settle(receipt, desired):
            def observed():
                operation = call('project_restore_status', operation_id=receipt['operation_id'])['operation']
                assert operation['state'] not in ('failed', 'blocked', 'expired', 'stale')
                return operation if operation['state'] == desired else None
            return wait_for(observed, 30, 'Public project initialization deadline')
        receipt = call('project_restore_plan', mode='initialize', expected_revision=revision,
                       confirm=True, message_id=uuid4().hex)
        plan = settle(receipt, 'ready')['plan']
        result = call('project_restore_apply', expected_revision=revision, confirm=True, message_id=uuid4().hex,
                      plan_id=plan['plan_id'], plan_sha256=plan['plan_sha256'])
        assert settle(result, 'complete')['result']['initialized'] is True


def run(args):
    work = Path(args.work).resolve()
    assert not work.exists(), 'Fresh diagnostic root required; no reset or retry'
    work.mkdir(mode=0o700, parents=False)
    marker = work / 'started.json'
    with marker.open('x') as output:
        json.dump({'scope': 'diagnostic only', 'at': datetime.now(timezone.utc).isoformat()}, output)
        output.flush()
        os.fsync(output.fileno())
    fd = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    ca_file = Path(args.ca_manifest)
    assert sha(ca_file) == args.ca_manifest_sha256
    ca = json.loads(ca_file.read_text())
    assert ca['ready'] is True and ca['real_validation'] is True and ca['nonce_validation'] is True
    assert ca['validation_http_port'] == 8080 and ca['directory_url'] == 'https://localhost:19100/dir'
    for name in ('frontend_root', 'issuer_root'):
        regular(ca[name])
        assert sha(ca[name]) == ca[name + '_sha256']
    schema = json.loads(Path(args.schema).read_text())
    validator = Draft202012Validator({'$ref': '#/$defs/TLSStatus', '$defs': schema['$defs']}, format_checker=FormatChecker())
    report = {'schema': 'adhd/acme-native-diagnostic@1', 'passed': False, 'checks': [],
              'scope': 'Source-bound diagnostic cache, real local Pebble and maintained client; not release/image qualification. Optional continuity covers actual OIDC and federation catalog/auth transport only, not full identity-policy or source/discovery model-quality regressions.',
              'ca_manifest_sha256': args.ca_manifest_sha256, 'contract_sha256': sha(args.schema),
              'source_manifest_sha256': args.cache_manifest_sha256, 'public_ca_calls': 0,
              'phase': args.phase,
              'fixture_profile': 'eventing disabled; matcher null; no broker or model calls', 'failure_type': None}
    relay = ChallengeRelay(upstreams={'one.acme.test':18080, 'two.acme.test':18081})
    runtime = None
    oidc = federation = None
    primary = None
    def check(name, **facts):
        report['checks'].append({'name': name, 'passed': True, **facts})
    try:
        if args.phase == 'full':
            assert args.lego_sha256 and args.guardian_sha256, 'Actual reviewed client pair hashes required before issuance'
            pair = {}
            for name, digest in (('lego',args.lego_sha256), ('acme-guard',args.guardian_sha256)):
                path = Path(args.source)/'bin'/name
                regular(path)
                assert os.access(path,os.X_OK) and sha(path)==digest, 'Reviewed client pair drift'
                pair[name] = digest
            report['actual_client_pair_sha256'] = pair
        hub = work / 'hub'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        subprocess.run([sys.executable, str(Path(args.configure).resolve()), '--directory', str(hub),
                        '--port', str(port), '--store-path', str(hub / 'state.dets')], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
        config = json.loads((hub / 'hub.json').read_text())
        assert config['matcher'] is None
        config['eventing'] = {'enabled': False}
        (hub / 'hub.json').write_text(json.dumps(config))
        trust = hub / 'directory-root.pem'
        trust.write_bytes(Path(ca['frontend_root']).read_bytes())
        trust.chmod(0o600)
        runtime = NativeDiagnostic(hub, args.source, args.cache, args.elixir, args.cache_manifest_sha256,
                                   erlang=args.erlang, peer_trust=ca['issuer_root'] if args.continuity else None,
                                   peer_hosts=('one.acme.test', 'two.acme.test') if args.continuity else ())
        runtime.start()
        original_pid = runtime.process.pid
        admin = PublicClient(runtime.base)
        password = re.search(r'^Password: (.+)$', (hub / 'initial-admin-password.txt').read_text(), re.M)[1]
        admin.login('admin', password)
        initialize(admin)
        def status():
            value = admin.api({'op': 'tls_status'})
            validator.validate(value)
            return value
        disabled = status()
        assert disabled['enabled'] is False and disabled['https_state'] == 'disabled'
        error, _ = admin.mutate('tls_renew', expected=409)
        assert error['error']['code'] == 'TLS_RENEW_UNAVAILABLE'
        check('disabled bootstrap and authenticated renew rejection')

        for role in ('Developer', 'Viewer'):
            username, role_password = role.lower(), uuid4().hex + '-owned-role'
            admin.mutate('save_user', user={'username': username, 'name': role, 'email': username+'@fixture.invalid',
                                          'role': role, 'password': role_password})
            client = PublicClient(runtime.base)
            client.login(username, role_password)
            client.api({'op': 'tls_status'}, expected=403)
            revision = admin.api({'op': 'config_get'})['config_revision']
            client.api({'op': 'tls_renew', 'expected_revision': revision, 'confirm': True,
                        'message_id': uuid4().hex}, expected=403)
        PublicClient(runtime.base).api({'op': 'tls_status'}, expected=401)
        PublicClient(runtime.base, bearer=config['agents']['agent-a']).api({'op': 'tls_status'}, expected=401)
        check('global TLS status and renewal enforce current Admin role')

        plain = PublicClient(runtime.base)
        assert plain.rpc({'op': 'whoami'}, config['agents']['agent-a'])['agent_id'] == 'agent-a'
        assert plain.request('/health')[0] == 200
        check('original private HTTP health and authenticated A2A remain usable')

        before = admin.api({'op': 'config_get'})
        for domains in (['*.one.acme.test'], ['127.0.0.1'], ['One.acme.test'], ['one.acme.test.'], ['one.acme.test']*2):
            response, _ = admin.mutate('config_update', patch={'tls': {'acme': {'domains': domains}}}, expected=400)
            assert response['error']['code'] == 'INVALID_PARAMS'
            assert admin.api({'op': 'config_get'}) == before
        check('invalid DNS identifiers reject atomically', vectors=5)

        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen(1)
            response, _ = admin.mutate('config_update', patch={'tls': {'enabled': True, 'host': '127.0.0.1',
                                           'port': occupied.getsockname()[1]}}, expected=409)
            assert response['error']['code'] == 'CONFIG_APPLY_FAILED'
            assert admin.api({'op': 'config_get'}) == before
        check('HTTPS port collision preserves config and revision')

        if args.phase == 'bootstrap':
            report['passed'] = True
            report['unrun_scope'] = 'Issuance/relay/HTTPS/renewal/cold reuse require separately authorized real client pair; OIDC/federation/platform remain independent future strata.'
            return

        relay.set_mode('hold')
        relay.start()
        tls = {'enabled': True, 'host': '127.0.0.1', 'port': 18443,
               'challenge_host': '127.0.0.1', 'challenge_port': 18080,
               'acme': {'enabled': True, 'directory_url': ca['directory_url'], 'email': 'operator@one.acme.test',
                        'domains': ['one.acme.test'], 'accept_terms': True, 'renew_before_days': 1,
                        'retry_seconds': 30, 'order_timeout_ms': 30000, 'ca_cert_file': 'directory-root.pem'}}
        admin.mutate('config_update', patch={'tls': tls})
        assert relay.held.wait(20), 'Actual CA challenge GET must reach a real successful app proof'
        path, host, proof = relay.held_proof
        assert host.split(':')[0] == 'one.acme.test'
        code, headers, body = raw_challenge(path, host)
        assert code == 200 and body == proof and b'cache-control: no-store' in headers and b'content-type: text/plain' in headers
        for vector in challenge_request_vectors():
            if vector['id'] == 'active-token':
                continue
            assert raw_challenge(vector['path'].replace(TOKEN, path.rsplit('/', 1)[1]), host)[0] == 404, vector['id']
        assert raw_challenge(path, 'foreign.acme.test')[0] == 404
        assert raw_challenge(path, host, 'POST')[0] == 405
        check('real pending HTTP01 proof and narrow raw challenge surface', attack_vectors=len(challenge_request_vectors())-1)
        relay.release.set()
        initial = wait_for(lambda: (value if (value := status())['https_state'] == 'ready' else None), 35, 'Initial real ACME issuance')
        wait_for(lambda: relay.snapshot()['active'] == 0, 5, 'Challenge reply settled')
        relay.set_mode('pass')
        assert raw_challenge(path, host)[0] == 404
        secure = PublicClient('https://one.acme.test:18443', trust=ca['issuer_root'])
        assert secure.request('/health')[0] == 200
        cert = certificate_facts(secure.handshakes[-1]['der'], ['one.acme.test'], datetime.now(timezone.utc))
        assert cert['leaf_der_sha256'] == initial['certificate']['sha256']
        assert cert['serial_number_hex'] == initial['certificate']['serial']
        assert secure.handshakes[-1]['verified_chain_and_hostname'] is True
        check('real issued certificate independently trusted and hostname verified', certificate=cert)
        for wrong, expected_error in ((PublicClient('https://two.acme.test:18443', trust=ca['issuer_root']),ssl.SSLError),
                                      (PublicClient('https://one.acme.test:18443', trust=ca['frontend_root']),ssl.SSLCertVerificationError)):
            try:
                wrong.request('/health')
            except (URLError,ssl.SSLError) as error:
                reason = error.reason if isinstance(error,URLError) else error
                assert isinstance(reason,expected_error), 'Negative must be TLS rejection, not unrelated transport outage'
            else:
                raise AssertionError('Hostname/untrusted issuer must fail')
        assert secure.request('/health')[0] == 200
        check('wrong hostname and unrelated trust root fail closed')
        secure.login('admin', password)
        tokens = config['agents']
        def delivery():
            sent = secure.rpc({'op': 'send', 'recipient_id': 'agent-b', 'text': 'Owned real HTTPS ACME continuity'}, tokens['agent-a'])['delivery']
            poll = secure.rpc({'op': 'poll'}, tokens['agent-b'])
            assert any(row['id'] == sent['id'] for row in poll['deliveries'])
            secure.rpc({'op': 'ack', 'delivery_ids': [sent['id']]}, tokens['agent-b'])
        delivery()
        check('actual authenticated A2A send poll ack and Admin over native HTTPS')

        if args.continuity:
            oidc = OIDCContinuity(work/'oidc', secure.base, ca['issuer_root'])
            oidc.configure(secure)
            check('real signed PKCE OIDC callback over HTTPS and nonce CSRF cookie controls')
            federation = FederationContinuity(args, work/'peer', ca, runtime, admin, tokens, initialize)
            federation.start()
            check('two actual ACME-issued hubs and trusted outbound HTTPS federation catalogs')

        before_manual = status()
        accepted, command = admin.mutate('tls_renew')
        assert accepted['accepted'] is True
        changed = wait_for(lambda: (value if (value := status())['certificate'] and
                           value['certificate']['sha256'] != before_manual['certificate']['sha256'] else None), 40, 'Manual real renewal')
        assert admin.api(command) == accepted, 'Same receipt must replay after renewal'
        assert runtime.process.pid == original_pid and runtime.process.poll() is None
        assert secure.request('/health')[0] == 200
        rotated = certificate_facts(secure.handshakes[-1]['der'], ['one.acme.test'], datetime.now(timezone.utc))
        assert rotated['leaf_der_sha256'] == changed['certificate']['sha256']
        delivery()
        if oidc:
            oidc.after_rotation(changed['certificate']['sha256'])
        if federation:
            federation.check('after_rotation')
        check('hot real leaf rotation and exact renew receipt replay', certificate=rotated, same_vm=True)

        automatic = wait_for(lambda: (value if (value := status())['certificate'] and
                             value['certificate']['sha256'] != changed['certificate']['sha256'] else None), 100, 'Scheduled real renewal without manual submission')
        assert secure.request('/health')[0] == 200
        scheduled = certificate_facts(secure.handshakes[-1]['der'], ['one.acme.test'], datetime.now(timezone.utc))
        assert scheduled['leaf_der_sha256'] == automatic['certificate']['sha256']
        check('automatic renewal using real short-lived CA certificate', certificate=scheduled, manual_submissions_after_previous_rotation=0)

        runtime.stop()
        runtime.start()
        admin = PublicClient(runtime.base)
        admin.login('admin', password)
        persisted = status()
        assert persisted['certificate']['sha256'] == automatic['certificate']['sha256']
        assert secure.request('/health')[0] == 200
        check('unchanged-file cold restart retains active certificate and HTTPS')
        report['passed'] = True
    except BaseException as error:
        primary = error
        report['failure_type'] = type(error).__name__
        raise
    finally:
        cleanup = []
        for close in (federation.close if federation else lambda: None, oidc.close if oidc else lambda: None,
                      runtime.stop if runtime else lambda: None, relay.close):
            try:
                close()
            except BaseException as error:
                cleanup.append(type(error).__name__)
                if primary:
                    primary.add_note('Owned ACME fixture cleanup failed: ' + type(error).__name__)
        report['runtime_identities'] = runtime.identities if runtime else []
        report['peer_runtime_identities'] = federation.runtime.identities if federation and federation.runtime else []
        report['oidc_events'] = oidc.events if oidc else []
        report['federation_events'] = federation.events if federation else []
        report['relay'] = relay.snapshot()
        report['cleanup_errors'] = cleanup
        if cleanup:
            report['passed'] = False
        (work / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        (work / 'report.json').chmod(0o600)
        if cleanup and primary is None:
            raise AssertionError('Owned ACME fixture cleanup failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('work', 'source', 'cache', 'elixir', 'erlang', 'cache-manifest-sha256', 'ca-manifest', 'ca-manifest-sha256', 'schema', 'configure'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--phase', choices=('bootstrap', 'full'), default='bootstrap')
    parser.add_argument('--continuity', action='store_true', help='Explicit real OIDC and two-hub HTTPS federation stratum')
    parser.add_argument('--lego-sha256')
    parser.add_argument('--guardian-sha256')
    args = parser.parse_args()
    def expired(signum, frame):
        raise TimeoutError('Finite diagnostic suite budget')
    previous = signal.signal(signal.SIGALRM, expired)
    prior_term = signal.signal(signal.SIGTERM, expired)
    signal.alarm(900 if args.continuity else 600)
    try:
        run(args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        signal.signal(signal.SIGTERM, prior_term)


if __name__ == '__main__':
    main()
