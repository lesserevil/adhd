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

The [accepted-store workflow upgrade check](../validation/multi-workflow-upgrade-30.json)
uses the actual previously qualified optimizer store and its original executable,
selects its learned recipe through the public rollback operation, then upgrades
that closed store with the candidate30 executable. It compares complete public
projections for 41 History, eight retrieval, eight archive, 20 paired replay and
three optimizer workflows, plus eight labeled attempts, cohorts, deliveries and
publication counts. The selected recipe and all evidence survive migration and a
hard restart. A subsequent explicit recipe reset preserves historical evidence;
only retired global index generation availability may change. The original
qualified store files remain byte-for-byte unchanged. This check uses previously
recorded model evidence and makes no new semantic quality claim.

The [admitted-image evidence qualification](../validation/multi-evidence-image-30.json)
repeats all eleven isolation groups using the exact reviewed image manifest and
payload. Three actual container kills and replacements preserve private backend
data while checking query ownership, revocation and optimizer evaluation fences;
the report records each container ID and verified removal.

The [admitted-image accepted-store upgrade](../validation/multi-workflow-upgrade-image-30.json)
repeats all four workflow migration groups with actual container replacement.
The changed native runtime rebuilds derived global index generations; an old
proposal's global-generation availability may fall only when its saved manifest
is absent from the current and previous generations. All paired raw evidence,
labels, saved queries and learned selection remain exact. The check waits for
index readiness before comparing generation topology after an explicit reset.

The [fixed native candidate30 optimizer quality run](../validation/optimizer-live-quality-30-diagnostic.json)
did not qualify its frozen winner. Its correction control selected the original
“Correction: No” with probability 0.448863, tied with `unknown`, below the required
0.5. All three linked original records reached the model at the same frozen
watermark; the original observation and both replay branches retained the same
low-confidence result. The optimizer correctly rejected the winner with
`QUALITY_REGRESSION`, despite positive recall gain and reduced total cost. This
report preserves the exact original and replay exchanges; inspection added no
model calls. Positive live optimizer qualification remains open.

The same diagnostic also includes exchanges read through the actual previously
accepted runtime from a private clone of the unchanged qualified store. That run used the same
question, originals, reply chain and exact model criteria/template, selecting the
same quote at probability 0.613987. The old and current request objects match
after normalizing only opaque identities and timestamps. This historical
comparison confirms preserved context and prior support for the authored case;
it cannot by itself distinguish model sensitivity to metadata from serving drift.
No diagnostic inference calls were made.

The [candidate30 inherited live-model matrix](../validation/deep-live-model-30.json)
records one fixed native and image run of the existing History, retrieval,
Archive and paired Feedback suites: 69 authored cases per mode. The original
semantic, recall, negative-control and cost assertions remain intact. Paired
Feedback declares an 8 KiB assessment bound while retaining the 0.5 confidence
threshold. This matrix excludes positive optimizer qualification, whose failed
correction gate and exact diagnostic remain recorded above.

The [predeclared six-frame provider diagnosis](../validation/model-frame-30-diagnostic.json)
keeps the question, criteria, original text and reply graph fixed while varying
opaque identities and timestamps. All six input hashes were frozen before one
POST per frame, with no retries. The exact current frame remained below the
confidence threshold; the exact historical frame reproduced its prior value.
One metadata variant selected `unknown`; two fresh variants selected the quoted
negative above the threshold. This supports metadata sensitivity on this frame.
It is neither a model accuracy estimate nor positive optimizer qualification,
and a confident `unknown` still fails the unchanged supported-answer gold.

The [candidate30 inherited controlled regression matrix](../validation/deep-controlled-30.json)
retains 15 suites and 117 groups per mode, native and the admitted image. These
cover context, History, retrieval, Archive, Feedback, optimizer faults and recipe
selection, plus official A2A SDK exchanges and actual legacy-store producers.
The context suite explicitly upgrades both historical producers. This matrix
does not replace the separately failed real-model optimizer quality gate.

The [fixed eight-call instruction diagnosis](../validation/model-instruction-30-diagnostic.json)
adds one generic provenance instruction to all six frozen variants and two saved
independent negation/no-evidence controls. The current correction still fails;
three correction variants pass, compared with four before the addition, while
both controls pass. Every input hash was frozen before calls, with no retries.
The experiment intentionally differs from the current protocol instruction
constant; the proof preserves that rejection and separately validates the saved
responses offline. It supports no application change or optimizer qualification.

The [single preregistered source34 positive-witness attempt](../validation/optimizer-positive-34-min-evidence.json)
stopped at `MIN_EVIDENCE` after six provider POSTs. Both independently labeled
training searches already supplied every required original and answered directly,
so they did not establish the two recurring retrieval/context gaps needed for a
proposal. No winner or final held-out sources were created, and the experiment
was not retried. The proof retains the frozen seven-case manifest, exact model
exchanges and unchanged budget. This is a correctly rejected no-miss cohort,
not positive optimizer qualification; that capability remains unproven for the
current artifact. The earlier capsule-R quality failure remains separately open.

The [source34 native live-model regression matrix](../validation/deep-live-model-34-native.json)
passes all 69 existing History, retrieval, Archive and paired Feedback cases in
one run per suite. Harness hashes match the source30 matrix; gold, thresholds
and assertions remain unchanged, including the declared 8 KiB paired-feedback
assessment profile. These native results make no image qualification claim and
do not change either failed optimizer experiment or the open positive optimizer gate.

The [source34 native optional-model stream and backend smoke](../validation/live-eventing-backend-34-native.json)
uses six actual provider POSTs under a hard cap of twelve. It checks decisive
positive/negative filtering, raw delivery while inference is disabled, direct
History support with project isolation, and exactly one delivery of accepted
paused filter work after re-enabling the model. The owned relay and private bridge
are removed afterward. This feature witness does not claim lifecycle or image
qualification and does not change the unresolved optimizer experiments.

The [source34 native controlled regression matrix](../validation/deep-controlled-34-native.json)
passes all 117 groups in 15 existing suites, once each, with unchanged harness
hashes from source30. It includes both historical context producers, official
A2A SDK exchanges, real store upgrades and optimizer fault/selection checks.
Controlled model decisions establish behavior and failure isolation; live semantic
quality remains separately measured, and positive optimizer qualification is still open.

The [source34 rendered and fairness matrix](../validation/deep-rendered-34.json)
passes the five existing backend browser suites and three controlled fairness
suites on both native and the accepted image, once per runtime. Desktop and
mobile captures were inspected, and the proof retains every report and capture
hash. Fairness uses the declared two-permit project profile with the original
assertions; it makes no default-one-permit throughput or live optimizer quality
claim. The image, reviewed manifest and packaged hub bytes were verified.

The [source34 accepted-image live-model matrix](../validation/deep-live-model-34-image.json)
passes the same 69 existing History, retrieval, Archive and paired Feedback cases
once each. Harnesses, gold and confidence thresholds match the native matrix;
Feedback retains its declared 8 KiB assessment profile. The immutable image,
reviewed manifest and packaged hub digest were verified before execution. Model
ownership was handed off only between completed suites. These backend results do
not qualify either failed optimizer experiment or close the positive optimizer gate.

The [source34 accepted-image controlled matrix](../validation/deep-controlled-34-image.json)
passes all 117 groups across 15 existing suites, once each. The unchanged native
matrix's harness hashes match, including actual historical store producers and
all four official A2A SDK suites. The immutable image, exact reviewed manifest
bytes and packaged hub digest were verified before execution. Controlled behavior
and fault checks do not establish semantic model quality or positive optimizer
qualification; the separate failed optimizer evidence remains unchanged.

The [recovery-fixture compatibility check](../validation/recovery-helper-profile20.json)
retains the nine existing multi-project checks on accepted source34 after adding
future profile2.1 initialization support to the test fixture. The exact profile
gate keeps profile2.0 free of recovery operations. This is a compatibility result;
it provides no runtime qualification for the new recovery feature.

Recovery development checkpoint05 is retained separately in [the admission and unfinished restore reports](../validation/recovery-development-05.json). Admission passed five groups; broader restore, legacy selection and unsafe-input tests retain their exact failures and do not establish complete selective recovery qualification.

The unadmitted recovery development snapshot06 separately passed [actual accepted learned-selection recovery](../validation/recovery-learned-dev06.json): 41 History, eight retrieval, eight Archive, 20 paired replay and three optimizer workflow records, eight labels, the actual selected recipe and qualification, and unrelated newer project data survived target-only restore and hard restart. Preparation used public rollback of an already qualified recipe with zero model calls; a process-local provider network fence blocked connections. This is storage/provenance preservation, not a new live optimizer quality qualification or release admission.

The same development snapshot06 retains [unfinished unsafe-input and rendered recovery failures](../validation/recovery-development-06-failures.json): an out-of-contract ownership reason and an old-project response affecting the new-project alert. Prior checks and screenshot hashes are recorded, with unexecuted mobile/role coverage explicit. These failures remain separate from the passing learned-selection witness.

The complete mixed-state development test retains its [snapshot-bound optimizer timing failure](../validation/recovery-mixed-dev06-timeout.json). Seven child replays completed and the last History child began less than two seconds before the fixed 90-second shutdown, with zero uncertain calls. The accepted backup and later-state hashes remain recorded. Raising the reviewed lifecycle wait to 300 seconds changes no data, gold or quality gate and makes no throughput claim.

An unchanged-assertion diagnostic captured [the exact obsolete-view alert on development06](../validation/recovery-browser-dev06-alert.json), including its failure screenshot hash and direct visual inspection. Development09 separately passed [11 unsafe-backup and stale-plan groups](../validation/recovery-rejections-dev09.json) and [three Developer identity admission groups](../validation/recovery-developer-dev09.json). Known initialized missing evidence failed closed with the actual declared HTTP400/INVALID_PARAMS response, unchanged configuration and rejected new token; exact file restoration then allowed the identical previously unaccepted request. These are development results, separate from full mixed-state restore and rendered qualification.

Development09 [passed the existing desktop/mobile recovery browser assertions but failed manual freshness review](../validation/recovery-browser-dev09.json): the completed status was ready while the top target label still said recovery_required. Four direct screenshot inspections and all eight capture hashes are retained. Ready-label assertions were added for the next artifact; this result does not close rendered recovery acceptance.

Development09 retains [the complete mixed-state replay delivery timing failure](../validation/recovery-mixed-dev09-timing.json): the full1..50 replay reached a remaining30-second delivery poll before its300-second materialization wait. Both optimizer proposals had completed and remained rejected under their unchanged quality gates. The next fixture aligns all Kafka control-stage waits and explicitly checks each public ID family; this failed run establishes neither data loss nor complete allocator acceptance.

Development10 passed [two strengthened recovery and six index-panel browser groups](../validation/recovery-browser-dev10.json) on desktop/mobile. Actual initialization/restore updates the target label and hides initialization; obsolete real responses across project/view changes stay silent, while actual current Viewer grant denial remains visible. Fourteen capture hashes and eight direct screenshot inspections are retained, along with the initial overly specific denial-code diagnostic. This qualifies those native rendered flows, not the still-separate full mixed-state, federation, Docker or release gates.

Unadmitted development12 passed [22 native unsafe-input, Developer-admission and rendered recovery/index groups](../validation/recovery-development-12.json). The exact checkpoint is bound to unchanged harnesses; all 14 screenshot hashes and eight direct visual inspections are retained. Unknown uninitialized projects permit fresh Developer identity creation, while known missing evidence fails closed without changing configuration or accepting its token. Actual initialization/restore labels and project/view response isolation passed on desktop/mobile. This is scoped development evidence; complete mixed-state recovery, federation/crash, Docker and release gates remain separate.

The same unadmitted development12 checkpoint passed [actual accepted learned-selection recovery](../validation/recovery-learned-dev12.json): the original qualified selection, eight labels, 41 History, eight retrieval, eight Archive, 20 paired replay and three optimizer records survived the missing-target restore and hard restart. The source installation files remained unchanged; a process-local connection fence and paused target policy ensured zero provider POSTs. This establishes retained storage/provenance compatibility, not a new semantic optimizer quality result or complete recovery qualification.

Development10 completed [the full controlled mixed-state recovery lifecycle](../validation/recovery-mixed-dev10.json): actual missing-target restore preserved12 complete accepted subtrees, current security, private acknowledgements and unrelated newer project positions, then accepted102 fresh identities without reusing102 lost identities and survived a cold apply retry. Full Kafka replay ranges, actual poison-row repair/audit and optimizer evaluation ran before and after restore; all controlled quality regressions remained rejected. Explicit public ID checks passed, with a disclosed listing-completeness gap scheduled for the next checkpoint. Source/federated query allocation, crash, Docker, live semantic quality and release gates remain separate.

The first development14 query-callback fixture retains [its failed precondition](../validation/recovery-query-dev14-precondition.json): actual source/discovery remote jobs were accepted, but no later lost-source success arrived while earlier retained questions remained deliberately unavailable. It did not reach target loss or restore. The next fixture gates an actual backed-up same-ID response and its fresh postrestore poll, providing a stronger callback fence without assuming progress past blocked earlier jobs.

A stronger development14 attempt retains [the nonexpired pending source-query restart observation](../validation/recovery-query-dev14-restart.json). Its backed-up source job was pending, yet the cold-started origin retained partial/unavailable while its original remote job completed. More than71seconds remained on the original120-second deadline, and configuration bytes were unchanged. The suspected startup cache-revalidation path is explicitly an inference. This attempt also stopped before target loss/restore and provides no callback-fence qualification.

Development12 passed [the strengthened full mixed-state recovery lifecycle](../validation/recovery-mixed-dev12.json), including explicit complete public query enumeration and the actual replay-delivery fresh-epoch check. The fixture preserved12 full accepted subtrees,127 retained identities, current security and unrelated newer project positions;102 new identities did not reuse102 lost identities. All three controlled optimizer evaluations remained rejected. Complete Kafka replay ranges, real foreign-row repair/audit, cold restart and apply idempotency passed under the declared finite lifecycle bounds. Source/discovery callback and allocator checks remain separate, as do crash, Docker, live semantic quality and release gates.
