# Project recovery validation

The [offline validator report](../../verification/project-recovery/backup-validator.json)
records33 independent native-state, ownership, reference and bounds checks. It
validates complete retained snapshots without opening DETS or invoking live
configuration/model services; this is a pure-validator proof.

The [portable rebind report](../../verification/project-recovery/storage-rebind-native.json)
records12 native groups for frozen artifact
`2981accb64f9afb032dd996bb41f1fe2768cecfa8fdbedc464e4d1ce2e76b8b9`.
It covers complete stopped-server metadata rebind, moved-path cold startup,
unchanged product bytes/IDs/epochs, original publication/source retries, private
queue acknowledgements, retained workflow history, exact receipts after later
writes, and failures before a decision. Three separate cases stop the real
process after a successful metadata rename and directory fsync, then SIGKILL it
and verify restart/retry recovery at decision, registry and receipt boundaries.

These tests use actual native checkpoints and CLI operations. They precede the
additional raw-DETS hostile-input guard and do not qualify that later source or
claim container recovery coverage. An initial runner stopped on a harness-only
error-envelope assertion; the corrected report binds the exact harness bytes.

The raw checkpoint guard has independent [OTP27](../../verification/project-recovery/checkpoint-native.json)
and [OTP29](../../verification/project-recovery/checkpoint-otp29.json) reports,
each with46 passing checks. The tests execute the same new parser module against
actual runtime-produced checkpoints and a complete source36 product checkpoint.
They verify header/hash/count/trailer consistency, pointer and allocation
overlap/cycle rejection, exact one-row/state-map identity, integer free-list
structure, safe ETF and unknown-atom rejection, byte/deadline bounds, and legacy
phash lookup equivalence. Rejected inputs and explicitly unclosed headers cause
zero traced native DETS opens; each accepted file has exactly one native read-only
open and a lookup equal to the independently preflight-decoded value.

OTP29 executes the new module in the existing accepted image34 runtime with
network disabled and read-only source mounts. It does not claim that the existing
image34 application contains the recovery feature. The report's declared image
producer identity corresponds to the explicitly pinned Docker invocation; the
observed OTP/ERTS versions and file digests are recorded separately. Earlier
synthetic-fixture mistakes (nonzero-base trailer and hostile-atom length) remain
identified in the reports; their weaker results are not substituted for these
corrected checks. Full integrated recovery/CLI qualification remains a separate
gate after the guard is wired into every relevant native opener.

The subsequent [complete-allocation OTP27 report](../../verification/project-recovery/checkpoint-complete-native.json)
and [OTP29 counterpart](../../verification/project-recovery/checkpoint-complete-otp29.json)
bind the strengthened parser, with82 checks each. These add exact allocator-arena
coverage including live bucket padding, omitted free-block rejection, buddy
alignment, forged-arena rejection,23 actual retained product checkpoints and
eight actual reopen/value-growth/shrink/close stages on each runtime. This proof
supports the precise ordinary one-key physical subset stated in the recovery
interface; it does not claim generic DETS, imported/bchunk or custom-directory
compatibility. The earlier46-check reports remain historical evidence for their
earlier parser digest. Integrated service/CLI recovery remains independently gated.

The [integrated hostile-checkpoint CLI report](../../verification/project-recovery/rebind-hostile-native12.json)
binds source36-dev12 artifact `9b09eee676fb8ac2e95cba38cd29144c09f6e4a03acc0d84fb30747e745b7d71`.
Six explicit-hash requests reject missing free space, forged arena metadata,
a directory cycle, compressed/executable ETF and a free block within live padding.
Each returns the closed RESTORE_CONFLICT CLI error before a durable decision,
and every byte in its copied complete backup remains unchanged. Native-opener
tracing belongs to the separate parser reports, not this public CLI proof.

The [guarded integrated rebind report](../../verification/project-recovery/rebind-native12.json)
repeats all12 native portable/cold-server/crash groups on the same source36-dev12
artifact above, using the unchanged public CLI harness and fault hook. It covers
both healthy-byte preservation and the actual guarded opener path, retained
recovery history, moved-path cold startup, original/source retries and queue
acknowledgements, plus real fsync→SIGKILL recovery at decision, registry and receipt
boundaries. All12 pass. The earlier frozen review02 report remains evidence for
its earlier artifact; neither report claims an admitted release or container
qualification. The separate six hostile CLI cases use the same dev12 artifact.

The [actual pending-model service report](../../verification/project-recovery-pending-model/manifest.json)
passes four checks on frozen development13. A controlled local evaluator receives
an actual History POST and holds its response while the same hub loses one
nondefault project writer and restores an earlier complete empty backup. Releasing
the old typed response encounters a retired connection; neither the discarded
query nor publication reappears. The restored target accepts fresh writes, and
those writes and newer unrelated project data survive another cold start. The
runner adds only a private test observer for one Store loss; all data and recovery
operations use public Admin/A2A. This is cancellation and state isolation evidence,
not semantic quality or qualification of every pending model/peer/Kafka family.
An initial unsupported fixture operation and the old eventing worker's recovery
exception are retained as explicit limitations rather than hidden as clean runs.

The [actual peer catalog epoch report](../../verification/project-recovery/peer-epoch13-native.json)
binds source36-dev13 artifact `c5d684b9e9580170a3012fb369f4376cc1fbd7ec2f183124dbed12fea76667f1`
and records four passing checks across two isolated native hubs. A transparent
relay holds an actual authenticated v2 catalog success while the nondefault Red
writer is killed and its files are moved after observed Store DOWN. Public Admin
restore activates a fresh epoch in the same server process. Releasing the old
reply while its advertised cache lifetime is still valid leaves the directory
pending and empty. A separately held/released current-epoch catalog then populates
the directory, with its actual response revision/expiry; unrelated Blue private
messages and its route remain current. Models and eventing are disabled; no
provider, Kafka, container or lifecycle admission is claimed.

Two earlier harness failures are retained: [attempt1](../../verification/project-recovery/peer-epoch13-attempt1.json)
required a fresh request before releasing the old synchronous worker request;
[attempt2](../../verification/project-recovery/peer-epoch13-attempt2.json) allowed
only three seconds for a worker with a configured ten-second HTTP deadline.
The corrected test keeps the immediate empty-directory assertion and derives the
later refresh observation bound from that ten-second timeout plus two seconds
for scheduling. These timing corrections preserve the stale-result criterion.
The final origin stderr is empty; all owned hubs and relay threads were closed.

The [twelve-boundary native12 crash matrix](../../verification/project-recovery-crash/dev12/manifest.json)
passes eleven boundaries and preserves one failure after installing the snapshot:
the exact stage/target hardlink pair remains at link count two. Strict reads reject
that transient pair; subsequent unavailable-target alias lookup then stops startup.
[Native14 repair of the same interrupted fixture](../../verification/project-recovery-crash/repair14/manifest.json)
passes three checks, including exact original decision/state preservation and
another cold restart. This does not relabel the original failure or qualify all
boundaries on the successor.

The [actual Kafka callback repair](../../verification/project-recovery-pending-kafka/manifest.json)
passes five checks on frozen13 with only Resources/Eventing replaced. The original
accepted event is backed up pending; real old-topic and fresh-topic consumer
responses are held independently across live target restore. Releasing only the
old reply cannot create delivery/quarantine or advance the fresh offset. Releasing
the fresh reply delivers the original once, and its acknowledgement survives cold
restart. A retired active HTTP request now wakes its waiting owner through the
existing failure path, and the event worker survives a retired unit's failed error
recording. Ordinary completed HTTP releases add no cancellation message. The
[exact combined14 run](../../verification/project-recovery-pending-kafka/native14-manifest.json)
also passes all five checks; full image/platform qualification remains open.
The [retirement/link-boundary component report](../../verification/project-recovery/retirement-review14.json)
binds exact source36-dev14 artifact
`1ab074a9d82938c7f73854e70c9c680ca2fe623a4eabd5cfb9217662068d6979`
and six passing isolated checks. Real held HTTP verifies prompt retired-request
failure before the peer releases its response while Blue keeps its slot;
twenty ordinary real HTTP completions leave no unmatched failure messages.
The actual Eventing loop remains alive and begins independent work repeatedly
when a missing writer rejects both the work and failure-recording callbacks.
Actual closed staged tables verify both snapshot/checkpoint half-link recovery,
continued strict rejection of third/different-inode links, and preservation of a
valid advanced target. These are component checks, separate from the full
hub/Kafka/crash evidence. An initial harness compile attempt failed on ambiguous
Elixir `!=` spacing before any application modules ran; the corrected harness is
bound by the report digest.

The focused SourceQueries pin review on the source15-only overlay is retained in `verification/project-recovery/query-pin-overlay01-review.json`, with its failed ten-case raw report and log. Nine cases pass; explicit owner removal masked by another peer’s pending metadata remains a terminal-status defect. This is isolated actual-module evidence, not a full recovery or admission claim.
