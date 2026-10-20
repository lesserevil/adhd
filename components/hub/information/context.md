---
name: Contextual evidence
summary: Immutable contextual records and bounded authorized evidence traversal
kind: component
---
# Contextual evidence (INFO-002)

Extend publish with optional `context`, an object accepting only:

- `question`: nonblank UTF-8 text, at most 4096 bytes, retaining the question the
  publication answers verbatim.
- `subject` and `conversation_id`: nonblank strings, at most 512 bytes each.
  These are opaque user references, not a prescribed subject taxonomy.
- `reply_to`: one publication ID.
- `references`: at most 32 distinct objects `{publication_id, relation}`, where
  relation is `related`, `supports`, `contradicts`, `corrects`, or `question`.
- `snapshots`: at most eight objects `{uri,text}`. URI is an absolute http/https
  URL at most 2048 bytes and text is nonblank UTF-8 at most 16384 bytes. Store the
  supplied text; never fetch a URL during publication or evidence traversal.

All context combined is at most 65536 encoded bytes, independently of existing
text/data limits and the HTTP body cap. Reject unknown fields and malformed types.
Publication IDs use existing bounds. Pure CLI validation checks shapes; publish
also resolves every reply/reference to an existing project-public publication
before committing. Unknown/private-delivery IDs return NOT_FOUND without revealing
whether private content exists. An explicit correction is a new publication with
a `corrects` reference. It does not mutate or delete its target and is not proof
that the correction is true. Record authenticated author and claimed source as usual.

Publications contain `context` (default `{}`) and `content_identity`, the lower-case
SHA256 of canonical JSON for their immutable full envelope excluding
content_identity itself. Canonical JSON recursively sorts object keys and retains
array order and exact JSON values. Use deterministic encoding with no insignificant
whitespace. Preserve arbitrary existing JSON data; this identity is not a new
restriction to flat facts or a fixed domain ontology. Context and identity pass
through get/search, publication deliveries, model matching and administrator
publication views. Extend literal search to include encoded context. Existing
query-only search order/filters/response shapes remain compatible.

Deduplication compares the original decoded command including context. A new
source.item_id identifies a correction/revision event; it is never reused as a
mutable fact key. Existing stored retry results remain byte-for-byte equivalent
decoded objects, even if they lack newly added envelope fields.

Evidence traversal is deterministic, breadth-first, visited-ID deduplicated, with
configurable depth 0..4 and total expanded records 1..128 (defaults 2 and 64).
Include both outgoing references/replies and incoming corrections/replies within
the frozen authorized corpus. Preserve roots even when expansion reaches a limit.
Return explicit gaps `{publication_id,reason}` for missing, outside_snapshot,
depth_limit or record_limit; cycles terminate through visited-ID tracking and do
not duplicate evidence. Never cross private-message or project boundaries. Record
exact publication/context content identities used by a query or index. Later
replies and corrections invalidate affected derived index contexts, not originals.
Snapshot text retains its own sha256 identity in context manifests; a URL alone
is not evidence of the current contents of the remote page.

Use schema 3 for the extended DETS state. Upgrade schema 1 and 2 synchronously,
preserving source retry bindings (:sources), idempotent original results,
subscriptions, jobs, deliveries, ack state and sequences. Supply context `{}` and
compute stable identities for old envelopes. Add empty durable namespaces for
query jobs/attempts and versioned indexes/jobs without resetting any old state.
Unsupported/corrupt/wrong-project stores fail closed. Backup before upgrade;
rollback to older code requires the pre-upgrade backup. Native and independent
acceptance must exercise actual old-runtime stores and hard-kill recovery.

### Crash-safe commit and recovery bundle

DETS remains the working store. Its single object is not by itself an atomic
replacement under abrupt termination while a background write is in progress.
Maintain a private checksummed recovery journal at store_path + `.journal`,
containing the complete last committed state, including all historical reports,
idempotency, queues, query checkpoints and index work. Serialize the state with
the standard Erlang term codec, bind it with SHA256 and a versioned magic header,
and reject malformed checksums/frames, unsafe terms and invalid project/schema.
No credentials, provider tokens or live sessions enter either file.

For a transition, create a unique same-directory temporary journal exclusively,
restrict it to owner read/write, write and synchronously flush the complete frame,
close it and atomically rename it over the journal. Then update and synchronously
flush DETS before success. The journal rename is the logical commit point; a
client may retry an uncertain response using the original mutation identifier.
An uncommitted temporary file is not recovery authority. Do not claim protection
against storage hardware failure or power-loss behavior beyond the filesystem's
durability semantics; acceptance must prove abrupt process termination/restart.

At startup, a valid journal is authoritative and must pass full state validation
before readiness. Recover an out-of-date or unclean DETS working image from that
complete state. Preserve an unreadable/unclean image under a unique quarantine
name before rebuilding it; never substitute an empty state. A corrupt journal
fails startup even if DETS can be opened. Without a journal, require a valid clean
legacy DETS image (or genuinely new store), perform the existing upgrade, and
commit its first journal before readiness. Never silently repair a corrupt legacy
store without independent recovery evidence.

Back up/restore DETS and its journal together while stopped, preferably the entire
data directory. A restored pre-journal backup must remove/archive an upgraded
journal from the destination; do not mix snapshots. An old runtime rollback must
restore the complete pre-upgrade bundle. Exercise hard kills during asynchronous
indexing as well as idle matching, and verify recovery preserves exact accepted
results, history, private queues and acknowledgements. Test corrupt journal and
corrupt legacy images separately; valid-journal recovery is distinct from reset.

Round-trip “Yes” with its question/subject, cardinal/red-bird text, nested/scalar
JSON, linked correction, incoming reply and external text snapshot. Test shape
bounds, source retries/conflicts, unauthorized/private references, cycles,
snapshot cutoffs, traversal limits, acknowledgements and hard restart. Retain
exact evidence for later reconstruction and index rebuild.
