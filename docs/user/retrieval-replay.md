# Retrieval feedback and paired replay

Terminal Archive runs are captured asynchronously, after their own model lease and
referenced child runs have settled. Capture includes successful searches, audited
searches, fallback scans, empty scopes and incomplete/error observations. Disabling
capture preserves existing attempts and exposes the remaining backlog. Attempts
reference immutable Archive/History evidence; capturing them creates no publication,
subscription match or delivery.

An agent can list and inspect only its own attempts. Human Admins use **Feedback**
to inspect attempts, open the original Archive evidence, confirm independent labels
and start paired replays. A label names required original publication IDs, an
expectation (`supported`, `conflicting`, `no_evidence`), a cohort and optional
negation/correction tags. A no-evidence label requires a complete applicable scan
and has no support IDs. Model `support_ids` describes supplied originals; it is
not a human relevance judgment. Labels preserve the confirming actor, evidence
identity and every revision. An outdated label revision is rejected.

Identical normalized questions across owners and plans form one cohort group.
Shared confirmed source IDs and overlapping nonempty negative-control scopes also
join groups. Admins cannot put joined evidence in different cohorts. Observation
counts, independent groups and distinct plans remain separate. Agents cannot see
other owners' group membership. Declared replay exposure survives relabeling,
failed/cancelled work and retirement. A held-out group already used for another
candidate cannot be treated as fresh.

## Agent calls

Send these command objects in the usual authenticated A2A data part:

```json
{"op":"list_retrieval_attempts","limit":8}
```

```json
{"op":"get_retrieval_attempt","attempt_id":"ATTEMPT_ID"}
```

```json
{"op":"replay_retrieval","attempt_id":"ATTEMPT_ID","candidate_recipe":{"context_depth":2}}
```

```json
{"op":"get_retrieval_replay","query_id":"REPLAY_ID","limit":4}
```

```json
{"op":"continue_retrieval_replay","query_id":"REPLAY_ID","budget":{"calls":64}}
```

```json
{"op":"cancel_retrieval_replay","query_id":"REPLAY_ID"}
```

Creation, continuation and cancellation use actor-scoped A2A `messageId`
idempotency. Wrong-owner IDs return `NOT_FOUND`. Admin-created replays preserve the
agent owner and record the actual human requester; Admin sessions do not impersonate
an agent.

## Reading a comparison

Both branches perform fresh execution against the same question, source filters,
original IDs and watermark. `baseline:"recorded"` uses the attempt's saved recipe.
Scan-only attempts lack one and require explicit `baseline:"current"`. The candidate
is a partial patch of native recipe primitives; it cannot contain executable code
or expressions. It does not alter the live index.

Each branch builds isolated native rows, ranks and scores its bounded candidate
window, then assesses full originals with the current History choice template.
Insufficient, incomplete or failed candidate evidence requires a real complete
History child. Original/current full-coverage intent cannot be weakened. A cycle
diagnostic is resolved only when its target is among the exact supplied originals;
missing targets, other gaps and actual truncation still prevent sufficiency.

`coverage.assessed_ids` records the full originals actually supplied after candidate
selection. Confirmed retrieval recall uses those inputs, never every scored-window
or expanded index ID. A baseline may recover the correct answer by a full scan
while a better candidate retrieves the required originals and avoids that scan.
Both end-to-end answer correctness and retrieval recall are reported. Lower
fallback frequency alone does not establish an improvement.

`usage` reports actual per-run and lifetime cumulative calls, HTTP bytes, work
records, active time and uncertain calls for each branch and their sum. Native
state bytes are separate. Branch `comparison_usage` accumulates paid work across
continuations of the current experiment; explicit restart begins a fresh experiment.
Comparison cost deltas use those totals, so a previously completed baseline does
not become free when the candidate resumes. Observed latency is not an isolated
recipe-speed guarantee. No counterfactual model charges are invented.

`corpus:"current"` explicitly freezes a new watermark for both branches. This is
a changed-corpus observation and cannot reuse the old label for quality credit.
Unlabeled, incomplete, invalidated and retired observations are also ineligible.
Interpretation policies and label revisions fence pending work. Explicit
`restart:true` adopts current policies/labels on the replay's same frozen corpus;
only a new submission recaptures current data. Prior runs remain accessible.

## Administration and limits

**Settings → Feedback and replay** exposes all capture, retention, active-job,
state-byte, native-build-batch and per-branch budget settings. Changes are hot.
Each branch has separate records/calls/request-byte/active-time caps. Model calls
reserve costs before HTTP; interruption settles the full timeout once as uncertain
work. Archive and replay share one analysis lane, with at most one start per second
while subscription matching is due. Matching retains its independent worker.

**Activity** shows replay stages, branch evidence, actual costs and prior runs.
Admins can cancel work and explicitly retire terminal replay evidence. Retirement
removes derived native rows/direct evaluations and eligible internal History
children, retaining numeric metrics, labels, exposure and original publications.
`evidence_available:false` discloses that the raw replay can no longer qualify a new
experiment. Reducing a cap preserves existing data and still permits retirement.

The precise closed objects and semantic constraints are in
`components/hub/feedback/interface.md`,
`components/hub/feedback/replay.md` and the published
[protocol schemas](../protocol/schema.json). Adaptive recipe promotion remains a
separate roadmap gate.

## Project isolation qualification

Queries, attempts, labels, cohort exposure, paired replays, optimizer proposals
and index selections belong to an explicit admitted project. A local workflow ID
may have the same text in another project; the project and ID together identify
the resource. An actor with access to both projects must still select the intended
project on every ambiguous request. Role grants do not replace project admission.

The [earlier evidence matrix](../validation/multi-evidence-04.json) remains a
historical candidate record. The [independent two-project evidence matrix](../validation/multi-evidence-28.json)
records eleven passing groups against a precisely hashed development candidate and
real Kafka. It reuses an agent, questions, source/item IDs and message IDs across
two projects, checks query ownership and frozen watermarks, rejects foreign label
gold and optimizer training IDs, and exercises independent cohort exposure,
paired replays, recipe changes and selection resets. Actual `evaluate_index`
requests reject foreign held-out IDs; cancelling one project leaves the other
project able to finish a real evaluation after restart with its own final-case
references and summary. This routing fixture permits 64 KiB History requests and
positive cost deltas, and authors relevance from the original IDs actually
supplied to its typed endpoint; it does not certify the default quality policy.
The matrix also kills and restarts
the hub after revoking an owner while its evaluator request is in flight. The
controlled typed evaluator proves evidence routing and failure isolation; this
qualification does not measure semantic model quality.

Run the executable matrix with an isolated disposable hub configuration:

```sh
.venv/bin/python tests/multi_evidence.py --hub /absolute/path/to/hub.exs \
  --eventing-rest-url http://127.0.0.1:18082 \
  --keep-work _build/evidence --report _build/evidence.json
```

The [candidate30 evidence refresh](../validation/multi-evidence-30.json) repeats
all eleven isolation groups, including actual optimizer final evaluation and
revocation across hard restarts. It retains the controlled-fixture scope and
policy allowances above; actual-image qualification is separate.
