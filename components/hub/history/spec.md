---
name: Snapshot history questions
summary: Owned durable semantic history jobs and bounded contextual evidence evaluation
kind: component
---
# Snapshot history questions

This additive agent API profile 1.3.0 retains wire major 1. This extension adds `query_history`, `get_history_query`,
`continue_history_query`, `cancel_history_query` to A2A project-public commands.
It preserves literal `search`, subscription matching and federation envelopes.
These operations ask about the local historical archive at an explicit server
snapshot. They do not assert remote canonical ownership: explicit canonical-source
questions continue to use directory/queries.md source_query routing.
No new domain taxonomy or model weights are required. Originals remain authority;
model interpretations are fallible, separately stored operational state.

## Requests and ownership

`query_history` requires `question` (nonblank UTF8 <=4096 bytes). Optional `scope`
is an object with only `information_type` (identifier), `source_kind` (identifier),
`source_id` (nonblank <=256 bytes), `occurred_from`, `occurred_until` (RFC3339 with
zone, inclusive; years0001..9999, uppercase T/Z, seconds00..59 and at most six
fraction digits), and `watermark` (integer 0..9007199254740991 not beyond current
last-publication ingestion sequence). All supplied filters intersect.
Optional `complete` boolean defaults false, `budget` has optional integer
`records` 1..10000, `calls` 1..10000, `bytes` 1024..16777216 and `time_ms`
100..120000. Defaults come from hot `history` configuration. These are per-run
budgets; cumulative work is separately reported. Unknown keys/types fail closed.

`get_history_query` requires `query_id` and optionally accepts `run` (1..16),
`offset` (0..1000000, default0) and `limit` (1..64, default16) for evaluation
pages. An omitted run selects the current run; an explicit prior run returns
its retained immutable view, or NOT_FOUND if absent. `continue_history_query` requires
`query_id`, accepts `budget` and `restart` boolean default false. Cancellation
requires only `query_id`. All changes require ordinary mutation message identity;
identical retry returns original response; changed retry conflicts. Different
agents cannot inspect or mutate each other's questions (NOT_FOUND), including
agents whose owners have matching emails. Human Admin has explicit management
read/cancel operations, never an agent impersonation path. Agent removal excludes
work from scheduling; owner authorization is rechecked for each command.

Submission allocates a durable job immediately with state `pending`. It freezes
all public publication IDs at the watermark, selected primary IDs in ingestion
order, scope, original question, immutable evaluator/policy identity and exact
configuration. Selected primary records plus context expanded only within that
frozen public corpus may contribute evidence; private deliveries and operational
questions/answers/feedback never join the corpus. Later publications/corrections
cannot change an earlier query. Context outside the primary filters is allowed
only as a labeled expansion linked to selected records, with its IDs and gaps
reported separately. Existing record-read bounds apply (depth 2, max32 by default).
No HTTP fetch follows external URLs. Missing external snapshots remain gaps.

At most64 active history jobs (pending/partial/invalidated) and1024 total retained jobs; overflow returns
RESOURCE_EXHAUSTED. Retention/explicit deletion must not remove publication data.
A separate worker processes history jobs outside Store, at most one history model
request at once. While subscription work is due, start at most one history call
per second; otherwise process available work normally. This bounded priority
reserves opportunities for both workloads rather than starving queued history jobs. Every result
is committed only if the job is still pending, its run/version unchanged and the
current evaluator identity still matches its frozen identity. A history job has
at most16 runs, including continuations and explicit restarts; refuse further
runs with RESOURCE_EXHAUSTED. Restart resumes
from persisted checkpoints; a killed in-flight call may be repeated and counted
conservatively, with uncertain_calls made explicit. Reserve calls/bytes durably
before I/O; after abandoned reservations, retain those costs and conservatively
charge the reserved timeout before retrying. Cancellation prevents late results from restoring pending state.

## Results and coverage

All operations return `{query: HistoryQuery}`. HistoryQuery has `id`, `owner_id`,
`question`, `scope`, `snapshot:{server_id,watermark}`, `status` in
`pending,completed,partial,cancelled,invalidated`, `outcome` in
`unexamined,direct,inferred,conflicting,insufficient,no_evidence,unavailable`,
`created_at`, `updated_at`, `run` integer, `evaluator` immutable version manifest,
`budget`, `usage`, `coverage`, `answer`, `evaluations`, `next_offset` nullable,
`evaluation_count`, `prior_runs`, `error` nullable and `continuable` boolean.
The exact closed field shapes below extend these semantics.
`answer` consists of `excerpts` (original record identity, publication ID, exact
text or JSON serialization, and context identity), `support_ids`, `contradiction_ids`,
`uncertainty` and `assessment`; it never invents domain prose or overwrites facts.
Each evaluated group retains all originals needed for the joint interpretation,
question, resolved relationships, external snapshots and gaps. Complementary
attributes do not automatically contradict. Repeated reports do not establish
number of distinct referents. Explicitly requested wording cannot be replaced
by background knowledge. A correction is another assertion, not automatic truth.

Coverage records primary `total`, `examined`, `remaining`, evaluated group count,
expanded-context IDs/count, gaps/truncation, whether all primary records were
examined, and whether a final joint assessment completed. Full record coverage
alone does not certify truth or final answer completeness. `no_evidence` requires
all primary records examined and a completed final assessment with no support;
an empty scope has zero groups and no_evidence, with explicit empty-corpus
uncertainty. `conflicting` keeps both assertions; neither missing evidence nor
model error means false. Independent fixtures establish bounded model quality,
not universal correctness.

Budgets count examined primary records, reserved/attempted model calls, exact serialized
request bytes and elapsed active-run milliseconds. Never truncate originals
silently to fit a model. A group too large for the per-request byte limit is a
visible context gap and partial unavailable outcome; continuation with unchanged
request limit cannot pretend to fix it. Exhausted budgets checkpoint and set
partial with a reason and continuation. A failed/timeout/malformed model response
sets partial unavailable with an explicit retryable error, without marking that
group examined. `continue` extends a partial run under the same frozen evaluator;
configuration drift marks pending work invalidated and continuation requires
explicit `restart:true`. Restart retains the same corpus/snapshot/question,
clears prior judgments, adopts current evaluator and preserves prior run records.
Cancellation is terminal except explicit restart, which creates a new run.

## Choice evaluator

Use the configured Nemotron SystemOne `choice` adapter independently of the
subscription `noul` relevance path. No free-text generation or keyword fallback.
POST history.url (default matcher.url) with `model`, `state` and `questions`.
State contains question and a group of complete public contextual originals.
Questions include `assessment:{type:"choice",criteria:{direct:description,inferred:description,
conflicting:description,insufficient:description,no_evidence:description},instructions:...}` and
`answer:{type:"choice",criteria:{unknown:description,conflict:description,joint:description,...quoted records},instructions:...}`.
The answer choices select original excerpts; joint interpretation always cites
all members of the evaluated group, including necessary complementary assertions. Even groups previously judged
insufficient remain available to joint evaluation; relevance is not an ingestion
or per-record exclusion gate.
The final aggregation re-evaluates all participating originals jointly within
the same byte bound. Earlier group judgments remain auditable and never replace
original evidence or become an exclusion gate. If that cannot fit, retain partial evidence
and explicit aggregation gap rather than claim a complete synthesized answer.

Response requires exact configured model and `answers` for every asked question.
Optional `usage`, `metrics` and `scoring` objects are provider telemetry, ignored
for interpretation and subject to the whole-response byte bound. Other top-level
keys and unexpected answer keys are errors. Each answer is
`{type:"choice",choice:<one offered label>,probabilities:<map of all labels>,confidence:<selected probability>}`.
Confidence must equal the selected probability within 0.00001.
Probabilities are finite numbers 0..1, sum within 0.00001 of 1, selected choice has
maximum probability (ties allowed). Unexpected keys, missing choices, unknown
labels, wrong type/model or malformed JSON are evaluator errors. Require selected
probability >= history.min_confidence_ppm/1000000 for support; otherwise retain
uncertain insufficient assessment. `answer=unknown` overrides apparent direct
support; conflict keeps contradictory originals. Retain raw typed decisions,
request-byte SHA256, model/config/template identity and runtime cost per group.
Record corpus completeness separately from assessment confidence.

## Hot configuration and management

`history` is optional with defaults: enabled true, url/model null (inherit matcher),
operator_version "configured-model-v1", max_state_bytes33554432 (1048576..268435456),
timeout_ms3000 (100..30000), request_bytes6144 (1024..65536), records128,
calls64, bytes262144, time_ms30000, min_confidence_ppm500000,
context_depth2 (0..4), context_limit32 (1..64). The records/calls/bytes/time_ms
defaults live in a nested budget object. Operator version is a nonblank string
of at most128 bytes; advance it when changing provider weights behind the same
endpoint/model name. This is an operator assertion, not cryptographic model
attestation. URL/model can be cleared to null from Admin Settings to restore
inheritance. Record/call/byte/time defaults have
the request ranges above. All configuration is editable, validated and hot through
Admin Settings including URL/model changes; no new startup-only setting.
Evaluator identity hashes enabled, effective URL, model, operator version, template
identity, confidence and
context/request limits; changing timeout, default budgets or state byte limits
does not invalidate
judgments. API and Admin UI expose job list/detail/cancel and coverage/errors.
Admins alone can inspect other owners' operational questions. Developer/Viewer
cannot inspect them through read-only overview or activity endpoints. All schemas,
OpenAPI operations, SDK examples and independent negative vectors must exactly
match the implemented contract before qualification.



The exact public object shapes, management integration and machine contracts are
in history/interface.md. Generic model template data is history/evaluator.md.

A request deadline shortened by the remaining active-time budget expires as
BUDGET_TIME; an evaluator timeout at its independently configured timeout remains
MODEL_ERROR. Millisecond deadline accounting permits one millisecond of clock
quantization tolerance. A budget can block the next complete request/group before
its numeric counter is fully spent; do not truncate that request to use a remainder.
