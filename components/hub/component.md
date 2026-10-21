---
namespace: adhd
version: 0.1.0
display_name: Agentic Distributed Harness Depot
profiles: ["application", "portable"]
sample: false
inheritable: true
provides:
  - name: application.portable-json
    version: 1.0.0
requires: []
authoring_inputs:
  - kind: specification-to-source-skill
    uri: skills/specification-to-source/portable-application-implementation/SKILL.md
  - kind: specification-to-source-skill
    uri: skills/specification-to-source/portable-specification-planning/SKILL.md
workflow_definition: workflows/production/staging/dev/workflow.md
routing_policy: routing/production/staging/dev/routing.json
flavor_slots:
  - slot_id: build-system
    axis: build.system
    cardinality: zero-or-one
    capability_contract: application.portable-json
  - slot_id: language
    axis: implementation.language-ecosystem
    cardinality: exactly-one
    capability_contract: application.portable-json
  - slot_id: os
    axis: platform.os
    cardinality: exactly-one
    capability_contract: application.portable-json
entrypoints:
  - name: run
    kind: portable-application
    path: run
acceptance_contracts: []
source_dependencies: []
specification_roots:
  - component.md
  - core/spec.md
  - information/spec.md
  - management/spec.md
  - presentation/spec.md
  - federation/spec.md
  - configuration/spec.md
  - identity/spec.md
  - protocol/spec.md
  - directory/spec.md
  - directory/queries.md
  - evidence/spec.md
  - history/spec.md
  - history/interface.md
  - history/evaluator.md
  - retrieval/spec.md
  - retrieval/index.md
  - retrieval/interface.md
  - archive/spec.md
  - archive/interface.md
  - feedback/spec.md
  - feedback/replay.md
  - feedback/interface.md
  - optimization/spec.md
  - optimization/selection.md
  - optimization/interface.md
  - multi/spec.md
  - eventing/spec.md
  - resources/spec.md
  - storage-relocation/spec.md
---
# Agentic Distributed Harness Depot (ADHD)

Provide one private, multi-project A2A service where authenticated agents publish
work updates, maintain plain-text subscriptions, receive queued information,
exchange addressed messages, and search published information. Use the selected
language's standard runtime facilities for hub logic and the selected Kafka REST
Proxy service for broker access. Support one running service per server registry
and one writer per project store.
The product contract below takes precedence over generic portable CLI practice
where the long-running serve mode requires it.

## Behavioral contracts

Read all named specification roots. core/spec.md owns the compatible CLI, A2A,
base configuration, persistence and matching contract. information/spec.md owns
publication envelopes and legacy-store upgrade. management/spec.md owns original
console operations; presentation/spec.md owns naming. federation/spec.md owns
asynchronous trusted-peer discovery. configuration/spec.md and identity/spec.md
explicitly extend live settings, human authentication/roles and Admin access;
protocol/spec.md owns versioned wire publication and conformance. directory/spec.md
extends authenticated catalogs, identity correlation and canonical source routing.
evidence/spec.md adds immutable contextual records and snapshot reads. These
extensions replace the named earlier restrictions; other behavior stays compatible.
history/spec.md, history/interface.md and history/evaluator.md add bounded owned
local-archive question jobs and the separate short-response choice evaluator.

retrieval/spec.md, retrieval/index.md and retrieval/interface.md add replaceable
contextual candidate indexes and owned bounded semantic retrieval jobs.

archive/spec.md and archive/interface.md add owned search-then-scan workflows,
original-evidence sufficiency and separate full-scope sampled audits.

feedback/spec.md, replay.md and interface.md add operational attempt capture,
independent adjudication/cohorts and paired frozen replay; they also select the
versioned closed-cycle sufficiency refinement. They do not publish derived facts.

Adaptive index proposals are bounded by optimization/spec.md; durable effective
selection and rollback follow optimization/selection.md, with exact Admin messages
and qualification evidence in optimization/interface.md.

Multiple projects follow multi/spec.md, which replaces single-project identity,
mutable project IDs and project-bound peer transport assumptions. Kafka eventing
follows eventing/spec.md, which replaces mandatory model matching with raw or
optionally filtered project streams and owns broker durability/cutover. These two
contracts take precedence over earlier restrictions on exactly those subjects.
