---
name: History job interface
summary: Closed query result shapes and hot Admin management integration
kind: component
---
# History job interface

This closes the public shapes and management extension of history/spec.md.

## Exact public job shapes

All field names in this section are required unless explicitly nullable. Do not
return internal credential/configuration objects or endpoint URLs. Strings use
UTF8 byte bounds; integers exclude JSON booleans and fractional/exponent tokens
where the base integer-token profile requires that. Public counts are nonnegative
integers <=9007199254740991. IDs retain the base publication/agent ID limits.
Unknown object fields are invalid. JSON Schema/OpenAPI publish these same shapes.

HistoryQuery additionally has project_id (the project label frozen at submission)
and complete (the original requested boolean). scope contains only the submitted
filters except watermark plus kind="local_archive". snapshot carries the stable
server UUID and last-publication watermark. Preserve this label/snapshot across
project renames; freeze request metadata independently of mutable display labels.
A completed scan examines the full selected primary scope whether complete was
requested or not. That flag also constrains later search-then-scan composition.

budget is exactly {records,calls,bytes,time_ms} with the request ranges above.
usage is exactly {records,calls,bytes,time_ms,uncertain_calls,cumulative_records,
cumulative_calls,cumulative_bytes,cumulative_time_ms,cumulative_uncertain_calls}.
Records count newly examined primary IDs; calls/bytes include reserved HTTP
attempts even when the provider fails. Time counts active assembly/inference work,
not idle queue time. Failed or malformed groups do not become examined because
a request was attempted. Low-confidence valid decisions can mark coverage examined
but must retain uncertain insufficient interpretation. Conservatively settled
abandoned calls are distinguished from measured completed work by uncertain_calls.

coverage is exactly {total,examined,remaining,groups,expanded_ids,gaps,truncated,
primary_complete,final_complete}. expanded_ids are distinct expanded public IDs
outside the primary filters, in ingestion order (max10000); report truncation if
that cap is reached. gaps use the evidence/spec.md GAP shape (max128); truncated
is true if any context/group evidence was bounded. Evaluation pagination uses
next_offset and does not itself reduce corpus coverage. Primary coverage and
final joint assessment are separate booleans. Full primary coverage cannot imply
external snapshot availability or complete world knowledge. Gaps/uncertainty stay
visible even when a bounded local-archive scan completes.

answer is exactly {assessment,selection,excerpts,support_ids,contradiction_ids,
uncertainty}. assessment uses the outcome enumeration. selection is null or a
chosen offered answer label. excerpts is an array (max128) of closed objects
{publication_id,identity,context_identity,field,value}; field is text or data,
value is the full original text field or JSON serialization of its original data.
No generated factual prose is an excerpt. identity/context_identity use the
contextual record shapes. support_ids and contradiction_ids are distinct public
publication ID arrays (max10000). For direct/inferred/conflicting decisions retain
all jointly evaluated originals as citations, not merely the selected answer quote.
uncertainty is a distinct array of labels from empty_corpus, incomplete_primary,
context_gaps, low_confidence, interpretation_disagreement, background_inference,
model_error, aggregation_limit, resource_limit, configuration_changed and cancelled. A no_evidence model
judgment describes lack of support for the requested fact; it never asserts the
fact is false. The unknown answer overrides an apparently direct assessment.

Each evaluation is exactly {stage,primary_ids,record_ids,context_identities,request,request_json,
request_sha256,answers,bytes,time_ms,gaps,truncated}. stage is group or synthesis;
IDs and context identities correspond in the same ingestion-ordered record list.
request is the exact parsed SystemOne request actually serialized for that call;
request_json is the exact serialized UTF8 body (max65536 bytes), and request_sha256
hashes those bytes. Decoding request_json must equal request. Retain those bytes
so a later JSON encoder change cannot alter reconstruction.
answers contains the exact validated assessment/answer typed decisions. This
owner/Admin-only operational evidence never becomes a publication or delivery.
Evaluation pages begin at offset and include at most limit entries and262144
serialized UTF8 bytes; next_offset is the next integer offset or null at the end.
Do not silently omit an oversized entry: expose resource_limit and retain the
entry for inspection under a suitable later bound. evaluation_count is total
retained evaluations; prior_runs is the distinct prior run-number array (max15).
Continue/restart archives the previous run view; an explicit get run selects it.
Continuation retains completed groups on the same frozen corpus/evaluator; restart
clears judgments and re-evaluates that same corpus with current evaluator settings.

error is null or {code,message,retryable}. Codes are BUDGET_RECORDS, BUDGET_CALLS,
BUDGET_BYTES, BUDGET_TIME, CONTEXT_LIMIT, FINAL_LIMIT, MODEL_ERROR, CONFIG_CHANGED,
RESOURCE_LIMIT and CANCELLED. Messages are nonblank <=256 bytes and contain no
credentials or provider exception bodies. A pending invalidated job becomes
invalidated with CONFIG_CHANGED; explicit restart is required. Model failure is
partial/unavailable with MODEL_ERROR and no false no_evidence result. Cancelled
jobs retain prior coverage/evidence and cannot be resurrected by a late result.
continuable is true only for partial/cancelled/invalidated work with a remaining
run slot; nonretryable context/final bounds require explicit restart after changing
bounds or a smaller new scope, rather than repeating an unchanged failure forever.

The initial adapter bounds every model group to64 records and final joint input
to128 records plus the request byte bound. Exceeding these bounds yields explicit
partial/unavailable CONTEXT_LIMIT or FINAL_LIMIT, not a silently sampled answer.
Preserve completed evaluations for inspection. Never claim a complete answer
because all primary records were visited if final aggregation did not complete.
Cap serialized history operational state by max_state_bytes independently of
original publications. Refuse new work before overflow, reserving65536 bytes for
terminal/error checkpoints; if an evaluation would exceed the remaining capacity,
retain prior durable work, reserved cost and explicit RESOURCE_LIMIT. Ingestion,
subscriptions and original evidence are not deleted or blocked by index/history
state exhaustion. Operators may raise the hot state limit and explicitly continue.

## Admin integration and machine contracts

Extend existing Admin query_jobs kind filtering/results and query_job /
cancel_query_job to kind history. query_job accepts optional run, offset and
limit with the history get bounds; reject these extra fields for other job kinds.
History entries in query_jobs contain the complete job summary with an empty
evaluation page and next_offset0 when evaluations exist; query_job supplies
the owner-authorized evidence pages. Activity supports inspecting those pages. Admin read/cancel uses the same confirmed,
actor-scoped idempotent management interface. Developer/Viewer cannot inspect
other owners' history via Activity, overview or management reads. Activity labels
these as query jobs, shows source/discovery/history kind, coverage and errors,
and offers cancellation while pending. History configuration has structured
Admin controls, including clearing evaluator URL/model to inheritance. Preserve
all existing source/discovery job behavior and existing credential/role boundaries.

The exact generic prompt and criterion strings are history/evaluator.md. Publish
HistoryQuery, HistoryScope, HistoryBudget, HistoryConfig, HistoryModelRequest,
HistoryModelResponse and per-operation command/result schemas, profile 1.3.0
OpenAPI, positive/negative examples and independent conformance. Model URL is
private configuration; public evaluator is exactly {adapter_version,
operator_version,model,template_sha256,identity,policy}, with lowercase SHA256 identities. policy is exactly {enabled,request_bytes,
context_depth,context_limit,min_confidence_ppm}, frozen at submission/restart.
HTTP telemetry fields are ignored for semantic authority. The deployed provider
context limit can reject a byte-valid request; expose MODEL_ERROR without hidden
compaction, truncation, taxonomy extraction or keyword substitution.

The semantic schema annotations x-choiceDistribution, x-choiceExchange, x-historyChoices,
x-orderedTimes and x-jsonOf
are critical profile constraints. x-choiceDistribution validates finite [0,1]
probabilities summing to1 within0.00001, a maximum-probability offered selection
and matching confidence. x-choiceExchange checks response model, question IDs
and probability keys against the paired request. x-jsonOf maps a UTF8 JSON string
field to its equal parsed sibling object, rejecting duplicate keys and nonfinite
numbers; x-sha256Of then binds the exact string bytes as in the evidence profile.

x-historyChoices requires exactly quote_0 through quote_(N-1) plus the three
fixed criteria for N records. Each quote criterion has the normative prefix and
the complete original text; a data quote parses as JSON equal to original data.
x-orderedTimes checks supplied occurrence bounds in chronological instant order.

HistoryRecordedModelRequest preserves the same closed model/state/questions shape
but retains original instruction and criterion strings across template upgrades,
without imposing today's template text on archived evidence. HistoryEvaluation
uses that recorded shape. HistoryModelRequest separately constrains current
outbound requests to the normative template. A recorded exchange still validates
model/question/choice correspondence and complete probability distributions.
