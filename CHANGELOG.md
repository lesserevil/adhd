# Changelog

## Unreleased

- Name the project Agentic Distributed Harness Depot (ADHD) consistently in
  documentation, helper help, web presentation and Agent Card description, while
  preserving existing technical identifiers and client contracts.

- Hub: add a private web console for health, archived information, subscriptions and
  delivery/matching activity, with a separate administrator credential, confirmed
  management actions and durable mutation retries.

- Extend stored publications with message/status types, source provenance, event
  timestamps, arbitrary JSON content, retrieval by ID, source/type search filters,
  durable source-event deduplication, and compatibility with original prototype stores.
- Add a pinned Docker deployment for the Elixir hub, private configuration and
  per-agent client setup, durable data mounts, health checks, and independent
  container acceptance with real Nemotron matching and backup/restore recovery.
- Provide a service README, user guide, admin operations guide, and troubleshooting
  reference covering agent coordination, container operation, credentials, and recovery.
- Add an agent coordination skill covering startup subscriptions and catch-up,
  publishing and polling during work, and processing updates before acknowledgement.
- Implement the first Elixir A2A coordination hub with per-agent authentication,
  durable subscriptions and deliveries, background Nemotron matching, polling and
  acknowledgements, addressed messages, and publication search. Validate the
  prototype with 10 native cases and 16 independent SDK scenarios, including
  hard restart and live two-agent coordination.
- Start and smoke-test the selected Nemotron checkpoint on a private GPU host,
  verifying checkpoint integrity and typed relevance responses for project updates.
- Select Nemotron Deciffusion 8B v2.1 as the initial decision model and the
  official A2A Hello World sample as the starting interoperability fixture.
- Establish two-agent project coordination as the first use case, with durable
  storage, polling and acknowledgements, new-publication subscriptions, and basic
  search in one private hub.
- Clarify Jev-like matching as typed probabilistic relevance judgments, with hub
  policy deciding which publications to queue for subscribers.
- Define the A2A information hub's requirements for indirect messaging, publishing,
  plain-text subscriptions with model-based matching, queued delivery, and search.
- Default to Elixir with Make on macOS; remove Python-only pip packaging from the
  project defaults.
- Initialized the project with Literate AI's specification-led lifecycle and durable
  user-directed work queue.
