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
bearer_token,tls_ca_pem,retention_ms,max_pending_events,max_pending_bytes}` with optional
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

project-recovery/spec.md extends only restored/explicitly initialized routes with
a fresh durable per-project topic epoch. Existing projects keep this exact legacy
topic spelling until such a transition. Recovery uses the current effective
service/security/policy, never restores shared Kafka storage or consumes an old
topic tail, and fences every late producer/consumer callback by target epoch.

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
Recovery forms expose confirmed retry/reconcile with a reason, explicit inclusive
replay ranges and exact subscription revisions, replay status and paged audit.
Bounded subscription lists must state truncation and offer explicit ID/revision
target entry so all valid targets remain selectable; reject duplicates and more
than 64 targets before submission.

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

## Audited Admin recovery and bounded replay

The project-scoped Admin commands below require Admin authority, explicit
`project_id` under the ordinary operation-scope rules, and closed request/result
schemas. Recovery never accepts broker content as an original. `eventing_status`
adds `replay_watermark`, the maximum retained publication ingestion sequence (0
when empty), and `control_revision`, initially 0. The revision fences consumer
instances and in-flight fetch/produce results independently of hot configuration.

`eventing_audit` takes optional `offset` (default 0) and `limit` (1..100, default
50), returning `{items,truncated}`. Items are durable ordered control records:
`{id,kind,actor_id,project_id,message_id,reason,at,details}`. `kind` is `repair` or
`replay`. Details are the exact accepted control arguments excluding op, project,
confirm, message_id and reason. `eventing_replay` requires `replay_id` and returns
`{replay:{id,status,event_ids,subscriptions,created_at}}`; status is `pending` until
all selected events have durably materialized their frozen replay targets, then
`materialized`. This means downstream work is durable; filtered decisions and
agent acknowledgements may remain pending. Neither endpoint exports payloads or
transport credentials. Audit records and replay plans survive restart.

`repair_eventing` requires `message_id`, `confirm:true`, nonempty `reason` up to
1024 UTF-8 bytes, `offset` (nonnegative integer), `expected_checkpoint` (nonnegative
integer), `expected_digest` (64 lowercase hexadecimal SHA-256 characters), and
`action` equal to `retry` or `reconcile`. The digest identifies the quarantined
physical record, not a publication. The exact quarantine key, current durable
checkpoint and digest must match or fail `EVENTING_CONFLICT` without mutation.
An invalid-offset quarantine cannot be reconciled by guessing an offset. `retry`
clears that quarantine and recreates the consumer at its unchanged durable
checkpoint. `reconcile` is allowed only for the quarantined checkpoint itself:
audit the physical skip, requeue every accepted unmaterialized logical event whose
producer acknowledgement names that physical offset, then advance to offset+1.
Unrecognized foreign content is only skipped physical evidence, never model input
or a logical event. The audit retains `missing_logical_proof` when no accepted
original is linked. Requeued originals retain their stable envelope, subscriptions,
policy and identifiers. Delivery completion is never inferred from the skip.
Repair is allowed while archived so accepted work can drain. It increments the
control revision, invalidates old responses and recreates the consumer with
explicit positions. The result is `{audit_id,control_revision,next_offset}`.

`replay_events` requires `message_id`, `confirm:true`, reason as above,
`from_sequence`, `to_sequence` (positive inclusive ingestion sequences),
`expected_watermark`, and `subscriptions:[{id,revision}]` (1..64 distinct IDs).
Validate the entire request before changing durable state. Require from<=to<=
replay_watermark, exact expected watermark, currently existing active subscriptions
at exactly those revisions, current recipient membership, and configured matcher
for filtered targets. An empty retained-publication range fails `NOT_FOUND`.
At most 1000 originals and 16 MiB of prospective additional durable event/target
work may be selected; enforce the configured outstanding event/byte bounds as
well. Exceeding selection bounds fails `RANGE_TOO_LARGE`; outstanding-capacity
failure is `BACKPRESSURE`. No partial replay may be accepted. Archived projects
reject replay. Ordinary activation sequences are never changed: historical fanout
occurs only for explicitly selected replay targets. Preserve all existing immutable
event envelopes; retained pre-cutover originals may obtain a first envelope using
their original publication ID and original ingestion sequence, never a newly
allocated publication. Republish through Kafka rather than bypassing transport.
The result is `{replay:{id,status,event_ids,subscriptions,created_at}}`.

Freeze replay target snapshots and provenance separately from the immutable event
and original subscription snapshot. Raw and filtered match reasons may carry an
optional `replay_id`. Recipient/publication delivery identity remains unique;
append a distinct reason without changing its acknowledgement. Filter jobs dedupe
by publication, subscription ID and subscription revision. Replaying an already
evaluated identical target reuses that result rather than re-running inference.
Replay does not silently replay other history, add current subscriptions to
ordinary accepted events, or resurrect acknowledged deliveries.

Both mutating controls use durable actor/project/message ID idempotency: return an
identical accepted result before rechecking now-stale checkpoint/range/revision
preconditions; conflicting reuse fails `IDEMPOTENCY_CONFLICT`. Audit and plan
creation, outbox changes, control revision and idempotent result commit atomically.
Neither control cancels or rewrites a pending configuration transport decision.

Filtered subscription work freezes criterion, subscription revision, threshold and
matcher adapter (model identifier, URL, timeout and retry policy) at acceptance,
including while the Kafka broker is unavailable. Later hot configuration changes
must not reinterpret those accepted decisions. Frozen adapters contain no
transport tokens. The current matcher disabled state, archive status, recipient
admission and configuration generation still fence attempts and commit; accepted
work waits while disabled/archived. Legacy pending jobs without an authored frozen
adapter retain their historical compatibility behavior. Match evidence reports
the adapter and threshold that actually evaluated the job.

An optional hot `eventing.tls_ca_pem` string contains 1..16 PEM X.509 CA
certificates, at most 65536 UTF-8 bytes total. Parse each certificate and require
its basicConstraints CA flag. Reject private keys, encrypted entries, malformed
certificates, unknown PEM entries and non-whitespace text outside certificates.
Configured roots replace the operating-system roots; omission restores system
roots. Always require peer verification and HTTPS hostname verification. Trust
changes participate in transport preflight using the candidate trust, revision
fences and consumer replacement, while retaining checkpoints on the same binding.
Status includes `quarantines:[{offset,reason,digest,at}]`, at most the one blocking
record; an unparseable offset is null. Retry for such a record uses the current
checkpoint as the requested offset and its exact digest; reconcile is forbidden.
Repair audit details additionally contain `missing_logical_proof` boolean.
Pending byte admission accounts for immutable event plus frozen target snapshots.

A hot trust change must perform a new TLS handshake with the candidate roots.
Do not reuse a socket or resumed TLS session authenticated under previous trust.
The HTTP client must isolate connection reuse by trust configuration or disable
HTTPS connection/session reuse; merely supplying new per-request CA options is
insufficient. In Erlang httpc the request-level `socket_opts` option disables
persistent connection reuse (see the [official httpc documentation](https://www.erlang.org/doc/apps/inets/httpc.html)); also disable TLS session reuse for this profile.
For the retained OTP27 client, the request-level socket options must be nonempty:
its httpc_manager implementation only forces a fresh connection when that list
has at least one element. A harmless `keepalive:false` option satisfies this
condition; an empty list does not. Qualify removal/rotation after a successful
connection to the same origin, rather than testing only a fresh process.

The published application schema's critical `x-uniqueBy` annotation takes a
property name and requires distinct values of that property across object-array
items. Schema-profile consumers must implement it or reject the profile, as for
existing critical annotations. Apply `x-uniqueBy:"id"` to replay target arrays:
JSON Schema uniqueItems alone cannot reject an ID repeated at a different revision.
Audit schemas also bind `kind` to its matching repair/replay details shape.

## Revisioned Admin subscription editing

The project-scoped Admin command `update_subscription` requires subscription_id,
expected_revision (the subscription revision, not global configuration revision),
mode, selectors, confirm:true and message_id. Filtered mode additionally requires
filter or the legacy description alias, never both; raw mode forbids both.
Optional paused defaults false. Mode/selectors/criterion replace the complete
future subscription policy; this is not a partial patch. The response is exactly
`{subscription:Subscription}`. Reject unknown fields, including agent_id: resolve
the existing owner server-side, require that agent's current selected-project
admission, then apply ordinary subscription validation and revision semantics.
Only Admin can edit another agent's subscription. A stale subscription revision
returns HTTP409 CONFIG_CONFLICT; actor/project/message-ID idempotency returns an
identical accepted result before rechecking that revision. Editing, pausing or
resuming affects future acceptance snapshots only: preserve accepted frozen
filter jobs, raw deliveries and acknowledgements. New edits on archived projects
fail PROJECT_ARCHIVED. Forms must expose raw/filtered mode, selectors, criterion,
pause/resume and current subscription revision without requiring JSON editing.
Admin `subscriptions` additionally accepts optional offset (integer JSON token,
0..9007199254740991, default0). Apply the optional agent filter first, then the
stable newest-first subscription ordering, then offset and limit. Preserve exact
`{items,truncated}` response and existing default limit50/max100. An out-of-range
offset returns empty items/truncated:false. Browser Previous/Next controls must
permit inspection and editing beyond the first100 subscriptions, resetting the
page on project switch/navigation/create. Paging is a live view: concurrent
mutations may change page boundaries; callers needing stable targets use IDs and
subscription revision checks, never page position as mutation authority.

## Project event policy overrides

One server still owns one Kafka service. Root eventing defines service enabled,
rest_url, timeout_ms, retry_ms, bearer_token and tls_ca_pem; these transport and
security settings cannot be overridden by a project. Root topic/retention/backlog
values provide defaults. Project settings.eventing permits exactly topic_prefix,
retention_ms, max_pending_events and max_pending_bytes, with the same types/bounds
as root policy. Each key is independently optional. Omission or null removes that
project override and inherits the effective root value; an absent/null/empty
policy block inherits all four. Reject unknown/transport keys even if null.

Hot candidate validation must resolve every project's effective policy. Before a
change to enabled/binding/security/topic/retention is durably decided, preflight
each affected project's destination using its candidate effective policy. A new
project may use provisional immutable identity metadata to provision its topic;
preflight must not open a new empty store or admit its project before commit.
Record one durable transition decision for all affected stores, recover it before
workers start, and retain the existing failure/cutover invariants. A project-only
topic change requeues only that project's unmaterialized events with stable
identities; another project's topic/checkpoint cannot reset. Retention changes on
the same binding preserve offsets. Budget changes apply prospectively to new
acceptance and replay; lowering a limit never discards accepted pending work.
Admin project forms expose independent inheritance controls for the four keys;
service credentials/enablement remain in server settings. Raw progress and queue
accounting use the selected project's effective limits and policy.

Existing-topic retention must not mutate during predecision validation: a later
project or listener preflight failure cannot safely roll back records deleted by
an early shrink. Preflight may create an unused destination topic with candidate
policy but only reads/validates existing topic configuration. The durable config
transaction records desired policy before any existing retention alter. Apply
and verify that policy during recoverable per-project transition completion,
before recording that store's transition ID complete. A postdecision failure is
an incomplete committed transition: fail closed and replay the desired policy at
startup, never report that the old live configuration was restored. Preflight
connectivity checks cannot guarantee a later infrastructure write succeeds.

If a fetched broker batch fails its configuration/control revision fence, close
that consumer instance and recreate it at the durable next offset. Retaining an
instance whose network fetch advanced while materialization was rejected would
skip accepted work; an unchanged topic binding does not make that safe.

## Bounded filter-ready queues and durable deferred intents

Root eventing additionally permits max_pending_filter_jobs (default256) and
max_pending_filter_jobs_per_subscription (default64), integer JSON tokens1..100000.
Both are safe independently inherited project policy overrides. Both limits apply
when admitting a new pending subscription decision job; a larger per-subscription
limit never bypasses the project limit. Reductions retain accepted jobs above the
new cap and prevent new slots until enough jobs finish/cancel. Models, archive and
current recipient admission still fence attempts; capacity never grants authority.

An unavailable model must not turn a publication into a nonmatch, refuse its raw
stream because a filter-ready queue is full, or allocate unbounded ready jobs.
Overflow remains a durable deferred intent in the accepted event's existing frozen
target snapshot. Retain a compact staged/cancelled bitmask and cursor alongside that
row, and an ordered sequence index referring to those original rows; do not copy
originals, criteria or adapter policy into another unbounded queue. Retained facts
and unresolved intents still consume backend storage; this is not an unlimited disk
guarantee. Existing transport/disk acceptance bounds remain independent. Limit a
staging turn to128 target positions and64 event rows, using indexed continuation
rather than repeatedly scanning all retained originals. Ready jobs deduplicate by
publication/subscription/revision and preserve accepted criterion/model/threshold.
A bounded ready-job identity index enables slot accounting without rescanning all
completed decisions. Reconstruct indexes/counters from authoritative state once
when upgrading older state; preserve accepted work and identifiers.

Once broker observation is durable, raw fanout and registration of its frozen filter
intents count as materialized transport. Deferred registration is not a completed
match and does not fabricate a score. Stage eligible intents incrementally as slots
free; preserve pending work while the model is disabled, project archived or owner
admission revoked. Unsubscribe cancels its unresolved intents through bounded cleanup;
never evaluate them after removal. Replay targets follow the same bounds and retain
replay provenance. Replay status adds deferred when transport is materialized but
some selected filter intents are not yet ready jobs; materialized means its intents
have been staged/cancelled, not that pending model decisions or agent handling finished.

Eventing status adds pending_filter_jobs, deferred_filter_targets (nonnegative
integer counts), filtering_paused (model absent or project archived), and
filter_queue_limits containing exactly the two effective limits. The existing
pending_events count remains transport backlog, not model backlog. A replay record
adds deferred_filter_targets; root Admin exposes both pending and deferred costs.
The backend transaction synchronizes intent masks, indexes/counters, ready job and
its duplicate guard together. Killing/restarting cannot lose or stage an intent twice.
Qualification must fill both caps under actual model failure while actual Kafka raw
streams continue, reduce limits hot, restart, resume the model and prove every retained
target is resolved with its original criterion/revision/policy and no duplicate delivery.
This extends the four-key project policy subset to six keys. Persist the last
configured effective model adapter per project, including when a filtered
subscription is created/edited, before it may be disabled. A publication arriving
while models are disabled freezes that dormant adapter with its current criterion,
revision and threshold. It remains deferred/paused until models are re-enabled;
never freeze an empty adapter or silently reinterpret it with a replacement model.
The disabled state still prohibits outbound inference. Older state initializes this
metadata only from its effective configured adapter (the required adapter in an
accepted legacy profile) or an already durable last-effective snapshot. Never guess
a binding from unrelated old decision jobs. Each successful durable configuration
decision synchronously persists the effective project adapter before acknowledging
the change; startup recovery repeats that binding before workers start. Thus rapid
A-to-B-to-disabled changes retain B without relying on a worker tick. If an older or
incomplete state has neither proof, its affected targets remain deferred and report
FILTER_POLICY_UNAVAILABLE through eventing last_error; never infer with a replacement
model. Their raw recipients still progress and unsubscribe can cancel the intents.
