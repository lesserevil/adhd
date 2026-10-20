---
name: Contextual retrieval
summary: Replaceable indexes and explicit search-to-scan query policy
kind: component
---
# Retrieval and fallback (SEARCH-001 and SEARCH-002)

Retain literal archive `search` unchanged. Query mode search uses a replaceable
general-purpose contextual index to select candidates, fetches original evidence,
then evaluates support with the generative evaluator. An index accelerates access;
it is never authoritative and never the only copy of evidence. No domain labels,
branch columns or predicted question taxonomy are required at ingestion.

Configuration optionally accepts `retrieval` with only candidate_limit (1..100,
default 20), semantic_pool (1..1000, default 100), context_depth (0..4, default 2),
chunk_bytes (256..8192, default 2048), bigrams (boolean, default false),
audit_ppm (integer 0..1000000, default 100000), and policy_version (identifier,
default search-scan-v1). Every supplied value is validated at startup. Use
standard runtime Unicode word tokenization, term frequencies and BM25-like
lexical ranking (k1=1.2, b=0.75), exact token boost, and deterministic ID/sequence
tie-breaking. Long text is chunked with byte offsets on UTF-8 boundaries and all
original bytes remain stored. Context includes question/referent and authorized
linked records, so “Yes” is not indexed alone. Manifest binds canonical recipe,
source/context identities, state, size_bytes, indexed_records, total_records,
indexed_through watermark, created_at and previous active version. Context changes
invalidate affected incoming/outgoing neighbors before active coverage is current.

Provide semantic candidate selection using the actual configured Nemotron
SystemOne relevance protocol, separately from truth evaluation. Rank an eligible
bounded pool of contextual chunks for whether they help answer the whole question,
including contradictions; pool selection combines lexical ranking with deterministic
coverage of other indexed chunks. Include zero-lexical candidates so paraphrases
can be discovered. Evaluate complete original/context text, question and chunk
identity. Use finite noul probability as a candidate relevance score, not truth;
retain it with lexical score and rank. Normalize scores to integer ppm. Respect
query budgets and expose pool/total chunk coverage. Failure is unavailable retrieval,
never a silent nonmatch or keyword fallback. A limited pool is not exhaustive.
Deduplicate candidate publications; retrieve originals/context before synthesis.

Create an initial durable index job on schema-3 startup and enqueue updates
atomically with publication. Index jobs run asynchronously outside the writer;
publishing succeeds independently of indexing/retrieval/model availability.
Unfinished builds resume after restart. Record built-through watermark and
per-context identities; invalidate/refill affected contexts for new references
and corrections. Keep old active data until new data is ready. Full rebuilds
read originals and activate atomically only after catching up concurrent writes.
No private delivery, query result or feedback enters an evidence index.

Expose A2A `retrieve`: question (nonblank, 1..4096 bytes), optional scope using
query bounds, optional limit (1..100 default candidate_limit). It creates a
normal owned query job with mode search and stage retrieve, returning
`{query:QUERY}`; query_result exposes validated candidate IDs/scores in
`candidates` alongside the query's evidence result and index coverage. It has
normal idempotency/ownership/budget semantics. Index unavailable is explicit.

## Search sufficiency and fallback

`search_then_scan` is the query default. Freeze the same scope/snapshot for both
paths. Persist a plan judgment for whether exhaustive evaluation is required.
Assess sufficiency semantically against the whole question and retained evidence;
neither hit count nor a high similarity score suffices. Current-view questions
must include later potentially superseding evidence before asserting current facts;
an incomplete index or candidate pool cannot establish that old activity remains
current. Exhaustive count/all questions require a complete scan unless an actually
validated equivalent full-coverage index path is available; top-k is not equivalent.

Escalate to scans on exhaustive_required, no_support, conflicting_evidence,
insufficient_context, stale_index, index_unavailable, retrieval_failed or
evaluation_failed. Persist actual execution_path and reasons. Query search-only
returns explicitly nonexhaustive/incomplete results when evidence is insufficient;
it does not secretly scan. Scan mode bypasses index dependency entirely.
Search-then-scan resumes from durable scan checkpoints. Errors and budget exhaustion
remain failed/partial and cannot be reported as exhaustive absence.

For apparently sufficient search answers, select independent crypto-random audits
with configured audit_ppm. Persist decision and probability once, before model
work, so restart cannot resample opportunistically. Audited queries run the scan
on the identical snapshot and expose both paths/comparison. Budget-limited audits
are explicit partial comparisons. Record audited versus fallback populations
separately; do not treat fallback-only examples as representative successes.

## Management and acceptance

Add admin read operations `indexes`, `index_jobs`, and `query_jobs`, each accepting
optional limit and returning `{items,truncated}`. Query job metadata includes ID,
owner, state, coverage, timestamps and versions, never question, answer, private
context or model payload. Add confirmed idempotent admin `rebuild_index` returning
`{index:MANIFEST}`; accepts only op, confirm:true, message_id and optional recipe
defined by adaptive index policy. The Activity view shows index/query coverage and
job states, and offers confirmed rebuild. Keep existing matching retry behavior.

Test exact IDs and paraphrases, contextual Yes, lexical zero-hit semantic support,
negation not mistaken for support, index catch-up, downtime, context invalidation,
concurrent rebuild/version switch, and preservation of original search. Verify
fallback from misses/stale index/outage, count/all requests, conflicting results,
budget exhaustion and sampled audits finding a plausible but incomplete answer.
Measure and expose the limits; do not claim calibrated semantic accuracy.
