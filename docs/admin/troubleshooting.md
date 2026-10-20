# Troubleshooting

[Project guide](../README.md) → troubleshooting

For Agentic Distributed Harness Depot (ADHD), start with the failing layer: container startup, hub health, client authentication,
then delivery and model connectivity. Use the [admin guide](operations.md) for
commands and the [API reference](../user/hub-api.md) for request shapes.
Collect image ID, redacted configuration fields, timestamps, HTTP/error codes, and
bounded logs. Do not include bearer tokens or private project content in reports.

| Symptom | Checks and recovery |
| --- | --- |
| Docker command missing or permission denied | Run container commands on the Linux Docker host as an account with Docker access. No local Docker installation is required on the authoring Mac. |
| Staging refuses output or reports hash drift | Use a new output directory; rerun `litai build components/hub --update-receipt` and `litai verify` before staging. Never edit an artifact or manifest to force a hash match. |
| Container name already exists | Inspect the existing container. If it is the intended stopped hub, start it; for an upgrade, stop/remove it after backup and recreate it. Never remove an unfamiliar container. |
| Startup exits or reports invalid configuration | Check `docker logs --tail 100 adhd-hub`. Validate JSON, distinct tokens of at least 24 characters, model fields, numeric bounds, and loopback host. Do not paste the config into a ticket. |
| Address already in use | Another process owns the configured port. Select a free port in server config, set `public_url` accordingly, recreate the container, and update client access. Host mode does not use Docker port publishing. |
| Store file cannot be opened | Confirm the host data directory exists, is writable by the runner's UID/GID, and is mounted at `/data`. The configured path should be `/data/hub.dets`. Use an absolute config path when running outside the container. |
| Corrupt store or another process has it open | Stop all writers and preserve the original files. Recover from a verified offline backup. Never delete the store to make startup succeed or run two containers against it. |
| Connection refused or discovery URL unreachable | Check container state and `/health` on the Docker host, then the tunnel/proxy and `public_url` in the Agent Card. Loopback on the agent's machine is not the server's loopback without a tunnel. |
| HTTP 401 | Use that agent's current private client file and bearer token. Verify the server was recreated after token rotation. Client `--agent` selects a token; it cannot override server identity. |
| JSON-RPC -32601 / -32602 | Use A2A 1.0 `SendMessage` with one JSON command part, supported operation names, required fields, and integer poll/search limits. The helper uses JSON text parts to preserve integers through the SDK. |
| IDEMPOTENCY_CONFLICT | A message ID was reused with different content. Retry the original command unchanged or give a new mutation a new ID. |
| SOURCE_CONFLICT | A source kind/ID/item ID was reused by the same submitting agent with a changed publish command. Retry the original payload exactly or use a new item/revision ID for a new event. |
| FORBIDDEN or NOT_FOUND on ack/unsubscribe | Use IDs returned to the authenticated caller. A batch ack is atomic: an invalid or foreign ID prevents the whole batch. |
| Delivery repeats after polling | Expected until acknowledged. Read its `id`, finish processing or record follow-up, then call `ack` with `delivery_ids`. Polling alone never advances the queue. |
| New subscription misses earlier information | Subscriptions apply only to subsequent publications. Search older published information; adding a subscription does not replay history. |
| Published update has no delivery | Check that the intended subscription existed at publication time, its description, the threshold, and model connectivity. Delivery is asynchronous. The model may judge the update irrelevant; published data remains searchable. |
| Hub healthy but matching delayed | Health excludes model availability. Check the separate model `/health` and network/tunnel from the Docker host. Pending jobs retry durably; do not republish repeatedly. |
| Search misses a direct message or paraphrase | Direct messages are not searchable. The `search` command is literal substring matching. Use `retrieve` or durable `query` for semantic evidence; configure the separate generative evaluator for answers. |
| Old publication retry lacks provenance fields | Preserved schema-1 idempotency results are returned verbatim. Retrieve the publication with `get` or `search` to see its normalized message type, agent source, and occurrence time. |
| Container is unhealthy or exits under load | Check logs, `docker stats`, and `docker inspect adhd-hub --format '{{.State.OOMKilled}}'`. Check host disk space and data permissions. An unhealthy health check alone does not trigger a Docker restart. Adjust limits only with workload evidence. |
| Restored data differs from the latest state | Restore returns to the backup point, including then-pending deliveries and acknowledgements. Preserve the pre-restore directory and use the rollback procedure if the wrong backup was chosen. |

## Isolate matcher problems

First check the matcher on the Docker host:

```bash
curl --fail http://127.0.0.1:18770/health
```

A healthy model process is necessary but a typed SystemOne response is also
required. The hub expects `answers.relevance` with `type: "noul"` and a finite
numeric `noul` value between zero and one. A malformed response, timeout, or HTTP
error stays pending and retries; it is not treated as a nonmatch. See the exact
request/response contract in [model integration](../architecture/model-integration.md).
When the endpoint is remote, verify the configured URL and private SSH tunnel
before changing subscriptions or thresholds.

Do not lower the threshold simply to hide an outage. Threshold changes affect
relevance decisions and need evaluation using representative project updates.
Keep a concrete publication/subscription example for diagnosis, with sensitive
content removed. The prototype has no queue-inspection or manual requeue admin API.

## Recover safely

Use the [offline backup and restore procedure](operations.md#backup-and-restore).
Keep original files and exact image IDs before recovery. If a new deployment
fails, revert using the previous image and a compatible store. Stop when a backup
is missing, a store's origin is unclear, or another writer may still be running;
resolve that condition before changing durable data.

## Web console

See [Web management console](web-console.md) for setup. A 404 from /admin/api means
admin_token is absent; add it to the private server configuration and restart. A
401 means the administrator credential is missing, wrong or rotated; agent tokens
are intentionally rejected. Reload and sign in with the current private token.
A 403 indicates a mismatched Origin: open the console and API through the same
private hub URL. Never disable the browser boundary to work around this.

An unavailable matcher can leave jobs pending while the hub and archive remain
usable. Restore matcher connectivity, Refresh, then optionally confirm retry of
pending jobs. Retry does not resurrect cancelled jobs or acknowledged deliveries.
If a management request loses its connection, retry with the same message_id and
unchanged command; 409 means the ID was already used for different input.
Lists are bounded; use Information filters to narrow results. Private addressed
message bodies are unavailable in the administrator UI by design. A stale page
after an upgrade should be reloaded; login is required again because the token is
held only in page memory.
