---
name: Selective project recovery
summary: Verified target-only restore with independent durable decisions and fresh allocation and transport generations
kind: component
---
# Selective project recovery

This extends multi/spec.md, configuration/spec.md, storage-relocation/spec.md,
identity/spec.md, resources/spec.md and eventing/spec.md. It owns project restore;
whole-server rollback remains separate. The accompanying interface.md and
interface.schema.json are normative future interfaces, not claims that accepted
profile2 artifacts already implement them. Preserve every unaffected operation.

## Scope and invariants

An authenticated current Admin may restore one registered project from a verified
offline backup under its original server ID/project ID, preserving verified aliases, into a
missing or logically empty target. Keep current global settings, users, roles,
credentials, OIDC, memberships, peer grants and every unrelated project unchanged.
Never import backup configuration, create missing principals, grant admission,
restore a shared Kafka volume, merge records or roll back a populated target.

Logical emptiness means no publication, private message, delivery (including
acknowledged), subscription, source or mutation receipt, semantic/query/index job,
evidence/context, feedback/label/cohort, replay, primitive/proposal/evaluation,
selection or other accepted project-owned record. Administrative store headers,
empty maps, sequence/allocation counters and metadata-only transport health are
not accepted records. Nonempty outbox, frozen subscription intents, quarantine,
replay/repair audit or old accepted query-peer cache also make a target populated.
Absence of current visible search results is never an emptiness proof.

A missing target requires explicit allow_missing:true and a verified initialized
route entry. Both authoritative snapshot and checkpoint must be absent. One
missing file invokes ordinary verified snapshot/checkpoint recovery first; an
unreadable, corrupt, mismatched or uncertain survivor is not an empty target.
Never delete unknown files or treat their corruption as permission to restore.
Plans for a registered but never initialized project first complete normal empty
creation; initialization and recovery cannot race.

## Route registry and cold startup

Before opening writers, establish one owner-only server storage-route registry
beside CONFIG_FILE, derived from its absolute location. It is server metadata,
not operator configuration and not a project store. Version1 entries bind the
full server/project IDs, append-only verified alias bindings, initialized flag, current route
generation, project epoch, allocation epoch, storage anchor and selected complete
generation digest. Paths never derive from display names. Bind the registry to
the configured server and configuration location; reject unknown schemas,
duplicate identities/aliases, colliding routes and symlink/foreign files.

Persist an independent owner-only CONFIG_FILE.stores.marker loss witness in the
same recoverable creation/adoption transaction. Registry is CONFIG_FILE.stores;
recovery operations/receipts/reservations are CONFIG_FILE.recovery; existing
configuration receipts are CONFIG_FILE.journal; the serialized tagged decision is
CONFIG_FILE.transaction. Every full backup includes the marker and complete
metadata set. Existing marker plus absent/corrupt registry without a valid owned
creation/adoption decision is global integrity failure, never fresh admission.
An absent marker plus conflicting metadata/store evidence is also not fresh.
Location binding is not silently changed at startup. The explicit offline
rebind-storage interface below supports complete stopped-server backups moved to
a different configuration location, preserving all server/project identities and
state. Selective project recovery does not perform that whole-server rebind.

Bootstrap explicitly distinguishes fresh installation, verified existing complete
stores, and known initialized missing stores. Installing the registry for an
existing store verifies its snapshot/header without a second live DETS opener.
When no old registry exists, an absent required existing store with durable config
history must not be inferred fresh. Migration needs explicit proven fresh state
or authenticated Admin initialization below; otherwise keep that target halted.
A handwritten new configuration with no admitted fresh intent can start its global
authentication/Admin/control plane while the unknown target stays uninitialized.
Its Admin recovery page must offer explicit plan/apply empty initialization, bound
to current server/project/alias identity, config revision, no accepted records and
absence of conflicting files. This is never available for a known initialized
missing target: only verified restore may recover that target. Creating the
initial built-in Admin/password file is global authentication bootstrap and does
not authorize product-store initialization. A corrupt/lost existing registry is
not an uninitialized target and cannot be bypassed by this initializer.

After registration, startup never recreates a missing initialized target empty.
Mark that target recovery_required and admit Admin recovery commands while serving
healthy other projects. Other operations on the target return retryable
RECOVERY_REQUIRED without an acceptance receipt. Registry corruption or an
unresolvable server-wide transaction fails startup closed. Public health exposes
no project registry; authenticated per-project status reports availability.

Every writer/snapshot reader, retained-agent identity guard, hot relocation,
archive/resume, worker and backup resolver MUST use this registry. No fallback to
the old ID-derived path after recovery. Relocation moves the current selected
generation, atomically updates its registry route, preserves project/allocation
epochs, and leaves old copies offline. Recovery and relocation decisions share
one serialized server transaction coordinator. Full backup includes configuration,
configuration journal, route registry, external recovery journal and all selected
project generations; historical offline copies are not current stores.

## Local legacy adoption compatibility

Ordinary first startup and continuation of a previously decided legacy upgrade may
encounter locally created schema1..3 stores from a supported producer whose normal
umask produced checkpoint/snapshot modes0640,0644,0660 or0664 instead of0600.
This is a local adoption path, never an imported backup/bundle permission exception.
The source must be owned by the running server UID, regular, singly linked and
readable, with no symlink path component. Historical permission acceptance excludes
execute/special bits and world-write permission; current schema4 stores retain the
normal private-file requirement. A schema4 generation without its matching route
registry/witness is not a legacy adoption input: recover its matching metadata
through whole-server recovery instead of inferring a fresh registry. Unknown
layouts or unsafe metadata fail closed.

Read the entire bounded local source through an opened handle, checking its exact
identity against lstat before and after reading; reject changed identities, lengths
or bytes. Preflight checkpoint structure and safe ETF before any native DETS opener;
validate snapshot framing/checksum/safe terms and project/aliases/server consistency.
A closed checkpoint-only source is supported; an unclosed checkpoint requires the
independently validated authoritative matching snapshot under ordinary interrupted
write recovery. Full native-state validation must precede adoption staging/decision.
Do not infer fresh identity from a malformed, foreign or wrong-project survivor.
Supported pre-federation schema1 and schema2 producers did not persist a server
ID. Only that well-formed historical absence permits provisional server-ID genesis: validate
its complete raw state and project/aliases under one provisional ID before any
backup/marker/decision mutation, then reuse that exact ID in the decided
configuration and adopted registry/generation. A non-null stored ID must match;
never substitute an ID for malformed identity or any schema3 or later missing header.

Do not chmod an unverified configured path or open historical files natively to
secure them. Use the verified bytes/state to create owner-private staging and active
generations through the existing durable adoption transaction, with closed checkpoint
preflight before native reads. Retain original source bytes/modes/inodes and all
existing rollback backups unchanged. Bind adoption proofs to the verified source
identities/content and exact checkpoint/snapshot absence, rechecking before decision; startup still requires exclusive
ownership of the storage set. Symlinks, hardlinks, non-owned files, malformed state,
identity conflicts and concurrent source changes reject without changing those inputs
or admitting a writer. Imported/offline bundles remain subject to strict private
ownership, mode and hardlink rules above and below; the generic private reader is
not relaxed by this local-only compatibility path.

## Backup bundle and verification

An operator places an offline bundle in recovery.backup_root/BACKUP_ID. Admin
commands accept a bounded identifier, never a filesystem path or URL. The console
explains this prerequisite and validates the selected bundle through the plan API.
Do not run an external archiver, follow symlinks, traverse parents, extract an
archive or access arbitrary absolute paths. All bundle directories/files must be
regular owned entries, private to the server owner, with no symlink components.
Refuse hardlinked payloads and paths overlapping live stores or metadata.

The exact manifest and size/hash rules are in interface.md. A bundle contains a
complete synchronized authoritative project snapshot and matching backed-up global
configuration for original identity/ownership proof. A future exporter may prepare
the bundle; an existing complete stopped-server backup can be adapted offline
without modifying or opening its checkpoint writable. Copy the verified snapshot
and exact original configuration, calculate the declared hashes, then atomically
publish the manifest. A generated manifest alone does not prove completeness:
the planner independently validates the complete underlying state schema,
snapshot checksum, server/project header, aliases and every internal reference.

The SHA256 supplied by Admin binds exact manifest bytes (including whitespace).
Manifest paths are fixed basenames. Verify each exact length and SHA256 before
decoding, then verify again against the still-open regular files during apply.
Reject duplicate JSON keys, invalid UTF8, unknown fields, trailing bytes, unsafe
term values, unknown snapshot schemas, invalid references and decompression
bombs. Current ADHDSTATE1 snapshots are uncompressed deterministic ETF, prefixed
by ASCII ADHDSTATE, byte1 and 32-byte SHA256 of the ETF body. Safe bounded decoding
rejects executable/function/PID/port/reference terms and unknown atoms; no
untrusted dynamic atom creation. Reject compressed ETF in this bundle version.

Closed native checkpoint verification must preflight untrusted bytes before any
native DETS opener. Support the modern checksummed DETS version9 ordinary hub-writer layout emitted
by the supported OTP runtimes: set/key-position1, min=m=next=256, n=0, one
permanent2048-byte directory part at1336 and segment at3384,
ordinary buddy-arena origin5432 and exactly one {:state,map} object. This is a
physical-format subset; custom-minimum, grown-key-directory, bulk/import/bchunk
layouts are unsupported and fail closed. Complete supported legacy1..3 logical
snapshot bundles remain restorable by creating a fresh ordinary checkpoint.
Bound the entire encoded file, structural walk and term scan by the frozen
byte/deadline/batch limits. Verify header hash and counts, file trailer, reachable
segment/slot/bucket pointers, disjoint live allocations, free-list structure and
nonoverlapping free allocations. Count the entire power-of-two live bucket
allocation including padding. Verify exact partition of [0,5432+2^31), with free
and live bucket alignment to the original5432 or reloaded1336 allocator bases;
reject missing free blocks, free blocks within live padding, forged arena bases,
unsupported layouts, unknown versions, cycles, overlaps, trailing structures,
compressed or unsafe ETF and unknown atoms.
Only after exact safe term decoding may a read-only repair:false native opener
run, and its single lookup must equal the preflight-decoded object. A matching
operator-supplied hash is never a substitute for this validation. A recognized
structurally valid header explicitly marked not closed may return needs-repair
without native opening. Ordinary independently verified authoritative-snapshot
reconstruction may handle that case under its forensic-preservation rules;
byte-preserving offline rebind must reject it. Malformed or unsupported closed
checkpoints fail closed, never trigger an untrusted native repair/decode path.

Retain the complete accepted state, not a search/export projection. Preserve
workflow primitives, selections and qualification provenance; revalidate their
owning compatibility identities against current code/config/epoch and mark only
invalidated qualifications stale. Recovery cannot invent a new quality pass,
model winner or optimization promotion.

Referenced users/agents include active and historical authors, recipients,
subscription/query/job owners, source/command receipt actors, evidence subjects
and all nested workflow owners, not only currently queued rows. Current configured
principals must still exist. Compare backed-up and current stable user ID and
provider binding (local username or OIDC provider_id/issuer/subject), and each
agent's original owner ID. Preserve the union of current target aliases and verified backup aliases. Existing
current alias-to-project bindings are unchanged: an alias bound to another target
is a conflict, never reassigned. An unbound verified historical backup alias may
be restored only to this target, without changing current global configuration;
never discard current aliases that appeared after the backup. A changed role,
display name, email, password, token or grant is not imported. A missing or reassigned owner, unprovable identity or alias
collision is a conflict. Disabled existing owners remain disabled; their data may
be restored without authorizing work or access. For unowned legacy agents, equal
ID/null-owner alone cannot prove continuity: require an equal original/current
credential SHA256, unless a durable original principal-incarnation record proves
continuity across rotation. Bundle version1 supplies configuration proof only;
without actual retained incarnation proof, changed unowned credentials are an
explicit unsupported/unprovable-history conflict, not a guessed identity. Future
proof formats require their own reviewed version. Compare credentials privately;
never return hashes.
Federated same-email correlation is not local ownership proof.

## Hot configuration and bounded work

Root recovery is closed and optional. Omission uses these defaults; each field is
independently hot and editable from Settings. Null deletes the optional root
object or optional field through normal merge-patch semantics; effective defaults
apply after merging. backup_root defaults to CONFIG_FILE + ".backups" and is a
private absolute directory (relative supplied paths resolve beside CONFIG_FILE).
Missing backup_root is permitted until a plan attempts to read a bundle.

| Setting | Default | Inclusive range |
| --- | --- | --- |
| max_backup_bytes | 67108864 | 65536..1073741824 |
| max_records | 100000 | 1..1000000 |
| scan_batch_records | 256 | 1..4096 |
| timeout_ms | 300000 | 1000..1800000 |
| plan_ttl_ms | 900000 | 1000..86400000 |
| max_operations | 10000 | 1..1000000 |

backup_root is 1..4096 UTF8 bytes, no NUL. Integers reject booleans/fractions.
max_backup_bytes includes all manifest/payload bytes; manifest <=65536 bytes,
configuration <=1048576 bytes. Count every top-level and nested retained record,
including receipts, against max_records. At most one recovery verification or
staging job and one additional closed-stage DETS table are active per server.
Other projects retain model/network/event lane capacity. Recovery disk scans yield
between bounded batches, use one finite-memory decoder bounded by the admitted
bytes/records and never execute inside the global configuration or live writer
mailbox. Limits and a monotonic absolute deadline freeze at acceptance; lowering
limits does not erase accepted operations or cancel a decided installation.

max_operations and capacity.operations count durable accepted external mutation-receipt
entries, not distinct operation IDs. Every newly accepted message_id consumes one
entry, including an apply request coalesced into an already decided operation;
plan, apply and explicit offline rebind consume their own entries; capacity.operations
counts both online and offline receipt maps in the shared external journal.
Internal lifecycle transitions consume no additional entries. An exact authenticated replay consumes no entry and remains
replayable at the cap; current authorization is checked before replay.
Reject new work before acceptance when max_operations durable entries or the
single active/staging slot are occupied. No unbounded pending job queue. Receipts
and decided recovery metadata are never silently pruned to satisfy a cap. Expose
counts; hot cap increases permit further admission. Planning/apply consume separate
slots only while running; a ready plan is a retained operation, not an active job.
Timeout before decision records a bounded failure and cleans owned stage; after
decision it stops ordinary target serving and completes recovery or reports blocked.

## Plan and apply transaction

Plan mode restore accepts expected_revision, backup_id, manifest_sha256 and
allow_missing. Mode initialize explicitly accepts confirm:true, has no backup
fields, and is limited to uninitialized targets as described above. Both modes
durably journal a redacted accepted operation before returning. Verification is
asynchronous. A ready plan binds exact backup file identities/hashes, config
revision, server/project/aliases, current original-owner proof digest, target
availability and complete emptiness/watermark proof, current route/project epoch,
new unique storage/allocation/transport epochs, effective target policy and expiry.
Its SHA256 is over the canonical UTF8 JSON plan specified in interface.md. A ready
plan is evidence for review, not a reservation or permission to restore later.

Apply binds plan_id, plan_sha256, expected_revision, confirm:true and message_id.
Authenticate as current Admin, then resolve durable idempotency before stale-plan,
revision, expiry or target checks. Same actor/message/command returns its original
redacted acceptance receipt across target replacement/restart; changed command is
IDEMPOTENCY_CONFLICT. Agent messages use no recovery namespace. Idempotency and
recovery jobs live outside the target store. A new message for an already decided
plan resolves to that same recovery operation; it cannot install twice.

For restore reverify all backup identities/content and current ownership/permissions;
for initialize reverify uninitialized admission and absence of conflicting files.
Stage a
complete closed checkpoint/snapshot under the proposed private generation, and
preflight the fresh Kafka topic under current service security/policy. Apply the
bounded post-create metadata readiness rule in eventing/spec.md, passing the
immutable accepted recovery deadline as an upper bound on the single monotonic
provisioning/request budget. Queue wait and readiness retry cannot reopen that
deadline;40002 cannot bypass topic validation. Require exactly-zero integer beginning/end
offsets after readiness, and fail before decision on exhausted or invalid preflight.
Never mutate
old topic retention or consume its tail. No broker success is synthesized. Before
decision, acquire the serialized coordinator and freeze only the target writer.
Previously accepted target transactions settle; later ones return
CONFIG_APPLY_IN_PROGRESS with Retry-After:1. Recheck exact config revision, aliases,
ownership, route, target epoch and all logical emptiness under that freeze. A
concurrent other-project/config transaction may finish, but revision/route drift
invalidates this undecided plan. Unrelated writers/epochs remain active.

Durably fsync one decision binding the verified stage, old/new route and epochs,
plan digest, complete target state digest, accepted apply receipt and post-install
baseline. Before decision, old target remains authoritative; failure releases only
this transaction's freeze and removes only its owned stage/new empty topic where
safe. After decision, never resume old target serving or report an ordinary abort.
Install without overwriting foreign files, fsync directories, remove staging hardlink
aliases, atomically select the new route/epochs, validate the new generation, open
one target writer, persist completion receipt and release its freeze. Old files
remain offline. No current global configuration revision/settings change.

Cold startup replays decided recovery before opening the affected writer, even
when the current project is archived or unavailable. Already activated state may
contain later accepted writes: require matching route/project/allocation epochs
and generation/sequence >= baseline; at the baseline require the exact decided
digest. Never copy the older stage over later valid writes. Missing/invalid decided
material fails closed with blocked status; healthy unrelated projects still serve
when the registry/decision itself is valid. A retry of apply for that decided plan
may resume the same operation, never choose another plan or baseline. Invalid
server-wide registry/decision integrity stops startup entirely.

## Transport, late work and identifiers

Each restored target gets a 128-bit CSPRNG project epoch distinct from every
retained/live/backup epoch on this server. New topic is exactly effective
topic_prefix + "." + first16 lowercase hexadecimal characters of
SHA256(UTF8(server_id)) + "." + first16 lowercase hexadecimal characters of
SHA256(UTF8(project_id)) + ".r" + lowercase32hex(epoch) + ".events.v1";
group is topic +
".fanout". Record full identities and epoch for collision checks. Legacy routes
retain exact old topic names. Transport changes use current connection, TLS,
credentials and effective target retention/caps. Recovery is permitted with
eventing.enabled=false; record the new epoch durably, expose transport disabled,
and use its fresh topic on later enable. Failure of required enabled preflight
prevents the decision. Never reuse an old topic/group, rewind broker state or
restore the shared Kafka volume.

Keep backed-up immutable event/publication/delivery IDs, source receipts, completed
filter decisions and acknowledged status. Rebind only backend transport metadata
to the new epoch: old broker offsets are evidence, not positions in the fresh
topic. New durable next offset starts0. Requeue accepted backed-up outbox/frozen
target work needed to finish recipient processing; do not turn completed historical
publications into fresh subscription activations or resurrect acknowledged rows.
Dedup backed-up deliveries by preserved logical identity. Quarantine referring to
old physical offsets becomes retained offline evidence, not a blocking gap in
the new topic. Restore explicitly reports transport_discontinuity:true; initialization reports
false because it has no prior accepted transport history. New and replayed
envelopes carry the preserved original identity; topic+epoch supply transport
generation and validation fences. No old topic tail may enter restored state.

Every asynchronous callback captures and rechecks project epoch immediately
before durable commit/export: model/filter/history/index/replay/optimizer,
peer/directory/source queries, identity exchange and Kafka fetch/produce/commit.
Cancel target resource tickets and close old consumer through its recorded endpoint.
An already sent network message cannot be unsent; mark old in-flight logical
query work cancelled/superseded in audit and do not silently duplicate its remote
side effects. Resume backed-up pending work only under current admission/lifecycle
and original deadlines; expired work becomes terminal. Retain its accepted IDs,
frozen filter/model/threshold/revision and ownership/dependency evidence. Model
disable/archive pauses semantic work; removed admission cancels or denies work
under the owning feature policy, never transfers it. A backed-up remote job uses
its original pinned peer/query ID and status/idempotent retry contract, never a
new identity that silently duplicates its remote side effect. Expired caches stay
expired and canonical claims require current routing/authorization reconciliation. Archived restored projects
stay archived and semantic work paused. Other projects' tickets/epochs/consumers
remain unchanged.

Preserve all backed-up IDs verbatim. Before any new project-owned allocation,
durably select a fresh CSPRNG128 allocation epoch, independent of sequence ordering
and never reused after recovery, including failed/abandoned generations. New IDs
are KIND + "_" + lowercase32hex(allocation_epoch) + "_" + lowercase base36(counter),
KIND matching [a-z][a-z0-9]{0,15}, counter a positive JSON-safe integer with no leading
zero. Allocate/increment atomically with the accepted record; reject exhaustion,
never wrap or reset within an epoch. Apply to every newly allocated standalone object identity across publications,
subscriptions, deliveries/private messages, event IDs not derived from originals,
all semantic/federated/source/index jobs, contexts/evidence/feedback/labels/cohorts,
replay, primitives/proposals/evaluations/selection generations and internal object
IDs exported in receipts. Content-addressed recipe/qualification identities and
derived feedback/attempt/cohort/cluster/evidence lineage hashes remain deterministic
when their existing contracts define identity that way. Such derivation must bind
the preserved original or namespaced parent/source identity for every distinct
logical object; hashing only reused counters or mutable text is not a substitute.
The same content-addressed object may intentionally retain its same identity; a
different lost post-backup logical object must not be recreated under that ID.
Every independently allocated identity in each family still uses the fresh
namespace: deterministic IDs are not a generic bypass of allocation fencing. Server-owned recovery operation/plan IDs use a separate persistent
server metadata allocator, never the target allocator. User/agent/project/server
identity and client message/source IDs are not rewritten. Config-generated reset
message IDs are external idempotency tokens, not newly allocated product objects;
preserve their existing retry semantics.

Existing IDs remain opaque valid IDs, not counters to parse or authorization.
Store readers accept both legacy and new allocation formats. A new-format store
header declares the allocator/route version; old binaries fail before writing it.
Public object schemas keep existing opaque-ID bounds (<=128 bytes), not a new
mandatory pattern for legacy rows. Sequence ordering remains separate and monotonic
within the restored retained history; no claim recovers lost post-backup data.

## Required independent qualification

Cover default/no-default and archived targets, missing and empty admission,
unchanged current global auth/grants and other-project newer facts/acks/jobs/
positions, secret redaction, all original ownership refs and every record family.
Reject populated, partial/corrupt, reassigned/missing owner, wrong identity/alias,
bad bounds/hash/schema, symlink/hardlink/path collision, unauthorized/stale and
expired plans without mutation. Exercise duplicate requests across restart and
after activation, plus foreign mutation-ID reuse.

Kernel-kill before/after stage, decision, install, route activation, completion
receipt and cleanup; prove one complete chosen generation and no overwrite of
later activated writes. Independently inspect complete snapshots/registry/journal,
not just API counts. Delay actual model/peer/Kafka replies across epoch change;
prove target stale work fenced and unrelated work progresses. Publish/ack/create
all allocator families after restore and prove no lost post-backup ID collision.
Use real Kafka to prove old tails excluded and only target topic changes. Qualify
the exact accepted native artifact, exact immutable image and both Compose/Kind
forms, while retaining separate full-server restore regressions.
