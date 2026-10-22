---
name: Durable effective recipe selection
summary: Atomically promote caught-up generations and preserve operator intent and rollback
kind: component
---
# Separate authority from derived rows

Persist selection control outside retrieval_index. Schema1 control contains
revision0..9007199254740991, selected nullable selection, previous nullable selection,
last_reset_id nullable opaque ID. A selection contains a complete primitive recipe,
primitive base_identity, proposal_id nullable, qualification_runtime nullable,
qualification_identity nullable digest, selected_at, activation_watermark and
qualification_watermark. Preserve this authority if derived rows are corrupt or
rebuilt. Invalid authoritative control fails store opening; never silently reset it.

Primitive base identity is SHA256 canonicalJSON of the complete operator recipe,
excluding runtime. The base config stays the operator value. An override applies
only when its base identity matches that value. Native-to-container/runtime
migration preserves the selected primitive while derived rows rebuild; expose
current vs qualification runtime and avoid claiming fresh runtime qualification.

Resolve effective config explicitly from one raw Config snapshot and one Store
snapshot. Do not change Config.get into a Store call or read a dynamic global
selection from Retrieval.effective. Capture resolved recipe/control for outside
native/model work and re-resolve actual current config/state at every lease/commit.
Keep ordinary matching/federation config raw: their global generation digest must
not acquire private retrieval tags. Feature-specific R/Archive/replay/optimizer
paths receive resolved snapshots. An explicit private replay candidate overrides
its branch recipe but retains the global effective baseline fence.

## Promotion and rollback

Promotion requires current Admin expected_revision and expected_selection_revision,
or current explicitly enabled automatic policy. Revalidate frozen proposal,
interpretation/runtime, group/label/exposure identities, baseline primitive/base,
selection revision, expected child runs and raw evidence. Both branches and every
required cohort gate must be eligible. No concurrent publication/context update
may be dropped: catch up the candidate to current public watermark and require a
complete exact source manifest under its primitive recipe, with no excluded roots.

In ONE durable Store transaction switch both selected primitive control and active
native generation, increment selection revision and retain the old effective recipe
and active generation as rollback. Never claim a config-file patch followed later
by index activation is atomic promotion. Before the ACK, canonical state is durable.
Concurrent readers see either complete matching recipe/generation pair. Pending
old-policy results are fenced rather than committed to the new selection.

The current active+rollback+ordinary staging+private candidate generations must fit
the shared configured native capacity. Reject insufficient room without dropping
rollback. Ordinary publication/context catchup must preserve a protected rollback
generation instead of replacing it with the same selected recipe. The next
promotion intentionally replaces rollback with that operation's previous active.

Rollback is an asynchronous owned Admin operation: build/catch up the retained
previous recipe to current originals/context under current bounds, then atomically
switch its primitive and complete generation together. A request never serves stale
rollback rows as ready. Preserve the replaced selection as previous. Cancellation,
interruption, source publication/context changes and hot resource reductions remain
visible checkpoints. Missing originals or corrupt authority cannot be repaired by
inventing a recipe or discarding source data.

A ranking/window/weight-only variant with identical tokenizer/chunk/context fields
may reuse the active structural rows and update exact generation recipe metadata.
New publications/incoming context still require correct catchup. Native row reuse
is observed work, not a new index construction claim.

## Operator resets and durable configuration recovery

Any successful explicit Admin patch containing retrieval.recipe, including an
identical merged value or deletion, resets the override. An actual external-file
primitive base change also resets; whitespace rewrite and unrelated patches do not.
Copy-active-to-base uses an ordinary explicit recipe patch and clears the override.
Existing generations become explicitly stale/building if their recipe differs;
never serve a mismatched generation as current.

Reset linearizes at its durable Store control transaction before configuration
mutation ACK. Protect crash recovery using the existing owner-only config commit
transaction with optional index_reset{id}. Preserve a reset-bearing transaction
until Store acknowledges its idempotent last_reset_id. Startup replays config and
journal, opens the authoritative store, completes that exact reset and only then
removes the transaction. Repeated crashes cannot reset twice or lose the decision.
A failed predecision config write must not clear a live selection. Store moves keep
an offline old copy and apply the committed reset to the selected destination.
Do not use a config-revision-only future marker: unrelated later no-op changes
could otherwise activate a failed reset. No new user-editable config-file location
or startup setting is introduced.

## Visibility and retirement

Existing retrieval_index adds selection:IndexSelectionView. Show base/effective and
previous recipes, selection revision, application state, activation/qualification
watermarks and current/qualification runtime. Agents see only global index control
metadata, never proposal questions, labels, cohort members or human identity.
Admin optimization detail exposes qualified evidence and explicit promotion,
rollback, reset/copy-base and derived retirement. Current state and retired evidence
are distinct. A generation moved into active need not remain duplicated privately;
retain its exact manifest/qualification mark and disclose later unavailable global
raw generation separately from retained paired evidence.
