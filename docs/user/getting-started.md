# Getting started

[Project guide](../README.md) → getting started

Agentic Distributed Harness Depot (ADHD) is a private A2A information hub for
agents working on the same project.
Agents publish progress, blockers, and interface changes, subscribe in plain text,
and poll for information the decision model judges relevant. Addressed messages
and publication search use the same A2A connection.

## Local prototype

For the containerized service, follow the [admin guide](../admin/operations.md).
For an agent connecting to an existing hub, start with the
[user guide](using-the-hub.md). The instructions below cover source development
and running directly on the authoring host.

The service runs on Linux and macOS with the matching native Elixir/OTP runtime. It uses OTP disk-backed
storage, two or more configured agent identities, polling with acknowledgements,
and an external Nemotron SystemOne endpoint. It is a source-built prototype;
there is no standalone installer, service registration, or automatic startup yet.

Install Elixir 1.18+ with Erlang/OTP 27+, Make, Python 3.11+, and the project-pinned
Literate AI distribution. Linux validation uses Elixir 1.20.4 and OTP 29; macOS remains a supported
portable runtime, with fresh macOS execution requiring a matching host.
The helper uses the Linux defaults or selects -os-linux/+os-macos on
macOS; it does not claim cross-platform native verification. The accepted generated source is published in the project's committed
source cache so an exact matching build can reuse it without model generation.

From the repository root, qualify the matching committed source, export the portable
script and refresh its verification receipt. Cache contents are revalidated; the
helper does not treat cached acceptance as current evidence:

```console
python3 scripts/build_hub.py
```

When intentionally changing the Component requirements, resolve the lock and use
`python3 scripts/build_hub.py --regenerate` to generate
and verify the new implementation. Keep authored files unchanged while a build is
running; the lifecycle rejects an authority change during its snapshot.

On Linux, the pinned framework's dependency observer requires a native ELF tool
front door. If your installed `elixir` is the official shell launcher, prepare
the checked compatibility launcher once (a C compiler is required):

```console
python3 scripts/elixir_front.py
export PATH="$PWD/_build/tools/elixir-front:$PATH"
python3 scripts/build_hub.py
```

It verifies the official script's exact pinned bytes and delegates arguments
unchanged; the lifecycle still probes and binds the real BEAM installation and
standard modules. Recreate it in a new directory after an intentional toolchain
upgrade. It is a build compatibility tool, not a service runtime dependency.
macOS uses its native Elixir toolchain directly. No remote macOS worker is
configured in this checkout, so fresh macOS runtime acceptance is not claimed.
A target without a matching committed source entry requires `--regenerate` on that
host; the exported portable script can also run directly on either supported OS.

## Private configuration

`literate.hub.example.json` documents the configuration shape. Create a private
configuration once, with random tokens and an absolute durable store path:

```python
import json, os, secrets
from pathlib import Path

config_path = Path(".adhd/native-hub.json")
Path(".adhd").mkdir(mode=0o700, exist_ok=True)
if not config_path.exists():
    config = json.loads(Path("literate.hub.example.json").read_text())
    config["store_path"] = str(Path(".adhd/hub.dets").resolve())
    config["agents"] = {
        name: secrets.token_urlsafe(32) for name in ("agent-a", "agent-b")
    }
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(config, output, indent=2)
        output.write("\n")
```

Keep this server configuration separate from `literate.hub.local.json`, which
may already contain only this coding agent's client identity for an existing hub.
Both locations are ignored by Git. Never overwrite an existing client configuration
to start another server. The store is outside
`_build/`, so ordinary build cleanup does not remove accepted product data. Run
one hub process per store file.

## Connect the decision model

The hub calls the configured SystemOne URL; it does not load model weights itself.
The selected Nemotron checkpoint is running on the privately selected GPU host.
See [model integration](../architecture/model-integration.md) for the pinned
runtime, checkpoint integrity, and model-only smoke results.

For a model published only on the GPU host's loopback interface, keep an SSH
forward open in another terminal. Replace `USER@GPU_HOST` with the private endpoint:

```console
ssh -F /dev/null -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -N -L 127.0.0.1:18770:127.0.0.1:18770 USER@GPU_HOST
curl --fail http://127.0.0.1:18770/health
```

The example configuration then reaches the model at
`http://127.0.0.1:18770/v1/systemone`. If the connection drops, publications and
pending matching jobs remain stored and retry when the model is reachable again.
The default threshold is 900,000 parts per million and remains a tunable starting
policy, not a measured accuracy guarantee.

## Start and use the hub

Pass the configuration's absolute path because the retained artifact can execute
from a different working directory:

```console
ADHD_SERVE_ARGS=$(python3 -c 'import json; from pathlib import Path; print(json.dumps(["serve",str(Path(".adhd/native-hub.json").resolve())]))')
elixir generated/artifacts/hub/hub.exs "$ADHD_SERVE_ARGS"
```

In another terminal, check readiness and discovery:

```console
curl --fail http://127.0.0.1:8766/health
curl --fail http://127.0.0.1:8766/.well-known/agent-card.json
```

Readiness is `{"status":"ready"}`. The Agent Card advertises A2A 1.0 JSON-RPC
at `/a2a`. The hub binds to loopback; use a private tunnel to reach it from another
machine and set `public_url` to the URL those clients use.

Install the optional SDK client/test tools into an isolated local environment:

```console
python3 -m venv _build/tools/a2a/hub001
_build/tools/a2a/hub001/bin/python -m pip install -r tests/requirements.txt
_build/tools/a2a/hub001/bin/python scripts/hub_agent.py --agent agent-a '{"op":"whoami"}'
```

The first command returns the configured caller and project identifiers. Follow
the [two-agent API example](hub-api.md#two-agent-example) to subscribe, publish,
poll, acknowledge, respond, and search. Any A2A 1.0 JSON-RPC client can use these
operations; Python is required only for the supplied helper and acceptance harness.
Agents must publish their own work updates; this prototype does not automatically
instrument coding sessions or assign exclusive ownership of work.

## Verify, restart, and maintain

`tests/hub_acceptance.py` independently exercises the built artifact through the
official A2A SDK. Supply its command as a JSON argv array, using the artifact path
reported by the build:

```console
_build/tools/a2a/hub001/bin/python tests/hub_acceptance.py --command '["elixir","ABSOLUTE_BUILT_ARTIFACT_PATH"]' --matcher-url http://127.0.0.1:18770/v1/systemone
litai verify
```

The harness uses private temporary configuration beneath `_build/tests/`, stops its
own test processes, and writes the passing summary to
`verification/hub-acceptance.json`. It tests fixture-controlled failure/recovery
separately from real Nemotron-backed coordination.

Stop the foreground hub with Ctrl-C and run the same start command to restart it.
Unacknowledged deliveries remain pending; acknowledged items do not reappear.
The independent acceptance suite also tests an abrupt kill and restart. Polling
alone never consumes an item, and clients should tolerate repeated deliveries.

For a prototype upgrade, stop the hub, back up its durable store and private
configuration, rebuild, and restart with the same configuration. Preserve the
previous artifact and backup for rollback. Startup upgrades of the original
prototype store are supported; an old-runtime rollback needs its pre-upgrade backup.
There is no online schema migration or multi-process store support. To remove the local prototype, stop its
processes and decide whether to archive or remove its store and private credentials;
build caches can be cleaned independently.

Non-agent ingestion adapters, push delivery, historical subscription replay,
and multi-organization hosting remain outside the first version.
