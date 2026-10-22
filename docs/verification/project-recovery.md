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
