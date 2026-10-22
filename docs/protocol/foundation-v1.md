# ADHD profile-1 foundation (historical)

This page records the inherited profile-1 semantics through application profile
1.7. It is historical background. Use the [current protocol index](README.md) and
[multi-project/Kafka contract](multi-eventing.md) for project selection, optional
matching, delivery reasons and peer-v2 replacements. Profile-2 clients must apply
those replacements; the single-project and mandatory-matching statements below
describe profile 1 only.

This profile describes independently implementable interfaces. Component
contracts are normative and are distributed with the container artifact. Their
repository paths are `components/hub/core/spec.md` (A2A and persistence),
`information/spec.md` (envelopes), `management/spec.md` (management),
`configuration/spec.md` (live settings), `identity/spec.md` (users and OIDC),
`federation/spec.md` (peer exchange) and `protocol/spec.md` (wire rules), with the
latter paths relative to `components/hub/`. `directory/spec.md` owns metadata
exchange and identity comparison; `directory/queries.md` owns canonical routing
and source-job messages. None requires reading
implementation source. Changes to messages require contract, schema, examples,
compatibility and conformance updates together.

## Versions and interface inventory

| Interface | Exact profile | Discovery and transport |
| --- | --- | --- |
| Agent to hub | [A2A 1.0.0](https://a2a-protocol.org/v1.0.0/specification/), JSON-RPC 2.0 binding, ADHD commands below | Agent Card at `GET /.well-known/agent-card.json`; `POST /a2a` |
| Peer to peer | ADHD HTTP federation 1 | `GET /protocol`; `POST /federation/v1` |
| Legacy peers | Original unversioned ADHD submit/status | `POST /federation`, preserved unchanged |
| Human administration | ADHD admin 1, local sessions or explicitly allowed legacy bearer | `/admin`, `/admin/api`, login/session/logout endpoints |
| OIDC backchannel | [Core 1.0 errata 2](https://openid.net/specs/openid-connect-core-1_0-errata2.html), [Discovery 1.0 errata 2](https://openid.net/specs/openid-connect-discovery-1_0-errata2.html), [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) S256, RS256 | Configured issuer discovery, authorization redirect, token exchange and JWKS |
| Decision model | SystemOne typed `noul` relevance and separate `choice` history adapters | Configured HTTP endpoint, default `/v1/systemone`; independent `/health` |
| Schemas | [JSON Schema draft 2020-12](https://json-schema.org/draft/2020-12/json-schema-core) and [OpenAPI 3.1.0](https://spec.openapis.org/oas/v3.1.0.html) | `GET /protocol/schema`, `GET /protocol/openapi`; CLI `protocol-schema`, `protocol-openapi` |

Agent-facing A2A is mandatory. Peer federation is its own HTTP protocol and does
not create or require A2A Tasks. The current transport uses durable submit/status
polling. No pubsub broker or alternative transport is implied.

`GET /protocol` returns the public descriptor specified in the protocol contract.
Versioned peer requests include integer `protocol_version:1`; responses include
that field. Legacy bodies omit it. Unknown `/federation/vN` returns HTTP426,
`UNSUPPORTED_VERSION` and `supported:[1]`. A bad v1 body returns400; clients must
not silently retry it using the legacy endpoint. The CLI's `describe` envelope and protocol version remain compatible; its
operation list grows with additive capabilities.

The current downloadable schema/OpenAPI snapshots are linked from the
[protocol index](README.md); they are not profile-1 snapshots. Profile 1 used
schema `$id` `urn:adhd:protocol:1`, with additive application versions through
1.7.0 and peer wire major 1. Clients inspect operation capabilities; peers lacking
directory/source operations are explicitly unavailable for those operations.
String bounds are UTF-8 bytes: apply the documented `x-maxBytes` / `x-minBytes`
constraints as well as standard JSON Schema validation. These annotations count
bytes in the decoded string, not bytes in its escaped JSON representation.
OpenAPI schemas describe transport envelopes; `$defs.agent_*` describe commands
inside A2A DataParts. `$defs.result_*` and `$defs.admin_result_*` describe results.
Arbitrary publication data is recursive JSON, including scalars, arrays and null.

## Common HTTP and JSON rules

Requests use UTF-8 `application/json`; bodies must be valid JSON without duplicate
object keys at any depth, BOM, nonfinite numbers or malformed string encodings.
Integers do not accept JSON booleans, decimal or exponent encodings. Apply
`x-integerToken:true` as a profile constraint in addition to JSON Schema, whose
standard integer concept also permits mathematically integral decimal numbers.
Arbitrary publication JSON numbers retain their normal JSON representation. Omitted, null and empty values have distinct
meanings defined per field. Reject unknown command keys. HTTP header/length/body
limits and unsupported transfer framing are specified in the base contract;
ambiguous lengths, chunked requests and trailing bytes are rejected before dispatch.
Every response closes its HTTP connection and has a byte Content-Length.

IDs are opaque and case-sensitive. Agent/project identifiers use their documented
ASCII identifier alphabet. Generated times are UTC RFC3339 with milliseconds;
`occurred_at` preserves reported fractional precision while normalizing to UTC.
Historical idempotency results remain byte-equivalent JSON values after upgrades.
Clocks must be synchronized for peer deadlines. Clients never supply arbitrary
reply URLs. Backchannel clients do not follow redirects or disable TLS verification.

| HTTP status | Meaning for admin/peer operations |
| --- | --- |
| 200 | Completed synchronous operation or status/result retrieval |
| 202 | Peer submit durably accepted; evaluation may still be pending |
| 302 | OIDC redirect, with the appropriate state/session cookie |
| 400 | Invalid message, parameters, state or OIDC proof |
| 401 / 403 | Missing/invalid authentication / insufficient role or origin/CSRF failure |
| 404 | Unknown resource or disabled legacy interface |
| 409 | Revision/idempotency/identity conflict or failed atomic apply |
| 413 / 415 | Oversized body / unsupported media type |
| 426 | Unsupported federation version |
| 429 | Bounded resource or login limit; Retry-After seconds |
| 500 / 503 | Internal failure / configuration write or dependency unavailable |

Admin errors are `{ "error": { "code": "CODE", "message": "generic" } }`.
`CONFIG_CONFLICT` may include `current_revision` inside error. V1 peer errors add
`protocol_version:1`. Messages never echo credentials, raw provider responses or
private data. A2A retains JSON-RPC errors: parse -32700, invalid envelope -32600,
method -32601, params -32602, internal -32603, domain -32000. Domain errors carry
Google `ErrorInfo` with `domain:"adhd.hub"` and matching reason/metadata.code.

## Agent commands

Send one `SendMessage` with a nonempty messageId, ROLE_USER and one DataPart
containing the command, or a TextPart containing its JSON encoding. Replies are
ROLE_AGENT Messages with one result DataPart. Streaming, push and Task operations
are not advertised. Agent bearer tokens authorize their own actor; a human login
cannot be used as an agent credential.

| Commands | Purpose and result |
| --- | --- |
| whoami | Caller and current project IDs |
| subscribe / list_subscriptions / unsubscribe | Own natural-language subscriptions |
| publish / get / search | Immutable project publications, source-item deduplication and retrieval |
| send / poll / ack | Private addressed deliveries and durable acknowledgements |
| federated_query | Durable asynchronous direct-peer query |
| get_federated_query / cancel_federated_query | Owner-only incremental results or cancellation |
| federation_directory / identity_matches | Fresh catalogs and correlations for the agent owner |
| query_history / get_history_query / continue_history_query / cancel_history_query | Owned frozen local history scans and paged original/model evidence |
| source_query / get_source_query / cancel_source_query | Durable canonical-only source questions |

Exact field limits, required/optional keys and result envelopes are in the base,
information and federation contracts. Search filters combine with AND. Private
messages never enter project-public search or exported federation evidence.
Subscriptions evaluate future publications, not an automatic historical backfill.

## Administration and OIDC

`GET /admin/session` returns either authenticated user/CSRF/revision or
`{authenticated:false,methods:{local,oidc,key}}` without project data. Local
`POST /admin/login` takes username/password. Sessions use an opaque HttpOnly,
SameSite=Lax, Path=/admin cookie, Secure with HTTPS. Cookie-authenticated admin
POSTs also require same Origin and X-CSRF-Token. Logout revokes the session.
OIDC ID/access tokens are not accepted directly as local API bearer tokens.

| Role | Read project/admin metadata | Create own agent | Users/roles/settings and full private-data access |
| --- | --- | --- | --- |
| Viewer | Yes | No | No |
| Developer | Yes | Yes | No |
| Admin | Yes | Yes, any valid owner | Yes |

Admin operations are overview, publications, publication, subscriptions, deliveries,
jobs, create_subscription, remove_subscription, retry_jobs, config_get,
config_update, config_validate, users, save_user, update_profile, agents,
create_agent, private_delivery, test_oidc, link_oidc, federation_directory, identity_matches
refresh_federation, query_jobs, query_job and cancel_query_job. The role matrix in the
identity contract governs all APIs. Delivery lists remain metadata-only;
private_delivery is the explicit Admin-only full-envelope operation.

Persistent user/config mutations require expected_revision, message_id and
confirm:true where specified. Config updates apply RFC7396 merge-patch semantics:
omit to retain, null to remove/reset, arrays replace. The server owns revision,
password hashes and proved OIDC identities. Secrets are omitted from config_get;
its secrets map contains only JSON-pointer presence booleans. Request replay is
scoped by authenticated actor plus message_id and a command digest. Stale writes
fail409; they do not overwrite intervening changes.

OIDC uses authorization code + PKCE S256, random state and nonce, a bound state
cookie, five-minute single-use flows, exact issuer/audience/nonce validation and
unique RS256 signing key IDs. Multiple audiences require azp; azp, when present,
must equal client_id. Token expiry, issue time, optional not-before, RSA strength,
key use and malformed JWT encodings are checked. A missing/invalid group array
cannot manufacture a role. Local role mappings resolve Admin > Developer > Viewer;
unmapped users need an explicit configured default, otherwise access is denied.
Provider failure never silently enables another sign-in method.

link_oidc prepares a confirmed, Admin-authorized proof flow. It is not a direct
identity assignment API. Completion preserves user ID, role and agent ownership,
requires the original administrator authorization and a current revision, and
rejects identities already attached to another account. Built-in admin stays local.
Ordinary issuer+subject login never merges local accounts by matching email.

## Asynchronous federation and matching

Local query states are pending → completed, partial or cancelled. Peer jobs are
pending → completed or expired. Terminal results do not return to pending.
A submit ACK follows durable persistence of command and authorized evidence
snapshot. Repeated submit/status exchanges may occur; logical deduplication is
separate from network delivery. Retry matching keys return their original result;
changed commands conflict. Peers respond only for their authenticated origin.

Origin collection records selected/responding/failed/pending peers and preserves
selection order. Late answers after cancellation/deadline do not commit. Transport,
429 and 5xx failures retry within the common deadline and bounded delay; permanent
peer failures remain explicit. No response is not a negative fact. Current
federation uses direct peers and no recursive forwarding. See the federation
contract for all message fields, fan-out/storage bounds and export visibility.

The matcher receives model + publication/project evidence + a typed relevance
question. It returns a finite probability in [0,1]. The hub converts to integer
parts per million and applies the configured threshold. Model errors are durable
retryable work, never nonmatches. No generative response or Qwen service participates
in this publication/subscription path. Provider usage/metrics/scoring metadata is
not used as relevance or permission authority.

## Directory and canonical-source extension (profile 1.1.0)

Use the [directory guide](../user/federation-directory.md) for configuration and
agent examples. Versioned peer operations are `catalog`, `identities`,
`source_submit` and `source_status`; legacy submit/status are unchanged. Their
exact bodies and state/ownership fences are specified in `directory/spec.md` and
`directory/queries.md` relative to the hub Component. No peer or cached profile
can assert a local role. All source questions require a structured source or
provider/host/tenant-qualified alias; broad project discovery is not authoritative
for a source. No question is forwarded to a copy as a substitute for its owner.

Directory snapshots carry a stable server ID, current project label, content
revision, generated time, ten-second maximum age and opaque pagination cursor.
Revision is SHA-256 over canonical UTF-8 JSON `{visible,items}` across all pages:
lexicographically sorted object keys, compact separators, ordinary JSON escaping,
unescaped non-ASCII characters and no floats. Arrays retain their order. Catalog
entries are ordered by scope digest; profiles are ordered by local user ID.
A changed snapshot cursor returns409 SNAPSHOT_CHANGED; restart at page one.
Metadata is never relayed as a local claim, and cache reception/restart never
extends original expiry. A source-submit origin pin not learned yet returns503
DEPENDENCY_UNAVAILABLE; a known identity mismatch is409 IDENTITY_CONFLICT.

Source jobs retain owner/scope correlation, command deduplication, deadlines and
cancellation across restart. A source status may become revoked after an owner
claim or evidence permission changes, and must omit its response. The compatible
legacy endpoint returns403 for revoked snapshot evidence, including previously
completed jobs, without rewriting historical stored results. Policy failure is
never reported as semantic nonmatch. Retry-After seconds and HTTP-date hints are
bounded by the original query deadline; invalid/unbounded hints cannot extend it.

[Executable examples](examples.json) include valid and invalid request/response
shapes and are independently checked against the published schema. Example times
are illustrative: live submit deadlines must be generated in the future and at
most 120 seconds away. See conformance reports for actual three-hub exchanges.

Admin-only query-job list/detail/cancellation APIs expose discovery and source
records without making a human session an A2A agent credential. Cancellation
is a product mutation, with confirmed, actor-scoped message-id retry semantics;
it does not change configuration revision. Activity provides the corresponding
Admin controls. Current permissions are checked before serving cached mutations.

New/rotated agent, Admin and peer bearer credentials use RFC6750 b64token ASCII
characters and at most 4096 bytes, with their existing minimum lengths. This
keeps them usable within HTTP framing limits. Unchanged legacy credentials
remain compatible; unsafe replacement values never activate. Passwords and
OIDC client secrets are separate JSON/backchannel fields with their own bounds.

## Contextual evidence (profile 1.2.0)

Agent `publish_record` accepts publish fields plus optional `context`; it returns
`{record,matching:"pending"}`. `get_record` accepts publication_id and optional
watermark, max_depth and limit, returning `{snapshot,record,related,gaps,truncated}`.
Admin `record` provides the same read through existing local authorization.
The exact contract, `components/hub/evidence/spec.md`, defines immutable
identities, link resolution at ingestion, frozen membership, privacy, traversal
ordering/bounds and gaps. No peer protocol or OIDC message changes are introduced.
Original publish/get/search envelopes remain compatible. Clients discover these
operations in the published schema; older peers need not implement them.

`x-maxCanonicalBytes` bounds compact sorted-key UTF-8 JSON, with Unicode preserved.
`x-sha256Of` maps a digest property to its sibling string property and requires
SHA256 over the exact UTF-8 string. Both annotations are mandatory application
profile validation in addition to JSON Schema shape checks. The context schema
contains no numeric values; arbitrary JSON publication content keeps its existing
number semantics and immutable opaque record identity.

## Snapshot history questions (profile 1.3.0)

The normative contracts are `components/hub/history/spec.md`, `interface.md` and
`evaluator.md`. [History questions](../user/history-queries.md) explains the workflow.
Four additive A2A commands create, inspect, continue/restart and cancel owned jobs.
Agent ownership is checked independently of email; explicit Admin query-job APIs
supply evidence inspection and cancellation. No federation envelope changes.

HistoryQuery reports a frozen public archive scope/watermark, evaluator identity,
per-run and cumulative cost, separate primary/final coverage, original excerpts,
uncertainty, errors and evaluation pages. Operational interpretations never become
publications. Later corrections cannot enter an older snapshot. Scope occurrence
times use years 0001..9999, uppercase T/Z, seconds 00..59 and at most six fractional
digits; supplied bounds are ordered by instant. Private evidence is excluded.

The independent SystemOne `choice` adapter asks assessment and answer questions.
Every offered probability must be present, finite and in [0,1], sum to 1 within
0.00001, and select a maximum with matching confidence. Model names and question
keys must match the paired request. Malformed responses remain partial model
errors, never nonmatches or unsupported facts. The normative template supplies
exact instructions and fixed criteria; quote choices contain whole originals.
Recorded requests preserve their historical instructions across template upgrades.

These annotations are critical validation rules beyond JSON Schema:

- `x-choiceDistribution`: complete finite normalized probabilities, maximum
  selection and matching confidence.
- `x-choiceExchange`: response model, question IDs and probability key sets match
  the paired request.
- `x-historyChoices`: exactly the fixed criteria and quote_0 through quote_(N-1)
  containing each complete original text or equivalent original JSON data.
- `x-jsonOf`: strict JSON string parses to its equal sibling object, rejecting
  duplicate keys, nonfinite values and boolean/number substitution. `x-sha256Of`
  binds its exact UTF8 bytes.
- `x-orderedTimes`: supplied lower/upper occurrence bounds are chronologically
  ordered, including zone offsets and microseconds.

Owner/Admin evidence records exact request_json bytes and digest, parsed request,
validated typed answers and original context identities. Limits and pagination
remain explicit. Evaluator URL is private configuration. Public evaluator versions
are operator assertions, not cryptographic weight attestations. Live History
Settings include inheritance, confidence, context, budgets and state capacity.
Subscription `noul` behavior remains unchanged.


## Contextual retrieval (profile 1.4.0)

The normative contracts are `components/hub/retrieval/spec.md`, `index.md` and
`interface.md`. [Candidate retrieval](../user/retrieval.md) explains agent and Admin
workflows. Five additive A2A commands create/read/continue/cancel owned retrieval
jobs and read safe index status. Admin has explicit index inspection, confirmed
rebuild and query-job inspection/cancellation. Peer envelopes are unchanged.

Native contextual BM25 generations bind exact originals, context inputs, recipe,
runtime and watermarks. Builds checkpoint outside the serialized writer and activate
after catch-up. Frozen queries reconstruct older row inputs when a newer generation
contains later context; their document statistics exclude future/out-of-scope rows.
Completed candidate plans never claim exhaustive coverage or answer support.

The separate SystemOne usefulness request asks exactly `useful` with type `noul`.
Its compact state contains the question, root publication ID and ordered original
fragment views. The paired response must match the configured model and contain
exactly one finite typed probability in [0,1]. Failures are explicit model errors.
Full identities, UTF-8 spans, hashes and exact request bytes remain in evaluation
evidence outside the model input. Recorded instructions preserve historical runs.

Additional critical validation rules:

- `x-utf8Span`: integer nonnegative offsets, end >= start and end-start equals
  the exact UTF-8 byte length of fragment text; `x-sha256Of` checks its digest.
- `x-noulExchange`: paired model and exact useful question/answer agree; the
  answer is a finite typed noul probability, never a boolean or an invented key.
- `x-fragmentProjection`: the ordered model fragments equal the recorded full
  fragments projected to origin_publication_id, field and text. Root ID and
  truncation flag equal the evaluation's publication_id and fragment_truncated.

The root convenience schema uses anyOf for command families that share safe reads;
transport-specific schemas still reject unknown fields. Retrieval scores are
relevance only. Original-context inspection and history scans retain their own
contracts and budgets. The archive extension below composes fallback; automatic
recipe qualification/promotion remains a separate capability.


## Archive workflow (profile 1.5.0)

`query_archive`, `get_archive_query`, `continue_archive_query` and
`cancel_archive_query` compose owned retrieval, original support assessment and
full History scans. Read the exact field, template and budget definitions in
`components/hub/archive/interface.md` and the policy in `archive/spec.md`.
[The archive guide](../user/archive-queries.md) describes calling and interpreting
these operations. Agent commands remain A2A DataParts; Admin uses explicit query-job
inspection/cancellation. This extension does not change peer wire major 1.

Each question freezes owner, scope, original primary IDs and ingestion watermark.
Mode is search, scan or search_then_scan. Explicit `complete:true` requires full
primary/final evaluation; language planning cannot certify completeness in every
language. Search scores never establish support. Candidate assessment fetches full
originals/context with a separate typed choice evaluator. Unknown, insufficient,
conflicting or failed support requires a scan in hybrid mode. Search-only retains
an explicit partial result when it cannot answer under its contract.

The five stage budgets and counters distinguish planner, retrieval, assessment,
scan and audit. A budget continuation keeps its execution plan and sampling draw;
explicit restart creates a new plan on the same frozen corpus. Child references
bind the exact owner/question/scope/snapshot/run. Child interference is explicit.
Operational judgments never become publications or subscription deliveries.

Successful candidate answers alone are eligible for audits. Each plan durably
predraws 32 random bytes before inference. Under the declared uniform256 model,
the threshold is floor(rate_ppm * 2^256 / 1000000). Exact numerator/denominator
are decimal strings. The draw remains private until successful-search eligibility
is recorded with selection. A selected audit uses a separate full History child;
partial/failed audits do not establish equivalence or ground-truth negative labels.

Critical validation rules, in addition to the earlier profile annotations:

- `x-archiveSample`: verify the exact rational threshold, draw, eligibility,
  selected flag and population. Rate 0 never selects; rate 1000000 always selects
  eligible successes. Ineligible plans conceal their draw.
- `x-archiveUsage`: each total counter equals the sum of the five stage counters;
  cumulative stage costs cannot be smaller than that run's costs.
- `x-byteLengthOf`: declared bytes equal the exact UTF-8 length of request_json.
- `x-archiveOriginals`: ordered IDs and context identities equal those of the full
  original records in the assessment request.
- `x-archiveBindings`: bind plan/sample rate, child reference/run and frozen
  owner/question/scope/snapshot, evaluation question/model, and direct support
  required for audit eligibility.

Existing `x-jsonOf`, `x-sha256Of`, `x-choiceExchange`, `x-choiceDistribution` and
`x-historyChoices` remain mandatory. Current requests publish the revised shared
History choice template; recorded requests preserve historical instructions.
Template version changes invalidate pending interpretation through policy identity,
while historical completed runs remain readable.

## Feedback and paired replay (profile 1.6)

The closed commands and objects are specified in
`components/hub/feedback/interface.md`, with capture/cohort rules in `spec.md` and
paired execution in `replay.md`. The [replay guide](../user/retrieval-replay.md)
explains interpreting confirmed recall separately from supported answers and
actual fallback costs. Human Admin labels are independent assertions. Agent
feedback/replay reads are owner-scoped; Admin creation records the human requester
without impersonating that owner. Changed-corpus, unlabeled, incomplete and retired
observations cannot qualify retrieval improvement.

Two additional critical annotations require independent validation:

- `x-replayBindings`: bind primitive recipe/runtime identities, interpretation
  descriptors, question/model inputs, returned/assessed original IDs, captured label
  revision/identity, expected History owner/scope/snapshot/run and comparison
  eligibility. Confirmed recall derives from supplied candidate originals. A
  changed corpus or retired evidence is ineligible. Actual experiment costs bind
  comparison deltas.
- `x-replayUsage`: branch counters equal the parent's corresponding usage, totals
  equal the sum of both branches, and cumulative counters cannot be smaller than
  their current run. `comparison_usage` accumulates the current experiment across
  continuations and resets only for an explicit restart.

The existing exact request JSON/SHA/byte-length, typed choice/noul, fragment-span
and full-original annotations also apply to replay evaluations. Unknown critical
annotations must fail closed. Replay adds no peer wire-major change.

## Adaptive index selection (profile 1.7)

Profile1.7 adds optional Admin-only `optimization_status`, `index_proposals`,
`index_proposal`, `propose_index`, `evaluate_index`, `continue_index_proposal`,
`cancel_index_proposal`, `promote_index`, `rollback_index`,
`reset_index_selection` and `retire_index_proposal`. Mutations require the current
configuration revision, actor-scoped message ID and explicit confirmation;
promotion/reset/rollback also bind the expected selection revision. Agents keep
existing A2A commands; internal Replay requester_kind `optimization` names the
parent proposal and cannot be supplied by agent transports. Peer federation is
unchanged. See `optimization/interface.md`, `spec.md` and `selection.md` under
`components/hub/` for every closed field, enum, bound, failure and lifecycle rule.

Optimization is disabled by default, with review mode selected. Structured hot
Admin configuration owns all recurrence/cohort/quality thresholds, native limits,
automatic mode and aggregate budgets. Frozen training selects one winner before
fresh held-out execution. Stable exposure identities prevent relabeling, retirement,
failed work or group merges from manufacturing fresh evidence. Continuation and
explicit failed-pair retries preserve all actual cumulative costs.

`RetrievalIndexRead.selection` distinguishes primitive operator base, effective
selection, previous recipe and current/qualification runtime. Promotion switches
the caught-up native generation and primitive selection in one durable transaction.
Rollback builds/catches up before switching; explicit recipe patches reset the
override even when merged values are identical. Source originals and labels remain
authoritative. Qualification watermarks cover the evaluated case marks, not every
source through the activation mark or a new runtime.

Independent critical handlers `x-optimizationBindings` and `x-optimizationUsage`
bind runtime/recipe identities, frozen winner, cohort membership, expected child
runs, available evidence and native manifests; they check per-case and aggregate
quality/cost arithmetic and retained unsuccessful work. A positive mean recall
gain cannot hide a recall loss on any evaluated case, even when full fallback
preserves that case’s answer. Case pages are bounded, so
complete aggregate verification requires all pages and referenced paired replay
labels/evidence. Unknown critical annotations fail closed. Schema, OpenAPI, fixtures and independent lifecycle/model tests must travel together. Human
labels and model judgments remain fallible; scoped improvements are not a general
answer-quality or isolated-latency guarantee.

## Multi-project successor

The [current protocol index](README.md), [multi-project contract](multi-eventing.md)
and [examples](multi-eventing-examples.json) describe the profile-2 replacements.
Profile-1 acceptance does not establish compliance with those replacements.
