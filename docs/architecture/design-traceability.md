# Design traceability

<!-- literate-ai:authority-reviewed sha256:6c8435b97018930dd68c6eac895c4a4ddd713833ee75ecc5c948bd5a23a2321c -->

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

[Formal source41 admission](../../verification/eventing-readiness-source41/admission/manifest.json)
and the [compiled image audit/two-build comparison](../../verification/ownedMULTI008/source41-compiled-image-positive/audit.json)
bind the source, actual image, cache and context. Both sequential no-cache,
network-free builds produced identical image/configuration/layer identities on
the pinned amd64 builder. Current independently scoped positives include:

- [Core13/94](../../verification/ownedMULTI008/source41-core13-positive/audit.json),
  including [wire8](../../verification/ownedMULTI008/source41-core13-positive/wire.json).
  [Protocol export conservation](../../verification/ownedMULTI008/source41-protocol-conservation/review.json)
  is semantic rather than byte identity; the published snapshots are preserved.
- [Compose11/Kind10](../../verification/ownedMULTI008/source41-baseline-platform-positive/audit.json):
  complete model-free programs, replacement, same-volume broker patch upgrade,
  cold restore and selective recovery preserving newer Blue/global state.
- [Secured Kind7](../../verification/ownedMULTI008/source41-secured-kind-positive/audit.json):
  TLS/native OAuth, trust/token/Secret/key rotations, durable progress and unchanged
  hub identity; private plaintext proxy-to-broker transport remains explicit.
- [Deployed model programs](../../verification/ownedMULTI008/source41-deployed-model-positive/audit.json):
  eight outer checks and 12 actual provider POSTs across both platforms, with typed
  filter/search gates and privacy checks; no general accuracy claim.
- [Metadata readiness23](../../verification/eventing-readiness-compiled41-positive/audit.json)
  and [committed retention recovery3](../../verification/eventing-retention-compiled41-positive/audit.json)
  exercise the successor Eventing behavior on the compiled image.
- [SDK17](../../verification/eventing-readiness-sdk17-positive/manifest.json) and
  [callback5/28](../../verification/recovery-callback41-positive/manifest.json)
  cover their complete SDK and pinned incoming/query/HTTP callback programs;
  callback instrumentation is distinct from default-entrypoint deployment gates.
- [Focused UI32](../../verification/ownedMULTI008/source41-focused-ui-positive/audit.json),
  [cache17](../../verification/container-cache41-positive/audit.json) and
  [scalar ABI19](../../verification/ownedMULTI008/source41-image-abi-positive/audit.json)
  retain their distinct UI, cache and observer-compatibility scopes.

The complete [Kafka14/68 run](../../verification/kafka41-full14-positive/audit.json)
also passes on the current image, with owned-service cleanup and protected
services unchanged. The [complete recovery25](../../verification/recovery41-full25-positive/manifest.json) and [final property composition](../../verification/ownedMULTI008/source41-final-composition-after-full25/review.json)
complete the runtime requirement review; the [active queue](../roadmap/active-work.md)
records the final documentation-authority/receipt/context bridge and proper parent closure.
Earlier CNI, model, migration and subsystem evidence keeps its exact source scope;
the [conservation review](../../verification/ownedMULTI008/source41-conservation-join-review/review.json)
states the permitted joins and limits. The changed guides are included in the
proper-CLI documentation/authority transition and reviewed receipt/context bridge.
Historical source40/compiled05 admissions and false invocations remain immutable.

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

The [first documentation authority bridge](../../verification/source41-first-documentation-bridge/manifest.json)
binds the reviewed guides to a CLI-issued receipt and the unchanged qualified
source, complete staged context and compiled image. [Dependency-ordered CLI closure](../../verification/source41-roadmap-parent-closure/manifest.json)
records all six parent outcomes. The [active queue](../roadmap/active-work.md)
tracks the final authority refresh after archival and its terminal verification.
