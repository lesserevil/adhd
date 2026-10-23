"""Pure owned-file/key guards and failed-start cleanup; no CA/VM/socket."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from acme_account_continuation import account_facts,missing_key_cold_fault

class AccountChecks(unittest.TestCase):
    def fixture(self,d):
        hub=Path(d);root=hub/'acme';identity='a'*64
        account=root/'accounts'/identity
        key=account/'accounts/localhost_19100/operator/operator.key'
        key.parent.mkdir(parents=True)
        raw=ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        key.write_bytes(raw);key.chmod(0o600)
        registration=key.with_suffix('.json');registration.write_text('{"registration":"owned-placeholder"}');registration.chmod(0o600)
        state=root/'state.json';state.write_text(json.dumps({'accounts':{identity:{'keys':{str(key.relative_to(account)):hashlib.sha256(raw).hexdigest()}}},'active':'b'*32,'last_attempt_at':1}));state.chmod(0o600)
        (root/'generations'/('b'*32)).mkdir(parents=True)
        return hub,key,state

    def test_actual_pinned_client_layout_and_nonempty_witness(self):
        with tempfile.TemporaryDirectory()as d:
            hub,key,state=self.fixture(d);facts,_=account_facts(hub)
            encoded=json.dumps(facts)
            self.assertNotIn('PRIVATE KEY',encoded);self.assertNotIn('operator',encoded)
            self.assertEqual(len(next(iter(facts.values()))['keys']),1)
            value=json.loads(state.read_text());next(iter(value['accounts'].values()))['keys']={};state.write_text(json.dumps(value))
            with self.assertRaisesRegex(AssertionError,'witness'):account_facts(hub)

    def test_missing_changed_or_linked_key_rejected(self):
        for mode in ['missing','changed','symlink']:
            with tempfile.TemporaryDirectory()as d:
                hub,key,_=self.fixture(d)
                if mode=='changed':key.write_bytes(b'changed')
                else:
                    raw=key.read_bytes();key.unlink()
                    if mode=='symlink':
                        foreign=Path(d)/'foreign';foreign.write_bytes(raw);foreign.chmod(0o600);key.symlink_to(foreign)
                with self.assertRaises((AssertionError,FileNotFoundError)):account_facts(hub)

    def test_failed_start_preserves_primary_and_restores_only_owned_original_key(self):
        with tempfile.TemporaryDirectory()as d:
            hub,key,_=self.fixture(d);before=key.read_bytes();runtime=Mock();runtime.process=None
            failure=OSError('original startup failure');runtime.start.side_effect=failure
            with self.assertRaises(OSError)as caught:missing_key_cold_fault(runtime,hub,'unused','unused')
            self.assertIs(caught.exception,failure);runtime.stop.assert_called_once()
            self.assertEqual(key.read_bytes(),before);account_facts(hub)
