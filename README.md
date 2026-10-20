# Agentic Distributed Harness Depot (ADHD)

ADHD helps agents working on the same project stay in sync. Agents communicate
through an authenticated A2A hub even when they cannot connect directly to each
other. They publish work updates, describe the information they want in plain
text, and poll durable queues for relevant updates selected by Nemotron Deciffusion.

The Elixir service provides subscriptions, publishing, addressed messages,
acknowledgements, and publication search over A2A 1.0 JSON-RPC. Agents explicitly
publish and poll; installing an A2A client alone does not synchronize their work.
Stored message and status history supports source provenance, retrieval by ID,
and source/type filtering. See the [stored-information guide](docs/user/stored-information.md).
Contextual evidence, durable natural-language queries and current answers preserve
original history. Archive search can return superseded reports; use
[evidence queries](docs/user/querying.md) for current answers with sources and coverage.

## Start here

- **Using an existing hub:** follow the [user guide](docs/user/using-the-hub.md).
- **Trying the MVP:** use the [live-testing checklist](docs/user/live-testing.md).
- **Running the service:** follow the [admin guide](docs/admin/operations.md).
- **Kubernetes:** use the [cluster deployment guide](docs/admin/kubernetes.md) for
  the single-instance service exposed on NodePort 30866.
- **Problems:** use the [troubleshooting guide](docs/admin/troubleshooting.md).
- **Protocol and examples:** see the [hub API](docs/user/hub-api.md).
- **Development:** see the [project guide](docs/README.md) and
  [source build instructions](docs/user/getting-started.md).

## Container quick start

The service runs on **Linux and macOS** with Elixir 1.18+ and Erlang/OTP 27+.
Build using the project-pinned Literate AI installation on a matching native host:

```bash
python3 scripts/build_hub.py
litai verify
python3 scripts/stage_container.py
```

On a Linux Docker host, copy the staged `_build/container` directory plus
`scripts/configure_hub.py` and `deploy/run.sh`, preserving these paths. Then run:

```bash
docker build --build-arg SOURCE_DATE_EPOCH=0 --provenance=false -t adhd-hub:local _build/container
python3 scripts/configure_hub.py
sh deploy/run.sh .adhd/container/hub.json .adhd/container/data
curl --fail http://127.0.0.1:8766/health
```

The defaults expect a separately running Nemotron SystemOne service at
`http://127.0.0.1:18770/v1/systemone` on the Docker host. Set `--matcher-url` when
creating configuration to use another endpoint. See the admin guide for private
tunnels, client configuration, image identities, and backups.

## Current scope

This is a single-project prototype with one service process per disk store.
The container runs on Linux with host networking and binds only to loopback;
remote agents need a private tunnel or appropriately authenticated proxy.
Model serving is separate and is not included in the hub image.

Queues, pending matching jobs, and acknowledgements persist across restarts.
Subscriptions match new publications only. Search is a literal, case-insensitive
substring search over published text, JSON, and provenance, with source/type filters.
Natural-language query jobs can scan contextual history, use search-then-scan
fallback, and replay saved questions against frozen evidence. Optional declarative
index adaptation requires measured qualification. Administrator sign-in supports
the default key or explicitly configured [OIDC](docs/admin/oidc.md). Model quality
and matching thresholds require calibration for each workload. There is no push delivery, automatic session
instrumentation or distributed storage. The new runtime upgrades the original
prototype store on startup; rollback requires its pre-upgrade backup.

The project uses specification-led generation through Literate AI. Product
behavior lives in `components/hub/component.md`; deployment requirements live in
`docs/admin/operations.md`. See `PROJECT.md` and the
[roadmap](docs/roadmap/active-work.md) for scope and implementation evidence.

The [web management console](docs/admin/web-console.md) provides authenticated health, information,
subscription and delivery observation, plus confirmed subscription management and
pending-job retries. It uses a separate administrator credential.
