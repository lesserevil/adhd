"""Actual HTTPS OIDC and two-server federation continuity, no fake ACME/model.

Import is inert. The OIDC provider is the existing real signed-JWT/PKCE fixture.
Federation qualifies catalog/auth/canonical identity and outbound verified TLS;
it does not claim model-dependent discovery/source answer quality.
"""
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

from acme_runtime import NativeDiagnostic, PublicClient


def redirect_to(value, expected):
    parsed, base = urlsplit(value), urlsplit(expected)
    assert (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)
    assert not parsed.username and not parsed.password and not parsed.fragment
    return parsed.path + ('?' + parsed.query if parsed.query else '')


def secure_cookies(client):
    cookies = list(client.cookies)
    assert cookies, 'Actual HTTPS cookie required'
    assert all(cookie.secure and cookie.has_nonstandard_attr('HttpOnly') and
               (cookie.get_nonstandard_attr('SameSite') or '').lower() in ('lax', 'strict')
               for cookie in cookies), 'HTTPS auth cookies must keep security attributes'


class OIDCContinuity:
    def __init__(self, root, base, issuer_root):
        self.root, self.base, self.issuer_root = Path(root), base, issuer_root
        self.provider = self.client = None
        self.user_id = None
        self.events = []

    def configure(self, admin):
        # Preserve the original real provider unchanged, but do not pull its
        # unrelated model/httpx imports into inert pure/bootstrap paths.
        from foundation_acceptance import Provider
        self.root.mkdir(mode=0o700)
        self.provider = Provider(self.root)
        settings = {'provider_id': 'owned-acme-provider', 'issuer': self.provider.issuer,
                    'client_id': 'independent-client', 'client_secret': 'fixture-client-secret',
                    'redirect_uri': self.base + '/admin/oidc/callback', 'scopes': ['openid', 'profile', 'email'],
                    'groups_claim': 'groups', 'role_groups': {'Admin': ['admins'], 'Developer': ['engineering'],
                                                          'Viewer': ['readers']}, 'default_role': None, 'timeout_ms': 3000}
        admin.api({'op': 'test_oidc', 'settings': settings})
        admin.mutate('config_update', patch={'public_url': self.base, 'auth': {'mode': 'both', 'oidc': settings}})
        self.client, session = self.login('normal')
        assert session['authenticated'] is True and session['user']['role'] == 'Admin'
        assert session['user']['oidc']['issuer'] == self.provider.issuer
        self.user_id = session['user']['id']
        exchanges = self.provider.exchanges
        _, denied = self.login('wrong-nonce')
        assert denied['authenticated'] is False and self.provider.exchanges == exchanges + 1
        self.provider.mode = 'normal'
        revision = admin.api({'op': 'config_get'})['config_revision']
        status, _, _ = self.client.request('/admin/api', {'op': 'tls_renew', 'expected_revision': revision,
                                         'confirm': True, 'message_id': uuid4().hex}, headers={'X-CSRF-Token': 'wrong'})
        assert status == 403, 'HTTPS OIDC cookie must not bypass CSRF'
        self.events.append({'stage': 'configured', 'signed_token_exchanges': self.provider.exchanges,
                            'nonce_rejection': True, 'csrf_rejection': True, 'https_cookies_checked': True})

    def login(self, mode):
        self.provider.mode = mode
        client = PublicClient(self.base, trust=self.issuer_root)
        status, _, headers = client.request('/admin/oidc/start')
        assert status == 302
        secure_cookies(client)
        path = redirect_to(headers['Location'], self.provider.issuer)
        provider_client = PublicClient(self.provider.issuer)
        status, _, headers = provider_client.request(path)
        assert status == 302
        callback = redirect_to(headers['Location'], self.base)
        assert callback.startswith('/admin/oidc/callback?')
        client.request(callback)
        status, session, _ = client.request('/admin/session')
        assert status == 200
        if session['authenticated']:
            secure_cookies(client)
            client.csrf = session['csrf']
        return client, session

    def after_rotation(self, expected_leaf):
        status, session, _ = self.client.request('/admin/session')
        assert status == 200 and session['authenticated'] is True and session['user']['id'] == self.user_id
        assert self.client.api({'op': 'tls_status'})['certificate']['sha256'] == expected_leaf
        self.events.append({'stage': 'after_rotation', 'same_oidc_user_and_session': True,
                            'verified_leaf_sha256': expected_leaf})

    def close(self):
        if self.provider:
            self.provider.close()
            assert not self.provider.thread.is_alive(), 'Owned OIDC provider remained'


class FederationContinuity:
    def __init__(self, args, root, ca, origin_runtime, origin_admin, origin_tokens, initialize):
        self.args, self.root, self.ca = args, Path(root), ca
        self.origin_runtime, self.origin_admin, self.origin_tokens = origin_runtime, origin_admin, origin_tokens
        self.initialize = initialize
        self.runtime = self.admin = None
        self.events = []

    def start(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        subprocess.run([sys.executable, str(Path(self.args.configure).resolve()), '--directory', str(self.root),
                        '--port', str(port), '--store-path', str(self.root/'state.dets')], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
        config = json.loads((self.root/'hub.json').read_text())
        assert config['matcher'] is None
        config['eventing'] = {'enabled': False}
        (self.root/'hub.json').write_text(json.dumps(config))
        trust = self.root/'directory-root.pem'
        trust.write_bytes(Path(self.ca['frontend_root']).read_bytes())
        trust.chmod(0o600)
        self.runtime = NativeDiagnostic(self.root, self.args.source, self.args.cache, self.args.elixir,
                                       self.args.cache_manifest_sha256, erlang=self.args.erlang,
                                       peer_trust=self.ca['issuer_root'], peer_hosts=('one.acme.test', 'two.acme.test'))
        self.runtime.start()
        self.admin = PublicClient(self.runtime.base)
        password = re.search(r'^Password: (.+)$', (self.root/'initial-admin-password.txt').read_text(), re.M)[1]
        self.admin.login('admin', password)
        self.initialize(self.admin)
        self.admin.mutate('config_update', patch={'public_url':'https://two.acme.test:18444','tls': {'enabled': True, 'host': '127.0.0.1', 'port': 18444,
                          'challenge_host': '127.0.0.3', 'challenge_port': 8080, 'acme': {
                              'enabled': True, 'directory_url': self.ca['directory_url'], 'email': 'operator@two.acme.test',
                              'domains': ['two.acme.test'], 'accept_terms': True, 'renew_before_days': 1,
                              'retry_seconds': 30, 'order_timeout_ms': 30000, 'ca_cert_file': 'directory-root.pem'}}})
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if self.admin.api({'op': 'tls_status'})['https_state'] == 'ready':
                break
            time.sleep(.1)
        else:
            raise AssertionError('Second actual ACME-issued peer readiness')
        self.peer_tokens = config['agents']
        self.a = self.origin_admin.api({'op': 'config_get'})['config']
        self.b = self.admin.api({'op': 'config_get'})['config']
        assert self.a['server_id'] != self.b['server_id']
        self.outgoing, self.incoming = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.peer_url = 'https://two.acme.test:18444'
        self.origin_url = 'https://one.acme.test:18443'
        for admin, local, remote, url, outgoing, incoming in (
                (self.origin_admin, self.a, self.b, self.peer_url, self.outgoing, self.incoming),
                (self.admin, self.b, self.a, self.origin_url, self.incoming, self.outgoing)):
            admin.mutate('config_update', patch={'federation': {'description': 'Owned HTTPS federation fixture',
                         'timeout_ms': 3000, 'retry_ms': 100, 'catalog': {'visible': True, 'entries': []},
                         'peers': [{'server_id': remote['server_id'], 'url': url, 'token': outgoing,
                                    'inbound_token': incoming, 'project_pairs': [{'local_project_id': local['project_id'],
                                                                               'remote_project_id': remote['project_id']}]}]}})
        self.check('before_rotation')

    def check(self, stage):
        for runtime, tokens, peer in ((self.origin_runtime, self.origin_tokens, self.b),
                                      (self.runtime, self.peer_tokens, self.a)):
            client = PublicClient(runtime.base)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                peers = client.rpc({'op': 'federation_directory'}, tokens['agent-a'])['peers']
                if any(row['server_id'] == peer['server_id'] and row['project_id'] == peer['project_id'] and
                       row['status'] == 'ready' for row in peers):
                    break
                time.sleep(.1)
            else:
                raise AssertionError('Actual outbound peer HTTPS catalog must validate and become ready')
        leaves = []
        for local, remote, url, token in ((self.a,self.b,self.peer_url,self.outgoing),
                                          (self.b,self.a,self.origin_url,self.incoming)):
            client = PublicClient(url, trust=self.ca['issuer_root'], bearer=token)
            body = {'protocol_version': 2, 'op': 'catalog', 'origin_server_id': local['server_id'],
                    'origin_project_id': local['project_id'], 'destination_project_id': remote['project_id']}
            code, value, _ = client.request('/federation/v2', body)
            assert code == 200 and value['server_id'] == remote['server_id'] and value['project_id'] == remote['project_id']
            import hashlib
            leaves.append(hashlib.sha256(client.handshakes[-1]['der']).hexdigest())
            denied = PublicClient(url, trust=self.ca['issuer_root'], bearer='wrong-current-peer-token')
            assert denied.request('/federation/v2', body)[0] == 401
        self.events.append({'stage': stage, 'two_real_servers': True, 'outbound_verified_https_catalogs': True,
                            'inbound_https_v2_catalog': True, 'wrong_peer_token_denied': True,
                            'actual_handshake_leaf_sha256': leaves,
                            'scope': 'No source/discovery model answer quality claimed'})

    def close(self):
        if self.runtime:
            self.runtime.stop()
