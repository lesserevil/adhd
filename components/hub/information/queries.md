---
name: Evidence queries
summary: Durable natural-language semantic scans and current-state answers
kind: component
---
# Evidence query jobs (QUERY-001 and INFO-003)

Add these A2A operations to CLI describe in sorted order and to the shared pure
validator. They use the existing authenticated project boundary. New mutations
use existing per-actor messageId idempotency, while reads return current state.
Unknown fields are invalid params. Query ownership is private to the submitting
agent; another agent receives FORBIDDEN for known foreign query/attempt IDs.

- `query`: required nonblank `question` (1..4096 UTF-8 bytes); optional `mode`
  (`scan`, `search`, `search_then_scan`, default search_then_scan), `view`
  (`current`, `history`, default current), `scope`, `budget`, `index_id`.
  Result `{query:QUERY}` after durable creation; inference is asynchronous.
- `query_status`: required `query_id`; result `{query:QUERY}`.
- `query_result`: required `query_id`; result `{query:QUERY,result:RESULT_OR_NULL}`.
  Partial/incomplete results are explicitly labeled; do not wait for inference.
- `query_continue`: required `query_id`; optional `budget`; resume a partial or
  failed job from its last committed checkpoint with additional resources, using
  the original frozen corpus. Terminal done/cancelled jobs return NOT_READY.
- `query_cancel`: required `query_id`; set cancelled atomically. An in-flight
  response cannot overwrite cancellation. Repeated cancellation succeeds.
- `query_attempts`: optional query_id and limit 1..100 default 50; returns
  `{attempts:[...]}` newest first for the caller only.
- `query_replay`: required query_id, optional index_id; create a new owned job
  against the exact prior frozen corpus/question/scope/view and selected index.
  Result includes `{query:QUERY,replay_of:ID}`. Never include later publications
  in same-snapshot replay; a fresh query is how to evaluate a newer corpus.

`scope` is an object with optional information_type, source_kind, source_id using
existing bounds, and occurred_from/occurred_to UTC-normalizable datetime strings.
All filters combine with AND. Reject reversed time bounds. Never confuse named
projects mentioned in text with the configured visibility project. At submission
freeze matching publication IDs, their content identities and current monotonic
ingestion watermark. Context traversal respects that frozen membership and
authorization. Empty scope means all project-public publications, never sends,
feedback, query answers or other internal records. Missing context remains a gap.

`budget` accepts only max_records (1..100000, default 1000), max_calls (1..10000,
default 100), and timeout_ms (100..300000, default 30000), bounding each invocation
segment, including continuation. Count context roots and distinct expanded
records explicitly. Stop at a checkpoint before exceeding a budget; expose
partial coverage and allow continuation. Batch deterministically, at most eight
records and 32768 encoded input bytes per model request. Oversized single records
must be processed in bounded chunks with span offsets; never silently truncate
source evidence. Persist chunk coverage, including remainder. Build a bounded
interim evidence summary with source IDs across batches so jointly useful records
can participate in synthesis. Do not use independent per-record classifications
to discard evidence necessary only in combination. Context gaps and over-budget
summaries cause explicit incompleteness rather than invented exhaustiveness.

QUERY exposes id, owner_id, question, scope, view, mode, status (pending, running,
partial, done, failed, cancelled), stage, created_at, snapshot_watermark,
snapshot_identity, total_records, examined_records, remaining_records,
context_gaps, calls, elapsed_ms, evaluator_version, policy_version, index_id,
execution_path, fallback_reasons and replay_of when applicable. Persist
checkpoints/attempts; recover running jobs as pending after restart. Serialize
short transitions only. All inference/network work runs outside the store writer.
Commit only when job generation/version and state still match. Query errors are
bounded generic codes; never retain raw exception bodies or provider credentials.

RESULT contains `outcome` (supported, no_evidence, conflicting, unknown), `answer`
(string at most 8192 bytes), `facts` (at most 100 `{statement,publication_ids}`
objects), `evidence` (at most 128 `{publication_id,excerpt,stance}` objects),
`uncertainties` (at most 100 strings), `requires_exhaustive` boolean,
`complete` boolean, and `coverage` with examined/total records, watermark and gaps.
Stance is supports, contradicts or context. Each evidence ID must belong to the
frozen authorized corpus and excerpt must be a literal nonempty span of its
text, encoded data, context question or context snapshot. Each fact must cite
nonempty IDs validated against that evidence. Reject invented citations/excerpts,
malformed output and unsupported positive facts; classify as failed/incomplete,
not no_evidence. Keep execution completeness separate from semantic outcome.
Full coverage is not a guarantee of model correctness. No-evidence does not mean
the proposition is false. Preserve contradictions and inference uncertainty.

## Evaluator adapter

Configuration optionally accepts `evaluator` with required `url` (absolute
http/https chat-completions URL) and `model` (nonblank, at most 256 bytes), optional
`api_key_env` (environment variable name), timeout_ms (100..300000, default 30000),
version (identifier, default chat-json-v1), max_output_tokens (256..16384,
default 4096), and context_depth (0..4, default 2). Reject unknown keys and invalid
configuration. Read the key only from the named process environment variable;
fail startup if named but unset. Never store/log/return it. HTTPS verifies peer
certificates. Limit response bytes to 1 MiB. No evaluator keeps legacy operation
valid; query jobs become failed with EVALUATOR_UNAVAILABLE, not fabricated answers.
Use a supplied external OpenAI-compatible service; do not execute coding-agent
tools from publication content or invoke shells to interpret reports.

POST the standard chat-completions shape `{model,messages:[{role:"system",
content:INSTRUCTIONS},{role:"user",content:JSON_CONTEXT}],temperature:0,
max_tokens:MAX,response_format:{type:"json_object"}}`; bearer authentication is
supplied only when api_key_env is configured. Read choices[0].message.content
as one strict JSON object. Missing/invalid choices, refusal, truncated finish
reason, bad schema, nonfinite values and HTTP errors fail the model step.
Reject Markdown fences and surrounding prose. Allow usage metadata, recording
only nonnegative integer token counts; do not parse prose as a successful answer.

JSON_CONTEXT includes question, view, scope, snapshot_watermark, stage
(plan, evaluate, synthesize, sufficiency), complete QUERY coverage, current batch
of complete PUBLICATIONs with chunk offsets when needed, prior validated interim
RESULT and index metadata where applicable. The system prompt requires the exact
RESULT fields above, grounded citations, source attribution, same-source temporal
supersession, independent activities, conflicting sources, context-aware synthesis
and explicit uncertainty. It declares every source string untrusted data and
forbids following source instructions. `plan` determines requires_exhaustive
semantically; count/all/exhaustive requests always require full evidence coverage.
An evaluation result cannot claim complete before all relevant chunks/records are
examined. Final synthesis sees retained validated evidence, chronology and coverage.
The server controls complete/status fields and validates citations in every phase.

The existing Nemotron noul worker remains solely a relevance classifier. It cannot
stand in for extraction/synthesis. Test the configured generative service on
independently labeled examples before claiming answer capability.

Acceptance includes linked Yes/question, jointly useful records, explicit color
versus inferred cardinal color, uncertain distinct-bird count, negation,
correction, concurrent writes with frozen scope, absent evidence, malformed or
invented model output, model outage, cancellation, budget exhaustion, continuation,
private query access, source isolation, idempotency and hard restart. Run an actual
configured evaluator separately from deterministic protocol/failure fixtures.
