---
name: A2A hub core
summary: Compatible command protocol, durable operations and base runtime
kind: component
---
# A2A coordination core

## Command-line interface

The artifact accepts one JSON array argument with these positional forms:

- `["describe"]` returns exactly `{"name":"ADHD","version":"0.1.0","protocol":"1.0","operations":["ack","cancel_federated_query","federated_query","get","get_federated_query","list_subscriptions","poll","publish","search","send","subscribe","unsubscribe","whoami"]}`.
- `["validate", COMMAND]` validates a hub command using the same domain validator
  as HTTP processing, without accessing storage, authentication, or the network.
  Success returns exactly `{"valid":true,"op":OP}`. Invalid commands exit nonzero
  with a concise diagnostic on stderr. All operation-specific shape, length,
  number, required-field, and unknown-field checks below apply here as well.
- `["serve", CONFIG_FILE]` reads a UTF-8 JSON configuration file, starts the store,
  matcher worker, and HTTP listener, emits one JSON readiness line
  `{"status":"ready","url":BASE_URL}`, and remains running until terminated.
  Operational logs go to stderr, never alongside JSON responses on stdout.

Reject other forms. Implement the framework test and smoke dispatch before product
argument parsing as required by the selected skill. Generate native tests of domain
state transitions, durable reopening, authorization boundaries, and matcher failures,
not only CLI descriptions. The manifest cases must still have matching native
behavior cases and call the public CLI logic with their own argument values.

## Configuration and access

The exact configuration shape below is the legacy base. configuration/spec.md
and identity/spec.md explicitly add live settings, empty-agent first install,
config_revision, users, agent_owners and auth; they own those extensions and
transactional reconfiguration, including project identity and store-path changes.


CONFIG_FILE is an operator-owned JSON object with required fields `project_id`
(nonempty identifier), `store_path` (disk file path), and `agents` (object mapping
agent identifiers to distinct bearer-token strings of at least 24 characters).
Identifiers are 1..128 ASCII letters, digits, dot, underscore, or hyphen.
`host` defaults to `127.0.0.1` and accepts only that loopback address in this first
version. `port` defaults to 8766 and is an integer 1..65535. `public_url` defaults
to `http://127.0.0.1:PORT` and describes the externally reachable tunnel/proxy URL.

`matcher` is a required object with `url` (an absolute http/https SystemOne endpoint,
e.g. http://127.0.0.1:18770/v1/systemone), `model` (nonempty string), optional
`timeout_ms` (100..30000, default 3000), and `retry_ms` (100..30000, default 1000).
`threshold_ppm` is an integer 1..1000000, default 900000; it is an initial tunable
policy, not a calibration claim. Fail startup for invalid configuration or an
unreadable/corrupt existing store; never replace a corrupt store with an empty one.
Do not log bearer tokens or include them in persisted product state or responses.

Agent identity comes solely from `Authorization: Bearer TOKEN`; it cannot be
chosen by a message field. Unknown/missing tokens return HTTP 401 with a Bearer
challenge. Agents see published information only within the configured project;
unknown project_id values are rejected. A token cannot read, acknowledge, or remove
another agent's private deliveries or subscriptions. Direct messages are visible
only to their recipient through polling, never through publication search.

## HTTP and A2A 1.0 binding

GET `/health` returns HTTP 200 and `{"status":"ready"}` when the store and listener
are operational. It remains available if matching is temporarily unavailable.
GET `/.well-known/agent-card.json` returns a valid A2A 1.0 AgentCard with one
`supportedInterfaces` entry for BASE_URL + `/a2a`, protocolBinding `JSONRPC`, and
protocolVersion `1.0`; product version is `0.1.0`. Advertise no streaming, push,
or extended-card capabilities. Declare HTTP bearer authentication in the 1.0
securitySchemes/securityRequirements shape, JSON input/output modes, and one
project-coordination skill. These two GET routes are public and reveal no tokens,
agent roster, data, queue sizes, or matcher URL.

POST `/a2a` accepts JSON-RPC 2.0 `SendMessage`. Require a string/non-null integer
RPC id, params.message with a nonempty messageId, role `ROLE_USER`, and exactly
one part: either `{"data": COMMAND}` or `{"text": JSON_ENCODED_COMMAND}`. Part
`mediaType` may be supplied. Reject file parts, conflicting parts, unknown command
fields, and unsupported taskId-based continuations. contextId may be omitted or a
nonempty string; the response uses it when supplied, otherwise the project id.
SendMessage immediately returns `{"jsonrpc":"2.0","id":ID,"result":{"message":{
"messageId":SERVER_ID,"contextId":CONTEXT,"role":"ROLE_AGENT","parts":[{"data":RESULT}]
}}}`. No A2A Task is created; publication matching proceeds independently as a
hub job. Never conflate an A2A task subscription with a hub content subscription.

Accept A2A-Version `1.0`; if omitted use 1.0. Reject incompatible versions with a
structured JSON-RPC error. Unsupported methods return -32601; malformed JSON uses
-32700, invalid envelopes -32600, and invalid params/commands -32602. Domain errors
use -32000 and data `[{"@type":"type.googleapis.com/google.rpc.ErrorInfo",
"reason":CODE,"domain":"adhd.hub","metadata":{"code":CODE}}]` with stable codes
NOT_FOUND, FORBIDDEN, IDEMPOTENCY_CONFLICT, SOURCE_CONFLICT, or PROJECT_MISMATCH. Internal errors use -32603 without
sensitive detail. GET/POST routing, response Content-Type application/json, byte
Content-Length, and Connection: close must work with the official Python A2A SDK
1.1.0. Unsupported routes return 404; unsupported media types 415. Never crash the
listener on bad input. Reject Transfer-Encoding, duplicate/invalid Content-Length,
headers above 16 KiB, bodies above 1 MiB, and incomplete requests after 5 seconds.
Use a bounded receive loop, not an unbounded socket read. Accept normal HTTP/1.1
clients; closing each response is permitted. Keep concurrent reads responsive
while the worker performs network inference.
Header values must have optional ASCII space and horizontal-tab whitespace
removed from both ends before authentication or other interpretation. In
particular, `Authorization: Bearer TOKEN` is a valid header, including the single
space following the colon. Removing only an exact multi-character substring
containing both space and tab is incorrect.

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
  Optional metadata: `information_type`, `source`, and `occurred_at`, defined in information/spec.md.
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

A DELIVERY has id, project_id, recipient_id, sender_id, kind (`publication` or
`message`), text, data, created_at, and (for publication kind) publication_id and
matches (array of `{subscription_id,probability_ppm,threshold_ppm,model}`). Model
probability is explicitly rounded to the nearest integer part per million before
threshold comparison. No other numeric rounding is implied. Delivered record ids
and content remain stable between polls and across restarts.

## Idempotency and persistence

Use message.messageId scoped to authenticated agent as the idempotency key for
successful subscribe/unsubscribe/publish/send/ack mutations. Compare decoded
command maps independent of JSON object key order. Repeating the same command
returns the original domain result and causes no duplicate work/delivery.
Reusing that key for different command content returns IDEMPOTENCY_CONFLICT.
A retry may use a different JSON-RPC id. Read operations return current state.

Persist publications, subscriptions, matching jobs, completed delivery evidence,
acknowledgements, monotonic ordering sequence, and mutation idempotency records.
Use an OTP disk-backed store (DETS is acceptable) with one serialized writer.
Commit and synchronously flush each complete state transition before returning
success. Creating a publication and its matching jobs is one transition; completing
an evaluation and creating/updating its delivery is another. Do not acknowledge
success before sync. Keep credentials/configuration separate from persisted state.
A completed acknowledged publication delivery remains deduplicated even if another
matching subscription for that recipient finishes later.

After clean shutdown or abrupt process termination and restart with the same
configuration/store, accepted data and all unacknowledged deliveries remain and
pending matching resumes. Do not rely on memory-only queues or shutdown hooks
for durability. Document the first version's single-process/single-store limit.

## Background model worker and failures

The HTTP request path must not call inference. A background worker processes
persisted publication/subscription jobs. Supply `model` and publication context
(including text/data/author_id) as SystemOne state and a `noul` relevance question
whose instructions include the original plain-text subscription. Send JSON to
the configured matcher.url using the standard HTTP client; HTTPS must verify the
server certificate. Accept only a valid response for that question with a finite
numeric probability 0..1. HTTP failures, timeouts, incomplete/malformed answers,
booleans, or probabilities outside that range are failures, not nonmatches.

The exact SystemOne request shape is `{"model":MODEL,"state":{"publication":PUBLICATION},
"questions":{"relevance":{"type":"noul","instructions":QUESTION}}}` where QUESTION
asks whether the publication satisfies the subscription and contains its complete
plain-text description. The response shape is `{"model":MODEL,"answers":{
"relevance":{"type":"noul","noul":PROBABILITY}}}` with possible additional
usage/metrics/scoring fields. Read only `answers.relevance.noul` as the probability;
require its question and type to be present. A top-level `noul` request field,
an answers array, or a top-level `probability` field is not this protocol. These
schemas match the already-tested Nemotron SystemOne adapter.

On a valid match at/above threshold, queue a publication delivery. Deduplicate
per publication and recipient even when multiple subscriptions match; append
matching subscription evidence to that same delivery without resurrecting an
acknowledged delivery. A nonmatch completes its job with no delivery. If a
subscription has been removed before its result commits, cancel that job and do
not use the stale result. Removing a subscription does not withdraw older queued
information. If no subscriptions exist when publishing, complete with no jobs.

Keep failed jobs durable and retry in the background after retry_ms (backoff may
increase to at most 30 seconds). A retry cannot duplicate a completed delivery.
Poll/search/publish must remain usable when the matcher fails. Never silently
substitute keyword matching or a deterministic fixture in product mode. Network
work must happen outside the store writer so it cannot block unrelated requests.

## Required acceptance scenarios

Two separately authenticated SDK clients subscribe and publish project updates.
The live Nemotron model matches an API-change publication to the client agent,
which polls it, acknowledges it, publishes a response, and sends an addressed
message. Search finds publications but not the direct message. An irrelevant
publication does not create an undesired delivery under the configured policy.

Independent acceptance must also cover unauthorized/foreign access, malformed
requests that leave the listener alive, mutation retries/conflicts, duplicate
subscriptions producing only one delivery, nonretroactive subscription creation,
model failure and recovery, acknowledgement batch atomicity, and a hard kill
followed by restart without losing queued information or acknowledgements. Use
independent fixtures for deterministic failure cases and at least one actual
Nemotron-backed end-to-end path. No stub result qualifies as model integration.

Also independently verify arbitrary JSON publication values, agent message/status
history, source/type filtering, retrieval by stable ID without subscribing,
private-message isolation from get/search, source-item retries and conflicts,
metadata in matching context and deliveries, and retention after acknowledgement
and hard restart. Test a synthetic external-source event through the same path
without contacting an external connector. Open a real schema-1 fixture produced
by the previous prototype and preserve its accepted data and idempotent results.

## Web management

The named management/spec.md specification defines the administrator UI, API, and
optional admin_token configuration. configuration/spec.md and identity/spec.md
explicitly extend live configuration, human roles and Admin private-data access;
protocol/spec.md defines wire publication and version conformance. Agent-facing
bearer scopes and publication privacy remain governed here.
