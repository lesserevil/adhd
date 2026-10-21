# Multi-project federation and event controls qualification

Native candidate qualification on 2026-10-21 passed the independent
[federation harness](../../tests/federation_multi.py) (14 groups, 273 schema-validated
wire messages) and [event controls harness](../../tests/eventing_controls.py)
(8 groups). This is evidence for the named candidate, not a retained-source
release or semantic model-quality attestation.

| Evidence | SHA-256 |
| --- | --- |
| Native candidate `hub-controls-13.exs` | `aabfcf968501260d912b27109c31819c69f4eaf74fe6fc755040a87bc6734ca1` |
| Federation report `_build/roadmap/multi/federation-13.json` | `75d64a368a3148e2e7e99e63cb82b9ec7c332e8b1ae63af1a04933ab42607b4d` |
| Controls report `_build/roadmap/multi/controls-13.json` | `98acbfe0b80f7f843d6e22a051baaa78274cf1b8f0898d40399f006f7d417a8d` |
| Federation harness at execution | `4544718021de73f2ea36a79c8524fd6215109be3b338932d95a9465b896d1ba6` |
| Controls harness at execution | `79b4ee52f30ecbccf88e97a092506bf5d6a397cf8ca5aca58312200bfae3db9f` |
| Accepted legacy candidate `index-hub-21.exs` | `1d3459aab65c295b8edb988dbf7bf716ecece78e9e7e7062ec19312984ee7d48` |

The ignored evidence directory contains the exact source-input manifest
`controls-13-source.json`, private fixture logs/stores/configuration, reports and
broker container/image identity capture `federation-brokers.json`. Private fixtures
and generated source are deliberately not checked in.

Three actual multi-project server processes used distinct pinned Kafka/REST Proxy
8.3.2 services with cluster IDs `MkU3OEVBNTcwNTJENDM2Qk`,
`NEiAAXk0v1xqZFCdSDoQjA`, and `Xle2vV-sRlSWjarQJq3IFw`. Their project IDs and display
labels deliberately collided; server IDs were fresh per run to isolate broker
history. The suite observed four distinct remote server/project answers, exact
query namespaces, bounded authorized aggregate catalog pages, local/remote
canonical routing, duplicate ownership conflicts, hot grant revocation and hard
restart. A separately executed accepted legacy binary queried the new default
project and was queried by it. Archived legacy routes exported an empty catalog
and returned HTTP403 for new work. Credential scans covered all project stores.
Raw Kafka-to-A2A delivery required zero model inference; later semantic queries
used 15 controlled typed requests. No real-model accuracy or latency claim follows.

The controls suite used a forwarding gateway to an actual Kafka service. It
proved acceptance-time model URL/model ID/threshold retention across a hot change
while the broker was blocked; explicit replay of retained pre-cutover originals;
late-subscriber replay without changing ordinary activation; exact request
idempotency; acknowledged delivery preservation; atomic refusal under configured
backpressure; digest/checkpoint guarded quarantine retry and audited physical
skip; and republishing the original after corrupting its actual producer record.
Audit, replay status, accepted control identity and acknowledgements survived a
hard process restart. Archiving rejected new replay while preserving the accepted
control's idempotent result.

These profiles used HTTP Kafka transport. They do not qualify custom-CA/OAuth
security, replicated Kafka durability, Kubernetes, live-model quality or the final
retained build. HTTPS trust-isolation changes following this candidate require
separate deployment qualification. All private server processes were stopped.
The extra broker on port 18086 was removed; port 18085 cleanup ownership passed to
the OpenRig qualification worker, and the preexisting port 18082 service remained.

## Completion audit candidates

A later bounded audit qualified Admin edit/pause/resume, exact revision/message-ID
retries, model-pending work and acknowledgement preservation, real Developer/Viewer
denial, live membership/archive fencing, and pagination over 106 subscriptions.
`hub-contract-audit-27.exs` SHA256
`423a1de693782489a8c8ef648341bf4b73a782995c744ff3a913c5320ac20c9e`
passed four independent Admin groups; report `audit-27-admin-edit.json` SHA256
`aafb9dcc1f2b95a3feb5ff051b3d3c177609b3557849f1966f8c4feddd5ea0d8`.

The same candidate passed four real-Kafka per-project policy groups, including a
second-project preflight failure leaving the first topic's actual retention
unchanged, a fetched record held across hot configuration and recovered from its
durable position, independent project retention/backlog/topic cutover, per-field
inheritance reset, acknowledgement preservation and new-project provisioning.
Report `audit-27-project-policy.json` SHA256
`0e1e3f76de0b0ee04bb65bdfddf1e19ef1c5151d352fc211dbc6a076f5604423`.

The preceding candidate 26 passed all eight foundation protocol groups against
fresh exact CLI/HTTP schema/OpenAPI exports, preserving independent model/history/
retrieval semantic negatives and version/authentication boundaries. Its separate
eventing protocol suite passed three groups with 22 valid/24 invalid vectors and
actual official-SDK raw delivery. Reports `audit-26-full-protocol.json` and
`audit-26-eventing-protocol.json` are in the same ignored evidence directory.
These remain candidate evidence; subsequent filter-queue budget work and the final
combined retained artifact require their own qualification.
