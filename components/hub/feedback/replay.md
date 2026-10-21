---
name: Paired retrieval replay
summary: Fresh baseline and candidate execution over the same frozen original scope
kind: component
---
# Replay execution

Use the exact operations and shapes in interface.md. A replay compares two fully
specified native RetrievalRecipe values against one question/corpus and one current
model policy. It is not another source publication or an update to the live index.
Do not change global configuration to run an experiment. Use existing native row
construction, BM25, typed usefulness and full-original History assessment templates.

Creation takes an owned attempt and candidate_recipe (partial primitive patch),
baseline recorded|current defaultrecorded, corpus frozen|current defaultfrozen,
optional limit1..64 default original limit and HistoryBudget. Recorded baseline is
the actual saved search recipe; reject BASELINE_UNAVAILABLE if absent. Current
baseline explicitly freezes the actually effective live recipe at submission.
Merge candidate patch into the chosen complete baseline, validate all primitives
and reject arbitrary expressions/fields. Report baseline origin separately from
the original attempt's recipe/policy. Never relabel historical retry costs as a
fresh baseline observation.

Frozen corpus uses the original question, filters, project label, primary IDs and
server/watermark, excluding later records/corrections. Current corpus explicitly
freezes a new watermark and applicable primary IDs for BOTH branches. Report this
as changed_corpus, never an index-quality improvement and never silently transfer
old labels to new evidence. Keep original and replay snapshot identities visible.

Each branch uses equal budget caps, the same current Retrieval/History evaluator
settings and same completeness requirement. Retain an explicit requirement from
the original plan, current complete guards or explicit complete:true. Never weaken
original full-coverage intent. If current planning semantics differ so the original
bounded-intent judgment cannot be reused, conservatively require full scope.
No extra free-text/embedding model or background domain facts are introduced.

## Execute and account

Run baseline then candidate in one shared analysis lane. Native work builds
isolated rows in bounded yielded batches from the exact primary originals/context
at the replay watermark; it cannot pollute or activate the live index. Preserve
row/input manifests, recipe/runtime identities and actual original fragment spans.
Rank under the chosen recipe and score only its bounded semantic window. Record
all unassessed candidates explicitly rather than scoring them zero by inference.
Incomplete materialization/coverage cannot establish a negative label.

Fetch full originals and bounded History context for returned candidates; never
assess fragments as complete originals. Require complete original assembly, then
use the exact current HistoryEvaluator choice/quote exchange. Direct support is
provisionally sufficient only when completeness does not require scanning. Model
errors, insufficient/inferred/conflicting support, absent candidates, incomplete
context or exhaustive intent require a real full History child. Respect disabled
Retrieval/History dependencies explicitly.

Child creation and parent reference commit in one Store transaction. A child has
the original owner, same question, filters, full primary set, server/watermark and
complete:true. Never forge History primary_ids or publication_ids input filters.
Use equal configured scan budgets, capped by the parent branch's remaining budget.
If a remaining budget is below a valid child minimum, checkpoint the corresponding
budget error instead of starting invalid/unbounded work. Keep expected child run
and reject independent continuation/cancellation as CHILD_CHANGED. No public A2A
transport impersonation is used by Admin-created jobs.

Actual branch costs include native rows, semantic and original assessment work and
its real fallback child. Do not compare a cheap unanswered baseline with a complete
candidate and pretend it avoided answering work. Do not invent counterfactual
provider charges or borrow another run's historical latency. Charge calls/request
bytes before HTTP, monotonic active assembly/inference time and child usage deltas
once. Queue idle is excluded. Persist nonce/run/branch/stage/policy/owner leases;
settle an abandoned reservation once with uncertain_calls and its full timeout.
A full provider timeout is MODEL_ERROR; a budget-shortened wait is BUDGET_TIME.

Budget applies separately and equally to each branch, with a total equal to their
sum. Records counts processed native/semantic/support/scan work, not unique source
IDs; bytes counts actual HTTP bodies, not native index storage. Record native state
bytes separately. Default budget comes from FeedbackConfig; each run permits an
explicit override within existing HistoryBudget bounds. Resource/HTTP exceptions
are explicit partial states and never nonmatch. Matching-due analysis starts are
at mostone/second across Archive, replay and optimizer, not once per kind.

## Compare and continue

Capture the exact confirmed label revision if available. Report missing label,
changed-corpus label mismatch, incomplete branch or retired evidence as ineligible
comparison; never turn them into success/negative fixtures. Fresh baseline and
candidate interpretation policies are identical except their primitive recipes.
Report actual policies and operator versions; those are not provider-weight
attestations. Record direct interpretation/materialization failures across checkpoints of the
same experiment; continuation cannot turn a failed baseline into eligible quality
evidence. Explicit restart reruns both branches and resets that failure marker.
History CONTEXT_LIMIT/FINAL_LIMIT remains a context limit, not CHILD_CHANGED; a
non-restart continuation cannot bypass a child context limit.
Policy changes invalidate pending work; explicit restart adopts them
on the same frozen replay corpus. Label changes invalidate pending labeled work.

Measure confirmed original recall from actually returned candidate assessment
inputs, not all scored-window/context IDs, and never treat History support_ids as
individual gold relevance. Restrict gold scoring to confirmed original IDs in the
frozen allowed scope. Report each branch's retrieved gold/expected gold counts,
retrieval_recall_ppm, supported-answer pass, false support, fallback/full coverage,
actual calls/bytes/time, native bytes and branch/child failures. Supported labels
need confident direct support plus their required originals; conflict labels need
conflicting assessment and their originals; no_evidence accepts explicit no-support
(insufficient or no_evidence), never a positive answer. Full-scope requirements
still require complete primary/final evaluation.

A successful full scan can make baseline and candidate end-to-end answers both
correct while their retrieval recall and inference costs differ. Preserve both
metrics; lower fallback alone never establishes improvement. Observed timing is
not an isolated recipe-speed guarantee, especially on a warmed provider. Classify
missing retrieval, context assembly, interpretation, no-source-evidence and
incomplete/error comparisons separately. Current-corpus observations retain their
separate kind even when their answers improve.

Statuses pending/completed/partial/cancelled/invalidated;16 runs; continuation keeps
frozen inputs, recipes, current completed judgments, label/exposure and child refs.
Only explicit restart after completed/cancelled/invalidated adopts new policy and
resets branch checkpoints on that replay's same corpus. It does not recapture a
new current corpus. A new changed-corpus comparison requires a new submission.
Record prior runs and cumulative costs. Cancel fences direct leases, cancels active
children and settles consumed work. Revalidate owner registration on every commit;
removed-owner work becomes explicit partial OWNER_REMOVED and cannot commit results.

Admin retirement requires a terminal job and confirmation. Remove only heavy
native rows/direct evaluations and disclose evidence_availablefalse with original
evaluation counts and retained metrics. Apply to prior runs too. It may remove only internally created terminal History
children still at the exact owned referenced run and not referenced by another
parent; independently advanced/ordinary History jobs remain intact. Preserve the
cached summaries/counts and mark their raw evidence unavailable. Labels, exposure
history, source publications, Archive runs and deliveries remain untouched. Preserve recorded numeric metrics but mark comparison eligibility false/retired.
Retired raw evidence cannot satisfy a new qualification. Existing state/cap reductions
permit bounded cleanup even when new growth is prohibited.

## Closed-cycle policy refinement

Archive sufficiency policy archive-sufficiency-v2 distinguishes a traversal cycle
diagnostic from missing context. For assessment, a cycle gap is resolved ONLY when
its target ID is among the exact full original records supplied at the frozen
watermark. Preserve the gap in public diagnostics. It does not block sufficiency
or mark those complete inputs truncated. Every other gap, missing cycle target,
real depth/limit/request bound or gap-cap truncation still prevents sufficiency.
No duplicate records, future/private resolution or silent truncation is allowed.

The same rule applies to full-scan comparison completeness: primary/final coverage,
no error/truncation and no blocking gap; a cycle's target must be in the fully
examined primary/expanded original set. This refines the earlier conservative
all-gaps rule; it does not change the contextual-read wire shape or hide cycles.
Bind the new policy identity, invalidate pending old-policy Archive work and keep
completed historical runs readable. The real two-hop development probe must recover
retrieval and supported originals without reducing confidence/request bounds; fresh
independent held-out controls remain necessary for promotion.
