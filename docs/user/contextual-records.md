# Contextual records

Contextual records extend immutable publications with the communication context
needed to understand them. These commands are part of API profile 1.2.0; check
`/protocol/schema` for availability on a running server. The authoritative
contract is `components/hub/evidence/spec.md`.

Use `publish_record` when a statement depends on a question, subject, conversation
or task. Existing `publish` clients continue to work unchanged.

```json
{
  "op": "publish_record",
  "text": "Yes",
  "context": {
    "question": "Is there a bird in that tree?",
    "subject": "tree-observation-1",
    "conversation": "morning-walk"
  }
}
```

The reply contains `record` and `matching:"pending"`. The record retains the
original publication, context, immutable record identity, context hash and
resolved links. You can still use `get` and literal `search` for the underlying
publication. Context strings are communication hints; you need no domain schema,
entity table or truth classification. Arbitrary publication JSON remains intact.

Publish later observations separately. For example, publish “I see a cardinal in
that tree” and “There is a red bird on the branch” using the same subject. A later
“Actually, that was a leaf” can carry a correction link:

```json
{
  "op": "publish_record",
  "text": "Actually, that was a leaf.",
  "context": {
    "subject": "tree-observation-1",
    "links": [{"relation": "corrects", "publication_id": "publication-17"}]
  }
}
```

`reply`, `supports`, `corrects` and `related` describe relationships between
statements. A correction preserves both statements and their authors; it does
not make the newest statement true. Source-event retries compare the context as
well as the original content. Changing it requires a new source event.

Read a record and its bounded context with:

```json
{"op":"get_record","publication_id":"publication-17","max_depth":2,"limit":32}
```

The result includes a snapshot `{server_id,watermark}`, root `record`, `related`
records, `gaps` and `truncated`. Expansion includes public resolved links in both
directions and exact shared subject/conversation/task strings. It stops at the
requested depth and count. Cycles, missing references and missing external
snapshots remain visible. A missing or private addressed message is never expanded;
both produce the same unresolved-reference behavior.

Retain the returned watermark and use it on a later `get_record` request to
reconstruct the earlier membership after new replies or corrections arrive.
Watermarks track publication ingestion, independently of reported event time.
Record and context identities survive restart, project renaming and store moves.
A project rename updates the displayed project field consistently with existing
publication reads. Record IDs and original statements remain stable.

A link unresolved at ingestion stays unresolved. Publishing a guessed target ID
later cannot change earlier evidence. Add a new linked record when a relationship
becomes known. External references may include an authorized text snapshot and
its SHA256; the hub verifies supplied hashes and never fetches a URL automatically.
A URL without a snapshot is an explicit evidence gap.

The admin Information page exposes a read-only **Communication context** view
under publication details. Viewer and Developer access follows the existing
public-information permissions. Private addressed messages remain excluded.
Contextual records provide reproducible evidence; semantic scan answers and
adaptive indexes are separate roadmap work.
