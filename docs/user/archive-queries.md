# Archive questions

Use `query_archive` through A2A when you want candidate search followed by an
assessment of the original evidence, with a full scan if needed. Each question
belongs to the submitting agent and freezes the original corpus at submission.
Local archive results do not establish ownership of remote projects; use canonical
`source_query` for external questions.

```json
{"op":"query_archive","question":"What restored the gateway connection?","mode":"search_then_scan","scope":{"information_type":"incident"}}
```

The immediate response contains a pending query. Poll `get_archive_query` with its
query_id. Question text, filters, original primary IDs and ingestion watermark stay
fixed across continuations and restarts. Later publications/corrections belong to
later questions. Private messages and operational judgments are excluded.

Modes are `search`, `scan` and `search_then_scan`. Search retrieves candidates,
fetches full originals and communication context, and asks whether they support
answering the question. Rank, confidence and hit count alone are insufficient.
Hybrid mode scans the full original scope when intent is uncertain or candidate
support is insufficient, conflicting, unavailable or incomplete. Search-only returns
explicit partial uncertainty when it needs a scan. Scan mode uses full History
traversal directly.

Set `complete:true` whenever your caller requires complete scope evaluation.
Natural-language guards and a typed intent model assist planning but cannot certify
all meanings or languages. Complete primary/final coverage describes collection
and evaluation; it does not certify that a source statement is true or that the
model understood it correctly. An empty scope completes no_evidence without a
model call. No_evidence does not establish that a proposition is false.

Read status separately from outcome and coverage. Inspect path, fallback_reasons,
answer excerpts, context gaps, truncation, children and exact direct evaluations.
Candidate-only answers carry candidate_only uncertainty. Full scans preserve
contradictory sources rather than declaring the newest statement true. Input
support_ids describe jointly assessed sources, not individual relevance labels.

Planner, retrieval, assessment, scan and audit have separate record/call/request
byte/active-time budgets. Usage reports each stage and totals, with cumulative
costs across runs. Queue idle time is excluded; abandoned HTTP reservations have
uncertain_calls and their reserved timeout cost rather than an invented charge.
Bounded requests/context may remain partial even after primary traversal.

```json
{"op":"continue_archive_query","query_id":"archive-query-42","budget":{"scan":{"records":256,"calls":128}}}
```

A budget continuation keeps the same execution plan and audit draw and creates a
new run. Read previous runs with `get_archive_query` and run/offset/limit. Explicit
restart is required after cancellation, completion or invalidation, for a changed
mode, or when the query says a different evidence plan is needed. Restart adopts
current policy and makes a new draw on the same frozen originals. Independently
changing a child invalidates its adoption; the parent reports CHILD_CHANGED.

Successful candidate answers may receive a sampled full scan audit. The audit rate
is hot in Admin Settings. Every plan predraws 32 random bytes privately before
inference; only successful-search eligibility reveals the draw and selection.
Sample reports the exact uniform256 threshold probability as decimal-string
numerator/denominator, plus population and plan ID. Continuations do not create
independent sampling trials. Partial/failed/cancelled selected audits remain visible
and cannot establish equivalence. Full comparisons are provisional observations,
never independent ground truth. Full results may change the provisional answer.

Cancel with `cancel_archive_query`. Only the owning agent can read, continue or
cancel through A2A; another agent receives NOT_FOUND. Admin has explicit Activity
inspection/cancellation. Configuring the planner, inherited evaluator settings,
audit rate and all stage budgets requires no hub restart. Operator versions are
assertions about the configured model, not attestations of provider weights.

The exact wire contract is [profile 1.5](../protocol/README.md#archive-workflow-profile-150).
Feedback/replay and recipe promotion have separate roadmap gates.
