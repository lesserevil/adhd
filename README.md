# Agentic Distributed Harness Depot (ADHD)

Licensed under the [Apache License 2.0](LICENSE) (`Apache-2.0`).
Bundled third-party material retains its own license and attribution notices,
including the [Prompt Master MIT license](skills/agent/prompt-master/LICENSE.prompt-master).

ADHD helps agents working across isolated projects stay in sync. Agents communicate
through an authenticated A2A hub even when they cannot connect directly to each
other. They publish work updates, subscribe to project events and poll durable queues.
Profile 2 uses per-server Kafka; optional plain-text filters use a separately
configured short-response model.

The Elixir service provides subscriptions, publishing, addressed messages,
acknowledgements, and publication search over A2A 1.0 JSON-RPC. Agents explicitly
publish and poll; installing an A2A client alone does not synchronize their work.
Stored message and status history supports source provenance, retrieval by ID,
and source/type filtering. Opt-in [federation](docs/user/federation.md) adds durable
asynchronous discovery across trusted project hubs, using approved project evidence.
See the [stored-information guide](docs/user/stored-information.md).

## Start here

- **Using an existing hub:** follow the [user guide](docs/user/using-the-hub.md).
- **Trying the MVP:** use the [live-testing checklist](docs/user/live-testing.md).
- **Running the service:** follow the [admin guide](docs/admin/operations.md).
- **Local GPU model:** use the included [model container](docs/admin/model-service.md).
- **Connecting project hubs:** follow [federated discovery](docs/user/federation.md)
  and [canonical source routing](docs/user/federation-directory.md).
- **Problems:** use the [troubleshooting guide](docs/admin/troubleshooting.md).
- **Protocol and examples:** see the [hub API](docs/user/hub-api.md).
- **Development:** see the [project guide](docs/README.md) and
  [source build instructions](docs/user/getting-started.md).

## Container quick start

Use a profile-2-qualified artifact for the multi-project Kafka application. The
[model-free Compose/Kubernetes guide](docs/admin/event-service.md) owns its private
broker, persistent volumes and optional model deployment. Earlier accepted
profile-1 artifacts and their evidence remain a compatibility baseline; they do
not qualify the combined architecture.

The current source41 compiled candidate has passed the complete
[13-program core gate (94 checks)](verification/ownedMULTI008/source41-core13-positive/audit.json)
and [Compose11/Kind10 deployment programs](verification/ownedMULTI008/source41-baseline-platform-positive/audit.json).
[Current qualification and limits](docs/admin/event-service.md#qualification)
include the complete [Kafka14/68 gate](verification/kafka41-full14-positive/audit.json).
Full recovery25, final evidence composition and documentation-authority review
remain pending; this is not an all-green release claim.

Build the accepted portable Elixir artifact with the project's pinned Literate AI
installation and Elixir/OTP toolchain on the supported Linux authoring host:

```bash
litai build components/hub --update-receipt
litai verify
python3 scripts/stage_container.py
```

The current retained-source snapshot has a framework export limitation; use the
[evidence-bound rebuild staging route](docs/admin/operations.md#build-and-transfer)
if `litai build` reports an unsupported retained-source coding CLI.

On a Linux Docker host, copy the staged `_build/container` directory plus
`scripts/configure_hub.py` and `deploy/run.sh`, preserving these paths. Then run:

```bash
docker build --build-arg SOURCE_DATE_EPOCH=0 --provenance=false -t adhd-hub:local _build/container
python3 scripts/configure_hub.py --legacy-single-project
sh deploy/run.sh .adhd/container/hub.json .adhd/container/data
curl --fail http://127.0.0.1:8766/health
```

The standalone run.sh example above is explicit legacy compatibility. For
profile 2 use the Compose application in the event-service guide. A model is
optional: start the included GPU model container only for semantic filtering or
semantic queries, with a verified checkpoint:

```console
python3 scripts/model_service.py /absolute/path/to/checkpoint/bf16
```

Legacy defaults reach its Nemotron SystemOne service at
`http://127.0.0.1:18770/v1/systemone` on the Docker host. Set `--matcher-url` when
creating configuration to use another endpoint. See the admin guide for private
tunnels, client configuration, image identities, and backups.

## Current scope

The profile-2 contract supports multiple isolated projects per server, with one
hub process owning the registry and every project store. Linux Compose/Kubernetes
packaging keeps Kafka private; remote agents use the authenticated hub endpoint.
The older standalone host-networked run.sh path remains a legacy option.
The included model service runs in a separate GPU container with a read-only
checkpoint mount. Federation connects explicitly configured peers; it does not
automatically discover servers or share private addressed messages.

Queues, pending matching jobs, and acknowledgements persist across restarts.
Ordinary subscriptions receive new publications only; historical replay is an
explicit bounded Admin operation. Search is a literal, case-insensitive
substring search over published text, JSON, and provenance, with source/type filters.
Only filtered subscriptions use model thresholds, which require workload
calibration. Raw delivery and literal search work with matcher:null. There is no push delivery, automatic session
instrumentation or distributed storage. The new runtime upgrades the original
prototype store on startup; rollback requires its pre-upgrade backup.

The project uses specification-led generation through Literate AI. Product
behavior lives in `components/hub/component.md`; deployment requirements live in
`docs/admin/operations.md`. See `PROJECT.md` and the
[roadmap](docs/roadmap/active-work.md) for scope and implementation evidence.

The [web management console](docs/admin/web-console.md) provides authenticated health, information,
subscription and delivery observation, plus confirmed subscription management and
pending-job retries. It uses a separate administrator credential.
