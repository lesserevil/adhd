"""Inert independent ACME acceptance data and certificate observations.

No ACME client, service, process or socket starts here. DER parsing alone never
qualifies a trust chain; the runtime harness must use an ordinary verifying TLS
client and retain that handshake separately.
"""
from datetime import timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from cryptography import x509
from cryptography.hazmat.primitives import serialization


TEST_DOMAINS=('hub.acme.fixture.test','peer.acme.fixture.test')
TOKEN='aBcdEfghIjklMnopQrstuVwxyZ0123456789_-abcDEF'


def challenge_request_vectors():
    prefix='/.well-known/acme-challenge/'
    return [
        {'id':'active-token','path':prefix+TOKEN,'expectation':'exact-active-key-authorization'},
        {'id':'unknown-token','path':prefix+'Z'*43,'expectation':'404'},
        *[{'id':name,'path':path,'expectation':'404'}for name,path in [
            ('admin-route','/admin'),('root-route','/'),('a2a-route','/a2a'),
            ('token-directory',prefix),('dotdot',prefix+'../account.key'),
            ('encoded-dotdot',prefix+'%2e%2e%2faccount.key'),
            ('double-encoded-dotdot',prefix+'%252e%252e%252faccount.key'),
            ('extra-slash',prefix+TOKEN+'/extra'),('backslash',prefix+'..\\account.key'),
            ('percent-nul',prefix+TOKEN+'%00'),('query',prefix+TOKEN+'?suffix=1'),
            ('double-leading-slash','/'+prefix+TOKEN),('encoded-separator',prefix+TOKEN+'%2fextra')]],
    ]


def raw_challenge_get(path,host):
    # Explicit ASCII request target, preserving adversarial escapes without URL
    # normalization by a client library. No request is sent by this fixture.
    assert '\r'not in path and '\n'not in path and '\r'not in host and '\n'not in host
    return ('GET '+path+' HTTP/1.1\r\nHost: '+host+'\r\nConnection: close\r\n\r\n').encode('ascii')


def certificate_facts(der,expected_domains,now):
    assert now.tzinfo is not None
    cert=x509.load_der_x509_certificate(der)
    names=cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    assert len(names)==len(set(names))and set(names)==set(expected_domains),'Certificate SAN set differs'
    now=now.astimezone(timezone.utc)
    assert cert.not_valid_before_utc<=now<cert.not_valid_after_utc,'Certificate outside validity interval'
    spki=cert.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    return {'leaf_der_sha256':hashlib.sha256(der).hexdigest(),
            'public_key_spki_sha256':hashlib.sha256(spki).hexdigest(),
            'serial_number_hex':format(cert.serial_number,'x'),'dns_names':sorted(names),
            'not_before':cert.not_valid_before_utc.isoformat(),'not_after':cert.not_valid_after_utc.isoformat(),
            'validity_seconds':(cert.not_valid_after_utc-cert.not_valid_before_utc).total_seconds(),
            'chain_trust_checked_here':False}


def certificate_key_pair_facts(der, private_key_pem):
    """Compare actual parsed public keys independently; never publish key bytes."""
    assert len(der) <= 1048576 and len(private_key_pem) <= 65536
    cert = x509.load_der_x509_certificate(der)
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    left, right = public(cert.public_key()), public(key.public_key())
    assert left == right, 'Issued leaf does not match private key public SPKI'
    return {'key_pair_match': True, 'public_key_spki_sha256': hashlib.sha256(left).hexdigest()}


def active_private_key_facts(hub_root, der):
    """Read only the owned active generation and compare its actual public key."""
    root=Path(hub_root)/'acme'
    state=json.loads((root/'state.json').read_text())
    generation=state['active']
    assert isinstance(generation,str) and re.fullmatch(r'[A-Za-z0-9_-]{32}',generation)
    current=root/'generations'/generation
    for path in (root,root/'generations',current):
        metadata=path.lstat()
        assert stat.S_ISDIR(metadata.st_mode) and metadata.st_uid==os.getuid() and metadata.st_mode&0o777==0o700
    path=current/'key.pem'
    metadata=path.lstat()
    assert stat.S_ISREG(metadata.st_mode) and metadata.st_nlink==1 and metadata.st_uid==os.getuid()
    assert metadata.st_mode&0o777==0o600 and metadata.st_size<=65536
    return certificate_key_pair_facts(der,path.read_bytes())
