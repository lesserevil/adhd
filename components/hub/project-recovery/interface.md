---
name: Selective recovery interfaces
summary: Closed future Admin recovery requests, durable jobs, plans and offline bundles
kind: interface
---
# Selective recovery wire and bundle profile

interface.schema.json defines the exact JSON Schema2020-12 shapes. All objects are
closed; defaults are applied only where explicitly stated. Unknown fields,
duplicate keys, invalid UTF8, booleans as integers, unsafe integers and invalid
UTF8 byte lengths are INVALID_PARAMS. IDs are case-sensitive. Uint means integer
0..9007199254740991. Times are UTC RFC3339 with Z, not client authority. SHA256 is
lowercase64hex; epochs are lowercase32hex. UTF8 byte limits apply in addition to
JSON Schema string lengths. The existing bearer/session+CSRF/origin protections
and generic secret-free errors govern POST /admin/api. No new public/A2A route.

These are future additive Admin operations. Do not alter published actual2.0
schemas or claim support until a reviewed successor artifact serves and passes
these interfaces. Future combined schemas/OpenAPI incorporate all definitions,
closed result/error unions, root recovery settings and these operation scopes.

## Requests, receipts and access

| Operation | Required fields after op | Optional fields | Scope |
| --- | --- | --- | --- |
| project_restore_plan | project_id,expected_revision,message_id; restore mode:backup_id,manifest_sha256; initialize mode:mode=initialize,confirm:true | mode (default restore),allow_missing (restore only,default false) | Admin; canonical registered target, including unavailable/archived |
| project_restore_apply | project_id,plan_id,plan_sha256,expected_revision,confirm:true,message_id | none | Admin; same target as plan |
| project_restore_status | project_id | operation_id | Admin; no mutation ID |

Plan/apply responses are HTTP200 accepted receipts with exactly accepted:true,
operation_id,kind (plan/apply),project_id. They acknowledge a durable external
operation, not completed verification or restored data. The job may fail later;
clients poll status. Per-Admin stable user ID (or legacy server Admin principal)
plus message_id forms the external idempotency key. Hash the canonical complete
command excluding message_id; include project_id and explicit mode/defaults so absent mode and restore, and
absent allow_missing and false in restore mode, are equivalent. Persist that hash and original receipt,
never configuration values/credentials. Authorize current Admin before replaying
any receipt. Same-message changed command is409 IDEMPOTENCY_CONFLICT. A successful
receipt remains replayable after expiry, failure, target replacement or restart.

Status returns exactly project_id,availability,route,capacity,settings,operation.
settings contains every effective recovery setting, including resolved backup_root,
and is Admin-only; this is the sole response permitting that configured root path.
availability is ready,uninitialized,recovery_required or restoring; it describes local target
availability, independent of project active/archived. route reports only generation,
project_epoch,allocation_epoch and topic (nullable for disabled transport/legacy
epoch as defined by schema), never paths or credentials. capacity has operations,
max_operations,active (0/1). With operation_id, return that target's operation or
404 NOT_FOUND; a foreign-project operation is also404. Without it return latest
retained operation, or null. Neither form mutates the job or consumes deliveries.

The Operation union has exact fields operation_id,kind,project_id,state,created_at,
updated_at,progress,plan,result,failure. Plan states: queued,verifying,ready,stale,
failed,expired. Apply states: queued,staging,decided,installing,activating,complete,
blocked,failed. Progress reports unique bundle bytes verified as bytes_read, unique retained
records_checked and the frozen dataset maximums (not total repeated physical IO);
Counts may not exceed maximums. A queued/verifying/failed plan exposes null
(no reviewed Plan exists); ready/stale/expired exposes the immutable reviewed Plan.
Apply always exposes its reviewed Plan. Plan result is always null; apply result is nonnull only in complete. failure is nonnull only
in failed/blocked. blocked means a durable decision exists and completion needs
recovery; failed means no decision exists and no target switch occurred. A blocked
operation may move through installing/activating to complete; never to failed.

Retry apply with the same reviewed plan and a new message_id can resume an already
decided blocked operation, returning its same operation_id. It is not a second
decision and does not recheck target emptiness against restored accepted data.
Completed plans also resolve to the same operation. Undecided failed apply requires
a new plan; an old plan cannot be used to silently bypass failed verification.
All such resumed work still requires current Admin authorization and valid owned
decision integrity. Persist every transition/failure for bounded redacted audit.

## Plan identity and failure semantics

Plan.plan_id equals its creating plan operation_id. Plan contains mode,plan_id,server_id,project_id,aliases,backup_id,manifest_sha256,
config_revision,created_at,expires_at,target,backup,references,selected,policy and
plan_sha256. Its hash is SHA256 of [RFC8785 JCS](https://www.rfc-editor.org/rfc/rfc8785.html)
UTF8 serialization of that object **without plan_sha256**. It is a digest, not a
signature or authorization. aliases are sorted distinct original historical
aliases, excluding canonical project_id. references.proof_sha256 binds a private
canonical map of every original/current principal linkage and provenance match;
only its digest and counts leave the server. No token/password/OIDC secret/hash
is part of returned Plan. target.state_sha256 is null only for an admitted missing or uninitialized
target; the corresponding sequence/storage generation are the registry's last
verified values. Empty target has exact digest and current watermark.

Selected route_generation must be greater than target.route_generation. Fresh
project_epoch/allocation_epoch are reserved durably before a ready plan; abandoned
or expired reservations are never reused. Selected topic is null only when transport
is disabled, but the project epoch is still reserved. policy reports six effective
target eventing fields: topic_prefix and retention/backlog/filter-cap integers,
no service/security fields.
Initialize plans have null backup_id,manifest_sha256 and backup; references
report only current identity proofs, never fabricated backup evidence. Their
target availability is uninitialized and watermark is zero with null digest.
A known initialized target cannot receive an initialize plan. The accepted Apply
receipt has the same shape for both modes; status always shows its reviewed mode.
After restore/initialization, the complete result reports initialized (true only
for empty initialization), route/epochs/topic/discontinuity and
counts, sequence and storage generation. It contains no backup filenames or raw
snapshot/configuration values. Counts are observations, not an alternative to
restoring every record family in spec.md.

Before acceptance, exact error envelope is {error:{code,message}}, plus
current_revision only for CONFIG_CONFLICT. Messages are fixed generic text, never
raw exception/URL/path/owner inputs. HTTP400 INVALID_PARAMS;401 UNAUTHORIZED;
403 FORBIDDEN;404 PROJECT_NOT_FOUND/NOT_FOUND;409 CONFIG_CONFLICT,
IDEMPOTENCY_CONFLICT,RESTORE_STALE_PLAN,RESTORE_CONFLICT,BACKPRESSURE;
503 RESTORE_BUSY,RECOVERY_REQUIRED,CONFIG_APPLY_IN_PROGRESS (Retry-After:1).
An unknown/unauthorized project uses existing non-disclosing project behavior.
No acceptance or idempotency success is written for these rejections.

Asynchronous Failure is exactly code,reason,retryable,conflicts,truncated. code is
RESTORE_INVALID_BACKUP,RESTORE_CONFLICT,RESTORE_STALE_PLAN,RESTORE_TIMEOUT,
RESTORE_IO_ERROR,RESTORE_UNAVAILABLE or RECOVERY_REQUIRED. reason is the schema's
closed enum. conflicts is <=16 aggregated {reason,count} rows, unique reason,
sorted by reason; truncated is true iff further conflict categories were
omitted. These are never private principal identifiers, stored text, filenames, credentials or raw
remote errors. An invalid hash/schema, missing/reassigned owner or populated target
is not transient. IO/transport unavailability can be transient before decision;
after decision only blocked/RECOVERY_REQUIRED is allowed. A ready plan is effectively expired when its deadline passes; otherwise it is
stale when current config/route/identity/target proof differs. Expiry has precedence
when both conditions hold. Status may derive this eligibility state without
mutating storage; background reconciliation persists it, and Apply independently
rechecks it. Stale/expired never become ready again; retain the immutable reviewed
Plan and require a new plan. A successful duplicate receipt is still replayable.

## Offline bundle version1

The manifest is recovery.backup_root/BACKUP_ID/manifest.json, where BACKUP_ID is
1..128 ASCII identifier characters (letters/digits/dot/underscore/hyphen), excluding
"." and "..". It is <=65536 bytes. Its exact schema is BackupManifest: schema=
adhd/project-backup@1; server_id,project_id,aliases,captured_at; source containing
route_generation,project_epoch,allocation_epoch,storage_generation,sequence;
snapshot descriptor for exactly project.snapshot; configuration descriptor for
exactly server-config.json; principal_proof exactly {kind:configuration-v1}.
Each descriptor has name,bytes,sha256. No URLs, alternative paths or undeclared
files are opened. File metadata/ownership and no-link rules remain mandatory.

project.snapshot is a complete closed authoritative ADHDSTATE1 snapshot, not a
DETS file opened in a second process. server-config.json is the exact private
backed-up root config needed to prove original server/project/aliases/principals.
It can contain secrets and therefore is never returned, stored in the target,
copied to current configuration or logged. The manifest records complete source
generations and canonical identity; planner verifies they equal snapshot/config
contents, or the actual verified legacy schema's derivable identity. A null legacy
epoch is valid only where that old schema genuinely had no epoch. No invented
incarnation or retroactive ownership proof. The configuration-v1 proof allows
owned-agent credential rotation while stable original owner/provider binding
matches; unowned legacy continuity follows spec.md's explicit stricter boundary.

The selected backup must preserve every old alias; current aliases may have grown
since backup but cannot have moved to another project. Retain the union on restore,
without reassigning any existing current binding or erasing current aliases.
An unbound verified old alias may be restored only to this same target; current
global configuration remains unchanged.
Plan aliases report that verified union and its digest participates in the plan.

## Console and wire example

Admin project recovery view includes effective hot limits/backup root, target
availability, backup-ID and manifest-digest inputs, explicit missing-store consent,
asynchronous progress/failures, reviewed plan identity/owner counts/backup watermark,
and an explicit Apply action binding that exact digest/revision. Disable Apply until
ready, recheck server-side regardless of UI, and show discontinuity/data-loss scope.
Use existing browser identity/project epochs to discard late status responses.
Do not expose recovery controls to Developer/Viewer or agent tokens. This UI is
required for both healthy empty and unavailable missing targets.

```json
{"op":"project_restore_plan","project_id":"red","backup_id":"offline-20261021","manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","expected_revision":12,"allow_missing":true,"message_id":"review-red-1"}
```

```json
{"accepted":true,"operation_id":"restoreplan_abcd","kind":"plan","project_id":"red"}
```

```json
{"op":"project_restore_status","project_id":"red","operation_id":"restoreplan_abcd"}
```

After status exposes a ready Plan, apply with its actual returned digest and ID:

```json
{"op":"project_restore_apply","project_id":"red","plan_id":"restoreplan_abcd","plan_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","expected_revision":12,"confirm":true,"message_id":"apply-red-1"}
```

```json
{"accepted":true,"operation_id":"restore_abcd","kind":"apply","project_id":"red"}
```

The example digests/IDs are illustrative, not valid proof for a real bundle.

Explicit unknown-target initialization is also reviewed/applied through Admin:

```json
{"op":"project_restore_plan","mode":"initialize","project_id":"red","expected_revision":12,"confirm":true,"message_id":"review-empty-red-1"}
```

This command cannot admit a known initialized missing target, populated files or
uncertain/corrupt existing registry. It imports no backup and grants no access.

## Application version and snapshot identities

The successor application/OpenAPI profile is2.1.0; combined schema $id is
urn:adhd:protocol:2.1. Descriptor protocol major2/admin envelope1, A2A1.0 and peer
versions1/2 are unchanged. Discover this additive capability through the served
schema/OpenAPI; no new descriptor field is required. Keep existing healthy
operation/result envelopes unchanged. New status owns availability/route fields;
do not append them to closed old list/project/delivery objects. Root recovery is
optional and is not injected into old config_get responses merely because effective
defaults exist. New status/UI exposes those effective defaults. Strict profile2.0
validators are not promised to accept2.1 commands/errors. Publish refreshed2.1
schemas/examples/conformance only with the reviewed implementing artifact.

Backup manifest schema is exactly adhd/project-backup@1. Route registry version is
exactly1. External recovery journal version is exactly1. Snapshot framing remains
ADHDSTATE byte1 with SHA256 and uncompressed deterministic ETF. Supported input
state schemas are1,2,3 and the new4 only, with their complete native validators.
Unknown schema is rejected, never guessed. New live state has schema:4 plus
route_generation (positive safe integer), project_epoch (lowercase32hex),
allocation_epoch (lowercase32hex), allocation_counter (Uint, initially0). The
selected route and matching complete checkpoint/snapshot must agree on these
fields before activation. Preserve every other old state/row/receipt identity.
Legacy snapshots genuinely lacking these fields have null epochs and source
route_generation0 in their offline manifest; planner verifies that absence.
Schema4 backups require nonnull epochs, matching positive route_generation and
counter. Old binaries rejecting schema4 must fail before product writes.

Adoption of a complete old store establishes schema4/header and current route in
a recoverable server-metadata migration before writer activation. This does not
change its Kafka topic spelling or replay history. Retain the pre-migration complete
backup and durable decision; a kill must complete the compatible selected pair or
halt. Empty initialization instead records explicit fresh admission before opening
its new writer. Do not fabricate either admission from absent files.

New preacceptance recovery error messages are fixed: RESTORE_STALE_PLAN =
"Recovery plan is stale"; RESTORE_CONFLICT = "Project recovery conflict";
RESTORE_BUSY = "Project recovery is busy"; RECOVERY_REQUIRED = "Project recovery
is required". Existing codes retain their accepted messages.

Independent contract vectors are `tests/fixtures/project-recovery.json`, checked
by `tests/project_recovery_contract.py`; these qualify future schema shape and
semantic bindings only, not a running implementation or authorization behavior.
