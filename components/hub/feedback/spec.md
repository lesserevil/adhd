---
name: Retrieval feedback and adjudicated replay
summary: Owned operational attempts and independent labels for reproducible retrieval comparisons
kind: component
---
# Feedback authority

Profile1.6 extends archive workflows with operational feedback and paired replay.
It does not turn model output, labels, questions, recipes or index jobs into source
publications, literal-search results, record IDs or subscription deliveries. Preserve
all earlier authentication, source identities, canonical routing and snapshot rules.
Use the existing Nemotron/SystemOne typed adapters; no new model weights or code
execution inferred from model output. Replay/optimizer share the existing analysis
model lane; matching, normal Retrieval and History workers remain independent.

## Attempt capture and ownership

Asynchronously capture every terminal Archive run, including successful search,
no-evidence/scan-only, partial/error/cancelled and sampled-audit observations. The
stable attempt key is {archive_query_id,plan_id,run}; capture waits until any
referenced child run is quiescent so late child costs cannot alter the captured
terminal observation. Duplicate polling/recovery
cannot create another observation. Preparation occurs outside Store and commits
only against the exact unchanged terminal run. Never stall ordinary Archive,
publication or delivery work if capture is disabled or full. Expose capture backlog,
limits and generic error counters; missing capture is not a successful observation.
A budget continuation is another run in the same plan, not another sampling trial.

Capture question, owner, frozen scope/project/server/watermark, primary source
identity, original policy/recipe when actually available, candidate IDs/ranks,
original assessment, scan/audit references and completeness, answer comparison,
fallback reasons, costs, timing and versions. Reference exact original Archive
run/evaluations rather than duplicating raw model exchanges or every nested child.
Cached compact summaries do not certify individual relevance: History support_ids
are all jointly evaluated inputs. Preserve their meaning when interpreting feedback.
Scan-only older runs may lack an original retrieval recipe; record unavailable,
never guess it from current settings.

Agents list/read/replay only their own attempts; wrong owner yields NOT_FOUND,
independently of common human ownership/email. Humans use explicit Admin management
operations. Admin replay records the actual human requester and the original agent
owner; it does not impersonate an A2A agent. New work needs a registered owner.
Agent APIs never expose other owners' questions, labels, group members or counts.

## Observations and independent labels

Classify observations conservatively: successful_search_unchecked,
successful_search_audited, provisional_retrieval_gap, provisional_answer_difference,
possible_archive_gap, required_scan, index_unavailable, incomplete_comparison or
unclassified. An answer change alone does not distinguish missing retrieval from
interpretation. Model failures, missing/truncated context, partial scans, cancelled
work and low-confidence comparisons are not negative evidence. A completed scan
finding nothing does not establish that the proposition is false.

Only an authenticated current Admin can confirm a label. A label declares expected
original support (supported), explicit incompatible sources (conflicting), or no
source evidence (no_evidence), plus exact supporting publication IDs, cohort and
optional negation/correction tags and note. Confirmation is explicit. Supported/
conflicting labels require1..128 distinct source IDs; no_evidence requires none.
IDs must belong to the attempt's original frozen primary scope or its declared
bounded public communication context. Reject private/future/foreign source IDs.
Validate source eligibility outside Store, then recheck attempt/label/config fences
before atomically saving. A no_evidence label requires full applicable original
scope coverage; it is not a universal claim about reality.

Labels are independent human assertions, not certified facts. No agent/model can
create a confirmed optimizer label. Record actor kind/ID, time, monotonically
increasing revision and frozen evidence identity. Keep16 label versions; reject
further revision growth explicitly rather than rewriting a referenced version.
Expected label revision is mandatory on save. Old replays retain their captured
label; pending work invalidates when that label changes. Incomplete model
comparisons can receive a human positive label but remain separately incomplete.

With a confirmed label, distinguish confirmed retrieval gaps (required primary
support absent from returned candidates), context-assembly gaps (candidate roots
present but required context not assembled), interpretation gaps (required inputs
present but interpreted differently), correctly supported search,
adjudicated no-source-evidence or incomplete assessment. Budget/policy/evaluator failures preventing assessment remain incomplete pipeline
observations. Never treat all model inputs as individually relevant gold. Record both observational and adjudicated
classifications and their different authority.

## Cohorts and recurrence

Cohorts are training, held_out or regression. Identical normalized questions on one
server are one group across owners, runs, plans and corpus versions. Normalize
Unicode NFKC, lowercase and whitespace only; do not infer a subject taxonomy.
Also join labels sharing confirmed supporting original IDs. For no_evidence labels,
join overlapping nonempty frozen primary source sets. Empty sets do not join all
unrelated questions. Reject conflicting assignments across joined groups; Admin
must reconcile them explicitly before qualification. Never leak another owner's
group membership through an agent response.

Track raw observation count, independent groups and same-plan resumptions
separately. Cluster recurring defects by observational/adjudicated failure class,
actual recipe/policy identity and context completeness, without entity columns.
Index unavailable, disabled retrieval and evaluator errors need operational repair;
they do not automatically justify another recipe.

Any candidate replay using a held_out group durably marks that group exposed before
evaluation, including failure/cancellation. Proposal-owned held-out work may resume
only with its already frozen winner/policy; another candidate/proposal cannot call
that evidence fresh. Changing labels/cohort does not erase exposure. Exposed groups
may be explicitly reused as regression/training but never silently unspent.
Record declared replay exposure for training, regression and unlabeled groups as
well, so relabeling previously evaluated evidence cannot manufacture fresh held-out
evidence. Software tracks declared use; it cannot prove an operator never saw source text.

## Bounds and administration

Feedback defaults enabledtrue, max_state_bytes33554432, max_attempts1024,
max_replays256, max_active_replays16, build_batch8 and replay budget
{records:1024,calls:256,bytes:2097152,time_ms:120000}. State bytes1MiB..256MiB;
attempts1..16384; retained replays1..4096; active1..64 not above retained count;
batch1..64. Budget uses existing HistoryBudget bounds. All fields are hot and
structured Admin Settings; reducing a cap preserves existing observations and
permits cancellation/retirement, while rejecting new growth explicitly.

Admin can inspect attempt evidence, label revisions, cohort/exposure/recurrence
summaries, actual paired replay stages/costs and source references; create/cancel
replays and explicitly retire terminal replay derived data. Retirement never removes
original publications, Archive attempts or labels/exposure history. Retained metrics
must disclose unavailable raw replay evidence and cannot claim fresh reproducibility
or satisfy new qualification. No background garbage collection deletes sources.

Qualification requires owned/idempotent capture, labeling/cohort collision and
exposure checks, exact wire/SDK/browser controls, real-model same-snapshot recovery,
privacy, no-delivery pollution, hard interruption/leases, budgets/hot policies and
native/Docker upgrades. Optimizer promotion retains its own INDEX-001 gate.
