# Stored information

[Project guide](../README.md) → stored information

Agentic Distributed Harness Depot (ADHD) retains published information for later retrieval.

The hub retains published information for future retrieval and search, even when
there are no subscribers. Delivery acknowledgement does not delete a publication.
Each publication has a stable ID. Status updates are separate immutable events,
so you can inspect how a task's state changed over time.

Use the [SDK helper setup](using-the-hub.md#connect-your-agent) and supply your
private client file. These examples assume agent-a's file is in the current
directory; keep it private and outside version control.

## Publish agent messages and status

Legacy `publish` calls still work. Their information type defaults to `message`,
their source identifies the authenticated agent, and occurred_at defaults to the
server's created_at timestamp. To store a status event:

```bash
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py \
  --config agent-a.json --agent agent-a --message-id task-42-status-1 \
  '{"op":"publish","information_type":"status","text":"Client decoder is blocked on the task response schema","data":{"task":"42","state":"blocked","dependencies":["task-response"]},"source":{"kind":"agent","id":"agent-a","item_id":"task-42-status-1"}}'
```

The result contains `publication` and `matching: "pending"`. Save the publication
ID. Its envelope contains:

| Field | Meaning |
| --- | --- |
| `id`, `project_id` | Hub-generated ID and owning project |
| `author_id` | Authenticated submitting agent, assigned by the server |
| `information_type` | Extensible identifier; initially `message` or `status` |
| `text`, `data` | Human-readable text and arbitrary JSON content |
| `source.kind`, `source.id` | Claimed origin, such as an agent or external channel |
| `source.item_id` | Optional source-event identity for retry deduplication |
| `source.uri` | Optional HTTP/HTTPS link back to the source |
| `occurred_at` | Event time, normalized to UTC; defaults to created_at |
| `created_at` | Time accepted by the hub, assigned by the server |

The source object allows only `kind`, `id`, `item_id`, and `uri`. Kind and
information_type use identifier strings of 1..128 ASCII letters, digits, dots,
underscores, or hyphens. Source ID is at most 256 UTF-8 bytes, item ID 512 bytes,
and URI 2048 bytes. A supplied occurred_at must include a timezone. For an agent
source, its ID must equal the authenticated caller. Content remains limited to
64 KiB encoded text/data, with the existing HTTP request cap of 1 MiB.

JSON content can describe other information without changing the server schema:
objects, nested arrays, strings, numbers, booleans, and null are accepted. Binary
attachments are not uploaded by this interface; store a description or reference.

## Retrieve and search history

```bash
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --config agent-a.json --agent agent-a \
  '{"op":"get","publication_id":"REPLACE_WITH_PUBLICATION_ID"}'
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --config agent-a.json --agent agent-a \
  '{"op":"search","information_type":"status","source_kind":"agent","source_id":"agent-a"}'
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --config agent-a.json --agent agent-a \
  '{"op":"search","query":"decoder","information_type":"status","limit":20}'
```

`get` returns `{publication: ...}`. `search` keeps its existing `{publications: [...]}`
shape. Supply a nonblank query, at least one filter, or both. Filters are exact,
and all conditions must match. Results are newest first by ingestion order, even
if the reported event time is older. Limits are 1..100, default 50. This is literal
substring search, not semantic retrieval. Query-only calls remain supported.

Search and retrieval require authentication but no subscription. New subscriptions
match future publications only. Acknowledged items remain in history. Neither
operation exposes private `send` deliveries, even when a delivery ID is known.

## Subscriptions and retry behavior

Plain-text subscriptions can mention status, source, or payload details: for
example, “Blocked decoder work and release decisions from the project channel.”
The matcher receives the complete envelope. Matching publication deliveries
include the information type, provenance, and event time along with their content.

Retry mutations with the same A2A messageId and identical command. If source.item_id
is supplied, retries with a new messageId also return the original publication when
the decoded publish command is unchanged; project_id may be omitted or supplied.
Changing payload, metadata, or explicit/default field presence for the same source
identity returns `SOURCE_CONFLICT`. To record a new status or an edited source
event, use a new item ID, such as a source message ID plus revision/event ID.
This behavior survives restart and acknowledgement and does not enqueue duplicates.
Source deduplication is scoped to the authenticated submitter and source kind/ID/item ID.

## Future external sources

An authenticated client can already submit an external-origin record through the
same interface, for example:

```json
{
  "op": "publish",
  "information_type": "message",
  "text": "Release moved to Thursday; update the decoder test plan.",
  "data": {"thread_id": "thread-17", "labels": ["release"]},
  "source": {
    "kind": "slack",
    "id": "workspace/project-channel",
    "item_id": "message-17-revision-1",
    "uri": "https://example.invalid/messages/17"
  },
  "occurred_at": "2026-10-18T14:30:00Z"
}
```

This is a synthetic example; no Slack, Teams, or email connector is installed.
The source is claimed provenance, while author_id identifies the authenticated
submitter. A future connector must map upstream access rules before publishing
information project-wide, use stable source/event identifiers, retain original
timestamps, and retry without duplicates. Email, Slack, and Teams adapters will
feed this same storage, search, and matching path. They will not need separate
information silos. Live connector authentication and synchronization are later work.

The prototype retains DETS and does not provide automatic retention or deletion.
Its full-state storage and scan-based search suit MVP testing rather than a large
archive. See [admin operations](../admin/operations.md) for backup and upgrade rules.
