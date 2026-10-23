# ADHD wire protocol

The current published application profile is **2.2.0**, with JSON Schema
`urn:adhd:protocol:2.2` and OpenAPI 3.1.0. Download the exact accepted native
runtime [JSON Schema](schema.json) and [OpenAPI](openapi.json) exports. The runtime
also serves them at `GET /protocol/schema` and `GET /protocol/openapi`, and
exports them with CLI `protocol-schema` and `protocol-openapi`.

The [publication qualification](../../verification/acme/protocol22-qualified-positive/manifest.json)
binds these unmodified CLI bytes to the accepted ACME source artifact, the actual
26 conservation vectors, complete scope inventory and eight whole HTTP wire
groups. The 421 unaffected inherited definitions are conserved. Five additional
raw differences are exclusively ordering of JSON Schema `required` names; the
proof retains those differences and applies the existing narrow wire comparison
rule. All other array order, constraints, literals and annotations remain strict.
The earlier failed fixture attempts remain recorded as failures.

Profile 2.2 adds the global Admin TLS operations and TLS configuration described
in the [managed HTTPS wire contract](acme.md). This is protocol qualification:
certificate, fault, browser and Compose checks have also passed. Kubernetes and
the final authority bridge remain pending. Protocol qualification alone does not
claim those separate runtime scopes.
The [active work queue](../roadmap/active-work.md) owns that completion status.

## Interfaces and versions

| Interface | Version and discovery |
| --- | --- |
| Agent to hub | A2A 1.0.0, JSON-RPC 2.0 `SendMessage`; `GET /.well-known/agent-card.json`, `POST /a2a`. |
| Peer federation | ADHD HTTP versions 1 and 2; `GET /protocol`, `POST /federation/v1`, `POST /federation/v2`. Version 1 requires an explicit legacy project pair. |
| Human administration | Admin envelope 1; `/admin`, `/admin/api` and login/session/logout endpoints. Profile 2.1 adds selective recovery; 2.2 adds global Admin-only `tls_status` and revision-fenced `tls_renew`. |
| Public descriptor | Protocol major 2; application/schema minor 2.2 does not change this major. |
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

- [Managed HTTPS and HTTP-01](acme.md) describes the additive TLS interface and
  its [schema-validated examples](acme-examples.json).
- [Multi-project and Kafka profile](multi-eventing.md) specifies project selection,
  raw and optionally filtered subscriptions, peer-v2 scopes, errors and compatibility.
  Its [executable examples](multi-eventing-examples.json) retain their declared
  profile; the current [scope inventory](scopes.json) covers all operations.
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

Application 2.1 extended 2.0 with selective recovery and target availability;
2.2 adds managed TLS/ACME. Use the validator for the advertised application
profile: strict older validators may reject new fields and operations. The exact
previous [2.1 downloads and historical index](v2.1/README.md),
[2.0 JSON Schema](v2.0/schema.json) and [2.0 OpenAPI](v2.0/openapi.json) remain
available. Required multi-project selection and raw reason shapes distinguish
2.0 from profile 1. A2A stays 1.0.0, Admin envelopes stay 1, and peer wire versions
remain explicitly 1 or 2. Authorization or v2 errors never permit silent fallback
to v1 or the unversioned legacy endpoint.

All wire-visible changes require contracts, schemas, examples, compatibility notes
and independent conformance together. JSON Schema shape validation alone is
insufficient: enforce the documented critical `x-*` annotations, UTF-8 byte bounds,
integer-token rules, exact request/response bindings and current authorization.
Unknown critical annotations fail closed. Omitted, null and empty values keep their
specified distinct meanings; reject duplicate keys and unknown command fields.
