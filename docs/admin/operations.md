# Admin guide

[Project guide](../README.md) → administration

## Deployment contract

For profile 2, run one ADHD hub process owning its registry and all isolated
project stores, with one private Kafka service per server. Follow the
[event-service deployment guide](event-service.md) for model-free Compose and
Kubernetes packaging, optional models, security and recovery. The standalone
container commands below retain the historical host-networked compatibility path
and build lifecycle; they do not replace the Kafka application manifests. Store
data and the writable private configuration directory in operator-owned bind mounts
outside the image. Directory mounts support atomic hot configuration replacement. Never run two containers against the same store, including
during upgrades, recovery, or backup. An optional local model runs separately and needs a GPU; raw pub/sub and literal
search need no model. The hub container does not need GPU access or model weights.

The authoring defaults are Elixir, Make, and Linux. The exported artifact is
a portable Elixir source script, not a macOS executable or native BEAM closure.
Container packaging preserves that exact script and compiles its declared modules
once during the OCI image build using the pinned Linux runtime. At startup, the
loader verifies the source, compiler inputs, runtime anchors and complete module
cache before loading application modules and running the original CLI dispatcher.
A missing or changed cache fails startup; rebuild the image from admitted staging
inputs. Keep `/app` and `/runtime/adhd` in the image rather than mounting replacement
files over them. No additional compiler Flavor is required for this packaging path.
Linux runtime compatibility is independently checked by the container acceptance
suite. The Linux Flavor now owns the native authoring target and its lifecycle
evidence.

The image pins official Elixir 1.20.4 / OTP 29 Alpine by digest. The staging tool
requires passing project verification, checks the exported artifact hash, and produces a minimal build context with a
Dockerfile, hash manifest, and deterministic archive containing the script,
health probe, manifest, and all hub behavioral contracts.
It never sends the repository, configuration, stores, or checkpoint to Docker.
This is local OCI deployment packaging, not a registry publication or tagged
Literate AI native-package release.

For the legacy standalone run.sh path, use Linux Docker Engine with host networking. That path binds the listener to `127.0.0.1`. The profile-2 Compose/pod listener
may use `0.0.0.0` behind the private deployment ingress. There is no `-p` mapping:
host networking shares the host's network namespace. The matcher URL's loopback
address consequently refers to the Docker host. Docker documents this behavior
in its [host networking guide](https://docs.docker.com/engine/network/drivers/host/).
Docker Desktop host networking is not validated by this project.

The application includes a [local GPU model service](model-service.md) with a
pinned Docker Compose deployment and checkpoint verification. Start it before
checks that use semantic filtering or model-backed search.

## Runtime and dependency licenses

ADHD source is [Apache-2.0](../../LICENSE). The historical compiled05 inventory uses
`elixir:1.20.4-otp-29-alpine@sha256:f1a8c06b332cacc7239381a25331a807fb63962f8221dff545ea4d8f78b0f50c`.
Its recorded runtime is Elixir 1.20.4, OTP 29.1.2, Rebar3 3.27.0,
Alpine 3.24.2-r0 and musl 1.2.6-r2. The
[dependency audit](../../verification/compiled05-dependency-license-audit/audit.json)
binds these versions, the compiled-image admission and exact upstream Elixir/OTP
license references. Event transport uses OTP `inets`/`httpc`, SSL and crypto;
it adds no Hex/Mix Kafka library. The current source41 candidate retains the same
three third-party base layers and runtime environment, as checked by the
[source/module conservation review](../../verification/ownedMULTI008/source41-remaining-scope-review/review.json).
Its changed application/cache layers are separately bound by the
[source41 image audit](../../verification/ownedMULTI008/source41-compiled-image-positive/audit.json).
This conservation carries the recorded dependency inventory forward, not a new
legal-clearance or full-transitive-license claim.

The [actual image inventory](../../verification/compiled05-dependency-license-audit/actual-image-inventory.json)
retains the APK database hash and all 24 package records with their declared
licenses. These include GPL, LGPL, MIT, Apache, MPL, BSD, X11 and Zlib terms;
the virtual `.erlang-rundeps` package has no declared license field. The hub's
Apache license does not replace these package terms. The archive inspection found
`app/LICENSE` as its conventional license/notice filename; it did not establish a
complete third-party notice or source-offer bundle. Package declarations and file
hashes provide traceability, not legal clearance or a complete transitive BOM.

The same audit distinguishes host SDK/browser/OpenRig qualification tools from hub
runtime dependencies. Kafka/REST Proxy terms are in the
[event-service inventory](event-service.md#artifact-and-license-inventory), and
optional serving code, checkpoint weights and CUDA/base terms are in the
[model-service inventory](model-service.md#dependency-and-license-inventory).

## Build and transfer

On the supported authoring host, with the pinned Literate AI installation and
Elixir/OTP toolchain:

```bash
litai build components/hub --update-receipt
litai verify
python3 scripts/stage_container.py
```

The pinned framework currently rejects `operator-retained-source` when exporting
an admitted cache entry (`unsupported accepted-source coding CLI selection`;
BUILD-001). For a qualified retained-source rebuild, preserve its JSON result and
run independent acceptance, then stage with the evidence-bound route:

```bash
python3 scripts/stage_container.py --rebuild-result _build/federation/qualify.log \
  --acceptance-report verification/federation-regression.json \
  --output _build/container
```

This route requires a passing rebuild bound to the current receipt and checks the
artifact bytes against independent acceptance. Refresh the rebuild result after
authority changes. It does not manufacture a framework export or change provenance.

The context includes every normative file in the current hub lock, including
`specification/project-recovery/interface.schema.json`; each payload must match
its locked SHA256. Missing, redirected, duplicate or changed inputs fail before
the context is written. Existing top-level specification aliases remain available.

If the default `litai` on PATH differs from the project-pinned installation, select
the reviewed interpreter and entry script explicitly with
`--litai-command '["/absolute/python","/absolute/litai"]'`. This changes only the
verifier invocation; current receipt and artifact checks still apply. The staging
acceptance harness accepts the same option.

The output directory must be new; choose `--output _build/container-next` for
another staging run. A stale hash fails staging. A changed specification requires
the rebuild procedure in [source setup](../user/getting-started.md).

Use a current Docker Engine with BuildKit. Staging normalizes archive ownership,
timestamps, and permissions; the build command fixes image timestamps and disables variable
provenance attestations. Record the image ID and input manifest. The
[current source41 compiled-image comparison](../../verification/ownedMULTI008/source41-compiled-image-positive/audit.json)
records identical image configuration and filesystem layer identities from two
independent sequential builds, both without build cache or network access. The
[earlier comparison](../../verification/container-precompile-image40/reproducibility-first-negative/manifest.json)
reproduced the final cache bytes but differed in intermediate layer metadata and
remains a failed reproducibility result. The positive result covers the exact
pinned amd64 builder and context; it does not establish identical images across
different CPU architectures, compiler versions or Docker versions. The [earlier compiled05 positive](../../verification/container-precompile-image40/reproducibility05-positive/manifest.json)
retains its original image/context scope. Current
[cache17](../../verification/container-cache41-positive/audit.json),
[scalar observer ABI19](../../verification/ownedMULTI008/source41-image-abi-positive/audit.json)
and [core13/94](../../verification/ownedMULTI008/source41-core13-positive/audit.json)
are separate gates: cache validation and observer compatibility do not by themselves
prove recovery or application durability. See Docker's
[reproducible build guidance](https://docs.docker.com/build/ci/github-actions/reproducible-builds/).

Transfer the staged directory and `deploy/run.sh`, `scripts/configure_hub.py` to
the Linux host. Preserve their relative paths and run the remaining commands on
that host, as a non-root account with Docker access. This host-networked runner
also needs its dedicated Kafka/REST service ready first; the
[native quickstart](../user/getting-started.md#private-configuration) shows the
loopback-only backend setup. Select the actual private REST origin explicitly:

```bash
docker build --build-arg SOURCE_DATE_EPOCH=0 --provenance=false -t adhd-hub:local _build/container
docker image inspect adhd-hub:local --format '{{.Id}}'
python3 scripts/configure_hub.py --directory .adhd/container \
  --eventing-rest-url http://127.0.0.1:18082
sh deploy/run.sh .adhd/container/hub.json .adhd/container/data
curl --fail http://127.0.0.1:8766/health
```

For a different port, project, or matcher URL, pass `--port`, `--project-id`, or
`--matcher-url` to the configuration tool. An existing configuration directory is
never overwritten. The defaults create two identities, `agent-a` and `agent-b`,
with distinct random tokens, plus local user `admin` with a random password saved
in `initial-admin-password.txt`. Files have mode 0600 and their directory is 0700.
Sign in at `/admin`, complete the name/email profile, and use Users, Agents and
Settings for subsequent configuration. Complete the
[first-use Recovery review/apply](web-console.md#first-use-project-initialization)
for each new project before publishing; a ready global health endpoint alone does
not establish project storage availability.

The runner requires Linux `realpath`, Python 3, an available configured port, and
writable configuration/data directories owned by the invoking account. It can
bootstrap a missing configuration file in an existing private directory. It
runs with that account's UID/GID, a read-only root filesystem, dropped capabilities,
no new privileges, bounded logs, and a writable temporary filesystem. It sets
limits of 512 MiB memory, two CPUs, and 128 processes. Adjust these limits in the
deployment recipe when workload measurements require it. The default container
name is `adhd-hub`; optional third and fourth runner arguments select name and image.

## Configuration and credentials

The server file is `.adhd/container/hub.json`. Its important fields are:

| Field | Purpose |
| --- | --- |
| `server_id` | Stable server identity shared by its projects |
| `projects` | Stable project IDs, display names, lifecycle status and optional settings overrides |
| `project_id` | Optional legacy default selector; new multi-project clients select a project explicitly |
| `agent_projects` | Explicit project admissions for each agent |
| `host`, `port` | Private listener and available TCP port; use loopback for the legacy host runner |
| `public_url` | Base URL advertised in discovery; must be reachable by clients |
| `store_path` | Storage anchor; the durable registry selects each project's active generation and must be retained with its route files |
| `agents` | Agent ID to distinct bearer-token mappings, at least 24 characters each |
| `matcher` | Optional decision model; null leaves raw subscriptions and literal fact search operational |
| `matcher.url`, `matcher.model` | Configured SystemOne endpoint and model identifier when filtering is enabled |
| `matcher.timeout_ms`, `matcher.retry_ms` | Inference timeout and background retry interval |
| `threshold_ppm` | Match policy, initially 900000; needs workload calibration |
| `federation` | Optional trusted peers, approved project description and publication export allowlist; see [federation setup](../user/federation.md) |
| `auth` | Local/OIDC/both mode, explicit legacy-key policy, session lifetime and OIDC provider/group mappings |
| `users`, `agent_owners` | Stable user profiles, one role per user and agent ownership, managed in Users/Agents |
| `eventing` | Per-server Kafka REST transport, topic policy, retention, trust/credentials and backlog bounds |
| `resources` | Shared and per-project work capacity |
| `recovery` | Hot backup-root and bounded recovery work settings |
| `config_revision` | Server-owned conflict-control revision |

On first use, confirm Kafka readiness and complete
[Admin project initialization](web-console.md#first-use-project-initialization)
for every `uninitialized` registered project before sending data. Registration,
agent membership and global `/health` readiness do not create/admit a store. A
known `recovery_required` target needs verified recovery, not empty initialization.

Give each agent only its `.adhd/container/agent-a.json` or `agent-b.json` client
file. It contains that agent's token and the URL, without the other identities.
Transfer it privately and keep it out of logs, chat, and version control. For
credential rotation and all hub setting changes, use the live Admin forms in
[Web console](web-console.md). Update affected clients when credentials or URLs
change. The runner mounts the whole private directory so atomic file replacement
remains visible. No hub restart is needed except to change the configuration-file
location; software upgrades still require replacing the runtime. Removing an identity does not erase its historical publications or inbox.

Remote agents need a private tunnel or an operator-managed TLS proxy. For a tunnel,
set `public_url` to the URL used on the client side and forward that client port
to the service host's loopback port. Restrict tunnel/proxy access and require the
hub bearer token. The plain HTTP listener must stay private. The product does not
provision proxies, TLS certificates, or network-wide authentication.

## Model connectivity

For optional model filtering, the local Nemotron deployment listens on the Docker
host at port 18770. Check it independently before enabling the model:

```bash
curl --fail http://127.0.0.1:18770/health
```

If the model runs elsewhere, configure a reachable private endpoint or keep an SSH
tunnel open on the Docker host as described in [source setup](../user/getting-started.md#optionally-connect-the-decision-model).
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
publish-to-delivery path. Use Admin Overview for counts and matcher health, and Activity for delivery,
matching-job and federated-query status. Avoid putting bearer tokens in diagnostic output.

## Backup and restore

Local upgrades validate historical schema1..3 checkpoints and snapshots before
creating a new active generation. Supported historical modes0600,0640,0644,0660
and0664 are accepted only for regular, singly linked files owned by the running
server, without symlink path components. The hub keeps original bytes, permissions,
inodes and existing rollback backups unchanged; the adopted generation is private.
This does not change the strict private-file requirements for imported backups.

Pre-federation schema1 and schema2 stores can lack a server ID. After validating
the complete historical state, the hub chooses one ID and retains it through
migration and restart. A malformed or conflicting ID, or a missing ID in schema3
or later, is rejected. A schema4 generation requires its matching registry and
recovery metadata; use whole-server recovery when those files have been lost.

Each store has a matching `.snapshot` recovery file. Keep the checkpoint and
snapshot together: startup rejects conflicting generations rather than rolling
back acknowledged data. A valid snapshot recovers an interrupted DETS write; it
does not authorize silently resetting an unrelated corrupt store.

For profile2.1, follow the complete
[Kafka/server recovery-set procedure](event-service.md#recovery-backups-and-upgrades),
including registry/marker/recovery sidecars, every selected project generation and
Kafka state. The directory-copy example below is the historical standalone
storage path; it is not by itself a complete profile2.1 recovery set.

Take an offline backup; do not copy a live DETS file. Stop every process using the
store and save both the data directory and the matching private configuration:

```bash
docker stop --time 30 adhd-hub
umask 077
ADHD_BACKUP_DIR=".adhd/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ADHD_BACKUP_DIR"
cp -pR .adhd/container "$ADHD_BACKUP_DIR/config"
docker inspect adhd-hub --format '{{.Image}}' > "$ADHD_BACKUP_DIR/image-id.txt"
docker start adhd-hub
```

The recorded ID identifies the running image even if its tag has changed. Protect and retain backups
according to project data requirements. Store client credentials privately as
needed; the server backup contains all server credentials and the initial-password
file. Include configuration sidecars/replay journals. If Settings moved a store
outside this directory, back up that configured location too before restarting.

To restore, first verify the backup is complete and readable. Stop and remove
the container while preserving current data for rollback:

```bash
docker stop --time 30 adhd-hub
docker rm adhd-hub
mv .adhd/container .adhd/container-before-restore
cp -pR "$ADHD_BACKUP_DIR/config" .adhd/container
sh deploy/run.sh .adhd/container/hub.json .adhd/container/data adhd-hub adhd-hub:local
curl --fail http://127.0.0.1:8766/health
```

Use the backed-up image ID as the final argument if its format differs from the
current image. Ensure restored files retain ownership suitable for the runtime
UID. Verify identity, known publications, pending deliveries, and acknowledgements
through the SDK. Restoring intentionally returns to the backup point: later
publications and acknowledgements are absent. To undo the restore, stop/remove
the container, move the restored directory aside, put
`.adhd/container-before-restore` back at `.adhd/container`, and run the old image.
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


Archive questions have separate planner, retrieval, original-assessment, fallback
scan and audit budgets. Settings exposes every field, including audit rate and
History endpoint inheritance. Inspect actual stage costs, child runs and sampling
population in Activity; cancellation fences direct work and active children.
See [archive questions](../user/archive-queries.md). Keep partial/failed audits
visible; they do not provide negative labels for future tuning.
