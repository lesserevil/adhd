---
name: Contextual candidate retrieval
summary: Replaceable native contextual indexes and bounded semantic candidate scoring
kind: component
---
# Contextual candidate retrieval

This additive profile 1.4.0 preserves wire major1, literal search, history scans,
subscription matching, original records and canonical-source routing. Candidate
retrieval accelerates local-archive questions; similarity never establishes support
or exhaustiveness. No additional model weights, embedding service or nonstandard
runtime dependency. The initial backend is versioned native BM25 plus separately
budgeted SystemOne noul usefulness judgments. Full support assessment still fetches
originals; query_history continues to evaluate the full frozen primary scope.

## Owned requests

Agent `retrieve` requires question (nonblank UTF8<=4096). Optional scope uses the
history scope/time/watermark contract, limit integer1..64 default8, and budget uses
HistoryBudgetInput with retrieval defaults. All filters AND; watermark cannot exceed
last-publication ingestion sequence. `get_retrieval` takes query_id and optional
run1..16, offset0..1000000, limit1..64 default16. `continue_retrieval` takes query_id,
optional budget and restart boolean defaultfalse. `cancel_retrieval` takes query_id.
Agent `retrieval_index` takes no extra fields and returns the nonsecret index status.
Unknown fields/types fail. Each mutation uses existing actor-scoped message identity;
identical retry returns original result, changed retry conflicts. Wrong owners get
NOT_FOUND, even if human owners share email. Admin has explicit read/cancel/index
management; human sessions never impersonate agents. Agent removal stops scheduling.

Submission freezes local server/project label, question, requested scope/watermark,
all selected primary publication IDs in ingestion order, limit, evaluator and
recipe/policy identity. Later publications and corrections cannot join that query.
Private messages, questions, model judgments, feedback and generated recipes never
join archive/index evidence or produce subscription deliveries. Canonical external
questions retain source_query; a local candidate is no remote ownership assertion.

States pending, completed, partial, cancelled, invalidated are separate from candidate
coverage. Completed means the declared bounded candidate plan ran, never that all
applicable evidence was found. Reports disclose full primary scope, indexed scope,
lexically ranked count, planned/examined semantic window and unexamined corpus.
No hit count, rank, score or confidence alone establishes answer sufficiency.

At most64 active pending/partial/invalidated and1024 total retained retrieval jobs,
16 runs per job. Separate state limits preserve originals under resource exhaustion.
Continue checkpoints the same frozen corpus, ranking and evaluator; explicit restart
retains corpus/question, clears judgments and adopts current settings. Archive prior
run views. Completed/cancelled/invalidated work requires restart. Preserve idempotent
history and literal APIs. Every result commit rechecks current run, nonce, owner
registration, status and evaluator/configuration identity. Cancel/configuration drift
fences late replies. Changing a default budget, timeout or state limit does not
invalidate judgments; changing effective model/URL/version, recipe, confidence or
request-fragment policy does. Completed historical results retain their old identity.

One separate retrieval scorer runs outside Store. At mostone retrieval model request
at once. When subscription matching is due, start at mostone retrieval call per
second; retain opportunities for both workloads and preserve the independent history
worker. Reserve calls/request bytes durably before HTTP. Resume abandoned reservations
with explicit uncertain_calls and conservative reserved timeout cost, never invented
provider charges. Valid decisions alone mark semantic records examined. Time counts
active ranking/assembly/inference, excluding idle queue time. A remaining-run deadline
shorter than provider timeout expires BUDGET_TIME (one-ms tolerance); independent
provider timeout remains MODEL_ERROR. Errors never become semantic nonmatches.

## Configuration

All fields hot and fully editable through structured Admin Settings. Optional
retrieval defaults: enabledtrue; url/modelnull inherit matcher dynamically;
operator_version="configured-model-v1" nonblank<=128; timeout_ms3000 (100..30000),
request_bytes6144 (1024..65536), min_confidence_ppm500000 (1..1000000),
max_index_bytes33554432 and max_query_bytes16777216 (each1048576..268435456),
max_records10000 (1..10000), build_batch8 (1..64), model_fragments4 (1..16).
Budget defaults records32,calls32,bytes262144,time_ms30000 with HistoryBudget ranges.
Clearing URL/model to null restores inheritance. Operator version is an operator
assertion, not an attested provider weight hash.

Recipe is a closed primitive object, defaults:
{tokenizer:"words",chunk_bytes:1024,context_depth:1,context_limit:8,
include_context:true,semantic:true,semantic_window:32,lexical_weight:1,
semantic_weight:2}. Tokenizer words or identifiers; chunk_bytes128..4096,
context_depth0..4, context_limit1..64, booleans exact, semantic_window1..128,
weights integer0..16 with positive total and positive semantic_weight when semantic
is true. No arbitrary source, SQL, executable expression or domain extraction field.
Recipe identity hashes {adapter_version,runtime,recipe} as defined in interface.md
using the directory
canonical JSON profile (only strings/integers/booleans). Model settings do not change
native index content. Index limits/batch/budgets apply live without erasing originals.
Recipe changes schedule isolated rebuild; old active version remains visible/stale
until a replacement catches up and atomically activates. Explicit Admin rebuild uses
confirmed actor-scoped product mutation identity; it does not change config revision.

## Qualification

The exact index and ranking contract is index.md; result/model/management shapes are
interface.md. Before closure publish schemas/OpenAPI/examples and independent SDK,
wire, real-model, browser and container evidence. Test exact IDs/paraphrases, Yes with
its question, negation as relevant evidence without a support claim, frozen replay,
index outages/limits, real interrupted builds, concurrent corrections, rebuild and
atomic switching. Index failures never reject an otherwise valid durable publication,
change original content, or consume/duplicate acknowledgements and deliveries.
