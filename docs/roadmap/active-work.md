# Active work

This file is the durable resumption queue for user-directed and discovered work. Before
implementation, follow `skills/agent/record-user-directed-work/SKILL.md`.
Keep detailed designs in focused roadmap documents and link them here.

## Detailed-roadmap lifecycle

This file is the sole resumable queue. Create a supporting file beneath `docs/roadmap/`
only when one item cannot keep a program's rationale, ordering, and acceptance contract
readable. Put this visible header immediately after the detailed document's title:

```markdown
- **Status:** active
- **Owning queue item:** [AREA-NNN](active-work.md#area-nnn-heading)
- **Completion / archival evidence:** pending while AREA-NNN remains open
```

Status is exactly `active`, `partial`, `deferred`, `completed`, or `historical`. The
owner must resolve to a checkbox or named program heading in this file. A terminal state
requires linked evidence. Keep a completed plan here only when doing so preserves useful
inbound links; move substantial closed programs beneath `docs/history/roadmap/`, retain
their owner, and mark them `historical`. Do not create a separate file for an ordinary
queue item or let `docs/roadmap/` become a plan archive.

## Roadmap implementation cycle

The user authorized implementing all pending entries, grouping branches as useful,
including the local builds and acceptance execution requested in the prior turn.
Work is on `feat/roadmap`; existing uncommitted work and the safety stash are
preserved. Execution order is INFO-002, QUERY-001 with INFO-003, SEARCH-001,
SEARCH-002, SEARCH-003, INDEX-001, AUTH-001, then final DOCS-002 verification.
Each entry retains its own acceptance gates. Context/query, adaptation and OIDC
API suites and live generative cases pass on the qualified artifact. Crash recovery
uses a checksummed atomic journal alongside DETS; stopped-store backup/restore
preserves the bundle. Final artifact and reproducible container checks are recorded
in [the implementation review](../architecture/roadmap-implementation.md).
Support both Linux and macOS as the user clarified; retain the macOS target and
add the Linux Flavor. The pinned container is runnable, but the lifecycle requires
a host-readable BEAM installation, so install checksummed official prebuilt
Elixir/OTP under ignored _build/tools for native Linux verification. No remote
macOS worker is registered; macOS acceptance must remain explicitly unverified
until a matching host is available. Reviewed Standard rebind plan
sha256:7d0230166ca280be4a63d53974978f3b0e4651dd1e720255cc63e8ee3f0df34a
updates the installed distribution/runner pins while retaining the same policy,
required evidence kinds and minimum test count. Keep inference
for answers separate from the existing Nemotron relevance classifier. Validate the
configured generative endpoint before choosing its typed query adapter. No running
service replacement or remote Git publication is included in this development cycle.

## P0

### [x] ONBOARD-001 — Establish the information hub's product requirements

- **Owner:** project mission and documentation
- **Direction:** Build an A2A information hub for indirect agent communication, information publishing, natural-language subscriptions, and agent queries/search.
- **Conclusion:** Record the product requirements and acceptance scenarios in PROJECT.md before choosing protocol bindings, persistence, or a matching model. This item establishes intent; runtime implementation remains separate work.
- **Depends on:** none
- **Implementation:**
  - [x] Record the project mission, required behaviors, acceptance scenarios, and unresolved implementation decisions in PROJECT.md.
  - [x] Replace product documentation placeholders with an accurate description and current implementation status.
- **Evidence:**
  - [x] Review requirements against the user's direction and pass project authority and lock verification: `litai verify --gate authority --gate locks` passed both gates. The matcher identity remains an explicit open decision, not a selected dependency.

Check the parent only after every required subtask and evidence item passes. Add the
release-visible outcome to `CHANGELOG.md`; Git preserves prior queue states.

### [x] CONFIG-001 — Default to Elixir

- **Priority:** P0
- **Owner:** project configuration
- **Direction:** Use Elixir as the default implementation language in this project.
- **Conclusion:** Install the bundled lang-elixir Flavor and replace the Python default; remove the Python-only pip packaging default while retaining Make and macOS.
- **Depends on:** none
- **Implementation:**
  - [x] Install lang-elixir and update default selectors.
  - [x] Refresh the sample Component lock for the new defaults.
- **Evidence:**
  - [x] Project authority and lock verification pass with Elixir selected and no Python-only packaging default: `litai verify --gate authority --gate locks` passed both gates; sample lock refreshed by `litai lock samples/hello-component`.

### [x] MATCH-001 — Clarify Jev-style subscription matching

- **Priority:** P0
- **Owner:** project mission and documentation
- **Direction:** Use the supplied Jev reference to clarify the model class intended for subscription matching.
- **Conclusion:** Specify semantic classification with typed probabilities from publication context and subscription criteria; keep provider, model version, thresholds, and failure policy open.
- **Depends on:** none
- **Implementation:**
  - [x] Update matcher requirements and documentation using primary Jev documentation: https://docs.typesafe.ai/primitives. PROJECT.md records typed relevance probabilities, hub decision policy, and independent subscription questions.
- **Evidence:**
  - [x] Verify source-supported matcher semantics and pass project authority and lock checks: `litai verify --gate authority --gate locks` passed both gates. Provider, threshold, uncertainty handling, and failure policy remain open decisions.

### [x] SCOPE-001 — Define the first shared-project coordination scope

- **Priority:** P0
- **Owner:** project mission and documentation
- **Direction:** Accept the proposed first-version defaults and start with two agents coordinating work on the same project.
- **Conclusion:** Record one private hub with durable storage, polling and acknowledgements, a replaceable Jev-style matcher, new-publication subscriptions, agent text/JSON publishing, and basic search. Define coordination examples and restart/reconnect acceptance without choosing an agent client or deployment.
- **Depends on:** none
- **Implementation:**
  - [x] Update PROJECT.md and product documentation with accepted scope and the two-agent workflow, including offline catch-up and restart/acknowledgement acceptance scenarios.
- **Evidence:**
  - [x] Review coverage of accepted defaults and verify project authority and locks: `litai verify --gate authority --gate locks` passed both gates. Runtime implementation remains pending.

### [x] INTEGRATE-001 — Select initial A2A test peer and decision model

- **Priority:** P0
- **Owner:** project mission and integration requirements
- **Direction:** Use a simple compliant A2A test agent and the available internal Nemotron Deciffusion 8B v2.1 decision model instead of requiring Jev access.
- **Conclusion:** Inspect official A2A samples and model repository metadata; record the initial model choice, verified inference dependencies, and remaining serving prerequisites without downloading weights or starting compute.
- **Depends on:** none
- **Implementation:**
  - [x] Inspect model README/configuration and official A2A sample documentation; source identities and integration findings are recorded in docs/architecture/model-integration.md.
  - [x] Update project requirements and integration guidance with selected dependencies and unresolved serving details. Initial model selected; live serving is tracked by SERVE-001.
- **Evidence:**
  - [x] Source-check integration claims and pass project authority and lock validation: `litai verify --gate authority --gate locks` passed both gates; the documented relevance request parses as JSON. No live inference or A2A interoperability run is claimed.

### [x] SERVE-001 — Validate a reachable Nemotron inference service

- **Priority:** P0
- **Owner:** private inference deployment
- **Direction:** Test locally when appropriate or use one of the offered private GPU hosts.
- **Conclusion:** After the user-managed reboot, host and container GPU discovery both pass with matching driver 595.99.02. The selected RTX 4090 host has about 23 GiB free VRAM and 135 GiB free root disk. Prepare an isolated loopback-only inference service without changing existing workloads.
- **Depends on:** none
- **Implementation:**
  - [x] Check serving footprint and isolate the model runtime and checkpoint. The digest-pinned image is running with a read-only BF16 checkpoint mounted, dynamic FP8 quantization, a 60% GPU-memory budget, and loopback-only access. Transfer and on-host SHA256 checks matched the pinned internal checkpoint. The user-managed reboot resolved the driver mismatch.
  - [x] Run a healthy service and record a real relevance request/response with the selected checkpoint. `/health` returned `ready: true`; two real publication cases returned typed Noul probabilities. Exact requests, responses, and identities are in verification/deciffusion-smoke.json.
- **Evidence:**
  - [x] Validate positive and negative project-update judgments and record the exact runtime/checkpoint identity: API-change relevance 0.985936 versus outage relevance 0.003173; the outage case ranked outage relevance highest (0.997199) but also scored API relevance 0.798187. This is serving/response evidence, not a production threshold or calibrated-quality claim. `litai verify --gate authority --gate locks` passed both gates.

### [x] HUB-001 — Implement the first durable A2A coordination hub

- **Priority:** P0
- **Owner:** hub Component, protocol contract, and acceptance
- **Direction:** Build the agreed first working hub with two agents sharing project updates, subscriptions, queued delivery, messages, search, and restart recovery.
- **Conclusion:** Author the hub Component and precise A2A contract, generate an Elixir implementation through the installed lifecycle, and verify it with independent two-agent clients and the live Nemotron endpoint. Keep runtime data private and persisted; bind test services to loopback. User approval of the implementation plan includes local build and execution for acceptance.
- **Depends on:** none
- **Implementation:**
  - [x] Define the A2A operation and durable-state contract and resolve the hub generation plan: components/hub/component.md and its generated lock resolve Elixir/Make/macOS; CLI oracle bound to the exact specification identity.
  - [x] Rebind the stale Standard installation identity using reviewed plan sha256:a7615db8b45aa3c16a0f09ce114832c787ed64372e4e85a17be2720ae65d586a. Installed version remains 1.2.0 and the policy/evidence requirements are unchanged. The first build stopped safely before generation.
  - [x] Record local workflow limitations: `project.peer_work_git_failed` because HEAD has no commit; tracker inspect reports forge unsupported and no remote. No branch, merge, push, or remote CI action was attempted.
  - [x] Generate and build the Elixir service and its native tests. The clarified Component generated an Elixir implementation; all 10 native cases passed. A stable-authority rebuild recorded a passing lifecycle receipt. Native and verifier-owned argument vectors were checked to remain distinct. Accepted source is published to the committed source-cache target.
  - [x] Run independent two-agent protocol, failure, isolation, idempotency, and restart tests, including real Nemotron matching: all 16 black-box checks passed using a2a-sdk 1.1.0. Evidence: verification/hub-acceptance.json. A dropped private model tunnel caused the first live attempt to time out; reconnecting restored the healthy endpoint and the complete suite passed.
  - [x] Document runnable setup and product usage and retain passing evidence. Setup/API guides and the SDK helper are verified, including integer-limited polling through JSON text parts. Ordinary build/run export is verified, and its artifact hash matches the 16-case independent report, including a real unrelated publication check. The starter sample catalog audit was refreshed. Strict accepted-source-only continuation reported source_cache.runtime_absent after oracle reconciliation; no gate was bypassed, and the documented ordinary build reuses and verifies the source candidate. The private prototype is running; credentials and durable data are ignored by Git.
- **Evidence:**
  - [x] Hub build/native tests and independent A2A SDK scenarios pass: 10 native cases and 16 SDK scenarios, persistent unacknowledged delivery after hard kill, acknowledgement retention, model failure/recovery, and live Nemotron coordination. verification/hub-acceptance.json binds the exact exported artifact SHA256. `litai verify` passed authority, both locks, and receipt; source-intelligence and HTML gates are skipped by configuration. Start/end peer surveys and the read-only GC plan cannot run without an initial Git commit; no remote forge/CI is configured, and no cleanup, push, or merge was attempted.

### [x] SKILL-001 — Describe agent coordination through the hub

- **Priority:** P1
- **Owner:** project agent skill and usage documentation
- **Direction:** Provide a reusable skill for startup subscriptions and polling, ongoing work updates, and processing and acknowledging deliveries.
- **Conclusion:** Add a project-owned client skill using the existing A2A helper and API contract, linked from the project guide; preserve explicit polling, agent identity, and durable acknowledgement behavior.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Write and link the three-step coordination skill with setup, retry, and acknowledgement guidance: skills/agent/coordinate-via-hub/SKILL.md, referenced in docs/README.md.
- **Evidence:**
  - [x] Validate skill structure and links and run project authority and lock checks: skill-creator quick_validate passed; all three linked files exist; command and delivery fields reviewed against the hub contract; litai verify --gate authority --gate locks passed. Start/end peer surveys remain unavailable because Git HEAD has no initial commit; no remote forge is configured.

### [x] DEPLOY-001 — Run the hub service in a container

- **Priority:** P1
- **Owner:** hub deployment specification and packaging
- **Direction:** The hub service should run containerized.
- **Conclusion:** Provide a containerized deployment of the Elixir hub with durable storage outside the container, private runtime configuration, and connectivity to the separately served matcher. Implemented an isolated Linux Docker runtime for the accepted portable Elixir script, retaining macOS/Make/Elixir authoring defaults. Host networking preserves the loopback-only service contract; configuration and storage stay outside the image.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Define the container deployment contract and required target Flavors: docs/admin/operations.md records the Linux Docker runtime, pinned Elixir/OTP realization, host networking, and persistent data boundary. The existing Elixir/Make/macOS Flavors produce portable source; packaging does not claim a native Linux cross-build.
  - [x] Add a reproducible container image and documented startup, configuration, persistent-volume, health-check, and shutdown procedures: deploy/Dockerfile, deploy/health.exs, deploy/run.sh, scripts/stage_container.py, and scripts/configure_hub.py. A deterministic payload archive removes Docker copy-layer timestamp variance. Two independent no-cache builds produced the same image identity; verification/container-reproducibility.json records inputs and builder versions.
- **Evidence:**
  - [x] Run two-agent coordination against the containerized hub and verify queued deliveries and acknowledgements survive container replacement with the same persistent volume: all 20 checks passed, including real Nemotron matching, hard-kill restart, documented runner startup, container replacement, offline backup/restore, and rollback. Evidence: verification/container-acceptance.json.
  - [x] Verify the container can reach the configured matcher without embedding credentials or model weights in the hub image: live Nemotron SDK coordination passed. The staged context contains only a Dockerfile, a hash manifest, and a deterministic archive of the accepted script, health probe, contract, and manifest. Server credentials are mounted read-only; the model and data remain external. Private config isolation, exclusive creation, artifact drift rejection, and archive identities were checked.

### [x] DOCS-001 — Provide complete service documentation

- **Priority:** P1
- **Owner:** project README and service documentation
- **Direction:** Provide a README, user documentation, admin documentation, and troubleshooting documentation.
- **Conclusion:** Review and extend the existing project README and prototype guides into a coherent documentation set for hub users and administrators. Document actual supported behavior and incorporate container deployment instructions when DEPLOY-001 is implemented. The root README and connected user, admin, and troubleshooting guides are written. Container and recovery procedures, documentation navigation, native build, and full project verification all passed.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Review existing documentation and update the README with the service purpose, capabilities, quick start, and links to user, admin, and troubleshooting guides: README.md and docs/README.md now route each audience to the appropriate guide.
  - [x] Complete user documentation for agent setup, authentication, the coordination skill, subscriptions, publishing, messaging, polling, acknowledgements, and search: docs/user/using-the-hub.md connects client setup and the coordination loop to the existing API examples.
  - [x] Add admin documentation for installation, containerized operation coordinated with DEPLOY-001, configuration, credentials, persistent storage, backup and restore, upgrades, monitoring, and matcher connectivity: docs/admin/operations.md.
  - [x] Add troubleshooting documentation for startup failures, authentication errors, missing or delayed deliveries, matcher outages, connectivity problems, and storage or recovery failures: docs/admin/troubleshooting.md.
- **Evidence:**
  - [x] Verify documented commands and examples against the supported service and check documentation navigation and project authority: configuration, staging, build, startup, health, SDK coordination, and recovery commands were exercised; guide links resolve. Verified staging exactly reproduces the tested input manifest/archive and rejects artifact drift. The native build passed all 10 cases; litai verify passed authority, both locks, and the current receipt, with source-intelligence and HTML gates skipped by configuration. Start/end peer surveys and GC planning remain unavailable without an initial Git commit, and tracker reconciliation is skipped because no remote forge is configured; no push, merge, or shared Docker cleanup was attempted.
  - [x] Exercise the documented administrator startup, backup and restore, and recovery procedures; verify container-specific instructions after DEPLOY-001 is implemented: the independent container suite invokes the actual runner and configuration tool, replaces containers over the same data, restores an offline backup, and rolls back to the preserved pre-restore data. All four operations checks and the original 16 SDK scenarios passed.

### [x] INFO-001 — Store and retrieve information from agents and future external sources

- **Priority:** P1
- **Owner:** hub information model, ingestion, subscriptions, and search
- **Direction:** Store client-submitted information for future searching, initially agent messages and status updates, and later messages from email, Slack, Teams, and other sources; allow subscriptions and search across this information.
- **Conclusion:** Extend the existing durable publish/search path into a common information model with source and content metadata. Start with agent messages and status while preserving arbitrary JSON content. Keep private addressed-message visibility distinct from project-published information. Future external connectors should use the same storage, subscription-matching, and search path. Implemented information type, source provenance, occurrence time, retrieval by ID, source/type filters, and source-item deduplication while retaining DETS as approved. The original prototype store upgrades without losing accepted state. A verified container is running with private per-agent client files and a live-testing guide. Live external connectors remain subsequent work; synthetic external-origin information already uses the shared contract.
- **Depends on:** HUB-001
- **Implementation:**
  - [x] Defined in components/hub/component.md and the named components/hub/information/spec.md boundary; includes arbitrary JSON values, immutable history, bounded metadata, authenticated author identity, and project/private visibility rules.
  - [x] Generated the extended Elixir runtime through the installed lifecycle. The first candidate had an HTTP-handler syntax error; lifecycle repair produced the accepted implementation. All 8 native cases and 6 private CLI acceptance vectors passed, with distinct native/oracle arguments.
  - [x] The matcher receives complete envelopes and deliveries retain type, source, and event time. Independent fixture checks and live Nemotron status delivery verify this path, retention after ack, and retry deduplication.
  - [x] Added get by publication_id and exact information_type/source_kind/source_id search filters, including filter-only searches. Existing query-only and publish clients retain their shapes and behavior. Private delivery IDs cannot be retrieved through get or search.
  - [x] Documented in docs/user/stored-information.md, API/user/admin guides, the coordination skill, and docs/user/live-testing.md. Future adapters must map upstream visibility, source/event or revision IDs, original timestamps, and retries into the same authenticated contract. No live connector integration is claimed.
- **Evidence:**
  - [x] 24 independent host SDK scenarios passed, including arrays/scalars/null, source/type filters, archive retention after ack, hard restart, and source-item retries. Evidence: verification/hub-acceptance.json. A real store produced by the original runtime retained history, inboxes, ack state, pending jobs, and original idempotent results after upgrade.
  - [x] 27 container scenarios passed, including the original protocol/restart suite, all information-archive scenarios, real Nemotron matching, documented runner, replacement, backup/restore, and rollback. Evidence: verification/container-acceptance.json. Independent no-cache image builds matched; verification/container-reproducibility.json binds the tested source and both specification roots.
  - [x] Synthetic Slack-origin publication matched, delivered, and remained searchable through the common contract. The deployed container passed the live status/archive smoke test; verification/live-mvp-smoke.json records the result. Cold backups preserve the prior local runtime/config/store and the pre-upgrade data. Private client files are under .adhd/mvp/. Full litai verify passed authority, both committed locks, and the current receipt; source-intelligence and HTML gates are skipped by configuration. The deployed container also retained history and acknowledgements across restart. Source is published to the committed cache. Start/end peer surveys and GC planning remain unavailable without an initial Git commit; no remote forge is configured, so no tracker reconciliation, push, merge, or shared cleanup was attempted.

### [x] UI-001 — Add a simple web management and observation UI

- **Priority:** P1
- **Owner:** hub web interface and administrator API
- **Direction:** Provide a simple web management and observation UI for the service.
- **Conclusion:** Implemented the four-view console and separate administrator API, durable management retry records, credential isolation and metadata-only observation of private deliveries. Fresh normal-build generation preserves the original schema-2 source-event index; the first candidate's migration defect was caught by a real old-runtime upgrade check and corrected in the canonical contract. Verified the exported artifact in hardened containers and a real browser, then replaced the private MVP using an offline backup. The same image retained agent state across restart.
- **Depends on:** INFO-001
- **Implementation:**
  - [x] Defined Overview, Information, Subscriptions and Activity in components/hub/management/spec.md; registered the named specification root.
  - [x] Separate optional admin_token, legacy-disabled API, agent/admin token separation, memory-only browser credential, same-origin checks, strict CSP, redacted diagnostics, and delivery metadata without private bodies.
  - [x] Implemented embedded assets and nine admin operations, including confirmed subscription removal and pending-job retry; mutation IDs persist atomically across restart. Normal build exports the tested candidate.
  - [x] Added docs/admin/web-console.md, updated operations/troubleshooting/navigation/live-testing guides and the private configuration helper; the helper provisions a separate mode-0600 administrator token.
- **Evidence:**
  - [x] Two-agent fixture and live deployment checks passed; verification/web-console-browser.json covers message/status/search/details, queued deliveries and simulated outage. verification/web-console-live-smoke.json covers real matcher health and unchanged live agent state after replacement and restart.
  - [x] 31 SDK scenarios passed (verification/hub-acceptance.json), including invalid admin configuration, auth/origin boundaries, disabled legacy configs, private visibility, durable action retries/conflicts and both earlier store formats. Browser confirmation cancellation and response-loss retry passed; deployed responses/logs contain no bearer tokens.
  - [x] Desktop/mobile screenshots and accessibility snapshots inspected at 1440 and 390 pixels: no overflow or normal-path page/console/network errors. Fault-injected 503/401/network loss recovered as intended. 12 native tests, eight independent CLI vectors and 33 hardened-container scenarios passed; independent no-cache image builds matched (verification/container-reproducibility.json). Full litai verify passed authority, both locks and current receipt; source-intelligence and HTML gates are skipped by configuration, with the UI independently checked in Playwright. Accepted source is published to the committed cache. Peer surveys and tracker reconciliation remain unavailable without an initial commit or configured remote; no commit, push, merge or shared cleanup was attempted.

### [x] AUTH-001 — Optional OIDC authentication for administrator pages

- **Priority:** P1
- **Owner:** hub administrator authentication and web management interface
- **Direction:** Add optional OpenID Connect (OIDC) authentication for administrator pages, retaining the current admin key as the default authentication method.
- **Conclusion:** Implemented explicit key/OIDC modes, authorization code with S256 PKCE, RS256 token validation, subject authorization, memory sessions, CSRF/origin checks and local logout. Default key and A2A agent authentication remain compatible. Provider and rendered-browser fixtures pass; see docs/admin/oidc.md.
- **Depends on:** UI-001
- **Implementation:**
  - [x] Define explicit authentication-mode selection with admin key as the default, optional OIDC provider configuration, and backward compatibility for existing server and client configurations.
  - [x] Specify OIDC sign-in/callback, identity and token validation, administrator authorization rules, protected API access, session expiry/logout and request-forgery protection. Define explicit key/OIDC coexistence policy; avoid silent fallback when an explicitly selected OIDC mode fails.
  - [x] Implement optional OIDC protection for administrator pages and their supporting API while preserving administrator permissions, private-message visibility boundaries and existing A2A agent authentication.
  - [x] Document provider setup, required configuration and secrets, redirect URLs, mode selection, session/logout behavior and troubleshooting; retain a straightforward admin-key setup path.
- **Evidence:**
  - [x] Verify the unchanged default admin-key flow with OIDC unconfigured, including existing configurations and agent workflows.
  - [x] Exercise OIDC sign-in, allowed and denied administrator identities, invalid or expired identity tokens, callback validation, session expiry/logout, provider failures and absence of credential leakage.
  - [x] Verify browser and direct API access enforce the selected authentication mode and preserve management-action safety and private-data boundaries; pass applicable project, SDK, container and desktop/mobile browser checks.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/oidc-acceptance.json and roadmap-browser.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] NAME-001 — Use Agentic Distributed Harness Depot consistently in documentation and help text

- **Priority:** P2
- **Owner:** project naming, documentation and hub user-facing text
- **Direction:** Expand ADHD as Agentic Distributed Harness Depot, using Depot rather than Database, and update documentation, help text and related user-facing references accordingly.
- **Conclusion:** Implemented Agentic Distributed Harness Depot (ADHD) as the full product name across documentation, helper help, component display metadata, browser title/sign-in/authenticated brand and Agent Card description. The exact CLI describe response and existing adhd/ADHD identifiers remain compatible. The tested container is deployed using the existing credentials and store, with an offline pre-update backup. Evidence: verification/name-acceptance.json.
- **Depends on:** none
- **Implementation:**
  - [x] Inventoried the named product surfaces; verification/name-acceptance.json records the current documentation set and three public helper help checks. Generic hub/database terminology and technical paths remain descriptive or stable identifiers.
  - [x] Updated project goals, README/guide introductions, agent coordination skill, helper descriptions and component display metadata; added components/hub/presentation/spec.md to own exact public presentation. Preserved legitimate database terminology and historical evidence.
  - [x] Generated and qualified the runtime through litai, exported its tested artifact, included the presentation specification in the container manifest and published accepted source to the committed cache. Updated CHANGELOG.md. Deployed without changing credentials, container name or data paths.
- **Evidence:**
  - [x] Naming inventory and three helper --help outputs passed; full litai verify passed authority/documentation review, both locks and the current receipt. Tracker and peer surveys remain unavailable without a configured remote or initial commit; no commit, push or merge was attempted.
  - [x] Five native cases and eight independent CLI vectors passed, as did 31 SDK and 33 hardened-container scenarios, including real model matching and both earlier store upgrades. Exact describe compatibility and Agent Card naming passed. Playwright desktop/mobile screenshots and accessibility structure confirmed the full name fits with no normal-path page, console, network errors or document overflow; search/details, subscription create/cancel/remove, guide toggle and logout/reload passed. Independent no-cache image builds matched. Live agent state and existing credentials were preserved. Reports: verification/name-acceptance.json and its linked evidence. Source-intelligence and HTML gates are skipped by project configuration; browser inspection was performed independently.

<a id="info-002-preserve-contextual-evidence-without-a-domain-taxonomy"></a>

### [x] INFO-002 — Preserve contextual evidence without a domain taxonomy

- **Priority:** P1
- **Owner:** hub information model and persistence
- **Direction:** Retain full agent statements and their context so future questions and re-indexing do not require predicted data buckets.
- **Conclusion:** Implemented immutable context envelopes, relationships/corrections, content identities and schema-3 upgrades preserving old source retries and history. A checksummed atomic journal recovers unclean DETS images without silently repairing or resetting originals. See docs/user/stored-information.md and docs/user/querying.md.
- **Depends on:** INFO-001
- **Implementation:**
  - [x] Specify optional question, reply, conversation and subject references with contextual snapshots, provenance and bounded authorized link traversal; preserve arbitrary text/JSON and unknown domain concepts.
  - [x] Implement immutable corrections and evidence relationships, stable content identities, legacy-store compatibility, retry semantics and durable storage without replacing original statements with extracted facts.
  - [x] Document context submission and re-indexing semantics, including missing references, cycles, changed external sources and private-message isolation.
- **Evidence:**
  - [x] Round-trip Yes with its question and subject, cardinal/red-bird reports, arbitrary JSON and a later correction across retries, acknowledgements and hard restart.
  - [x] Upgrade existing stores without data loss; reject unauthorized context expansion and demonstrate reconstruction of the exact evidence used by a historical query.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/roadmap-acceptance.json and roadmap-hub-acceptance.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] QUERY-001 — Evaluate natural-language questions by scanning contextual history

- **Priority:** P1
- **Owner:** hub query evaluator and A2A query jobs
- **Direction:** Answer unforeseen questions from original evidence without requiring a purpose-built index.
- **Conclusion:** Implemented owner-private durable query jobs over frozen authorized evidence, bounded scans, continuation/cancellation, strict cited model output and explicit incomplete/unavailable outcomes. A real generative evaluator passes independently labeled branch and contextual-bird scenarios. See docs/user/querying.md.
- **Depends on:** INFO-002
- **Implementation:**
  - [x] Define natural-language query requests, scope/snapshot identity, asynchronous job lifecycle, budgets, continuation, cancellation, idempotency and authorized result retrieval.
  - [x] Evaluate all records in the scope with context expansion and cross-record synthesis; retain supporting and contradicting source IDs, uncertainty, evaluator versions and examined/remaining coverage.
  - [x] Implement durable checkpoints and explicit partial, unavailable, conflicting and no-evidence outcomes; keep inference outside the store writer and literal search compatible.
- **Evidence:**
  - [x] Answer bird presence, explicitly reported species/color and distinct-bird count without domain columns; handle corrections and evidence requiring multiple linked records.
  - [x] Exercise hard restart, timeout, malformed model results, cancellation, concurrent publication and budget exhaustion; never report incomplete scans as exhaustive or missing evidence as false.
  - [x] Validate a real configured evaluator against independently labeled fixtures; existing typed subscription relevance alone must not qualify as answer synthesis.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/roadmap-acceptance.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] SEARCH-001 — Build replaceable general-purpose contextual retrieval

- **Priority:** P1
- **Owner:** hub retrieval adapters and derived index lifecycle
- **Direction:** Retrieve unforeseen questions without requiring users to predict indexes or classify incoming publications.
- **Conclusion:** Implemented replaceable contextual lexical indexes plus actual Nemotron semantic candidate scoring, asynchronous catch-up/rebuild and atomic version switches. Literal search and original evidence remain available. The real-model paraphrase check and caller limit pass. See docs/admin/retrieval.md.
- **Depends on:** INFO-002
- **Implementation:**
  - [x] Define contextual indexing input and candidate response contracts, publication/context identities, index/model versions, indexed-through watermarks and explicit stale/unavailable states.
  - [x] Implement asynchronous idempotent indexing, incremental updates, context-change invalidation, full rebuild and atomic version switching while ingestion remains durable during index failures.
  - [x] Preserve literal search and support scoped candidate retrieval followed by original-record/context fetch; choose backend and embedding model from measured needs rather than a domain taxonomy.
- **Evidence:**
  - [x] Find paraphrases and exact identifiers, including Yes indexed with its question; negation similarity must not be treated as support.
  - [x] Rebuild from originals, catch up after downtime and switch versions under concurrent ingestion without losing records or leaking private context; expose incomplete coverage.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/roadmap-retrieval-model.json and adaptation-acceptance.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] SEARCH-002 — Fall back from search to semantic scans

- **Priority:** P1
- **Owner:** hub query planning and evidence sufficiency policy
- **Direction:** Try inexpensive search first and scan when it fails to produce useful evidence.
- **Conclusion:** Implemented semantic sufficiency planning, search/scan/search-then-scan modes, durable fallback reasons and sampled complete-snapshot audits. Current answers require superseding evidence coverage; missing or incomplete evidence cannot establish absence. See docs/user/querying.md.
- **Depends on:** QUERY-001, SEARCH-001
- **Implementation:**
  - [x] Define search, scan and search-then-scan modes with explicit scope, budgets, completeness requirements and stable query snapshots.
  - [x] Escalate on insufficient or conflicting evidence, absent/stale indexes, retrieval errors and exhaustive requests; evaluate usefulness against the question rather than score or hit count alone.
  - [x] Add configurable sampled scan audits of apparently successful searches; expose fallback reasons, partial outcomes, evidence and audit selection probabilities without blocking normal hub traffic.
- **Evidence:**
  - [x] Recover useful evidence missed by search, including later corrections; distinguish search misses from no evidence in the scanned corpus.
  - [x] Exercise plausible incomplete answers, negation, count/all requests, index outages and scan budget exhaustion; preserve explicit uncertainty and scope completeness.
  - [x] Verify scan audits can discover hidden misses in apparently successful searches and record their sampling policy.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/roadmap-acceptance.json and adaptation-acceptance.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] SEARCH-003 — Record retrieval failures and replay past questions

- **Priority:** P1
- **Owner:** hub retrieval feedback and evaluation history
- **Direction:** Re-evaluate failed searches and learn from repeated search-then-scan attempts.
- **Conclusion:** Implemented owner-private attempts, versioned coverage/evidence comparisons, gap classifications, normalized recurrence groups and same-snapshot replay. Feedback never becomes source evidence or subscription traffic. See docs/admin/retrieval.md.
- **Depends on:** SEARCH-002
- **Implementation:**
  - [x] Record question, authorized scope/snapshot, search candidates/ranks, scan evidence, answer changes, completeness, fallback reason, versions, cost and latency with access controls.
  - [x] Cluster recurring misses and replay saved attempts against changed retrieval configurations on the same evidence snapshot; keep later-corpus re-evaluation separately labeled.
  - [x] Create regression and held-out cohorts including successful searches, no-evidence cases and sampled audits; retain feedback separately from source publications to prevent self-confirming retrieval.
- **Evidence:**
  - [x] Reproduce a miss with stable source/configuration identities and measure improvement without mistaking new publications for better indexing.
  - [x] Classify missing evidence, ranking/context defects, model errors and incomplete scans correctly; incomplete/model-generated judgments are not unquestioned ground truth.
  - [x] Verify feedback authorization, duplicate retry handling, restart persistence and replay isolation from subscription deliveries and ordinary evidence searches.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/adaptation-acceptance.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] INDEX-001 — Generate and qualify retrieval improvements from observed misses

- **Priority:** P1
- **Owner:** hub adaptive indexing jobs and operator policy
- **Direction:** Use repeated search-then-scan failures to identify and generate the indexes retrieval actually needs.
- **Conclusion:** Implemented bounded declarative recipe proposals, isolated candidate jobs, disjoint replay cohorts, quality/resource gates, catch-up, atomic promotion, rollback and retirement. Review and automatic modes pass; ineffective recipes are not repeatedly proposed. Adaptation remains opt-in. See docs/admin/retrieval.md.
- **Depends on:** SEARCH-003
- **Implementation:**
  - [x] Define configurable recurrence/support thresholds and diagnose repeated misses; generate versioned declarative recipes tied to evidence rather than arbitrary generated executable code.
  - [x] Build isolated candidates from authoritative records with durable checkpoints and resource limits; replay training and held-out/regression cohorts and report quality, coverage, latency and storage tradeoffs.
  - [x] Promote only candidates passing configured criteria and corpus catch-up, atomically switch versions, retain rollback and prevent repeated ineffective rebuilds; support operator-selected automatic or review-based promotion.
  - [x] Document lifecycle states, failure handling, retirement and management visibility; add generated runtime behavior through owning Component specifications and the authorized Literate AI lifecycle.
- **Evidence:**
  - [x] An observed recurring paraphrase/context miss produces a candidate that improves held-out retrieval; a ranking-only defect need not create a new index.
  - [x] Reject candidates that regress correction/negation, privacy, successful-query recall or resource limits; reject insufficient evaluation evidence.
  - [x] Exercise interrupted builds, concurrent publications/context updates, promotion, rollback and retirement while source records and hub delivery state remain intact.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/adaptation-acceptance.json and roadmap-container.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

### [x] DOCS-002 — Keep documentation aligned with supported behavior

- **Priority:** P1
- **Owner:** project contributor guidance and documentation
- **Direction:** Add rules ensuring documentation matches the actual functions of the system.
- **Conclusion:** Implemented project documentation consistency policy and reviewed supported-feature and limitation claims across specifications, guides, helpers and console. The authorized Linux lifecycle refreshes the stale runtime receipt. Final documentation plan/review and full verification are recorded with the implementation evidence.
- **Depends on:** none
- **Implementation:**
  - [x] Added docs/user/documentation-policy.md and required it from AGENTS.md, CLAUDE.md and docs/README.md; added the Unreleased changelog outcome. The policy requires same-change updates, evidence-backed capability and limitation claims, review of summaries/examples, explicit future-feature labels, and recorded completion evidence.
  - [x] Corrected docs/admin/operations.md to describe queued-delivery counts, matching-job status, matcher health and confirmed pending-job retries; retained the historical-metrics limitation.
- **Evidence:**
  - [x] Reviewed the corrected operations claims against components/hub/management/spec.md, the current cached source/store.exs and source/matcher.exs, tests/admin_cases.py and existing verification/name-hub-acceptance.json. The existing acceptance report was inspected, not rerun. Reviewed entry-point links, project-guide navigation and policy scope; local links in all edited guidance and operations documents resolve.
  - [x] Ran the documentation-update plan, recorded the current authority review through litai project documentation-review --record, and ran litai verify and git diff --check. Authority and both locks pass; source-intelligence and HTML gates are skipped by configuration; receipt fails with project.test_receipt_stale after the documentation authority change. The plan's config-command warning is a false positive: litai --help lists config and litai config paths --help succeeds. Start/end peer surveys and open issue/review listings succeeded with no open items or collectable branches/worktrees; no remote writes or cleanup occurred.
  - [x] Refresh the stale runtime-test receipt through an authorized lifecycle build on the supported authoring host and pass full litai verify. The requested implementation cycle now includes authorized generated-code execution and a fresh lifecycle receipt.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/current.json and roadmap-container-reproducibility.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.

- **Continuation review:** Preparing the local handoff commit exposed a new-file blank-at-EOF warning missed by an unstaged-only diff. Trim the authored protocol specification and preserve immutable cache bytes with Git attributes.
  - [x] Requalified the unchanged runtime against the normalized specification: six native cases and eleven independent CLI vectors passed; runtime SHA256 is unchanged. Source-cache metadata and documentation were refreshed, staged whitespace checks pass, and the local handoff commit is prepared. Full verification is refreshed after closing this item.

### [x] DEPLOY-002 — Run ADHD in Kubernetes with an exposed service port

- **Priority:** P1
- **Owner:** hub deployment and operations documentation
- **Direction:** Run ADHD here in the Kubernetes cluster and expose it on an open port.
- **Conclusion:** Inspect the local cluster and accepted images, deploy one durable hub instance with private credentials and a pod-local proxy preserving the loopback-only hub contract, expose the proxy on a service port, and verify authenticated operations and matcher connectivity. Deployed the exact previously accepted hub image in namespace adhd with a loopback-preserving nginx proxy, private credentials, node-bound persistent storage, host-network matcher access and NodePort 30866. Existing Docker service and data are preserved. Runtime checks passed; the framework receipt remains stale from documentation authority edits and no fresh lifecycle build is claimed.
- **Depends on:** none
- **Implementation:**
  - [x] Added deploy/k8s/adhd.yaml with digest-pinned pre-imported images, one Recreate replica, local-path PVC, read-only Secret and ConfigMap mounts, non-root containers, resource limits, no service-account token and NodePort 30866. Private rendered configuration and credentials are under ignored .adhd/k8s/. Imported the accepted images into the selected node runtime. Corrected nginx temporary-directory paths after the initial read-only-filesystem startup failure; the final rollout is healthy.
  - [x] Deployed and verified health, console shell, Agent Card, two authenticated agent identities, rejected unauthorized/agent-as-admin/cross-origin requests, publication idempotency, live Nemotron matching, and administrator matcher health. Two successive pod replacements preserved publications, delivery IDs, retry results and acknowledgements. Temporary subscription was removed and probe deliveries acknowledged. A temporary probe on another cluster node reached the exposed NodePort and was deleted.
  - [x] Added docs/admin/kubernetes.md and linked it from README.md and docs/admin/operations.md; updated CHANGELOG.md. Documented credentials, private HTTP access, NodePort/proxy ports, single-writer placement, separate existing Docker state, offline backup prerequisites, restart procedures and local-path limitations. The deployment does not claim automatic failover or independently tested Kubernetes backup/restore.
- **Evidence:**
  - [x] Client and server dry runs passed; final server dry run reports resources unchanged. Final Deployment has both containers ready and the PVC is Bound. Eleven deployment checks pass in verification/kubernetes-acceptance.json, including cross-node NodePort health and the running artifact hash matching the accepted artifact. Configured credentials are absent from deployment logs. Exact image and artifact identities, manifest hash and live match evidence are retained in that report.
  - [x] Documentation links and git diff --check pass. Reviewed the documentation-update plan and recorded the current documentation authority marker. litai verify passes authority and both locks, skips configured source-intelligence/HTML gates, and fails only project.test_receipt_stale; refreshing that runtime receipt remains DOCS-002 follow-up. The config-command warning remains a confirmed false positive against current CLI help. Start/end peer surveys and issue/review listings report no open work or collectable branches/worktrees. No repository publication or existing-service shutdown was performed.

### [x] AGENT-001 — Connect this coding agent to the Kubernetes hub

- **Priority:** P1
- **Owner:** local agent configuration and coordination guidance
- **Direction:** Connect this agent to ADHD.
- **Conclusion:** Use the existing agent-a identity with an owner-only per-agent client file, install the documented SDK helper dependencies in an isolated workspace environment, subscribe and catch up through the coordination skill, publish session status, and add conditional checkout startup instructions without exposing credentials or claiming automatic background synchronization. Connected successfully as agent-a in project adhd through the existing SDK helper; the conditional startup instructions and private local configuration preserve the connection setup for subsequent coding sessions.
- **Depends on:** none
- **Implementation:**
  - [x] Created ignored mode-0600 literate.hub.local.json containing only agent-a credentials and its public URL; installed tests/requirements.txt in _build/tools/a2a/hub001. Verified identity, created and reused subscription sub-6, searched history, and published connection status pub-7. Received and acknowledged a private self-addressed inbox probe. Recognized historical pub-2 as synthetic deployment-test input and published clarification pub-10 so it cannot be mistaken for an actual API change.
  - [x] Added conditional coordination requirements to AGENTS.md and CLAUDE.md, documented checkout setup and explicit polling in docs/user/using-the-hub.md, and added the Unreleased changelog entry. No MCP server or background poller is claimed or installed.
- **Evidence:**
  - [x] All SDK connection checks passed; verification/agent-connection.json retains identity, subscription/publication IDs, permissions and inbox evidence. A temporary cluster NodeNotReady event restarted both containers during final checks; the agent reconnected, verified subscription persistence, retried the pending clarification with the same message ID, and confirmed successful publication. Existing incoming queues were empty; the acknowledged self-check does not reappear.
  - [x] Changed documentation links and git diff --check passed; pip check found no broken requirements. Documentation drift plan reviewed and authority marker refreshed. litai verify passes authority and locks, skips configured source-intelligence/HTML gates, and retains the known stale runtime receipt under DOCS-002; no fresh service build is claimed. Start/end peer surveys and issue/review listings report no open or collectable work. Future sessions follow repository guidance; processing occurs only while an agent explicitly publishes/polls.

### [x] INFO-003 — Answer from current facts while preserving report history

- **Coordination:** Renumbered from the uncommitted local INFO-002 after pulling the upstream contextual-evidence entry with that ID. Existing upstream IDs and dependencies are preserved.

- **Priority:** P1
- **Owner:** hub information model, current-fact resolution and query contract
- **Direction:** Keep historical reports, but answer what an agent is doing or who is working on a branch using the latest applicable information, including later completion reports.
- **Conclusion:** Implemented current answers by reconciling original contextual reports at query time with an explicitly configured generative evaluator. Completion and late-event scenarios retain history and independent activity, with grounded provenance and uncertainty. There is no fixed domain-specific ingestion taxonomy. See components/hub/information/current-facts.md and docs/user/querying.md.
- **Depends on:** INFO-001
- **Implementation:**
  - [x] Defined intended current facts, supersession, effective order, correction requirements, conflicts, interpretation and current/history query behavior in components/hub/information/current-facts.md, registered as a named specification root; PROJECT.md records the product requirement. The following runtime work implements this contract.
  - [x] Added an independent acceptance contract covering free-text start/completion, reverse lookup, history, late events, multiple activities, conflicts, correction, inference failure, privacy, migration, retries and restart. Fresh executed scenarios are recorded in the completion evidence below.
  - [x] Updated README.md, docs/README.md, docs/user/stored-information.md, docs/user/hub-api.md, docs/user/using-the-hub.md and skills/agent/coordinate-via-hub/SKILL.md to explain archive-search semantics and the current-query workflow. CHANGELOG.md describes the requirements change with the implemented behavior.
  - [x] Define exact typed model interpretation/query schemas, correction representation and A2A commands/errors; validate actual model support independently of subscription relevance. The separate generative adapter is qualified independently.
  - [x] Generate, build and qualify the extended runtime through the authorized lifecycle; validate existing stores and current CLI/A2A compatibility before deployment.
- **Evidence:**
  - [x] Reviewed the documentation paths above against components/hub/component.md, information/spec.md, the new current-facts contract and existing archive acceptance scenarios in tests/information_cases.py. Existing native/SDK/container evidence was not rerun or rewritten. Documentation-update plan reviewed; its config-command warning is a false positive confirmed by litai config paths --help. Refreshed the documentation-review marker. Hub lock and both catalog audits refreshed; final litai verify passes authority and both locks, skips configured source-intelligence/HTML gates, and fails only the already-known project.test_receipt_stale. git diff --check passes. That planning-only receipt is superseded by the fresh completion evidence below.
  - [x] Start/end peer surveys and open issue/review listings succeeded with no open or collectable work. Verified hub identity agent-a/project adhd, reused sub-6, searched prior context and polled; no deliveries required acknowledgement. Published plan pub-22 through the coordination skill. No repository publication, cleanup or service replacement occurred.
  - [x] Pass native and independent SDK acceptance for current facts, history, uncertainty, durability, isolation and model failure; refresh lifecycle evidence before completion.

- **Completion evidence:** Linux artifact `b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`; `verification/roadmap-acceptance.json and roadmap-hub-acceptance.json`. [Implementation/documentation review](../architecture/roadmap-implementation.md) records the affected guides, source provenance, actual model checks, native/SDK/container/browser results and limitations. macOS is supported; fresh macOS execution was unavailable. Existing deployments are unchanged.
