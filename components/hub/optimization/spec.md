---
name: Bounded adaptive index qualification
summary: Generate native recipe neighbors from confirmed misses and qualify a frozen winner
kind: component
---
# Authority and defaults

INDEX-001 builds on feedback/spec.md, feedback/replay.md, retrieval/spec.md and
retrieval/index.md. Generate only existing validated RetrievalRecipe primitives.
No executable expressions, SQL, entity schema, embeddings, new weights, free-text
model or confidence reduction. An unavailable index or interpretation/model error
is an operational failure, not sufficient reason for a new recipe.

OptimizationConfig defaults: enabledfalse, mode review, max_state_bytes33554432,
max_proposals64, max_active_proposals4, max_variants8, build_batch8,
recurrence_groups2, min_training_groups2, min_held_out_groups2,
min_regression_groups2, min_positive_training1, min_positive_held_out1,
min_no_evidence_controls1, min_negation_controls1, min_correction_controls1,
min_recall_gain_ppm1, max_total_calls_delta0, max_total_bytes_delta0,
max_native_growth_ppm2000000, cooldown_ms300000,
budget{records:16384,calls:512,bytes:16777216,time_ms:900000}.

All are hot structured Admin Settings. Mode review|automatic; bytes1MiB..256MiB;
retained proposals1..1024; active1..16<=retained; variants1..8; batch1..64;
all group/stratum thresholds1..64; recall gain1..1000000;
maximum total calls delta-100000..100000, bytes delta-268435456..268435456;
native growth1000000..8000000 ppm; cooldown1000..86400000ms.
Aggregate budget records1..1000000, calls1..100000, bytes1024..268435456,
time100..86400000ms. Each paired replay also obeys FeedbackConfig's current
per-branch budget. Model/time/byte work is actual, not counterfactual. State caps
include proposal records and private candidate generations; shared native index
capacity includes active, rollback, ordinary staging and optimizer candidates.
Shrinking caps preserves existing sources/proofs and permits bounded cancellation
or retirement. Disabled optimization rejects new work and pauses automatic work;
explicit cancellation/retirement, operator reset and rollback remain available
for recovery. New learned promotion requires optimization enabled.

## Recurrence and training

Only current registered agent owners' confirmed training attempts can anchor a
proposal. Use latest eligible attempt per joined independent cohort group. A
confirmed retrieval/context-assembly gap, complete frozen original membership and
recorded recipe are required for recurrence. Automatic triggers compare the actual
attempted runtime-bound recipe identity with the current effective recipe: old
remedied misses must not regenerate proposals forever. Count observations, distinct
plans and independent groups separately. Explicit proposals use their supplied
training IDs and still require recurrence/support counts and confirmed labels.

Capture primitive base hash, effective baseline recipe, selection revision,
interpretation/runtime identities, confirmed label versions, exact evidence and
cohort membership. Freeze training membership before model work. Group joins or
label changes affecting selected cases invalidate pending work; independent groups
cannot be split or counted twice. Empty negative scopes do not inflate support.
All training controls must meet their asserted answer expectation; model support_ids
are not individually relevant gold. Use the exact feedback paired replay over the
same frozen question/scope/mark and current policy, baseline current, corpus frozen.

Generate deterministic distinct neighbors, bounded by max_variants, in this order:
context_depth+1 (max4); enable context when disabled; double context_limit(max64);
halve chunk_bytes(min128); double chunk_bytes(max4096); other native tokenizer;
double semantic_window(max128); increase semantic_weight by1(max16) when semantic
is enabled. Validate full recipes; exclude unchanged/duplicate identities. A
ranking/window/weight-only change may reuse structurally identical rows: no native
row rebuild is necessary just to change scoring. Preserve reuse counts and actual
native cost. Never mutate the live recipe to run a candidate.

Evaluate all bounded training candidates. Reject incomplete, analysis-failed,
changed-corpus, retired or unlabeled comparisons. A winner must improve confirmed
original recall, pass all asserted answers, introduce no false support or answer
regression and meet aggregate calls/bytes limits. Rank by greater recall gain,
then fewer calls, fewer HTTP bytes, then recipe identity. Lower fallback alone is
not improvement. Native storage bounds still apply before promotion.

Freeze exactly one winner and its policy/recipe identity BEFORE selecting or
executing held-out content. If none qualifies, reject with NO_IMPROVEMENT or the
explicit dependency/budget/failure cause; do not rebuild indefinitely. A durable
signature binds baseline, interpretation, training groups/labels/evidence and
candidate set. Automatic generation respects cooldown and skips an existing
signature, including rejected/cancelled/retired jobs. Changed evidence/label/policy
may produce a new signature. No automatic retries of an unchanged failed model
experiment.

## Independent final evaluation

After freezing, enter awaiting_evaluation. An Admin supplies distinct confirmed
held_out/regression attempt IDs, or explicit automatic mode selects eligible
current groups after the freeze. Require configured independent group and stratum
counts. At least one held-out positive is required; negative controls must include
nonempty complete no_evidence scope, negation and correction assertions across
final cohorts. Do not inspect held-out model evidence to choose the winner.

Declare held-out exposure durably before any candidate execution, including failed
or cancelled work. Use proposal ID/kind optimization plus frozen winner/policy,
not a fresh per-replay ID, so only the same proposal/winner/policy can resume.
Respect feedback's stable semantic/source exposure keys across cohort changes and
merges. Already evaluated training/regression/unlabeled content cannot become fresh
held-out evidence by relabeling. Changed-corpus replay cannot qualify promotion.

Run fresh paired baseline/winner comparisons with actual full-History fallback on
all final groups. Require every comparison eligible and every expected answer pass,
zero false support and answer regressions, positive configured mean confirmed
retrieval recall gain and total calls/bytes deltas within limits. No evaluated case may lose confirmed original retrieval recall, including a
previously successful query, negation or correction control, even when fallback
preserves its final answer or the aggregate recall gain remains positive. Report independent counts and per-case recall,
answer correctness, full coverage, fallback, actual calls/bytes/time and native
bytes separately. Observed time is not an isolated speed guarantee. Human labels
and interpretations remain fallible; qualification is explicitly scoped evidence.

Then build/catch up a complete isolated global public index under the frozen
winner; qualify only if structural completeness, policy/evidence fences and native
storage ratio pass. Disclosure distinguishes case qualification watermarks from
current activation watermark; no quality claim covers future unexamined sources.

## Work and lifecycle

Admin controls only; agents continue their existing retrieval/Archive/replay APIs.
Internal Replay requester_kind optimization identifies its parent proposal and
never impersonates a human or agent transport. The original agent still owns each
replay; removed-owner commits fail visibly. Parent creation of a replay and its
expected-run reference is one Store transaction. Independent child continuation,
cancellation or missing raw evidence invalidates qualification.

Use the same shared Archive/replay analysis lane. Matching stays independent and
analysis starts total at mostone/second while matching is due. Native builds yield
bounded batches outside Store; exact state/base/selection/policy/owner/label/run
fences protect every commit. Persist cursors and uncertain leases through replay
semantics; count child cumulative deltas once, including unsuccessful work.

Statuses pending,awaiting_evaluation,qualified,promoted,rejected,partial,cancelled,
invalidated,retired; phases training,awaiting_evaluation,evaluating,building,ready,
done. Keep at most16 explicit continuation checkpoints. Partial budget/resource
work resumes only identical captured policy/evidence/base/selection and frozen
winner. Explicit retry_failed:true may restart a failed internal pair on the same
corpus/recipes/policy; preserve its prior runs and all aggregate actual charges.
Otherwise model failures never become successful comparisons by continuation.
Invalidated/cancelled/rejected work needs a new signature/proposal; it cannot
silently adopt new labels or re-credit spent held-out content.

Qualified review jobs wait for current Admin promotion. Automatic mode may promote
only while the current explicit mode and all current gates authorize it. No
qualifying labels, insufficient strata, stale policy, changed selection, incomplete
index or resource failure means no promotion. Keep explicit errors and remedies.
Retirement removes only inactive derived candidate/replay evidence, never originals,
deliveries, subscriptions, labels, exposure or selected/rollback generations.
Metrics/signatures/provenance remain, evidence_availablefalse cannot qualify anew.
