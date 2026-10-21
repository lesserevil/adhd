---
name: Multiple project boundaries
summary: Stable projects, admission, scoped state and server federation
kind: component
---
# Multiple projects on one server

This contract replaces earlier single-project restrictions, mutable project
identity and project-bound peer identity. Other contracts remain in force. MUST,
SHOULD and MAY use RFC2119/RFC8174 meanings. Model output, a browser selection,
an A2A contextId and possession of another project's record ID are never authority.

## Configuration and identities

For container and pod deployments, root `host` accepts `0.0.0.0` in addition
to the legacy default `127.0.0.1`. Both values support hot listener rebinding;
all authentication, framing and private-network deployment requirements remain.
This explicitly replaces the earlier loopback-only restriction.

The server has one stable `server_id`, generated and synchronously recorded once
for a new install; migration preserves the existing durable server ID. It cannot
be changed through config_update. Project and actor identifiers retain the core
1..128 ASCII letter/digit/dot/underscore/hyphen bounds and are case-sensitive.

The new root field `projects` is an array of 1..256 objects. Each has exactly:
`id` (unique immutable identifier), `name` (nonblank UTF-8, 1..256 bytes), `status`
(`active` or `archived`, default active), `description` (UTF-8, 0..4096 bytes,
default empty) and `settings` (object, default {}). Settings permit only existing
project-owned matcher, threshold_ppm, federation, history, retrieval, archive,
feedback and optimization policy fields, plus the safe eventing policy subset
defined in eventing/spec.md, validated using their owning contracts.
An absent setting inherits the server default; removing an override restores
inheritance. Root auth/users/agents/agent_owners/listener/public_url/store_path,
server resources, Kafka connection/security/enablement and credentials cannot
appear in settings.
Projects cannot be removed once admitted. Hard deletion/transfer is unsupported.
Changing name or description does not change any ID, key, cursor or retry result.

Existing root `project_id` remains a legacy default binding. Without projects,
construct exactly one project with that ID and name, migrate existing data into
it, and preserve historical aliases. With projects, project_id, when present,
MUST identify one entry and remains an immutable legacy selector; omission does
not select the first array member. New config must not redefine a historical alias
as another project. Labels need not be unique and never identify resources.

Users gain `project_ids`, an array of distinct existing project IDs, default empty
for newly created non-Admin accounts. `agents` remains the existing ID-to-secret
map and `agent_owners` retains its existing shape. New `agent_projects` is an
object mapping each agent ID to distinct existing project IDs; unknown agents
are invalid. Grants cannot exceed the owner's current admissions. Admin has
implicit admission to all projects without listing every ID. Existing legacy
users and agents migrate into the legacy project; this exception is recorded
once, never reapplied to newly created accounts. An explicit empty grant stays
empty. OIDC establishes server identity and highest server role only; it cannot
grant project admission through email equality or a role mapping.

Admin retains full access. Developer can create/manage agents only on their own
behalf, within their own admitted projects. Viewer cannot mutate. Only Admin can
change project registry/admission, role and other users' agent grants. A role
never implies non-Admin admission. Membership validation also applies to file
reload, OIDC role changes and configuration APIs; forbidden stale grants are
removed or rejected atomically, never temporarily usable.

## Request selection and disclosure

Every existing project-owned agent command accepts `project_id`. A supplied ID
MUST name an admitted project for that authenticated credential. Omission is
accepted only if exactly one effective project is available, or the request uses
an explicitly persisted legacy credential/default binding. A multi-project agent
without such a binding gets PROJECT_REQUIRED. Never infer project from a record
ID, publication source, name, contextId or first array element. The root whoami
and list_projects operations may omit selection: whoami adds `project_ids` to
its identity result; list_projects returns `{projects:[{id,name,status,
description}]}` in configured order, limited to current admission.

Unknown and inaccessible project IDs both return PROJECT_NOT_FOUND, with the
same response shape and no project existence/count disclosures. In an authorized
project a foreign resource ID is NOT_FOUND, even if valid elsewhere. Retain
FORBIDDEN for another owner's resource within the same visible project. Check
admission before counts, pagination, cache lookup or model request construction.
IDs/cursors/results MUST bind project, actor and relevant policy revision.
Mutation idempotency is (server_id,project_id,authenticated agent,messageId).
Equal message IDs in different projects are independent. Legacy responses remain
verbatim when replaying accepted legacy mutations; new results use stable IDs.

## Complete ownership matrix

| Scope | Operations/state/configuration |
| --- | --- |
| Server | users, local/OIDC login, passwords, roles/groups, sessions, CSRF, bootstrap recovery; agent tokens/owners and grant registry; listener/public URL/config location/backend root; model worker capacity; Kafka connection/security and default topic policy; peer transport credentials; minimal public health and protocol discovery. |
| Project + actor | subscribe/list_subscriptions/unsubscribe and subscription edits; poll/ack/send/private delivery; mutation retry identities; all owned history/retrieval/archive/federated jobs, cancellation, feedback attempt reads and replay jobs. |
| Project | publish/get/search, source deduplication, immutable originals/context/corrections/referents/citations/snapshots; sequences and cursors; materialized delivery work; canonical source claims/export IDs; history/retrieval/archive policy; index recipes/rows/rebuilds and effective optimizer selection; adjudication/cohorts/replay/proposals/rollback/retirement; catalog caches and coverage; effective project topic/retention/backlog policy. |
| Server-authenticated, project-pair-authorized | federation submit/status/catalog/source jobs, export checks, remote identity correlation and request/result caches. |

All existing Admin project views and commands require project selection subject
to the same rule. Admin config_get/config_validate/config_update, user/role/grant
management and server diagnostics are server-scoped; they MUST NOT accidentally
read a projected partial configuration as the authoritative full config. Viewer
and Developer status/counts include only admitted projects. Public health exposes
neither registry nor project/model/backlog metrics. Other public protocol routes
publish schemas/capabilities, never project existence or data.

A send recipient must be active and admitted to the selected project. References
in publications, context traversal, snapshots, correction chains, citations,
feedback evidence and child jobs must remain in that project. A multi-project
agent cannot use its second grant to bridge a reference or receive deliveries
from the first while polling the second. Shared model resources and code do not
share originals, queries, training cohorts or optimizer selections.

## Lifecycle, stores and recovery

Each project has a separate durable DETS store, single serialized writer and
project-bound worker namespace. The legacy project retains its original
store_path; additional project paths are derived from immutable IDs under a
private backend directory, never from untrusted display names. One running hub
owns the registry and all those stores. Store headers bind server and project;
opening a mismatching store fails closed. No two processes write one file.

Creating a project commits registry, validated empty store and generation before
success. An archived project remains readable to admitted actors, preserves all
originals and acknowledgements and permits poll/ack, cancellation and status.
It rejects new publish/send/subscribe, new queries/index/replay/proposals and
federated submit with PROJECT_ARCHIVED. Already accepted broker handoffs and
recipient deliveries drain; semantic/query/model jobs are durably paused and
resume under current authority on activation, unless their original deadline has
expired. Archive suppresses canonical advertisements and new export work; cached
claims become unavailable, never reassigned implicitly. Resume does not replay
old originals into new subscriptions or revive terminal work.

All settings and grants apply hot with expected_revision and existing durable
configuration journal. A worker snapshots project ID, membership/role, config and
lifecycle generations and rechecks them before commit/export. Revoked users or
agents cannot retrieve old results; in-flight work cannot commit under revoked
authority. Revocation never transfers ownership or erases original evidence.

Migration MUST preflight identities/schema/free writable destinations, retain a
matching config/backend backup, and write recoverable staged/completed markers.
Missing/partial config/store commits recover one complete generation or stop with
a recovery error, never start empty. Repeat migration is idempotent. Preserve
credentials, IDs, content, aliases, source retries, old idempotency results, pending
jobs, delivery/ack state and selection provenance. Mark invalidated qualification
stale. A process kill at each boundary must recover. Older binaries MUST reject
the new schema; downgrade requires restoring matching pre-upgrade backups.

Full restore includes registry, config, secrets and every project store. A project
restore must validate original server/project identity and all user/agent refs,
reject a populated destination or identity collision, and require an Admin plan;
it never silently merges records or invents missing owners. Broker recovery uses
eventing/spec.md. Per-project admission, bounded queues and round-robin eligible
worker scheduling prevent one project exhausting all shared inference/network
slots; publish/poll/ack for another project remain responsive during saturation.

## Project-qualified federation v2

Peer credentials identify one server, not a claimed project. Each peer config
adds `server_id` and `project_pairs`, an array of distinct objects
`{local_project_id,remote_project_id}`. Both IDs use the identifier bounds;
local IDs must exist. Inbound authorization is the reverse direction of that
pair; check actual authenticated server plus both IDs on every operation. Store
transport credentials only in private root configuration. Legacy peers retain
their old project_id/url/token/inbound_token shape and map only to one explicitly
bound local default/project pair. They cannot discover other local projects.

Publish /federation/v2 and advertise versions [1,2], preserving /federation and
/federation/v1 byte-compatible operations for their configured legacy binding.
Version2 requests require `protocol_version:2,op,origin_server_id,
origin_project_id,destination_project_id` plus the exact existing operation
fields; claimed server must match credential identity. Responses contain
protocol_version:2,server_id,project_id plus the existing result fields. Errors
are `{protocol_version:2,error:{code,message}}`; unsupported versions return426
with supported:[1,2]. Unknown/unauthorized pairs return403 FORBIDDEN uniformly.
No fallback from a failed v2 operation to v1 or recursive federation forwarding.

For submit/status/source jobs, durable keys bind authenticated origin server,
origin project,destination server/project,query_id. Status and cancellation cannot
cross that tuple. Deadlines/retries/canonical evidence fences retain prior bounds.
V2 catalog requests permit one destination project or the explicit `catalog`
server operation with destination_project_id omitted; the latter returns only
pair-authorized projects, each `{project_id,revision,generated_at,expires_at,
entries}`, using existing catalog paging/completion rules per project. Catalog
caches bind server/project/revision; partial, expired or unavailable catalogs are
not negative ownership evidence. Remote project IDs need not match local IDs.

The server-wide catalog response is exactly `{protocol_version:2,server_id,
revision,generated_at,max_age_ms:10000,projects,next_cursor}`. One page contains
at most one project, permitting its complete bounded catalog without exceeding
256 KiB. Each project is exactly `{project_id,revision,generated_at,expires_at,
visible,entries}`; archived projects are visible:false with empty entries. The
top revision hashes the configured-order array of `{project_id,revision}` for all
pair-authorized projects. A cursor binds authenticated server, origin project,
local server, that complete revision and next project offset. A change anywhere
returns SNAPSHOT_CHANGED; reject cursors from a different origin. Expiry remains
10 seconds, never extended by caching. No project_id singleton appears at the
top of this aggregate; ordinary destination-qualified results still require it.

Canonical external scope ownership is the exact (server_id,project_id) pair.
Duplicate current claims across local projects are conflicts like remote claims;
never select first or newest. A local canonical target uses the same authorization,
export policy and evidence snapshot via internal dispatch, without self-HTTP.
A multi-project query must explicitly freeze an array `project_ids` of 1..32
currently admitted projects; omit it for the selected project only. Results keep
separate project/owner/evidence/coverage records and never auto-publish across
projects. Recheck admission before returning asynchronous results. Email equality
only correlates identities; it never transfers roles, admission or agents.

## Contract acceptance

Independently exercise every scope row with two populated projects, one hidden
project and a multi-project agent, deliberately colliding actor-local/source/
message IDs. Test singleton legacy binding, ambiguous omission, config/file/OIDC
live revocation, archive/resume, pagination/model leakage and concurrent writes.
Kill migration/config/worker boundaries and restore matching backups. Use three
real federated processes with local and remote canonical owners, conflicting
claims, mixed v1/v2 pairs, stale caches and incremental partial coverage. Export
closed request/result/error schemas and independent valid/invalid fixtures for
all new shapes before claiming wire conformance.
