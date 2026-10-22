# Design traceability

<!-- literate-ai:authority-reviewed sha256:8777208fbd783c87e24e71300b9331b27d82809079c70afbebd8d432f77219eb -->

[Project guide](../README.md) → design traceability

Behavior belongs in Component specifications; target variance belongs in Flavors;
conversion technique belongs in exact skills; execution order belongs in workflows;
model eligibility belongs in routing; validation and authorization remain framework
policy. The manifest selects the source-intelligence provider, while its local database
remains
derived evidence outside source authority. Changes should update the owning artifact,
its nearby explanation or diagram,
and an end-to-end test. Illustrations aid understanding; prose requirements and
acceptance scenarios remain normative. See the [project map](../user/project-layout.md).

The contextual evidence and adaptive retrieval direction in `PROJECT.md` maps to
INFO-002, QUERY-001, SEARCH-001 through SEARCH-003 and INDEX-001 in the
[active queue](../roadmap/active-work.md). The
[shared design](../roadmap/adaptive-retrieval.md) describes their future workflows
and acceptance boundaries. Current Component contracts still provide immutable
publications, literal historical search and semantic matching of new publications;
QUERY-001 adds a separately qualified snapshot history scan through the three
`components/hub/history/` contracts. Generated indexes retain separate roadmap gates.
Runtime changes must update the owning Component contracts and pass their recorded
generation and independent acceptance gates before usage documentation claims them.

The federated discovery direction in `PROJECT.md` maps to FED-001 in the active
queue. `components/hub/federation/spec.md` owns asynchronous discovery across
authorized direct peers, approved export evidence, provenance and explicit partial
coverage. Durable HTTP submit/status queues provide the first transport; pub/sub
remains an alternative for correlated peer queries. The profile-2 multi contract
now supersedes the original one-project server boundary. QUERY-001's broader
contextual-history scans remain separate work. FED-001 records the native, upgrade,
multi-hub and container acceptance needed to qualify this implementation.

The multiple-project direction in `PROJECT.md` supersedes the single-project
product restriction through pending MULTI-001 through MULTI-008 in the active
queue. The [multiple-project plan](../roadmap/multi-project.md) maps identity,
admission, durable partitioning/migration, agent evidence workflows, peer routing,
hot Admin configuration and resource fairness to their owning hub contracts.
The new `components/hub/multi/spec.md` owns the target multi-project contracts;
the combined architecture now has [source34 lifecycle admission and guarded staging](../../verification/multi-eventing/image-admission-34.json)
and an [independently audited exact image payload](../../verification/multi-eventing/image-payload-34.json).
Final program qualification remains open. Current native evidence includes
[151 project and migration groups](../../verification/multi-eventing/native-project-migration-34.json),
[15 eventing/protocol/durability checks](../../verification/multi-eventing/native-eventing-34.json)
and [66 complementary Kafka/federation checks](../../verification/multi-eventing/native34-complement/manifest.json).
The source30 container evidence remains historical; current source34 runtime
image/platform qualification is running. The [completion review](../../verification/multi-eventing/completion-review-34.json)
keeps the individual remaining predicates and substantive model/restore gaps explicit.

The Kafka pub/sub direction in `PROJECT.md` maps to pending KAFKA-001 through
KAFKA-009 and the [eventing plan](../roadmap/kafka-pubsub.md). It replaces mandatory
semantic subscription matching with per-server Kafka, independent A2A subscriber
delivery and optional plain-text filters. Backend originals/search remain distinct
from broker retention. Hub contracts own protocol/durability/access changes;
deployment artifacts and dependency Flavors own Kafka/client packaging and the
Compose/Kubernetes application. Coordinate MULTI migration and final acceptance;
historical model-only evidence does not qualify this architecture. The initial
admission above binds the combined implementation; program closure still requires
the complete native, container and deployment evidence.

`components/hub/eventing/spec.md` owns the selected REST Proxy adapter, exact
commit-versus-position offset semantics and recoverable hot transport transitions.
`components/hub/resources/spec.md` owns bounded model/network/eventing lanes,
per-project fairness, deadline/revision fencing and Admin-only resource diagnostics.
The generated candidates and independent fault, browser, SDK and deployment reports
remain separate from final lifecycle admission and release evidence.

MODEL-001 owns the [model Compose deployment](../../deploy/model.compose.yaml),
checkpoint-verifying startup helper and live SystemOne acceptance. The model
container is deployment authority outside the generated hub source; its pinned
image, reviewed checkpoint and GPU configuration are documented in the
[model service guide](../admin/model-service.md).

AUTH-001, ROLE-001 and CONFIG-002 map to the hub identity and configuration
contracts: local bootstrap credentials, proved OIDC identities, one local role,
live settings, sessions and transaction recovery. FED-002/FED-003 map to
`components/hub/directory/spec.md` and `directory/queries.md`: stable server
identities, local-only email correlation, bounded catalogs and canonical-only
source jobs. PROTO-001 owns the [protocol inventory and schemas](../protocol/README.md);
all peer extensions remain separate from agent-facing A2A. Independent HTTP,
SDK, process-kill, browser and Docker evidence qualify the corresponding queue
items; a contract or candidate alone does not close them.

INFO-002 extends the archive through `components/hub/evidence/spec.md`: contextual
record envelopes, immutable correction links, ingestion-time reference snapshots,
publication watermarks and bounded public traversal. Its acceptance binds original
text/JSON and historical membership across retries, restart and actual earlier-store
upgrades. QUERY-001 and the retrieval/index program remain separately qualified work.

QUERY-001 owns owner-isolated history jobs, the exact typed-choice evaluator and
recorded exchanges, frozen scope, durable cost reservations, independent scheduling,
continuation/cancellation and hot Admin controls. Qualification requires live
model quality cohorts, wire validation, crash recovery, SDK, browser and container
evidence; a diagnostic candidate alone does not close the request.

The [history qualification](../../verification/history-qualified.json) binds the
retained-source artifact and Docker image to all 27 passing reports. Query results
remain bounded/fallible; the four retrieval/index requests retain independent gates.

The [retrieval qualification](../../verification/retrieval-qualified.json) binds
the admitted artifact and image to 33 independent reports. Scores select possible
evidence; they never certify truth, support or exhaustive scope. Archive fallback and paired replay have separate qualification records; adaptive
promotion retains its own acceptance gate.


Archive contracts in `components/hub/archive/spec.md` and `interface.md` compose
owned Retrieval/History children with a separate original-evidence sufficiency
policy, stage costs and uniform256 sampled audits. The [archive qualification
record](../../verification/archive-qualified.json) records its current evidence
status; SEARCH-002 closes only when that record and its required native/Docker,
model, SDK, protocol and browser gates pass. Operational judgments remain excluded
from original publications. SEARCH-003 and INDEX-001 retain independent gates.

The [feedback qualification](../../verification/feedback-qualified.json) binds
SEARCH-003's owned attempts, independent human labels, joined cohorts, durable
exposure and fresh paired replay to its admitted artifact and native/Docker
proofs. Cached candidate judgments never become archive facts.

INDEX-001 authority is `components/hub/optimization/spec.md`, `selection.md` and
`interface.md`. It generates only bounded existing native recipe primitives from
confirmed recurring misses. Training freezes one winner before held-out use;
current labels, expected child runs, original snapshots and actual aggregate costs
fence qualification. A complete isolated public generation catches up before one
Store transaction switches its primitive and active rows. Authoritative selection
survives derived-index damage and runtime changes; the latter invalidate claims
of current runtime qualification. Explicit operator recipe patches durably reset
the override. Lifecycle, independent model/cohort, fault, SDK, browser, protocol and
container evidence remain required before the active roadmap gate can close.

The subsequent identity/registry corrections remain an open release gate.
The [retired identity guard review](../../verification/multi-eventing/identity-guard-review-32.json)
explains Config/Store serialization and the corrected legacy snapshot boundary;
[candidate33 source identity](../../verification/multi-eventing/identity-guard-33-source.json)
is provisional. The [native eventing refresh](../../verification/multi-eventing/native-eventing-32.json)
retains its exact earlier artifact scope. The
[fanout/offset boundary qualification](../../verification/multi-eventing/eventing-boundaries-31.json)
and [criterion audit](../../verification/multi-eventing/criterion-audit-31.json)
retain historical source31 evidence. The
[expired canonical-owner qualification](../../verification/federation-stale-owner/manifest.json)
proves that an unavailable canonical owner is not replaced by a noncanonical copy.
Final artifact/image evidence must be rebound after the outstanding corrections.

The [registry-removal diagnostic](../../verification/multi-eventing/downgrade-33.json)
preserves the actual source33 failure. The
[corrected registry qualification](../../verification/multi-eventing/registry-guard-34.json)
passes dry/apply/file-reload rejection and cold restart with retained originals
and acknowledgements, both with and without a default project. The
[legacy guard trace](../../verification/multi-eventing/legacy-guard-33.json)
is targeted module-unit evidence of zero checkpoint opener calls, with a real
positive tracing control; it is not a public legacy lifecycle qualification.

The [exact source34 eventing refresh](../../verification/multi-eventing/native-eventing-34.json)
passes fifteen native eventing, SDK and fanout/commit crash checks. Its
[stale canonical-owner refresh](../../verification/federation-stale-owner/manifest34.json)
passes four routing checks; these are native results and do not attest the pending
container or deployment qualification.

The [source34 metadata refresh](../../verification/multi-eventing/metadata-refresh-34.json)
regenerates native-test declarations and the source BOM against the current
official recipe and locked graph. It changes no application or native-test bytes.
The first recipe-mismatch lifecycle attempt remains failed. The repaired
[current admission](../../verification/multi-eventing/admission-34-result.json) passed,
including all18 native declarations and the unchanged91 independently reviewed
oracle vectors. These generated declarations do not replace the independent
stateful guard, crash or browser qualifications.

The [real coordinator qualification](../../verification/multi-eventing/rebalance-34/assessment.json)
retains actual managed-observer membership/assignment changes beside the explicitly
assigned bridge, genuine broker commit fencing, a hub kill and durable recovery.
It does not claim managed bridge ownership transfer or multiple-writer availability.
Current native [117 controlled workflow/SDK groups](../validation/deep-controlled-34-native.json),
[69 existing live-model cases](../validation/deep-live-model-34-native.json) and
the [six-call filter/backend witness](../validation/live-eventing-backend-34-native.json)
are distinct from the still-open positive optimizer qualification and selective
project restore capability.

Selective target recovery is now owned by `components/hub/project-recovery/spec.md`,
its `components/hub/project-recovery/interface.md`
and MULTI-007. The future2.1 profile preserves current global authentication and
unrelated project state; explicit initialization cannot bypass a known lost store.
[87 independent vectors and six examples](../../verification/project-recovery/contracts.json)
qualify contract shape only. Runtime implementation, crash boundaries and exact
successor native/image/platform recovery remain open. The browser authentication
transition contract in `components/hub/identity/spec.md`
also fences old-context responses; [native35ui evidence](../../verification/multi-eventing/admin-session-35/manifest.json)
is a development result, not source34 image repair or successor admission.

Recovery capacity now counts each accepted external mutation receipt, including
coalesced apply messages; authenticated exact retries remain free at the cap.
[Nine frozen component checks](../../verification/project-recovery/components/manifest.json)
cover callback dependencies, resource ticket retirement and pure transport/work
transformations. They do not qualify complete restore, real cancellation or
successor image operation. The durable decision coordinator remains under integration.

[Two frozen real HTTP checks](../../verification/project-recovery/http-epoch/manifest.json)
hold actual loopback responses across an epoch switch: the old target request
cannot succeed, while another project's request completes and retains its lane.
A stale request is also rejected before opening a TCP connection. This is isolated
Net/Resources evidence; complete restore and actual model/peer/Kafka crossover
remain unqualified. [The offline backup validator](../../verification/project-recovery/backup-validator.json)
passes 33 checks over retained actual snapshots, including original principal and
project-reference proofs, without opening DETS or calling live services.

[Actual process-kill evidence](../../verification/project-recovery-crash/manifest.json)
records a predecision pass and an interrupted snapshot installation that exposed
an availability-only comparison stopping startup. A Coordinator-only repair
resumed that same interrupted installation, preserved retained target and current
unrelated state, and passed another cold restart. Remaining crash boundaries,
checkpoint hardening, complete recovery and successor platform qualification stay open.
[Development09 kill checks](../../verification/project-recovery-crash/dev09/manifest.json)
also pass the actual after-first-snapshot boundary without a default project and
the before-cleanup boundary for an archived project, using real Kafka and no model.

[Guarded native12 recovery](../../verification/project-recovery-native/manifest-dev12.json)
passes18 native regressions; the separate guarded portable rebind report passes12
actual CLI/cold-start/fsync-kill groups. The ordinary-checkpoint parser passes82
vectors on both OTP27 and OTP29; six actual hostile rebind requests reject before
metadata changes. [Development13 federation HTTP](../../verification/project-recovery-federation/manifest-dev13.json)
qualifies authenticated recovery503 with Retry-After1 independently from A2A's
HTTP200 JSON-RPC domain failures. [A real pending-model service case](../../verification/project-recovery-pending-model/manifest.json)
also passes cancellation across a live target-only restore and a subsequent cold
restart. Full peer/Kafka callback crossover, the complete crash matrix, formal
successor admission and exact image/platform coverage remain separate open gates.
