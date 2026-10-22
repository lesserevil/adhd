# Active work

This file is the durable resumption queue for user-directed and discovered work. Before
implementation, follow `skills/agent/record-user-directed-work/SKILL.md`.
Keep detailed designs in focused roadmap documents and link them here.

## Detailed-roadmap lifecycle

This file is the sole resumable queue. Create a supporting file beneath `docs/roadmap/`
only when one item cannot keep a program's rationale, ordering, and acceptance contract
readable. Put this visible header immediately after the detailed document's title:

```markdown
- **Status:** active
- **Owning queue item:** [AREA-NNN](active-work.md#area-nnn-heading)
- **Completion / archival evidence:** pending while AREA-NNN remains open
```

Status is exactly `active`, `partial`, `deferred`, `completed`, or `historical`. The
owner must resolve to a checkbox or named program heading in this file. A terminal state
requires linked evidence. Keep a completed plan here only when doing so preserves useful
inbound links; move substantial closed programs beneath `docs/history/roadmap/`, retain
their owner, and mark them `historical`. Do not create a separate file for an ordinary
queue item or let `docs/roadmap/` become a plan archive.

## Authorized implementation batches

The [readiness successor](../../verification/eventing-readiness-candidate01/root-source-review.json)
changes only Eventing and ProjectRestore; it is not yet qualified. The proper
lock and documentation-authority gates pass. Its [first lifecycle attempt](../../verification/eventing-readiness-lifecycle41-first-failure/manifest.json)
stopped before application compilation because the retained snapshot omitted
the required test manifest and source SBOM. The [validated metadata repair](../../verification/ownedMULTI008/eventing41-sidecar-capture/manifest.json)
and fresh 58-file snapshot now pass that gate. The [second lifecycle attempt](../../verification/eventing-readiness-lifecycle41-oracle-failure/manifest.json)
built the exact successor export, then stopped because the independent oracle
still referenced the previous specification set; no new receipt was issued.
The [oracle review](../../verification/eventing-readiness-oracle-review41/review.json)
preserves all 106 arguments and expected results and updates only their specification
binding. The [proper lifecycle rerun](../../verification/eventing-readiness-source41-lifecycle-positive/manifest.json)
now passes and issues the successor receipt with all 18 declared tests passing.
The [first independent readiness run](../../verification/eventing-readiness-native23-first-failure/manifest.json)
passes the real-broker lag case, then fails its queue-control case; the remaining
21 cases are unrun. Inputs and native/proxy cleanup are independently verified.
The positive control incorrectly shares one global HTTP ticket with Blue's normal
one-second Kafka polling, so absence of the deliberate hold does not establish
absence of queue contention. Correct that control to two global tickets and one
per project, observe those limits through the public resource-status API, and
retain its same 20 visibility faults and three-second deadline. The negative queue
case keeps its original single global ticket, held Blue request, observed queued
Red work and shared three-second budget within the ten-second recovery budget.
The correction also retains bounded failure traces before assertions can discard
them. Its complete rerun is recorded below; the earlier failure remains false.
The [corrected-control run](../../verification/eventing-readiness-native23-retention-failure/manifest.json)
passes 15 whole cases, including the observed shared-budget queue expiry, then
fails existing-retention after its durable decision and real Kafka alter; seven
cases remain unrun. The desired policy and transaction remain, as required for
an incomplete committed transition. Its positive retention fixture also shares
one project HTTP ticket with Blue's normal poll; establish two project tickets
and observe independent policy capacity without changing its one-second budget
or any policy/readback/preservation assertions. The original failure cause stays
unconfirmed. Add a separate deterministic postdecision readback-failure test:
fail only the selected topic's readback after real alteration under the durable
decision, then cold-start unchanged state and prove desired-policy replay,
transaction completion and preserved records, acknowledgments, routes and offsets.
Repeat a cold start to check idempotence. Existing generic config crashes and
topic-prefix cutover tests do not cover this retention-specific recovery boundary.

The [complete successor readiness run](../../verification/eventing-readiness-native23-positive/manifest.json)
now passes all 23 cases against the proper successor export and receipt, with
zero unrun cases, verified input/tool closure and all owned native processes and
proxies cleaned up. It preserves the original assertions and deadlines, observes
the independent positive-control capacity, verifies the actual old/new Kafka
retention values around the durable decision, and retains the shared-budget queue
expiry. Both earlier failed runs remain false. The separate committed-retention
failure and unchanged-file cold-recovery companion and source admission are
recorded below. Compiled-image and deployment qualification remain open.

The [separate retention companion](../../verification/eventing-retention-native-positive/manifest.json)
now passes all three checks across three owned native starts: actual alteration
under the durable decision followed by injected readback failure, desired-policy
replay before healthy response headers on unchanged-file restart, and a second
restart without repeated alteration, offset reset or acknowledged delivery replay.
Records, routes, revisions and message receipts are preserved; all owned processes
and proxy handlers are cleaned up. The [fresh source admission](../../verification/eventing-readiness-source41/admission/manifest.json)
binds both native reports to the actual official receipt, rebuild and provenance.
The [successor image qualification](../../verification/ownedMULTI008/source41-compiled-image-positive/audit.json)
now records two independent sequential builds with identical image, configuration
and filesystem-layer identities. Its create-only offline audit verifies the exact
59-file application payload, 33 specifications, 59 compiled modules and 65 cache
entries, normalized timestamps and owned-container absence. This is scoped build
and payload evidence. Its [complete cache/CLI gate](../../verification/container-cache41-positive/audit.json)
now passes all 17 groups, including 18 built-in tests and all 12 corruption
rejections. The [six-family ABI gate](../../verification/ownedMULTI008/source41-image-abi-positive/audit.json)
passes all 19 physical probes, with actual container identities absent; the
historical runner's unretained issued-name limitation is stated explicitly.
The [compiled retention companion](../../verification/eventing-retention-compiled41-positive/audit.json)
passes all three recovery checks across three actual default-entrypoint VMs,
verifying 59 application files and 67 cache/toolchain files in each VM and complete
owned cleanup. The [complete compiled readiness matrix](../../verification/eventing-readiness-compiled41-positive/audit.json)
now passes all 23 cases on that image. [SDK compatibility and cold startup](../../verification/eventing-readiness-sdk17-positive/manifest.json)
passes all 17 cases under the original 30-second readiness deadline. The
[late-callback recovery gate](../../verification/recovery-callback41-positive/manifest.json)
passes all five original programs /28 checks with actual compiled VM custody;
that gate uses its original instrumented Store-loss entrypoint. Current deployment,
security, browser and deployed-model results are recorded below. Next: finish the
fresh full25 recovery gate, then consolidate exact scoped evidence, declared
verification and operating limits. Core13 and full14 Kafka now pass independently.

The [successor core13 attempt](../../verification/eventing-readiness-core13-first-failure/manifest.json)
stopped in its first foundation program after 11
partial checks: enabling OIDC returned `CONFIG_CONFLICT` with live revision 19
following the external-file reload exercise. No whole foundation result or later
core program is qualified by that attempt. The fixture retains a full private
configuration dictionary from before the successful external reload and restores
it after its invalid-file check; mutation helpers then obtain revision metadata
from that file. Review this stale-restoration premise against the live revision
contract, retain the original false run and cleanup evidence, and synchronize the
fixture's last-good full configuration after the accepted reload if confirmed.
The failed request's exact expected revision was not retained; do not invent it or
change application conflict behavior. Preserve all original assertions, deadlines
and conflict-denial checks, with no automatic mutation retry.

The [reviewed foundation fixture repair](../../verification/foundation-reload-fixture-repair/manifest.json)
retains its last-good configuration immediately after the successful reload. The
fresh full core13 run uses that single assignment change and preserves the
original assertions and deadlines; the first false attempt remains unchanged.
The [Kafka federation timeout diagnosis](../../verification/eventing-readiness-kafka14-federation-timeout/manifest.json)
records 13 whole programs passing before the final federation program stops after
seven partial checks. Its catalog configuration update was durably accepted as
revision 2, but the client timed out waiting for HTTP status under the original
five-second bound. The delayed phase is unproven. Next, retain the false run and
independent cleanup evidence, then gather bounded, sanitized request/commit timing
without retrying mutations or widening that bound before choosing a correction.

The source41 full recovery run passes its first 23 whole programs, including all
15 crash cases, then fails the storage-rebind harness's actual-VM command-line
identity assertion. Its child assertion precedes the missing report that the
parent reports as `FileNotFoundError`; the final hostile-rebind program is unrun.
The real decision-durable fsync sentinel exists and cleanup reports closure, but
the mismatching command-line fields were not retained. Next, independently retain
the false attempt and cleanup, identify the launch/custody mismatch, and preserve
exact process identity and original fault assertions in any correction. Partial
checks do not qualify either failed program.

The fresh core13 attempt passes foundation and ten further whole programs, then
auth setup fails before starting its first hub because it resolves
`scripts/configure_hub.py` relative to the private runtime working directory.
Workflow-upgrade remains unrun. Resolve this authored fixture input from the test
file's repository root, retain the negative run and unchanged application scope,
and test setup from a different working directory. Preserve the original Python
launcher, setup arguments, authentication assertions and deadlines. The rebind
follow-up is likewise diagnostic first: retain sanitized argument-match booleans
and hashes before the exact VM assertion, including failure cleanup, without
recording serialized requests or relaxing custody.

The [source41 deployment qualification](../../verification/ownedMULTI008/source41-baseline-platform-positive/audit.json)
now passes all 21 model-free checks across Compose and Kind, including replacement,
broker patch upgrade, complete cold restore and target-only selective restore.
The independent audit verifies the full frozen inputs, actual compiled VM custody
and owned-resource absence. The [Kafka negative audit](../../verification/kafka41-compiled-first-failure/audit.json)
and [full recovery negative audit](../../verification/recovery41-full25-first-failure/audit.json)
preserve the failed aggregates and their passing whole-program prefixes separately;
later private Kafka service cleanup does not change either failed result.
The [secured Kind audit](../../verification/ownedMULTI008/source41-secured-kind-positive/audit.json)
also passes its seven reported checks with all 48 original assertion sites
conserved; the current program has 51 assertion sites, which are not 51 separate
reported cases. The [focused browser qualification](../../verification/ownedMULTI008/source41-focused-ui-positive/audit.json)
passes Admin18, Events12 and recovery2 with exact compiled VM custody, all 26
PNG/accessibility snapshot pairs and owned cleanup. Its separate
[manual desktop/mobile review](../../verification/ownedMULTI008/source41-focused-ui-manual-review/review.json)
covers 18 actual captures and two accessibility reads.

The [auth setup path repair](../../verification/ownedMULTI008/source41-auth-path-repair/review.json)
now passes its independent-working-directory fixture tests. A
[fresh full core13 plan](../../verification/ownedMULTI008/source41-core03-preparation/review.json)
retains all original jobs rather than borrowing its eleven-program prefix.
The [focused rebind controller](../../verification/rebind-focused41-once-controller/manifest.json)
and [federation timing diagnostic](../../verification/federation-admin-timing-preparation/metadata-review.json)
run the original scenarios with additive sanitized observations; neither changes
the failed aggregate or independently closes the full regression requirement.
Both focused diagnostics now pass: [rebind2/18](../../verification/rebind41-focused-positive/manifest.json)
and [federation1/14](../../verification/federation41-focused-positive/audit.json),
with independent input and cleanup audits. All retained rebind argument matches
are true; the earlier mismatch remains unexplained. The previously slow catalog
update returns within the original five-second timeout in the diagnostic, without
establishing the earlier delay's cause. The [fresh full25 recovery](../../verification/recovery41-full25-second-preparation/manifest.json)
and [fresh full14 Kafka](../../verification/source41-kafka-fresh-full14-preparation/review.json)
plans retain every original scenario and deadline and borrow no passing prefixes.
The recovery runtime gate remains open. The
[complete fresh Kafka run](../../verification/kafka41-full14-positive/audit.json)
now passes all 14 original programs /68 checks, with unchanged assertions and
deadlines, complete input/tool closure, strict owned-resource absence and unchanged
protected services. The [complete core run](../../verification/ownedMULTI008/source41-core13-positive/audit.json)
passes all 13 programs /94 checks without borrowing either failed attempt's prefix.
The [pinned declared verification](../../verification/source41-declared-verify-positive/manifest.json)
passes authority, locks and current official receipt, with two configured skips;
final documentation recording and verification remain part of the closure review.

The [source41 deployed model audit](../../verification/ownedMULTI008/source41-deployed-model-positive/audit.json)
passes on both Compose and Kind: eight outer reported checks and twelve actual
upstream POSTs total, six per platform under the original twelve-per-platform
cap. Filtering, cited fact search, raw progress, privacy and same-VM hot
disable/resume are covered by the original assertions and semantic reports;
these counts do not invent twelve separately serialized test cases. The original
model container identity, cooperative lease release and owned cleanup are verified.

Retained qualification below uses source40 and the compiled05 image. The
[native core continuation](../../verification/native40-core28-cwd-positive/manifest.json)
passes28 whole suites/156 checks; its separately verified foundation prefix adds20
checks, yielding29 suites/176 checks without relabeling the earlier failed runs.
[Model-free Compose and Kind](../../verification/ownedMULTI008/compiled05-baseline-platform-positive/manifest.json)
pass21 whole checks, and [secured Kind](../../verification/ownedMULTI008/compiled05-secured-kind-positive/manifest.json)
passes seven scenarios/51 assertions, including actual credential/certificate and
broker/proxy replacement. The [Calico bootstrap](../../verification/network-policy-kind40-bootstrap12-positive/audit.json)
passes both rollouts. The separate [complete CNI route gate](../../verification/ownedMULTI008/cni-static-gate-positive/audit.json)
now passes all 18 routes with exact image custody and full owned-resource cleanup.

The [compiled05 core attempt](../../verification/final05-core13-first-failure/manifest.json)
remains failed: foundation, wire and store-move passed whole; multi-project passed
eight partial checks before the fixture tried to initialize an unrelated newly
registered project during restart. That additional operation returned
`RESTORE_IO_ERROR`; its underlying cause is unproven. That attempt did not qualify
the original restart assertions. Fixture bootstrap is now restricted to its
initial inventory, preserving explicit admission for later projects and all
original assertions/deadlines. The [fresh ten-suite continuation](../../verification/final05-core13-composed94-positive/manifest.json)
passes all59 checks. Together with the original three whole suites/35 checks,
the original core13 program now covers94 checks with no partial checks counted.
[Native browser qualification](../../verification/native40-ui-whole86-positive/manifest.json)
passes nine whole programs/86 assertions, matching the independently qualified
container browser scope. [Kafka qualification](../../verification/final05-kafka-whole68-positive/manifest.json)
passes all14 whole programs/68 checks. The first full NetworkPolicy route run
[failed before traffic](../../verification/network-policy-kind40-route13-negative/audit.json)
on broker fixture readiness; its underlying Pod cause is unknown. The [observed route15 failure](../../verification/network-policy-kind40-route15-negative/audit.json)
records broker utility exit137 with empty logs; its cause remains unknown and
zero routes were tested. The [route17 runtime capture](../../verification/network-policy-kind40-route17-negative/audit.json)
confirms an actual0.162-second exit137 but encounters an unsupported `kubelet-`
cgroup prefix. The [single-Pod diagnostic](../../verification/network-policy-kind40-utility18-negative/audit.json)
also exits137 under the original192Mi limit. Its supported Pod/container cgroup
paths are unavailable when sampled; no memory counters were obtained and the
cause remains unknown. The [reviewed native startup gate and observer](../../verification/network-policy-kind40-counter19-source-preparation/review.json)
now have a [successful static compile](../../verification/network-policy-kind40-counter19-compile-only/review.json),
with unchanged frozen inputs and no dynamic dependencies. The [bounded native and environment witness](../../verification/network-policy-kind40-counter19-handler-exec01-positive/audit.json)
now passes eight native checks and verifies clock and inherited signal-state
preservation in the admitted image; it does not establish the utility exit cause.
The network-only fixture now follows the recorded static-helper direction below.
Its [complete protocol cross-check](../../verification/network-policy-static-protocol-positive/audit.json)
passes all 25 original observations against native and original Elixir probes,
with both owned container IDs and names independently absent. The earlier
[wrapper timeout](../../verification/network-policy-static-protocol-first-negative/audit.json)
remains failed. The [first static CNI run](../../verification/ownedMULTI008/cni-static-gate-first-failure/audit.json)
reaches Pod readiness but fails its imported-image alias lookup before traffic;
zero routes are qualified and all owned resources are cleaned. After exact
single-child OCI-index diagnosis, the [fresh complete CNI run](../../verification/ownedMULTI008/cni-static-gate-positive/audit.json)
now passes all 18 pre-policy controls and exactly five allowed/thirteen denied
post-policy routes. All nine Pod image chains, post-traffic identities/readiness,
two helper ConfigMap UIDs, namespace cleanup and full disposable-cluster cleanup
are independently verified. This completes the network-only subrequirement;
successor application/Kafka qualification remains separate and open.
The
[full-application recovery attempt](../../verification/final05-recovery25-prefix9-first-failure/manifest.json)
retains nine whole suites/44 checks; the no-default-project crash case failed
with `RESTORE_IO_ERROR` before reaching its requested boundary. Its partial
check is excluded and15 later suites remained unrun in that attempt. The
[source-unchanged diagnostic](../../verification/final05-recovery-phase05-diagnostic/manifest.json)
passes all five original case assertions and observes normal staging/checkpoint/
transport completion; the earlier failure did not reproduce in that diagnostic.
Later [bounded retained-log correlation](../../verification/final05-original-r25-broker-correlation/manifest.json)
also identifies the original failed topic's configuration404 after a creation201;
the diagnostic pass did not disprove that transient provisioning failure.
The [ordinary compiled-image continuation](../../verification/final05-recovery16-prefix13-first-failure/manifest.json)
passes thirteen whole suites/61 checks, then fails before the requested after-cleanup
boundary; two offline-rebind suites remain unrun. Retained broker logs identify
a transient own-topic configuration404 immediately after topic creation201.
Combined with the earlier nine whole suites/44 checks, this proves22 whole
suites/105 checks on compiled05; partial failed-case checks are excluded.
Next: retain the correlated failure/cleanup evidence and fix bounded post-create
metadata readiness in the owning eventing contract before successor qualification.
The original assertion/deadline remains unchanged. The
[proper documentation lifecycle and image bridge](../../verification/ownedMULTI008/final-documentation-compiled05-bridge/manifest.json)
now pass:18 native tests, current receipt verification and exact equality of all
five staged container files,59 application files and33 canonical specifications.
The new receipt is retained separately from the original admission; the compiled
image remains unchanged. [Ten independently complete parent items](../../verification/ownedMULTI008/closed-ten-parent-batch05-review/manifest.json)
are now closed through the proper CLI in dependency order, with current receipt
verification preserved. Six parents remain open;
selective recovery and successor application/Kafka integration remain active.

The [leaf-by-leaf closure review](../../verification/final05-leaf-closure-proposal/review.json)
supports49 additional implementation/evidence checklist closures across the
multi-project and Kafka programs. Historical subsystem tests remain scoped to
their original artifacts and are complemented by exact unchanged-code comparisons
and current integration tests. The [current stale-owner4 audit](../../verification/ownedMULTI008/compiled05-stale-canonical-owner-positive/manifest.json)
now closes the broad canonical-routing evidence leaf alongside the three-server
Kafka federation and callback proofs. The
[compiled configuration crash gate](../../verification/ownedMULTI008/compiled05-config-crash3-positive/manifest.json)
passes all three cases/13 original assertions with unchanged bounds. Two full
selective-recovery leaves remain open, together with the separate integrated
deployment and parent completion gates. The documentation receipt/context bridge
is now independently complete. CNI enforcement is qualified separately; selective
recovery and successor application qualification remain open.

The user has now authorized implementation of all outstanding roadmap work,
grouped in branches with parallel agents. MULTI-001 through MULTI-008 and
KAFKA-001 through KAFKA-009 are the current implementation program. Their
ordered design and acceptance programs are [multiple projects per server](multi-project.md)
and [Kafka pub/sub with optional filtering](kafka-pubsub.md). MULTI-001
contracts are integrated on `roadmap/contracts`; current integration adds complete
Admin subscription edits and checks the final protocol/onboarding inventory. Kafka
deployment and independent acceptance proceed on `roadmap/deployment` and
`roadmap/acceptance`.
`roadmap/integration` preserves the earlier qualified work as baseline commit
`a8f7de8` and integrates the contract, packaging and acceptance branches. A new
disposable implementation candidate under `_build/roadmap/multi/source` now
exercises project-specific stores/workers, admission, hot registry operations,
real Kafka outbox/fanout, optional filters and schema profile2. Independent SDK
acceptance passes project isolation and hard restart, raw/selector fanout,
controlled filter failure/revision and real lost-produce-reply deduplication.
These are development candidates, not final lifecycle qualification. The
[partial progress record](../../verification/multi-eventing-progress.json) binds
their exact artifact/report identities and outstanding gates. Tracker
reconciliation and the start-of-cycle peer survey found no open
ADHD issues/reviews or collectable existing branches.

Admitted image38 has passed [official admission and exact image
payload review](../../verification/project-recovery/development38/admission/manifest.json).
Its [native core composition](../../verification/project-recovery-core38-serial/manifest.json)
covers 169 groups, its [controlled workflow/SDK composition](../../verification/project-recovery/development38/history-second/manifest.json)
covers 117, and its [Kafka matrix](../../verification/project-recovery-eventing38/manifest.json)
passes all 13 suites / 66 checks. The fixed [native and image optimizer experiment](../../verification/multi-eventing/optimizer38-positive/manifest.json)
passes both legs with 172 actual model requests; unsuccessful earlier experiments
remain failed. The reviewed [2.1 wire publication](../../verification/protocol21-publication/manifest.json)
retains the accepted 2.0 snapshots and binds 87 recovery vectors and eight wire groups.

Integrated qualification remains open. [Native38 browser qualification](../../verification/native38-ui-initial/manifest.json)
stopped at a genuine mobile replay-ID overflow; the [painted-text diagnosis](../../verification/native38-ui-overflow/manifest.json)
led to a CSS-only successor39. [Formal host39 admission](../../verification/project-recovery/development39/admission/manifest.json)
now matches the exact artifact used by all nine passing native browser suites;
no image39 was built. The [five image recovery suites](../../verification/project-recovery/development38/image-recovery-cap2/manifest.json)
pass all28 groups under the explicit overlapping-callback resource profile, with
the original failed attempt retained. The [image core run](../../verification/image38-core-initial/manifest.json)
passes ten complete suites but exposes an ownership-verification crash; two later
suites remain unrun. The [narrow successor40 repair](../../verification/ownership40-development/manifest.json)
passes18 native checks and all three public ownership fault/recovery checks;
its [formal host admission and exact image40 payload audit](../../verification/project-recovery/development40/admission/manifest.json) now pass. All59 packaged application files and33 canonical specifications match the staged manifest; [packaged18 and exact-image ownership3](../../verification/project-recovery/development40/image-ownership-positive/manifest.json) now pass. Missing/corrupt Red snapshots preserve configuration/revision/tokens and healthy Blue progress; exact snapshot restoration permits authorized agent creation. Broader image runtime qualification remains open. The [complete native recovery inventory](../../verification/project-recovery/development38/native-final7/manifest.json)
now passes all52 unique whole suites, including all15 actual crash variants. Root
independently verifies its exact original order as13+21+11+7 complete passes. The
three earlier aggregate runs remain failed; their partial suites are excluded.
The final invocation uses the existing `--fixed-baseline` flag for the repaired
query validator. All466 frozen inputs and11 external bindings are unchanged;
this is native38 evidence, without an image or latest-successor qualification claim. The reviewed image filesystem/migration ladder
ran serially with17 original jobs /85 expected checks and all five observers
bound to the passing actual image ABI probes. The [terminal failed run](../../verification/image38-filesystem-plan03-negative/manifest.json) stopped at the after-decision
store-move custody check: the process tuple changed between pre-STOP observations;
the exact differing field was not retained. The tuple includes a whole memory-map
hash, which can legitimately change, so repair that observation guard without
weakening stable process identity or source-bound observer mapping checks. Retain
the failed aggregate,10 complete storage checks and four complete before-decision
move checks; do not count the failed suite's one partial check or14 unrun jobs.
Root independently verifies all21 recorded app containers and five codec helpers
are absent and the complete exact-image container enumeration is empty. The [custody guard repair](../../verification/image-process-custody-preparation/manifest.json) now binds stable process identity and the exact source-bound observer mapping before and after kernel STOP, with39 isolated checks passing. The original failed filesystem aggregate remains false; the [fresh remainder](../../verification/image38-filesystem-remainder01-positive/manifest.json) passes all15 jobs/71 checks with strict independent probe/target absence checks. Combined only with the two earlier whole passing jobs, image38 covers the original17 jobs/85 checks; this does not qualify image40. The [full image40 filesystem run](../../verification/image40-filesystem-current01-positive/manifest.json) now passes all17 jobs/85 checks independently, without counting image38 evidence. Root reverified the complete input/tool closure and all retained hashes, and reconfirmed strict absence of all156 recorded owned IDs/issued names. The [fresh image40 Kafka plan](../../verification/image-kafka-matrix-preparation/image40-current02.json) retains all thirteen original suites and68 current checks with current helpers and image-bound observer proofs. Its [separate private Kafka service](../../verification/project-recovery/development40/kafka-service-bootstrap/manifest.json) has booted successfully, with three actual distinct cluster identities confirmed; the [once-only application matrix](../../verification/image40-kafka-current02-negative/manifest.json) stopped with45 whole checks passing because the no-model outage invocation produced seven checks against an erroneous expectation of nine. Its aggregate remains false. The [fresh missing-check remainder](../../verification/image40-kafka-remainder01-positive/manifest.json) passes the two optional-model checks and fourteen federation checks; together with the original45 whole checks and independently complete seven-check raw outage, the same admitted image now covers all68 original checks. Root reverified every retained report and prior binding plus strict absence of all seven owned handles; this does not qualify live-model semantics or the remaining deployment/security gates. Preparation and isolated
guard checks for all 15 image recovery crash variants, private-network learned
recovery and the actual-image offline rebind adapter have also passed; the [exact-image42-row run](../../verification/ownedMULTI008/recovery40-first-terminal/manifest.json) completed eight whole rows/39 checks, then failed because its crash observer was disarmed by two earlier baseline kills. The original aggregate remains false. A guarded observer rearm preserves all original assertions and deadlines; the [34 failed/unrun rows](../../verification/ownedMULTI008/recovery40-remainder34-terminal/manifest.json) completed all15 crash rows/71 checks, then stopped at a component fixture that rejected Elixir1.20’s successful formatter summary. The original aggregate remains false, all103 owned IDs/names are absent, and the subsequent allocator continuation passes its five original checks before a separate fixture barrier failure. The [terminal eighteen-row continuation](../../verification/ownedMULTI008/recovery40-remainder18-terminal/manifest.json) passes all194 remaining checks. The exact original42-row union now covers309 checks, with earlier failed aggregates retained and no overlap counted. This qualifies the original interpreted image40; compiled05 callback/runtime refresh remains separate. The integrated platform driver and missing-target
selective restore checks pass38 isolated checks while retaining all84 original
platform assertions. The [first repaired40 platform matrix](../../verification/project-recovery/development40/platform-first-failure/manifest.json) stopped after eight whole Compose checks, including same-volume broker upgrade and full cold restore. A selective-restore fixture incorrectly expected Viewer access to Admin-only eventing status; the corrected fixture checks allowed Blue reads and preserves Admin/project denials, with23 isolated checks passing. That Compose aggregate remains false and its Kind leg unrun; the [fresh platform run](../../verification/project-recovery/development40/platform-compose-positive-kind-negative/manifest.json) passes all11 whole Compose checks, including selective restore without VM restart and progress after hub-only replacement. Its aggregate remains false because Kind broker/proxy startup tried uncached registry digests instead of the byte-equivalent imported manifests; the [fresh Kind-only run](../../verification/ownedMULTI008/kind40-positive/manifest.json) now passes all10 whole checks, including real traffic, component replacement, full cold restore, selective Red restore preserving current Blue/security/broker state, retry/ack and namespace/PV cleanup. The11 Compose and10 Kind checks compose only through their exact common admitted artifact/image/staging identities; the prior aggregate stays false. Security, enforcing-CNI and live-model deployment gates remain open. All owned platform resources are independently absent. The [image40 SDK attempt](../../verification/project-recovery/development40/sdk-first-failure/manifest.json) also remains false after its original readiness deadline: bounded diagnostics confirmed the owned running VM and exact payload, but did not prove readiness or a cause. The [transparent original-health recorder](../../verification/project-recovery/development40/sdk-health-first-failure/manifest.json) confirms207 image connection failures through the unchanged30-second deadline, with no HTTP response or owned TCP listener observed in the later bounded snapshot. The native producer reached readiness in24.081seconds; this does not establish a compilation or application initialization cause. All four SDK ladders remain unqualified. The [first native configuration-fault attempt](../../verification/ownedMULTI008/native-config40-first-terminal/manifest.json) also failed before its first mutation: eleven first-install renames each received the fixture's two-second strace delay. The corrected fixture first performs public bootstrap and graceful shutdown on the same real state, then begins the original traced cold startup before publication. The [fresh native configuration-fault run](../../verification/ownedMULTI008/native-config40-positive/manifest.json) passes all three transaction/config/journal kill scenarios with all13 assertions and original45/25/16-second bounds intact; root independently verified the full input closure and absence of all50 recorded trace threads. Exact-image configuration-fault evidence remains separate. Complete
recovery, image/runtime and platform evidence must still pass before parent items close. The older
[source34 review](../../verification/multi-eventing/completion-review-34.json)
remains historical evidence rather than current program completion.

The Kafka pivot replaces
mandatory model matching in the target architecture, retains A2A for agents and
adds per-server Kafka plus Compose/Kubernetes packaging. Complete MULTI-001's
identity design, then KAFKA-001's transport/subscription design before shared
storage and workflow implementation. MULTI-008 waits for KAFKA-009's integrated
qualification. The earlier implementation evidence below remains historical.

The [requirement-by-requirement remaining-work inventory](../../verification/roadmap-completion-audit40/audit.json) binds all99 unchecked queue lines and their supporting-plan obligations to scoped evidence. It preserves incomplete and historical results rather than treating implementation presence as qualification.

The user authorized implementation of all outstanding work in sensible groups.
Work proceeds through authored Component contracts, generated implementation,
independent acceptance and evidence-based closure, preserving existing work.

1. Protocol foundation (PROTO-001), then live configuration and user access
   (CONFIG-002, AUTH-001, ROLE-001). Contracts and retained source passed the
   build lifecycle. Native, browser, staging and Docker acceptance passed.
   Identity edge cases passed with the directory batch. Initial timed-out generation was repaired
   and admitted with explicit retained-source provenance.
2. Federated identity and canonical catalogs/routing (FED-002, FED-003). The
   directory contract, implementation and independent acceptance are qualified.
   All 22 three-hub catalog/routing cases and matching Docker cases passed,
   alongside authentication, protocol, browser and live-model regressions.
3. Contextual evidence (INFO-002), semantic scans (QUERY-001) and contextual
   retrieval (SEARCH-001) and fallback/audits (SEARCH-002) are qualified. Continue
   with feedback/replay (SEARCH-003) and adaptive index qualification (INDEX-001).
4. Upstream accepted-source export correction (BUILD-001), with local regression
   evidence and a reviewable upstream contribution; external filing/publication
   remains subject to the existing authorization boundary.

Only evidence-qualified items may be closed. No batch completion is implied by
this execution order or by specification changes alone.

Foundation evidence so far binds executable SHA-256
`a427322b535084eb8d1767a25905709dd444053a91d55268c02b3407a160a7c0`:
`verification/foundation-acceptance.json` (20 cases),
`verification/auth-lifecycle.json` (9 cases including real session expiry),
`verification/config-recovery.json` (3 actual process kills at commit boundaries),
`verification/protocol-acceptance.json` (5 groups with independent schema validation),
`verification/foundation-sdk.json` (31 scenarios including real model and legacy upgrades),
`verification/foundation-federation.json` (26 scenarios including real three-hub discovery),
and both foundation/legacy browser reports (desktop/mobile). New Users and Settings
captures were visually reviewed. `verification/oidc-policy.json` adds four profile,
email-separation and group-policy scenarios. `verification/foundation-container.json`
passes all 20 new scenarios and `verification/foundation-container-regression.json`
passes 34 scenarios including the documented runner, hot port/health, password
rotation, container replacement, backup/restore and live Nemotron coordination.
`verification/foundation-staging.json` passes four integrity/determinism checks.
Docker image: `sha256:c0f03874144d3de3a9f5e958c8493b6dbc98c06ff0eec04bdff1e7170cea4946`.
`verification/foundation-container-federation.json` passes 25 container peer scenarios.
This first baseline preceded the directory extensions qualified below.

Directory-batch completion evidence binds executable SHA-256
`048ca679f9275380cc6235ad655d07992d0c076b8a2c27f3d0d117978daa62a3`,
qualified receipt `sha256:3c9ba41fb59c94caaa0cfdee68f591762546e29bdffac2fbb97e19e81196d7f6`,
and Docker image `sha256:ef1894b80747a2f1f7e0de8f70a84f00351e29440180048a7241c530c85d36d5`.
`verification/directory-catalog.json` and `directory-container-catalog.json`
each pass 22 independently authored catalog, canonical-routing, identity and fault
cases. `directory-foundation.json` and `directory-container-foundation.json`
each pass 20 account/role/live-setting cases. Native `directory-auth.json` (9),
`directory-recovery.json` (3 process-kill boundaries), `directory-credentials.json`
(4) and `directory-oidc.json` (5) cover bootstrap, rotation, recovery, legacy keys,
OIDC profiles/group policy and renamed built-in account protection.
`directory-sdk.json` passes 31 scenarios including both real earlier-store upgrades
and live Nemotron; `directory-federation.json` passes 26. `directory-protocol.json`
passes five independent schema/OpenAPI/framing groups for API profile1.1.0,
wire major1 and A2A1.0. `directory-browser.json` and `directory-console.json`
pass desktop/mobile interaction and privacy checks with no normal-path errors;
ready-state catalog and Admin query-control captures were visually reviewed.
`directory-container-sdk.json` passes 34 scenarios including hot port/health,
rotated credentials, container replacement and backup/restore;
`directory-container-federation.json` passes 26 including live three-hub inference.
`directory-staging.json` passes four integrity/determinism checks. All these report
paths are under `verification/`. The build passed 13 native cases and 13 independent
CLI vectors; all declared verify gates passed at this baseline. Subsequent context
contracts and candidates have separate qualification and do not change this evidence.

Subscription matching retains the selected short-response Nemotron decision
model. The user clarified that new data needs a fast, decisive match/no-match
judgment; no Qwen deployment or generative step belongs in that path. Historical
query requirements remain separately scoped and do not justify replacing the
subscription matcher. Current-model latency smoke results are recorded separately
from workload-wide accuracy or capacity claims.

## P0

### [x] ONBOARD-001 — Establish the information hub's product requirements

- **Owner:** project mission and documentation
- **Direction:** Build an A2A information hub for indirect agent communication, information publishing, natural-language subscriptions, and agent queries/search.
- **Conclusion:** Record the product requirements and acceptance scenarios in PROJECT.md before choosing protocol bindings, persistence, or a matching model. This item establishes intent; runtime implementation remains separate work.
- **Depends on:** none
- **Implementation:**
  - [x] Record the project mission, required behaviors, acceptance scenarios, and unresolved implementation decisions in PROJECT.md.
  - [x] Replace product documentation placeholders with an accurate description and current implementation status.
- **Evidence:**
  - [x] Review requirements against the user's direction and pass project authority and lock verification: `litai verify --gate authority --gate locks` passed both gates. The matcher identity remains an explicit open decision, not a selected dependency.

Check the parent only after every required subtask and evidence item passes. Add the
release-visible outcome to `CHANGELOG.md`; Git preserves prior queue states.

### [x] CONFIG-001 — Default to Elixir

- **Priority:** P0
- **Owner:** project configuration
- **Direction:** Use Elixir as the default implementation language in this project.
- **Conclusion:** Install the bundled lang-elixir Flavor and replace the Python default; remove the Python-only pip packaging default while retaining Make and macOS.
- **Depends on:** none
- **Implementation:**
  - [x] Install lang-elixir and update default selectors.
  - [x] Refresh the sample Component lock for the new defaults.
- **Evidence:**
  - [x] Project authority and lock verification pass with Elixir selected and no Python-only packaging default: `litai verify --gate authority --gate locks` passed both gates; sample lock refreshed by `litai lock samples/hello-component`.

### [x] MATCH-001 — Clarify Jev-style subscription matching

- **Priority:** P0
- **Owner:** project mission and documentation
- **Direction:** Use the supplied Jev reference to clarify the model class intended for subscription matching.
- **Conclusion:** Specify semantic classification with typed probabilities from publication context and subscription criteria; keep provider, model version, thresholds, and failure policy open.
- **Depends on:** none
- **Implementation:**
  - [x] Update matcher requirements and documentation using primary Jev documentation: https://docs.typesafe.ai/primitives. PROJECT.md records typed relevance probabilities, hub decision policy, and independent subscription questions.
- **Evidence:**
  - [x] Verify source-supported matcher semantics and pass project authority and lock checks: `litai verify --gate authority --gate locks` passed both gates. Provider, threshold, uncertainty handling, and failure policy remain open decisions.

### [x] SCOPE-001 — Define the first shared-project coordination scope

- **Priority:** P0
- **Owner:** project mission and documentation
- **Direction:** Accept the proposed first-version defaults and start with two agents coordinating work on the same project.
- **Conclusion:** Record one private hub with durable storage, polling and acknowledgements, a replaceable Jev-style matcher, new-publication subscriptions, agent text/JSON publishing, and basic search. Define coordination examples and restart/reconnect acceptance without choosing an agent client or deployment.
- **Depends on:** none
- **Implementation:**
  - [x] Update PROJECT.md and product documentation with accepted scope and the two-agent workflow, including offline catch-up and restart/acknowledgement acceptance scenarios.
- **Evidence:**
  - [x] Review coverage of accepted defaults and verify project authority and locks: `litai verify --gate authority --gate locks` passed both gates. Runtime implementation remains pending.

### [x] INTEGRATE-001 — Select initial A2A test peer and decision model

- **Priority:** P0
- **Owner:** project mission and integration requirements
- **Direction:** Use a simple compliant A2A test agent and the available internal Nemotron Deciffusion 8B v2.1 decision model instead of requiring Jev access.
- **Conclusion:** Inspect official A2A samples and model repository metadata; record the initial model choice, verified inference dependencies, and remaining serving prerequisites without downloading weights or starting compute.
- **Depends on:** none
- **Implementation:**
  - [x] Inspect model README/configuration and official A2A sample documentation; source identities and integration findings are recorded in docs/architecture/model-integration.md.
  - [x] Update project requirements and integration guidance with selected dependencies and unresolved serving details. Initial model selected; live serving is tracked by SERVE-001.
- **Evidence:**
  - [x] Source-check integration claims and pass project authority and lock validation: `litai verify --gate authority --gate locks` passed both gates; the documented relevance request parses as JSON. No live inference or A2A interoperability run is claimed.

### [x] SERVE-001 — Validate a reachable Nemotron inference service

- **Priority:** P0
- **Owner:** private inference deployment
- **Direction:** Test locally when appropriate or use one of the offered private GPU hosts.
- **Conclusion:** After the user-managed reboot, host and container GPU discovery both pass with matching driver 595.99.02. The selected RTX 4090 host has about 23 GiB free VRAM and 135 GiB free root disk. Prepare an isolated loopback-only inference service without changing existing workloads.
- **Depends on:** none
- **Implementation:**
  - [x] Check serving footprint and isolate the model runtime and checkpoint. The digest-pinned image is running with a read-only BF16 checkpoint mounted, dynamic FP8 quantization, a 60% GPU-memory budget, and loopback-only access. Transfer and on-host SHA256 checks matched the pinned internal checkpoint. The user-managed reboot resolved the driver mismatch.
  - [x] Run a healthy service and record a real relevance request/response with the selected checkpoint. `/health` returned `ready: true`; two real publication cases returned typed Noul probabilities. Exact requests, responses, and identities are in verification/deciffusion-smoke.json.
- **Evidence:**
  - [x] Validate positive and negative project-update judgments and record the exact runtime/checkpoint identity: API-change relevance 0.985936 versus outage relevance 0.003173; the outage case ranked outage relevance highest (0.997199) but also scored API relevance 0.798187. This is serving/response evidence, not a production threshold or calibrated-quality claim. `litai verify --gate authority --gate locks` passed both gates.

### [x] HUB-001 — Implement the first durable A2A coordination hub

- **Priority:** P0
- **Owner:** hub Component, protocol contract, and acceptance
- **Direction:** Build the agreed first working hub with two agents sharing project updates, subscriptions, queued delivery, messages, search, and restart recovery.
- **Conclusion:** Author the hub Component and precise A2A contract, generate an Elixir implementation through the installed lifecycle, and verify it with independent two-agent clients and the live Nemotron endpoint. Keep runtime data private and persisted; bind test services to loopback. User approval of the implementation plan includes local build and execution for acceptance.
- **Depends on:** none
- **Implementation:**
  - [x] Define the A2A operation and durable-state contract and resolve the hub generation plan: components/hub/component.md and its generated lock resolve Elixir/Make/macOS; CLI oracle bound to the exact specification identity.
  - [x] Rebind the stale Standard installation identity using reviewed plan sha256:a7615db8b45aa3c16a0f09ce114832c787ed64372e4e85a17be2720ae65d586a. Installed version remains 1.2.0 and the policy/evidence requirements are unchanged. The first build stopped safely before generation.
  - [x] Record local workflow limitations: `project.peer_work_git_failed` because HEAD has no commit; tracker inspect reports forge unsupported and no remote. No branch, merge, push, or remote CI action was attempted.
  - [x] Generate and build the Elixir service and its native tests. The clarified Component generated an Elixir implementation; all 10 native cases passed. A stable-authority rebuild recorded a passing lifecycle receipt. Native and verifier-owned argument vectors were checked to remain distinct. Accepted source is published to the committed source-cache target.
  - [x] Run independent two-agent protocol, failure, isolation, idempotency, and restart tests, including real Nemotron matching: all 16 black-box checks passed using a2a-sdk 1.1.0. Evidence: verification/hub-acceptance.json. A dropped private model tunnel caused the first live attempt to time out; reconnecting restored the healthy endpoint and the complete suite passed.
  - [x] Document runnable setup and product usage and retain passing evidence. Setup/API guides and the SDK helper are verified, including integer-limited polling through JSON text parts. Ordinary build/run export is verified, and its artifact hash matches the 16-case independent report, including a real unrelated publication check. The starter sample catalog audit was refreshed. Strict accepted-source-only continuation reported source_cache.runtime_absent after oracle reconciliation; no gate was bypassed, and the documented ordinary build reuses and verifies the source candidate. The private prototype is running; credentials and durable data are ignored by Git.
- **Evidence:**
  - [x] Hub build/native tests and independent A2A SDK scenarios pass: 10 native cases and 16 SDK scenarios, persistent unacknowledged delivery after hard kill, acknowledgement retention, model failure/recovery, and live Nemotron coordination. verification/hub-acceptance.json binds the exact exported artifact SHA256. `litai verify` passed authority, both locks, and receipt; source-intelligence and HTML gates are skipped by configuration. Start/end peer surveys and the read-only GC plan cannot run without an initial Git commit; no remote forge/CI is configured, and no cleanup, push, or merge was attempted.

### [x] SKILL-001 — Describe agent coordination through the hub

- **Priority:** P1
- **Owner:** project agent skill and usage documentation
- **Direction:** Provide a reusable skill for startup subscriptions and polling, ongoing work updates, and processing and acknowledging deliveries.
- **Conclusion:** Add a project-owned client skill using the existing A2A helper and API contract, linked from the project guide; preserve explicit polling, agent identity, and durable acknowledgement behavior.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Write and link the three-step coordination skill with setup, retry, and acknowledgement guidance: skills/agent/coordinate-via-hub/SKILL.md, referenced in docs/README.md.
- **Evidence:**
  - [x] Validate skill structure and links and run project authority and lock checks: skill-creator quick_validate passed; all three linked files exist; command and delivery fields reviewed against the hub contract; litai verify --gate authority --gate locks passed. Start/end peer surveys remain unavailable because Git HEAD has no initial commit; no remote forge is configured.

### [x] DEPLOY-001 — Run the hub service in a container

- **Priority:** P1
- **Owner:** hub deployment specification and packaging
- **Direction:** The hub service should run containerized.
- **Conclusion:** Provide a containerized deployment of the Elixir hub with durable storage outside the container, private runtime configuration, and connectivity to the separately served matcher. Implemented an isolated Linux Docker runtime for the accepted portable Elixir script, retaining macOS/Make/Elixir authoring defaults. Host networking preserves the loopback-only service contract; configuration and storage stay outside the image.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Define the container deployment contract and required target Flavors: docs/admin/operations.md records the Linux Docker runtime, pinned Elixir/OTP realization, host networking, and persistent data boundary. The existing Elixir/Make/macOS Flavors produce portable source; packaging does not claim a native Linux cross-build.
  - [x] Add a reproducible container image and documented startup, configuration, persistent-volume, health-check, and shutdown procedures: deploy/Dockerfile, deploy/health.exs, deploy/run.sh, scripts/stage_container.py, and scripts/configure_hub.py. A deterministic payload archive removes Docker copy-layer timestamp variance. Two independent no-cache builds produced the same image identity; verification/container-reproducibility.json records inputs and builder versions.
- **Evidence:**
  - [x] Run two-agent coordination against the containerized hub and verify queued deliveries and acknowledgements survive container replacement with the same persistent volume: all 20 checks passed, including real Nemotron matching, hard-kill restart, documented runner startup, container replacement, offline backup/restore, and rollback. Evidence: verification/container-acceptance.json.
  - [x] Verify the container can reach the configured matcher without embedding credentials or model weights in the hub image: live Nemotron SDK coordination passed. The staged context contains only a Dockerfile, a hash manifest, and a deterministic archive of the accepted script, health probe, contract, and manifest. Server credentials are mounted read-only; the model and data remain external. Private config isolation, exclusive creation, artifact drift rejection, and archive identities were checked.

### [x] DOCS-001 — Provide complete service documentation

- **Priority:** P1
- **Owner:** project README and service documentation
- **Direction:** Provide a README, user documentation, admin documentation, and troubleshooting documentation.
- **Conclusion:** Review and extend the existing project README and prototype guides into a coherent documentation set for hub users and administrators. Document actual supported behavior and incorporate container deployment instructions when DEPLOY-001 is implemented. The root README and connected user, admin, and troubleshooting guides are written. Container and recovery procedures, documentation navigation, native build, and full project verification all passed.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Review existing documentation and update the README with the service purpose, capabilities, quick start, and links to user, admin, and troubleshooting guides: README.md and docs/README.md now route each audience to the appropriate guide.
  - [x] Complete user documentation for agent setup, authentication, the coordination skill, subscriptions, publishing, messaging, polling, acknowledgements, and search: docs/user/using-the-hub.md connects client setup and the coordination loop to the existing API examples.
  - [x] Add admin documentation for installation, containerized operation coordinated with DEPLOY-001, configuration, credentials, persistent storage, backup and restore, upgrades, monitoring, and matcher connectivity: docs/admin/operations.md.
  - [x] Add troubleshooting documentation for startup failures, authentication errors, missing or delayed deliveries, matcher outages, connectivity problems, and storage or recovery failures: docs/admin/troubleshooting.md.
- **Evidence:**
  - [x] Verify documented commands and examples against the supported service and check documentation navigation and project authority: configuration, staging, build, startup, health, SDK coordination, and recovery commands were exercised; guide links resolve. Verified staging exactly reproduces the tested input manifest/archive and rejects artifact drift. The native build passed all 10 cases; litai verify passed authority, both locks, and the current receipt, with source-intelligence and HTML gates skipped by configuration. Start/end peer surveys and GC planning remain unavailable without an initial Git commit, and tracker reconciliation is skipped because no remote forge is configured; no push, merge, or shared Docker cleanup was attempted.
  - [x] Exercise the documented administrator startup, backup and restore, and recovery procedures; verify container-specific instructions after DEPLOY-001 is implemented: the independent container suite invokes the actual runner and configuration tool, replaces containers over the same data, restores an offline backup, and rolls back to the preserved pre-restore data. All four operations checks and the original 16 SDK scenarios passed.

### [x] INFO-001 — Store and retrieve information from agents and future external sources

- **Priority:** P1
- **Owner:** hub information model, ingestion, subscriptions, and search
- **Direction:** Store client-submitted information for future searching, initially agent messages and status updates, and later messages from email, Slack, Teams, and other sources; allow subscriptions and search across this information.
- **Conclusion:** Extend the existing durable publish/search path into a common information model with source and content metadata. Start with agent messages and status while preserving arbitrary JSON content. Keep private addressed-message visibility distinct from project-published information. Future external connectors should use the same storage, subscription-matching, and search path. Implemented information type, source provenance, occurrence time, retrieval by ID, source/type filters, and source-item deduplication while retaining DETS as approved. The original prototype store upgrades without losing accepted state. A verified container is running with private per-agent client files and a live-testing guide. Live external connectors remain subsequent work; synthetic external-origin information already uses the shared contract.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Defined in components/hub/component.md and the named components/hub/information/spec.md boundary; includes arbitrary JSON values, immutable history, bounded metadata, authenticated author identity, and project/private visibility rules.
  - [x] Generated the extended Elixir runtime through the installed lifecycle. The first candidate had an HTTP-handler syntax error; lifecycle repair produced the accepted implementation. All 8 native cases and 6 private CLI acceptance vectors passed, with distinct native/oracle arguments.
  - [x] The matcher receives complete envelopes and deliveries retain type, source, and event time. Independent fixture checks and live Nemotron status delivery verify this path, retention after ack, and retry deduplication.
  - [x] Added get by publication_id and exact information_type/source_kind/source_id search filters, including filter-only searches. Existing query-only and publish clients retain their shapes and behavior. Private delivery IDs cannot be retrieved through get or search.
  - [x] Documented in docs/user/stored-information.md, API/user/admin guides, the coordination skill, and docs/user/live-testing.md. Future adapters must map upstream visibility, source/event or revision IDs, original timestamps, and retries into the same authenticated contract. No live connector integration is claimed.
- **Evidence:**
  - [x] 24 independent host SDK scenarios passed, including arrays/scalars/null, source/type filters, archive retention after ack, hard restart, and source-item retries. Evidence: verification/hub-acceptance.json. A real store produced by the original runtime retained history, inboxes, ack state, pending jobs, and original idempotent results after upgrade.
  - [x] 27 container scenarios passed, including the original protocol/restart suite, all information-archive scenarios, real Nemotron matching, documented runner, replacement, backup/restore, and rollback. Evidence: verification/container-acceptance.json. Independent no-cache image builds matched; verification/container-reproducibility.json binds the tested source and both specification roots.
  - [x] Synthetic Slack-origin publication matched, delivered, and remained searchable through the common contract. The deployed container passed the live status/archive smoke test; verification/live-mvp-smoke.json records the result. Cold backups preserve the prior local runtime/config/store and the pre-upgrade data. Private client files are under .adhd/mvp/. Full litai verify passed authority, both committed locks, and the current receipt; source-intelligence and HTML gates are skipped by configuration. The deployed container also retained history and acknowledgements across restart. Source is published to the committed cache. Start/end peer surveys and GC planning remain unavailable without an initial Git commit; no remote forge is configured, so no tracker reconciliation, push, merge, or shared cleanup was attempted.

### [x] UI-001 — Add a simple web management and observation UI

- **Priority:** P1
- **Owner:** hub web interface and administrator API
- **Direction:** Provide a simple web management and observation UI for the service.
- **Conclusion:** Implemented the four-view console and separate administrator API, durable management retry records, credential isolation and metadata-only observation of private deliveries. Fresh normal-build generation preserves the original schema-2 source-event index; the first candidate's migration defect was caught by a real old-runtime upgrade check and corrected in the canonical contract. Verified the exported artifact in hardened containers and a real browser, then replaced the private MVP using an offline backup. The same image retained agent state across restart.
- **Depends on:** INFO-001
- **Implementation:**
  - [x] Defined Overview, Information, Subscriptions and Activity in components/hub/management/spec.md; registered the named specification root.
  - [x] Separate optional admin_token, legacy-disabled API, agent/admin token separation, memory-only browser credential, same-origin checks, strict CSP, redacted diagnostics, and delivery metadata without private bodies.
  - [x] Implemented embedded assets and nine admin operations, including confirmed subscription removal and pending-job retry; mutation IDs persist atomically across restart. Normal build exports the tested candidate.
  - [x] Added docs/admin/web-console.md, updated operations/troubleshooting/navigation/live-testing guides and the private configuration helper; the helper provisions a separate mode-0600 administrator token.
- **Evidence:**
  - [x] Two-agent fixture and live deployment checks passed; verification/web-console-browser.json covers message/status/search/details, queued deliveries and simulated outage. verification/web-console-live-smoke.json covers real matcher health and unchanged live agent state after replacement and restart.
  - [x] 31 SDK scenarios passed (verification/hub-acceptance.json), including invalid admin configuration, auth/origin boundaries, disabled legacy configs, private visibility, durable action retries/conflicts and both earlier store formats. Browser confirmation cancellation and response-loss retry passed; deployed responses/logs contain no bearer tokens.
  - [x] Desktop/mobile screenshots and accessibility snapshots inspected at 1440 and 390 pixels: no overflow or normal-path page/console/network errors. Fault-injected 503/401/network loss recovered as intended. 12 native tests, eight independent CLI vectors and 33 hardened-container scenarios passed; independent no-cache image builds matched (verification/container-reproducibility.json). Full litai verify passed authority, both locks and current receipt; source-intelligence and HTML gates are skipped by configuration, with the UI independently checked in Playwright. Accepted source is published to the committed cache. Peer surveys and tracker reconciliation remain unavailable without an initial commit or configured remote; no commit, push, merge or shared cleanup was attempted.

### [x] AUTH-001 — Administrator authentication with local username/password and optional OIDC

- **Priority:** P1
- **Owner:** hub administrator authentication and web management interface
- **Direction:** Add optional OpenID Connect (OIDC) authentication for administrator pages, retaining compatibility with the current admin key. Include a dummy, simple local username/password provider for use before OIDC is set up. The built-in admin account uses this provider, receives a random password at first install, and saves that initial password in a discoverable text file.
- **Conclusion:** Plan interchangeable local username/password and OIDC sign-in providers for the administrator console and its supporting API. The local provider supports bootstrap and development before an identity provider is configured; bootstrap the built-in `admin` account with a cryptographically random per-install password rather than a universal hard-coded login. Save the initial password as `initial-admin-password.txt` beside the hub configuration file, so its location follows the selected configuration storage location. Keep authentication state hashed; the explicitly requested bootstrap text file is the exception for first-admin discovery. Preserve existing admin-key installations. Configure providers and credentials through CONFIG-002's admin Settings with hot activation and rotation. Selecting OIDC must not silently enable password/key fallback on provider failure; coexistence is explicit. ROLE-001 governs each user's server-local role and agent ownership; authenticating does not itself grant agent impersonation. Use the same authenticated user identity for Admin, Developer and Viewer, with authorization governed by ROLE-001. Provider selection, bootstrap, authorization and sessions are qualified natively and in Docker; next action is to preserve the built-in account identity through username edits and complete federation identity boundaries. OIDC setup includes assigning provider groups to the server roles in ROLE-001, with Admin-managed group lists and highest-role resolution. The first implementation batch is in qualification.
- **Depends on:** UI-001
- **Implementation:**
  - [x] Define explicit authentication-provider selection, local username/password bootstrap, optional OIDC configuration and backward compatibility for existing admin-key server/client configurations.
  - [x] Populate every user's `name` and `email` profile fields and retain a link to their OIDC provider when OIDC-backed. Store the configured provider reference plus validated issuer and subject (`iss`, `sub`) as the external identity link; map name/email from validated claims. Specify collection of missing claims and bootstrap profile details through the admin page without fabricating email addresses. Local-provider accounts, including initial `admin`, can exist before OIDC setup and have no OIDC link until explicitly linked.
  - [x] Specify a simple local username/password provider using the same administrator identity/session boundary as OIDC, password hashes in authentication state (with the explicit initial-password text-file exception below), generic failed-login responses and no credential logging or universal default password.
  - [x] On first installation create the built-in `admin` account in the simple local provider, generate its password using a cryptographically secure random source, persist its password hash, and save the initial plaintext password in `initial-admin-password.txt` beside the configuration. Restrict the text file to the owning operator (0600 on Unix or equivalent); report its location without logging its contents. Do not expose the password through the admin page, APIs or diagnostics.
  - [x] Preserve the built-in account's local-provider identity across username/profile edits, so renaming cannot bypass the prohibition on linking the bootstrap account to OIDC.
  - [x] Provision bootstrap credentials only once: preserve the account/password across restarts, upgrades and container replacement, never overwrite an existing initial-password file or silently reset a changed password. Document where host operators find the file through the persistent configuration-directory mount, and that it records the initial password rather than tracking later rotations.
  - [x] Add local-provider selection and credential setup/rotation to the admin page through CONFIG-002; apply changes without restarting and define session revocation when credentials change.
  - [x] Specify OIDC sign-in/callback, identity and token validation, administrator authorization rules, protected API access, session expiry/logout and request-forgery protection. Define explicit key/OIDC coexistence policy; avoid silent fallback when an explicitly selected OIDC mode fails.
  - [x] Include group-to-role mapping in OIDC setup: let Admins add and remove one or more OIDC groups for each of Admin, Developer and Viewer, and configure the provider's group-claim field. Use group membership from validated OIDC identity claims, bound to the configured provider. Resolve all matching mappings to exactly one role using Admin > Developer > Viewer; missing, malformed or unmapped claims must not elevate access.
  - [x] Implement optional OIDC protection for administrator pages and their supporting API while preserving administrator permissions, private-message visibility boundaries and existing A2A agent authentication.
  - [x] Document local username/password setup before OIDC, provider selection and transition, OIDC secrets/redirect URLs, session/logout behavior and troubleshooting; retain the existing admin-key setup path.
- **Evidence:**
  - [x] Verify a clean install provisions `admin` with a working random password in the documented owner-readable text file; separate installations receive different passwords. Verify secure file permissions, no unintended plaintext copies/logging/API disclosure, no overwrite on restart/upgrade/container replacement, and preservation of a password changed through the admin page.
  - [x] Verify local username/password sign-in works without an OIDC provider; reject incorrect credentials, enforce logout/session expiry and exercise hot credential rotation and revocation without leaking passwords.
  - [x] Verify the unchanged default admin-key flow with OIDC unconfigured, including existing configurations and agent workflows.
  - [x] Exercise local-to-OIDC transition and explicit coexistence from admin Settings without a restart; an OIDC outage must not silently reactivate the local provider.
  - [x] Exercise OIDC sign-in, allowed and denied administrator identities, invalid or expired identity tokens, callback validation, session expiry/logout, provider failures and absence of credential leakage.
  - [x] Verify local/OIDC users retain name/email profile fields and correct provider links; a changed name or email must not change the internal user identity, role or agent ownership. Verify distinct issuer/subject identities within one server are not merged automatically by matching email, missing claims have an explicit profile-completion path, and linking a local account requires authorized proof rather than an email match. Separately permit FED-002's cross-server same-email identity correlation without transferring local roles or permissions.
  - [x] Verify Admin-only group mapping from OIDC Settings, multiple groups on a role and memberships matching multiple roles; enforce highest-role resolution, reject untrusted group claims and apply mapping removal/changes live without retaining stale elevated access.
  - [x] Verify browser and direct API access enforce the selected authentication mode and preserve management-action safety and private-data boundaries; pass applicable project, SDK, container and desktop/mobile browser checks.

Qualified profile-1.1 completion evidence: see the directory-batch evidence above.

### [x] NAME-001 — Use Agentic Distributed Harness Depot consistently in documentation and help text

- **Priority:** P2
- **Owner:** project naming, documentation and hub user-facing text
- **Direction:** Expand ADHD as Agentic Distributed Harness Depot, using Depot rather than Database, and update documentation, help text and related user-facing references accordingly.
- **Conclusion:** Implemented Agentic Distributed Harness Depot (ADHD) as the full product name across documentation, helper help, component display metadata, browser title/sign-in/authenticated brand and Agent Card description. The exact CLI describe response and existing adhd/ADHD identifiers remain compatible. The tested container is deployed using the existing credentials and store, with an offline pre-update backup. Evidence: verification/name-acceptance.json.
- **Depends on:** none
- **Implementation:**
  - [x] Inventoried the named product surfaces; verification/name-acceptance.json records the current documentation set and three public helper help checks. Generic hub/database terminology and technical paths remain descriptive or stable identifiers.
  - [x] Updated project goals, README/guide introductions, agent coordination skill, helper descriptions and component display metadata; added components/hub/presentation/spec.md to own exact public presentation. Preserved legitimate database terminology and historical evidence.
  - [x] Generated and qualified the runtime through litai, exported its tested artifact, included the presentation specification in the container manifest and published accepted source to the committed cache. Updated CHANGELOG.md. Deployed without changing credentials, container name or data paths.
- **Evidence:**
  - [x] Naming inventory and three helper --help outputs passed; full litai verify passed authority/documentation review, both locks and the current receipt. Tracker and peer surveys remain unavailable without a configured remote or initial commit; no commit, push or merge was attempted.
  - [x] Five native cases and eight independent CLI vectors passed, as did 31 SDK and 33 hardened-container scenarios, including real model matching and both earlier store upgrades. Exact describe compatibility and Agent Card naming passed. Playwright desktop/mobile screenshots and accessibility structure confirmed the full name fits with no normal-path page, console, network errors or document overflow; search/details, subscription create/cancel/remove, guide toggle and logout/reload passed. Independent no-cache image builds matched. Live agent state and existing credentials were preserved. Reports: verification/name-acceptance.json and its linked evidence. Source-intelligence and HTML gates are skipped by project configuration; browser inspection was performed independently.

<a id="info-002-preserve-contextual-evidence-without-a-domain-taxonomy"></a>

### [x] INFO-002 — Preserve contextual evidence without a domain taxonomy

- **Priority:** P1
- **Owner:** hub information model and persistence
- **Direction:** Retain full agent statements and their context so future questions and re-indexing do not require predicted data buckets.
- **Conclusion:** Implemented immutable contextual records, corrections, bounded frozen public traversal and checksummed crash-recovery snapshots. Originals remain authoritative and private deliveries remain excluded. The [qualified artifact evidence](../../verification/context-qualified.json) completes this item; semantic history questions and adaptive retrieval retain their separate unchecked gates.
- **Depends on:** INFO-001
- **Qualification evidence:** Retained-source artifact SHA256 `660745edc3b48aad037ec51e7a0745f30eb1973ad4fd20a7c20808666c8f2885`, receipt `37fcf7c06086c723efa95d2be13e2b451f5393df4c553d507b9e66dd45ea5592`, and Docker image `b7b03facd0d3e6b7ba1b2a68eb33d1bfc682b44ff5308e05885ce95eb2489f9e`. Twenty hash-bound reports cover eight record cases, ten actual crash/integrity cases, both earlier native store producers and native-to-container snapshot upgrade, native/container SDK and live three-hub federation, 22-case catalogs on both runtimes, profile 1.2 schema/OpenAPI conformance, authentication/configuration recovery and desktop/mobile browser checks. All required results pass; the aggregate preserves the corrected independent-test preconditions and profile assertion.
- **Implementation:**
  - [x] Specify optional question, reply, conversation and subject references with contextual snapshots, provenance and bounded authorized link traversal; preserve arbitrary text/JSON and unknown domain concepts.
  - [x] Implement immutable corrections and evidence relationships, stable content identities, legacy-store compatibility, retry semantics and durable storage without replacing original statements with extracted facts.
  - [x] Document context submission and re-indexing semantics, including missing references, cycles, changed external sources and private-message isolation.
  - [x] Recover interrupted DETS writes from a checksummed synchronized state snapshot; a real hard-kill federation run exposed a `needs_repair` startup failure. Preserve acknowledged state and reject corrupt, conflicting or wrong-project recovery data.
- **Evidence:**
  - [x] Round-trip Yes with its question and subject, cardinal/red-bird reports, arbitrary JSON and a later correction across retries, acknowledgements and hard restart.
  - [x] Upgrade existing stores without data loss; reject unauthorized context expansion and demonstrate reconstruction of the exact evidence used by a historical query.

### [x] QUERY-001 — Evaluate natural-language questions by scanning contextual history

- **Priority:** P1
- **Owner:** hub query evaluator and A2A query jobs
- **Direction:** Answer unforeseen questions from original evidence without requiring a purpose-built index.
- **Conclusion:** Implemented owned asynchronous snapshot history questions using the existing short-response model, original contextual evidence, durable costs/checkpoints, bounded joint assessment and explicit uncertainty. The [qualified history evidence](../../verification/history-qualified.json) completes this item. Search acceleration and adaptive indexing retain four separate open gates.
- **Depends on:** INFO-002
- **Implementation:**
  - [x] Define natural-language query requests, scope/snapshot identity, asynchronous job lifecycle, budgets, continuation, cancellation, idempotency and authorized result retrieval.
  - [x] Evaluate all records in the scope with context expansion and cross-record synthesis; retain supporting and contradicting source IDs, uncertainty, evaluator versions and examined/remaining coverage.
  - [x] Implement durable checkpoints and explicit partial, unavailable, conflicting and no-evidence outcomes; keep inference outside the store writer and literal search compatible.
- **Evidence:**
  - [x] Answer bird presence, explicitly reported species/color and distinct-bird count without domain columns; handle corrections and evidence requiring multiple linked records.
  - [x] Exercise hard restart, timeout, malformed model results, cancellation, concurrent publication and budget exhaustion; never report incomplete scans as exhaustive or missing evidence as false.
  - [x] Validate a real configured evaluator against independently labeled fixtures; existing typed subscription relevance alone must not qualify as answer synthesis.
- **Qualification evidence:** Retained-source artifact SHA256 `b34659b630e8d911a43817b725857032b6ade422f49807247fb6206c553469a1`, receipt `4bdc40333a68a3a4de62eae3d50704a3e25222c8a9ac40a382e733e2b8e6a9fb`, Docker image `6d1f800d3719fd9edafe8da4b1e8978eb7a6815ddc0ea111ee6075f980f9234e`. Twenty-seven hash-bound reports cover 14 native and 14 Docker lifecycle/fault groups, 22 independently labeled real-model questions on each runtime (13 development, nine held out), four official-SDK/current-and-earlier-store producers, actual prior-template evidence preservation, ten storage interruption/integrity cases, original-context/legacy upgrades, live federation, catalogs, auth/configuration, protocol 1.3 and desktop/mobile controls. All required results pass. Bounded input/state limits and model fallibility remain explicit; fixture/development corrections are retained in the aggregate.

### [x] SEARCH-001 — Build replaceable general-purpose contextual retrieval

- **Priority:** P1
- **Owner:** hub retrieval adapters and derived index lifecycle
- **Direction:** Retrieve unforeseen questions without requiring users to predict indexes or classify incoming publications.
- **Conclusion:** Implemented native contextual BM25, bounded typed semantic relevance, owned frozen retrieval jobs and asynchronous versioned index rebuilds with hot Admin controls. The [qualified retrieval evidence](../../verification/retrieval-qualified.json) completes this item. Candidate scores never establish truth or exhaustiveness. SEARCH-002/003 and INDEX-001 retain separate fallback, feedback/replay and promotion gates.
- **Depends on:** INFO-002
- **Implementation:**
  - [x] Define contextual indexing input and candidate response contracts, publication/context identities, index/model versions, indexed-through watermarks and explicit stale/unavailable states.
  - [x] Implement asynchronous idempotent indexing, incremental updates, context-change invalidation, full rebuild and atomic version switching while ingestion remains durable during index failures.
  - [x] Preserve literal search and support scoped candidate retrieval followed by original-record/context fetch; choose backend and embedding model from measured needs rather than a domain taxonomy.
- **Evidence:**
  - [x] Find paraphrases and exact identifiers, including Yes indexed with its question; negation similarity must not be treated as support.
  - [x] Rebuild from originals, catch up after downtime and switch versions under concurrent ingestion without losing records or leaking private context; expose incomplete coverage.
- **Qualification evidence:** Artifact SHA256 `96b7bda8cd17962a8c82251fbc99ae22f312fc097ea4bf35bd2a306b8188e2ac`, receipt `bf6505275419af41d0bb6efd9798cfa363a679de17209d11d96df2864dfec8a1`, image `aa01ae8984022bd3a2da33a4fb7bb4cb209dbdb5e5d09afce018383a735c24c9`. Thirty-three hash-bound reports include nine retrieval lifecycle groups and six index/resource/interrupted-build groups on both native and Docker runtimes, 21 live-model retrieval cases on each runtime (nine held-out labels plus distractor ranking and linked originals), official SDK workflows across five native and four native-to-container producers, profile 1.4/58 examples, desktop/mobile controls and prior storage/history/auth/configuration/catalog/federation regressions. All results pass. Initial development input/status defects and harness corrections remain documented; model fallibility and bounded coverage are explicit.

### [x] SEARCH-002 — Fall back from search to semantic scans

- **Priority:** P1
- **Owner:** hub query planning and evidence sufficiency policy
- **Direction:** Try inexpensive search first and scan when it fails to produce useful evidence.
- **Conclusion:** Implemented owned frozen search/scan composition, full-original sufficiency assessment, exact uniform256 sampled audits, separate stage budgets/costs, interruption/child fencing and hot Admin settings/evidence. The [qualified archive evidence](../../verification/archive-qualified.json) closes this gate. Model interpretations and scan comparisons remain provisional; explicit complete:true requests full applicable primary/final coverage. Feedback/replay and adaptive promotion retain separate gates.
- **Depends on:** QUERY-001, SEARCH-001
- **Implementation:**
  - [x] Clarify the shared original-quote template so explicit negatives/contextual No can answer yes/no questions; retain existing History quality gates and fresh archive held-out cases.
  - [x] Define search, scan and search-then-scan modes with explicit scope, budgets, completeness requirements and stable query snapshots.
  - [x] Escalate on insufficient or conflicting evidence, absent/stale indexes, retrieval errors and exhaustive requests; evaluate usefulness against the question rather than score or hit count alone.
  - [x] Add configurable sampled scan audits of apparently successful searches; expose fallback reasons, partial outcomes, evidence and audit selection probabilities without blocking normal hub traffic.
- **Evidence:**
  - [x] Recover useful evidence missed by search, including later corrections; distinguish search misses from no evidence in the scanned corpus.
  - [x] Exercise plausible incomplete answers, negation, count/all requests, index outages and scan budget exhaustion; preserve explicit uncertainty and scope completeness.
  - [x] Verify scan audits can discover hidden misses in apparently successful searches and record their sampling policy.

- **Qualification evidence:** Forty-four hash-bound reports cover 17 archive lifecycle groups and 23 real-model scenarios on each runtime, including four fresh held-out questions after final template freeze; all22 existing History quality cases; exact profile1.5/81 protocol examples; desktop/mobile hot controls; matching-lane fairness; actual four-producer official SDK/store upgrades; old-template migration/inflight fencing on native and Docker; and prior retrieval/index, storage, identity/configuration, catalog and three-hub federation gates. The one superseded native state-cap fixture failure and its complete14-group passing rerun remain recorded.

### [x] SEARCH-003 — Record retrieval failures and replay past questions

- **Priority:** P1
- **Owner:** hub retrieval feedback and evaluation history
- **Direction:** Re-evaluate failed searches and learn from repeated search-then-scan attempts.
- **Conclusion:** Implemented owner-scoped asynchronous attempt capture, independent Admin labels/cohorts/recurrence clusters, fresh same-snapshot paired replay with real History fallback costs, durable policy/owner/child/lease fencing, hot controls and profile1.6. The [qualified feedback evidence](../../verification/feedback-qualified.json) closes this gate. Model interpretations and human assertions remain fallible; the three live-model development/regression cases are not fresh optimizer held-out evidence. Adaptive promotion retains INDEX-001.
- **Depends on:** SEARCH-002
- **Implementation:**
  - [x] Distinguish closed-cycle diagnostics from missing public context in archive sufficiency/comparison, preserving actual gaps and bounds under a new policy identity.
  - [x] Record question, authorized scope/snapshot, search candidates/ranks, scan evidence, answer changes, completeness, fallback reason, versions, cost and latency with access controls.
  - [x] Cluster recurring misses and replay saved attempts against changed retrieval configurations on the same evidence snapshot; keep later-corpus re-evaluation separately labeled.
  - [x] Create regression and held-out cohorts including successful searches, no-evidence cases and sampled audits; retain feedback separately from source publications to prevent self-confirming retrieval.
  - [x] Preserve direct analysis failures across budget continuation, distinguish actual History context limits from independently changed children, and retain numeric metrics after derived-evidence retirement; focused frozen-build fault/lifecycle tests pass.
- **Evidence:**
  - [x] Reproduce a miss with stable source/configuration identities and measure improvement without mistaking new publications for better indexing.
  - [x] Classify missing evidence, ranking/context defects, model errors and incomplete scans correctly; incomplete/model-generated judgments are not unquestioned ground truth.
  - [x] Verify feedback authorization, duplicate retry handling, restart persistence and replay isolation from subscription deliveries and ordinary evidence searches.

- **Qualification evidence:** 57 hash-bound native/container reports cover the frozen artifact and image; lifecycle/fault/privacy/bounds, both-kind matching fairness, desktop/mobile controls, five actual store-producer SDK upgrades, original History/Archive/retrieval quality regressions, and existing storage/identity/configuration/catalog/federation/deployment gates. Typed-wire examples and critical semantic/unsupported-annotation checks pass. Same-corpus live contextual Yes/No cases recover confirmed original recall with fewer actual calls/bytes while both branches answer correctly; unrelated-entity no-evidence remains unsupported.

### [x] INDEX-001 — Generate and qualify retrieval improvements from observed misses

- **Priority:** P1
- **Owner:** hub adaptive indexing jobs and operator policy
- **Direction:** Use repeated search-then-scan failures to identify and generate the indexes retrieval actually needs.
- **Conclusion:** Implemented profile1.7 bounded native recipe trials from independent confirmed recurring misses, a frozen training winner followed by fresh held/regression evaluation, and atomic promotion/rollback of complete caught-up indexes under hot review or automatic policy. The [qualified evidence](../../verification/optimization-qualified.json) binds 75 native/container reports, the authorized lifecycle receipt, exact accepted image, independent protocol snapshots and harnesses. The six fresh evaluation groups improve mean retrieval recall by 833333ppm with zero asserted answer failures/regressions/false support and four fewer calls/24189 fewer bytes in the final comparison. This qualifies those labeled fixtures and runtimes; human labels and model decisions remain fallible. SEARCH-003 stays independently frozen and qualified.
- **Depends on:** SEARCH-003
- **Implementation:**
  - [x] Define configurable recurrence/support thresholds and diagnose repeated misses; generate versioned declarative recipes tied to evidence rather than arbitrary generated executable code.
  - [x] Build isolated candidates from authoritative records with durable checkpoints and resource limits; replay training and held-out/regression cohorts and report quality, coverage, latency and storage tradeoffs.
  - [x] Promote only candidates passing configured criteria and corpus catch-up, atomically switch versions, retain rollback and prevent repeated ineffective rebuilds; support operator-selected automatic or review-based promotion.
  - [x] Document lifecycle states, failure handling, retirement and management visibility; add generated runtime behavior through owning Component specifications and the authorized Literate AI lifecycle.
- **Evidence:**
  - [x] An observed recurring paraphrase/context miss produces a candidate that improves held-out retrieval; a ranking-only defect need not create a new index.
  - [x] Reject candidates that regress correction/negation, privacy, successful-query recall or resource limits; reject insufficient evaluation evidence.
  - [x] Exercise interrupted builds, concurrent publications/context updates, promotion, rollback and retirement while source records and hub delivery state remain intact.

- **Qualified implementation:** accepted artifact SHA-256
  `1d3459aab65c295b8edb988dbf7bf716ecece78e9e7e7062ec19312984ee7d48`,
  receipt `sha256:f2ccbd20232cc65afbbbc5f10b38fa6190c99c5ce560304ff03c92507bec2369`,
  image `adhd-hub:optimization-local`
  (`sha256:45c0befd89d04f6063b523496c492fbf2ae27481abd8a6438cdf04e41859ceb1`).
  Independent native/Docker conformance covers 141 authored protocol examples,
  66 private oracle cases and 18 native vectors. Desktop/mobile settings and actual
  qualified evaluation/promotion were inspected. Real old-producer and cross-runtime
  upgrades preserve selected recipes while marking prior-runtime qualification
  accurately. Source/delivery isolation, shared-lane fairness, hot store moves,
  explicit base reset, faults and restart recovery pass. Exact schema/OpenAPI
  snapshots preserve runtime differences limited to unordered required-name lists.
  End-of-cycle survey found no collectable work; the accepted receipt remains current.

<a id="fed-001--federate-project-hubs-for-asynchronous-discovery"></a>

### [x] FED-001 — Federate project hubs for asynchronous discovery

- **Priority:** P1
- **Owner:** hub federation, query jobs and project documentation
- **Direction:** Keep one server per project, but let an agent ask its local hub whether other projects are doing X; the local server contacts other ADHD servers and gathers answers asynchronously. Consider pub/sub for requests and responses.
- **Conclusion:** Add opt-in federation between independent single-project hubs, reusing the planned asynchronous query lifecycle and evidence-backed answers. Pub/sub is a candidate transport, not a selected broker or protocol. Federation does not imply shared storage, automatic publication replication or task assignment. The implemented contract defines direct-peer federation with durable HTTP submit/status queues, explicit project profiles and publication export allowlists, model-backed relevance and owner-scoped query jobs. This delivers project discovery independently of QUERY-001's broader historical synthesis.
- **Depends on:** INFO-001; shares the asynchronous query conventions of QUERY-001 without requiring its full contextual-history scan engine.
- **Planning evidence:** Tracker reconciliation found no open issues or pull requests; the start-of-cycle peer survey found no collectable work. Implementation and behavioral acceptance are complete. The installed framework lacked Elixir support, so the reviewed Standard rebind selects the exact Elixir-capable upstream revision in requirements-build.txt. Linux is now the default build target for the container host; the macOS Flavor remains selectable. Native and hardened-container federation each pass 25 scenarios; the existing SDK/store-upgrade suite passes 30 and container operations suite passes 32. Live discovery and existing coordination also pass against the included GPU model service.
- **Implementation:**
  - [x] Define peer identity, discovery/bootstrap, authenticated trust and operator-controlled participation; specify which project descriptions, queries, evidence and answers may cross hub boundaries. Private addressed messages and non-exportable context must remain local.
  - [x] Specify durable query IDs, origin/responder project and hub IDs, response correlation, incremental local result retrieval, deadlines, cancellation, retry deduplication, loop prevention, hop/fan-out limits and resource budgets. Evaluate pub/sub request and response channels without requiring a global broker.
  - [x] Implement bounded asynchronous dispatch to participating peers, remote authorized evidence evaluation and durable collection of provenance-bearing responses. Report selected, responding, failed and pending peers; distinguish no matches within responding scope from unknown or incomplete coverage.
  - [x] Document one-server-per-project deployment, peer onboarding/removal, visibility controls, query/result workflow and failure handling; preserve standalone operation and existing local APIs when federation is disabled.
- **Evidence:**
  - [x] Exercise at least three independent project hubs: ask the local hub which projects are doing X, obtain relevant remote project answers asynchronously with source provenance, and retrieve progressive and final results without blocking ordinary publish/poll traffic.
  - [x] Verify offline/slow peers, deadline expiry, partial/no-match outcomes, cancellation, duplicate or cyclic forwarding, bounded fan-out, retry and hard-restart recovery without duplicate logical responses or lost accepted jobs.
  - [x] Reject unauthorized peers and prevent export of private messages, restricted publications, linked private context and credentials; verify disabled federation and existing single-project workflows remain compatible.

- **Qualified implementation evidence:** `verification/federation-acceptance.json`
  and `verification/federation-container.json` cover durable direct-peer jobs,
  progressive results, outage recovery, cancellation, malformed peers, bounded jobs,
  privacy and credential separation. `verification/federation-regression.json`
  covers SDK behavior and real legacy-store upgrades;
  `verification/federation-container-regression.json` covers hardened deployment
  and backup/restore. `verification/federation-browser.json` records desktop/mobile
  console regression with zero normal-path errors; both rendered screenshots were
  visually reviewed. `verification/federation-staging.json` passes four
  receipt/hash/determinism checks. Accepted artifact SHA-256:
  `ec94917a4e079b7677dd895fc5a08f0acbf083d9f401f585abf9d74da6af2976`.
  Qualified source is published in the committed source cache. Start/end peer
  surveys found no collectable work or open reviews.

- **Live acceptance:** `verification/federation-live.json` passes 26 scenarios,
  including three independent hubs with the actual SystemOne service: beta matched
  at 998,675 ppm and gamma returned a nonmatch at 380 ppm, with approved evidence
  and project provenance. `verification/federation-live-regression.json` passes
  29 existing SDK/information/management/live-coordination scenarios; the relevant
  coordination update scored 998,901 ppm and unrelated content was not delivered.

### [x] MODEL-001 — Run the selected decision model alongside the hub

- **Priority:** P1
- **Owner:** model deployment and operator documentation
- **Direction:** Set up a Nemotron/SystemOne service on this host and include a model Docker container in the application.
- **Conclusion:** Use the already selected pinned Nemotron Deciffusion image and approved checkpoint, GPU acceleration, loopback exposure and bounded model resources. Preserve typed semantic matching and validate live federation with the actual service.
- **Depends on:** INTEGRATE-001
- **Implementation:**
  - [x] Add reproducible model container deployment with checkpoint verification and operator instructions.
  - [x] Start the model on the available GPU without disturbing existing host workloads.
- **Evidence:**
  - [x] Verify checkpoint identity, container GPU access and healthy typed SystemOne responses.
  - [x] Run federation discovery and existing hub acceptance against the real model service.

### [x] BUILD-001 — Support qualified retained-source cache artifact exports

- **GitHub issue:** [#97](https://github.com/jordanhubbard/literate-ai/issues/97)
- **Priority:** P2
- **Owner:** upstream Standard lifecycle accepted-source export
- **Direction:** Record the framework provider-selection gap discovered while qualifying federation.
- **Conclusion:** Filed issue #97 with explicit authorization and implemented a local provider-neutral upstream fix: reconstruct exact path-free retained lookup from current verified membership, preserve the retained cache namespace, reject stale/retired/ambiguous bindings and run current acceptance before export. The [local qualification](../../verification/build-retained-export-qualified.json) includes real portable export, independent-acceptance refusal preserving prior receipt/export and no-generation checks. The application's framework pin and receipt-bound rebuild staging remain unchanged. Clean full upstream release qualification and publication remain future publication gates; no upstream merge/release is claimed.
- **Depends on:** none
- **Implementation:**
  - [x] Prepare a sanitized upstream reproduction and issue draft describing the rejected retained-source provider.
  - [x] With explicit user authorization, filed upstream issue #97; reproduction confirms lookup-only selection rejects the retained-source provider.
  - [x] Implement and preserve a reviewable local upstream patch with exact retained review recovery and portable acceptance/export tests.
- **Evidence:**
  - [x] An upstream lifecycle accepts admitted retained-source cache entries and exports an artifact with current acceptance.

BUILD-001 upstream report (filed as issue #97):
“Accepted-source export rejects a qualified retained-source provider. Reproduce
by admitting a source tree through the reviewed retained-source lifecycle,
publishing its successful cache entry, then requesting an accepted-source build.
The selection constructor rejects `operator-retained-source` even though the
entry passed admission. Expected: either accept the verified provider with current
independent acceptance, or expose an explicit supported export operation without
rewriting provenance. Add a portable retained-source/cache/export round-trip
fixture and preserve fail-closed rejection of unadmitted entries.” A local provider-neutral fix is now under test in the parent checkout;
receipt-bound local staging remains independently checked and the application's
framework pin has not changed.

Upstream search found the related retained-adoption proposal
[issue 22](https://github.com/jordanhubbard/literate-ai/issues/22), which covers
conversion-stage admission rather than this qualified-cache export rejection.
No existing exact export issue was found; issue #97 preserves the narrower follow-up.
The parent checkout records RETAINED-EXPORT-001. Its local fix reconstructs a
path-free retained lookup, scopes discovery to current verified membership and
allows full accepted retained entries to face current lifecycle acceptance before
export. All 15 focused retained tests pass, including actual export with the
original input removed, current independent-acceptance refusal preserving prior
receipt/artifact, and rejection of retired/stale memberships. A fresh focused run passes all 15 checks. All framework functional outcomes pass
across the completed checkpointed repair (1,740 passed, 100 explicit skips); lint,
format, layout, public export and documentation review pass. The full repair is
explicitly not a clean release-gate attestation. The [portable patch](../../verification/upstream-retained-export.patch)
and hash-bound local qualification remain reviewable. Issue #97 stays open; clean
full upstream release qualification/publication and application framework adoption
remain separate future gates.

The subsequent clean full Python regression now passes with exit0. Its exact
machine outcomes are retained in
`verification/upstream-python-clean.json.gz` and hash-bound by the local
qualification record: 1,740 passed, 100 explicit skips, zero failures. Other
upstream release gates, publication and application adoption remain unclaimed.

MODEL-001 deployment qualification found Docker tmpfs defaults to `noexec`; first
inference could not load Triton's compiled extension. The Compose scratch mount
now explicitly permits execution while retaining read-only root/checkpoint,
capability removal and resource limits. Startup verification includes a real typed
inference request after readiness, so a healthy engine alone cannot qualify setup.

MODEL-001 current-host deployment evidence is in
`verification/model-deployment.json` and `verification/model-service.json`:
verified BF16 checkpoint, pinned image, A40 CDI access, loopback listener,
read-only root/checkpoint, bounded resources and real typed startup inference.
Independent relevance probabilities were 0.992879 for image decoding and 0.003824
for financial reporting on the approved image-decoder profile. These smoke
results establish serving compatibility, not calibrated workload-wide accuracy.
The NVIDIA Toolkit base package was installed without a driver change, Docker
restart or stopping existing host workloads.

### [x] CONFIG-002 — Configure the running hub entirely from the admin console

- **Priority:** P1
- **Owner:** hub configuration lifecycle and administrator console
- **Direction:** All hub configuration must be hot without a hub restart, except the configuration location; all configuration including OIDC setup must be available from the admin page.
- **Conclusion:** Introduce a durable revisioned configuration service, authenticated Settings UI and atomic live reconfiguration of credentials, matcher, federation, listener, project identity and data store. Only the startup configuration location is immutable. Implement AUTH-001 local username/password and OIDC provider setup through the same settings workflow, with explicit authorization, protected sessions and recovery from failed changes.
- **Depends on:** UI-001
- **Implementation:**
  - [x] Reject unusable new/rotated HTTP bearer credentials before activation, including unsafe header characters and values exceeding supported header bounds; preserve unchanged legacy credentials.
  - [x] Define configuration persistence, conflict control, secret handling, bootstrap, atomic live changes and migration semantics for every existing setting.
  - [x] Implement Settings forms and authenticated configuration APIs, including the built-in admin account, local username/password provisioning/rotation, provider selection, OIDC setup/verification, group lists assigned to roles and ROLE-001's Admin-only role management; use AUTH-001's first-install password file for initial access.
  - [x] Include FED-003's information catalog visibility and canonical source ownership configuration in Admin-only Settings; hot ownership changes must update catalog revisions and invalidate affected routing caches.
  - [x] Update workers, listeners, storage, credentials and deployment mounts to consume current configuration without hub restart.
- **Evidence:**
  - [x] Verify every setting takes effect with the same hub process, survives restart and preserves accepted data; reject invalid, stale and failed changes without partial activation.
  - [x] Exercise administrator Settings and OIDC flows at desktop/mobile sizes, plus SDK, federation, storage-migration, container and live-model regression.

Qualified profile-1.1 completion evidence: see the directory-batch evidence above.

### [x] ROLE-001 — Assign one server-local role to each user

- **Priority:** P1
- **Owner:** hub user identity, authorization and agent ownership
- **Direction:** Each server has Admin (full access, including the initial admin user), Developer (can add agents on their own behalf), and Viewer (read-only). Each user has exactly one role. Only Admins assign roles. OIDC group assignments resolve to the highest permitted role. Every user also has a name, email and a link back to their OIDC provider.
- **Conclusion:** Define one effective role per user per server with precedence Admin > Developer > Viewer. Bootstrap AUTH-001 admin with Admin. Developer inherits read-only inspection and can create agents bound to the authenticated user as owner; Viewer cannot mutate server state. Enforce permissions in server APIs as well as the UI. Role administration and OIDC group-to-role mappings are Admin-only. Include group mapping in AUTH-001's OIDC scope: each role accepts one or more provider groups, managed in the admin page with hot updates. Resolve all matched groups to one highest role rather than accumulating roles or letting users choose a role. FED-002 permits same-email users on federated servers to be treated as the same person, but each server retains its own role: no remote role, privilege or group-to-role mapping propagates directly or transitively.
- **Depends on:** AUTH-001
- **Implementation:**
  - [x] Define persistent server-local user records with an immutable internal user ID, `name`, `email`, exactly one effective role, and an OIDC identity link (configured provider reference, issuer and subject) when OIDC-backed; local-only accounts have no OIDC link before setup. Bind agent `owner_user_id` and role assignment to the internal ID, not display name/email. Preserve ownership across profile changes and explicitly authorized local/OIDC linking; reject forged ownership on Developer agent creation.
  - [x] Include Admin inspection and cancellation of Agent-owned discovery/source query jobs, without granting human sessions A2A agent impersonation. Scope product mutation retries by the current authenticated administrator identity.
  - [x] Author the complete permission matrix: Admin full access to server resources, data and management; Developer read access and agent creation only on their own behalf; Viewer read-only with no mutation endpoints. Reconcile the requested Admin full access with earlier administrator data-visibility restrictions in the implementation contract.
  - [x] Provide Admin-only role assignment and role-management controls in the admin page through CONFIG-002, with live enforcement of promotions/demotions and no restart; bootstrap the initial admin account with Admin.
  - [x] Implement Admin-controlled OIDC group lists on roles as part of AUTH-001, with deterministic maximum-role resolution (Admin > Developer > Viewer), including explicit unmatched-group and manual-versus-group assignment rules without implicit privilege escalation.
- **Evidence:**
  - [x] Verify exactly one role per user per server, initial admin privileges, Admin-only role assignment, denied self-promotion and cross-server independence.
  - [x] Verify Developer can create an agent only with their own authenticated ownership, cannot create for another user or assign roles, and Viewer cannot mutate through direct APIs or the UI.
  - [x] Verify live role changes affect existing sessions and permissions consistently; exercise desktop/mobile role controls and preserve authentication and agent-workflow regressions.
  - [x] Test OIDC group mapping alongside AUTH-001: users in multiple mapped groups receive exactly the highest role; cover multiple groups per role, Admin-only mapping edits, group removal, unmatched groups and live configuration changes without stale elevated access.

Qualified profile-1.1 completion evidence: see the directory-batch evidence above.

### [x] FED-002 — Correlate federated user identities by email without sharing roles

- **Priority:** P1
- **Owner:** hub federation identity and server-local authorization
- **Direction:** Federated ADHD servers may assume users with the same email are the same user. This must not imply any transitive role assignment.
- **Conclusion:** Allow matching user email profiles to identify the same person across trusted federated servers, including when the local user IDs or OIDC provider links differ. Preserve distinct server-local account IDs, provider links, agent ownership and exactly one local effective role on each server. An identity correlation does not copy roles, inherit permissions, assign a role or authorize an action on another server. Each receiving server applies only its own role assignments and OIDC group-to-role mappings.
- **Depends on:** FED-001, AUTH-001, ROLE-001; PROTO-001 contract definition/review before new identity-exchange wire behavior.
- **Implementation:**
  - [x] Specify minimal authenticated user-identity exchange between configured federation peers and documented email comparison/correlation behavior, keeping profile provenance and handling email updates without treating email as the immutable local account ID.
  - [x] Represent cross-server same-email identity correlation separately from local account linking, credential/session handling, agent ownership and per-server authorization; update AUTH-001 and ROLE-001 contracts to make the boundary explicit.
  - [x] Keep role assignments and OIDC group-to-role mappings server-local and Admin-controlled; reject remote role assertions as authority for local access and prevent role propagation through chains of federated servers.
- **Evidence:**
  - [x] Verify users with matching email can correlate across two federated servers even with different internal IDs or OIDC provider identities, while nonmatching emails are not assumed to identify the same user.
  - [x] Verify the same correlated user can be Admin on one server and Viewer or Developer on another; role changes and OIDC mapping changes on one server do not change roles or permissions on another.
  - [x] Exercise a three-server federation chain to prove no direct or transitive role propagation, and verify identity matching alone cannot bypass destination-server authorization or grant ownership of another local agent.

Qualified profile-1.1 completion evidence: see the directory-batch evidence above.

### [x] PROTO-001 — Specify and verify every federated-system wire protocol rigorously

- **Priority:** P1
- **Owner:** hub public interfaces, federation protocol specifications and conformance
- **Direction:** Ensure all over-the-wire protocols used in the federated system are exactly documented and rigorous. Agents communicate with ADHD servers using A2A; federated ADHD servers are not required to use A2A with each other.
- **Conclusion:** Maintain normative, versioned wire contracts sufficient for an independent implementation without reading hub source. Inventory agent-to-hub A2A, server-to-server federation, browser/admin APIs, OIDC provider exchanges and model-service requests. Treat agent-facing A2A and the peer federation protocol as separate interfaces: A2A is required for agents, while server-to-server protocol selection is independent and does not require or forbid A2A. Preserve the current documented HTTP federation transport until an explicitly specified alternative is selected. Distinguish implemented protocol behavior from planned extensions. Published standards must have exact versions and explicit application profiles or deviations; custom messages require machine-readable schemas, complete semantics and independent conformance fixtures. Protocol definition and review precede new wire behavior, including FED-002 user identity exchange and FED-003 information catalogs, canonical source claims, routing and cache freshness/invalidation.
- **Depends on:** FED-001
- **Implementation:**
  - [x] Document and enforce the protocol boundary: agent clients use A2A; peer federation may use a separately selected protocol. Test agent-facing A2A interoperability independently from peer protocol conformance, and require a reviewed contract for any new peer transport without imposing A2A on federation.
  - [x] Inventory each wire interface, transport and exact upstream standard/version; assign stable protocol/schema versions and specify compatibility, version/capability discovery, unsupported-version rejection, deprecation and upgrade behavior, including compatibility with the existing unversioned federation endpoint.
  - [x] Author normative contracts for methods/paths or channels, headers/content types, authentication and authorization, request/response/event envelopes, field meanings and required/optional/null distinctions, encoding, IDs, numeric bounds, timestamps and clock assumptions, field/size limits and malformed/unknown-field handling. Define complete status/error envelopes and HTTP mappings; include executable positive and negative message vectors and machine-readable schemas, with OpenAPI where applicable.
  - [x] Specify asynchronous state machines, correlation/provenance, durable acceptance points, ordering and delivery guarantees, retryable versus permanent failures, backoff/rate limits, deduplication scope and lifetime, idempotency conflicts, polling, deadlines, cancellation, late/duplicate/out-of-order responses and restart recovery. Document current HTTP transport and define any future pubsub protocol separately before use.
  - [x] Document credential roles and trust boundaries, transport protection, peer revocation/hot configuration effects, allowed disclosure and credential redaction. For FED-002 specify identity/profile fields and exact email comparison while explicitly forbidding direct or transitive role/permission inheritance. For OIDC reference its exact discovery, code/PKCE, token-validation, session and group-claim profiles rather than inventing an alternate OIDC protocol.
  - [x] Require every wire-visible change to update the normative contract, schemas, examples, compatibility notes and conformance tests together. Link current versus planned contracts from operator/developer guides and prevent stale documentation from qualifying an implementation.
- **Evidence:**
  - [x] Validate all published examples against their schemas and exercise actual requests/responses against independent conformance vectors; reject unknown fields/versions, malformed encodings/types/bounds, incorrect identities, correlation mismatches and unauthorized disclosure.
  - [x] Run multi-server interoperability and fault cases covering incompatible versions, lost acknowledgements, retries, duplicate/out-of-order messages, slow/offline peers, cancellation, deadlines, process recovery and identity-versus-role isolation. Include malformed HTTP framing, oversized payloads and authentication/origin failures at each applicable boundary.
  - [x] Review the published contracts for independent implementability and completeness; verify a separately authored protocol client or responder can interoperate using the published contracts and fixtures, without importing hub implementation internals. Record protocol/schema versions with passing conformance evidence.

Qualified profile-1.1 completion evidence: see the directory-batch evidence above.

### [x] FED-003 — Publish information catalogs and route queries to canonical source owners

- **Priority:** P1
- **Owner:** hub federation catalogs, source ownership and query routing
- **Direction:** Each federated server publishes, and provides on request, a list of the information it contains and the source scopes for which it is canonical. Examples are GitHub project foo/baz, selected Slack channels and a Jira project. Questions about a claimed source must go to its canonical server; other servers are not canonical for that source. Peers may cache ownership data for future pub/sub and search.
- **Conclusion:** Introduce an authenticated, versioned per-server information catalog that distinguishes contained information from canonical ownership. A resolved source scope has one authoritative server within the configured federation; a replica or matching description does not confer authority. Route source-specific questions to that owner and retain owner/source provenance in results. Ownership lookup and caching support future pub/sub and search without selecting a broker or implementing external-source ingestion. Unavailable owners and conflicting or unknown ownership must remain explicit rather than silently substituting a noncanonical server.
- **Depends on:** FED-001, PROTO-001, CONFIG-002
- **Implementation:**
  - [x] Define stable, provider-scoped source/resource identities and catalog descriptors, including provider host/tenant and repository, workspace/channel or project identifiers. Document aliases, renames and scope boundaries so similarly named GitHub repositories, Slack channels or Jira projects cannot collide. Distinguish canonical, replicated/derived and merely referenced information, with availability/coverage metadata where applicable.
  - [x] Specify and expose authenticated catalog retrieval on request from every participating server, including empty catalogs, bounded/paginated snapshots, server identity, catalog/schema revision and freshness metadata. Publish exact schemas, request/response/error semantics and examples through PROTO-001 before adding wire behavior; disclose catalog metadata under federation visibility rules without exposing credentials or private content.
  - [x] Provide Admin-managed hot configuration of canonical source scopes and catalog visibility through CONFIG-002. Define conflict detection and explicit ownership resolution/transfer/revocation across trusted peers; a unilateral or newer cached claim must not silently replace an established owner. Specify overlapping scope handling and refuse to invent an authoritative answer while ownership is ambiguous.
  - [x] Resolve ownership before source-specific query dispatch: send questions about a known source only to its canonical server; exclude nonowners as authoritative respondents even when they hold copies. Define source resolution for aliases and free-text questions, split multi-source questions by canonical owner, and report unknown ownership, conflict, partial coverage or an unreachable owner explicitly while preserving asynchronous job, deadline and provenance semantics.
  - [x] Allow bounded peer caches of catalog/ownership metadata with original owner/advertiser provenance, revisions, expiry/revalidation and invalidation on transfer, removal, peer revocation or hot configuration changes. Define stale-cache behavior and loop prevention; cached metadata may guide future pub/sub routing and searching but does not make the caching server canonical or grant additional access.
- **Evidence:**
  - [x] Exercise at least three servers with a canonical GitHub foo/baz owner, a noncanonical copy holder, distinct Slack channel sets and a Jira project; retrieve each catalog and prove queries reach the correct owner while copy holders cannot supply canonical answers.
  - [x] Verify provider/tenant/name collisions, aliases/renames, overlapping or conflicting claims, explicit ownership transfer/revocation, stale/expired caches, invalidation and peer removal without duplicate canonical ownership or silent routing to the wrong server.
  - [x] Verify asynchronous multi-source routing, unknown ownership, owner outages and deadlines retain explicit incomplete/unavailable status and provenance; test empty/large catalogs, access controls, metadata privacy and independent protocol/schema conformance.

Qualified profile-1.1 completion evidence: see the directory-batch evidence above.

### [x] LICENSE-001 — License ADHD under Apache 2.0

- **Priority:** normal
- **Owner:** Project licensing and documentation
- **Direction:** Add an Apache 2.0 license to this project.
- **Conclusion:** Add the unmodified official Apache License 2.0 at the repository root and declare the project license in its README and durable goals; retain separately licensed bundled material and its notices.
- **Depends on:** none
- **Implementation:**
  - [x] Add LICENSE and project license references without changing third-party notices.
- **Evidence:**
  - [x] Compared `LICENSE` byte-for-byte with the official Apache text (`https://www.apache.org/licenses/LICENSE-2.0.txt`); SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. Verified README/project references and unchanged bundled Prompt Master MIT notice against Git HEAD. `litai project validate` passed.

<a id="multi-001-define-multiple-project-identity-boundaries-and-compatibility"></a>
### [x] MULTI-001 — Define multiple-project identity, boundaries and compatibility

- **Priority:** P1
- **Owner:** hub Component architecture and public contracts
- **Direction:** Allow each ADHD server to host multiple projects while retaining federation between servers.
- **Conclusion:** Own the multi-project program in [the detailed roadmap](multi-project.md). Separate stable server identity, stable project identity and external source scope; replace one-server-per-project only through versioned contracts. Contract definition and independent scope/wire review are complete; dependent runtime qualification remains open in MULTI-002 through MULTI-008.
- **Depends on:** none
- **Implementation:**
  - [x] Inventory single-project assumptions in every Component contract, client, deployment path and acceptance harness.
  - [x] Specify project lifecycle, server-wide roles plus explicit project access, agent memberships, cross-project behavior and server/project configuration precedence.
  - [x] Specify exact agent/Admin/peer wire changes, version negotiation and the legacy single-project compatibility boundary before dependent implementation.
- **Evidence:**
  - [x] Review a complete operation/state/configuration scope matrix and proposed protocol examples, including denied access and mixed-version peers.
- **Contract completion evidence:** Contracts are complete in `components/hub/multi/spec.md` and the exact published `docs/protocol/scopes.json`, profile-2 schema/OpenAPI and examples. `tests/protocol_scope.py --schema docs/protocol/schema.json` passes exhaustive operation/configuration coverage. [Native wire conformance](../../verification/multi-eventing/final-wire-30.json) passes eight groups on artifact `698496fe…`, including positive/negative traffic and exact CLI/HTTP interface equivalence; [native federation](../verification/native-eventing.json) adds actual three-server, legacy-pair and denied-scope traffic. Runtime program qualification remains with MULTI-002 through MULTI-008.

### [x] MULTI-002 — Partition durable state and migrate single-project installations

- **Priority:** P1
- **Owner:** hub core, information, configuration and persistence contracts
- **Direction:** Preserve existing installations and isolate durable state for multiple projects on one server.
- **Conclusion:** Introduce a durable project registry and project-qualified keys, preserving stable server identity, original provenance and legacy default-project behavior. Choose the physical store layout from crash-safety and hot-lifecycle requirements rather than assuming one DETS file per project.
- **Depends on:** MULTI-001, KAFKA-001
- **Implementation:**
  - [x] Add registry, immutable IDs, mutable labels/aliases and explicit active/archive lifecycle; reserve deletion for a separately specified policy.
  - [x] Partition all data, idempotency, queues, cursors, snapshots, caches and derived state by project; validate references at persistence boundaries.
  - [x] Implement versioned legacy config/store migration with preflight, backup, interruption recovery and explicit downgrade restrictions.
  - [x] Coordinate backend/outbox/project key ownership and one recoverable migration sequence with KAFKA-001 and KAFKA-008.
  - [x] Reject hot removal of the project registry or any admitted project, including dry validation; candidate33 accepted an Admin patch deleting projects and memberships. Preserve complete configuration/revision and retained project data on rejection, including installations without a default project.
- **Evidence:**
  - [x] Upgrade actual earlier accepted stores and preserve publications, private deliveries, acknowledgements, queries, source IDs and selected optimizer recipes.
  - [x] Kill/restart migration and project transactions; prove no partial admission, silent empty stores, identity reassignment or cross-project key collisions.

### [x] MULTI-003 — Enforce project access and agent memberships

- **Priority:** P1
- **Owner:** hub identity and configuration contracts
- **Direction:** Assign agents and admit users to specific projects without changing the three server-wide roles.
- **Conclusion:** Keep exactly one server role per user and existing OIDC highest-role rules. Add project admission independently of roles; Admin has full server access, Developer manages only their own permitted agents, Viewer remains read-only. Agent membership may include several projects; credentials never gain access from a requested project ID.
- **Depends on:** MULTI-001, MULTI-002
- **Implementation:**
  - [x] Add Admin-managed user project access and agent project memberships with stable ownership and explicit project selection.
  - [x] Enforce role, admission, ownership and membership checks on every direct and indirect operation, including live revocation and queued work.
  - [x] Preserve local admin bootstrap, OIDC provider links, groups-to-role configuration and non-transitive email correlation; do not import remote access grants.
  - [x] Prevent a Developer from recreating a removed agent ID that retains private deliveries, receipts, subscriptions or owned jobs in any project. A public-interface probe on candidate31 verified new-owner access to the former owner's private queue. Preserve explicit Admin recovery/reassignment and retained data; add native/container retirement/recreation regression evidence. Candidate32 implements an all-project verified-snapshot guard; native first-install OIDC/accounts checks remain passing in `verification/multi-eventing/oidc-first-setup-32.json`. Independent candidate32 retirement and snapshot-fault suites pass, and role/browser checks pass22 groups. Review found a legacy missing-snapshot path could attempt the bootstrap DETS opener; candidate33 removes that fallback and uses only a verified snapshot server identity. The current source40 ownership repair, core94 retirement/fault cases and native/container role and account browser runs now qualify that path; the original failed candidates remain historical.
- **Evidence:**
  - [x] Exercise the role/owner/project matrix through API and browser, including guessed IDs, forged scopes, stale sessions, token rotation and revocation during work. The [independent OIDC policy image run](../../verification/ownedMULTI008/compiled05-oidc-policy-positive/manifest.json) now passes all five original cases and16 assertions on compiled05, retaining the native path and original policy assertions. The auth-only fixture uses the actual private bootstrap password, publicly disables its unused event transport before first project admission and verifies all projects ready after the original renamed-admin restart. Two actual compiled VMs, hard restart and strict owned cleanup are independently bound; the first fixture failure remains retained. The broader role/owner/project matrix is independently qualified by the exact sourceC native API9/role/account evidence and current native/container browser9/86, including guessed scopes, session revocation, token rotation and delayed-work fences; the leaf-only evidence binding is retained separately from parent program closure.

### [x] MULTI-004 — Scope agent coordination and evidence workflows to projects

- **Priority:** P1
- **Owner:** hub core, evidence, history, retrieval, archive, feedback and optimization contracts
- **Direction:** Make all agent operations, subscriptions and evidence workflows behave correctly with multiple projects.
- **Conclusion:** Use explicit authorized project context throughout. Default publication, messaging and subscriptions remain project-local; multi-project agents use separate project operations. Cross-project search is an explicit bounded fan-out with per-project provenance, never an implicit merged corpus.
- **Depends on:** MULTI-002, MULTI-003, KAFKA-001
- **Implementation:**
  - [x] Scope publish/get/search/send/subscribe/poll/ack, source deduplication, corrections and reference traversal; prevent cross-project references from granting visibility.
  - [x] Scope history/retrieval/archive jobs, feedback/cohorts/replay, optimizer training/evaluation/selection and all caches, snapshots and cancellation.
  - [x] Add explicit authorized local project discovery and cross-project query fan-out with per-project coverage, deadlines, incremental results and revocation handling.
  - [x] Apply KAFKA-001's raw/filtered subscription boundaries; integrate the A2A Kafka bridge and independent fact-history projection through KAFKA-003 and KAFKA-005.
- **Evidence:**
  - [x] Run interleaved projects with identical local IDs and content; prove delivery, deduplication, evidence, replay and optimizer isolation.
  - [x] Prove explicit fan-out returns only admitted project evidence with accurate partial coverage and no private addressed messages.

### [x] MULTI-005 — Federate servers hosting multiple projects

- **Priority:** P1
- **Owner:** hub federation, directory and protocol contracts
- **Direction:** Discover and query projects across servers even when each server hosts many projects.
- **Conclusion:** Authenticate peer servers independently from source/destination project authorization. Publish only approved project catalogs; canonical ownership routes to an exact server/project pair while remaining exclusive for each external source scope. Preserve asynchronous durable requests and explicit incomplete coverage.
- **Depends on:** MULTI-001, MULTI-003, MULTI-004
- **Implementation:**
  - [x] Version directory discovery, per-project catalogs, canonical claims, peer trust grants and identity correlation; cache by stable server/project/revision.
  - [x] Bind durable requests, status polling, responses and idempotency to authenticated origin server plus origin and destination projects; reject scope substitution and stale authority.
  - [x] Handle same-server canonical routing, conflicts, project archival, peer revocation and negotiated legacy peers without duplicate delivery or silent downgrade.
- **Evidence:**
  - [x] Qualify at least three real servers with multiple projects, local/remote canonical routing, conflicting owners, stale caches, outages, retries and revocation. The current [three-server Kafka federation](../../verification/final05-kafka-whole68-positive/manifest.json), [stale-owner four-check run](../../verification/ownedMULTI008/compiled05-stale-canonical-owner-positive/manifest.json) and [callback/epoch fences](../../verification/final05-recovery-callback28-positive/manifest.json) jointly qualify this scope. Expiry uses the original10-second TTL and12-second wait; an unavailable canonical owner never delegates work to a reachable noncanonical server.
  - [x] Validate exact new wire traffic independently and test old/new peer compatibility, bounded forwarding, privacy and unchanged server-local roles.

### [x] MULTI-006 — Manage multiple projects through the hot Admin console

- **Leaf qualification:** All seven implementation/evidence leaves are supported
  by [the exact requirement map](../../verification/admin-roadmap-closure-review05/review.json),
  current native and container browser9/86, and the mapped core/API evidence.
  Its item-specific dependencies and evidence are complete; integrated program qualification remains with MULTI-007/MULTI-008 and KAFKA-009.

- **Priority:** P1
- **Owner:** hub management, presentation and configuration contracts
- **Direction:** Make all project and server configuration available through Admin without restarting the hub.
- **Conclusion:** Separate server settings from selected-project settings, using explicit forms and revisioned transactions. Keep configuration-file location as the sole restart exception; project creation, archival, membership, source ownership, federation, model policy and OIDC remain hot.
- **Depends on:** MULTI-002, MULTI-003, MULTI-004, MULTI-005
- **Implementation:**
  - [x] Add accessible project creation/switching/rename/archive forms, user/agent access management and per-project catalog/export controls.
  - [x] Distinguish server-wide users, roles, OIDC, listener/model resources and defaults from project overrides with explicit inheritance and reset semantics.
  - [x] Scope all views/actions, clear stale browser context on project switching/revocation and preserve confirmation, secret handling, CSRF and concurrent-edit checks. Refresh must reload the admitted project list and names before requesting the selected project; externally removed access must clear the old selection and pending actions.
  - [x] Repair first-time OIDC setup so the Admin connection test is available for proposed settings before initial save; the inherited browser regression found the button hidden until a provider was already configured. Requalify the corrected artifact and image.
  - [x] Diagnose and repair the [unexpected HTTP401 in the exact-image foundation browser flow](../../verification/multi-eventing/foundation-browser-34-failure.json). A [deterministic actual-service probe](../../verification/multi-eventing/admin-stale401-34/manifest.json) now proves that an old list_projects HTTP401 resets a newly authenticated workspace while its server session remains valid. Fence stale auth responses and cancel old-context requests; requalify normal desktop/mobile OIDC setup, linking and logout without ignoring unexpected errors. The original untraced401 is not definitively attributed. [Native development35ui qualification](../../verification/multi-eventing/admin-session-35/manifest.json) now passes the strict race regression on both viewports, current-session revocation, the unchanged accounts/OIDC browser suite and18 native cases; the same race harness fails actualimage34. Current native and compiled05 browser qualification now covers this repair, including the strict delayed-response/session-fencing cases.
  - [x] Wrap complete namespaced object IDs in Events replay subscription labels and replay-status paragraphs within the 390px mobile viewport. The [admitted38 browser run](../../verification/native38-ui-initial/manifest.json) fails on document overflow; subsequent painted-text measurements identify these two unwrapped text regions, while navigation remains correctly clipped inside its own scroller. Preserve full IDs, accessible labels, desktop layout and the unchanged replay/acknowledgement assertions; qualify the repair on native and container runtimes before closing this follow-up.
- **Evidence:**
  - [x] Inspect desktop/mobile flows for every role; exercise concurrent tabs, stale revisions, project switching, live OIDC/access changes and project archival without restart.

### [ ] MULTI-007 — Bound shared resources and operate project lifecycles

- **Priority:** P1
- **Owner:** hub workers, model integration, storage and deployment contracts
- **Direction:** Prevent one project from starving other projects sharing a server and model service.
- **Conclusion:** Share per-server Kafka and an optional existing short-response model service while enforcing per-project admission/budgets and server-wide limits. Raw pub/sub must progress without a model. Make create/archive/resume operations hot and define their effect on accepted work, retries and evidence retention; coordinate Kafka-specific fairness and lifecycle fencing with KAFKA-002 through KAFKA-006.
- **Depends on:** MULTI-002, MULTI-004, MULTI-005
- **Implementation:**
  - [x] Specify fair scheduling and accounting across projects and job classes, bounded queues/caches/storage and backpressure.
  - [x] Fence workers against project archival, access changes and configuration revisions; preserve durable accepted work with explicit terminal/paused states.
  - [x] Add project-aware diagnostics/audit records and documented full-server and project backup/restore semantics, collision handling and container recovery.
  - [ ] Implement selective recovery into a missing or logically empty target under its original server/project identity, with an Admin plan, complete ownership/reference validation, target-only durable storage/Kafka generations and worker fencing. Preserve every other current project and current global configuration; reject populated logical targets. Follow [the project recovery plan](project-restore.md). The closed recovery authority in `components/hub/project-recovery/spec.md` and [87 independent wire vectors plus six examples](../../verification/project-recovery/contracts.json) are reviewed. Storage registry/bundle verification, Admin jobs, fresh allocation and transport generations, and worker fences are in progress; [five allocator development checks](../../verification/project-recovery/allocator-development.json) pass without claiming integrated recovery. The [development integration checkpoint](../../verification/project-recovery/integration-development.json) records allocator, callback/ticket fences and Admin recovery UI seams; [Nine frozen native component checks](../../verification/project-recovery/components/manifest.json) now pass for nested origin fences, active/queued target tickets, transport reset and pending-work preservation; the decision coordinator compiles. Guarded native development12 now passes18 regression cases and five actual private restore checks; the checkpoint guard passes82 vectors on each of OTP27 and OTP29, and six actual hostile offline rebind cases reject without metadata changes. Native development13 also passes six authenticated federation HTTP checks, including recovery503/Retry-After. The full twelve-boundary crash matrix, actual late network callbacks, broad successor regressions and formal artifact/image/platform qualification remain open. The [compiled05 late-callback qualification](../../verification/final05-recovery-callback28-positive/manifest.json) now passes all five original programs /28 checks, covering pending model/Kafka callbacks, outgoing and incoming queries, and peer epoch fencing through actual instrumented compiled boot. Original assertions, two-slot fixture profile and deadlines remain unchanged; root independently revalidates all21 actual VMs, cache/source custody,58 owned handles and789 process identities after cleanup. Default OCI startup remains covered separately by SDK/UI/deployment. Full-server restore does not discharge this requirement.
- **Evidence:**
  - [x] Saturate one project with slow/failing model and peer work; demonstrate bounded progress for another and truthful costs/coverage.
  - [ ] Exercise hot lifecycle changes, worker crashes, restart, container replacement and backup/restore without leakage or duplicated committed results.

### [ ] MULTI-008 — Qualify and document the multiple-project upgrade

- **Leaf qualification:** Normative staging, coordinated documentation and the
  multiple-project/federation demonstration are complete under
  [the exact property/evidence review](../../verification/ownedMULTI008/multi008-independent-leaf-review/property-review.json).
  The complete regression, migration and final consolidation gates remain open.

- **Successor readiness qualification:** Run all original23 real-broker readiness cases on the new admitted compiled image, preserving every deadline and capacity premise. Bind each actual VM to the source/cache payload and prove complete owned cleanup; the native23 result alone cannot qualify the image. The separate committed-retention recovery companion remains independently required.
- **Core fixture revision premise:** The reviewed foundation fixture now captures its full accepted private configuration after public external-reload acceptance, before the invalid-file exercise. Actual-AST regression checks preserve every original assertion, call and deadline and demonstrate that the predecessor can restore stale revision bytes. Application source and conflict-denial behavior are unchanged. Keep the [original partial failure](../../verification/eventing-readiness-core13-first-failure/manifest.json) false; the [fresh full13 preparation](../../verification/eventing-readiness-core13-second-preparation/manifest.json) borrows no partial prefix and requires separate execution and cleanup qualification.
- **Priority:** P1
- **Owner:** hub acceptance harnesses, protocol documentation and operator/client guides
- **Direction:** Finish the program only with independent evidence for isolation, compatibility and operation.
- **Conclusion:** Bind qualification to the exact accepted artifact and container, with native, SDK, browser, migration, federation, fault and live-model evidence. Existing single-project evidence remains historical and cannot attest the new architecture.
- **Ownership verification failure follow-up:** The admitted38 image core run rejects a missing snapshot correctly, but a corrupt registered target snapshot throws a restore-verification error through the Developer `create_agent` ownership check and terminates `ADHD.Config`. Subsequent `config_get` returns500 and the hub exits. Preserve the actual failed report/logs and ten complete passing suites; do not count its two partial fault checks or the two unrun suites as qualified. The [independently reviewed repair](../../verification/ownedMULTI008/ownership40-review.json) converts unavailable ownership evidence into a published redacted configuration error before mutation, preserving configuration/revision/tokens and the live shared service. [Native40 passes18 self-tests and three actual ownership checks](../../verification/ownership40-development/manifest.json), including healthy Blue progress during both faults and authorized creation after exact snapshot restoration. Native38core169 did not include this distinct suite; the earlier profile2.1 retirement-fault pass belongs to development09, not this artifact. [Exact-image40 ownership recovery now passes all three checks plus eighteen packaged self-tests](../../verification/project-recovery/development40/image-ownership-positive/manifest.json). [All six image40 filesystem observer families now pass nineteen actual export probes](../../verification/project-recovery/development40/image-observer-abi/manifest.json), with source/mapping/process custody and independent strict absence of all nineteen containers. **Next:** qualify the remaining recovery, configuration, Kafka, browser and deployment suites against this exact image. Keep source38/source39 and their reports immutable.
- **Additional qualification follow-ups:** Retain all three global hot-configuration rename crash cases (`tests/config_recovery.py`) in the integrated audit; these are outside the native169 core composition. The [native strace fixture correction](../../verification/ownedMULTI008/recovery-remaining/config-mutation-witness.json) now observes only bytes appended after the mutation client is armed, with two isolated checks proving earlier bootstrap renames cannot satisfy it; all original assertions and the25-second deadline remain unchanged. Its actual three-case run is pending, and native strace does not qualify a container VM. The [dedicated image adapter and observer](../../verification/ownedMULTI008/recovery-remaining/config-image-preparation.json) are independently reviewed, with16 isolated checks and a host-only ELF audit. The [fresh standalone rename probe](../../verification/config-image-abi38-positive/manifest.json) now passes actual libc forwarding, physical rename, source-bound readonly mapping, stable process custody/kernel STOP and exit137 with independent removal. Its source-specific proof is accepted by the current validator. The [image40 three-boundary configuration application run](../../verification/project-recovery/development40/config-image-positive/manifest.json) now passes all three whole cases after full292-file/eight-binding review and14 isolated guard checks. Root independently revalidates the original qualification, six actual59-file VM payload checks, three kernel boundaries and strict absence of all eighteen Docker identifiers. Its original thirteen assertions and45/25/16-second bounds are preserved; initial revision comes from authenticated public configuration and legacy-disabled transport is proven by existing public initialization responses. Preserve the rejected bytecode-contaminated preparation and the earlier false pre-mutation default audit. The corrected native strace3 remains a separate pending gate. The image result does not discharge native, browser, wider recovery or release qualification. Existing five observers and the default18 ABI cases remain unchanged. The [initial controlled image ladder](../../verification/project-recovery/development38/controlled-image-first-failure/manifest.json) stopped before any functional case: its runtime file audit incorrectly included the Dockerfile build input, then cleanup rejected a valid lowercase Docker missing-object response. Preserve its failed aggregate and14 unrun suites. The narrowly corrected helpers pass12 isolated checks, and root verifies the fresh15-suite/117-group plan preserves every original entrypoint, argument and deadline while binding the staged Dockerfile separately; the [corrected batch terminated with eleven whole suites /100 groups passing](../../verification/project-recovery/development38/controlled-image-prefix-100/manifest.json), then the first Feedback SDK image failed its unchanged thirty-second readiness deadline before completing a case. Three later SDK suites remain unrun. Exact261-file closure, eighteen externals and five bindings remain unchanged; independent audit confirms all62 issued Docker handles and37 owned process identities absent. Preserve the failed aggregate; the cause of the SDK startup failure is unresolved and no deadline has been widened. All four SDK ladders remain pending for the actual repaired40 image. The remaining recovery component capsule and cleanup supervisor pass32 isolated checks (including asyncio-safe deadline propagation); root statically reassembles all53 source files to the exact admitted38 artifact and parses the capsule without evaluating it. Actual OTP29 component execution remains pending. All seven HTTP recovery suites now bind post-cleanup image evidence and fail closed on cleanup failure; their actual image application runs remain pending.
- **Held Kafka callback fixture follow-up:** Preserve the admitted image38 serial attempt: the model callback suite passed four groups, while Kafka restore apply exceeded the fixture's unchanged 20-second settlement bound before a durable decision. Required fresh-topic preflight shares the default single project eventing slot with the deliberately held old 30-second HTTP request; queue residence is part of that request budget, not a product 20-second restore promise. Qualify this overlapping-callback scenario with an explicit two-slot project eventing fixture profile, retain the global sixteen-slot limit, observe actual public scheduler counts, and keep all old-response, offset, identity, acknowledgement, Blue and cold-reopen assertions. This scoped fixture does not claim default-one-slot restore latency or bypass product admission. Retain the failed attempt and prepare a fresh serial image plan for review before execution.
- **Held-callback qualification result:** The [fresh serial image38 plan](../../verification/project-recovery/development38/image-recovery-cap2/manifest.json) now passes five complete suites/28groups: pending model4, pending Kafka5, queries8, incoming7 and peer epoch4. Root independently rehashed all reports, eight actual origin/peer runtime bindings,239 frozen files and four bound inputs, then confirmed all21 app containers and16 payload probes absent. Preserve the old failed matrix and do not extend this scope to default-one-slot latency, the broader recovery52 matrix, successor40 or release qualification. This status belongs in the execution queue; stable recovery contract documentation is unchanged.
- **Depends on:** MULTI-001, MULTI-002, MULTI-003, MULTI-004, MULTI-005, MULTI-006, MULTI-007, KAFKA-009
- **Implementation:**
  - [x] Complete local OCI staging of the locked normative hub specification closure, including the recovery JSON Schema, and allow explicit selection of the verifier CLI/interpreter. The original Markdown-only walker omitted declared JSON authority and an ambient CLI could differ from the project-pinned framework. Preserve existing aliases and deterministic archives; reject changed, missing, redirected or colliding inputs and qualify the exact staged byte identities before successor image claims. This is local deployment packaging, not a native-package or registry release.
  - [x] Update normative specs/traceability, schemas/OpenAPI/examples, agent onboarding, configuration tooling, deployment and operator recovery guides.
  - [ ] Run the complete multiple-project matrix plus existing regression suites against native and Docker artifacts and the existing model container.
  - [ ] Record acceptance identities, upgrade/rollback limitations and unresolved gates; close dependent items and the detailed roadmap only when their evidence passes.
- **Protocol publication follow-up:** The admitted38 runtime exports schema/OpenAPI2.1 and passes the independent87-vector combined-schema and eight-group wire checks, but the protocol landing page still calls itself profile1 while its downloadable snapshots remain2.0. Publish the exact reviewed2.1 exports, retain byte-identical2.0 snapshots, separate historical profile1 semantics from current project/Kafka/recovery rules, and link conformance evidence. Publication does not close the remaining runtime/image/platform gates.
- **Local legacy adoption compatibility follow-up:** The oldest supported actual producer writes a valid closed schema1 checkpoint with historical mode0664 and no persisted server ID; successor16 applies imported-bundle private-mode checks during local identity probing and registry adoption, rejecting the unchanged accepted source. Keep bundle/import checks strict and preserve source16. In a separate derived successor, add an explicit local-only bounded owned regular/nlink1/no-symlink reader, safe checkpoint/snapshot preflight and project/server proof; create only private verified staged generations before native opening, retaining original files and migration rollback backups unchanged. Source37 now has component, file-proof, native and actual interrupted-upgrade/cold-replacement evidence; its four SDK ladders pass, while the additional schema2 identity case below requires successor38. Final native, lifecycle, image and platform qualification remain open.
- **Pre-federation schema2 compatibility:** Source37 passes all four SDK producer ladders and seven current context groups, but the existing Context suite's second supported historical producer also lacks a persisted server ID. Its actual closed schema2 checkpoint passes pure physical parsing and complete graph validation; source37 rejects only because its identity genesis guard permits schema1 alone. Extend verified historical absence to schema1 and schema2 in a new immutable successor. Keep schema3-and-later missing IDs, malformed or conflicting IDs, unclosed-checkpoint rules and imported-bundle permissions fail closed. Retain the source37 failure and qualify both historical producers through upgrade and cold restart before claiming the full context suite.
  - [x] Qualify real oldest-producer0664 and historical snapshot permissions, exact bytes/IDs/acks/retries and cold restart; repair a copy of the actual interrupted prepared migration; prove malformed/foreign/wrong-project/symlink/hardlink/non-owned inputs retain bytes/mode/inode and open no native checkpoint. Recheck strict imported-bundle permission rejection; bind evidence to the repaired successor without relabeling source16. The [complete successor composition](../../verification/ownedMULTI008/hostile-legacy-successor-composition/property-matrix.json) binds every named property, including the actual foreign-UID test and prepared-copy cold replacement, through conserved code and current compiled-image integration. Historical runtime scopes and failed/skipped attempts remain explicit.
- **Accepted pending-query backup follow-up:** An untouched runtime backup containing pending source/discovery jobs fails RESTORE_INVALID_BACKUP/schema before activation. Diagnosis finds the private validator ignored typeless string constraints, causing both `Scope.host` oneOf branches to match a valid DNS host; the same issue ignores typeless numeric and array bounds. Apply JSON Schema keywords to instances of their matching types regardless of explicit type declarations, enforce IPv6 format and exact oneOf cardinality, and qualify actual accepted-query state plus negative host/limit vectors. Do not skip validation or widen the published source grammar.
- **Pending source-query restart follow-up:** Native14 turns an already dispatched pending SourceQuery into partial/unavailable during origin restart while its original120-second deadline still has more than71 seconds left, current grants/configuration are byte-identical and the actual remote job has completed. Expired/revalidating catalog metadata must not terminalize an already pinned accepted job by itself: retain its ID, owner and deadline, wait for a fresh canonical revalidation and resume the original idempotent peer job. Keep new-query unavailable responses, explicit revocation/removal, identity conflicts and deadline expiry fail closed; never dispatch through stale metadata or a replacement owner. Preserve the failing actual pre-restore witness and qualify same-ID old/fresh callbacks independently.
- **Target isolation follow-up:** Actual native14 corruption acceptance passes checksum, stale snapshot, foreign identity, missing checkpoint and damaged checkpoint cases with global Admin and newer Blue state still available. A registered target snapshot symlink still stops the whole hub. Preserve that failure and quarantine only its validated registered target without opening/following the path; keep shared registry/marker/decision corruption globally fail closed. Uninitialized entries must retain that status only while both selected files are exactly absent. Also qualify initialization after a hot relocation makes the former root inaccessible; empty entries must not remain anchored there.
- **Live callback follow-up:** The real Kafka consumer-response fixture on development13 restores its target successfully but the old eventing worker logs `RECOVERY_REQUIRED` and exits; the per-project worker-start guard then prevents transport progress. Preserve this run, keep the eventing loop alive across a retired work unit, and notify the waiting owner when an active HTTP ticket is retired so it can begin a fresh epoch promptly. The [two-module native repair](../../verification/project-recovery-pending-kafka/manifest.json) now passes five actual broker callback/ack/restart checks; the [exact combined14 rerun](../../verification/project-recovery-pending-kafka/native14-manifest.json) also passes all five checks.
- **Successor admission preparation:** Reconcile the installed framework distribution with the pinned Standard through the reviewed CLI flow before lock/recipe refresh; do not hand-edit the pin, locks or receipt. Regenerate native-test and source-BOM metadata for the recovery modules. Keep Makefile dependency declarations identical to the assembler source closure; staging review found `resources.exs` omitted from `SRCS` although it was already assembled. Its declared clean target also lacked `tools/clean.exs`; restore the unchanged protected helper from source34 before staging, and verify only owned output directories are removed.
- **Kafka transport progress repair:** The unchanged native14 hot-move test exceeds its20-second raw-fanout bound although broker produce/offset/commit requests take roughly10–20ms. Duration-only copies trace the delay to shared HTTP client keepalive sessions behind one-second consumer long polls, with Resource acquisition and Store work remaining bounded. An otherwise identical copy using isolated closing Eventing HTTP sessions passes all seven original cases, including the same20-second fanout gate,16 concurrent writes and cold recovery. Apply that transport isolation without changing broker success bodies, resource caps, model networking or deadlines; qualify final combined runtime and verify closing-session lifecycle.
- **Successor regression follow-up:** Frozen development13 passes fresh explicit Admin initialization and authentication setup, but changing `store_path` to a fresh root returns `503 CONFIG_WRITE_FAILED`. Diagnose and repair registry-selected generation relocation, retain the original failed foundation/store-move runs, then rerun exact hot-move, collision, interrupted-move and cold-restart cases. The repaired native14 now completes hot relocation, but its original concurrent fanout deadline still fails despite observed broker progress; preserve and diagnose that result before closure. Source13 stays immutable; no successor migration closure is claimed.
- **Native progress:** Candidate34 (`7cc2f584…`) passes25 suites/151 core, migration, relocation, auth and fault groups; exact artifact/report bindings are retained in `verification/multi-eventing/native-project-migration-34.json`. Official admission now passes; exact-image runtime qualification and unresolved model/restore gates remain open. Independent wire and actual accepted learned-workflow upgrade checks also pass; see `verification/multi-eventing/wire-workflow-34-manifest.json`.
- **Evidence:**
  - [x] Verify locked normative staging closure and explicit verifier argv construction with independent byte/determinism/collision/symlink tests. The [construction-only proof](../../verification/project-recovery/development16/staging-closure-review.json) passes14 tests and includes all33 locked specifications; the [proper CLI receipt/context bridge](../../verification/ownedMULTI008/final-documentation-compiled05-bridge/manifest.json) now independently verifies actual successor staging of the unchanged compiled05 payload/specification/compiler context. Complete runtime qualification remains a separate gate.
  - [x] Demonstrate two agents coordinating in each of two projects on one server, a multi-project agent and a denied third project, plus a multi-server discovery/canonical-routing scenario.
  - [ ] Run declared lifecycle verification and independent wire/privacy/migration/browser/fairness checks with reproducible artifact-bound reports.

<a id="kafka-001-specify-kafka-eventing-and-optional-subscription-filters"></a>
### [x] KAFKA-001 — Specify Kafka eventing and optional subscription filters

- **Priority:** P1
- **Owner:** hub event, subscription and protocol contracts
- **Direction:** Pivot project pub/sub to per-server Kafka, retain A2A for agents and make plain-text model filtering optional.
- **Conclusion:** Own [the Kafka pub/sub program](kafka-pubsub.md). Project-wide event subscriptions receive publications from all agents without inference; optional plain-text filters narrow an authorized stream. Separate event transport, durable agent delivery and searchable originals. The contract and independent wire review are complete. Real service packaging and implementation exist, while dependent runtime qualification remains open in KAFKA-002 through KAFKA-009.
- **Depends on:** MULTI-001
- **Implementation:**
  - [x] Review the four implementation groups and model-free/filtered end-to-end acceptance scenario in [the detailed plan](kafka-pubsub.md#work-and-acceptance-order); use this as the next contract-review action.
  - [x] Define event envelopes, project/topic/partition identity, subscription selection/filter modes, activation watermarks, ordering, replay and delivery deduplication.
  - [x] Specify exact A2A/Admin/broker schemas, compatibility, durability boundaries and filter revision/error semantics before implementation.
  - [x] Select and pin a maintained Kafka client and compatible broker; explicitly revise the current standard-runtime-only constraint and record license/dependency/build implications.
- **Evidence:**
  - [x] Review implementable positive/negative wire examples and a state/ownership matrix for Kafka, backend storage, delivery state and model work.
- **Contract completion evidence:** `components/hub/eventing/spec.md` defines the outbox/backend/Kafka/delivery/model ownership matrix, closed event and subscription envelopes, offsets versus positions, filter revisions and migration compatibility; `components/hub/component.md` explicitly selects standard HTTP plus the maintained REST Proxy API. Compose/Kubernetes pin Kafka and REST Proxy 8.3.2 by digest and disclose the separate REST Proxy license. [Native eventing conformance](../verification/native-eventing.json) independently validates 24 positive and 27 negative vectors plus actual broker events; [wire conformance](../../verification/multi-eventing/final-wire-30.json) binds profile 2 to admitted artifact `698496fe…`. Transport/deployment implementation qualification remains with KAFKA-002 through KAFKA-009.

### [x] KAFKA-002 — Integrate per-server Kafka with durable event publication

- **Priority:** P1
- **Owner:** hub event transport, core persistence and dependency contracts
- **Direction:** Give each logical ADHD server its own Kafka service for isolated project event transport.
- **Conclusion:** Implement project-isolated topics and bounded producers/consumers with an explicit durable outbox or equivalent verified handoff. Preserve stable event identity across retries and coordinate backend writes with broker publication without claiming end-to-end exactly-once delivery.
- **Depends on:** KAFKA-001, MULTI-002
- **Implementation:**
  - [x] Provision documented internal topics/partitions and authentication/ACL boundaries; keep private addressed messages and credentials outside public event topics.
  - [x] Implement durable publish acceptance, retry/deduplication, consumer checkpoints and health/backpressure under broker outages.
  - [x] Fence consumers and topic lifecycle against project archive, restore, credential rotation and configuration revisions.
- **Evidence:**
  - [x] Kill hub/broker around each publish/checkpoint boundary; prove no acknowledged event is lost and retries do not create duplicate logical publications.
  - [x] Exercise multi-project isolation, rebalances, broker unavailability, disk/queue limits and recovery with a real Kafka service.
- **Current native qualification:** [The source34 complementary matrix](../../verification/multi-eventing/native34-complement/manifest.json) retains 66 passing checks across 13 single-run suites, including real broker outage/recovery, retention recovery, project policy, resource limits, delivery retries, cutover interruption and three-broker federation. Twelve raw reports bind the exact artifact directly; the lost-reply report is bound compositionally through its frozen plan and retained driver, with that limitation explicit. This supplements the separate 15-check core/protocol/durability proof. [Actual managed-observer coordinator changes and manual-bridge recovery](../../verification/multi-eventing/rebalance-34/assessment.json) now pass five native checks; this does not claim managed bridge ownership transfer or HA. [Current compiled05 Kafka qualification](../../verification/final05-kafka-whole68-positive/manifest.json) now passes all14 whole suites/68 checks, complemented by the current filesystem fault and configuration crash gates.

### [x] KAFKA-003 — Bridge Kafka subscriptions to durable A2A deliveries

- **Priority:** P1
- **Owner:** hub A2A, subscriptions, delivery and authorization contracts
- **Direction:** Agents continue to publish, subscribe, poll and acknowledge through A2A while Kafka handles event distribution.
- **Conclusion:** A project-wide unfiltered subscription includes all authorized project publications across agents, including the subscriber own publications. Independent subscribers each receive their stream; Kafka worker load sharing must not accidentally distribute events among agents instead of broadcasting.
- **Depends on:** KAFKA-002, MULTI-003, MULTI-004
- **Implementation:**
  - [x] Add explicit project subscriptions with optional deterministic selectors and no required model/description; preserve legacy described subscriptions as filtered mode.
  - [x] Persist independent subscription progress and recipient deliveries; separate broker processing offsets from agent acknowledgements and handle out-of-order ack safely.
  - [x] Define overlapping-subscription deduplication, unsubscribe/pause/resume, offline consumers, bounded replay and explicit retention-gap handling without weakening existing unacknowledged-delivery durability.
- **Evidence:**
  - [x] Run official A2A SDK flows with multiple subscribers receiving every project event and no direct broker access; prove zero model calls.
  - [x] Exercise disconnect/reconnect, concurrent subscribe/publish, filter changes, repeated polls/acks, overlapping subscriptions and consumer rebalances.

### [x] KAFKA-004 — Apply optional Jev-like filters without blocking raw streams

- **Priority:** P1
- **Owner:** hub model integration, subscription worker and scheduling contracts
- **Direction:** Allow a plain-text semantic filter to narrow a subscription, while unfiltered pub/sub needs no model.
- **Conclusion:** Evaluate only explicitly filtered subscriptions using the existing replaceable short-response decision adapter. Failure remains pending/error rather than a negative match or silent delivery of unfiltered content; raw subscriptions and unrelated projects progress independently.
- **Depends on:** KAFKA-003
- **Implementation:**
  - [x] Define filter enable/disable/edit revisions, threshold policy, input context and durable retry/backlog state; use deterministic selectors before inference.
  - [x] Add isolated queues, fairness, timeouts, per-project/subscription budgets and filter-decision provenance without inventing probabilities for raw deliveries. Current integration bounds the model-ready queue and retains overflow as deferred frozen targets in original durable event state; raw fanout must continue and diagnostics must distinguish ready, deferred and paused work.
  - [x] Make the model provider optional at startup; expose unsupported/unavailable filtered subscriptions explicitly and preserve accepted pending decisions across recovery.
- **Evidence:**
  - [x] With no model configured and with a hung/failing model, prove raw subscriptions deliver promptly with zero inference calls and other projects are not starved.
  - [x] Validate real short-response filtered matches/nonmatches, malformed decisions, retries, hot filter edits and revocation without silent misses or duplicated deliveries.

### [x] KAFKA-005 — Preserve backend fact search independently of pubsub

- **Priority:** P1
- **Owner:** hub information, evidence, history, retrieval and optimization contracts
- **Direction:** Keep facts and their original evidence searchable regardless of subscription filters or Kafka retention.
- **Conclusion:** Retain durable original publications and provenance in the backend; only deliveries are filtered. Literal/metadata search works without a model; semantic/history/archive workflows may use an optional model with explicit availability and coverage states.
- **Depends on:** KAFKA-002, MULTI-004
- **Implementation:**
  - [x] Define backend/index ingestion watermarks and read-after-publish/search visibility; recover projection lag without treating missing indexed facts as negative evidence.
  - [x] Preserve original history after broker retention, filter rejection, delivery acknowledgement and subscriber removal; keep private messages excluded.
  - [x] Decouple search/model workers and readiness from raw eventing, adapting replay/cohorts/optimizer evidence to project-scoped event identities and optional models.
- **Evidence:**
  - [x] Publish with no model and no subscriptions; prove facts remain searchable after filtering, acknowledgements, restart and broker log expiry.
  - [x] Exercise lag/rebuild/restore and model-disabled semantic queries with truthful coverage and unchanged evidence/privacy guarantees.

### [x] KAFKA-006 — Expose hot Kafka and subscription controls in Admin

- **Leaf qualification:** All six implementation/evidence leaves are supported
  by [the exact requirement map](../../verification/admin-roadmap-closure-review05/review.json),
  both current browser runtimes, Kafka14/68 and actual secured Kind7/51.
  This includes live credential rotation; integrated recovery and deployment qualification remains a separate program gate.

- **Priority:** P1
- **Owner:** hub configuration, identity and management contracts
- **Direction:** Manage eventing, subscriptions and optional model filtering from Admin without restarting the hub.
- **Conclusion:** All hub-managed broker connections, secret references, topic policy, subscription selectors/filters, model enablement and project settings use hot revisioned Admin changes. Distinguish broker infrastructure rollouts from hub restarts; preserve existing server roles and project admission.
- **Depends on:** KAFKA-003, KAFKA-004, KAFKA-005, MULTI-006
- **Implementation:**
  - [x] Add normal forms for raw versus filtered subscriptions, filter health/backlogs and project-wide event observation. Provide confirmed revisioned subscription edits, pause/resume and selector/filter changes through Admin; preserve queued deliveries and acknowledgements.
  - [x] Provide hot connection/credential/topic-policy changes with validation, cutover watermarks, consumer fencing and rollback; forbid silent resets or implicit replay. Recovery forms must support explicit subscription IDs/revisions beyond the bounded first page, with no hidden replay target truncation. Current integration provides partial per-project topic-prefix, retention and backlog-policy overrides with explicit inheritance; broker endpoint, security and enabled state remain server-wide. Qualify failed multi-project retention proposals against actual broker state before closing this control gate.
  - [x] Qualify interruption recovery of the new durable all-project transport transition and implement explicit Admin quarantine repair; candidate10 already passes real-Kafka successful/failed cutover and hard restart, linked in the partial progress record.
  - [x] Expose authorized broker lag, outbox/projection backlog, retention gaps, budgets and delivery/model status with secret redaction and server/project scope.
- **Evidence:**
  - [x] Inspect desktop/mobile role-scoped flows, stale revisions, CSRF, access revocation and model on/off transitions.
  - [x] Rotate broker credentials and change connection/filter settings live under load; prove no hub restart, lost accepted work or cross-project exposure.

### [ ] KAFKA-007 — Package per-server Kafka for containers and Kubernetes

- **Leaf qualification:** Five packaging/deployment leaves are complete under
  [the exact current evidence map](../../verification/ownedMULTI008/documentation-cli-progress-and-leaf-review/leaf-proposal.json).
  The compile-once compound leaf remains open for its complete-regression clause.
  Recovery continuation exposed a post-create Kafka metadata propagation defect;
  the hub eventing authority owns its repair, alongside deployment qualification.

- **Compiled successor gate:** Keep the full23 readiness-fault image gate open until the actual successor cache/image admission and runtime evidence pass. Preserve earlier failed attempts and use the unchanged original scenario assertions; no broader packaging or release claim follows from preparing a wrapper.
- **Priority:** P1
- **Owner:** deployment artifacts, dependency Flavors and operator guides
- **Direction:** Deploy each ADHD server with its own Kafka service using Kubernetes pods or equivalent plain containers.
- **Conclusion:** Ship both a plain-container Compose application and a Kubernetes application with hub, persistent Kafka and optional model profiles. Each server owns one logical Kafka service, which may contain several brokers; broker replication and hub replica safety must be stated rather than implied by pods.
- **Depends on:** KAFKA-002
- **Implementation:**
  - [x] Select pinned Kafka/KRaft images and client compatibility; declare dependencies, persistent volumes, private listeners, secrets, resource limits and readiness/startup/shutdown ordering. Generate and retain a distinct installation cluster ID, preserving existing volume metadata rather than assigning the tutorial cluster ID to every deployment.
  - [x] Handle transient own-topic metadata unavailability after successful Kafka creation within a bounded shared deadline. Preserve fresh-empty-topic, topology, retention and authorization checks; prove eventual readiness, deadline exhaustion without a restore/configuration commit, and rejection of invalid metadata. Retain the actual creation201/configuration404 recovery failure and qualify the repair through a proper successor artifact/image. The [targeted property review](../../verification/ownedMULTI008/source41-readiness-leaf-review/review.json) binds the proper source41 receipt, all 23 native and compiled readiness cases, both separate retention-recovery companions and exact image/cache custody. The parent and complete-regression compound leaf remain open.
  - [x] Provide Compose and Kubernetes packaging with model-free baseline and optional existing model/GPU service or configured remote model; choose and document Kubernetes manifest/chart ownership.
  - [ ] Compile the exact admitted hub modules during the pinned OCI build and verify the source/toolchain/module closure before loading it at startup. Preserve the exported source, original CLI behavior and runtime fault-observer interfaces; do not rerun application compilation on each container start. The [public compiler diagnostic](../../verification/project-recovery/development40/compiler-diagnostic-preparation/root-start.json) retains the original30-second SDK failure and observes module compilation callbacks beyond30seconds after container start. Bind the actual trace and cleanup evidence, then qualify the packaging repair against the unchanged SDK readiness deadline and complete required runtime/deployment regressions; traced timing is diagnostic, not an untraced CPU benchmark. The first [actual compiled-image offline audit](../../verification/container-precompile-image40/admission/manifest.json) confirms unchanged59-file application payload,33 canonical specifications and59 hash-bound compiled modules. It also records a final-stage COPY parent timestamp that prevents a reproducibility claim. The [corrected compiled03 admission](../../verification/container-precompile-image40/compiled03-admission/manifest.json) now binds the actual59-file payload,33 specifications,59 compiled modules and normalized final metadata. Its [complete cache qualification](../../verification/container-cache40-compiled03-positive/audit.json) covers original18 built-in tests, three CLI exports, the copy control and all12 rejection cases, preserving the first false fixture aggregate. The [unchanged original SDK17](../../verification/compiled-sdk-retarget-preparation/whole17-03-positive/manifest.json) now passes all Feedback5/Archive4/History4/Retrieval4 cases against this exact admitted image, retaining the original30-second readiness deadline and actual source/cache/VM custody. A [sequential independent rebuild](../../verification/container-precompile-image40/reproducibility-first-negative/manifest.json) reproduces every final cache byte and metadata entry but yields different intermediate layer identities; bitwise image reproducibility remains open. The corrected compiler-only deterministic option and explicit runtime-directory copy now produce [identical image identities from two independent sequential builds](../../verification/container-precompile-image40/reproducibility05-positive/manifest.json); [compiled05 admission](../../verification/container-precompile-image40/compiled05-admission/manifest.json) retains the unchanged application/specification bytes and actual cache audit. The final image now passes [all17 cache/CLI groups](../../verification/container-cache40-compiled05-positive/audit.json), including18 built-in checks and12 rejection cases, and [all19 ABI probes across six observer families](../../verification/image40-compiled05-abi19-positive/audit.json). All owned cache and ABI container IDs are independently absent. The [fixed live-model quality69](../../verification/quality40-compiled05-positive/audit.json) also passes all22 history,21 retrieval,23 archive and3 feedback cases with actual source/cache/VM custody,174 bounded POSTs and unchanged model identity. The final image also passes [all17 original SDK cases](../../verification/final05-sdk-whole17-positive/manifest.json) under the original30-second readiness deadline and [nine browser programs /86 assertions](../../verification/final05-ui-whole86-positive/manifest.json), including the two actual OpenRig rigs, OIDC accounts and session-response fencing. Root retained [manual continuation capture review](../../verification/final05-preparations/ui/manual-continuation-review.json) alongside the earlier five-capture review; raw images remain private. The [final compiled-image filesystem gate](../../verification/final05-filesystem-whole85-positive/manifest.json) now passes all17 original suites /85 checks; independent audit verifies the complete declared input/tool closure, all67 recorded container IDs,47 probe/codec names and19 recorded kernel PIDs absent, with historical name/start-tick recording limits stated explicitly. Next: finish deployment, remaining recovery and runtime gates, then refresh operator documentation through the final lifecycle review. [Deployed filtering/search evidence](../../verification/ownedMULTI008/compiled05-deployed-model-terminal/manifest.json) now qualifies all six original cases on each of actual Compose and Kind: twelve bounded provider POSTs total, raw Blue progress, privacy, cited fact queries and same-VM hot disable/resume. Both platform children exited0 and their required qualifiers, complete input closure, model identity, lease release and resource absence are independently verified. The external launcher returned143 for an unknown reason; that outer result remains false and does not replace the two complete child suites. No provider retry was performed. Earlier image evidence remains scoped to its original image.
  - [x] Document single-node versus replicated broker durability, single-writer hub replica limits, backup/restore, rolling broker upgrades and hot hub configuration propagation.
- **Evidence:**
  - [x] Boot clean Compose and disposable Kubernetes deployments with real Kafka and no model; run A2A pub/sub and backend search smoke tests.
  - [x] Exercise replacement/restart, PVC or volume reuse, broker failure/upgrade, secret rotation and optional-model enablement; validate manifests and image/dependency/license inventories.

### [ ] KAFKA-008 — Migrate existing subscriptions and queues to Kafka safely

- **Priority:** P1
- **Owner:** hub configuration/store migration and operator recovery contracts
- **Direction:** Upgrade current single-project/model-only installations and coordinate the multiple-project migration.
- **Conclusion:** Preserve old descriptions as explicit semantic filters, existing delivery IDs/acks, original facts and pending decisions. New project-wide subscriptions are unfiltered. Coordinate one recoverable migration/cutover with MULTI-002 instead of independent competing upgrades.
- **Depends on:** KAFKA-003, KAFKA-004, KAFKA-005, KAFKA-007
- **Implementation:**
  - [x] Specify ordered schema/config upgrades, cutover watermarks and topic initialization for legacy and already multi-project stores.
  - [x] Reconcile durable outbox, Kafka offsets, pending model jobs, deliveries and backend projection state without replaying old publications as newly subscribed events.
  - [x] Provide preflight, backups, resumable migration markers, abort/recovery and explicit downgrade restrictions for store plus broker state.
- **Evidence:**
  - [x] Migrate actual earlier accepted stores with offline agents, pending filters, duplicate retries and acknowledged deliveries; compare identities and counts.
  - [x] Inject crashes at every cutover boundary and restore backups; prove no silent loss, unsolicited history replay, cross-project leakage or double delivery.

### [ ] KAFKA-009 — Qualify Kafka pubsub and update all operating contracts

- **Successor fixture isolation:** The retained Kafka14 basis uses private REST
  port 18088, which is still owned by its historical qualification service. The
  existing fresh-service requirement needs a separately selected owned port.
  Parameterize only that private endpoint, retaining the original default and the
  healthy baseline endpoints, all 14 programs, 68 checks and deadlines. Verify the
  selected loopback mapping, service ownership and distinct cluster identities
  before execution; preserve the historical service and its evidence.
- **Leaf qualification:** Four contract/pubsub demonstration leaves are complete
  under [the current evidence map](../../verification/ownedMULTI008/documentation-cli-progress-and-leaf-review/leaf-proposal.json).
  Enforcing-CNI traffic now passes the separate network gate. Complete declared
  verification, selective recovery, successor application qualification and the
  final receipt/context bridge remain required before parent closure.

- **Priority:** P1
- **Owner:** hub acceptance, protocol conformance and deployment documentation
- **Direction:** Qualify the combined Kafka and multiple-project architecture before marking the pivot complete.
- **Conclusion:** Require independent artifact-bound native, real-Kafka, A2A SDK, browser, migration, federation, container and Kubernetes evidence. Existing model-only and single-project evidence remains historical; no new release or deployment is claimed by the roadmap.
- **Network fixture:** Use a hash-bound static TCP helper in the admitted image to qualify the network-only contract. Preserve all nine Pods, eighteen successful pre-policy controls, five allowed and thirteen denied post-policy routes, exact banner validation, original deadlines, resource/security limits, image/Pod custody and UID-fenced cleanup. Earlier utility startup failures retain their false outcomes and unknown causes. The first static run reaches Pod readiness but fails before traffic because CRI cannot resolve Kubernetes' imported-image alias. Resolve the immutable manifest digest reported by the Pod through containerd content, verify the exact content hash and image-manifest/config descriptor against the admitted config digest, and retain CRI config-ID validation within the original shared custody timeout. A mutable tag alone is insufficient. The [second failed run](../../verification/ownedMULTI008/cni-static-gate-second-failure/audit.json) correctly rejects an unsupported document shape; [read-only export diagnosis](../../verification/ownedMULTI008/cni-static-custody-format-diagnosis/audit.json) now proves that the exact Pod digest is a single-child OCI index. Support exactly one bounded index hop and one child manifest, verify every digest/size/media-type link and the admitted Linux/amd64 config, and retain raw private custody inputs before validation can fail. Reject ambiguous children, recursive indexes, remote URLs and tag fallback under the same shared 30-second deadline. Actual hub/Kafka deployment qualification remains independently required.
- **Depends on:** KAFKA-001, KAFKA-002, KAFKA-003, KAFKA-004, KAFKA-005, KAFKA-006, KAFKA-007, KAFKA-008, MULTI-007
- **Implementation:**
  - [x] Update normative Component contracts, schemas/OpenAPI/examples, client onboarding, traceability, deployment and troubleshooting guides together.
  - [x] Run zero-model raw-subscription/search acceptance and separate live-model filtered/semantic-query acceptance plus multi-project and federated regressions.
  - [x] Verify durable handoffs, fanout, fairness, retention/replay gaps and fault recovery at documented limits; record exact artifact/image/broker/client identities.
- **Evidence:**
  - [x] Demonstrate two projects with multiple publishers and independent raw/filtered subscribers, an unauthorized project and a federated peer using its own Kafka.
  - [ ] Pass declared verification and independent wire/privacy/fault/migration/deployment suites; document remaining limits and publication gates before closure. Qualify the shipped `deploy/k8s/private.yaml` on a disposable enforcing CNI separately: prove each route is reachable before policy, then verify allowed same-namespace hub-to-REST and REST/broker-to-broker traffic and denied unrelated/cross-namespace traffic at the declared ports. A default Kind cluster or successful policy apply alone does not prove enforcement. This network-layer fixture must remain distinct from actual Kafka/hub deployment qualification.

### [ ] INTEROP-001 — Support OpenRig cross-rig communication through ADHD

- **Priority:** P2
- **Owner:** hub agent integration, A2A contracts and interoperability acceptance
- **Direction:** Make ADHD compatible with OpenRig so agents in different rigs can exchange project events, messages and knowledge through ADHD. Preserve this cross-rig compatibility as the multi-project, Kafka and federation work evolves.
- **Conclusion:** OpenRig and ADHD are complementary: retain OpenRig for agent execution and work coordination, and ADHD for durable information exchange and federation. Preserve A2A as the agent-facing boundary and support independently operated rigs without requiring every participating agent to use OpenRig. The pinned OpenRig integration now uses an external A2A adapter with private rig/seat/project bindings. Native OpenRig A2A support is not assumed.
- **Depends on:** MULTI-008, KAFKA-009, PROTO-001
- **Implementation:**
  - [x] Inspect and pin the supported OpenRig release/API; specify stable rig/agent identity, ADHD project mapping and a minimal A2A adapter or skill where needed.
  - [x] Provide setup for agents in separate OpenRig rigs to publish/subscribe, send/poll/acknowledge and search through one ADHD hub, then through federated hubs with canonical routing.
  - [x] Preserve project admission, owner/role boundaries, provenance, retries and loop/duplicate prevention; keep rig identity as provenance rather than an automatic access grant.
  - [x] Document supported versions, credential provisioning, recovery and the division of responsibility; retain support for agents outside OpenRig.
- **Evidence:**
  - [x] Run two actual OpenRig rigs with independently authenticated agents: verify cross-rig raw events with zero inference, direct messages, acknowledgements and backend search; include an optional plain-text filter case.
  - [x] Verify offline/restart/retry recovery and denial of unauthorized projects, then exercise two rigs using separate federated ADHD servers with exact rig/agent/project/source provenance and no transferred roles.

- **Qualification evidence:** [Native52 UI/interop](../../verification/native34-ui/manifest.json) and [exact admitted-image52 UI/interop](../../verification/image34-ui/manifest.json) each include 11 actual pinned OpenRig0.6.14 checks: two independently authenticated terminal infrastructure rigs, real daemon/hub restart, source retry, raw zero-inference delivery, private messages/acks/search, optional controlled filtering and canonical federation through distinct Kafka services. The adapter scope does not claim an LLM coding-provider workload. All item-specific checks pass; the parent remains open until its MULTI-008/KAFKA-009 integrated-qualification dependencies close.
