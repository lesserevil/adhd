---
name: Stored information
summary: Publication envelopes, source identity, and prototype store compatibility
kind: component
---
# Stored information and prototype compatibility

## Stored information envelope

A PUBLICATION contains the existing `id`, `project_id`, `author_id`, `text`, `data`,
and server-generated `created_at`, plus:

- `information_type`: identifier using the existing 1..128 ASCII identifier
  rules, default `message`. Initial examples are `message` and `status`; accept
  other valid identifiers without code changes.
- `source`: object with required `kind` (identifier, 1..128) and `id` (nonblank
  UTF-8 string, up to 256 bytes); optional `item_id` (nonblank, up to 512 bytes)
  and `uri` (absolute http/https URL, up to 2048 bytes). Reject unknown keys.
  Default is `{kind:"agent",id:AUTHENTICATED_AGENT_ID}`. For explicit kind
  `agent`, require source.id to equal the authenticated caller, otherwise
  FORBIDDEN. Other kinds such as `email`, `slack`, or `teams` identify the origin
  reported by an authorized submitter. Provenance is a claim, not independent
  proof of access to that source; author_id always identifies the authenticated
  submitting agent and cannot be overridden.
- `occurred_at`: valid ISO-8601 datetime with explicit timezone, up to 64 bytes,
  normalized to UTC ISO-8601. Default equals created_at. Preserve the distinction
  between an event's reported time and the time the hub accepted it.

Metadata has the above independent bounds in addition to the content limit and
the existing HTTP body cap. Reject attempts to set `id`, `created_at`, `author_id`,
or other server-owned fields. A publication is immutable, retained regardless of
whether anyone subscribes or acknowledges it. It remains retrievable/searchable
until an explicitly designed future retention mechanism removes it. Status is
an append-only event history; a newer status does not overwrite an older one.
Binary attachments and live external connectors are outside this iteration;
structured JSON can carry descriptions and references to other content.

If source.item_id is present, additionally deduplicate ingestion by the tuple
(authenticated author_id, source.kind, source.id, source.item_id). Repeating the
same decoded publish command, ignoring only op and project_id, returns the exact
original publication with matching:"pending", even with a different A2A messageId.
Object key order is irrelevant. Reusing the source identity with any different
content, metadata, or supplied/default field presence returns SOURCE_CONFLICT.
Do not create another publication, matching job, or delivery for a source retry,
including after acknowledgement or restart. Source identities from different
authenticated submitters are separate. When item_id is absent, only normal
messageId idempotency applies. Persist source-dedup command/result bindings.

Pass the complete publication envelope, including type, source, timestamps, text,
and JSON data, into the existing semantic matching worker. Publication deliveries
must additionally include information_type, source, and occurred_at from the
publication, without changing their existing fields. Private message deliveries
keep their existing shape. Future connectors submit through the same authenticated
publish contract; they cannot make private source material project-wide without
an explicit upstream visibility decision.

### Existing prototype stores

Retain DETS for the MVP. Support opening the first prototype's schema-1 state
without losing publications, subscriptions, private messages, queued jobs,
acknowledgements, idempotency bindings, or monotonic sequence. That state is one
DETS set object `{:state, STATE}`. STATE is an atom-keyed map with keys `schema`
(integer 1), `project`, `seq`, `subscriptions`, `publications`, `deliveries`,
`jobs`, and `idempotency`. The last five are maps. Subscriptions/publications are
keyed by record ID and have atom keys `seq`, `value`, where value is the public
string-keyed record. Deliveries additionally have atom key `ack` (boolean).
Jobs are ID-keyed atom maps containing `id`, `seq`, `publication_id`,
`subscription_id`, `recipient_id`, `description`, `status` (:pending/:done/:cancelled),
and `retry_at` (system-time milliseconds). Idempotency is keyed by {actor, messageId}
tuples, with atom-map values `command` and `result` holding original public maps.

Validate an existing store before upgrading. Supply missing legacy publication
metadata as information_type `message`, source `{kind:"agent",id:author_id}`,
and occurred_at equal to created_at. Normalize legacy publication deliveries
similarly using the underlying publication. Preserve original stored idempotency
results verbatim on a retry, even when those historical results lack metadata.
Commit any schema upgrade synchronously before reporting readiness. Reject
corrupt or unsupported schemas and wrong-project stores without resetting them.
Use a new schema version for incompatible internal layouts; an old-runtime
rollback uses its pre-upgrade offline backup rather than the upgraded file.
Generate native coverage for both new-envelope persistence and schema-1 loading.

