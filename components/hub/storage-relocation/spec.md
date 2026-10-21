---
name: Hot project store relocation
summary: One durable decision moves every project writer and recovers partial installations
kind: component
---
# Hot backend relocation

This extends configuration/spec.md and multi/spec.md. A root store_path edit
moves every existing project store, including archived projects and installations
without a legacy project_id. The root path is only an anchor in the latter case;
there is no implicit default store. Additional project paths retain their stable
ID-derived mapping. The change does not restart a healthy hub.

Validate the complete configuration, registry transition, new listener and Kafka
transition before deciding. Refuse occupied destinations, symlink final targets,
colliding checkpoint/snapshot paths and an absent or unwritable root parent.
Do not overwrite or delete any foreign destination, including on failed preflight.
Creating the private project child directory is permitted. Registry additions
must not start new empty writers under a proposed configuration before commit.

Freeze every existing project writer before copying any project. Transactions
already accepted by a writer finish their normal synchronous persistence before
it freezes; later transactions return retryable CONFIG_APPLY_IN_PROGRESS rather
than accepting writes against a moving backend. Freeze tickets belong only to
this configuration transaction. A predecision failure releases all its tickets,
keeps the old live configuration, and removes only its own staging files.

For Admin/ordinary HTTP operations, CONFIG_APPLY_IN_PROGRESS is HTTP503 with
Retry-After:1. For a valid A2A JSON-RPC request it is the existing HTTP200 JSON-RPC
-32000 service error with google.rpc.ErrorInfo metadata.code set to
CONFIG_APPLY_IN_PROGRESS. This code is retryable; the caller retries the identical
command and message ID after bounded backoff. It is never an acceptance receipt
and consumes no mutation idempotency entry. Errors after the durable decision may
close the connection instead; the uncertain outcome follows the same message-ID
recovery rule.

Each frozen writer stages a closed complete checkpoint and digest-protected
snapshot. Preserve server/project identities, aliases, sequences, originals,
source retries, command idempotency/results, delivery and acknowledgement state,
broker offsets/outbox/quarantine, model jobs, query/index/replay/optimizer state
and storage generation. Bind each staged copy to its source and destination,
project/server IDs, baseline sequence/generation and state digest. No staged
file is a live writer. Staging must remain bounded to one additional open DETS
table at a time, rather than doubling the project table budget.

Record the complete validated configuration, configuration idempotency journal,
all store moves and pending policy transitions in one owner-only fsynced durable
transaction decision beside CONFIG_FILE. Before this decision, old state remains
authoritative. Afterwards, every store and configuration effect must complete
or the process must fail closed; never resume the old configuration against a
partially installed generation. A client whose connection dies at this boundary
must treat its outcome as uncertain and recover/retry its original message ID.

Install the authoritative snapshot and checkpoint without replacing an existing
file, synchronizing directory changes. Remove staging aliases before opening the
new live writer so that an allegedly immutable staging copy cannot share the
mutable checkpoint inode. Validate the installed state before activation. Switch
all frozen existing writers, publish the new configuration, start newly admitted
project writers, and release freeze tickets only after all existing destinations
are valid. Old source stores remain offline recovery copies and are never
implicitly reopened, merged, or deleted. Full backups must name the current
configuration plus all current project stores, not these older copies.

Before publishing configuration or opening any project at cold startup, replay
every decided installation idempotently. A partially installed copy must either
complete from its owned stage or fail closed; missing project files must not
silently initialize empty state. An already installed target may have newer
accepted writes if a kill occurred after activation but before decision cleanup.
Accept it only with matching project/server identity and a valid generation and
sequence at least the decided baseline; at that baseline its digest must match
exactly. Never overwrite it with older staged state. Existing checkpoint/snapshot
compatibility validation remains required. Undecided orphan staging files are
offline remnants, not authority to advance configuration or recover over a live
store.

The supported deployment requires exactly one hub process owning a configuration
and its complete backend volume. Compose runs one instance and Kubernetes uses
one replica with Recreate and exclusive persistent storage. Operators must stop
the old owner before moving a volume to another process. Per-VM process names,
writer serialization and freeze tickets do not enforce cross-process exclusion.
Concurrent independent processes opening the same configuration/volume are
unsupported; no claim of a distributed lock or multi-writer recovery is made.
An inability to establish the supported single-owner deployment is a deployment
error, not permission to run concurrent recovery.
