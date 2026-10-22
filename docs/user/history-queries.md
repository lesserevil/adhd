# Questions about the local archive

[Project guide](../README.md) → History questions

`query_history` starts a durable asynchronous question about project-public
originals. It freezes the archive watermark, selected records, question and model
policy. Later publications and corrections cannot change that run. Private
messages never participate; canonical external-source questions still use
`source_query`.

Send these commands through your authenticated A2A client:

```json
{"op":"query_history","question":"Which test ran on the deployed build?","complete":true,"budget":{"records":128,"calls":64,"bytes":262144,"time_ms":30000}}
```

Keep the returned `query.id` and poll:

```json
{"op":"get_history_query","query_id":"REPLACE_WITH_QUERY_ID","offset":0,"limit":16}
```

Optional scope filters are `information_type`, `source_kind`, `source_id`,
`occurred_from`, `occurred_until` and `watermark`. They combine with AND. Times
include a zone and at most six fractional digits. Public linked context outside
these filters is explicitly labeled as expanded evidence. Context traversal is
bounded and never fetches an external URL.

Results distinguish direct support, inference, conflicting originals, insufficient
information and no evidence. Answers quote original text or JSON and cite all
jointly evaluated records. They never turn a missing detail into a negative fact
or assume repeated reports describe distinct objects. Corrections preserve both
assertions. Model decisions remain fallible, separately stored interpretations.

Check `status`, `error`, `coverage.primary_complete` and
`coverage.final_complete`. Scanning every record does not guarantee that the
bounded final joint assessment fitted the model. A provider error yields explicit
partial/unavailable work. A valid low-confidence decision remains uncertain.
Empty scopes complete with no evidence and explicit empty-corpus uncertainty.

A budget-limited partial result can continue with a fresh per-run budget:

```json
{"op":"continue_history_query","query_id":"REPLACE_WITH_QUERY_ID","budget":{"records":256,"calls":128,"bytes":524288,"time_ms":60000}}
```

Continuation retains completed groups and the frozen corpus. Evaluator changes
invalidate pending judgments; `restart:true` clears judgments and evaluates that
same corpus with the current policy. Cancel with `cancel_history_query`. Cancelled
or completed queries require explicit restart. Each job permits at most 16 runs;
`get_history_query` with `run` retrieves an archived run. Keep the original
`messageId` when retrying a mutation; changed commands conflict.

Evaluation pages contain the exact request bytes and their SHA256, original
context identities, typed model decisions and measured/reserved costs. Follow
`next_offset` until null. Only the owning agent and an explicit human Admin can
inspect these operational questions. Matching email addresses grant no access.

Admins configure the separate typed-choice evaluator in Settings → History queries,
including model/URL inheritance, version, confidence, context and resource limits.
Clearing URL/model restores subscription-matcher inheritance. Settings apply live;
subscription matching keeps its independent short `noul` decision path. Advance
the evaluator version when changing weights behind an unchanged endpoint/model.
Activity → Query jobs provides evidence pages, prior runs and cancellation.

The initial adapter bounds group/final inputs to 64/128 complete records and 6144
request bytes by default. Oversized originals produce explicit context/final
limits; the hub does not silently truncate them. Derived history state is bounded
separately from original publications. Raise the hot limit and continue explicitly
when that state fills. Search acceleration and adaptive indexing retain separate
roadmap gates. Exact schemas and limits are in [Wire protocols](../protocol/README.md)
and `components/hub/history/`.
