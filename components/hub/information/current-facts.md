---
name: Current facts
summary: Resolve changing reports into current answers without deleting history
kind: component
---
# Current facts and retained history

Current-answer requirements for INFO-003, implemented by the query jobs specified
in queries.md. `get` and `search` continue to retrieve unchanged archive reports.
These requirements become available only after the extended runtime is accepted.

## Reports and facts

Retain every publication unchanged. Maintain durable, versioned query-result projections in which newer assertions
supersede earlier ones without deleting
their publications, provenance or deliveries. Acknowledgement does not affect
fact validity. Interpret ordinary text and JSON publications, including default
`message` types, without requiring special fact keys or prior publication IDs.

Given Agent A's “I am working on branch 'foo' on project 'baz'” followed by
“I am done working on branch 'foo' on project 'baz'”, a current query about A's
activities must not report A still working on foo. A query about who is working
on baz/foo must exclude A. Both reports remain retrievable through `get`, `search`
and an explicit history query. Completion does not prove A is idle, or that foo
was merged or deleted.

Facts describe the latest supported reports, not independently verified reality.
Retain authenticated submitter, claimed origin, effective time, acceptance time,
and evidence publication IDs. Relevance probability does not establish truth.

## Identity, scope and supersession

Identify each assertion's subject, property/activity and distinguishing scope.
Branch work is scoped by agent, named work project and exact case-sensitive
branch. A work project is distinct from the hub's configured visibility project.
Task IDs distinguish simultaneous tasks when supplied. Never merge different
agents' work or same-named branches in different projects.

Starting bar does not end foo unless the report explicitly describes replacement
or switching. Finishing foo leaves unrelated work active. Omitted fields do not
retract facts. Working, blocked, paused and completed remain distinct states;
only a current working state qualifies for “who is working”. Retain inactive
completion/retraction evidence so rebuild cannot resurrect earlier activity.
A later explicit restart may reactivate it.

For one reporting source, order assertions by normalized `occurred_at`, breaking
equal-time ties with monotonic ingestion sequence. Preserve `created_at`
separately. Late older reports fill history without overriding later events.
Future plans and unsupported future-dated claims are not present activity.

A later self-report supersedes an earlier self-report about the same activity.
Third-party assertions remain attributed; a different author cannot silently
overwrite a self-report by arriving later or claiming its origin. Incompatible
independent claims remain disputed unless a documented authority rule resolves
them. Arrival order alone does not establish trust.

Resolve “I” to the authenticated author for that author's own agent report.
External attributed material retains its speaker, rather than identifying the
submitting connector as the speaker. Quoted text, examples, questions,
hypotheticals and explicitly synthetic tests are not actual activity assertions.
Resolve “done with it” only with sufficient source context; otherwise preserve
unresolved evidence. Content cannot instruct the interpreter to change authority,
expose private data or accept unsupported assertions.

Explicit corrections retain original and correcting evidence and recompute
affected state. Define a validated representation before generation, rejecting
dangling, foreign-project and private-delivery references. `source.item_id`
remains an immutable event/revision deduplication identity, not a mutable fact key.

## Current queries and history

Provide a distinct natural-language query operation that defaults to current
facts and requires explicit history mode for past assertions. Preserve existing
archive `search` and stable-ID `get` behavior. Archive matches are historical
reports, not guarantees of current truth.

Support “What is agent-a doing?” and “Who is working on branch 'foo' on project
'baz'?” from the same resolved projection. Include evidence publication IDs and
effective timestamps with facts, with superseded evidence available for explanation.
Expose the processed-through ingestion sequence and unresolved/pending evidence.
Facts and citations must have retained, project-visible support. No subscription
is required; private messages and foreign projects are excluded from answers and
model context.

Resolve supersession across all relevant history before text/state/value filters,
ranking or result limits. Filtering for “working” first incorrectly discards
completion evidence. Limits bound returned facts, not evidence used to establish
current state. Agent lookup and reverse activity lookup must agree.

Distinguish supported facts, no known current activity, unknown/incomplete state,
and disputed/ambiguous state in the public response contract. No known activity
does not prove idleness. Preserve competing and unresolved evidence. Never give
a confident stale answer while a later accepted report could change it. If pending
interpretation cannot yet be scoped, conservatively mark answers incomplete
through the accepted ingestion watermark. Stale candidates may be shown only
with an explicit stale/incomplete label.

## Persistence and evaluator contract

The exact query operations, response fields, typed chat-completions adapter,
budget/checkpoint rules and privacy boundaries are defined in queries.md. Use
query.view=current by default; history mode is explicit. Keep the full original
context corpus as authority rather than extracting a fixed domain schema during
ingestion. Query-result projections are derived, versioned and reproducible.

A current answer must consider all relevant source evidence, including later
completions and corrections, before applying requested activity/value filters.
Incomplete candidate coverage cannot establish that an earlier activity is still
current; escalate search-then-scan queries to scan before asserting current state.
Freeze evidence membership at the submission watermark, expose that watermark,
and label results as of that snapshot. A fresh query includes later publications;
a same-snapshot replay deliberately does not. Preserve explicit source authority
and temporal-order instructions in every evaluation/synthesis model prompt.

Late reported event times use normalized occurred_at; ingestion sequence breaks
same-source equal-time ties. Third-party statements do not silently replace
self-reports. Correction references are the context.references relation corrects
specified in context.md. Completion remains available evidence, so replay and
restart cannot revive an earlier working claim merely because it matches a term.

query jobs/attempts persist their evidence identities, interpreter/prompt versions,
coverage and source references. A failed or malformed evaluator produces explicit
incompleteness and retryable continuation; never a confident stale fact. Every
accepted publication, including pre-upgrade records, remains in the query corpus.
No separate mutable extracted-fact store or domain-specific ingestion taxonomy is
required. The noul classifier selects relevance candidates only; the configured
generative evaluator performs grounded synthesis and must pass real model checks.

## Independent acceptance

Use separate authenticated clients and retained publication IDs. Expected answers
must be independent of the implementation's projection.

| Scenario | Observable result |
| --- | --- |
| Plain-text start then completion | Both questions exclude A from active foo work; completion is cited; both reports remain retrievable. |
| Completion omits “working” | Working queries consider completion before filtering. |
| Start foo and bar, finish foo | Bar and other agents' work on foo remain active. |
| Same branch in different projects | Finishing baz/foo leaves qux/foo active. |
| Late older start after completion | Foo stays inactive after ingestion, hard restart and rebuild. |
| Equal effective times from one source | Ingestion sequence breaks ties deterministically. |
| Complete then explicitly restart | A becomes active with restart time and evidence. |
| Third party contradicts A | Attribution/conflict is visible; latest arrival alone cannot override A. |
| Quoted, hypothetical, synthetic or future reports | No unsupported present activity is asserted. |
| Ambiguous completion | Preserve unresolved evidence; unrelated work is unaffected. |
| Pending interpretation or model outage | Incomplete answer; get/search/publish/poll work; recovery resumes interpretation. |
| Malformed or ungrounded inference | Reject without advancing watermark or inventing facts. |
| Correct erroneous completion | Retain original and correction; recompute under validated correction rules. |
| History exceeds result limit | Completion outside a matching page still supersedes old working claims. |
| Retry, acknowledgement, hard restart | Stable history/state, no duplicate or resurrected activity; pending work survives. |
| Upgrade each supported store format | Explicit backfill; publications, private messages, queues and idempotency preserved. |
| Private or foreign evidence | No private/foreign fact, citation or model context is exposed. |

Exercise deterministic resolver/failure fixtures and a real model interpreting
free-text start/completion and both questions. Publish fresh native, SDK, migration
and container evidence before claiming implementation. Old reports remain evidence
of the old runtime.
