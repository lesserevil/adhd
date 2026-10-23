"""Inert post-restart real-account continuation and known-key-loss fault.

Caller supplies an already-owned runtime/trusted client and exclusive CA window.
No new account is fabricated, key rewritten by the product, or issuer bypassed.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from uuid import uuid4
from cryptography.hazmat.primitives import serialization
from acme_acceptance_fixtures import certificate_facts
from acme_runtime import PublicClient, wait_managed_https


def private_bytes(path, maximum=65536):
    path=Path(path)
    before=path.lstat()
    assert stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1
    assert before.st_mode&0o777==0o600 and before.st_size<=maximum
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        actual=os.fstat(fd)
        assert (actual.st_dev,actual.st_ino)==(before.st_dev,before.st_ino)
        raw=os.read(fd,maximum+1)
        assert len(raw)==before.st_size and len(raw)<=maximum and not os.read(fd,1)
        after=path.lstat()
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink,s.st_mode)
        assert identity(after)==identity(os.fstat(fd))==identity(before)
        return raw
    finally:os.close(fd)


def account_facts(hub):
    """Independent real PEM/SPKI oracle; require actual witnessed keys, not {}."""
    root=Path(hub)/'acme';state=json.loads(private_bytes(root/'state.json',2097152))
    facts={};actual_paths={}
    for identity,record in state['accounts'].items():
        assert len(identity)==64 and all(c in '0123456789abcdef'for c in identity)
        account=root/'accounts'/identity
        paths=sorted((account/'accounts').rglob('*.key'))
        assert paths,'Real maintained-client account key must exist'
        actual={str(p.relative_to(account)):hashlib.sha256(private_bytes(p)).hexdigest()for p in paths}
        assert record['keys']==actual,'Persisted witness must cover all actual account keys exactly'
        rows=[]
        for path in paths:
            key=serialization.load_pem_private_key(private_bytes(path),password=None)
            der=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
            rows.append({'relative_path_sha256':hashlib.sha256(str(path.relative_to(root)).encode()).hexdigest(),
                         'public_spki_sha256':hashlib.sha256(der).hexdigest()})
        registration={hashlib.sha256(str(p.relative_to(root)).encode()).hexdigest():hashlib.sha256(private_bytes(p)).hexdigest()
                      for p in sorted((account/'accounts').rglob('*.json'))}
        assert registration,'Actual account registration metadata required'
        facts[identity]={'keys':rows,'registration_file_hashes':registration}
        actual_paths[identity]=paths
    assert facts,'Initialized real account required'
    return facts,actual_paths


def renew_after_restart(admin, hub, issuer_root, *, seconds=35):
    """Call only AFTER caller's recorded real restart/move and trusted readiness."""
    before,_=account_facts(hub)
    old=admin.api({'op':'tls_status'})
    assert old['https_state']=='ready' and old['certificate'] is not None
    revision=admin.api({'op':'config_get'})['config_revision']
    cmd={'op':'tls_renew','message_id':uuid4().hex,'expected_revision':revision,'confirm':True}
    receipt=admin.api(cmd)
    assert receipt=={'accepted':True,'config_revision':revision}
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        current=admin.api({'op':'tls_status'})
        if current['certificate'] and current['certificate']['sha256']!=old['certificate']['sha256']:break
        time.sleep(.1)
    else:raise AssertionError('Original bounded real renewal after restart')
    secure=PublicClient('https://one.acme.test:18443',trust=issuer_root)
    assert secure.request('/health')[0]==200
    cert=certificate_facts(secure.handshakes[-1]['der'],['one.acme.test'],datetime.now(timezone.utc))
    assert cert['leaf_der_sha256']==current['certificate']['sha256']
    after,_=account_facts(hub)
    assert after==before,'Real renewal must reuse original account keys/registration'
    assert admin.api(cmd)==receipt,'Exact MID replay remains idempotent'
    return {'passed':True,'actual_new_leaf':cert,'same_account_public_fingerprints':after,
            'registration_scope':'Same local registration files and public key fingerprints; CA registration-count claim requires independent issuer log proof'}


def missing_key_cold_fault(runtime,hub,issuer_root,password):
    """Stopped owned-key deletion; restore only after stopped fault observation."""
    assert runtime.process is None,'Caller must stop original owner first'
    facts,paths=account_facts(hub)
    key=next(iter(paths.values()))[0]
    original=private_bytes(key)
    root=Path(hub)/'acme';before=json.loads(private_bytes(root/'state.json',2097152))
    assert before['active'] is not None
    generations=sorted(p.name for p in (root/'generations').iterdir())
    key.unlink()
    primary=None
    try:
        runtime.start()
        client=PublicClient('https://one.acme.test:18443',trust=issuer_root)
        wait_managed_https(client,runtime)
        client.login('admin',password)
        value=client.api({'op':'tls_status'})
        assert value['last_error']['code']=='ACME_STORAGE' and value['acme_state']=='error'
        assert value['https_state']=='ready' and value['certificate'] is not None
        assert client.request('/health')[0]==200
        assert not key.exists(),'Known missing key must never be silently recreated'
        after=json.loads(private_bytes(root/'state.json',2097152))
        assert after['accounts']==before['accounts'] and after['active']==before['active']
        assert after['last_attempt_at']==before['last_attempt_at']
        assert sorted(p.name for p in (root/'generations').iterdir())==generations
        return {'passed':True,'observed_status':value,'preserved_account_fingerprints':facts,
                'key_restoration_scope':'Fixture restores exact original bytes only after stopping fault VM; product never reset witness/key'}
    except BaseException as error:
        primary=error;raise
    finally:
        try:
            runtime.stop()
            assert runtime.process is None
            fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                view=memoryview(original)
                while view:
                    n=os.write(fd,view);assert n>0;view=view[n:]
                os.fsync(fd)
            finally:os.close(fd)
            parent=os.open(key.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(parent)
            finally:os.close(parent)
            assert account_facts(hub)[0]==facts
        except BaseException as error:
            if primary:primary.add_note('Owned missing-key cleanup: '+type(error).__name__)
            else:raise
