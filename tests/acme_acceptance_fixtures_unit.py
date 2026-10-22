"""Pure fixture/oracle checks: ephemeral in-memory certs, no TestCA/server/process."""
from datetime import datetime,timedelta,timezone
import unittest
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from acme_acceptance_fixtures import(TEST_DOMAINS,TOKEN,certificate_facts,
                                     challenge_request_vectors,raw_challenge_get)


def ephemeral_certificate(names,start,end):
    key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'pure-fixture-only')])
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(start).not_valid_after(end)
          .add_extension(x509.SubjectAlternativeName([x509.DNSName(n)for n in names]),critical=False)
          .sign(key,hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.DER)


class FixtureTest(unittest.TestCase):
    def test_raw_adversarial_request_target_is_preserved(self):
        vectors=challenge_request_vectors()
        self.assertEqual(len({v['id']for v in vectors}),len(vectors))
        for v in vectors:self.assertTrue(raw_challenge_get(v['path'],TEST_DOMAINS[0]).startswith(('GET '+v['path']+' HTTP/1.1').encode()))
        self.assertIn('%2e%2e%2f',raw_challenge_get(next(v['path']for v in vectors if v['id']=='encoded-dotdot'),TEST_DOMAINS[0]).decode())
        with self.assertRaises(AssertionError):raw_challenge_get('/bad\r\nInjected: x',TEST_DOMAINS[0])

    def test_certificate_metadata_requires_exact_domains_and_current_validity(self):
        now=datetime(2030,1,1,tzinfo=timezone.utc)
        der=ephemeral_certificate(TEST_DOMAINS,now-timedelta(minutes=1),now+timedelta(minutes=2))
        facts=certificate_facts(der,TEST_DOMAINS,now)
        self.assertEqual(facts['validity_seconds'],180)
        self.assertFalse(facts['chain_trust_checked_here'])
        for domains,at in [(TEST_DOMAINS[:1],now),(TEST_DOMAINS,now+timedelta(minutes=2)),(TEST_DOMAINS,now-timedelta(minutes=2))]:
            with self.assertRaises(AssertionError):certificate_facts(der,domains,at)

    def test_rotation_requires_observed_leaf_change_not_a_status_counter(self):
        now=datetime(2030,1,1,tzinfo=timezone.utc)
        observations=[certificate_facts(ephemeral_certificate(TEST_DOMAINS,now-timedelta(seconds=1),now+timedelta(minutes=2)),TEST_DOMAINS,now)for _ in range(2)]
        self.assertNotEqual(observations[0]['leaf_der_sha256'],observations[1]['leaf_der_sha256'])
        self.assertEqual(observations[0]['dns_names'],observations[1]['dns_names'])

if __name__=='__main__':unittest.main()
