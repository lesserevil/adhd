# Admin guide

[Project guide](../README.md) → administration

## Deployment contract

For the node-bound cluster deployment and exposed NodePort, see
[Kubernetes deployment](kubernetes.md). It reuses the accepted hub image with a
proxy, separate credentials and a persistent volume.

Run one Agentic Distributed Harness Depot (ADHD) Elixir process per DETS store
in a Linux Docker container. Store
data in an operator-owned bind-mounted directory; mount configuration read-only
from outside the image. Never run two containers against the same store, including
during upgrades, recovery, or backup. The model runs separately and needs a GPU;
the hub container does not need GPU access or model weights.

Native service operation supports Linux and macOS. The checkout defaults to
Elixir, Make and Linux; scripts/build_hub.py selects the matching host OS Flavor. The exported artifact is
a portable Elixir source script, not a macOS executable or native BEAM closure.
Container packaging copies that exact script and recompiles it using the pinned
Linux runtime. No additional compiler Flavor is required for this packaging path.
Linux runtime compatibility is independently checked by the container acceptance
suite. A future native Linux build would require its own platform Flavor and
lifecycle evidence.

The image pins official Elixir 1.20.4 / OTP 29 Alpine by digest. The staging tool
requires passing project verification, checks the exported artifact hash, and produces a minimal build context with a
Dockerfile, hash manifest, and deterministic archive containing the script,
health probe, manifest, and both the hub and stored-information contracts.
It never sends the repository, configuration, stores, or checkpoint to Docker.
This is local OCI deployment packaging, not a registry publication or tagged
Literate AI native-package release.

Use Linux Docker Engine with host networking. The listener remains bound to
`127.0.0.1`, preserving the current application contract. There is no `-p` mapping:
host networking shares the host's network namespace. The matcher URL's loopback
address consequently refers to the Docker host. Docker documents this behavior
in its [host networking guide](https://docs.docker.com/engine/network/drivers/host/).
Docker Desktop host networking is not validated by this project.

## Build and transfer

On the supported authoring host, with the pinned Literate AI installation and
Elixir/OTP toolchain:

```bash
python3 scripts/build_hub.py
litai verify
python3 scripts/stage_container.py
```

The output directory must be new; choose `--output _build/container-next` for
another staging run. A stale hash fails staging. A changed specification requires
the rebuild procedure in [source setup](../user/getting-started.md).

Use a current Docker Engine with BuildKit. Staging normalizes archive ownership,
timestamps, and permissions; the build command fixes image timestamps and disables variable
provenance attestations. Record the image ID and input manifest. Reproducibility
is checked for the tested architecture and builder; it does not imply identical
images across different CPU architectures or Docker versions. See Docker's
[reproducible build guidance](https://docs.docker.com/build/ci/github-actions/reproducible-builds/).

Transfer the staged directory and `deploy/run.sh`, `scripts/configure_hub.py` to
the Linux host. Preserve their relative paths and run the remaining commands on
that host, as a non-root account with Docker access:

```bash
docker build --build-arg SOURCE_DATE_EPOCH=0 --provenance=false -t adhd-hub:local _build/container
docker image inspect adhd-hub:local --format '{{.Id}}'
python3 scripts/configure_hub.py --directory .adhd/container
sh deploy/run.sh .adhd/container/hub.json .adhd/container/data
curl --fail http://127.0.0.1:8766/health
```

For a different port, project, or matcher URL, pass `--port`, `--project-id`, or
`--matcher-url` to the configuration tool. An existing configuration directory is
never overwritten. The defaults create two identities, `agent-a` and `agent-b`,
with distinct random tokens. Files have mode 0600 and their directory is 0700.

The runner requires Linux `realpath`, an available configured port, a readable
config file, and a writable data directory owned by the invoking account. It
runs with that account's UID/GID, a read-only root filesystem, dropped capabilities,
no new privileges, bounded logs, and a writable temporary filesystem. It sets
limits of 512 MiB memory, two CPUs, and 128 processes. Adjust these limits in the
deployment recipe when workload measurements require it. The default container
name is `adhd-hub`; optional third and fourth runner arguments select name and image.

## Configuration and credentials

The server file is `.adhd/container/hub.json`. Its important fields are:

| Field | Purpose |
| --- | --- |
| `project_id` | Single project served by this store |
| `host`, `port` | Loopback-only listener and available TCP port |
| `public_url` | Base URL advertised in discovery; must be reachable by clients |
| `store_path` | `/data/hub.dets`, mapped to the host data directory |
| `agents` | Agent ID to distinct bearer-token mappings, at least 24 characters each |
| `matcher.url`, `matcher.model` | SystemOne endpoint and model identifier |
| `matcher.timeout_ms`, `matcher.retry_ms` | Inference timeout and background retry interval |
| `threshold_ppm` | Match policy, initially 900000; needs workload calibration |

Give each agent only its `.adhd/container/agent-a.json` or `agent-b.json` client
file. It contains that agent's token and the URL, without the other identities.
Transfer it privately and keep it out of logs, chat, and version control. For
credential rotation or configuration changes, stop the container, edit the private
file, update affected clients, and recreate the container so a file bind mount
cannot retain an old inode. Keep IDs and project identity stable when reusing a
store. Removing an identity does not erase its historical publications or inbox.

Remote agents need a private tunnel or an operator-managed TLS proxy. For a tunnel,
set `public_url` to the URL used on the client side and forward that client port
to the service host's loopback port. Restrict tunnel/proxy access and require the
hub bearer token. The plain HTTP listener must stay private. The product does not
provision proxies, TLS certificates, or network-wide authentication.

## Model connectivity

The default assumes the selected Nemotron SystemOne server is already listening
on the Docker host at port 18770. Check it independently:

```bash
curl --fail http://127.0.0.1:18770/health
```

If the model runs elsewhere, configure a reachable private endpoint or keep an SSH
tunnel open on the Docker host as described in [source setup](../user/getting-started.md#connect-the-decision-model).
Container health means the store and listener are available; it deliberately does
not mean inference is available. Pending matching jobs persist and retry after an
outage. See [model integration](../architecture/model-integration.md) for the
checkpoint and serving identities; no keyword fallback is used.

## Monitor and stop

```bash
docker ps --filter name=adhd-hub
docker inspect adhd-hub --format '{{.State.Health.Status}}'
docker logs --tail 100 adhd-hub
docker stats --no-stream adhd-hub
docker stop --time 30 adhd-hub
docker start adhd-hub
```

Readiness is `{"status":"ready"}` at `/health`. Docker probes every 30 seconds;
an unhealthy status does not itself restart the container. The restart policy is
`unless-stopped`, which handles process exits and daemon restarts but respects an
explicit stop. Check model health separately and periodically verify a representative
publish-to-delivery path. With `admin_token` configured, the
[web console and administrator API](web-console.md) provide queued-delivery counts,
matching-job status, matcher health observations, and confirmed retries of pending
jobs. Failed matching attempts remain pending for retry; they are not a separate
failed-job status. Historical metrics are not provided. Avoid putting bearer tokens
in diagnostic output.

## Backup and restore

Take an offline backup; do not copy a live DETS file. Stop every process using the
store and save the entire data directory and the matching private configuration.
Schema 3 stores a working DETS image plus an authoritative checksummed recovery
journal at `store_path + ".journal"`. Keep both files from the same stopped service;
do not restore a DETS image alongside a newer journal. A valid journal recovers
an unclean DETS image after process termination. Invalid journals fail startup
rather than silently falling back or resetting history. These checks establish
process-crash recovery, not a stronger filesystem or power-loss guarantee:

```bash
docker stop --time 30 adhd-hub
umask 077
ADHD_BACKUP_DIR=".adhd/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ADHD_BACKUP_DIR"
cp -p .adhd/container/hub.json "$ADHD_BACKUP_DIR/hub.json"
cp -pR .adhd/container/data "$ADHD_BACKUP_DIR/data"
docker inspect adhd-hub --format '{{.Image}}' > "$ADHD_BACKUP_DIR/image-id.txt"
docker start adhd-hub
```

The recorded ID identifies the running image even if its tag has changed. Protect and retain backups
according to project data requirements. Store client credentials privately as
needed; the server backup contains all server tokens.

To restore, first verify the backup is complete and readable. Stop and remove
the container while preserving current data for rollback:

```bash
docker stop --time 30 adhd-hub
docker rm adhd-hub
mv .adhd/container/data .adhd/container/data-before-restore
mv .adhd/container/hub.json .adhd/container/hub-before-restore.json
cp -pR "$ADHD_BACKUP_DIR/data" .adhd/container/data
cp -p "$ADHD_BACKUP_DIR/hub.json" .adhd/container/hub.json
sh deploy/run.sh .adhd/container/hub.json .adhd/container/data adhd-hub adhd-hub:local
curl --fail http://127.0.0.1:8766/health
```

Restoring the whole directory also removes journals from newer runs. When restoring
a pre-journal backup manually, archive/remove the upgraded journal with its data
directory before opening the older DETS file; never mix generations.

Use the backed-up image ID as the final argument if its format differs from the
current image. Ensure restored files retain ownership suitable for the runtime
UID. Verify identity, known publications, pending deliveries, and acknowledgements
through the SDK. Restoring intentionally returns to the backup point: later
publications and acknowledgements are absent. To undo the restore, stop/remove
the container, retain the restored directory, put `data-before-restore` and
`hub-before-restore.json` back in their original locations, and run the old image.
Do not overwrite an existing rollback directory on repeated recovery attempts.

## Upgrade and remove

Record the running image ID and take an offline backup first. Build the new image
under a separate tag, stop and remove the old container, then invoke the runner
with the same config and data paths and the new image. Verify health and the
two-agent workflow. Preserve the old image until acceptance is complete. There
is a built-in startup upgrade for the original schema-1 prototype store. It
preserves history, subscriptions, delivery/acknowledgement state, pending matching
jobs, sequence numbers, and retry records; old publications receive default agent
message metadata. Back up before this upgrade. Legacy idempotent retries still
return their exact original results, which can lack the new metadata fields;
`get` and `search` return the enriched envelope. Unsupported or corrupt schemas
are rejected. Other incompatible versions require an explicit migration plan.
For rollback, use the previous image and pre-upgrade compatible backup; do
not assume a new store format can be read by older code.

To uninstall, stop and remove only the hub container. Keep or archive the data,
private configuration, and backups according to your retention decision. Removing
the image or a build context does not remove bind-mounted data. Do not prune shared
Docker resources or remove the independently operated matcher.

## Verify a deployment recipe

On the Docker host, install the SDK dependencies into an isolated environment
and run the independent suite from the repository root:

```bash
python3 -m venv _build/tools/a2a/container
_build/tools/a2a/container/bin/python -m pip install -r tests/requirements.txt
_build/tools/a2a/container/bin/python tests/container_acceptance.py --image adhd-hub:local
```

This creates uniquely named disposable test containers and private test stores;
it never uses the deployed hub's store. It exercises the original SDK acceptance,
real model matching, container replacement, and the offline backup/restore/rollback
procedures. The report is `verification/container-acceptance.json` and includes
image and input identities. A live Nemotron endpoint is required for the live cases.

The [web management console](web-console.md) provides authenticated health, information,
subscription and delivery observation, plus confirmed subscription management and
pending-job retries. It uses a separate administrator credential.

When qualifying an upgrade, include the original schema-1 and pre-console schema-2
runtimes with `tests/hub_acceptance.py --legacy-command JSON_ARGV
--previous-command JSON_ARGV`. These tests create real stores using each earlier
runtime and check the current service preserves history, source-event retry
results, acknowledgements and pending matching jobs. Do not use a live store for
these tests. The administrator API suite runs with distinct disposable credentials.

Contextual queries and index jobs use schema 3; see [retrieval operations](retrieval.md)
for migration, replay, qualification and rollback. Answer synthesis uses a separate
optional evaluator described in [evidence queries](../user/querying.md). Optional
[OIDC](oidc.md) replaces administrator key sign-in only when explicitly selected.
