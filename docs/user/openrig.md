# OpenRig interoperability

ADHD's client adapter supports **OpenRig 0.6.14**, pinned to upstream tag
[`v0.6.14`](https://github.com/mvschwarz/openrig/tree/v0.6.14), commit
`df1c1517f03a403fb468523be1c563d489209a1d`. The published package is
`@openrig/cli@0.6.14`; its `rig --version` reports `0.6.14 (df1c1517)`.
Upstream requires Node 22 or newer and tmux on Linux/macOS. This compatibility
contract uses the documented CLI, daemon and terminal seats; it assumes no
native OpenRig A2A implementation. Other OpenRig versions require qualification.

OpenRig owns execution, runtime sessions, local work queues and terminal recovery.
ADHD owns project admission, durable events, subscriptions, addressed messages,
facts and federation. The adapter does not launch a provider/model, monitor panes,
copy OpenRig's queue into ADHD, or acknowledge deliveries automatically. Agents
outside OpenRig continue using the same [A2A API](hub-api.md).

## Provision one binding per seat and project

An ADHD Admin provisions an agent with the appropriate owner and project grants
through the Admin page, independently of OpenRig roles. Give each seat its own
agent credential. Rig membership, similarly named users and claimed provenance
confer no ADHD access. The operator supplies the expected hub server identity
from its authenticated directory. Do not bootstrap that trust from an untrusted
received event.

Create a private JSON file with exactly these fields and restrict it to the seat's
OS account (`chmod 600`). The values below are placeholders, not credentials:

```json
{
  "url": "https://hub.example.test",
  "server_id": "expected-stable-hub-server-id",
  "project_id": "project-red",
  "agent_id": "rig-alpha-worker",
  "token": "PROVISIONED_PRIVATE_BEARER",
  "rig_id": "RIG_UUID_FROM_RIG_PS",
  "seat_id": "work.worker"
}
```

Use `rig ps --nodes --rig RIG_NAME --json` to obtain the immutable `rigId` and
member `logicalId`. Display names, tmux session names, pane IDs, process IDs and
occupant generations are not durable rig/seat identity. Restoring the same rig
keeps its binding; importing a replacement rig with a new UUID requires a new
binding. Never silently rebind a token to a replacement rig. Separate projects
use separate files even when the seat is admitted to both.

Use TLS for remote hubs. The adapter permits HTTP for isolated loopback tests;
it does not establish TLS trust or distribute secrets. Credentials remain in
the private file, never CLI flags, environment values or an OpenRig spec. A
nonsecret absolute binding-file path may be supplied in the seat's environment
or context. Respect OS filesystem access: other processes under the same OS
account are not a security boundary.

Install the repository's [A2A client dependencies](getting-started.md), then run
the adapter from the existing seat, using the same Python environment:

```bash
python scripts/openrig_hub.py --binding /private/alpha-red.json \
  --message-id alpha-red-subscription-v1 \
  --command '{"op":"subscribe","mode":"raw"}'
python scripts/openrig_hub.py --binding /private/alpha-red.json \
  --message-id build-42-event-v1 \
  --command-file /private/build-42-event.json
```

For the publication command file:

```json
{"op":"publish","information_type":"status","text":"Build 42 passed","data":{"build":42},"source":{"item_id":"build-42-passed-v1"}}
```

Use `mode: "filtered", filter: "Only failed builds"` for an optional model
filter. Raw subscriptions require no model. Filters, Kafka, fact searches and
federated queries retain their existing hub semantics and limits. `send`, `poll`,
`ack`, `search`, `get`, `federation_directory`, `source_query` and the remaining
agent operations use their existing command shape; the binding supplies project
context. Commands that specify a different project are rejected locally.

## Exact wire and identity contract

`scripts/openrig_hub.py` uses the official A2A SDK with JSONRPC, A2A-Version 1.0,
and the agent's bearer token. Commands are JSON text parts to preserve integer
tokens. Before an action, authenticated `whoami` must match agent/project and
`federation_directory` must match server/project. A mismatch or denial stops the
action. This validates the provisioned identity, not OpenRig's local process
identity: rig/seat provenance is a caller claim, not remote attestation.

The SDK validates replies, then the adapter returns their original HTTP JSON
data. This preserves integer revisions for edit round trips and distinguishes
arbitrary payload numbers such as `1` and `1.0`; it never coerces every float to
an integer based on its mathematical value.

For `publish` and `publish_record`, the adapter assigns `source.kind: "openrig"`.
`source.id` is `openrig-v1-` followed by lowercase SHA-256 of UTF-8 compact JSON:

```text
["adhd-openrig-v1",server_id,project_id,rig_id,seat_id,agent_id]
```

JSON uses no ASCII escaping and separators `,` and `:` without whitespace.
Array order is fixed as shown; strings are preserved without Unicode
normalization. This avoids delimiter ambiguities and includes the server and
project namespace. Caller source metadata may contain only `item_id` and `uri`;
a nonblank stable `item_id` is required. The hub still assigns authenticated
`author_id`, project and publication identity; it does not trust the hash as an
authorization credential.

For publication and direct-message data, the adapter wraps the original value:

```json
{"openrig":{"version":1,"server_id":"...","project_id":"...","rig_id":"...","seat_id":"...","agent_id":"..."},"payload":{"build":42}}
```

Missing original data becomes `payload: null`. The wrapper and source identity
are deterministic and independent of restarts. Original data cannot replace the
reserved provenance. Text is preserved. Direct messages have this data wrapper
and the hub's authenticated sender; they do not become searchable publications.

Retain the exact command file and stable `--message-id` before each mutation;
reuse both on an uncertain response. Source item IDs deduplicate publication
retries under the hub's existing source-conflict rules. A changed event needs a
new source item and message ID. `poll` is observational; process a delivery before
acknowledging its exact ID. Restart the seat/daemon and poll again after an outage;
unacknowledged deliveries remain eligible. Do not reflect received events back
as new publications automatically: this adapter adds no federation relay or echo
loop. Federation preserves originating server/project/publication/source IDs;
remote facts must retain those identities rather than being re-authored locally.

For two hubs, configure authenticated peer identities and explicit project-pair
grants in Admin, publish each canonical source catalog, then use ordinary
`source_query` and asynchronous result polling. Route canonical scopes to their
owner. Each rig retains its local hub binding; remote roles and rig membership
are never imported. See [the protocol reference](../protocol/README.md) for the normative
server protocol (the OpenRig adapter does not replace it).

## Reproducible acceptance

`tests/openrig_acceptance.py` requires an explicitly installed pinned `rig`
executable and Node >=22 on PATH. It uses only isolated OPENRIG_HOME and tmux
state beneath the supplied private work directory, launches two actual rigs with
supported **terminal infrastructure seats**, and executes this adapter inside
their real panes. These deterministic seats prove CLI/daemon/mux and A2A
integration; they do not claim autonomous Claude/Codex/Pi model-agent execution.
No provider is launched and no existing provider configuration is changed.

```bash
python tests/openrig_acceptance.py --hub /path/to/qualified-hub.exs \
  --rig /isolated/node_modules/.bin/rig \
  --openrig-tarball /isolated/cli-0.6.14.tgz \
  --eventing-rest-url http://127.0.0.1:18082 \
  --keep-work _build/openrig/acceptance --report _build/openrig/report.json
```

Obtain the archive from the exact registry URL in `tests/openrig_pin.json`;
the fixture verifies its SHA-512 integrity and compares every archived package
file with the actual installed CLI/daemon before executing it. Install it into an
isolated npm prefix using Node >=22 (`npm install --prefix PREFIX
@openrig/cli@0.6.14`), keeping the operator's existing OpenRig installation intact.
Reports bind actual CLI version, artifact, adapter and harness hashes. Optional
`--with-model` uses the explicitly labeled controlled matcher to exercise filtered
delivery transport, not semantic quality. Final artifact and federated-rig
qualification remain separate evidence gates until their reports pass. Add
`--peer-eventing-rest-url URL --with-model` to run two separate real ADHD hubs,
require distinct broker cluster identities, and exercise canonical routing,
unchanged exported provenance, no role transfer and remote outage/restart.

The [source28 OpenRig qualification](../validation/openrig-28.json) records eleven
passing groups with the exact hub, adapter, harness, upstream package and runtime
identities. Two actual rigs exchange raw and controlled-filter deliveries through
real CLI/daemon/tmux seats, preserve numeric JSON types, and recover source IDs
and acknowledged queues after outages. Two separate hubs on distinct Kafka
clusters also preserve canonical remote provenance and local authentication
across a remote restart. This is terminal infrastructure-seat interoperability;
it does not certify autonomous model-agent behavior.
