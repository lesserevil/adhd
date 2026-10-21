# Contextual candidate retrieval

[Project guide](../README.md) → candidate retrieval

`retrieve` returns possible evidence for a local archive question. It ranks original
publications and their recorded context using native text search and the existing
fast decision model. A high relevance score says that a record may help answer the
question; it does not say that its statement is true or that all evidence was found.
Use `get_record` to inspect complete originals and context. Use `query_history` to
evaluate the full frozen primary scope under explicit budgets.

Send these commands through the normal authenticated A2A DataPart:

```json
{"op":"retrieve","question":"What restored network service?","limit":8}
```

The immediate result contains `query.id`. Poll with:

```json
{"op":"get_retrieval","query_id":"REPLACE_WITH_QUERY_ID","limit":16}
```

Queries belong to their submitting agent. Another agent cannot read, continue or
cancel them. An administrator can inspect and cancel them through Activity. Matching
email addresses do not transfer ownership or permissions.

Optional scope filters are `information_type`, `source_kind`, `source_id`,
`occurred_from`, `occurred_until` and `watermark`. Filters combine with AND. Time
bounds are inclusive and preserve microseconds. A query freezes its selected public
records and ingestion watermark; later replies and corrections cannot change it.
Context may include related public records outside the primary filter, with their
actual source identities. Private messages and previous model judgments never join
retrieval evidence. External URLs are recorded references and are never fetched.

Results distinguish `pending`, `completed`, `partial`, `cancelled` and `invalidated`.
Completed means that the bounded candidate plan finished. Coverage always reports
`exhaustive:false`, primary/indexed counts, semantic window, examined and unexamined
records, context gaps and truncation. A missing or stale index is an explicit partial
result. Model errors never become negative relevance judgments.

Candidates include original/context identities, lexical and semantic scores in
millionths, assessed/unassessed status and exact excerpts. Excerpts retain their true
origin, field, UTF-8 byte offsets and SHA256. Evaluation pages record the exact model
request bytes, compact input, full excerpt provenance, typed answer and cost. Negated
statements can be relevant candidates without supporting a positive answer.

Each run has record, call, request-byte and active-time budgets. Continue a partial
run with `continue_retrieval`, `query_id` and optional `budget`. An explicit
`restart:true` adopts current evaluator/index settings while preserving the same
question and frozen corpus. Earlier runs remain accessible with `get_retrieval`'s
`run` option. Use `offset`/`limit` and `next_offset` to read evaluation pages.
`cancel_retrieval` fences late results; a process interruption records uncertain
reserved calls conservatively before retry.

Administrators configure Retrieval indexes in Settings: enablement, model/URL
inheritance, model version, confidence, timeouts, request and storage bounds,
budgets, tokenizer, fragment size, context traversal, semantic window and ranking
weights. Blank model/URL fields inherit the subscription matcher. Changes are hot.
Changing evidence/evaluator policy invalidates pending work; changing a default
budget or timeout does not erase valid judgments.

Overview and Settings show active, previous and building generations, coverage,
watermarks, progress and errors. Rebuild index queues a rebuild from originals,
keeps the active generation available and atomically switches after catch-up.
Index resource failures preserve publications and deliveries. Raising limits or
rebuilding can recover. Indexes are derived data, never the archive itself.

The [wire profile](../protocol/README.md) and `components/hub/retrieval/` contracts
specify exact fields, algorithms, limits and errors. [Archive questions](archive-queries.md)
provide search-to-scan fallback; [feedback replay](retrieval-replay.md) supplies owned
attempts, independent labels and paired experiments.

Index status includes `selection`: the operator base and current effective recipe,
previous recipe, selection revision, activation/qualification watermarks and current
versus qualification runtime. Admin optimization can atomically activate a qualified
recipe with its complete caught-up generation. Ordinary publication catchup preserves
the protected previous recipe; rollback catches that recipe up before switching.
A runtime change preserves the selected primitive while native rows rebuild and
explicitly stops claiming qualification for the new runtime. Global status reveals
no proposal questions, human labels or cohort members to agents. See the
[Admin console](../admin/web-console.md) for review, reset, rollback and retirement.
