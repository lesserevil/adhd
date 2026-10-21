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

The separate [Kubernetes diagnostic manifest](kubernetes-manifest.json) adds a
live optional-profile run without changing the earlier rendering-only claims.
Its five checks cover actual Secret-mounted native HTTPS/JWT authentication,
hot hub token replacement and retired-key denial, replacement PKCS12 passwords
and server certificate in the Kubernetes Secret followed by REST pod replacement,
broker pod replacement against the same PVC, and continued A2A progress with the
actual group checkpoint advancing from 1 to 2. The native hub process remained
running; original and acknowledgement identities survived. Cleanup removed the
owned namespace, PVC and dynamically provisioned PV. Log checks found none of the
synthetic credentials. It does not claim uninterrupted REST availability during
an infrastructure rollout.

Run against an operator-owned disposable Kubernetes cluster with Delete-reclaim
storage and a private host bridge reachable by its pods:

```sh
.venv/bin/python tests/kafka_oauth_k8s.py --hub "$CANDIDATE" \
  --kubectl "$KUBECTL" --kubeconfig "$KUBECONFIG" \
  --namespace adhd-oauth-security --issuer-bind "$PRIVATE_BRIDGE" \
  --broker-image "$PINNED_BROKER" --proxy-image "$PINNED_PROXY" \
  --work _build/oauth-k8s-security --report _build/oauth-k8s-security.json
```

The harness refuses an existing namespace. It applies the authored deployment
and OAuth patch with explicitly supplied immutable image identities. Its issuer
is bounded and synthetic. Keystores/passwords change through the real Secret
object; a new REST pod activates them. The original proxy/broker registry
manifests differed from the offline imported OCI manifests on this host. The
read-only `tests/kafka_image_equivalence.py` probe verified both imported config
identities and every uncompressed layer against the original pinned local images;
that independent report is bound in the Kubernetes manifest.
