# Agentic Distributed Harness Depot (ADHD)

## Purpose

ADHD is an A2A-based information hub. It lets agents communicate through a shared
server even when they cannot connect directly to one another. It also collects
information from agents and other sources, distributes relevant information to
subscribers, and lets agents query or search the hub over their A2A connection.

Each agent needs a way to reach the hub; peer-to-peer connectivity is unnecessary.
Elixir is the project's default implementation language. ADHD expands to
Agentic Distributed Harness Depot; Depot is the agreed product name. The `adhd`
namespace, configuration paths and protocol identifiers remain unchanged.

## First working version

The first use case is two agents working on the same project and keeping each
other informed about their work. Two is the initial acceptance case, not a limit
on the number of agents. The hub conveys what agents report; it does not itself
assign tasks or establish exclusive ownership of files or work.

The agreed starting scope is:

- One private hub for trusted agents.
- Durable storage for published information, subscriptions, and queued deliveries.
- Agents poll for queued deliveries and acknowledge receipt. Polling alone does
  not permanently remove an item; an unacknowledged item remains available for
  delivery. Clients must tolerate repeat delivery.
- Accepted information, subscriptions, and unacknowledged deliveries survive
  server restarts and agent disconnections.
- A replaceable decision-model integration, initially using Nemotron Deciffusion
  8B v2.1 from the user-provided internal weights repository. Jev API access is
  not required. The decision threshold remains to be selected and evaluated.
- Subscriptions match new publications after subscription creation. Existing
  information remains available through query/search rather than automatic replay.
- Agent-published text and JSON, with basic search over stored publications.
  Non-agent ingestion adapters are a later extension.
- Stored information includes an extensible information type (initially message
  and status), source provenance, occurrence and ingestion timestamps, and arbitrary
  JSON content. Clients can retrieve a publication by ID and search history with
  source/type filters, independently of subscriptions and acknowledgements.
- Retain DETS for live MVP testing. External connectors will use the same ingestion,
  storage, subscription, and search contract; their live integrations come later.

### Two-agent coordination example

Agent A works on an API and Agent B works on its client in the same project.
Each publishes information about its current work, progress, blockers, interface
changes, and completed work as appropriate. These are example subjects rather
than a required fixed taxonomy.

Agent B could subscribe with: “Updates about API request or response changes,
backend blockers affecting the client, and work that overlaps my client tasks.”
Agent A could subscribe with: “Client integration problems, requested API changes,
and client progress that affects backend work.”

When Agent A publishes “I am changing the task response to include a status field,”
the matcher evaluates that publication against Agent B's subscription. A match is
queued for B, which polls, receives the update, and acknowledges it. B can publish
its own response or send A an addressed message. If B was offline, it can receive
the queued update on return and search earlier project publications for context.

## Required behavior

### Agent communication

An agent can submit a message addressed to another agent through the hub's A2A
interface. The hub queues it for the recipient rather than requiring a direct
connection between the agents. A recipient that is disconnected can receive its
queued messages after reconnecting.

### Information publishing

The hub accepts published information from agents and other information sources.
Published information is available for subscription matching and for queries or
search. Direct messages and published information have distinct purposes:
addressing a message to an agent does not by itself publish it to subscribers.
The first version accepts agent-published text and JSON. Adapters for non-agent
sources are a later extension.

The common publication envelope distinguishes the authenticated submitter from
the claimed original source. Source-item identities allow connector retries to
avoid duplicate records and deliveries. Status updates form an immutable history.
Published project information remains searchable after delivery acknowledgement;
private addressed messages remain outside project search and public-ID retrieval.

### Plain-text subscriptions

An agent subscribes by supplying a plain-text description of the information it
wants to receive. The server uses a relevance model to determine whether newly
published information matches that description. Matching is based on meaning;
agents do not need to encode their interests as topic names or filter expressions.

For each matching subscription, the hub queues the information for the subscribing
agent. Nonmatching information does not produce a delivery for that subscription.
Each subscription is evaluated independently, so one publication can be queued for
multiple agents. Queuing does not depend on the subscriber being connected at the
time of publication.

“Jev-like” means a model that makes typed probabilistic judgments from supplied
context and natural-language criteria. The hub supplies the publication as context
and each subscription as the criteria for a focused relevance question. The model
returns a typed probability that the publication satisfies the subscription. Hub
policy converts that probability into a match decision and queues matching items.
The matching result is consumed directly by software without parsing generated
prose. Independent subscription questions may be batched against the same publication.

The initial model is Nemotron Deciffusion 8B v2.1; the interface remains replaceable.
The threshold and inference deployment remain to be selected. A match probability expresses the
likelihood of relevance, not a graded measure of how relevant the item is.
Its calibration must be evaluated on representative project updates rather than
assumed from the shape of its output.

The user's reference is [Jev on Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)).
The primary [TypeSafe question documentation](https://docs.typesafe.ai/primitives)
describes typed questions, independent evaluation, and the Noul primitive, which
returns the probability of a yes answer without a separate confidence field.

### Queries and search

An agent can use its A2A connection to query or search information held in the hub
and receive the result through that connection. A subscription is not a prerequisite
for a query or search. The MVP supports retrieval by publication ID, literal
case-insensitive text/JSON/provenance search, and exact information-type/source
filters. The next retrieval program is recorded in
[adaptive retrieval](docs/roadmap/adaptive-retrieval.md), with six dependent
requests in [active work](docs/roadmap/active-work.md).

### Contextual evidence and adaptive retrieval direction

Preserve full statements and the questions, subjects, conversations and evidence
relationships needed to interpret them. New questions must not require users to
predict domain fields or indexes. Originals remain authoritative; extracted
interpretations, embeddings and indexes are replaceable derived data.

Support natural-language evaluation over contextual history, including a complete
scoped scan when indexes cannot provide useful evidence. Search-then-scan first
retrieves candidates, assesses their sufficiency for the actual question, and
falls back to scanning original records when needed. Answers identify their
sources, contradictions, uncertainty and actual coverage; a partial scan is not
exhaustive and missing evidence is not a negative fact. Sample apparently
successful searches for scan audits to discover hidden misses.

Retain search/scan comparisons and replay failed searches to diagnose recurring
misses. Use those observations to generate and evaluate retrieval improvements,
including new indexes when warranted, rather than anticipating all indexes in
advance. Candidate indexes must pass held-out and regression evaluation before
promotion, with bounded work, versioned recipes and rollback. Context, chunking,
ranking or interpretation defects may call for remedies other than a new index.

INFO-002, QUERY-001, SEARCH-001 through SEARCH-003 and INDEX-001 record this future
work and its acceptance gates. These requirements do not claim the current MVP
implements semantic historical queries or adaptive indexing.

## Acceptance scenarios

- Two agents working on one project publish work updates and subscribe using
  plain-text descriptions. Relevant updates from each are queued for the other,
  and both agents can search earlier published project information.
- An agent polls a queued item without acknowledging it. The item remains
  available; after acknowledgement it is no longer pending for that agent.
- The server restarts after accepting a publication and creating a queued match.
  The publication, subscription, and unacknowledged delivery remain available.
- An agent creates a subscription after a publication exists. The publication is
  searchable but does not create an automatic historical subscription delivery.
- Two agents cannot connect to one another but can reach the hub. A message sent
  through the hub is queued for the addressed agent and can be received by it.
- An agent is disconnected when another agent sends it a message. The message
  remains queued for receipt when the recipient reconnects.
- An agent publishes information and the matcher judges it relevant to a
  subscriber's plain-text request. The hub queues it for that subscriber.
- A non-agent source publishes information. It participates in the same
  subscription-matching and query/search behavior as agent-published information.
  This is a later-extension scenario outside the first working version.
- The matcher judges a publication irrelevant to a subscription. No delivery is
  queued for that subscription.
- Given a publication and a plain-text subscription, the matcher returns a typed
  probability of relevance. The hub applies its matching policy to that value;
  generated explanatory text is not needed for the decision.
- Two agents have matching subscriptions. The publication is queued for both,
  including a subscriber that is currently disconnected.
- An agent queries or searches over A2A without subscribing. The hub returns the
  query/search result through the A2A connection.

These are product acceptance requirements, not evidence of an implemented service.

## Decisions still needed for later versions

- Matching threshold calibration and broader relevance evaluation. The prototype
  uses the concrete SystemOne schema, an initial threshold of 900000 parts per
  million, and durable background retries on model failures.
- Additional protocol bindings and versions beyond the prototype's A2A 1.0
  JSON-RPC SendMessage operations.
- Containerized service operation is required. The first deployment recipe uses
  a Linux Docker host, a pinned Elixir runtime, private configuration mounts, and
  durable data outside the container. Production orchestration remains open.
- The production deployment environment. A private GPU test endpoint now serves
  the selected checkpoint and has passed two relevance smoke checks. Initial
  interoperability testing will use the official A2A Python Hello World sample
  and SDK client as a starting point, followed by two scripted agent identities
  exercising the hub's coordination operations. No specific agent framework is
  required of product users.
- Credential management beyond per-agent bearer tokens in a private configuration
  and any future multi-project access model.
- Retention, migration, and scaling beyond the prototype's single-process OTP
  disk store, stable delivery identifiers, explicit acknowledgements, and retries.
- Concrete evaluator/retrieval adapters, query-job API, resource budgets and
  promotion thresholds for the accepted adaptive retrieval direction. Domain
  schemas and advance prediction of required indexes are not user prerequisites.

Push notifications, automatic subscription history replay, multi-organization
hosting, and non-agent ingestion adapters are outside the first working version.

## Initial integration references

- Model weights: the user-provided
  [Nemotron Deciffusion 8B v2.1 repository](https://gitlab-master.nvidia.com/asteiner/nemotron-deciffusion-8b-v2.1-weights),
  inspected at commit `d80a66a22c7640bcaefd2d71ea04ad14541e1822`.
  Its README supplies BF16 and NVFP4 variants and identifies a serving container.
- Test peer: the official
  [A2A Hello World sample](https://github.com/a2aproject/a2a-samples/tree/main/samples/python/agents/helloworld)
  supplies a small server and SDK test client. The sample alone does not test
  hub publishing, subscriptions, polling, acknowledgements, or search; those
  require a hub-specific two-agent scenario. The hub remains Elixir; the Python
  sample is an interoperability fixture.
- Serving integration details and outstanding prerequisites are recorded in
  `docs/architecture/model-integration.md`.

## Current status

The Elixir MVP supports durable message/status history, source provenance, event
and ingestion timestamps, arbitrary JSON publication content, retrieval by ID,
source/type-filtered search, semantic subscriptions, and durable source-event
retry deduplication. DETS remains the approved prototype backend. A startup
upgrade preserves the original prototype's stored history and delivery state.

The current runtime passed 5 native cases, 31 independent host SDK scenarios
(including real schema-1 and schema-2 store upgrades), and 33 container scenarios. The
container suite covers real Nemotron matching, hard restarts, replacement,
offline backup/restore, and rollback. Two clean image builds produced the same
identity. A deployed container also passed a live two-agent status/archive smoke
test; private per-agent files and access instructions support live MVP testing.

The hub's contract is `components/hub/component.md`. Setup and usage are documented
in `docs/user/getting-started.md` and `docs/user/hub-api.md`. Independent HTTP/model
evidence is retained in `verification/hub-acceptance.json`; lifecycle evidence is
recorded separately by Literate AI. No standalone package, public deployment, or
production matching-quality guarantee is claimed.

Container packaging and service operations are documented in
`docs/admin/operations.md`; client onboarding is in `docs/user/using-the-hub.md`.
Container and recovery evidence is in `verification/container-acceptance.json`,
reproducibility evidence in `verification/container-reproducibility.json`, and
live-deployment checks in `verification/live-mvp-smoke.json`.

The administrator console is specified in components/hub/management/spec.md and
operated using docs/admin/web-console.md. Its optional separate credential grants
project-public observation, subscription management and pending-job retries; private
addressed payloads remain hidden. UI-001 is implemented; verification/web-console-browser.json and
verification/web-console-live-smoke.json record desktop/mobile interaction and live
deployment evidence. The private MVP retains its prior agent state after replacement
and restart, and exposes the console at its existing private HTTP URL.
