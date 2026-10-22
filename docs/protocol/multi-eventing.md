# Multi-project and Kafka protocol profile

This is the target contract for MULTI-001/KAFKA-001, not a claim that an older
accepted artifact implements it. Normative authority is
`components/hub/multi/spec.md` and
`components/hub/eventing/spec.md`. Existing
[profile-1 foundation](foundation-v1.md) remains applicable except for their explicit
replacements. Qualification must export schema/OpenAPI from the new accepted
artifact and independently validate actual traffic; these examples are authored
inputs, not generated evidence.

## Compatibility and negotiation

| Surface | Existing profile | Target behavior |
| --- | --- | --- |
| Agent transport | A2A1.0 JSON-RPC SendMessage | Unchanged; command in the one data/text part. |
| Project selection | Configured single project, optional equal project_id | Explicit admitted project_id; omission only singleton admission or persisted legacy binding. |
| Subscribe description | Required semantic criterion | Legacy alias for filtered mode; no criterion defaults to model-free raw mode. |
| Delivery reasons | Model score for every match | Raw reason contains mode/revision with no fabricated score; filtered reason preserves real model evidence. |
| Local mutation retries | Agent + messageId | Project + agent + messageId; legacy accepted receipts replay verbatim. |
| Server federation | v1 project-bound peer | v2 server credential plus explicit authorized origin/destination project pairs. v1 remains only for an explicit legacy pair. |
| Storage | One DETS store/project alias renames | Stable registry + one writer per project store; backup/marker-based migration, no silent identity rename. |
| Model availability | Matcher required | matcher:null is valid; raw/metadata selection/literal fact search do not infer. |
| Kafka | None | Per-server service, project topics and explicit durable handoffs; A2A agent ack stays separate. |

Public protocol discovery must advertise supported peer versions [1,2], v2 path
/federation/v2 and project-scoped/raw-filtered capabilities, with no private
project list. The base schema profile is 2.0.0 because required multi-project
selection and raw reason shapes change existing validation assumptions; peer
wiremajor2 is separately explicit. The additive selective-recovery profile2.1
publishes the current [schema/OpenAPI snapshots](README.md); its descriptor
major and peer versions stay unchanged. A2A-Version remains1.0. Old-to-new federation
works only through the configured legacy pair. New-to-old selects v1 only from
explicit configured compatibility, never after a v2 auth/error failure.

## Agent operations and errors

All existing project-owned operations accept project_id and keep their old
operation-specific fields. list_projects is a new authenticated read. whoami
adds current effective project_ids; a selected legacy project_id may remain for
compatible clients. list_projects result is `{projects:[{id,name,status,
description}]}` with no hidden projects. Unknown and inaccessible project use the
same PROJECT_NOT_FOUND domain error; ambiguous omission is PROJECT_REQUIRED;
archived mutations use PROJECT_ARCHIVED; disabled semantic capabilities use
MODEL_UNAVAILABLE; pre-acceptance queue exhaustion is BACKPRESSURE. These use the
existing JSON-RPC -32000/google.rpc.ErrorInfo representation. CLI validate checks
shape, not membership/model/broker availability.

During a hot all-project backend move, frozen writers reject new transactions
with retryable CONFIG_APPLY_IN_PROGRESS. Admin HTTP returns503 and Retry-After:1;
valid A2A requests retain HTTP200 with JSON-RPC -32000 and the same domain code in
google.rpc.ErrorInfo. Retry the unchanged command and message ID after bounded
backoff. Rejection creates no mutation receipt. A connection lost after the
durable move decision has an uncertain outcome and must use the same retry key.
See `components/hub/storage-relocation/spec.md` for recovery boundaries.

| Command | New fields/rules |
| --- | --- |
| subscribe | mode raw/filtered; filter or description alias, never both; selectors exact arrays information_type/source_kind/source_id/author_id. Raw forbids criterion, filtered requires nonblank criterion. |
| update_subscription | subscription_id, expected_revision, replacement mode/criterion/selectors; optional paused. Owner/project checked before revision. |
| publish | Existing text/data/metadata; acceptance adds durable event identity/sequence/state. |
| poll / ack | Existing limit/delivery_ids; selected project + owner; poll never commits/acks. |
| query fanout | Explicit project_ids freezes admitted scope; separate project evidence/coverage; never automatic cross-project publication. |

Raw reason shape is `{subscription_id,subscription_revision,mode:"raw"}`.
Filtered reason is `{subscription_id,subscription_revision,mode:"filtered",
probability_ppm,threshold_ppm,model}`. Subscription revision is a positive integer
JSON token. Every new object rejects unknown fields; IDs/UTF8 limits, duplicate
JSON-key rejection, integer-token constraints and HTTP framing remain normative.

## Peer v2 messages

Every ordinary request has protocol_version:2, op, origin_server_id,
origin_project_id and destination_project_id. Operation-specific fields are the
existing v1 fields excluding the old protocol_version/origin_project_id wrapper:
submit adds query_id/question/deadline_at; status adds query_id; catalog and
identities add optional cursor; source operations retain their exact existing
source/job/question/evidence fields. No body chooses its transport principal.
The server-wide catalog request alone may omit destination_project_id and returns
only pair-authorized project catalogs. It cannot expose the full registry.

Every result identifies protocol_version:2,server_id,project_id plus the
operation's existing fields. Project catalog pages retain revision,generated_at,
max_age_ms,visible,items,next_cursor and the prior snapshot/freshness rules. The
aggregate catalog represents each project separately; no shared cache revision
can erase a project's stale/unavailable coverage. Request/status ownership binds
origin server/project + destination server/project + query ID. A remote project
cannot poll another project's request even if both share a credential/server.

The server-wide catalog response is `{protocol_version:2,server_id,revision,
generated_at,max_age_ms:10000,projects,next_cursor}` and deliberately has no
singleton project_id. Each page contains at most one complete bounded project
catalog `{project_id,revision,generated_at,expires_at,visible,entries}`. Its top
revision covers all pair-authorized project revisions in configured order; its
cursor binds requester server/origin project and that full snapshot. A grant,
project or catalog change between pages rejects with SNAPSHOT_CHANGED rather
than stitching together incompatible ownership snapshots.

Canonical source owner is server/project, including same-server projects. Equal
scope claims conflict; copies and stale caches cannot become canonical. Email
correlation confers no role or admission. Federation brokers stay private and are
not mirrored; queries remain asynchronous authenticated HTTP jobs.

## Kafka adapter and handoff

The selected maintained adapter is Confluent REST Proxy v2, accessed using the
standard runtime HTTP client. Producer JSON media type is
application/vnd.kafka.json.v2+json. Consumer commits are explicit and follow a
synchronized backend materialization/checkpoint. Broker offset means transport
progress, not delivery acknowledgement. The initial project topic has one
partition; no project ordering claim is derived from a multi-partition broker.

Topic name: PREFIX.server_sha16.project_sha16.events.v1, hashes are lowercase
SHA256 of UTF8 IDs truncated to16 hexadecimal digits. Persist full identities and
reject a collision. Consumer group is that topic + .fanout. Fanout group load
sharing never divides independent agents' subscriptions. Physical broker
retries may duplicate records; stable event IDs deduplicate logical delivery.

| Durable point | Meaning |
| --- | --- |
| Accepted | Original + source retry + mutation receipt + sequence + subscription snapshot + outbox synchronized together. |
| Published | Kafka acks=all response validated and offset synchronized. |
| Materialized | Raw deliveries/filter work/dedup/checkpoint synchronized before broker commit. |
| Searchable | Backend original committed; derived indexes separately report catch-up. |
| Acknowledged | Agent's atomic owned A2A ack mutation synchronized; independent of consumer offsets. |

Retention does not delete facts/unacked deliveries. Lost offsets/gaps/quarantined
records require visible reconciliation from originals and explicit Admin repair;
never reset-to-latest and claim completeness. Server/proxy restarts, response loss
and outbox retries preserve logical event/delivery identity. Project topics and
broker credentials remain inaccessible to agents/peers.

## Dependency references

[Confluent REST Proxy API](https://docs.confluent.io/platform/current/kafka-rest/api.html)
defines the supported v2 production/consumer interfaces. The
[official image reference](https://docs.confluent.io/platform/current/installation/docker/image-reference.html)
identifies Kafka as Apache2 and REST Proxy as Confluent Community License.
The deployment pins8.3.2 image content identities; source and deployment license
notices must distinguish ADHD from that external service. Kafka transactions do
not atomically cover backend writes or agent receipts; see the
[Apache Kafka delivery design](https://kafka.apache.org/41/design/design/).

The REST v2 offsets commit body uses the last consumed offset: a durable next
position N commits offset N-1, and GET offsets must report N. Consumer positions
uses N directly. These two API meanings must not be conflated.

### Audited recovery and explicit replay

Project-scoped Admin `eventing_status` exposes the blocking quarantine digest and
physical offset, durable checkpoint, `control_revision`, and `replay_watermark`.
A `repair_eventing` request supplies `offset`, `expected_checkpoint`,
`expected_digest`, `action` (`retry` or `reconcile`), a nonempty `reason`, fresh
`message_id` and `confirm:true`. Retry rereads the physical record; reconcile
records an audited skip and republishes any linked accepted original. Foreign
broker data never becomes an original or model input. Exact stale preconditions
return HTTP409 `EVENTING_CONFLICT`.

Admin `replay_events` takes inclusive `from_sequence`/`to_sequence`, exact
`expected_watermark` from status, and explicit `subscriptions:[{id,revision}]`,
plus reason/message ID/confirmation. Admission is atomic and bounded to 1000
retained originals, 64 target subscriptions and 16 MiB additional durable work,
within current outbox limits. Old originals enter the real Kafka transport with
their original publication identity. Ordinary activation sequences and existing
acknowledgements remain intact. `eventing_replay` takes `replay_id` to observe
pending/materialized state; materialized means downstream work is durable,
including pending filtered jobs. `eventing_audit` pages durable control records
using optional offset and limit. All four commands require Admin authority.

Accepted controls are idempotent by actor, project and message ID. Repeating the
same command returns its original accepted result before stale precondition
checks; changing a command under the same ID conflicts. Raw/filtered match reasons
may include `replay_id`. No extra field is added to immutable Kafka envelopes.
Filtered jobs retain their accepted criterion, revision, threshold and model
adapter across hot configuration changes; disabling models pauses inference.

Optional hot `eventing.tls_ca_pem` configures 1..16 certificate-only X.509 CA roots
(up to 64 KiB), replacing system trust. Admin merge-patch null removes this setting
or a bearer token. TLS peer/hostname verification remains mandatory, and trust
changes require a new handshake, preventing previously authorized connections
from bypassing candidate trust preflight. See the normative eventing contract, `components/hub/eventing/spec.md`,
for exact bounds, recovery semantics and closed request/result schemas.

### Complete scope inventory

The authored [operation/configuration inventory](scopes.json) enumerates every
published agent/Admin operation and root configuration field, including project
settings inheritance. Run tests/protocol_scope.py against the exported accepted
schema; an added/removed operation or configuration field fails coverage until
its scope is reviewed. Server identity/listing operations disclose current
admission only; project-owner includes project admission and the owning actor,
not a global search of an actor's other memberships. Admin project operations
retain each operation's role/privacy rules; project scope does not grant a Viewer
write authority. Root federation transport/credentials/pairs are server-wide;
project descriptions/catalogs/export policy inherit defaults and may override.
The configuration-file CLI location is the sole restart setting. Immutable
server/project IDs and read-only config_revision are classified server-wide but
cannot be reassigned through a configuration patch.

Filter-ready admission has independent project and subscription budgets:
`max_pending_filter_jobs` (default256) and
`max_pending_filter_jobs_per_subscription` (default64), each an integer1..100000.
Set defaults in root `eventing`, or override either through a project's
`settings.eventing`. Transport/security remains server-wide. Reducing a cap keeps
already accepted jobs and prevents new ready slots until usage falls below it.

A full filter-ready queue leaves the accepted event's frozen targets deferred in
its original backend record. Kafka raw fanout continues independently. Admin
`eventing_status` distinguishes `pending_events` (transport),
`pending_filter_jobs` (ready decisions), and `deferred_filter_targets` (not yet
staged decisions); `filter_queue_limits` gives both effective caps, and
`filtering_paused` reports model-disabled or archived projects. These bounds limit
ready work, not total backend disk use.

`eventing_replay` can now report `deferred`, with its own
`deferred_filter_targets`. `materialized` means every target was staged or cancelled;
it does not promise all model decisions or agent processing finished. Disabling
models pauses inference while new publications retain the last durably configured
adapter and their acceptance-time threshold/criterion/revision. Enabling a different
model later cannot reinterpret those retained decisions. A historical state without
provable adapter provenance reports `FILTER_POLICY_UNAVAILABLE` and remains deferred.
