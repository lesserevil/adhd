# Kafka event service and deployment

Each logical ADHD server owns a private Kafka/KRaft service; all of its projects
share that service. Agents use authenticated A2A and never receive broker
credentials. Federated peers contact ADHD, not Kafka. Raw streams and literal
backend search need no model. Optional semantic filters and semantic search use
the separately configured decision service.

## Artifact and license inventory

The initial supported package is Linux amd64, Confluent Platform **8.3.2**
(Kafka 4.3 line), with immutable per-platform image manifests:

| Dependency | Image digest | License |
| --- | --- | --- |
| Kafka broker | `confluentinc/cp-kafka@sha256:23b7aed3099df6c95e31e8c4bf3b20682e360edbf9867bc2eac978e32c89cf7f` | Apache Kafka Apache-2.0; bundled image packages retain their own licenses. |
| REST Proxy and maintained Java Kafka client | `confluentinc/cp-kafka-rest@sha256:85f286aa0b8b6cfc1977d81bdb9b5eb3ece4942563afd49862e14d5e92ac7058` | Confluent Community License, external source-available dependency. |
| Optional Nemotron service | `ghcr.io/pst2154/nemotron-deciffusion@sha256:494aac2d7af43b7a70234792623a510bf29045a45b3aa893bc3170108ded9cea` | Service, CUDA/image dependencies and model checkpoint retain their licenses; see [model service](model-service.md). |

ADHD remains Apache-2.0. That license does not relicense external dependencies.
REST Proxy's Community License includes a restriction on competing hosted service
offerings; review the [upstream license](https://github.com/confluentinc/kafka-rest/blob/master/LICENSE)
for your distribution. Component interoperability and supported patch lines are
published in the [Confluent matrix](https://docs.confluent.io/platform/current/installation/versions-interoperability.html).
The hub uses Elixir/OTP HTTP against the [REST Proxy v2 API](https://docs.confluent.io/platform/current/kafka-rest/api.html),
not a newly authored Kafka wire client. No registry authentication or commercial
Confluent security plugin is required by these manifests.

## Model-free Compose application

Use the qualified hub image produced by the ordinary build lifecycle. Do not use
a historical image for this architecture. Initialize once as the account that
will own the container data (or adjust the UID/GID to match):

```sh
mkdir -p _build/operator/data
python3 deploy/init-config.py _build/operator/config
export ADHD_CONFIG_DIR="$PWD/_build/operator/config"
export ADHD_DATA_DIR="$PWD/_build/operator/data"
export ADHD_UID="$(id -u)" ADHD_GID="$(id -g)"
export ADHD_HUB_IMAGE=adhd-hub:qualified
docker compose -p adhd -f deploy/app.compose.yaml up -d --wait
```

`init-config.py` refuses to overwrite a configuration. Its randomly generated
server identity must survive replacement. Back up the entire config directory,
including the first-install administrator password file that the hub creates.
The hub can atomically update files in this directory for hot Admin settings.
Set `--public-url` at initialization to the actual agent-facing origin, including
any mapped port (for example `http://127.0.0.1:18766`) or HTTPS ingress origin.
The A2A card advertises this configured URL; a port-forward or proxy does not
rewrite it. The listener remains container port 8766. Change the public URL hot
in Admin when moving an installation. Hub HTTP is bound to host loopback; place your authenticated TLS ingress in front
of it for remote access. Never publish the broker/controller ports or REST Proxy.
The qualification-only `events.test.compose.yaml` exposes REST Proxy to loopback
and is excluded from the application package.

Broker readiness precedes proxy readiness and initial hub creation. After start,
a broker failure appears in eventing diagnostics; the hub keeps its durable
outbox and retries. HTTP liveness is separate from model availability. An accepted
original and handoff is not a claim that recipients have received or acknowledged
it. Admin shows durable handoff and subscription processing progress.

The baseline starts only hub, broker and proxy. To run the existing GPU service,
add `-f deploy/app.model.compose.yaml --profile model` and set the verified
`MODEL_CHECKPOINT`, UID/GID and GPU selection as documented in
[model service](model-service.md). Alternatively configure an existing remote
endpoint in Admin. Set matcher URL `http://model:8770/v1/systemone` for the Compose
model. Enabling a model/filter is a hot hub setting; adding the optional GPU
container is an infrastructure operation.

## Kubernetes application

Plain manifests are owned here rather than a third-party chart/operator. The
baseline is one hub replica using `Recreate`, one broker/controller StatefulSet
and one proxy replica. This single-writer hub may not be scaled above one against
its current store. A default dynamic StorageClass, amd64 nodes and a CNI enforcing
NetworkPolicy are required. This is a single-node durability topology, not an HA
Kafka cluster. The manifests request bounded CPU/memory and persistent volumes.

Set the seed `public_url` to the actual HTTPS ingress origin (or explicit
qualification port-forward origin), so SDK clients follow the correct A2A card.
Create the namespace and private config seed, select both image references in a
local overlay to the accepted immutable hub image, then apply:

```sh
kubectl apply -f deploy/k8s/events.yaml
kubectl -n adhd create secret generic hub-seed \
  --from-file=hub.json="$ADHD_CONFIG_DIR/hub.json"
# Set the hub and config-seed images in your reviewed local kustomize overlay.
kubectl apply -k deploy/k8s
kubectl -n adhd rollout status statefulset/kafka
kubectl -n adhd rollout status deployment/kafka-rest
kubectl -n adhd rollout status deployment/hub
kubectl -n adhd port-forward service/hub 8766:8766
```

The seed Secret is copied only when the mutable configuration is absent. Updating
it does not replace hot Admin state. `/config` and `/data` use separate directories
on the hub PVC. Neither static placeholders nor bootstrap credentials are checked
into these manifests. Applications do not receive Kubernetes API tokens. Network
policies allow broker ingress from broker/proxy and proxy ingress from hub only;
agent ingress terminates at the hub service. Kubernetes Secret encryption at rest
and TLS ingress are deployment responsibilities.

Apply `deploy/k8s/model.yaml` only when a GPU device plugin and a verified,
prepopulated model-checkpoint PVC are available. It never downloads model weights.
Use `http://model:8770/v1/systemone` as the hot matcher endpoint. The no-GPU baseline
never creates this PVC or pod.

## Recovery, backups and upgrades

The named Kafka volume and hub bind directories (Compose), or broker/hub PVCs
(Kubernetes), are separate durable domains. Never use `compose down -v`, delete a
PVC, change `server_id` or initialize a new KRaft cluster ID as a restart procedure.
Graceful shutdown allows the hub to stop work before its process exits and allows
Kafka time to flush; persistent originals/outbox and delivery IDs handle retries.
REST Proxy consumer instances are ephemeral; positions must be restored from the
hub's durable checkpoint, not assumed from a previous HTTP consumer instance.

For a consistent cold backup, stop/pause publication, drain or record pending
outbox and materialization positions, stop the hub and proxy, then stop Kafka.
Snapshot both durable domains and config as one labeled recovery set. Preserve
volume ownership and broker metadata. Restore both to compatible pinned images
before admitting new publication, verify IDs/offsets and pending deliveries, then
resume. Copying a live DETS file or a live broker directory is not a valid backup.
Do not restore only Kafka and infer that original facts or agent acknowledgements
have been restored.

Hub broker endpoint/timeouts and model/filter settings are revisioned hot Admin
configuration. Static Kafka listener/controller settings, broker images and
persistent storage sizes belong to deployment tooling and may roll Kafka without
restarting the hub. Rotate hub-managed secrets through Admin. Broker/proxy security
credentials are infrastructure secrets: stage the new credential, roll the proxy
as required, hot-update the hub reference, verify connectivity, then retire the
old credential. The supplied isolated baseline uses private plaintext transport;
shared/untrusted cluster networks require a reviewed TLS/SASL deployment overlay.

For broker upgrades, back up first, verify the supported client/broker matrix,
retain KRaft IDs and volumes, change exact image pins in a reviewed overlay and
roll the proxy/broker with a documented outage budget. A one-broker deployment has
an outage during replacement. Replication factor one and `acks=all` cannot survive
loss of its only disk/node. A replicated deployment needs at least three
controllers/brokers, replication factor three, minimum ISR two and separate fault
domains before stronger availability claims. Image rollback compatibility depends
on Kafka metadata/feature changes; restoring a coherent backup may be required.

The app bounds pending accepted outbox and delivery work; full queues reject
new admission explicitly. Kafka retention does not delete original facts or
acknowledgement state. Inspect lag, poison records, filter retry/backlog and
retention gaps in Admin. Recover gaps through authorized replay from originals;
never reset to latest and assert complete delivery.

## Qualification

`python3 tests/kafka_service.py --url URL --output _build/.../service.json` exercises
real topic creation, ordered publication, manual consumer replacement/replay,
explicit durable-position restoration and retention settings. It deliberately
labels its result service-only: it does not prove A2A, backend search, application
migration, GPU scheduling or production HA. Combined qualification must bind those
tests to the accepted app artifact, image, broker/proxy pins and exact manifests.

The [service qualification manifest](../../verification/kafka-service-qualified.json)
binds the real Compose and Kubernetes service probes, including retained records
after broker restart/pod replacement, to their exact image and manifest inputs.
Its scope excludes full-hub acceptance and release qualification.

For diagnostic app smoke tests, use the official SDK suite against the published
origin and a private credentials file. The two-phase recovery harness accepts an
operator-controlled restart between its phases:

```sh
python3 tests/multi_acceptance.py --rest-url "$BASE" \
  --credentials "$PRIVATE_CREDENTIALS" --report _build/sdk.json
python3 tests/kafka_platform_recovery.py --rest-url "$BASE" \
  --credentials "$PRIVATE_CREDENTIALS" --phase before \
  --snapshot _build/recovery-private.json --report _build/before.json
# Restart the owned hub container or replace its pod, preserving durable volumes.
python3 tests/kafka_platform_recovery.py --rest-url "$BASE" \
  --credentials "$PRIVATE_CREDENTIALS" --phase after \
  --snapshot _build/recovery-private.json --report _build/after.json
```

For an existing host-local model that containers cannot address directly, the
qualification relay binds only explicitly supplied private Docker bridge IPs.
It forwards to the already running model, caps concurrent requests, total calls,
request/response sizes and timeouts, and records typed responses plus request
hashes instead of raw request state. No model/container configuration is changed:

```sh
python3 tests/kafka_platform_gateway.py --bind "$PRIVATE_BRIDGE_IP" \
  --report _build/model-relay.json &
relay_pid=$!
python3 tests/kafka_platform_model.py --rest-url "$BASE" \
  --credentials "$PRIVATE_CREDENTIALS" \
  --model-url "http://$PRIVATE_BRIDGE_IP:18771/v1/systemone" \
  --gateway-report _build/model-relay.json --report _build/optional-model.json
kill -TERM "$relay_pid"
wait "$relay_pid"
```

Run these tests only against isolated fixtures: the SDK suite changes projects,
roles and memberships; the optional-model suite changes matcher configuration and
subscriptions before restoring model-free operation. Keep the private credentials,
password files and recovery snapshot out of Git. These diagnostic commands do not
replace accepted-artifact staging or final lifecycle qualification.

The [candidate platform diagnostic](../../verification/kafka-platform-diagnostic.json)
records eight official-SDK checks per platform, durable hub replacement and four
live Nemotron decisions across Compose and Kubernetes. Its image is explicitly a
lifecycle-unqualified diagnostic candidate. The temporary model relay was removed
and the existing model remained ready. Final accepted-artifact platform
qualification, browser coverage and the documented infrastructure upgrade/security
gates remain separate requirements.

## REST authentication and TLS boundary

The supplied private baseline does not enable REST Proxy HTTP authentication or
Kafka SASL. Sending an `Authorization: Bearer` header to that baseline does not
make it authenticated: the receiver must be configured to validate it. The hub's
optional hot `eventing.bearer_token` is an HTTP bearer credential, not a Kafka
SASL password, a Jetty Basic credential or the hub's user-login OIDC configuration.
Keep these security domains separate.

CP 8.3 documents three REST client authentication choices: HTTP Basic, mTLS and
OAuth/OIDC. The hub's bearer header maps to the OAuth/OIDC choice, provided the
proxy actually enables a trusted issuer, JWKS verification and an expected
audience. The documented standalone configuration uses
`rest.servlet.initializor.classes=io.confluent.common.security.jetty.initializer.AuthenticationHandler`
plus `oauthbearer.jwks.endpoint.url`, `oauthbearer.expected.issuer`,
`oauthbearer.expected.audience` and the configured subject/groups claims.
[Confluent's OAuth configuration](https://docs.confluent.io/platform/8.3/security/authentication/oauth-oidc/configure-rest-proxy.html)
is the authority for those properties. Security extensions have their own license
conditions; the baseline's Community License inventory is not a license claim
for enterprise authorization or principal propagation.

A reviewed secure overlay must configure both connections independently: hub to
REST Proxy, and REST Proxy to Kafka. Proxy HTTPS uses `listeners=https://...`,
a server keystore and its passwords; mTLS additionally requires a client truststore
and required client authentication. Proxy-to-broker TLS/SASL uses
`client.security.protocol=SASL_SSL`, the selected `client.sasl.mechanism`, JAAS
credentials and trusted broker certificates. Native Kafka broker ACLs remain
necessary when its principals need restricted topic/group access. See the
[CP 8.3 security guide](https://docs.confluent.io/platform/8.3/kafka-rest/production-deployment/rest-proxy/security.html)
and [connection configuration](https://docs.confluent.io/platform/8.3/kafka-rest/production-deployment/rest-proxy/config.html).

These are deployment integration requirements, not qualified overlays shipped in
the baseline. Before claiming secured rotation, prove missing/invalid/expired
credentials fail, current credentials pass, hot replacement preserves the hub
process and durable cursor, retired credentials fail, and logs/Admin redact all
secrets. Kafka/SASL credentials and certificate rotation may roll broker/proxy
pods; they must not require a hub restart. Do not enable an undocumented reverse
proxy or principal-propagation plugin and infer that these checks passed.

The [single-node patch-upgrade proof](../../verification/kafka-upgrade-qualified.json)
qualifies the pinned broker change from CP 8.3.1 to 8.3.2 while keeping REST Proxy
8.3.2 running. The same volume retained three original records and the actual
broker group checkpoint; the first new publication appended at the next offset.
`tests/kafka_upgrade.py` provides explicit before/after phases for this exercise.
It does not qualify a cross-minor metadata upgrade or replicated availability.

REST Proxy v2 offset translation is covered by a round-trip assertion: after
processing records 0 through 2, POST `/offsets` carries the **last consumed offset
2** and GET `/offsets` reports broker **next offset 3**. A restored manual consumer
uses position 3. These are distinct wire positions; posting 3 to commit would
advance the broker checkpoint to 4. The corrected service probe checks this
against real Kafka instead of inferring commit state from an empty poll.
