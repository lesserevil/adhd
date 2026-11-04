# Broadway and CubDB queue prototype

- **Status:** historical
- **Owning queue item:** none; BEAM-001 was removed by operator direction on 2026-11-04. See the [roadmap decision](../../roadmap/active-work.md#authorized-implementation-batches).
- **Completion / archival evidence:** batching/compaction manifest (`verification/beam-queue-batching/manifest.json`), following the initial prototype (`verification/beam-queue-prototype/manifest.json`); retained historical evidence, not an open investigation; [operator retirement decision](../../roadmap/active-work.md#authorized-implementation-batches).

Current adoption status: BEAM-002 is completed (`docs/roadmap/beam-production.md`). The local
installation uses qualified embedded eventing. This document retains the
investigation/prototype scope and historical results. The operator removed
BEAM-001 on 2026-11-04; these notes impose no further comparison or research work.

## Authorized scope

The user selected an isolated Broadway/CubDB prototype. This developer experiment
does not replace the installed Kafka deployment or alter the hub's portable
Component, A2A protocol, authentication, recovery format or model integration.
Its authored tooling lives in `tools/beam_queue`; it is not generated production
Component source. Native Mix owns this tool's build/test lifecycle. Dependencies,
compiler output, private package-manager state and test data live under an
exclusive private `_build/beam_queue01` (initial) or `_build/beam_queue02`
(follow-up) directory. Exact native dependency locks are
retained. No global Hex/Rebar installation or shared cache mutation is allowed.

The experiment uses the available Linux Elixir/OTP toolchain, Broadway 1.3.0 and
CubDB 2.0.2. The user's prototype request authorizes its isolated acquisition,
compilation and execution. No public listener or production store is required.

## Queue contract

- One CubDB owner per private database directory; `auto_file_sync: true`.
- Events belong to a project and epoch, with a stable logical ID and a strictly
  increasing project sequence. A duplicate with identical immutable content returns
  its previous result; conflicting reuse fails without modification.
- Enqueue commits the event, dedup receipt, sequence and pending counters in one
  transaction. Count/byte exhaustion rejects new work before committing; an already
  accepted identity still succeeds while capacity is exhausted.
- Claim only the earliest unsettled event of a project. An unexpired lease or
  blocked event prevents later events in that project from overtaking it; other
  projects continue. Lease tokens and project epochs fence stale callbacks.
- Actual Broadway processors perform fanout. All recipient records and processing
  progress commit atomically before Broadway acknowledges processing. Agent
  acknowledgements are separate and survive restart.
- Crash after materialization and before processing acknowledgement may replay
  processing but must not duplicate logical recipient deliveries.
- Retry leaves the same event at the head. Poison/retry exhaustion blocks the
  project with an explicit repair operation; there is no automatic skipped gap.
- Explicit epoch replacement fences old workers. This tests fencing, not the
  production selective-restore or migration protocol.
- Transport cleanup cannot erase unacknowledged deliveries or dedup receipts.

## Existing durable source boundary

A small synchronized DETS outbox fixture models the existing acceptance boundary;
it does not open or implement the production ADHD store format. A lost enqueue
reply must be replayable with the same identity without duplication. There is no
transaction across DETS and CubDB, and no claim that this experiment supplies a
production migration or full application integration.

## Required evidence

1. Exercise actual Broadway and CubDB, including ordered multi-project fanout,
   independent recipients, retry, lease expiry, stale tokens/epochs, blocked-gap
   repair, byte/count admission, idempotency and separate agent acknowledgements.
2. Kill private BEAM processes at explicit barriers before enqueue commit, after
   durable enqueue, during fanout transaction, and after fanout commit but before
   Broadway acknowledgement. Reopen unchanged disk data in another VM and check
   atomicity, sequence progression and exactly one logical delivery per recipient.
   SIGKILL/VM restart evidence does not establish power-loss durability.
3. Preserve a synchronized DETS original/outbox through lost queue replies and
   restart. Verify subsequent handoff and materialization without duplicate effects.
4. Run a bounded smoke benchmark, reporting actual workload, fsync setting,
   elapsed time, latency and memory/disk observations. It is not a Kafka comparison
   or qualification at the production maximum backlog.
5. Retain exact dependency/tool/source identities, actual exit statuses, fault
   barriers and cleanup observations. Check the installed hub remains healthy.

## Limits of the result

No A2A/SDK, OIDC, federation, Admin UI, semantic-model, multi-node HA, production
backup/migration or public deployment qualification is implied. A successful
prototype permits a subsequent implementation design, not automatic adoption.

The [Rheo source review](beam-eventing.md) remains useful background. Its Mnesia
experiment is deferred while the CubDB investigation proceeds.

## Initial result and reproduction

The authored tool (`tools/beam_queue/run.py`) uses a custom GenStage producer
with a real Broadway pipeline. CubDB transactions own event receipts, counters,
leases, recipient references and contiguous processing checkpoints. The DETS
fixture retains originals independently. Run from the repository root:

```sh
python3 tools/beam_queue/run.py --work _build/beam_queue02
```

This Linux-host runner expects the existing Elixir/OTP toolchain under
`_build/federation/native`, Python 3, Docker inspection access and the installed
hub's loopback health endpoint. Network access is needed for private Hex package
acquisition. Run one instance per work directory. Each run creates a new evidence
and data subdirectory, preserves earlier results, and does not change the
installed services. It verifies their container IDs, image IDs, start times,
restart counts and health before and after. Its own child process groups are
killed/reaped and checked for absence; test databases and logs remain as evidence.

On Linux x86_64, Elixir 1.18.4/OTP 27, the initial fourteen ExUnit tests passed. Five separate
SIGKILL scenarios passed, each with recovery in another VM and a second cold reopen:
before enqueue commit, after enqueue commit, inside fanout, after fanout commit
before Broadway ACK, and the synchronized DETS lost-reply handoff. Tests also
cover retry exhaustion/repair, stale epoch/token fencing, independent project
progress, slow-handler lease renewal, byte/count rejection, immutable recipient
snapshots, and agent acknowledgements retained through replay and pruning.

The final smoke run preloads 1,000 events (four projects, two recipients each,
256-byte payloads) before starting Broadway. With two BEAM schedulers, per-write
sync enabled and automatic compaction disabled, enqueue takes 10.65 seconds and
drain 35.28 seconds: 21.77 events/s over the full 45.93-second interval. Backlog
enqueue-to-handler latency is p50 23.15 s, p95 34.17 s, p99 35.18 s; these include
preloading and queue residence and are not steady-state agent delivery latency.
The three BEAM-memory observations are about 45.3–46.3 MiB; the database ends at
22.34 MiB. These are observations, not peak RSS, a memory cap, compacted size or
production performance qualification. No Kafka comparison was run.

The initial result supported continuing the design, not replacing Kafka. At that point, each enqueue,
claim, materialization and settlement currently makes its own synced transaction;
transactional batching and compaction/retention measurement were the next work.
Polling enumerates the project list; delivery inspection scans the database.
Pending quotas count payload bytes/events, not total disk or retained delivery
metadata. Dedup receipts, retired epochs and delivery records have no lifecycle
quota here. The follow-up below adds explicit compaction. Disk-full handling, publisher quotas, stuck-processor
timeouts, hot settings, backup/restore and production integration remain open.
Missing-head repair fails closed; this tool does not reconstruct corrupt data.

The manifest (`verification/beam-queue-prototype/manifest.json`) retains exact
source/dependency identities, exit statuses, crash barriers, output hashes,
benchmark observations and unchanged installed-service evidence. The preliminary
run is retained privately as exploratory evidence; the final rerun binds unchanged
sources throughout execution. Documentation review covers this contract, the
tool README, active-work/Rheo summaries, project guide and changelog. Current hub
guides, `README.md`, `PROJECT.md`, skills, CLI/UI and production contracts continue
to describe Kafka; this experiment adds no production configuration or protocol.
The completion review (`verification/beam-queue-prototype/review.json`) records
documentation findings and corrections, retained peer work, and normal `litai verify`:
three gates pass, with the configured source-intelligence and HTML checks skipped.

## Authorized batching and compaction follow-up

Extend the same authored tool, preserving the initial evidence. Batch enqueue is
bounded and atomic: any conflicting identity, sequence error or capacity failure
rolls back the entire call. Batch count is capped at 64 and aggregate payload at
1 MiB. Claim, renewal, fanout and settlement can share one synced transaction
across independent projects; each project still has at most one unsettled leased
head. Invalid or stale work must not prevent valid work for other projects from
committing. Actual Broadway batchers flush on a bounded size or timeout, including
low-volume streams. The producer coalesces demand/acknowledgement notifications for
1 ms before claiming work, so individual processor messages can share a write.
Agent acknowledgements remain separate.

Queue transactions run in a dedicated owner per database. This prevents a stopped
or killed Broadway caller from abandoning CubDB's write lock. A lost caller reply
can still mean the transaction committed; retrying the same identity resolves
that ambiguity. The owner is linked to its database, so an unexpected owner
failure also takes down that database rather than leaving it serving reads with
a dead writer. Restart orchestration and bounded ingress mailboxes remain future
production work. Dependency source is unchanged.

Expose explicit online CubDB compaction, preserving all live keys, dedup receipts,
unacknowledged deliveries and pending leases. Pruning remains explicit and only
removes settled transport rows; compaction is not a retention policy. Exercise
concurrent writes, snapshot readers, restart after compaction, and whole-VM kill
during an observed in-progress compaction. Never patch dependency source to create
the fault. Record physical bytes before/after cleanup and temporary headroom.

Add batch atomicity/fencing/fairness tests and real multi-item crash barriers.
Compare batch sizes 1 and 32 under the same 1,000-event/four-project workload,
fsync setting and two-scheduler runtime. Keep the production hub healthy and retain
source identities, actual exits, cleanup, measured throughput and limitations in
a new evidence directory. Power-loss, disk-full and production adoption remain
outside this bounded follow-up.


## Batching and compaction result

The follow-up manifest (`verification/beam-queue-batching/manifest.json`) binds
unchanged final source, locked dependencies and actual exits. All 21 tests pass.
All eleven whole-VM kill scenarios pass, each followed by two cold reopens: the
original five, four multi-item batch boundaries, interruption after compaction
copy but before promotion, and interruption after promotion/old-file cleanup.
The in-progress compaction barrier holds an owned writer transaction so the real
compactor must wait to promote its copied file; dependency code is unmodified.

The test suite also proves atomic whole-batch admission, isolation of stale
callbacks from valid peer work, rollback after a later project's fanout fails,
low-volume timeout flushing, online compaction catching a concurrent write,
old snapshot visibility and delayed file deletion, and completion/idempotent retry
after killing a transaction caller.

One paired smoke run uses the same 1,000 events, four projects, two recipients per
event, 256-byte payloads, two schedulers and synchronized writes in both modes:

| Observation | Batch limit 1 | Batch limit 32 |
| --- | ---: | ---: |
| Enqueue | 11.26 s | 1.36 s |
| Drain | 36.61 s | 13.41 s |
| Overall throughput | 20.89 events/s | 67.71 events/s |
| Actual processing batches | 1,000 × 1 event | 250 × 4 events |
| Backlog enqueue-to-handler p50 / p95 / p99 | 23.12 / 35.15 / 36.37 s | 7.67 / 12.90 / 13.36 s |
| Observed BEAM memory range | 45.69–47.26 MiB | 45.78–47.47 MiB |
| Physical bytes after pruning, before compaction | 24,577,047 | 22,536,215 |
| Physical bytes after compaction/cleanup | 517,140 | 517,140 |
| Observed bytes with old and new files coexisting | 25,094,187 | 23,053,355 |
| Compaction through cleanup | 0.20 s | 0.48 s |

This is a measured **3.24× throughput improvement** and **97.7% reduction** from
pruned-but-uncompacted file size in the batched run. Every live key compares equal
after compaction and cold restart. Pruning removes only settled transport rows;
all 2,000 recipient records and dedup receipts remain. Memory is sampled BEAM
memory, not peak RSS; coexistence is an observed file-size sum, not a guaranteed
headroom limit. Latency includes preload/backlog residence. This is one paired
measurement on a shared host, with no Kafka comparison or production load claim.

An intermediate rerun timed out during recovery. A controlled reproduction then
showed that CubDB 2.0.2 retains its write lock when a direct transaction caller is
killed. Queue transactions now belong to the dedicated writer, whose lifetime is
independent of Broadway workers. The killed-caller regression proves that its
transaction finishes and another caller can retry or write afterward. The
earlier failure (`verification/beam-queue-batching/initial-failure/manifest.json`)
remains failed; it is not relabeled as a successful recovery.

The installed hub/Kafka identities, start times, restart counts and health are
unchanged. All runner-owned process groups were reaped. Explicit compaction and
batching are complete for this prototype. One head per project still limits
single-project processing throughput; bounded mailboxes, live-data retention,
automatic compaction policy, disk exhaustion, internal compactor failure,
backup/restore and production integration remain future work. The
completion review (`verification/beam-queue-batching/review.json`) records
fresh documentation and declared verification separately from the initial result.
