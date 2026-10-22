# Design traceability

<!-- literate-ai:authority-reviewed sha256:70258782794b44b7a02876a42fed27ea339e8cf34707f7a4526f6f2171cab970 -->

[Project guide](../README.md) → design traceability

Behavior belongs in Component specifications; target variance belongs in Flavors;
conversion technique belongs in exact skills; execution order belongs in workflows;
model eligibility belongs in routing; validation and authorization remain framework
policy. The manifest selects the source-intelligence provider; its local database
is derived evidence. The [project map](../user/project-layout.md) identifies the
owner of each change. Contract, generated implementation, actual acceptance and
release evidence remain separate records.

## Implemented behavior and owning contracts

The contextual evidence and adaptive retrieval program in `PROJECT.md` is
implemented. The [shared design](../roadmap/adaptive-retrieval.md) records its
workflow and acceptance boundaries. Its original roadmap items are closed with
independent qualification; they are not future-only capabilities:

| Work | Owning contracts | Qualification scope |
| --- | --- | --- |
| INFO-002 contextual originals | `components/hub/evidence/spec.md` | Immutable envelopes, correction/context links, frozen reference membership and bounded traversal; [evidence qualification](../../verification/context-qualified.json). |
| QUERY-001 history | `components/hub/history/` | Owner-isolated frozen scans, typed choices, reservations, continuation/cancellation and hot controls; [history qualification](../../verification/history-qualified.json). |
| SEARCH-001 retrieval | `components/hub/retrieval/` | Native contextual BM25, optional semantic relevance, owned jobs and replaceable indexes; [retrieval qualification](../../verification/retrieval-qualified.json). |
| SEARCH-002 fallback/audits | `components/hub/archive/` | Owned Retrieval/History children, original-evidence assessment, fallback, sampling and stage costs; [archive qualification](../../verification/archive-qualified.json). |
| SEARCH-003 feedback/replay | `components/hub/feedback/` | Independent labels, cohorts, recurrence and fresh same-snapshot paired replay; [feedback qualification](../../verification/feedback-qualified.json). |
| INDEX-001 adaptive recipes | `components/hub/optimization/` | Bounded native recipe trials, frozen training winner, held/regression checks and atomic caught-up promotion/rollback; [optimization qualification](../../verification/optimization-qualified.json). |

These qualification records describe their exact artifacts, runtimes and labeled
fixtures. They do not establish universal model accuracy or automatically qualify
a newer integrated artifact. Model judgments and human labels remain fallible;
rankings never certify truth, exhaustive coverage or sufficient evidence.

AUTH-001/ROLE-001/CONFIG-002 map to identity/configuration contracts: local bootstrap,
proved OIDC identities, one server-local role, sessions, live settings and durable
configuration transactions. FED-001 owns direct-peer asynchronous HTTP discovery,
authorized exports and partial coverage. FED-002/FED-003 add local-only email
correlation, bounded catalogs and canonical server/project routing; equal email
never transfers roles or project grants. PROTO-001 owns the
[wire inventory and exact schemas](../protocol/README.md), including independent
agent, Admin, OIDC, model and peer interfaces.

## Current multi-project and eventing integration

The [multiple-project plan](../roadmap/multi-project.md) maps MULTI-001 through
MULTI-008 to identity, admission, partitioned storage, agent workflows, federation,
Admin controls, fairness and qualification. `components/hub/multi/spec.md` replaces
the original single-project boundary. `components/hub/resources/spec.md` owns
bounded independent model/network/eventing lanes and epoch/revision fencing.

The [Kafka plan](../roadmap/kafka-pubsub.md) maps KAFKA-001 through KAFKA-009 to
per-server Kafka with A2A delivery, optional filtered subscriptions and backend
search. `components/hub/eventing/spec.md` owns the REST Proxy adapter, durable
outbox/materialization, explicit commits, raw/filtered fanout, quarantine/repair
and bounded historical replay. Agent acknowledgements remain distinct from Kafka
positions; broker retention does not delete immutable originals.

Application 2.1 selective recovery is implemented under
`components/hub/project-recovery/{spec.md,interface.md,interface.schema.json}`.
Admin explicitly plans/applies initialization of unknown empty targets, or restores
one missing/logically empty project from verified backup. Current global accounts,
settings and unrelated project state remain intact. Known lost initialized stores
never become fresh empty projects. External journals, selected storage routes,
fresh project/allocation/topic epochs and private checkpoints fence recovery;
offline portable rebind is a separate CLI operation. Operational procedures are in
[the Admin guide](../admin/operations.md) and
[first-use initialization](../admin/web-console.md#first-use-project-initialization).

[Formal source40 admission](../../verification/project-recovery/development40/admission/manifest.json)
and [compiled05 admission/cache audit](../../verification/container-precompile-image40/compiled05-admission/manifest.json)
bind the unchanged source artifact to its exact packaged image and authored
contracts. The [independent build comparison](../../verification/container-precompile-image40/reproducibility05-positive/manifest.json)
records two identical sequential builds without cache or network access for the tested pinned
amd64 builder. The following current deployment results are independently scoped:

- [Compose11 plus Kind10](../../verification/ownedMULTI008/compiled05-baseline-platform-positive/manifest.json):
  complete model-free programs, replacement, Compose broker patch upgrade, full
  cold restore and selective target recovery preserving current Blue/global state.
- [Secured Kind](../../verification/ownedMULTI008/compiled05-secured-kind-positive/manifest.json):
  actual TLS/native OAuth, hot token/trust checks, Secret/certificate and pod
  rotations, durable cursor and unchanged hub identity, with strict cleanup.
- [Deployed model children](../../verification/ownedMULTI008/compiled05-deployed-model-terminal/manifest.json):
  all 12 Compose/Kind filtering/backend-search scenarios qualify independently;
  the outer launcher 143/false outcome remains recorded unchanged.

These positive gates do not declare MULTI/KAFKA integration or the whole goal
complete. The [active queue](../roadmap/active-work.md) owns the integrated native/core,
Kafka, complete recovery, CNI, browser and final documentation/lifecycle review.
Applying changed operating guides requires a fresh proper-CLI authority/receipt
transition. The old admission and runtime reports retain their original hashes;
an unchanged-source/image bridge must be a separate reviewed record.

MODEL-001 owns the optional [model Compose deployment](../../deploy/model.compose.yaml),
checkpoint-verifying helper and SystemOne service. Raw delivery and literal search
require no model. The [model guide](../admin/model-service.md) distinguishes serving
source, operator-supplied checkpoint and CUDA/base terms. The
[hub and service inventory](../admin/event-service.md#artifact-and-license-inventory)
separates application Apache-2.0 from external dependency licenses.

## Historical integration checkpoints

Earlier source30–34 and recovery development reports remain useful diagnosis and
regression records. Their open-gate language describes the checkpoint when they
were recorded; it does not override the current contracts or positive gates above.
The [source34 completion review](../../verification/multi-eventing/completion-review-34.json),
[registry-removal diagnostic](../../verification/multi-eventing/downgrade-33.json),
[corrected registry guard](../../verification/multi-eventing/registry-guard-34.json)
and [expired canonical-owner checks](../../verification/federation-stale-owner/manifest34.json)
preserve their exact artifact scopes and earlier failures.

Recovery integration similarly retains the
[initial process-kill findings](../../verification/project-recovery-crash/manifest.json),
[guarded native12 checkpoint](../../verification/project-recovery-native/manifest-dev12.json)
and [development13 federation HTTP](../../verification/project-recovery-federation/manifest-dev13.json).
These do not become current image proof by relabeling them. Current authority,
source/image identity, unchanged inputs and each required acceptance boundary must
be established explicitly before final roadmap closure.
