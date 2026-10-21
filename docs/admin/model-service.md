# Local decision model service

Run the selected Nemotron Deciffusion 8B v2.1 SystemOne adapter with
[model.compose.yaml](../../deploy/model.compose.yaml). The image is pinned by
digest; weights are mounted separately and are never included in the hub image.
The service publishes only `127.0.0.1:18770`. Linux host-networked hub containers
can use `http://127.0.0.1:18770/v1/systemone` as `matcher.url`.

## Host and checkpoint setup

Use a Linux Docker host with Compose, an NVIDIA GPU, a working driver and NVIDIA
Container Toolkit CDI support. The tested A40 has 48 GiB VRAM. The default is BF16,
60% GPU memory utilization, 8,192 tokens and four concurrent sequences. Reserve
32 GiB host RAM and sufficient disk for both the large image and checkpoint.
Other hardware needs separate qualification.

Follow NVIDIA's [toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
and [CDI guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html).
For Docker with native CDI enabled, `nvidia-container-toolkit-base` is sufficient.
Verify devices with `nvidia-ctk cdi list`; if necessary generate the description
with `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`. Verify container
access before loading the model:

```console
docker run --rm --device nvidia.com/gpu=0 ubuntu:24.04 nvidia-smi
```

Obtain the approved checkpoint using your existing authorized GitLab access.
Use the exact repository and revision in
[model integration](../architecture/model-integration.md), checking out
`d80a66a22c7640bcaefd2d71ea04ad14541e1822` and fetching Git LFS files under `bf16/`.
The checkpoint includes executable model code: keep all configuration, tokenizer
and Python files from that reviewed revision. Do not substitute unreviewed files.
The selected BF16 `model.safetensors` SHA-256 is
`f892562cfd1dcd0ac7d245e1790edf7ea0f3e78bd3427ced5468b8bd874eb1fc`.

## Start and operate

Run as the non-root account that can read the checkpoint and use Docker:

```console
python3 scripts/model_service.py /absolute/path/to/checkpoint/bf16
curl --fail http://127.0.0.1:18770/health
```

The helper verifies the weights hash and required companion files before starting
Compose, sets the container UID/GID to your account, and waits up to 15 minutes
for readiness, then sends a real typed inference request to exercise first-use
kernel compilation. `--verify-only` checks the checkpoint without starting a service.
Weights must be readable by that UID. No download token enters the container.
Startup can take several minutes; `/health` returns 503 until the engine is ready.
The read-only root has bounded writable scratch with execution enabled for Triton
compiled kernels, a read-only checkpoint mount,
bounded logs, no additional capabilities and automatic restart.

Set `MODEL_GPU` to another CDI device index or UUID, or `MODEL_PORT` to another
loopback port before invoking the helper. GPU memory utilization applies to the
selected GPU's total memory; leave room for other host workloads.

For subsequent administration, use the same Compose file and checkpoint path:

```console
export MODEL_CHECKPOINT=/absolute/path/to/checkpoint/bf16
docker compose -f deploy/model.compose.yaml ps
docker compose -f deploy/model.compose.yaml logs --tail 100 model
docker compose -f deploy/model.compose.yaml down
```

Stopping this service leaves the checkpoint on disk. Hub matching and federation
evaluation jobs remain durable and retry until their own deadlines. Keep this
unauthenticated model endpoint on loopback; use authenticated private tunneling
when a hub runs on a different host.


Probe typed relevance after readiness with:

```console
python3 tests/model_acceptance.py
```

This writes `verification/model-service.json` with actual model probabilities.
It is a serving smoke test, not workload-wide calibration evidence. The federation
and existing A2A suites exercise model integration through the hub.
