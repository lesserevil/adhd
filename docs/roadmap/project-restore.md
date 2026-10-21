# Selective project recovery

- **Status:** active
- **Owning queue item:** [MULTI-007](active-work.md#multi-007-bound-shared-resources-and-operate-project-lifecycles)
- **Completion / archival evidence:** pending; design only, no implemented selective restore

## Required outcome

Restore one missing or logically empty project from a verified backup under its
original server/project identity. Keep current global configuration, users, roles,
credentials, OIDC settings and every other project's current data. Do not restore
the shared Kafka volume. Existing full-server recovery remains a separate operation.
The current contract in `components/hub/multi/spec.md` requires an Admin plan,
reference validation and rejection of populated destinations or identity collisions.
The implementation must satisfy that capability before MULTI-007 closes.

Logical emptiness includes publications, private deliveries and acknowledgements,
subscriptions, jobs/queries, source receipts, mutation receipts and retained evidence.
A fresh physical directory does not make an existing populated project eligible.
Populated-project rollback and record merging are outside this operation.

## Execution order and ownership

1. Author the recovery contract and exact Admin plan/apply/status schemas, errors,
   bounds and wire examples. Extend the storage, configuration, eventing, identity,
   resource and management contracts together. Review the recovery state machine
   independently before generating a successor to frozen source34.
2. Add one server-owned storage-route and project-epoch registry beside the
   configuration file. All writer startup, snapshots, retired-agent checks, hot
   relocation and full backup must resolve the same registry. Legacy path mappings
   remain unchanged until a recovery selects a new target generation.
3. Implement bounded backup verification and Admin planning. Backups must bind a
   manifest, original server/project/alias identity, complete target snapshot and
   sufficient current user/agent ownership proof. Missing ownership proof, reassigned
   identities and missing referenced principals fail closed. Reading backup
   configuration never imports its secrets, roles or access grants.
4. Implement a target-only durable recovery transaction and startup recovery before
   opening writers. Reuse verified snapshot/staging, writer freeze and fsync/rename
   primitives; do not reuse relocation's complete saved-configuration replacement.
5. Integrate target-only Kafka generation, worker fencing and identifier allocation.
   Then provide Admin review/apply/status controls and operator recovery guidance.
6. Run native fault/privacy/identity tests, followed by exact-image and Compose/Kind
   selective-recovery tests. Retain full-server recovery as its own regression lane.

The owning generated modules include Config, Projects, Store, Storage, Eventing,
Resources, every asynchronous worker, CLI startup, Admin protocol and Web. New
storage-registry and recovery modules may factor the shared transaction. Generated
application changes remain derived from reviewed Component authority.

## Plan and transaction requirements

The Admin plan binds the verified backup content identities, current configuration
revision, original server/project identity, aliases, owner/reference mapping,
target emptiness or explicit missing-store admission, and proposed storage and
transport generations. Return a bounded redacted conflict report. Apply binds the
exact plan identity and a mutation ID; its durable receipt lives outside the target
store being restored. Recheck permissions, references and emptiness while holding
the target writer freeze and serialized decision ownership.

Persist initialized route metadata so a known missing project store cannot silently
become an empty new project. Provide an explicit Admin recovery path for a halted
missing target. Other projects may continue serving; the unavailable target must
return an explicit recovery state. Legacy bootstrap/migration needs separate cases
for fresh installations, existing complete stores and missing stores.

Stage a closed checkpoint and verified snapshot in a new owned target generation.
Before the durable decision, failure removes only owned staging and releases the
target freeze. After the fsynced decision, complete installation, route/epoch
selection, writer activation and the external recovery receipt, or fail closed.
Recovery may not overwrite an already activated target with later accepted writes.
Keep old target files offline for explicit operator recovery. Other project route
entries and all current global configuration remain unchanged.

## Kafka, identifiers and late work

Preflight a fresh target-only topic/group generation. Never rewind an existing
consumer group or shared Kafka volume, and never replay post-backup records from
an old topic into the restored state. Preserve backed-up event IDs, recipient and
filter decisions, delivery IDs and acknowledgements. Requeue only backed-up work
that still requires processing, with an explicit transport discontinuity.

Every asynchronous commit/export checks the target recovery epoch, including
inference, index/replay/optimizer work, directory/federation/source jobs and broker
consumption. Close the old consumer through its recorded endpoint. Unrelated
project epochs, tickets and consumers remain valid.

Preserve all backed-up identifiers. New identifiers after restore need a fresh
durable allocation namespace so lost post-backup IDs cannot be reused under the
same server identity. Apply this to every allocator, including query, delivery,
feedback, replay and optimizer IDs; retain sequence ordering separately. Specify
the opaque-ID format and validate old/new snapshot compatibility before changing
allocators. Restoring a backup does not claim to recover missing post-backup data.

## Required evidence

- Restore an empty and an explicitly missing target from a hash-bound backup while
  another project retains newer originals, acknowledgements, jobs, receipts and
  broker positions; current global users, roles, credentials and OIDC stay current.
- Reject populated logical targets, wrong identities/aliases, reassigned or missing
  owners, stale plans, bad hashes/schema, path/symlink collisions and unauthorized
  roles without mutation. Verify plan/apply retry identity and secret redaction.
- Prove old topic tails cannot reinject post-backup data, new target IDs cannot
  collide with lost post-backup IDs, and only the target's Kafka generation changes.
- Kill before/after stage, decision, install, route activation, receipt and cleanup.
  Reopening must choose one complete generation or fail closed, preserving newer
  activated writes and every unrelated project's state.
- Fence deliberately late target model/peer/consumer replies while unrelated
  project work completes. Cover default/no-default and archived targets.
- Exercise the exact accepted image and both supported container deployment forms.
  Whole-server cold restores do not satisfy these selective-recovery assertions.
