# Deploy managed ACME listeners

Use an admitted Linux amd64 image containing the reviewed immutable Lego/guardian
bundle. These optional templates expose listeners; they do not enable TLS, accept
issuer terms or select domains automatically. Follow the [operator guide](../../docs/admin/acme.md)
for public Admin setup, DNS, challenge routing, issuer trust and renewal controls.

For Compose, keep the existing private seed/data mount setup, then use:

```
docker compose -f deploy/app.compose.yaml -f deploy/app.acme.compose.yaml up -d
```

The overlay adds TCP80→8080 (token-only HTTP-01) and TCP443→8443 (native TLS).
The base mapping for HTTP8766 remains loopback-only. Do not expose8766 as a public
fallback. If a reverse proxy already owns80/443, omit this overlay and configure
that proxy's equivalent token route/TCP forwarding explicitly. Merely forwarding
public8080 does not satisfy public HTTP-01 validation. Preserve the original
`Host` header and exact challenge path when proxying; forwarded host headers are
not trusted as a replacement.

For Kubernetes, select the admitted immutable image in the base kustomization as
usual, inspect `kubectl kustomize deploy/k8s/acme`, then apply that directory. It
retains the original single-writer Deployment/PVC/security settings and adds a
LoadBalancer Service for only80/443. The provider must forward TCP to the named
ports; this template does not terminate TLS, create DNS records or claim enforcing
NetworkPolicy. Keep the base hub ClusterIP/private access boundary for8766.

The base Kubernetes template sets `ERL_FLAGS="+S 2:2 +Q 65536"`. Keep this
bound when adapting the template: an extremely high inherited descriptor limit
can otherwise make Erlang allocate its port table beyond the 1 GiB container
limit before the hub starts. The bound does not change certificate or listener
settings.

The overlay and Service use the default internal listener ports, 8080 and 8443.
If an Admin changes either listener port, update the corresponding Compose mapping
or Kubernetes port/Service target as well. Hot application settings do not rewrite
deployment manifests or external forwarding rules. Keep a private Admin repair
connection available while changing these routes.

In both deployments, retain the entire durable configuration mount across hub
replacement. The config-adjacent `acme/` directory contains private account keys,
certificate generations, scheduler state, retry floors and owner locks; preserve
its0700 directories/0600 files and the adjacent ACME initialization witness. Include
it in stopped server backups. Project-only backups do not contain these server
credentials. Mount private issuer trust read-only where explicitly configured;
never mount over `/runtime/adhd` or replace packaged executables. HTTP-01 tokens
are transient and never become a general static-file or application endpoint.

Build preparation uses `scripts/build_acme_client.py` with pinned source/Go
archives, exact patched-source hashes and an offline module cache;
`scripts/build_acme_musl.py` and `scripts/build_acme_guard.py` bind the static
guardian compiler inputs. `scripts/package_acme_tools.py` retains actual Go
build-info/module notices and emits a candidate pin update for review. Staging
requires `scripts/stage_container.py --acme-tools BUNDLE` alongside the ordinary
verified artifact arguments. Missing tools fail staging for ACMEClient artifacts.
Native source-tree binary fixtures are diagnostic assets, not a production
installer or a substitute for actual packaged-image ACME qualification.

Qualification uses the admitted Linux amd64 image with real isolated-CA issuance,
manual and scheduled renewal, and replacement retaining the same certificate and
private account. [Whole Compose and whole Kind checks](../../verification/acme/final-composition/manifest.json)
were observed separately; the earlier combined matrix remains false. The Kind
scope uses its local-path volume and NodePort forwarding, without a provider
LoadBalancer, general CSI/CNI, broker or model qualification. A temporary host
inotify ceiling used for the disposable Kind test was restored after cleanup.
Public issuer staging remains a separate owned-domain/network validation.
