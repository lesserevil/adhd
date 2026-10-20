# Retrieval indexes and adaptation

[Project guide](../README.md) → retrieval operations

Original publications and context remain authoritative. Indexes, query results and
feedback are derived records. The single-writer DETS store retains job checkpoints,
versions and evidence. Query/index work runs outside the serialized writer; model
or index outages must not prevent ordinary publication and polling.

The administrator console's Activity view lists index manifests, index/query jobs,
coverage and recipe/evaluation details. Query job metadata does not expose private
questions or answers. Confirmed actions rebuild, propose, qualify, promote,
roll back or retire an index. Retiring the active index is rejected; retirement
never removes publications or evaluation history.

## Rebuild and inspect

An initial contextual index is built asynchronously. New publications and context
relationships schedule durable updates, including incoming corrections/replies.
`indexes`, `index_jobs` and `query_jobs` are administrator read operations with
optional `limit` (1..100). Existing administrator authentication applies.

`rebuild_index` rebuilds the current recipe from retained originals. Changing the
recipe creates a candidate that requires qualification. The old active version
remains available until the replacement catches up and switches atomically.
Incomplete coverage and stale indexes cause query fallback rather than silent
absence. Inspect pending/failed jobs and available disk space before retrying.

Administrator mutation commands require `confirm: true` and a fresh `message_id`.
Retry an uncertain response with the same identifier and identical command.
The successful original result is retained across restart. `NOT_READY` means a
prerequisite or qualification gate has not passed; it is not permission to bypass it.

## Feedback and qualification

Query attempts record question/snapshot identities, versions, ranked candidates,
scan evidence, audit probability, coverage, answer changes and measured work.
Only the submitting agent can retrieve attempt details. Internal feedback is not
published or included in evidence search or subscription matching.

A complete scan finding useful missed evidence records a `retrieval_gap`.
Interpretation mistakes, possible archive gaps and incomplete comparisons remain
separate. Scan judgments are provisional labels. Saved queries can be replayed
against the same frozen corpus; new publications must not masquerade as a better
index. Independent fixtures and held-out/regression cohorts remain necessary.

`propose_index` selects a bounded declarative improvement from recurring gaps, or
accepts an explicit `recipe`. Supported recipe fields are `context_depth` (0..4),
`chunk_bytes` (256..8192), `bigrams` (boolean) and `semantic_pool` (1..1000).
Recipes cannot execute code, SQL or arbitrary model commands.

`qualify_index` evaluates a built candidate using disjoint training, held-out and
regression attempt IDs. Successful and no-evidence cases help detect regressions.
Qualification reports sample sizes, recovered/missed evidence, regressions, measured
calls/latency and storage. Missing cohorts, inconclusive comparisons, inadequate
held-out recovery, regressions or resource limits prevent promotion.

`promote_index`, `rollback_index` and `retire_index` require `index_id` in addition
to confirmation/idempotency fields. Promotion requires recorded successful gates
and corpus catch-up. Rollback catches up a retained usable version before switching.
Keep a prior version until the new one has been observed under current traffic.

## Automatic policy

Adaptation is disabled by default. Enable it explicitly in private server config:

```json
{
  "adaptation": {
    "enabled": true,
    "promotion": "review",
    "recurrence": 3,
    "min_training": 2,
    "min_heldout": 2,
    "min_regression": 2,
    "min_recovery_ppm": 100000,
    "max_regressions": 0,
    "max_size_bytes": 104857600,
    "max_candidates": 3,
    "cooldown_ms": 60000,
    "max_build_retries": 3
  }
}
```

These values are defaults. Review mode leaves qualified candidates for an explicit
promotion action. `promotion: "automatic"` permits promotion only after the same
recorded gates and catch-up; it does not authorize executable recipe content.
Recurrence alone does not prove that an index is the right remedy. Context assembly,
chunking, ranking and semantic pool changes are distinct possible improvements.
Retries, candidate counts, resource limits and cooldown bound the work.

Back up the entire data directory (DETS and its `.journal` recovery file) offline before schema upgrades. Schema 3 preserves prior
publication, subscription, delivery/acknowledgement and source retry state while
adding query/index namespaces. Restore a pre-upgrade backup for an older-runtime
rollback. Index rebuild is not a replacement for a store backup. DETS full-state
transitions and scan-based processing remain prototype scaling limits.
