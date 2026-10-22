import unittest
from acme_challenge_relay import ChallengeRelay, parse_request, public_event
from acme_acceptance_fixtures import TOKEN, raw_challenge_get


class RelayChecks(unittest.TestCase):
    def test_preserves_exact_host_and_target(self):
        path = '/.well-known/acme-challenge/' + TOKEN
        self.assertEqual(parse_request(raw_challenge_get(path, 'one.acme.test:8080')), (path, 'one.acme.test:8080'))

    def test_rejects_ambiguous_or_proxy_requests(self):
        good = raw_challenge_get('/.well-known/acme-challenge/' + TOKEN, 'one.acme.test')
        for raw in (good.replace(b'GET ', b'POST ', 1), good.replace(b'HTTP/1.1', b'HTTP/2'),
                    good.replace(b'Connection:', b'Host: second\r\nConnection:'),
                    good.replace(TOKEN.encode(), b'../secret'), good.replace(TOKEN.encode(), TOKEN.encode()+b'?q=1'),
                    good.replace(b'Connection:', b'Content-Length: 1\r\nConnection:'),
                    good + b'x', b'x'*8193):
            with self.subTest(raw_sha=__import__('hashlib').sha256(raw).hexdigest()):
                with self.assertRaises((AssertionError, ValueError)):
                    parse_request(raw)

    def test_evidence_does_not_publish_proof_or_token(self):
        import json
        event = public_event('/.well-known/acme-challenge/'+TOKEN, 'one.acme.test', 200, b'private-proof', 'hold')
        text = json.dumps(event)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn('private-proof', text)
        self.assertNotIn('one.acme.test', text)

    def test_inert_construction_and_caps(self):
        relay = ChallengeRelay()
        self.assertIsNone(relay.server)
        self.assertEqual(relay.snapshot()['requests'], 0)
        relay.close()
        self.assertTrue(relay.snapshot()['closed'])
        for args in ({'port':18080}, {'bind':'0.0.0.0'}, {'hold_seconds':31}, {'max_requests':257}):
            with self.assertRaises(AssertionError):
                ChallengeRelay(**args)
        pair = ChallengeRelay(upstreams={'one.acme.test':18080, 'two.acme.test':18081})
        self.assertEqual(pair.upstreams, {'one.acme.test':18080, 'two.acme.test':18081})
        self.assertIsNone(pair.server)
        for upstreams in ({'foreign.acme.test':18080}, {'one.acme.test':8080}, {'one.acme.test':True}):
            with self.assertRaises(AssertionError):ChallengeRelay(upstreams=upstreams)


if __name__ == '__main__':
    unittest.main()
