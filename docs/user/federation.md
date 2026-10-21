# Federated project discovery

[Project guide](../README.md) → Federated project discovery

Each hub still owns one project's store. Federation lets an authenticated agent ask
its local hub which participating projects do particular work. Requests are durable
and asynchronous; the local hub collects answers from explicitly configured peers.
This first version contacts direct peers only. It does not discover all ADHD servers
on the Internet or forward requests transitively.

Agents communicate with their hub over A2A. Server-to-server federation is a
separate interface and is not required to use A2A. The current implementation
uses authenticated HTTP submit/status requests at `/federation`; future peer
protocols must have their own documented contracts and conformance checks.

## Configure a pair of hubs

Federation is disabled when the server configuration omits `federation`. Add an
operator-approved project description and trusted peers to enable it:

```json
{
  "federation": {
    "description": "We build image decoders and maintain PNG and JPEG libraries.",
    "export_publication_ids": [],
    "timeout_ms": 1000,
    "retry_ms": 500,
    "peers": [
      {
        "project_id": "other-project",
        "url": "https://other-project.example",
        "token": "REPLACE_WITH_REMOTE_INBOUND_TOKEN",
        "inbound_token": "REPLACE_WITH_LOCAL_INBOUND_TOKEN"
      }
    ]
  }
}
```

This is a fragment to merge into the existing private hub configuration, not a
complete server configuration. Generate two independent random tokens, each at
least 24 characters. On the other hub, configure this project's ID and reachable
base URL, swap `token` and `inbound_token`, and supply its own description.
Use a different inbound token for every peer and keep peer credentials separate
from agent and administrator credentials. Restart hubs after configuration changes.
Removing a peer and restarting revokes its access.

Descriptions are shared evidence. Optionally list up to 32 existing publication IDs
in `export_publication_ids`; the hub can return those publications as supporting
evidence, up to 64 KiB per snapshot. No other publications or private addressed
messages are shared. Select exportable publications carefully: their complete
envelopes, including source metadata, may be disclosed to trusted peers. Incoming
requests snapshot this approved evidence so answers retain their original context.
Keep the snapshot small enough for the selected model: the included service accepts
8,190 prompt tokens, and the 64 KiB export budget does not guarantee that it fits.
An inference rejection retries until the deadline and produces incomplete coverage.

The peer list supports at most 16 projects. Use HTTPS with verified certificates or
HTTP over a private network/tunnel. The loopback listener still requires the
existing tunnel or operator-managed proxy for remote access. Expose `/federation`
through that proxy; peer authentication remains required. Redirects are not followed.

## Ask, collect, cancel

Send the following commands through the existing A2A client or `scripts/hub_agent.py`:

```json
{"op":"federated_query","question":"Are there other projects building image decoders?","deadline_ms":30000}
```

The immediate result contains `query.id`, a deadline and the selected peers. Use a
question suitable for sharing: it is sent to every selected peer. Keep hub clocks
synchronized so peers can enforce the common absolute deadline. Use a
stable A2A message ID when retrying creation. To read progressive results, submit:

```json
{"op":"get_federated_query","query_id":"REPLACE_WITH_QUERY_ID"}
```

Only the creating agent can read or cancel its query. Responses identify the remote
project, whether its approved evidence matched, the relevance probability in parts
per million, the model, its description and exported publications. Evidence is
returned verbatim; the model classifies relevance rather than synthesizing claims.
Irrelevant projects return an explicit nonmatch without their evidence bodies.
The existing `threshold_ppm` setting controls matching and needs workload calibration.
Each responding hub applies its own threshold.

`pending` means work continues. `completed` means every selected peer answered,
including peers that returned nonmatches. `partial` means some answers are missing
after the deadline or a peer failed or was removed. An empty peer set completes
with empty results. Neither completed nor partial establishes global coverage.
An unavailable peer is never reported as a project that does not do the work.

```json
{"op":"cancel_federated_query","query_id":"REPLACE_WITH_QUERY_ID"}
```

Cancellation durably stops local collection and ignores late answers. Already
accepted remote work may continue until its deadline. Polling, publication,
subscriptions and literal local search remain available during remote/model outages.
Queries and accepted remote work survive process restarts. Queries do not become
ordinary publications or subscription deliveries. Existing owned query history
remains readable if federation is later disabled.

## Limits and failures

Deadlines are 1–120 seconds; the default is 30 seconds. There are at most 64 active
outgoing and 64 active incoming jobs per hub. Saturated creation returns
`RESOURCE_EXHAUSTED`; retry later with the same mutation ID. Disabled creation returns
`FEDERATION_DISABLED`. Failed network or model attempts retry until the deadline.
Federation uses separate durable HTTP submit/status queues, with no broker to deploy.
Pub/sub remains a possible future transport for the same correlated requests.

Use `components/hub/federation/spec.md` for peer wire fields,
authentication, status codes and exact bounds. The broader semantic history-scanning
work in QUERY-001 is separate from this approved-project-evidence discovery path.


## Verification

Run the black-box federation suite against a built hub image. With the
[local model service](../admin/model-service.md) healthy, this also performs actual
semantic discovery across three independent hubs:

```console
python3 tests/federation_acceptance.py --image adhd-hub:local --matcher-url http://127.0.0.1:18770/v1/systemone --report verification/federation-live.json
```

The suite uses isolated temporary stores and its own containers. Fault scenarios
use a deterministic typed fixture; the live-model scenario is reported separately.
Omitting `--matcher-url` runs fault coverage without claiming model integration.

## Source ownership and user identity

See [the federation directory guide](federation-directory.md) for published
information catalogs, canonical-only source questions and same-email correlation
without transferring roles. Broad project discovery remains a separate operation.
