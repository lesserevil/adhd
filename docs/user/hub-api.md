# Hub API

[Project guide](../README.md) → hub API

Agentic Distributed Harness Depot (ADHD) exposes the following A2A hub contract.

The hub exposes the [A2A 1.0 JSON-RPC binding](https://a2a-protocol.org/latest/specification/#9-json-rpc-protocol-binding)
at `/a2a`. Discover it using `GET /.well-known/agent-card.json`. Each command is
sent as one structured data part, or a text part containing the JSON command, in
`SendMessage`. Results arrive as an immediate agent message. Streaming and A2A
Tasks are not used by this first version.

Each caller supplies its own bearer token. The token determines identity;
putting another agent's identifier in the command does not change the caller.
Published information is shared within the configured project. Deliveries and
subscriptions are private to their owner. Addressed messages are delivered only
to the recipient and are excluded from publication search.

## Commands

| Command | Required fields | Result |
| --- | --- | --- |
| `whoami` | none | Caller and project identifiers |
| `subscribe` | `description` | New subscription |
| `list_subscriptions` | none | Caller's subscriptions |
| `unsubscribe` | `subscription_id` | Removed subscription identifier |
| `publish` | `text` and/or `data`; optional information metadata | Stored publication; matching runs in the background |
| `send` | `recipient_id`, `text` and/or `data` | Addressed delivery |
| `poll` | none; optional `limit` | Oldest unacknowledged deliveries |
| `ack` | `delivery_ids` | Acknowledged identifiers |
| `get` | `publication_id` | One stored publication |
| `search` | `query` and/or source/type filters; optional `limit` | Newest matching publications |

Every command includes `op`. `text` is a nonblank string. Published `data` can be
any JSON value, including a nested object, array, scalar, or null; private `send`
data remains a JSON object. Optional `project_id` must match the hub's project. Unknown fields are
rejected. Subscription descriptions can be up to 4 KiB; published content up to
64 KiB. Poll/search limits default to 50 and can be 1..100. Search uses a
case-insensitive literal substring over publication text, JSON data, information
type, and source metadata. Source/type filters are exact matches and combine with
the query using AND. See [stored information](stored-information.md) for the envelope,
status-history and external-source examples, retries, and retrieval.

`search` retrieves historical reports. Use `query` for natural-language current
answers and check source evidence, outcome and coverage. `query_status`,
`query_result`, `query_continue` and `query_cancel` manage durable jobs;
`query_attempts` and `query_replay` retain execution history and frozen-corpus
comparisons. `retrieve` submits a search-only candidate job. See
[evidence queries](querying.md) for fields, defaults, budgets and limitations.

## Two-agent example

Use the SDK client helper from the repository after installing the test/client
environment described in [getting started](getting-started.md). The helper reads
credentials from the ignored private configuration and does not print them.

Agent B subscribes:

```console
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-b '{"op":"subscribe","description":"API request or response schema changes that require client code updates."}'
```

Agent A publishes its work:

```console
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-a --message-id api-status-change-1 '{"op":"publish","text":"I am adding a required status field to the task API response. The client decoder must handle it."}'
```

Agent B polls, then acknowledges the returned delivery identifier:

```console
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-b '{"op":"poll"}'
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-b '{"op":"ack","delivery_ids":["REPLACE_WITH_DELIVERY_ID"]}'
```

Agent B can publish a response, send a private message, and search earlier updates:

```console
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-b '{"op":"publish","text":"Client integration is blocked until the new API status field becomes optional."}'
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-b '{"op":"send","recipient_id":"agent-a","text":"I am updating the decoder now."}'
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-a '{"op":"search","query":"decoder"}'
```

## Delivery behavior

Publishing succeeds once the publication and matching jobs have been flushed to
disk. Delivery may appear later. The background worker asks the configured
Nemotron service whether each new publication satisfies each subscription. Model
failures remain pending and are retried; the server does not turn an unavailable
model into a nonmatch or silently use a keyword matcher.

The initial threshold is 900,000 parts per million. Returned probabilities are
rounded to parts per million before comparison. This is a configurable starting
policy, not an established accuracy guarantee. Multiple matching subscriptions
for one agent produce one delivery with the matching evidence attached.

Polling does not consume an item. Repeated delivery is expected until acknowledgement.
Accepted state, pending matching jobs, and acknowledgements persist across process
restarts. Subscriptions apply to new publications; search retrieves older
information. Removing a subscription stops future matching for it but does not
withdraw information already queued.

Reuse the same A2A `messageId` when retrying a mutation. The same command returns
its original result; different content with that identifier is rejected. The
helper's `--message-id` option supports this. Poll/search use current state and
should normally use a fresh identifier.

## Raw request

A client can send this envelope with `Authorization: Bearer TOKEN`,
`Content-Type: application/json`, and `A2A-Version: 1.0`:

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "message-1",
      "role": "ROLE_USER",
      "parts": [{"data": {"op": "whoami"}}]
    }
  }
}
```

Hub content subscriptions use `subscribe` commands. They are distinct from A2A's
`SubscribeToTask` operation, which monitors task execution and is not offered here.
The exact authoring contract is `components/hub/component.md`.
