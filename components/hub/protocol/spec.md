---
name: Hub commands
summary: A2A command validation and public envelopes
kind: component
---
# Hub commands

## Hub command schema

Every command is an object with `op` plus the fields listed for that operation.
An optional `project_id` must equal configured project_id. Reject any other field,
including actor_id/agent_id overrides. Strings must be valid UTF-8. Limits below
are bytes unless stated otherwise. All ids are nonempty strings up to 128 bytes.

- `whoami`: no extra fields. Result `{agent_id,project_id}`.
- `subscribe`: required `description`, nonblank 1..4096 bytes. Result
  `{subscription:{id,agent_id,project_id,description,created_at}}`.
- `list_subscriptions`: no extra fields. Result `{subscriptions:[...]}` for caller
  only, ordered by creation sequence.
- `unsubscribe`: required `subscription_id`. Result `{unsubscribed:ID}`. Unknown
  or already-removed id is NOT_FOUND; another owner's id is FORBIDDEN.
- `publish`: at least one of `text` (nonblank string) and a present `data` field
  (any JSON value, including arrays, scalars, or null). Combined encoded text/data
  must be at most 65536 bytes. Optional text may be absent when data exists.
  Optional metadata: `information_type`, `source`, and `occurred_at`, defined in information/spec.md; optional context is defined in information/context.md.
  Result `{publication:PUBLICATION,matching:"pending"}`;
  absent text/data normalize to empty string/empty object. Record the publication
  and snapshot the currently existing subscriptions as durable pending matching
  work before returning success. No subscription history replay.
- `send`: required `recipient_id` referring to a configured agent, and text and/or
  JSON-object data (its existing content contract, up to 65536 bytes). Publication
  metadata is not accepted here. Unknown recipient is NOT_FOUND. Result
  `{delivery:DELIVERY}`. Queue an addressed delivery without inference and without
  creating a searchable publication.
- `poll`: optional integer `limit` (1..100, default 50). Result `{deliveries:[...]}`
  containing the caller's oldest unacknowledged deliveries by creation sequence.
  Polling does not remove or acknowledge them.
- `ack`: required `delivery_ids`, array of 1..100 distinct nonempty ids. Validate
  ownership/existence of every id before any change. Result `{acknowledged:[IDS]}`
  in the requested order. Reacknowledging an owned delivery succeeds. Never partly
  acknowledge a batch with an unknown or foreign id.
- `get`: required `publication_id`. Result `{publication:PUBLICATION}`. Return
  the stored project publication, independent of delivery/acknowledgement state.
  Unknown IDs and IDs belonging only to private deliveries return NOT_FOUND.
- `search`: optional nonblank `query` (1..256 bytes), optional exact-match filters
  `information_type`, `source_kind`, `source_id`, and integer `limit` (1..100,
  default 50). Require a query or at least one filter; a supplied blank query is
  invalid. Filters use the same bounds as the corresponding metadata fields.
  Combine all filters and the query with AND. Result `{publications:[...]}`.
  Return newest publications first by ingestion sequence, not occurred_at.
  A query is a case-insensitive literal substring of text, JSON-encoded data,
  information_type, or JSON-encoded source. Omitted query applies filters alone.
  Search is project-wide; direct messages are excluded. Existing query-only
  clients retain their response shape and behavior.

The named information specifications extend this schema with contextual evidence,
durable query jobs, retrieval/fallback, feedback and adaptive indexes. The named
management/oidc.md adds optional OIDC while preserving key-mode defaults.

A DELIVERY has id, project_id, recipient_id, sender_id, kind (`publication` or
`message`), text, data, created_at, and (for publication kind) publication_id and
matches (array of `{subscription_id,probability_ppm,threshold_ppm,model}`). Model
probability is explicitly rounded to the nearest integer part per million before
threshold comparison. No other numeric rounding is implied. Delivered record ids
and content remain stable between polls and across restarts.
