# Local decision model service

Run the selected Nemotron Deciffusion 8B v2.1 SystemOne adapter with
[model.compose.yaml](../../deploy/model.compose.yaml). The image is pinned by
digest; weights are mounted separately and are never included in the hub image.
The service publishes only `127.0.0.1:18770`. Linux host-networked hub containers
can use `http://127.0.0.1:18770/v1/systemone` as `matcher.url`.

## Dependency and license inventory

The [scoped optional-model inventory](../../verification/ownedMULTI008/optional-model-dependency-license/manifest.json)
binds the running pinned image, checkpoint revision and hashes, 17 selected
installed components and 114 supplied legal-file hashes. Model weights remain an
operator-supplied external artifact and are excluded from the hub image. The
hub's Apache-2.0 license and the serving-source license do not grant rights to all
weights, CUDA components or base-image packages.

The serving source at commit `763a66b4bef4ad94a0f63ec9a2d9ad1e56673a4a` supplies
an [Apache-2.0 license](https://raw.githubusercontent.com/pst2154/nemotron-deciffusion/763a66b4bef4ad94a0f63ec9a2d9ad1e56673a4a/LICENSE).
Four actual serving files match that source revision byte for byte; this is not
whole-image build reproducibility. The checkpoint at revision
`d80a66a22c7640bcaefd2d71ea04ad14541e1822` has BF16 weights SHA-256
`f892562cfd1dcd0ac7d245e1790edf7ea0f3e78bd3427ced5468b8bd874eb1fc`.
Its pinned README declares “NVIDIA Nemotron Open Model License (same as v2).”
The tracked checkpoint supplies no full license text, specific license version,
standalone NOTICE or separate model card. That declaration is recorded as supplied;
a currently published license is not substituted for the missing version. One
configuration Python file carries an Apache-2.0 header, which describes that
source file rather than the whole checkpoint. Obtain the checkpoint through your
authorized source and retain its supplied terms with your installation.

The serving image's recorded base is Ubuntu 24.04.3 LTS. Its shipped
`/NGC-DL-CONTAINER-LICENSE`, selected Ubuntu copyright files and CUDA runtime
wheel EULA are hash-bound in the inventory. The `nvidia-cuda-runtime` 13.0.96
wheel declares `LicenseRef-NVIDIA-Proprietary`; those terms are separate from the
Apache-2.0 serving code. Installed vLLM, Transformers and FlashInfer declare
Apache-2.0; Torch records a mixed license expression. Triton and safetensors have
retained license files despite empty metadata fields. Tokenizers has no license
metadata field or distinct license file in the inspected package location, and
FlashInfer JIT cache declares Apache-2.0 without a distinct legal file there.
The detailed inventory preserves these unknowns and raw declarations.

This inventory covers the observed top-level components and supplied legal
materials. It provides neither a complete transitive Python/CUDA/OS/GPU-driver BOM
nor redistribution clearance. Public vLLM build labels are retained provenance,
not an independently reconstructed immutable base-image identity. See the
[hub runtime inventory](operations.md#runtime-and-dependency-licenses) for the
separate CPU-only hub package.

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

## Combined profile-2 candidate check

The [candidate live-model report](../../verification/multi-eventing/live-model-26.json)
binds native artifact `b6c17ba3121cd1f6b8a7adaef82b44c736bfd1d4010d8938aacb4c961f2f282a`
and its independent harness. Real Nemotron responses accepted an explicit breaking
API removal and rejected an unrelated lunch announcement at threshold 900000; the
observed two decision latencies were 137 ms and 88 ms. Raw Kafka subscribers
received both originals, a second project progressed without inference, and hot
model removal preserved raw progress and literal search. A semantic history query
cited the positive original and denied lookup through the other project. The
[bounded relay observations](../../verification/multi-eventing/live-model-26-gateway.json)
retain typed replies and request hashes, without raw prompts or credentials.
This small synthetic-input check uses the existing model container; it is not a
general accuracy/latency guarantee or final retained-build qualification.

The [later candidate check](../../verification/multi-eventing/live-model-28.json)
also kept the filtered subscription while the model was disabled, accepted a new
breaking-change publication with zero inference during the pause, and delivered
that publication once after re-enabling. Its original two classification calls
took 111 ms and 90 ms. The report binds candidate `31f33131ba3b6cf0f0ad30c2df0560e2175e8a4e78804017a236da91bb345615`
and its exact harness; [relay observations](../../verification/multi-eventing/live-model-28-gateway.json)
include the later resumed classification and semantic query. Final retained-image
qualification remains a separate gate.

The admitted OTP29 container was subsequently exercised on both platforms:
[Compose model evidence](../../verification/kafka-platform/compose-accepted-model.json)
and [Kubernetes model evidence](../../verification/kafka-platform/kind-accepted-model.json).
Their parent platform manifests bind each external model check to the exact
accepted artifact and actual running image. Each records all six provider POSTs,
including scoped semantic history and the resumed filtered subscription after hot
model re-enablement. These authored workload checks do not imply general calibration,
latency guarantees or qualification of GPU hardware beyond the tested host.

The [current source41 deployed-model gate](../../verification/ownedMULTI008/source41-deployed-model-positive/audit.json)
passes both complete Compose and Kind programs against the actual packaged runtime:
eight outer reported checks, with inner typed filter and semantic-search gates.
Each platform made six provider POSTs (12 total), covering filtered match/nonmatch,
model disable/resume, cited backend history search, separate raw progress and
foreign/private canary exclusion. Actual compiled VM custody, unchanged protected
model identity, released cooperative lease and strict cleanup are retained.
The [older compiled05 launcher143/false result](../../verification/ownedMULTI008/compiled05-deployed-model-terminal/manifest.json)
remains historical evidence and is not rewritten by this positive run. This fixed
synthetic corpus is not general semantic accuracy or latency calibration, a fresh
optimizer benchmark, or a full-transitive/legal-clearance inventory. Full current
Kafka14/recovery25 and final documentation-authority review remain separate gates.
