# ADHD wire protocol

The current reviewed application profile is **2.1.0**, with JSON Schema
`urn:adhd:protocol:2.1` and OpenAPI 3.1.0. Download the exact reviewed
[JSON Schema](schema.json) and [OpenAPI](openapi.json) exports. The runtime also
serves them at `GET /protocol/schema` and `GET /protocol/openapi`, and exports them
with CLI `protocol-schema` and `protocol-openapi`.

These snapshots come from admitted successor38. Its independent combined-schema
check covers 87 recovery vectors, exact normative definitions, resolved references,
unchanged inherited definitions and OpenAPI correspondence. Its eight-group wire
check covers actual HTTP, SDK and CLI traffic. The [publication evidence](../../verification/protocol21-publication/manifest.json)
binds the artifact, files and raw reports; those published bytes and provenance
remain unchanged.

The current source41 image passes the complete
[eight-group wire gate](../../verification/ownedMULTI008/source41-core13-positive/wire.json).
Its [read-only export comparison](../../verification/ownedMULTI008/source41-protocol-conservation/review.json)
binds actual cache17 CLI exports and the core HTTP/CLI snapshots. Profile 2.1 is
semantically conserved, not byte-identical: JSON object serialization order and
only five explicitly named `required` string-array orderings per document differ.
The comparison retains both arrays at each exact JSON Pointer and verifies every
other array, example, enum and value unchanged. It does not reorder or republish
these downloads. Current core/platform/browser positives and remaining complete
recovery25/Kafka14 and final authority gates are distinguished in the
[qualification guide](../admin/event-service.md#qualification) and
[active queue](../roadmap/active-work.md).

## Interfaces and versions

| Interface | Version and discovery |
| --- | --- |
| Agent to hub | A2A 1.0.0, JSON-RPC 2.0 `SendMessage`; `GET /.well-known/agent-card.json`, `POST /a2a`. |
| Peer federation | ADHD HTTP versions 1 and 2; `GET /protocol`, `POST /federation/v1`, `POST /federation/v2`. Version 1 requires an explicit legacy project pair. |
| Human administration | Admin envelope 1; `/admin`, `/admin/api` and login/session/logout endpoints. Application 2.1 adds selective recovery operations. |
| Public descriptor | Protocol major 2; application/schema minor 2.1 does not change this major. |
| Event transport | Per-server Kafka behind the hub; agents continue using A2A and durable hub delivery acknowledgements. |
| OIDC backchannel | Core 1.0 errata 2, Discovery 1.0 errata 2, authorization code with RFC 7636 S256 PKCE and RS256. |
| Optional model adapter | SystemOne typed relevance `noul` and separate history/answer `choice` exchanges. Raw subscriptions require no model. |

Agent credentials, human sessions and peer credentials are separate principals.
A peer cannot assign a local role. Server federation uses its own HTTP envelopes;
it does not require A2A between servers. Discovery exposes capabilities without
exposing the private project registry.

## Contracts, examples and compatibility

Component contracts under `components/hub/` are normative and travel in the image.
Implementations need not read generated hub source to implement these interfaces.

- [Multi-project and Kafka profile](multi-eventing.md) specifies project selection,
  raw and optionally filtered subscriptions, peer-v2 scopes, errors and compatibility.
  Its [executable examples](multi-eventing-examples.json) and
  [scope inventory](scopes.json) accompany the schemas.
- [Event repair and historical replay](event-recovery.md) specifies quarantine,
  offsets, replay watermarks, acknowledgements and durable retry behavior.
- Selective recovery follows `project-recovery/spec.md`,
  `project-recovery/interface.md` and its closed
  [normative JSON Schema](../../components/hub/project-recovery/interface.schema.json).
  The [positive and negative vectors](../../tests/fixtures/project-recovery.json)
  cover plan/apply/status and CLI-only portable rebind. Rebind is not an Admin API.
- [Inherited profile-1 semantics](foundation-v1.md) explain accounts/OIDC, catalogs,
  canonical sources, contextual evidence, history, retrieval, replay and optimization.
  Apply the explicit profile-2 replacements for project scope, matching and transport.
  [Inherited examples](examples.json) retain their declared 1.7 fixture provenance.
- [OpenRig integration](../user/openrig.md) uses the same agent-facing A2A contract
  for cross-rig communication; it adds no separate peer protocol.

Application 2.1 extends 2.0 with selective recovery and target availability.
Do not use strict 2.0 validators for 2.1 messages. The byte-identical accepted
[2.0 JSON Schema](v2.0/schema.json) and [2.0 OpenAPI](v2.0/openapi.json) remain
available for compatibility checks. Required multi-project selection and raw
reason shapes distinguish 2.0 from profile 1. A2A stays 1.0.0, Admin envelopes
stay 1, and peer wire versions remain explicitly 1 or 2. An authorization or v2
error never permits silent fallback to v1 or the unversioned legacy endpoint.

All wire-visible changes require contracts, schemas, examples, compatibility notes
and independent conformance together. JSON Schema shape validation alone is
insufficient: enforce the documented critical `x-*` annotations, UTF-8 byte bounds,
integer-token rules, exact request/response bindings and current authorization.
Unknown critical annotations fail closed. Omitted, null and empty values keep their
specified distinct meanings; reject duplicate keys and unknown command fields.
