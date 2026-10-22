# Multiple projects per ADHD server

- **Status:** partial
- **Owning queue item:** [MULTI-001](active-work.md#multi-001-define-multiple-project-identity-boundaries-and-compatibility)
- **Completion / archival evidence:** pending while MULTI-007/MULTI-008 and their integrated dependencies remain open

## Direction and current boundary

Each ADHD server supports multiple projects while continuing to federate with
other servers. One server per project remains a valid deployment. The contracts
and implementation are admitted; final combined qualification remains open under
MULTI-007/MULTI-008 and their dependencies. Historical results keep their original
artifact and runtime scope.

The `components/hub/multi/spec.md` contract and
[scope inventory](../protocol/scopes.json) own the boundaries. The current
[source41 evidence join](../../verification/ownedMULTI008/source41-conservation-join-review/review.json)
distinguishes changed Eventing/recovery paths from unchanged subsystems. The
[compiled-image admission](../../verification/ownedMULTI008/source41-compiled-image-positive/audit.json)
binds source `d41ecddd…` and image `207ad8e3…`; it does not itself close runtime gates.

Current scoped positives include [Compose11/Kind10](../../verification/ownedMULTI008/source41-baseline-platform-positive/audit.json),
[secured Kind](../../verification/ownedMULTI008/source41-secured-kind-positive/audit.json)
with seven reported checks and 51 assertion sites, and
[Admin/Events/recovery32](../../verification/ownedMULTI008/source41-focused-ui-positive/audit.json)
with [root's named capture review](../../verification/ownedMULTI008/source41-focused-ui-manual-review/review.json).
The separate [deployed-model programs](../../verification/ownedMULTI008/source41-deployed-model-positive/audit.json)
pass on both platforms: eight outer checks and twelve actual POSTs total, with the
original filtering, cited-query, Blue-progress, privacy and hot disable/resume gates.
These are separate programs, not one fresh full historical matrix. Complete current
core, federation and offline-rebind regressions, final requirement composition and
the documentation/receipt/context bridge remain open; retained failed aggregates
stay false.

This program belongs to ADHD's hub Component, tests, tooling and guides. It does
not require a framework pin upgrade, a new model or a database replacement. The
[Kafka program](kafka-pubsub.md) supplies one Kafka service per server for project
events, optional model filters and A2A agent access; broker replication is not the
federation transport. BUILD-001's upstream publication/adoption remains separate.
Implementation proceeds in authorized local feature branches; external publication
remains separately governed.

## Selected identity and admission model

| Entity | Identity and boundary |
| --- | --- |
| Server | One stable server ID; owns listener, durable configuration, users/authentication, server roles, model resources and peer trust. |
| Project | Stable opaque project ID distinct from a mutable display name and legacy aliases; belongs to one local server. Federated references include server ID and project ID. |
| User | Server-local ID, name, email and local/OIDC identity; exactly one effective server role. Explicit project admission is separate from that role. |
| Agent | Server-local ID and owner user; explicit memberships can admit the agent to multiple projects. Each operation uses one authorized project context. |
| External source scope | Existing provider/host/tenant/resource identity, distinct from an ADHD project; a canonical claim names its owning server/project pair. |
| Project data/job | Explicit project ID plus existing actor/resource identity; no ownership inferred from an ID prefix, display label, browser selection or model output. |

Keep Admin, Developer and Viewer as server-wide roles. Admin retains full access
to every project. The admission model adds an Admin-managed set of
projects for non-Admin users without introducing project roles: Developer keeps
the existing ability to create agents only on their own behalf, within admitted
projects; Viewer stays read-only. An agent's grants cannot exceed its owner's
current admission. Admin may manage agents for any owner. Only Admin grants
project access; Developer cannot admit themselves by creating an agent.

Keep existing local admin bootstrap/recovery and OIDC group-to-highest-server-role
rules. OIDC login does not automatically admit a new account to every project.
Specify any default admission explicitly; default to no project admission for new
non-Admin accounts. Migration admits existing users/agents to the legacy project
so upgrading preserves their prior access. Changes to membership, account status
and effective role must apply live to sessions, credentials and background work.
Equal emails across peers may correlate identity but never transfer roles,
admission, agent ownership or credentials.

Default coordination is project-local. A multi-project agent publishes,
subscribes, sends, polls and acknowledges in an explicitly selected project;
membership in two projects does not bridge their private messages or subscriptions.
Project event subscriptions are unfiltered by default in the target architecture;
an optional plain-text model filter narrows an authorized stream. Models are not
required for raw pub/sub or literal backend search. See KAFKA-001 through
KAFKA-009 for durable broker handoff, A2A acknowledgements and deployment scope.
Explicit multi-project discovery/query fan-out may search only admitted projects,
using separate project evidence and coverage. It does not implicitly publish a
result into another project. No automatic cross-project subscription matching is
included in the first implementation; agents may subscribe separately per project.

Project creation, rename, admission changes, archive and resume are hot Admin
operations. Archive must preserve originals and define the disposition of accepted
work, existing deliveries and canonical claims; it must not silently delete data.
Hard deletion, project transfer between servers and high-availability replication
are outside this first program and require separately specified policies.

A newly configured project stays uninitialized until an authenticated Admin plans
and applies explicit initialization. A known missing initialized store requires
recovery; it must never be silently recreated. See the operator's
[project initialization and recovery guidance](../admin/operations.md).

## Required scope inventory

MULTI-001 must classify every operation and configuration field before generation.
Use this minimum matrix and enumerate exact fields/operations in the contracts:

| Surface | Required scope or decision |
| --- | --- |
| Users, local passwords, OIDC, role/group policy, sessions | Server-wide; project admission checked independently on every authorized operation. |
| Agent credentials and owners | Server identity with explicit project grants; possession of a token never validates a requested project by itself. |
| Publish, get, search, source-event deduplication | Project; same source/item IDs in different projects cannot collide. |
| Direct messages, subscriptions, deliveries, acknowledgement | Project and actor; membership in another project never consumes these records. |
| Context/referents, corrections, citations, snapshots | Project; validate every reference, page token and transitive traversal. |
| History, retrieval, archive and federation queries | Project and owner; freeze explicit fan-out scope, budgets and policy revisions. |
| Feedback, cohorts, replay, recipes, indexes and optimizer selection | Project; shared code/model resources do not imply shared training or selection state. |
| Idempotency, sequence namespaces, cursors, caches and retries | Bind project and actor; cross-project reuse must never retrieve another project's result. |
| Catalogs, canonical source claims and export allowlists | Project-qualified evidence and export authorization, with server-wide conflict detection. |
| Listener, public URL, configuration location, global model capacity | Server-wide; configuration location remains the sole restart exception. |
| Matcher/retrieval policies, budgets and project descriptions | Explicit project overrides of declared server defaults; document inheritance/reset and effects on accepted work. |
| Peer authentication and trust | Server-wide transport identity plus explicit allowed origin/destination projects and export policy. |
| Health, status, audit and metrics | Minimal public server health; authorized server totals and project details without leaking hidden project existence. |

Authorization must happen before pagination, counts, cached-result reuse and model
request construction. Recheck authorization and export policy before committing
or returning asynchronous results. Hidden/unknown project and resource errors
must have a documented, consistent disclosure policy. Audit access changes and
operations using stable server/project/actor identities without recording secrets.

## Execution order and deliverables

| Work item | Deliverable | Prerequisites |
| --- | --- | --- |
| MULTI-001 | Identity, access and lifecycle contracts; full scope matrix; exact compatibility/wire design. | First action: inventory and author contracts. |
| MULTI-002 | Durable project registry, complete state partitioning and recoverable legacy migration. | MULTI-001, KAFKA-001 |
| MULTI-003 | User admission and agent memberships with server-side, live authorization. | MULTI-001, MULTI-002 |
| MULTI-004 | Project-scoped coordination and evidence pipelines; explicit local query fan-out. | MULTI-002, MULTI-003, KAFKA-001 |
| MULTI-005 | Multi-project catalogs, peer trust and asynchronous canonical routing. | MULTI-001, MULTI-003, MULTI-004 |
| MULTI-006 | Project-aware hot Admin forms, project selector and server/project settings. | MULTI-002 through MULTI-005 |
| MULTI-007 | Fair shared workers, budgets, lifecycle fencing, diagnostics and recovery. | MULTI-002, MULTI-004, MULTI-005 |
| MULTI-008 | Native/Docker qualification, protocol conformance and upgrade/operator/client documentation. | MULTI-001 through MULTI-007, KAFKA-009 |

Author normative contracts before implementation; write independent acceptance
alongside each phase. The final phase integrates existing phase evidence and runs
the complete regression matrix rather than postponing isolation tests until last.
Each active-work entry carries its own unchecked subtasks and evidence gate.
Complete MULTI-001 identity design, then KAFKA-001 transport design, before the
shared persistence/workflow phases. Coordinate the legacy migration with
KAFKA-008 and require combined Kafka qualification before MULTI-008 closes.

## Storage, configuration and migration contract

Select and justify backend storage layout in MULTI-002, separating it from
Kafka event transport and coordinating outbox/cutover recovery. Preserve the current
DETS backend unless evidence requires a separately recorded change. Every key,
relationship, index manifest, cache and durable worker record must have a defined
project boundary regardless of whether storage is shared or separated per project.
Keep one writer per physical store and atomic acceptance/idempotency semantics.

Map the existing single-project configuration/store into one explicit default
project. Preserve its original project identity/aliases, server ID, user and agent
ownership, credentials, source identities, immutable originals, private deliveries,
acknowledgements, in-flight jobs and query results. Retain optimizer selections and
qualification provenance; where the new architecture invalidates qualification,
mark it stale and require requalification rather than claiming equivalence.

Provide preflight, schema versions, backup requirements and recoverable migration
markers. Concurrent startup, interruption, partial config/store commits and restore
collisions must fail closed. Reapplying migration is safe. Document when an older
binary cannot open the upgraded store and require restoring the matching backup
rather than promising an unsafe downgrade. Specify full-server and project-level
backup/restore, identity collisions and missing user/agent references explicitly.

Project identity cannot change through rename. Resolve the current configurable
`project_id` rename behavior with stable IDs and aliases, preserving old provenance
and retry behavior. Do not silently merge projects whose labels or aliases collide.

## Protocol and federation contract

Before assigning new version numbers, classify each wire change for compatibility.
Continue agent communication over A2A; peer transport may remain HTTP. Publish
exact request/response/error schemas, state machines, bounds, version/capability
negotiation, canonicalization, request correlation and normative examples. Maintain
the rigorous existing unknown-field, framing and independently validated schema
requirements. A2A contextId and UI selection alone never authorize project access.

Permit legacy omission of project context only when the credential or negotiated
legacy endpoint is bound unambiguously to the migrated default project. Document
the exact rule; never choose the first project or infer one from user input.
Old project-bound peers must be mapped explicitly to their permitted project pair.
Reject unsupported or ambiguous interactions without silent downgrade or exposing
other local projects. Test both upgraded-to-old and old-to-upgraded directions.

Authenticate the peer server before trusting origin/destination project claims.
Authorize each pair against current grants. Bind durable request/status/results to
origin server, origin project, destination server/project, query ID and permitted
evidence. Preserve deadlines, cancellation, retries and duplicate suppression.
Shared endpoints must not let one remote project impersonate another or poll its
queries. Keep credentials, private messages and restricted context out of exports.

Catalog discovery lists only projects and source scopes approved for that peer.
Cache complete advertised catalogs by server/project/revision with freshness and
invalidation rules. Canonical ownership of an exact external scope names one
server/project pair; duplicates across projects on the same server are conflicts
just as duplicates across servers are. Copies never become canonical implicitly.
Route to a local canonical project without self-HTTP or relaxed authorization.
Fan-out results identify project, owner, evidence, coverage and unavailable scopes;
discovery never claims knowledge of all projects in the federation.

## Completion evidence

Use at least two populated projects on one server, a third inaccessible project,
two coordinating agents per populated project and one explicitly multi-project
agent. Deliberately reuse actor-local IDs, source IDs, message IDs, labels and
content across projects. Test each public operation and every indirect path for
cross-project reads, writes, deduplication and model-input leakage.

Use at least three real federated server processes, with multiple projects on
each, to test discovery, same-server and remote canonical ownership, conflicts,
mixed versions, export restrictions, stale caches, outages and bounded retries.
Verify asynchronous incremental results and accurate partial coverage.

Run actual legacy-store migrations and process-kill tests around migration,
configuration and worker commits. Exercise live access/OIDC changes, project
archive/resume, token rotation, browser switches and concurrent Admin revisions.
Saturate one project's matcher/query/optimizer and remote requests while another
continues within documented fairness bounds; retain real inference accounting.

Qualify the exact generated artifact and Docker image with independent SDK,
wire-validator, desktop/mobile browser and existing live Nemotron model evidence.
Run a model-free raw pub/sub and literal-search profile as well as optional
short-response filtering/search evidence. KAFKA-007 adds real Compose and
Kubernetes deployment qualification. Keep semantic subscription matching fast
and decisive. Record ordinary single-project
regressions alongside multi-project results. Close the program only when every
MULTI item has its required evidence; document remaining deployment/publication
gates separately and make no claims from old single-project qualification alone.
