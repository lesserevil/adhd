---
name: Kafka-backed project events
summary: Durable publication handoff, A2A fanout and optional semantic filters
kind: component
---
# Kafka eventing and optional subscription filters

This contract replaces mandatory model matching for subscriptions and the earlier
no-broker restriction. Agent transport remains A2A1.0 SendMessage, not Kafka or a
new A2A method. multi/spec.md owns project admission and store boundaries. Legacy
filtered subscriptions and typed SystemOne decisions remain compatible.

## Selected adapter and configuration

Use maintained Confluent Kafka REST Proxy HTTP API v2 with the runtime standard
HTTP client; no handwritten Kafka binary protocol or model in raw delivery.
Deployment pins cp-kafka and cp-kafka-rest 8.3.2, including immutable image digests
in packaging. Kafka is Apache2; REST Proxy is Confluent Community License, an
external dependency whose license must be included/disclosed separately from
ADHD's Apache2 license. A dedicated Kafka/KRaft service plus REST Proxy serves
one ADHD server; multiple projects use that service. No Schema Registry needed.

Root `eventing` is exactly `{enabled,rest_url,topic_prefix,timeout_ms,retry_ms,
bearer_token,retention_ms,max_pending_events,max_pending_bytes}` with optional
fields/defaults: enabled=true, rest_url=http://127.0.0.1:8082,
topic_prefix="adhd", timeout_ms=3000 (100..30000), retry_ms=1000 (100..30000),
retention_ms=604800000 (3600000..31536000000), max_pending_events=100000
(1..1000000), max_pending_bytes=1073741824 (65536..1099511627776).
bearer_token is optional secret 24..4096 bytes. Prefix is 1..32 ASCII alphanumerics,
underscore or hyphen. URL is absolute HTTP(S), no userinfo/query/fragment;
HTTPS verifies hostname/certificates, no redirects. Secrets never enter responses,
logs, events or model inputs. An absent matcher or `matcher:null` disables models;
new installs must boot model-free. Explicit eventing.enabled=false is legacy
compatibility mode and MUST be exposed as such, never reported as Kafka-backed.

Create one topic per project, named PREFIX + "." + first16 lowercase hexadecimal
SHA256(UTF8(server_id)) + "." + first16 SHA256(UTF8(project_id)) + ".events.v1".
Persist and collision-check the full identities alongside topic assignment. Each
has one partition, delete retention, no compaction, replication/min.insync.replicas
from deployment topology. Use producer acks=all; single-broker means only one
broker copy, not HA. Partition-count changes are unsupported until a versioned
ordering migration; no automatic resizing. Agents/peers have no broker credentials.
Restrict broker/proxy network and ACLs to server and deployment administration.

## Original acceptance and broker event

A publish durably commits the immutable original, source/item deduplication,
project ingestion sequence, mutation retry result, subscription activation
snapshot and outbox item in one synchronized backend transition. This is the
acceptance point; broker outage after acceptance is pending transport, not lost
original. An outage may admit within backlog limits; exceeding either pending
limit returns BACKPRESSURE before accepting anything. Retries of already accepted
identities still return the original success, even while admission is blocked.
Publish result retains publication and matching:"pending" for legacy clients;
new eventing metadata reports event_id,project_sequence and state pending,
published or materialized without implying recipient acknowledgement.

The event key is project_id. The exact JSON value has required fields
`schema_version:1,event_id,server_id,project_id,project_sequence,publication_id,
author_id,created_at,publication`. IDs/timestamps/publication obey their original
contracts; project_sequence is a positive JSON integer. event_id is stable and
unique within server/project, derived from or durably paired with publication_id.
No role/auth/token/private-message fields. `publication` is the immutable accepted
original, not an index summary or model paraphrase. Encoded event <=262144 bytes.
Keep both source provenance and ingestion time; occurred_at does not reorder it.

Publish strictly in project_sequence order to partition0 using POST
/topics/TOPIC, Content-Type application/vnd.kafka.json.v2+json and
Accept application/vnd.kafka.v2+json,
body `{records:[{key:PROJECT_ID,value:EVENT,partition:0}]}`. Success requires
HTTP2xx and every returned offsets entry having null error_code/error and a valid
partition0/nonnegative integer offset. A2A success alone is not Kafka success.
Persist acknowledged offset before retiring the outbox item. Lost proxy replies
can produce physical duplicates; durable (server,project,event_id) deduplication
provides one logical event. Do not claim exactly-once network transmission.

## Consumer and fanout handoff

One durable ADHD fanout group per project topic, not one load-sharing group for
unrelated agent subscriptions. Group name TOPIC + ".fanout". Create REST consumer
with format=json, auto.offset.reset=earliest and auto.commit.enable=false;
assign partition0 of that topic. On every consumer-instance creation, POST its
positions endpoint with the durable next-offset before fetching; a broker group
commit does not restore a manually assigned consumer position. Poll with application/vnd.kafka.json.v2+json.
Never trust the consumer base_uri host from a response; construct its instance
URL under the configured REST endpoint and validate response identity. Consumers
may be replaced after process/proxy restart using the same group and durable
checkpoint. HTTP response and record batches have finite configured time/size
bounds; timeout is retryable, not an empty semantic result.

Validate envelope, topic/partition, project identity, original equality and event
sequence against the accepted backend before materialization. Persist raw
recipient deliveries, filtered work, dedup identities and recoverable next-offset
checkpoint atomically, then POST explicit `{offsets:[{topic,partition:0,
offset:LAST_CONSUMED_OFFSET}]}` to the instance offsets endpoint. The REST v2
commit API adds one to the supplied consumed offset; with durable next-offset N,
POST N-1 and independently verify GET offsets reports N. In contrast, the
positions endpoint takes next-offset N directly. Never commit Kafka
progress first. Restart/rebalance may replay records safely. Broker offsets are
transport progress, unrelated to A2A acknowledgement.

Malformed, foreign or mismatching records are quarantined durably with digest,
offset and generic reason, never delivered or put into a model. Expose a blocked
gap and Admin repair/replay disposition; do not silently skip and claim complete
coverage. Other projects continue. Durable originals/outbox permit reconstruction
if retention expires; detect offset-out-of-range, record the missing range and
recover exact undelivered events in sequence before declaring caught-up. Never
reset to latest. A physical offset gap is not loss if all logical accepted events
are independently accounted for; record the reconciliation proof.

Retain unacknowledged deliveries and accepted originals independently of broker
retention. Keep dedup and retry records as long as their associated originals;
no time expiry. Filter backlogs are bounded separately. Admission fails before
limits, never evicts accepted pending work. On restore, bind backend, checkpoint,
broker identity/topic and replay generation; a mismatched or stale broker is
reconciled from originals before resuming, not trusted as complete.

## Subscription wire contract and revisions

`subscribe` accepts existing project_id and these optional fields: `mode`
(raw|filtered), `filter` (nonblank 1..4096 UTF8 bytes), legacy `description`
(same bound) and `selectors`. filter and description cannot coexist. Omitted
mode is filtered if filter/description exists, otherwise raw. Raw mode forbids
filter/description, including null/blank; filtered mode requires one nonblank
criterion and a configured matcher, else MODEL_UNAVAILABLE. Never synthesize a
filter to subscribe to everything. Legacy description maps exactly to filtered.

selectors is a closed object with optional arrays `information_type`,
`source_kind`,`source_id`,`author_id`; each array has 1..64 distinct exact strings
validated using the owning metadata/ID bounds. Keys combine with AND; values
within one key combine with OR. Omitted selectors means every project publication
across every agent, including the subscriber's own. Missing publication metadata
fails that selector. Private send deliveries are never project events.

A subscription records mode, criterion when filtered, selectors, revision,
active/paused state and activation project_sequence. Subscribe atomically captures
the latest accepted sequence; default receives only subsequent publications.
Subscription edits use a revisioned update_subscription command with required
subscription_id,expected_revision and a replacement mode/filter-or-description/
selectors, optional paused boolean. Unknown fields fail; owner only; idempotency
matches subscribe. Edits capture an effective sequence atomically. Already
accepted event/filter jobs keep their frozen revision; unsubscribe cancels pending
filtered jobs as before. Pause accepts no new event work; resume starts after its
new watermark, no hidden historical replay. Historical replay is an explicit
Admin-bounded project range with delivery dedup and provenance, never a change of
activation semantics. Legacy rows migrate as active filtered revision1.

One logical delivery per (project,recipient,publication), regardless of overlapping
subscriptions/modes. matches entries for raw are exactly
`{subscription_id,subscription_revision,mode:"raw"}`; filtered reasons add
mode:"filtered",probability_ppm,threshold_ppm,model plus subscription_revision to
the existing match evidence. Raw MUST NOT invent scores/model names. Existing
acknowledged delivery remains acknowledged when late reasons append. Direct
messages retain their separate authorized path. New event-materialized publication deliveries
retain the original publication's author_id as well as sender_id, source and
information_type; author_id and sender_id must agree. Legacy stored delivery
responses remain unchanged when replayed. Poll returns oldest currently
available durable deliveries by creation sequence; a later raw event may arrive
before an older filtered decision, explicitly no global completion-order promise.
Within the raw project stream ingestion order is preserved. Batch ack validates
all IDs before mutation, supports arbitrary order/reack and never advances past
unacknowledged unrelated records. Poll itself neither commits Kafka nor acks.

## Optional models, search and hot operations

Raw/selectors take zero model calls. Filtered work uses the existing short-response
SystemOne noul adapter and bounded retries; missing/malformed/error decisions
remain pending with error/usage status, never become a negative or raw disclosure.
Snapshot criterion/revision/threshold/model config; recheck authority and model
configuration generation before commit. Expired/revoked work is explicitly fenced.
Keep filtered, search/query and raw queues/budgets independent; round-robin
project work and bounded in-flight requests protect raw progress from a model
outage/saturated project. No model is used for permission or ownership decisions.

Originals and literal/metadata search/get commit with publication, so read-after-
publish succeeds even before broker catch-up. Search indexes report their own
project generation/watermark/lag; index lag cannot prove absence. Semantic history,
retrieval/archive/replay/optimizer require their documented model capabilities;
when disabled return MODEL_UNAVAILABLE or explicit unavailable child coverage,
never substitute an unqualified heuristic. Their failure leaves raw pub/sub and
literal search operational. Kafka retention never deletes fact history.

All configuration is hot except configuration-file location. Admin labeled forms
must cover broker URL/security, per-project topic/retention policy, backlog limits,
raw/filtered subscriptions, optional matcher and diagnostics. Secrets are write-only.
Expose accepted/published/materialized/search watermarks, lag, outbox/filter backlog,
consumer/checkpoint health, quarantine/gaps and retry status without credentials.
Server diagnostics are Admin-only; project views apply admission.

Changing broker URL, credentials or topic prefix fences old network attempts,
quiesces consumption, preserves accepted pending events and requires validated
identity/checkpoint reconciliation before commit. Failed apply retains old config.
Never reset offsets implicitly; retain old topic evidence until cutover complete.
Retention changes are validated against recoverable backend materialization.
Infrastructure static broker settings may require deployment rollouts, but not a
hub restart; Admin cannot execute arbitrary shell/Kubernetes commands.

Before deciding a hot transport change, probe the destination cluster and every
local project topic with finite deadlines; validate partition0-only topology and
delete-only cleanup, create missing topics, and apply the requested retention.
Failed preflight leaves the authoritative hub configuration/checkpoints unchanged;
created destination topics may remain as unused infrastructure. Retention changes
on an existing destination are external side effects and must be reported as such.
Record a unique transport-transition ID in the same durable configuration decision
as the new settings. Retain that decision until every project's state has applied
the transition; startup completes it before workers start. Per-project application
is idempotent by transition ID. On a different endpoint/topic binding, retain all
originals, deliveries and acknowledgements, requeue only events not materialized,
clear their obsolete physical offsets/observations, and start destination scanning
at offset0. Record the old checkpoint and a TRANSPORT_CUTOVER recovery gap with
the exact pending event IDs. Logical deduplication tolerates destination duplicates.
This is an explicit reviewed cutover, never an implicit consumer reset. A credential
change on the same binding retains the checkpoint. Quarantine evidence from the
old binding remains in transition history rather than being silently discarded.
Fence in-flight work by the full configuration revision, but retain consumer
instances across unrelated revisions; replace instances when transport settings
change and close the old instance at its original authorized endpoint.

Migration with multi/spec.md snapshots the legacy ingestion highwater, preserves
originals, subscription descriptions, pending jobs, delivery IDs/matches/acks and
retry identities. Initialize outbox only for events needing transport after the
recorded cutover; old pending model work remains frozen legacy work, not a full
history replay. Crash-safe migration markers prevent double enqueue. Paired
config/store/broker backup instructions and downgrade rejection are mandatory.

## Qualification gates

Use real pinned Kafka+Proxy with raw independent subscribers, overlapping reasons,
self-publication, model-free literal search and zero inference accounting. Exercise
publication/source retries, lost produce replies, crash before/after backend sync,
producer ack, fanout sync and offset commit; consumer replacement/rebalance;
retention gap/quarantine recovery; offline agent and filter outage; backlog refusal
and fair progress in another project. Test legacy semantic migration and partial
cutover restart, unchanged A2A SDK interoperability, v2 federation using separate
per-server brokers, real-model optional filters/search, Compose and Kubernetes
model-free profiles. Bind evidence to artifact/image/broker/proxy/deployment IDs.
