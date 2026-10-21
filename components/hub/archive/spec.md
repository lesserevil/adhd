---
name: Search then scan archive questions
summary: Owned frozen archive workflows with original-evidence sufficiency and sampled full-scope audits
kind: component
---
# Archive planning and fallback

Profile1.5 adds owned local archive workflows without changing literal search,
query_history, candidate retrieval, original records or canonical source_query.
One hub remains one project. Local archive results never assert remote source
ownership. Use source_query for canonical external questions. No new model weights,
free-text generation, embeddings, database extensions or domain columns.

Agent query_archive requires a nonblank question<=4096 UTF8 bytes. Mode is search,
scan or search_then_scan (default configured); optional scope is HistoryScopeInput,
complete boolean defaultfalse, limit1..64 default8, and per-stage budget. Freeze
question, original primary IDs, local server/project label, scope and ingestion
watermark at durable submission. Later records/corrections cannot join that run or
any continuation. All filters AND, inclusive microsecond event bounds. Private
messages, model judgments, attempt records and recipes never enter evidence/indexes
or emit subscription deliveries. Empty scope is explicitly completed no_evidence
with zero model calls and vacuously complete primary coverage, not a negative fact.

get_archive_query reads owned jobs and paged direct evaluations/prior runs.
continue_archive_query takes query_id, optional stage budget, restartfalse and mode;
changing mode requires restarttrue. Continue checkpoints the same frozen plan;
restart keeps question/corpus, adopts current policy and may change mode. Retain
16 runs,64 active pending/partial/invalidated jobs and1024 total. Completed,
cancelled or invalidated work requires explicit restart. Cancel fences direct
requests and cancels pending children. Wrong owners get NOT_FOUND independently
of email or human ownership. Admin has explicit job read/cancel; sessions never
impersonate an A2A agent. Product mutation identities remain actor scoped.

Execution status pending/completed/partial/cancelled/invalidated is separate from
semantic outcome, phase and scope coverage. A confident candidate answer can be
completed with candidate_only uncertainty; it never proves exhaustive evidence.
The explicit complete flag requires a full applicable original-scope evaluation.
For natural language, conservative intent planning assists but cannot certify all
possible languages/meanings. Callers requiring completeness must set complete:true.

## Plan and assess

Mode scan and complete:true require a full-scope History child; search-only instead
reports partial REQUIRES_SCAN when completeness is required. Exception: empty
scope is fully covered without scanning. Before a planner model call, tokenize the
question with the native words tokenizer and test these exact lowercase whole-word
conservative guards: absence, absent, all, comprehensive, correction, corrections,
count, counts, current, distinct, each, earliest, entire, entirety, every,
exhaustive, final, first, last, latest, least, max, maximum, min, minimum, most,
never, newest, no, none, oldest, total, totals, unique, without.
A hit only forces more evidence collection. It never matches/excludes records or
substitutes for relevance/support inference; false positives cost scans only.

Otherwise ask the configured short-response planner exactly one typed choice
intent with labels bounded,complete,unknown and the exact interface.md template.
Only a valid bounded selection at min_confidence_ppm permits candidate-only support
assessment. Unknown, low confidence, malformed/outage/timeout or context limits
require a scan in hybrid, or explicit partial in search mode. Expose raw choices
and the policy decision separately; never record a failed model as bounded intent.

Search creates a real Retrieval child using the same owner, question, frozen scope,
watermark, limit and retrieval-stage budget. Child creation and parent reference
persist in one Store transaction. Reject adoption of a child with another owner,
snapshot or run. Direct agent continuation/cancellation of an active child causes
CHILD_CHANGED rather than silently using independently authorized extra work.
Missing/stale/incomplete primary index, partial/error retrieval, zero candidates
or unavailable retrieval escalates to full scan in hybrid. Search-only reports the
actual failure/coverage. Similarity, rank, confidence and hit count never determine
answer sufficiency.

Fetch full candidate originals and bounded context at the parent's watermark using
its frozen History context policy. Deduplicate in original ingestion order. Do not
assess indexed fragments as complete originals. Model-input fragment truncation
alone does not establish original-record truncation; fetched unresolved context
gaps or bounds prevent sufficiency. Profile1.6 permits a cycle diagnostic only when
its target original is actually supplied; feedback/replay.md defines the refinement. At most128 original/context records in the support assessment;
apply the existing History request byte bound before HTTP. No silent truncation or
URL fetch. Use the exact HistoryEvaluator typed assessment/answer template, original
quote choices, finite distributions and confidence policy. Only confident direct
support, including a supported joint selection, is provisionally sufficient.
Inferred/insufficient/no-evidence/conflicting/failed assessment requires a full scan
in hybrid; search-only exposes partial uncertainty. Negation can support an explicit
negative answer; it never establishes a positive claim by similarity.

Full scan uses a real History child with original filters/watermark, complete:true
and scan budget. Never forge a restricted History primary_ids list or invent a
publication_ids input filter. Preserve History's full primary traversal, bounded
joint synthesis, context gaps, costs and partial/error semantics. A partial scan
cannot close a completeness requirement. Return source excerpts, contradictions
and uncertainty; absence of evidence is not falsehood. Prefer the full-scope result
when it disagrees with provisional candidate assessment, while recording both.

## Sample successful searches

Draw32 cryptographically random bytes for each execution plan before inference
and durably retain them privately. Budget continuations keep the same plan ID and
draw; only explicit restart creates a new plan/draw. Never reroll on mutation retry,
polling or process recovery. Report/sample independent plans rather than counting
continuations as independent audit trials.
Freeze audit_rate_ppm. Threshold=floor(rate_ppm*2^256/1000000); a uniform unsigned
256-bit draw below threshold is selected. Expose the exact rational probability
under this declared uniform256 model as decimal-string numerator/denominator.
The denominator is2^256. No floating-point or JSON unsafe-integer approximation.
Reveal draw_hex only when candidate support is provisionally sufficient, atomically
with eligible population/selection and audit scheduling. Until then it is null.

Only successful candidate answers are eligible. Report successful_search,
fallback_only,scan_only and undetermined populations separately. Selected audits
use a separate real History child on the full original scope and separate audit
budget. The provisional answer may be visible while phase auditing remains pending.
Full audit results can change the answer; disclose changed/unchanged observations
and source evidence. Failed/partial audits preserve explicit incomplete comparison;
they never establish equivalence, a negative label or a ground-truth search miss.
Cancelled selected audits remain selected in their recorded population.

## Durability and resources

One new analysis-model lane handles planner/support work outside Store; later
replay/optimizer work shares this lane. Preserve independent History/Retrieval and
subscription workers. While matching is due, start at mostone analysis call/second.
Reserve exact request bytes/calls and nonce/run/phase identity before HTTP. Recheck
owner registration, current policy, run, phase and nonce before committing. Settle
abandoned reservations with uncertain_calls and full reserved timeout cost; do not
invent provider charges. Queue idle time is excluded; assembly/inference active
time counts. Budget-limited timeout is BUDGET_TIME, independent timeout MODEL_ERROR.

Stages planner,retrieval,assessment,scan,audit have separate HistoryBudget bounds.
Charge child per-run/cumulative deltas once; polling never double charges. Parent
continuation records child baseline counters and expected run. Cancel/configuration
invalidation fences and cancels active children. Record child work already consumed,
even when a result is discarded. Dedicated state limits reject new growth and
preserve originals. Heavy context assembly, ranking and serialization remain outside
Store. Unexpected worker failures are explicit partial WORKER_ERROR, never nonmatch.

All archive fields are hot and structured Admin Settings. Defaults: enabledtrue,
default_mode search_then_scan; planner url/modelnull inherit effective History
URL/model; operator_version configured-model-v1; timeout_ms3000 (100..30000),
request_bytes6144 (1024..65536), min_confidence_ppm500000 (1..1000000),
max_state_bytes33554432 (1048576..268435456), audit_rate_ppm100000 (0..1000000).
Budget defaults: planner {records:1,calls:1,bytes:16384,time_ms:3000}; retrieval
{records:32,calls:32,bytes:262144,time_ms:30000}; assessment
{records:128,calls:1,bytes:65536,time_ms:30000}; scan and audit
{records:128,calls:64,bytes:262144,time_ms:30000}. Each stage is fully configurable.
History enablement controls History child availability; Archive support assessment
is its own operation using History evaluator settings. Retrieval disabled can still
fall back to an enabled scan. Disabled dependencies remain explicit, never ignored.

Policy identity binds implementation/template/guard versions, effective private
planner binding, confidence/request policy, actual mode/completeness, audit rate,
and effective Retrieval/History descriptors. Default budgets, timeout and state
limits do not invalidate valid judgments. Semantic policy/evidence changes invalidate
pending work; explicit restart adopts them. Default mode changes apply to future
submission; an existing run keeps its requested mode. Historical completed runs and
audit decisions retain old identities. Operator versions are assertions, not provider
weight attestations.

Qualification must bind exact schemas/OpenAPI/examples, independent SDK, real-model
held-out policy/support cases, desktop/mobile controls and native/Docker interruption,
privacy, concurrent correction, child interference, budget and sampled-hidden-miss
evidence. Keep SEARCH-003 and INDEX-001 gates separate until replay/promotion qualify.

Profile1.6 refines sufficiency to archive-sufficiency-v2 as specified in
feedback/replay.md: closed cycle diagnostics whose targets are supplied originals
remain visible but do not represent missing context. Preserve every actual
unresolved/depth/limit/request bound and historical completed run.
