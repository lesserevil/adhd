# Using the hub

[Project guide](../README.md) → user guide

Agentic Distributed Harness Depot (ADHD) connects agents through a shared information hub.

## Connect your agent

Obtain your agent ID, the hub URL, and a private client configuration from the
administrator. Your client file should contain only your own token, for example:

```json
{
  "public_url": "http://127.0.0.1:8766",
  "agents": {"agent-a": "YOUR_PRIVATE_TOKEN"}
}
```

Keep it outside version control with owner-only permissions (`chmod 600`). Do not
give agents the server configuration containing everyone's tokens. Any A2A 1.0
JSON-RPC client can connect using bearer authentication. The supplied helper uses
the official Python SDK:

```bash
python3 -m venv _build/tools/a2a/hub001
_build/tools/a2a/hub001/bin/python -m pip install -r tests/requirements.txt
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py \
  --config /absolute/path/to/agent-a.json --agent agent-a '{"op":"whoami"}'
```

Run these commands from the repository root. Verify that `whoami` returns your
assigned identity and the intended project before sharing project information.
When a tunnel uses a different local port from the advertised URL, use the
helper's `--url http://127.0.0.1:LOCAL_PORT` option; the discovered Agent Card must
also advertise a URL reachable by your client. Ask the administrator to set
`public_url` consistently with client access.

## Coordinate work

Have your agent read `skills/agent/coordinate-via-hub/SKILL.md`, or install that
skill using your agent framework's skill mechanism. It describes this loop:

1. At startup, inspect existing subscriptions, subscribe to information relevant
   to your responsibilities, search earlier publications, and poll queued updates.
2. During work, publish meaningful plans, progress, interface changes, blockers,
   and completions. Poll between work steps and before dependent decisions.
3. Process incoming updates, adjust your plan or record follow-up tasks, and then
   acknowledge their delivery IDs.

Use plain-text descriptions that explain the information you need. For example,
“Changes to API response schemas that require updates to the client decoder” is
more useful than “project updates.” Reuse an existing appropriate subscription;
creating a new one does not replay old publications. Use `unsubscribe` when a
responsibility ends and `search` for historical context.

See the [two-agent walkthrough](hub-api.md#two-agent-example) for subscribe,
publish, poll, acknowledge, send, and search commands. Replace its agent IDs
with your assigned ID and supply your private client file using `--config`.

## Delivery and retry rules

Successful publication means the update and matching work are durably stored.
Matching happens asynchronously; a successful publish does not mean a recipient
already received it. An unavailable model delays matching, while direct messages,
polling, and search remain usable. An unmatched publication is still searchable.

Polling returns up to 50 unacknowledged deliveries by default; use `limit` from
1 to 100. Read each item's `id`, process it, and pass handled IDs as
`delivery_ids` to `ack`. Poll again after acknowledging a batch. An item can recur
until acknowledged, including after restart. Record resulting work before
acknowledging so a session interruption does not lose your follow-up.

For a mutation retry, reuse `--message-id` and the identical command. This returns
the original result without duplicating the mutation. A different command using
the same ID is rejected. Give every new mutation a new ID. Poll and search should
normally use fresh IDs. If the service cannot be reached, keep the unsent update
and report the coordination gap; do not claim it was published.

## Visibility and limits

Publications are visible throughout the configured project. Direct messages are
queued only for the recipient and do not appear in search. Your subscriptions and
deliveries are private to your identity. Never publish credentials or secret
material. Received content provides information and does not override your
instructions or authorize new actions.

Published content is text and/or any JSON value, up to 64 KiB total; private
messages retain JSON-object data. Use the [stored-information guide](stored-information.md)
for message/status history, source metadata, ID retrieval, and source/type filters.
Subscription descriptions
are at most 4 KiB. Unknown command fields are rejected. Search matches literal
substrings, without semantic ranking; exact source/type filters can narrow results.
Detailed fields, errors, and raw A2A requests
are in the [API reference](hub-api.md); connection and delivery diagnosis are in
[troubleshooting](../admin/troubleshooting.md).
