---
name: Wire protocol contracts
summary: Independent protocol descriptions, schemas and compatibility conformance
kind: component
---
# Protocol foundation (PROTO-001)

A2A 1.0 JSON-RPC remains mandatory on the agent interface; federation is a distinct
HTTP protocol, not an A2A Task. Do not replace agent operations with invented A2A
methods. Use normative MUST/SHOULD/MAY with RFC2119/RFC8174 meanings. The following
profiles plus existing exact component/information/federation contracts are
normative. All new requests reject unknown keys and invalid shapes before mutation.

## Discovery and schema publication

GET /protocol returns a public non-secret descriptor exactly containing
{protocol:"adhd",version:1,agent:{protocol:"A2A",version:"1.0",path:"/a2a"},
admin:{version:1,path:"/admin/api"},
federation:{versions:[1],path:"/federation/v1",legacy_path:"/federation"},
schema_url:"/protocol/schema"}. This is capability/version discovery, not a list
of private sources or user profiles. GET /protocol/schema returns a valid JSON
Schema draft2020-12 document with $id urn:adhd:protocol:1, title and $defs for
all implemented operations and record envelopes in this Component. Serve the
same document from the accepted artifact and export it through CLI
["protocol-schema"] (one JSON result). GET /protocol/openapi and CLI
["protocol-openapi"] publish OpenAPI3.1.0 with info.version=1.7.0 and paths for
all implemented HTTP endpoints; schemas reference the same exact shapes. Exact
CLI describe remains unchanged; these additional positional forms do not add
A2A operations. Define request/response schemas, required keys, enums, inclusive
bounds, nullability, additionalProperties:false and mutation distinctions; do not
publish vacuous true/object-only schemas. Model arbitrary publication JSON with
recursive JSON values, not an accidental map-only restriction. Tests must validate
actual traffic against schemas with an independently implemented validator.
String limits are UTF-8 byte bounds. Published schemas use x-maxBytes and, where
needed for credentials, x-minBytes alongside standard JSON Schema constraints;
conformance validators must implement these byte-count annotations explicitly.

Unknown /federation/vN paths return 426 UNSUPPORTED_VERSION with supported:[1].
Unsupported protocol values inside v1 messages return400 INVALID_PARAMS; do not
silently downgrade or dispatch a legacy operation. The old /federation submit/status
wire contract remains accepted unchanged for compatibility and uses its old response
shape. New versioned endpoint supports the same submit/status semantics, plus
explicit extensions only when separately specified. Returned v1 body includes
protocol_version:1 and fields specified by the particular operation; never add this
field to the legacy endpoint's response. v1 requests include protocol_version:1,
op and operation-specific keys; reject duplicates/unknown fields. Authenticate peer
before decoding both versions; Bearer maps to peer identity, not the claimed body.

## HTTP/JSON profile

UTF-8 JSON, Content-Type application/json (optional charset=utf-8), no BOM, no
nonfinite numbers, no duplicate object keys at any depth, strict JSON strings and
size bounds in bytes. Distinguish omitted optional fields, explicit null and empty
values exactly as each operation specifies. Reject booleans for numbers/integers. Integer fields use integer JSON tokens;
decimal/exponent encodings are rejected even when mathematically integral.
Schemas mark this additional profile constraint with x-integerToken:true;
conformance validators must enforce the decoded integer type without float/bool.
Runtimes that erase this distinction must retain number-token metadata while
parsing JSON.
IDs are case-sensitive; sequence IDs are opaque, never parse their prefix as proof
of ownership. Generated datetimes are RFC3339 UTC with Z and millisecond precision.
Normalize occurred_at to UTC while preserving its reported fractional precision;
do not add a fraction to a whole-second input or rewrite historical results.
Accept documented input offsets only for occurred_at. Deadlines use absolute UTC
and require synchronized clocks; OIDC permits only its explicit 30s claim skew.

Existing HTTP framing limits remain: reject ambiguous duplicate Content-Length,
Transfer-Encoding/chunked, invalid lengths and trailing request data as documented
by component.md. No redirects followed by peer/model/backchannel clients; verify
HTTPS certificates and hostname. Endpoint URLs may not contain embedded credentials.
Connection/request deadlines and decoded response bounds apply before JSON use.
Do not use arbitrary peer-supplied reply URLs or IdP URLs from an unverified token.

New admin errors: {error:{code:STRING,message:GENERIC_STRING}} with optional
current_revision only on CONFIG_CONFLICT. Missing/invalid authentication=401,
insufficient role/origin/CSRF=403, invalid shape=400, missing resource=404,
idempotency/revision/apply conflicts=409, rate limit=429 (Retry-After seconds),
write or dependency unavailable=503, internal failure=500. No secret/input echo.
Resource admission MODEL_BUSY, NETWORK_BUSY and EVENTING_BUSY, stale queued
CONFIG_CHANGED and writer-freeze CONFIG_APPLY_IN_PROGRESS are retryable503
service errors for ordinary HTTP. Valid A2A requests retain their HTTP200
JSON-RPC -32000/ErrorInfo domain representation; retry the identical mutation
message ID after bounded backoff. Writer-freeze responses include Retry-After:1.
Event repair/replay precondition conflicts use EVENTING_CONFLICT/409; an
overlarge replay range uses RANGE_TOO_LARGE/413. EVENTING_DISABLED is503 and
requires enabling the capability rather than retrying indefinitely.
PROJECT_ARCHIVED denies new work with HTTP403 on ordinary HTTP/peer interfaces;
authorized reads and explicitly permitted recovery controls remain available.
Existing A2A errors retain their specified JSON-RPC/domain mapping. New A2A domain
codes use the same adhd.hub structured error shape, never pretend success.
Versioned peer errors have {protocol_version:1,error:{code,message}} with the
same HTTP class where applicable. A new path's malformed-body error is not a
reason to fall back to an unauthenticated or old protocol.

## Durable asynchronous profile

Query creation ACK means query plus peer/source scope is synchronously persisted;
peer submit ACK means incoming job and evidence snapshot are durable. It does not
mean inference has completed. Stable keys are (origin server/project,query_id)
for peer jobs and (authenticated actor,message_id) for local mutations. Compare
canonical decoded commands (object key order immaterial, arrays ordered); conflicting
reuse is409. Idempotency records remain as long as the associated durable record;
no time-based expiry in this version. Replies may be delivered/polled repeatedly:
logical deduplication is guaranteed, not exactly-once network transmission.

State machine: local pending -> completed|partial|cancelled only; incoming
pending -> completed|expired only. Terminal records never return to pending.
No response committed after deadline/cancellation; one logical answer per selected
peer. Config changes may invalidate in-flight work and require retry under current
policy, not accepting stale authority. Preserve ordered public results by selected
peer/source order regardless of arrival. Clock expiry, removed peer, unknown owner,
unauthorized peer and unavailable model must not be presented as semantic nonmatch.
Cancellation stops origin collection; accepted remote work may run until its
original deadline. Resource budgets and explicit coverage remain per feature.

Transport/429/5xx retries use bounded configured delay and common absolute deadline;
401/403/404/409 may terminally fail that peer. Honor a valid Retry-After within the
remaining budget; invalid/unbounded values do not extend the deadline. No recursive
forwarding for discovery. All model/network I/O is outside the serialized writer.
Document any additional routing hop limit in the owner-routing extension.

OIDC uses the exact standard profile in identity/spec.md, including code/PKCE,
issuer/JWK validation, cookie state/nonce/CSRF and server-local roles. SystemOne
model calls use configured model + state + typed questions and documented finite
numeric answers; never substitute keyword matching for a model failure.

directory/spec.md adds the exact v1 catalog, identity and source-job operations,
source/cache revision semantics and scope/owner fences. Include those operations
in the same published schema/OpenAPI inventory; no downgrade to legacy transport.

## Documentation and independent conformance

Export readable endpoint, operation, field, error, state-transition and version
compatibility tables in docs/protocol/. Include real valid and invalid JSON fixtures
for all new messages; keep these authored fixtures independent from generated
implementation-test manifests. Schema/OpenAPI files exported from the accepted
artifact must be reviewed against normative specifications and tested on actual
HTTP and CLI responses, not trusted because the code also generated them.

A protocol report binds artifact SHA256, protocol/schema versions and fixture
results. Test version discovery/unknown versions, authentication-role separation,
duplicate keys, bounds, JSON integer/boolean distinctions, HTTP framing, malformed
responses, stale authority, retry/dedup/deadline/cancel/restart, and information
visibility. Independently authored clients/responders must interoperate using
published documents, without importing generated runtime code. Update contract,
schema, examples, compatibility notes and tests together for any wire-visible change.
Future pub/sub would need its own topics/envelopes, delivery/ordering/retention and
ACL contract before implementation; no broker is selected by this version.


## Contextual retrieval extension

Profile1.4 adds retrieval/spec.md, index.md and interface.md (relative to this
Component). Preserve peer wiremajor1 and existing history/model contracts. Publish
all five agent operations, Admin index/rebuild/job variants and live RetrievalConfig.
The root convenience union uses anyOf because safe agent/Admin read operations
may share a command; each transport-specific command schema remains closed.
Critical x-utf8Span, x-noulExchange and x-fragmentProjection have the exact meanings
in retrieval/interface.md and require independent positive/negative validation.
Compact model inputs and full recorded provenance must remain consistent.


## Archive workflow extension

Profile1.5 adds archive/spec.md and interface.md, preserving peer wiremajor1 and
all earlier public operations. Publish owned archive commands, direct choice
exchanges, child provenance, stage budgets, audit populations and exact uniform256
sampling probabilities. Admin query-job variants and live ArchiveConfig are part
of the same schema/OpenAPI/examples update. Critical x-archiveSample,
x-archiveUsage, x-byteLengthOf, x-archiveOriginals and x-archiveBindings have the
exact meanings in archive/interface.md and require independent cross-field validation; errors, incomplete
audits and provisional comparisons never become ground-truth negative labels.


## Feedback and paired replay extension

Profile1.6 adds feedback/spec.md, replay.md and interface.md. Publish owned attempt
reads/replay commands, explicit Admin adjudication/cohort/retirement controls and
ReplayQuery job variants with hot FeedbackConfig. Preserve source/publication and
peer wiremajor1 shapes. Current-vs-recorded model requests remain distinct;
x-replayBindings and x-replayUsage plus inherited exact request/original constraints
require independent semantic-negative traffic. Never count exposed cohorts as fresh
or changed-corpus answers as retrieval improvements.

Profile1.7 adds optimization/spec.md, selection.md and interface.md. Publish Admin
proposal/evaluation/promotion/rollback/retirement messages, hot OptimizationConfig
and effective selection metadata. Internal optimization replays preserve original
agent ownership and durable proposal exposure. Selection authority remains outside
derived rows; exact critical optimization bindings/usage require independent
semantic-negative and native/container qualification. Peer major1 is unchanged.

## Selective recovery application profile2.1

project-recovery/interface.md and interface.schema.json own additive Admin
plan/apply/status, root hot recovery settings and RECOVERY_REQUIRED target-state
errors. The implementing successor exports application/OpenAPI2.1.0 and combined
schema urn:adhd:protocol:2.1. Descriptor major2/admin envelope1, A2A1.0 and peer
versions1/2 stay unchanged; existing healthy result shapes stay unchanged. New
status exposes target availability/defaults. Do not claim strict2.0 schemas
validate new2.1 messages. Retain actual accepted2.0 exports until a reviewed new
artifact implements and qualifies the extension; then publish schema, examples,
compatibility and independent conformance together.
