---
name: Feedback and replay wire interface
summary: Closed owned attempt, adjudication, cohort and paired replay messages
kind: component
---
# Profile1.6 feedback interface

All objects reject unknown keys. Strings and HTTP/JSON rules inherit protocol/spec.
Times are generated UTC RFC3339; digests lowercase SHA256 hex; counters nonnegative
safe JSON integers<=9007199254740991. IDs opaque nonblank<=128 bytes. Existing
HistoryScope/Input, HistoryBudget/Input, HistoryUsage, RetrievalRecipe/Input,
RetrievalEvaluator, History evaluator/answer, record/gap and Archive policy/sample/
coverage/usage/answer definitions keep their exact published meanings. RecipeInput
is a primitive partial patch, never an expression. Null and omission differ below.

## Commands

Agent operations require the authenticated owning agent. Optional common project_id
uses the existing single-project check; messageId actor-idempotency applies to
replay creation/continuation/cancellation and any explicit capture request.

| op | Required fields | Optional fields |
| --- | --- | --- |
| list_retrieval_attempts | none | classification,offset,limit |
| get_retrieval_attempt | attempt_id | none |
| replay_retrieval | attempt_id,candidate_recipe | baseline,corpus,limit,budget |
| get_retrieval_replay | query_id | run,offset,limit |
| continue_retrieval_replay | query_id | restart,budget |
| cancel_retrieval_replay | query_id | none |

classification is an observational/adjudicated diagnosis below. List offset0..1M
default0, limit1..64 default32; replay evidence page uses existing History page
bounds/defaults and262144-byte page cap. Baseline recorded|current defaultrecorded;
corpus frozen|current defaultfrozen. Replay limit1..64 default original limit;
budget HistoryBudgetInput, merged with FeedbackConfig budget per branch.
Restart boolean defaultfalse; it preserves frozen question/corpus/recipes but adopts
current policy/label and resets checkpoints. Only a new submission changes corpus.
Completed/cancelled/invalidated jobs require restarttrue. At most16 runs.

List result exactly {items,next_offset,status}; items FeedbackAttemptSummary,
next_offset nullable integer, status FeedbackStatus scoped to that agent. Get
attempt returns {attempt:FeedbackAttempt}. Replay operations return {query:ReplayQuery}.
Wrong-owner attempts/replays are NOT_FOUND, not an email/human-owner alias lookup.

Admin operations, requiring current Admin, expected_revision, actor-scoped
message_id and confirm:true for mutations:

- feedback_attempts: list fields above plus optional agent_id; same result.
- feedback_attempt: attempt_id; same get result.
- feedback_status: no extra fields; {status:FeedbackStatus} server-wide.
- feedback_cohorts: optional offset/limit; {items:[FeedbackCohort],next_offset}.
- feedback_clusters: optional offset/limit; {items:[FeedbackCluster],next_offset}.
- save_retrieval_label: attempt_id,expected_label_revision0..16,label; result
  {attempt_id,label:FeedbackLabel}. Label input exactly
  {expectation,support_ids,cohort,tags,note,confirmed}; expectation
  supported|conflicting|no_evidence; cohort training|held_out|regression;
  support_ids distinct original IDs max128; tags unique max2 of negation,correction;
  note0..2048 bytes; confirmed constanttrue. All fields required.
- replay_attempt: same replay creation fields; records explicit human requester,
  retains attempt's agent owner; {query:ReplayQuery}.
- retire_replay: query_id; terminal jobs only; {query:ReplayQuery}.

Existing Admin query_jobs adds kind replay; query_job/cancel_query_job return
{kind:"replay",query:ReplayQuery}. Paging/prior runs remain explicit. Human sessions
cannot send agent commands on behalf of another actor. No mutation changes roles,
agent ownership, original records or subscriptions.

## Attempts and labels

FeedbackStatus exactly {enabled,attempts,replays,active_replays,unrecorded_runs,
state_bytes,last_error}. Agent counts cover only that owner's accessible work;
state_bytes nullable for agents (server total Admin-only); last_error nullable
FeedbackError. No member/count detail about other owners is returned to an agent.

Observational diagnoses: successful_search_unchecked,successful_search_audited,
provisional_retrieval_gap,provisional_answer_difference,possible_archive_gap,
required_scan,index_unavailable,incomplete_comparison,unclassified. Adjudicated
diagnoses: confirmed_retrieval_gap,confirmed_context_assembly_gap,
confirmed_interpretation_gap,confirmed_supported_search,adjudicated_no_evidence,
incomplete_assessment. A classification filter accepts their union.

FeedbackAttemptSummary exactly {id,archive_query_id,plan_id,run,owner_id,project_id,
question,scope,snapshot,created_at,captured_at,status,mode,complete_required,
primary_count,primary_identity,evidence_identity,original_policy,recipe,
recipe_identity,candidates,answer,assessment,scan,audit,comparison,sample,path,
fallback_reasons,coverage,usage,diagnosis,adjudicated_diagnosis,label_revision,
cohort,exposed}.

status/mode are the original Archive run values. Scope/snapshot, original_policy,
sample/path/fallback/coverage/usage retain Archive meanings. recipe nullable complete
RetrievalRecipe; recipe_identity nullable digest: unavailable historical recipes
stay null. candidates max64 existing RetrievalCandidate values, not a gold list.
answer ArchiveAnswer. assessment nullable ArchiveAssessment; it describes all supplied originals.
scan/audit nullable FeedbackScanSummary. comparison nullable ArchiveComparison.
primary_count frozen count; primary_identity/evidence_identity bind frozen ordered
source/original-context identities and declared context policy. label_revision0..16,
cohort nullable enum; exposed boolean reports declared evaluation use, not truth.
adjudicated_diagnosis nullable enum, separate from observational diagnosis.

FeedbackScanSummary exactly {query_id,run,status,outcome,evaluator,primary_complete,
final_complete,examined,total,expanded_count,expanded_identity,gaps,truncated,usage,
error}. It compactly references the real History run. gaps max128; no unbounded
expanded-ID list or raw model responses are copied into attempts. Full evidence is
available through the owned Archive/History references and their explicit pages.
FeedbackAttempt extends summary with {labels,group_id}; labels max16 complete
FeedbackLabel versions; group_id opaque digest. List and cohort pages also stop at262144 bytes. An individually oversized row
returns RESOURCE_EXHAUSTED instead of a nonadvancing page cursor.

FeedbackLabel exactly {revision,expectation,support_ids,cohort,tags,note,confirmed,
actor_kind,actor_id,created_at,evidence_identity,identity}. revision1..16;
confirmed constanttrue; actor_kind human_session|legacy_token, actor_id opaque
principal identifier (legacy token never claims a named human). Expectation,
IDs/cohort/tags/note match input. identity binds assertion, actor, revision and
frozen evidence. No raw session, password, agent token, peer credential or OIDC
secret enters feedback/model input.

FeedbackCohort Admin-only exactly {id,cohort,attempt_ids,owners,groups,observations,
plans,exposed,exposures}. Distinct member IDs/owners are bounded by max_attempts;
groups counts independent joined groups, observations run records, plans independent
Archive plans. exposures max256 entries {job_id,kind,recipe_identity,policy_identity,
created_at}, kind replay|optimization. Exposure persists across label/cohort changes,
failed/cancelled work and replay retirement. Joined members cannot claim different
cohorts. Exhausted exposure metadata fails new growth explicitly.

FeedbackCluster Admin-only exactly {id,diagnosis,recipe_identity,policy_identity,
context_complete,observations,groups,plans,attempt_ids,owners}. id digest binds the
cluster key: diagnosis (latest adjudicated diagnosis when available, otherwise
observational), nullable recorded recipe identity, original Archive policy identity
and context_complete. The latter requires an actual complete original candidate
assessment with no blocking gap; a full fallback cannot hide incomplete candidate
assembly. observations counts runs, groups counts distinct joined independent
cohort groups, plans counts distinct Archive plans. Membership/owner lists bounded
by max_attempts; clusters sorted descending observations, then ID. Compute from a
consistent feedback snapshot outside Store and fence label/exposure/capture changes
before returning. An oversized row returns RESOURCE_EXHAUSTED.

## Replay policy and branches

ReplayPolicy exactly {adapter_version,runtime,global_retrieval_identity,
baseline_evaluator,candidate_evaluator,history_evaluator,archive_policy_identity,
requires_complete,identity}. Evaluators are exact existing descriptors, with branch
recipe identities and effective private URL bindings in their identity hashes.
No URL is exposed. Runtime binds native normalization. Completeness/policy changes
fence pending work; timeout/default budgets/state caps do not reinterpret judgments.

ReplayBranch exactly {status,phase,recipe,recipe_identity,indexed,total,
input_manifest_identity,candidates,assessment,scan,coverage,answer,usage,comparison_usage,native_bytes,
metrics,error}. status pending/completed/partial/cancelled/invalidated; phase
building,ranking,scoring,assessing,scanning,done. recipe complete; input manifest
nullable until prepared; candidates max64; assessment nullable ArchiveAssessment;
scan nullable HistoryQuery summary. Child reference is separately pinned below.
Coverage exactly {primary_count,indexed,semantic_examined,returned_ids,assessed_ids,
expanded_ids,gaps,truncated,primary_complete,final_complete,answer_scope}; ID lists
max128 except returned_ids max64; answer_scope unexamined,candidate_only,
partial_scope,full_scope. Preserve actual limits/gaps; no root is called examined
merely because ranking saw it. answer ArchiveAnswer; usage HistoryUsage;
native_bytes is the Erlang external serialized size of isolated native rows,
retained as an observation after retirement; it excludes query bookkeeping and
HTTP request bytes. comparison_usage
is HistoryUsage for the current experiment, accumulating paid continuations since
the last explicit restart (its cumulative fields equal those totals). Branch usage
keeps current-run and lifetime cumulative counters. Comparison cost deltas use
comparison_usage, so a carried completed baseline is never represented as free.

ReplayMetrics exactly {eligible,reason,expected_gold,retrieved_gold,
retrieval_recall_ppm,answer_pass,false_support,fallback,full_scope}. Counts and ppm
nullable without an eligible label/comparison. expected_gold/retrieved_gold count
confirmed original IDs, never model support_ids treated as individual labels.
answer_pass/false_support nullable booleans; fallback/full_scope actual booleans.
reason nullable enum unlabeled,changed_corpus,incomplete,retired,policy_changed,
label_changed,missing_originals. Ineligible observations cannot qualify promotion.

ReplayComparison exactly {eligible,reason,retrieval_gain_ppm,answer_regressions,
false_supports,fallback_delta,calls_delta,bytes_delta,time_ms_delta,native_bytes_delta,
provisional}. Gain/deltas nullable signed safe integers; regressions/counts nullable
nonnegative integers. Gain is candidate minus baseline recall under the same gold.
Cost deltas are actual candidate minus baseline, not estimated charges. provisional
constanttrue: labels are asserted and interpretations fallible. No changed-corpus
row receives index-improvement credit.

## Replay job and evaluations

ReplayQuery exactly {id,owner_id,requester_kind,requester_id,attempt_id,question,
project_id,scope,snapshot,original_snapshot,corpus,baseline_origin,created_at,
updated_at,status,phase,run,policy,budget,usage,label,label_revision,baseline,
candidate,children,comparison,evaluations,evaluation_count,next_offset,prior_runs,
evidence_available,error,continuable}.
requester_kind agent|human_session|legacy_token|optimization; requester_id actual opaque actor (or parent proposal ID for internal optimization).
corpus frozen|current, baseline_origin recorded|current. phase baseline|candidate|done.
Policy ReplayPolicy; budget HistoryBudget per branch; usage exactly
{baseline:HistoryUsage,candidate:HistoryUsage,total:HistoryUsage}. Totals sum counters;
cumulative counts cannot be smaller than a run. label nullable captured FeedbackLabel;
label_revision0..16. Children exactly {baseline,candidate}, each nullable
{query_id,run,last_status}; cached scan views must bind owner/question/scope/snapshot
and expected run. Completed/cancelled snapshots can preserve earlier partial cached
views while last_status records parent cancellation of abandoned work.

Direct evaluation is either existing RetrievalEvaluation extended with required
{branch,stage:"retrieval"}, or Archive assessment evaluation extended with required
{branch}; branch baseline|candidate. Preserve exact request_json/digest/bytes,
model response, original IDs/context identities, fragments and private-manifest
binding. Use recorded request templates for historical evidence. Current external
requests still validate against current typed templates. No arbitrary model text.

Evaluation_count original total; page is at most64 rows/262144 bytes. Retirement
returns no raw rows/next_offset and evidence_availablefalse while preserving that
count and metrics. Prior_runs max15 sorted earlier integers; continuable false when
retired or at run16, otherwise existing restart semantics. Label/exposure and costs
are not rerolled on continuation. Error nullable FeedbackError.

FeedbackError exactly {code,message,retryable}, message credential-free<=256.
Codes BASELINE_UNAVAILABLE,OWNER_REMOVED,CHILD_CHANGED,POLICY_CHANGED,LABEL_CHANGED,
HELD_OUT_EXPOSED,COHORT_CONFLICT,MISSING_ORIGINALS,RETRIEVAL_DISABLED,SCAN_DISABLED,
CONTEXT_LIMIT,MODEL_ERROR,RESOURCE_LIMIT,WORKER_ERROR,CANCELLED,BUDGET_RECORDS,
BUDGET_CALLS,BUDGET_BYTES,BUDGET_TIME. Creation/validation/auth errors use existing
transport envelopes; an execution failure retains explicit stage/coverage.

Critical x-replayBindings binds parent/branch recipes, evaluator models, question,
child owner/scope/snapshot/run, label evidence and changed-corpus ineligibility;
x-replayUsage validates branch/total and cumulative counters. Earlier byte length,
SHA/JSON pairing, typed choice/noul distributions, original inputs/fragment spans
remain critical. Do not silently ignore annotations. Publish schemas/OpenAPI,
positive/semantic-negative examples and native/Docker/official-SDK/browser witnesses
in the same profile update before claiming SEARCH-003 complete.
