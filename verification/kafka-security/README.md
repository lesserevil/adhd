# Native Kafka REST OAuth/TLS diagnostic

The manifest binds the exact generated diagnostic artifact, all source modules,
pinned CP8.3.2 images, optional deployment files, provider/probe harnesses and
sanitized reports. It is not a lifecycle/package/release attestation or a grant of
production Confluent licensing. Kubernetes coverage is read-only rendering.

The native hub diagnostic passed nine checks against a fresh real broker/proxy:
issuer TLS hostname verification, protected real v2/v3 operations, invalid bearer
cases, server trust verification, rejected invalid candidate credentials/trust,
hot bearer replacement with retired signing-key rejection, preserved original
and acknowledgement, and actual application/broker checkpoints advancing 1 to 2.
Teardown logs were checked for credentials, and all owned service resources were
removed. No existing broker, application or model service was changed. No semantic
model was started or used.

Run the committed harnesses in the repository's pinned Python test environment,
with native Elixir/Erlang on PATH, Docker available, and a fresh ignored work
directory. Use an operator-approved evaluation or licensed environment for the
native Confluent security handler:

```sh
.venv/bin/python tests/kafka_oauth.py --hub "$CANDIDATE" \
  --work _build/oauth-security --report _build/oauth-security.json \
  --project adhd-oauth-security --port 18087
.venv/bin/python tests/kafka_oauth_manifests.py --kubectl "$KUBECTL" \
  --work _build/oauth-render --report _build/oauth-render.json
```

The live harness creates its own private broker/proxy Compose project. It refuses
to adopt existing containers under that project name, binds diagnostic access to
loopback, runs a bounded synthetic HTTPS JWKS issuer on the private Docker bridge,
and deletes only its own containers, networks and volume afterward. Generated
keys, passwords, JWTs, completed properties and raw logs remain private under the
ignored work directory. The issuer exposes only test JWKS, not a production token
service or a user-login OIDC implementation.

The probe first gives the actual native JWKS client a trusted certificate for the
wrong hostname and requires authentication failure before any JWKS HTTP request.
It then repairs that fixture certificate, validates a signed JWT against issuer
and audience, rejects missing/invalid/expired credentials, exercises the real
hub through A2A and Admin, rejects invalid hot trust proposals, rotates the bearer,
retires the old JWKS key, and requires the old token to fail while the new token
works. A separate manually assigned REST consumer reads the actual broker group's
committed next position; it never fetches events or commits offsets.

The optional runtime profile uses Enterprise-licensed bundled security code under
its separately documented entitlement/trial conditions. It does not enable
principal propagation or claim that a header alone authenticates the proxy. Its
private plaintext proxy-to-broker lane is distinct from HTTPS/JWT security at the
REST boundary; the separate broker SASL_SSL example requires its own matching
listeners, credentials, trust, ACLs and runtime qualification.
