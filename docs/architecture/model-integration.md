# Initial model and A2A integration

The initial matcher is the user-selected Nemotron Deciffusion 8B v2.1 decision
model. “Jev-like” describes its role; a Jev account is unnecessary. The Elixir
hub will call a separately served model through a replaceable adapter.

## Verified inputs

The internal weights README, inspected at commit
`d80a66a22c7640bcaefd2d71ea04ad14541e1822`, supplies BF16 and NVFP4 checkpoints
and names `ghcr.io/pst2154/nemotron-deciffusion:8b-v2` as its serving image.
It mounts the selected checkpoint at `/models/checkpoint` and requires an NVIDIA
GPU. The BF16 checkpoint has now been downloaded and verified against the
repository SHA256 checksum. A private test service is running on the selected
GPU host, serving that checkpoint with dynamic FP8 quantization.

The [public serving implementation](https://github.com/pst2154/nemotron-deciffusion/tree/main/serving)
provides `/v1/systemone` for decisions and `/health` for readiness. Its
[adapter](https://github.com/pst2154/nemotron-deciffusion/blob/main/serving/app/adapter.py)
accepts state and typed questions. The hub can represent each subscription as a
yes/no relevance question about a publication and normalize its answer to a
relevance probability. The inspected scoring code returns the yes probability
under `answers.<question_id>.noul`. The live smoke checks confirmed this mapping
and the required request `model` field; exact requests and responses are retained
in `verification/deciffusion-smoke.json`.

The [scoring implementation](https://github.com/pst2154/nemotron-deciffusion/blob/main/serving/app/vllm_scoring.py)
explicitly reports `calibrated: false`. Treat returned probabilities as model
outputs to evaluate on project-update examples. Do not assume a Jev confidence
formula or claim demonstrated calibration.

## Serving validation

After the user-managed reboot, the selected host's NVIDIA kernel driver and
libraries agree on 595.99.02. Both host `nvidia-smi` and a GPU-enabled Docker
container successfully detected its RTX 4090 with approximately 23 GiB free VRAM.
It had approximately 135 GiB free root disk before installing the test runtime,
which resolved the earlier hardware/storage prerequisite.

The selected BF16 checkpoint is 16,979,144,720 bytes. Its SHA256 is
`f892562cfd1dcd0ac7d245e1790edf7ea0f3e78bd3427ced5468b8bd874eb1fc`, verified
in transit and again on the GPU host against the repository's `SHA256SUMS`.

The running container uses
`ghcr.io/pst2154/nemotron-deciffusion@sha256:494aac2d7af43b7a70234792623a510bf29045a45b3aa893bc3170108ded9cea`.
Its `start.sh`, `adapter.py`, `scoring.py`, and `vllm_scoring.py` byte hashes match
the public serving source at `763a66b4bef4ad94a0f63ec9a2d9ad1e56673a4a`.
This establishes correspondence for those inspected files, not a full image
reproducibility attestation.

The container is named `adhd-deciffusion-v21`. Its adapter listens on container
port 8770, published only at host loopback `127.0.0.1:18770`. Remote clients need
an SSH tunnel to that loopback address. The checkpoint is mounted read-only from
`~/.cache/adhd/deciffusion-v2.1/bf16` on the GPU host. No GitLab credentials were
written into that directory or the serving container.

Startup uses these settings:

```text
PORT=8770
DOWNLOAD_CHECKPOINT=0
MODEL_ID=Nemotron-Deciffusion-8B-v2.1
SERVED_MODEL_NAME=Nemotron-Deciffusion-8B-v2.1
QUANTIZATION=fp8
GPU_MEMORY_UTILIZATION=0.60
MAX_MODEL_LEN=8192
MAX_BATCHED_TOKENS=8192
MAX_NUM_SEQS=4
FLASHINFER_AUTOTUNE=0
COMPACT_OVER=0
```

The image is started with `--enforce-eager` and 2 GiB shared memory. Automatic
checkpoint downloading and long-input compaction are disabled. The live health
response reports an 8,190-token per-question prompt limit. Health returned
`ready: true`; GPU memory use was approximately 10 GiB after startup.

On the GPU host, inspect or stop/start this test service with:

```console
docker logs --tail 30 adhd-deciffusion-v21
curl --fail http://127.0.0.1:18770/health
docker stop adhd-deciffusion-v21
docker start adhd-deciffusion-v21
```

No driver repair or reboot was performed by the agent, and existing workloads
were not stopped. The user performed the reboot that resolved the mismatch.

### First relevance request

This request was accepted by the running SystemOne adapter:

```json
{
  "model": "Nemotron-Deciffusion-8B-v2.1",
  "state": {
    "publication": "I am changing the task API response to include a status field."
  },
  "questions": {
    "client_api_updates": {
      "type": "noul",
      "instructions": "Does the publication satisfy this subscription: API request or response changes that affect the client?"
    },
    "deployment_outages": {
      "type": "noul",
      "instructions": "Does the publication satisfy this subscription: production deployment failures or service outages?"
    }
  }
}
```

The API-change case returned 0.985936 for the API subscription and 0.003173 for
the outage subscription. The deployment-failure case returned 0.997199 for the
outage subscription and 0.798187 for the API subscription. Both ranked the intended
subscription highest and returned finite probabilities in [0, 1]. These are
independent subscriptions, not an exclusive routing choice: ranking alone does
not establish whether either item should be delivered under a production policy.

The relatively high API score on the outage case shows why representative data
and threshold evaluation remain necessary. These two smoke cases establish live
serving and response compatibility, not calibrated matching quality. The raw
observations and checkpoint/image identities are in
`verification/deciffusion-smoke.json`.

## A2A test peer

Start from the official [Hello World server and test client](https://github.com/a2aproject/a2a-samples/tree/main/samples/python/agents/helloworld).
The inspected sample commit is `6603ba3f2c31a7ef33e70b9d8b5b5f8be42ac9a3`;
its requirements pin `a2a-sdk==1.1.0`. Confirm and record the wire protocol version
when implementing the hub. This is a protocol fixture, not evidence of an
end-to-end hub test.

The hub-specific scenario will use two distinct agent identities: subscribe,
publish a project update, poll the matching delivery, acknowledge it, and query
the publication. It must also cover disconnection and server restart. A
deterministic matcher fixture can exercise queue mechanics; a separate real-model
run must establish semantic matching behavior.
