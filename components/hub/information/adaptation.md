---
name: Retrieval feedback and adaptation
summary: Reproducible query attempts, replay and qualified declarative index updates
kind: component
---
# Feedback, replay and index adaptation (SEARCH-003 and INDEX-001)

Persist an attempt on each query execution segment and final comparison. Include
owner, query_id, normalized question, authorized scope/snapshot identity and IDs,
view, mode, policy/evaluator/index versions, candidates with ranks/scores, examined
record/chunk coverage, source/context identities, support/contradiction evidence,
answer changes, missing IDs, fallback reasons, audit probability/population,
elapsed time and measured model usage. Never save credentials, raw HTTP errors,
private addressed payloads or executable model commands. Query attempts are
owner-only through query_attempts; admin gets metadata only. They are separate
from publications and cannot cause subscriptions or self-confirming search hits.

Comparison classifications are retrieval_gap when a completed scan finds useful
evidence absent from candidates; interpretation_gap when retrieved support was
misread; possible_archive_gap when completed evaluation finds no evidence;
inconclusive when scans/audits are partial, malformed or unavailable; and
no_regression when answers/evidence agree. These are provisional model-assisted
judgments, not unquestioned truth labels. Persist the actual evidence difference.
Normalize Unicode/case/whitespace for query grouping, but retain original question.
Generic token-overlap clusters can suggest related attempts without domain buckets.
Explain the grouping policy/version and never merge separate owner permissions.

query_replay evaluates the same frozen corpus, then records parent attempt and
version comparison. A new-corpus query must have a distinct identity/label and
cannot count as retrieval improvement caused by an index change. Include known
successes, no-evidence queries and sampled apparently successful queries in replay
cohorts. Persist independent fixture/adjudication labels separately when supplied;
model scan outputs alone do not prove correctness. Support retries and restarts
without duplicate attempts or subscription deliveries.

## Bounded declarative recipes

Configuration optionally accepts `adaptation` with only enabled (boolean, default
false), promotion (`review` default or `automatic`), recurrence (2..100 default 3),
min_training (1..100 default 2), min_heldout (1..100 default 2), min_regression
(1..100 default 2), min_recovery_ppm (1..1000000 default 100000),
max_regressions (0..100 default 0), max_size_bytes (1024..1073741824 default
104857600), max_candidates (1..10 default 3), cooldown_ms (1000..86400000
default 60000), and max_build_retries (0..10 default 3). Validate all supplied
fields. When enabled, use recurring completed retrieval-gap clusters to propose
supported recipes; repeated fallback alone is not a defect diagnosis.

A recipe accepts only context_depth (0..4), chunk_bytes (256..8192), bigrams
(boolean), and semantic_pool (1..1000). These select already supported capabilities,
never code, SQL, filesystem paths or arbitrary model-generated scripts. Diagnose
missing context, chunk boundaries, lexical ranking and limited semantic pool;
propose at most a bounded one-step improvement in the corresponding capability.
An interpretation/archive gap need not create an index. Canonical recipe and source
snapshot identities deduplicate proposals. Enforce cooldown, candidate cap, bounded
retries and resource limits; avoid rebuilding the same ineffective candidate.

Add confirmed idempotent admin operations:

- `propose_index`: optional recipe; returns `{index:MANIFEST}`. Without recipe,
  diagnose eligible failure clusters and propose a bounded recipe; NOT_READY if
  insufficient recurrence or evaluation cohorts. Explicit recipes may be built
  for inspection but cannot bypass qualification/promotion evidence.
- `qualify_index`: required index_id; schedule replay/evaluation of a built
  candidate; return `{index:MANIFEST}`. No in-memory fabricated metrics.
- `promote_index`: required index_id; promote only a qualified caught-up candidate.
- `rollback_index`: required index_id of a retained usable version; catch up and
  switch atomically, retaining the displaced version.
- `retire_index`: required index_id; refuse the active version with NOT_READY;
  discard only replaceable derived content, retaining manifest/evaluation evidence.

All accept exactly op, confirm:true, message_id, and their named optional/required
fields. Persist original mutation results across restart. Unknown ID is NOT_FOUND;
premature/failed qualification or unsafe retirement is NOT_READY. Propagate these
through stable admin 409 JSON errors. Admin indexes/read views display recipe,
state and evaluation counts/metrics with action confirmations identifying versions.

Lifecycle states: proposed, building, evaluating, ready, rejected, failed, active,
retired. Build asynchronously from immutable records with durable checkpoints;
all model/network work is outside the serialized writer. Record source watermark,
training, heldout and regression cohorts with disjoint IDs assigned deterministically
by stable attempt identity. Training includes failure examples; heldout examples
cannot be used to tune the proposal. Regression includes successful/no-evidence
and audit queries. Reject insufficient cohorts, inconclusive comparisons, no
measured heldout improvement, regressions above configured cap or resource limits.
Record sample sizes, recovered/missed evidence, support/contradiction changes,
candidate/current elapsed/call counts and size. Never claim unmeasured cost gains.

Qualified candidates must recover at least min_recovery_ppm of heldout missed
evidence and pass regression/resource gates; full coverage and privacy are hard
requirements. Use original saved snapshots for comparisons. Catch up current
publications and changed contexts before an atomic active-version switch; if
qualification context changes materially, rerun affected checks. Retain the previous
usable version for rollback. Review mode requires promote_index; automatic mode
promotes when all recorded gates pass without another human interaction. This
configuration is the operator's promotion policy, not permission to execute code.

Acceptance: reproduce a miss against stable corpus/config identities; distinguish
new evidence from improved retrieval; classify interpretation and partial-scan
failures; preserve feedback isolation and ownership. A repeated generic paraphrase
or context miss must produce a bounded candidate with measured heldout improvement;
a ranking-only remedy need not create a new capability. Reject negation/correction,
privacy, successful-query or resource regressions and insufficient evidence. Test
interrupt/restart, concurrent writes, catch-up, qualification, both promotion
modes, rollback and retirement without altering originals or delivery state.
