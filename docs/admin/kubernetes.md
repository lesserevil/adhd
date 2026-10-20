# Kubernetes deployment

[Project guide](../README.md) → [Operations](operations.md) → Kubernetes

`deploy/k8s/adhd.yaml` runs one accepted ADHD image and an nginx proxy in the
`adhd` namespace. The NodePort is **30866**, forwarding to the proxy on port 8768.
The hub itself listens on `127.0.0.1:8767`. Both containers share the selected
node's network namespace, so the existing matcher at
`http://127.0.0.1:18770/v1/systemone` remains reachable. The proxy binds to the
node address selected when rendering the manifest and preserves the original Host,
Authorization, Origin and A2A headers. Existing bearer authentication applies.

This deployment uses plain HTTP on a private node address. Use the private network
or a tunnel; add a TLS terminator before using it over an untrusted network.
The proxy's node-address port 8768 is also reachable on that private address.
The anonymous console shell, health route and Agent Card are public; project data
requires agent or administrator credentials. See [the web console](web-console.md).

## Storage and placement

The Deployment uses one replica and `Recreate` updates to keep one writer per
store. A `local-path` PersistentVolumeClaim holds `/data/hub.dets`; configuration
is mounted read-only from Secret `adhd-config`. The pod runs without root,
capabilities or a service-account token, with a read-only root filesystem and
bounded writable temporary directories. Runtime resources are limited.

This is a node-bound deployment: the imported images, local-path data, and local
matcher depend on the selected node. It does not provide automatic failover.
The 1 GiB storage request does not establish a filesystem quota for local-path
storage. Monitor actual disk usage and back up the store. Never scale above one
replica or run a separate process against this PVC. Deleting the PVC or namespace
can delete its local-path data; scaling the Deployment to zero preserves it.

The Kubernetes instance starts with its own store and fresh credentials. It does
not migrate or share the existing Docker instance's store or credentials.

## Prepare and apply

Use a kubeconfig authorized for the intended cluster. On this host the admin
kubeconfig is `/etc/kubernetes/admin.conf`, accessed through
`sudo kubectl --kubeconfig=/etc/kubernetes/admin.conf`. Do not disable TLS verification.
The commands below assume `kubectl` already uses the intended kubeconfig.

Verify that `local-path` storage is available, the selected node has a working
matcher on port 18770, and ports 8767, 8768 and NodePort 30866 are available.
The manifest pins the existing accepted hub and proxy images and uses
`imagePullPolicy: Never`; import them into that node's containerd `k8s.io` namespace
before applying:

```bash
docker save adhd-hub:name-mvp nginx:1.27.4-alpine -o /path/to/adhd-images.tar
sudo ctr -n k8s.io images import /path/to/adhd-images.tar
sudo ctr -n k8s.io images tag docker.io/library/adhd-hub:name-mvp docker.io/library/adhd-hub@sha256:d665a77c58d70ba112d596473bb6abeca8b880fb81ec06210ec710807ae7e864
sudo ctr -n k8s.io images tag docker.io/library/nginx:1.27.4-alpine docker.io/library/nginx@sha256:4ff102c5d78d254a6f0da062b3cf39eaf07f01eec0927fd21e219d0af8bc0591
```

The hub image and artifact identities match `verification/name-acceptance.json`.
This deployment reuses those accepted bytes; it does not claim a fresh framework
build or refresh an authority-bound runtime-test receipt. A new implementation
requires its own accepted image, updated manifest identities, and deployment checks.

Create private configuration in a new ignored directory. Replace `NODE_IP` with
the selected node's reachable private address:

```bash
python3 scripts/configure_hub.py --directory .adhd/k8s --project-id adhd \
  --port 8767 --public-url http://NODE_IP:30866
```

Render the two manifest placeholders without shell-expanding nginx variables:

```python
from pathlib import Path

node = "NODE_NAME"  # kubernetes.io/hostname label of the selected node
address = "NODE_IP"  # node's Kubernetes InternalIP, used by readiness probes
template = Path("deploy/k8s/adhd.yaml").read_text()
rendered = template.replace("${ADHD_NODE}", node).replace("${ADHD_BIND_IP}", address)
Path(".adhd/k8s/deployment.yaml").write_text(rendered)
```

Create the namespace and secret once, then validate and apply:

```bash
kubectl create namespace adhd --save-config
kubectl -n adhd create secret generic adhd-config --from-file=hub.json=.adhd/k8s/hub.json
kubectl apply --dry-run=server -f .adhd/k8s/deployment.yaml
kubectl apply -f .adhd/k8s/deployment.yaml
kubectl -n adhd rollout status deployment/adhd --timeout=120s
curl --fail http://NODE_IP:30866/health
```

The private `.adhd/k8s/admin-token.txt` signs into the console at
`http://NODE_IP:30866/`. Give each agent only its own `.adhd/k8s/agent-a.json` or
`agent-b.json`; do not share `hub.json`. Protect Kubernetes Secret read access as
carefully as these local files. Credentials are not included in the manifest.

## Observe, update and recover

```bash
kubectl -n adhd get pods,pvc,service -o wide
kubectl -n adhd logs deployment/adhd -c hub --tail=50
kubectl -n adhd logs deployment/adhd -c proxy --tail=50
```

Verify authenticated `whoami`, publication retrieval, pending deliveries, and
administrator `overview`; health alone does not establish matcher availability.
Qualify a deployment with real publish-to-match delivery and a pod replacement
that preserves publication IDs, pending delivery IDs, and acknowledgements.
`verification/kubernetes-acceptance.json` records the current deployment checks.

Before upgrades or backups, scale the Deployment to zero and wait for its pod to
terminate before copying the complete data directory. Upgraded schema-3 runtimes
require the matching DETS image and `.journal` recovery file together. Save the matching private configuration
and image identity with an offline backup, as in [Operations](operations.md).
Restore only to a stopped store and preserve the current store for rollback.
After startup, verify known publications and agent inboxes. No automated
Kubernetes backup/restore qualification is claimed here.

After changing the Secret or proxy ConfigMap, restart the Deployment; the service
reads configuration at startup and nginx does not automatically reload it:

```bash
kubectl -n adhd rollout restart deployment/adhd
kubectl -n adhd rollout status deployment/adhd --timeout=120s
```

To stop without deleting data, run `kubectl -n adhd scale deployment/adhd --replicas=0`.
Resume with `--replicas=1`. Keep the PVC, Secret and private credential files.
