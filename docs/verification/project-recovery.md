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
