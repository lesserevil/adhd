# BEAM-native eventing: Rheo evaluation

- **Status:** historical
- **Owning queue item:** none; BEAM-001 was removed by operator direction on 2026-11-04. See the [roadmap decision](../../roadmap/active-work.md#authorized-implementation-batches).
- **Completion / archival evidence:** source review complete; Rheo runtime experiments deferred in favor of the [Broadway/CubDB investigation](beam-queue-prototype.md); [operator retirement decision](../../roadmap/active-work.md#authorized-implementation-batches).

Current adoption status: BEAM-002 is completed (`docs/roadmap/beam-production.md`). The local
installation uses qualified embedded eventing. This document retains the
investigation/prototype scope and historical results. The operator removed
BEAM-001 on 2026-11-04; these notes impose no further comparison or research work.

## Scope and source identity

This is a source review, not a qualification or replacement of the running Kafka
deployment. No Rheo code, upstream tests, benchmark or crash experiment was run.

Reviewed Rheo **1.0.0**, published 2026-09-21, on 2026-10-25. The downloaded Hex
archive matches its release API checksum:
`1ccbc3c07ac26f8126ba24e2304876a0e3b1e975c43cb44e4c1671d1eba6e9d3`.
The relevant released source files were also byte-compared against tag `v1.0.0`,
commit `6d318335b39df4b8570f9088d3d515db8c56e277`.

The owning ADHD contracts remain `components/hub/eventing/spec.md`,
`components/hub/multi/spec.md` and `components/hub/project-recovery/spec.md`.
Their accepted-original, replay, authorization and recovery guarantees remain
requirements for any candidate transport.

## Assessment

Rheo is a useful candidate for a bounded prototype. Its stock Mnesia backend is
not yet established as sufficient for ADHD's crash-recovery requirements. Reuse
of its producer and consumer abstractions is promising; adoption requires an
ADHD adapter plus a proven storage/reconciliation strategy.

The [released package](https://hex.pm/packages/rheo/1.0.0) is MIT-licensed and
declares Elixir `~> 1.17`. Its mandatory dependencies are Jason and Telemetry;
GenStage and Broadway are optional integrations. Mnesia does not require the
optional SQL, MongoDB or Redis integrations. These declarations fit our current
Elixir version range, but compilation, dependency pinning, license inventory and
compile-once packaging still require qualification.

Rheo supplies streams, independent consumer groups, partition sequences, leased
delivery, fencing tokens, retry/dead-letter handling, replay and contiguous
acknowledgement frontiers. Its
[Broadway acknowledger](https://github.com/thanos/rheo/blob/6d318335b39df4b8570f9088d3d515db8c56e277/lib/rheo/broadway/acknowledger.ex)
maps processing success/failure to lease settlement and releases producer inflight
capacity. This is transport processing acknowledgement; ADHD must retain its
separate durable deliveries and agent poll/ack semantics.

## Findings and integration requirements

### Interrupted writes need a recovery design

The [Mnesia backend](https://github.com/thanos/rheo/blob/6d318335b39df4b8570f9088d3d515db8c56e277/lib/rheo/backend/mnesia.ex)
advertises `atomic_compare_and_set: false`. Append writes events and their index
before updating the stream's sequence counter. The
[storage wrappers](https://github.com/thanos/rheo/blob/6d318335b39df4b8570f9088d3d515db8c56e277/lib/rheo/backend/mnesia/store.ex)
use dirty operations, without an enclosing transaction or an explicit log-sync
step. Startup rebuilds secondary indexes but does not recompute sequence counters.

**Inferred risk, not a reproduced failure:** interruption between these writes
can leave event rows and sequence metadata inconsistent. GenServer serialization
does not make the group of writes crash-atomic. Delivery and frontier updates
also span separate writes. Process-restart persistence must not be interpreted as
a proven VM-crash or power-loss boundary.

Keep ADHD's synchronized original/outbox authoritative. Compare a reconstructible
Rheo transport generation with a hardened transactional Mnesia backend. Specify
when the outbox can retire an item, and how startup proves coverage before
resuming. A Mnesia transaction cannot include the existing DETS transition.

### A contiguous frontier does not serialize handlers

The [table engine](https://github.com/thanos/rheo/blob/6d318335b39df4b8570f9088d3d515db8c56e277/lib/rheo/backend/table_engine.ex)
can skip an earlier unclaimable lease and claim a later event. Its frontier tracks
contiguous terminal settlement; it does not itself require handlers to finish in
sequence. Broadway concurrency and redelivery can therefore require additional
ADHD sequencing. Prove project ordering through lease expiry, worker replacement
and retry rather than relying on the frontier alone.

Use one ADHD fanout group per project stream, with independent durable recipient
deliveries. Agents must not become competing consumers in that group. Preserve
project epochs, subscription activation snapshots and late-callback fencing.

### Rejection policy differs from a blocked transport gap

Retry exhaustion can reject a delivery. Rejected deliveries count as terminal for
frontier advancement. The inspected Mnesia tests explicitly cover advancing past
a rejected hole. ADHD's malformed/mismatching transport records instead require
durable quarantine and a visible blocked gap until an authorized disposition.
The adapter must preserve that distinction and keep filter failures separate
from raw transport progress.

### Retention and memory require application limits

All seven Mnesia tables use `disc_copies`. The reviewed public facade and Mnesia
path contain no event-retention/pruning operation; resetting a group retains the
event history. Producer `max_demand` bounds inflight leases, not the durable
backlog or total retained bytes.

Define admission limits and retention/reconstruction policy explicitly. Benchmark
bounded references to existing originals against stored payloads, including table
and index overhead. The current 1 GiB pending-byte default cannot simply become
an additional RAM-resident log inside the hub's 1 GiB container budget. Keep fact
history and acknowledged-delivery preservation independent of transport cleanup.

### Identity, storage and topology need an adapter

Rheo's event-ID index is shared across streams within a backend handle. The
reviewed append path does not make resubmission of a caller-supplied ID an
idempotent append. Specify namespaced internal identities and preserve ADHD's
logical event deduplication when an append reply is lost.

The default Mnesia directory is under the system temporary directory; configure
a private durable mount instead. Coordinate the one Mnesia application/schema
within the VM, and use fixed table prefixes rather than converting project or
agent IDs into dynamically growing atom/table names.

The Mnesia backend explicitly supports one node, not distributed lease
arbitration. This matches the first single-writer experiment. Multi-node HA is a
separate decision. Federation continues through authenticated ADHD protocols;
independent federated servers must not share a Mnesia cluster.

## Deferred Rheo experiment and decision gate

The user selected the [Broadway/CubDB prototype](beam-queue-prototype.md) instead.
The steps below remain a Rheo-specific alternative, not the current execution plan.

1. Preserve existing DETS originals/outbox and define an adapter with one project
   stream/fanout group, bounded queue references and separate agent acknowledgements.
2. Inject interruption between event/index/counter writes and between delivery,
   checkpoint and settlement writes. Restart the backend and whole VM separately;
   distinguish these tests from any power-loss claim.
3. Exercise lost append replies, expired/stale leases, retries and poison records.
   Check exact original coverage, ordering, duplicate logical effects, blocked-gap
   visibility, project isolation and epoch fencing.
4. Prove bounded backlog/retention, backup/selective restore and cold reconstruction.
   Measure idle/peak memory, disk growth, latency and catch-up against the existing
   Kafka baseline with the same workload and resource limits.
5. Select stock Rheo plus explicit reconstruction, a hardened backend, or another
   implementation only after that evidence. No production cutover is authorized by
   this review.

The inspected upstream tests provide useful functional coverage, but this review
does not establish interrupted multi-table-write or power-loss recovery. These historical limits remain unqualified; the associated investigation was
removed from the roadmap rather than relabeled as completed research.
