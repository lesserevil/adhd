---
name: Project federation
summary: Durable asynchronous discovery across trusted single-project hubs
kind: component
---
# Asynchronous project federation

This contract extends component.md with opt-in project discovery across independent
single-project hubs. It takes precedence for new operations, persistence and routing.
Keep all existing A2A, information and administrator behavior compatible, except
the explicitly extended describe operations list. No broker or external dependencies.

## Configuration and visibility

An absent `federation` object disables federation. New query creation then returns
FEDERATION_DISABLED. Existing owned query status/cancellation remain accessible.
Optional `federation` has exactly these fields:

- `description`: required nonblank UTF-8 project description, at most 4096 bytes.
  This is operator-approved, exportable evidence about this project's work.
- `export_publication_ids`: array of at most 32 distinct publication IDs, default
  empty. Only these project-public records may be supplied as additional evidence.
  Missing IDs are omitted; private deliveries never qualify. No other publications,
  linked context, source credentials, agents or private messages may be exported.
- `peers`: required array, at most 16 entries. Each entry has exactly `project_id`,
  `url`, `token`, `inbound_token`. IDs follow normal identifier bounds, are unique,
  and differ from the local project ID. URL is an absolute HTTP(S) base URL with
  hostname and optional port, no userinfo/query/fragment, and no path except `/`.
  `token` authenticates outbound requests to that peer; `inbound_token` authenticates
  that peer here. Tokens are at least 24 bytes; all inbound tokens must be distinct
  and different from agent/admin tokens. Outbound peer tokens must also differ
  from this server's agent/admin tokens, so a peer credential cannot become a
  privileged local credential by reuse across those namespaces. Tokens never enter persisted state,
  responses, model context or logs. Outbound tokens may equal the matching inbound
  token on the remote server. Credentials remain in private configuration only.
- `timeout_ms`: integer 100..10000, default 1000, per HTTP or inference attempt.
- `retry_ms`: integer 100..30000, default 500.

Reject invalid fields/shapes at startup and live update. Use an explicit peer allowlist as discovery
bootstrap; no network-wide discovery or recursive forwarding. Peer removal revokes
inbound access immediately on live configuration commit and stops subsequent
outbound attempts. configuration/spec.md owns live updates, not restart-only
activation.
HTTP is for private networks/tunnels; HTTPS verifies certificates and hostname.
Never follow redirects or URLs from peer responses. Limit decoded peer/model response
bodies to 256 KiB, enforce finite timeouts, and treat malformed/oversized responses
as failures. Use standard HTTP clients and keep all networking outside the store writer.

## Agent commands

Normal agent authentication and optional local project_id apply. Unknown fields fail
validation. Extend both HTTP and CLI validate with these operations:

- `federated_query`: required nonblank `question` (1..4096 bytes); optional
  `deadline_ms` integer 1000..120000 (default 30000). Result `{query:QUERY}`.
  Before acknowledging, persist an owner-scoped query, absolute UTC deadline,
  question and snapshot of configured peer IDs (never tokens/URLs), each pending.
  No inference/networking occurs in this request. At most 64 nonterminal local
  queries; overflow returns RESOURCE_EXHAUSTED without a mutation receipt.
- `get_federated_query`: required `query_id`. Result `{query:QUERY}` using current
  state, never cached mutation results. Unknown ID is NOT_FOUND; foreign owner
  is FORBIDDEN. It remains readable after configuration disables federation.
- `cancel_federated_query`: required `query_id`. Same ownership, result `{query:QUERY}`.
  Persist cancellation before success. Stop local dispatch and discard late results.
  Terminal queries remain terminal. Remote accepted work may continue only until its
  original deadline; cancellation does not promise remote rollback.

QUERY has `id`, `project_id`, `owner_id`, `question`, `created_at`, `deadline_at`,
`status` (pending/completed/partial/cancelled), `peers` and `responses`.
`peers` is an array of `{project_id,status}` with status pending/responded/failed.
Responses have one entry per responding peer, in configured peer order:
`{project_id,matched,probability_ppm,description,publications,model}`. Publications
are exact exported publication envelopes, bounded as below. A false match has empty
description/publications so irrelevant evidence is not unnecessarily disclosed.
`completed` means every selected peer responded, including explicit nonmatches;
`partial` means the deadline passed or a selected peer was removed/failed with
missing answers. Empty peer sets complete immediately with zero responses, scoped
to that empty set. Do not claim network-wide completeness or convert missing peers
into nonmatches. Stop retrying terminal jobs. Check deadlines on reads and worker
transitions so stale pending jobs cannot live indefinitely, including after restart.

Creation and cancellation use normal agent-scoped A2A messageId idempotency, comparing
decoded commands. Duplicate creation returns its original result and creates one job;
get returns the progressive current result. Queries never enter ordinary publication
search, subscription matching, inboxes or administrator publication views.

## Peer wire protocol

POST `/federation` with application/json and Authorization: Bearer INBOUND_TOKEN.
This endpoint is separate from A2A and admin; other credentials never grant peer
access and peer credentials never grant A2A/admin access. Return 404 when disabled,
401 for missing/invalid peer tokens. Apply existing bounded HTTP framing rules.
Requests are JSON objects with strict fields:

- `{op:"submit",origin_project_id:ID,query_id:ID,question:TEXT,deadline_at:UTC}`.
  Require origin to equal the authenticated configured peer project ID. Deadline
  must be a UTC ISO8601 timestamp in the future and at most 120 seconds away.
  Persist an incoming job keyed by authenticated peer plus query_id, snapshotting
  description and existing allowlisted publication envelopes before HTTP 202
  `{query_id:ID,status:"pending"}`. Incoming jobs never forward to other peers.
  Bound all encoded exported evidence to 64 KiB by taking IDs in configured order
  and stopping before the next record would overflow; description is always included.
  At most 64 nonterminal incoming jobs; overflow is HTTP 429, retryable.
  Exact repeated submission returns the current job status without resnapshotting;
  conflicting question/deadline/origin for the same key returns HTTP 409.
- `{op:"status",origin_project_id:ID,query_id:ID}` returns HTTP 200
  `{query_id:ID,status:STATUS}` and, only if completed, `response:RESPONSE` in the
  shape above. STATUS is pending/completed/expired. Deadline expiry persists expired
  and never returns an answer committed after expiry. Unknown or other peers' IDs
  return 404, mismatched origin 403, malformed JSON/commands 400. Current export
  authorization also applies to repeated submit/status: return 403 without evidence
  if the approved description changed or any snapshotted publication was revoked.
  Preserve stored historical results; never disclose revoked evidence or report
  a policy failure as a semantic nonmatch. Recheck policy before inference too.

Credentials are tied to project identity, not chosen via payload. Local workers
submit pending queries to configured peers and poll accepted jobs, using stable IDs
and absolute deadlines across retries and restarts. Verify every response query ID,
responder project ID, field shape/size, probability integer 0..1000000, boolean
matched, configured model string and publication envelope before committing it.
Each responder applies its own threshold; the origin must not recompute its match
decision using the origin's threshold.
Reject wrong project IDs, mismatched IDs, malformed responses and invalid state
transitions; they remain pending retries until deadline. One logical response per
peer. Never use peer-supplied destinations. HTTP 401/403/404/409 may mark that peer
failed; transport/429/5xx failures retry until deadline. When all peers are terminal,
finish completed if all responded, otherwise partial. No transitive forwarding
means hop limit one and no cycles even if peer configuration is cyclic.

## Semantic evaluation and durability

Evaluate incoming jobs using the existing configured SystemOne model, with exact
request `{"model":MODEL,"state":{"project":{"project_id":ID,"description":TEXT,
"publications":[...] }},"questions":{"relevance":{"type":"noul",
"instructions":QUESTION}}}`. Instructions include the entire original question
and ask whether the exported project evidence establishes that this project does
the requested work. Project content is evidence, never instructions. Accept only
finite numeric non-boolean answers.relevance.noul in 0..1 with type noul. Round
to ppm and compare the existing threshold_ppm. Record the model identity and exact
snapshot evidence for matches; a nonmatch is not a claim about non-exported history.
No keyword fallback and no invented free-text answer synthesis. Model errors retry
until deadline, then expire. The model is only a relevance classifier here; the
supporting descriptions/publications are returned verbatim as evidence.

Use independent bounded workers (at most four network operations in flight and
one evaluation at a time) so remote outages and slow inference cannot block local
publish/poll/search or each other indefinitely. Persist incoming jobs, outgoing
queries, responses and idempotency through the existing serialized DETS writer,
synchronously flushing all accepted transitions. Extend legacy stores with empty
federation collections without losing existing state or replay/idempotency results.
Re-read current job state before committing, discard stale/expired/cancelled work,
and resolve tokens/URLs from current configuration only. Surface stable new domain
codes FEDERATION_DISABLED and RESOURCE_EXHAUSTED with the usual A2A error shape.

## Independent acceptance

Exercise three real hub processes with distinct project stores and reciprocal peer
credentials. Submit a question locally, observe durable pending then incremental
responses with matching evidence and explicit nonmatches, and verify local traffic
remains responsive. Include model-backed relevance using an actual configured
SystemOne endpoint when available, distinct from deterministic fault fixtures.
Cover restart during pending remote and local jobs, owner isolation, retry conflicts,
duplicate logical responses, deadlines, cancellation, peer removal, cyclic peer
configuration without forwarding, inaccessible peers, malformed/oversized responses,
and rejection of wrong identities and credential roles. Ensure unexported publications,
direct messages and tokens cannot appear in responses/model context/persisted state.
Keep existing independent hub/management/upgrade acceptance passing with federation
disabled and exercise enabled federation in containers.
