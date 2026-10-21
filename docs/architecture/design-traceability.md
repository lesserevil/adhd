# Design traceability

<!-- literate-ai:authority-reviewed sha256:1d820a771b1e28006a89c01e1063a59e2f44e1c0e57b991211531965604fa3bf -->

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
the combined architecture now has an [initial lifecycle admission](../../verification/multi-eventing/lifecycle-admission-30.json)
and an [independently audited container payload](../../verification/multi-eventing/image-payload-30.json).
Final program qualification remains open: the current native evidence is linked
from [project and migration qualification](../../verification/multi-eventing/native-project-migration-30.json)
and [eventing and federation qualification](../verification/native-eventing.json);
[container project/protocol qualification](../../verification/multi-eventing/image-project-30.json)
now covers 74 groups. Broader container regressions and deployment recovery gates
remain in progress in `verification/multi-eventing-progress.json`.

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
