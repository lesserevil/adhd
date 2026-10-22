---
name: Adaptive index wire interface
summary: Closed Admin proposal, evaluation, promotion, rollback and selection messages
kind: component
---
# Profile1.7

Inherit protocol/spec.md JSON, auth, byte/integer and closed-object rules. Digests
are lowercase SHA256; IDs nonblank<=128 bytes; generated times UTC RFC3339. Counts
are nonnegative safe JSON integers. Existing RetrievalRecipe/Input, HistoryUsage,
FeedbackLabel, ReplayMetrics/Comparison and index manifests preserve their meanings.
ReplayQuery requester_kind additionally permits optimization; requester_id is the
parent proposal ID. This is internal creation only; agent commands still cannot
supply requester or exposure fields.

All operations below require current Admin. Mutations require expected_revision,
actor-scoped message_id and confirm:true. Role and revision are rechecked inside
commit, not only before outside preparation. Public agents retain existing commands.

| op | Additional required fields | Optional fields |
| --- | --- | --- |
| optimization_status | none | none |
| index_proposals | none | status,offset,limit |
| index_proposal | proposal_id | offset,limit |
| propose_index | none | training_attempt_ids,budget |
| evaluate_index | proposal_id,held_out_attempt_ids,regression_attempt_ids | none |
| continue_index_proposal | proposal_id | budget,retry_failed |
| cancel_index_proposal | proposal_id | none |
| promote_index | proposal_id,expected_selection_revision | none |
| rollback_index | expected_selection_revision | budget |
| reset_index_selection | expected_selection_revision | none |
| retire_index_proposal | proposal_id | none |

Read offset0..1M default0, limit1..64 default16; case pages stop at262144 bytes.
Mutation common fields are absent from reads. Attempt lists distinct1..64 when
present; no implicit cross-owner agent delegation. Propose omitted training IDs
selects eligible confirmed training groups. Evaluation IDs explicitly select their
confirmed held_out/regression cohorts; empty lists are invalid. No hidden model
labeling or question text rewriting. retry_failed boolean defaultfalse. Budget is
OptimizationBudgetInput, merged with current config; a continuation replaces total
caps, never resets already paid aggregate work. At most16 continuations.

List result {items:[OptimizationProposalSummary],next_offset}; status result
{status:OptimizationStatus}; every proposal operation {proposal:OptimizationProposal}.
Reset result {selection:IndexSelectionView}; reset changes authoritative selection,
not the operator recipe. Copy-active-to-base is the existing config_update with
retrieval.recipe explicitly equal to the displayed effective recipe. It resets the
override even if the merged recipe values are unchanged. Admin query_jobs adds kind
optimization; query_job/cancel_query_job return that kind and proposal projection.

## Configuration and status

OptimizationConfig exactly the fields/defaults/ranges in spec.md, with budget a
complete OptimizationBudget. BudgetInput allows any subset of its four fields.
ConfigPatch permits nullable leaves and merge-patch deletion as existing configs;
full merged validation enforces active<=retained. All controls hot and structured.
Automatic mode can select cohorts and promote only while currently enabled and
explicitly automatic; a stale captured mode is never authorization.

OptimizationStatus exactly {enabled,mode,proposals,active,eligible_training_groups,
fresh_held_out_groups,regression_groups,last_proposal_at,last_error,selection,
state_bytes}. Last time/error nullable. Counts from independent joined groups,
not repeated plans/observations. State bytes includes proposal/private generation
state; selected/rollback capacity is additionally enforced by retrieval's shared
native bound. No raw questions or credentials in status.

IndexSelectionView exactly {revision,applied,base_identity,base_recipe,
effective_recipe,selected,previous,rollback_available,current_runtime,
qualification_current}. revision safe integer; applied boolean; recipes complete;
base_identity primitive canonical hash; runtime nonblank string. selected/previous
nullable IndexSelectionDescriptor. qualification_current true only when an applied
selection has recorded qualification for this exact runtime; operator selection
has no implied learned qualification. Global metadata exposes no cohort/question,
label or human identity to an agent.

IndexSelectionDescriptor exactly {recipe,base_identity,proposal_id,
qualification_runtime,qualification_identity,selected_at,activation_watermark,
qualification_watermark}. Nullable proposal/runtime/qualification identity for an
operator recipe. Watermarks bound the same persistent server; qualification_watermark is the
maximum evaluated case mark, not universal coverage through that mark. Previous describes
the rollback recipe; its native rows may require catchup before activation.

## Proposals and evidence

OptimizationProposalSummary exactly {id,operation,created_at,updated_at,
requester_kind,requester_id,status,phase,run,base_identity,selection_revision,
baseline_recipe,winner_identity,signature,training_groups,held_out_groups,
regression_groups,budget,usage,evaluation,build,evidence_available,error,continuable}.
operation optimize|rollback; requester_kind human_session|legacy_token|automatic;
requester_id actual human/legacy principal or literal optimizer for automatic work.
No raw credential is retained. Status/phase enums are those in spec.md; run1..16.
Baseline complete recipe; winner nullable recipe digest; signature digest binds
frozen training/baseline/policy/candidates. Group counts independent. usage
HistoryUsage records actual aggregate child/build work and cumulative counters;
budget OptimizationBudget. Comparison costs never omit unsuccessful/retried calls.

OptimizationProposal extends summary with {base_recipe,policy_identity,runtime,
training_attempt_ids,held_out_attempt_ids,regression_attempt_ids,variants,children,
cases,case_count,next_offset,index_manifest,watermark,global_evidence_available}.
Attempt lists distinct max64, variants max8; children max640; cases max64 per page,
case_count original total and next_offset nullable. index_manifest nullable exact
RetrievalIndexManifest; watermark nullable current global-build watermark. Native
rows are private, not in this projection. global_evidence_available discloses
whether the original isolated global generation is still available: moving it into
active and later catchup can replace that generation. This is separate from paired
raw evidence_available; neither unavailable evidence can satisfy a new gate.

OptimizationVariant exactly {recipe,recipe_identity,changes_index,status,summary,
error}. Status pending|evaluating|qualified|rejected; summary nullable
OptimizationEvaluation; error nullable OptimizationError. Changes_index compares
structural recipe fields (tokenizer/chunk/context depth/limit/include), excluding
ranking/window/weight-only changes. Never claim reused rows were rebuilt.

OptimizationCase exactly {attempt_id,group_id,cohort,label_revision,replay_id,run,
variant_identity,policy_identity,comparison,baseline,candidate,usage}. Cohort
training|held_out|regression; label revision1..16; run expected1..16; baseline and
candidate ReplayMetrics; comparison ReplayComparison. usage exactly
{baseline:HistoryUsage,candidate:HistoryUsage,total:HistoryUsage}. Gold IDs originate
from independent confirmed labels. Keep per-case original recall separate from
supported answer/full-scope/fallback metrics. Cases are fresh same-corpus pairs;
actual source watermarks remain available through the owned replay references.

OptimizationChild exactly {replay_id,run,attempt_id,cohort,variant_identity,
last_status}. Cached expected runs cannot be silently replaced by independently
advanced children. Internal replay creation and parent reference commit atomically.
Retirement preserves counts/numeric metrics while removing only eligible inactive
raw data; retired/changed-corpus/analysis-failed cases cannot qualify.

OptimizationEvaluation exactly {eligible,reason,cases,groups,positive_groups,
no_evidence_groups,negation_groups,correction_groups,mean_recall_gain_ppm,
answer_failures,answer_regressions,false_supports,total_calls_delta,
total_bytes_delta,total_time_ms_delta,baseline_native_bytes,candidate_native_bytes,
passed}. reason nullable OptimizationError code; counts safe; gain/cost deltas
nullable signed safe integers until actual eligible comparisons exist. Native
bytes nullable until built. passed true requires all configured support/quality/
resource gates, not merely a positive average. Zero false support, no answer regression and no per-case confirmed retrieval
recall loss are mandatory, including when average gain is positive. Record observed time but do not certify isolated speed.

OptimizationBuild exactly {status,indexed,total,processed,reused,watermark,
native_bytes,manifest_identity,error}; status unstarted|building|ready|partial|failed;
watermark/manifest identity nullable until prepared; actual counters safe. Full
public/source-context manifest, no excluded roots and current watermark required
for activation. Processed is actual constructed rows; reused counts native rows
carried without reconstruction. Neither count is model HTTP usage.

OptimizationError exactly {code,message,retryable}, credential-free message<=256.
Codes MIN_EVIDENCE,NO_IMPROVEMENT,HELD_OUT_EXPOSED,COHORT_CHANGED,LABEL_CHANGED,
POLICY_CHANGED,SELECTION_CHANGED,BASE_CHANGED,CHILD_CHANGED,OWNER_REMOVED,
INCOMPLETE_EVALUATION,QUALITY_REGRESSION,RESOURCE_LIMIT,BUDGET_RECORDS,BUDGET_CALLS,
BUDGET_BYTES,BUDGET_TIME,WORKER_ERROR,CANCELLED,INDEX_INCOMPLETE,
GENERATION_UNAVAILABLE,OPTIMIZATION_DISABLED,NO_PREVIOUS_SELECTION,MISSING_ORIGINALS,
MODEL_ERROR,RETRIEVAL_DISABLED,SCAN_DISABLED,CONTEXT_LIMIT.
Transport validation/auth/not-found/idempotency errors retain existing envelopes.

## Critical validation and qualification

x-optimizationBindings independently binds variant identities, frozen winner,
case/child expected run and cohort, baseline/current selection revision, policy and
eligibility; copied/retired/changed-corpus results cannot masquerade as fresh quality.
x-optimizationUsage validates actual child/build totals, cumulative bounds and
per-case aggregate quality/cost arithmetic. Unknown critical annotations fail closed.
Existing x-replayBindings/Usage and exact request/response/original annotations apply.

Publish schema/OpenAPI1.7, positive and semantic-negative fixtures and user/admin
operational docs together. Native and Docker witnesses must include repeated
context/paraphrase misses, a training-frozen winner and subsequently authored fresh
held-out positives/nonempty negative controls, negation/correction regression,
interruption/owner/policy/label/child/exposure fences, concurrent publication/context
catchup, atomic promotion/rollback, operator reset/crash recovery and derived-only
retirement. Ordinary coordination/federation/identity/configuration and source/data
preservation remain required gates. Model interpretations and human labels are
explicitly fallible; every quality claim states its evaluated scope/runtime.
