---
name: Shared resource admission
summary: Bounded fair per-project model, network and event-transport admission
kind: component
---
# Shared resources across projects

A server shares finite outbound work capacity across its projects. Admit model
requests, ordinary peer/identity network requests and Kafka event-transport
requests into three independent lanes. Model absence, outage or a full model lane
must not occupy the eventing lane. A model filter is optional work after transport
materialization; a raw subscription never acquires a model slot.

The hot server-wide `resources` object accepts exactly these integer fields:

| Field | Default | Inclusive range |
| --- | --- | --- |
| `model_concurrency` | 4 | 1..256 |
| `project_model_concurrency` | 1 | 1..256 |
| `network_concurrency` | 16 | 1..256 |
| `project_network_concurrency` | 4 | 1..256 |
| `eventing_concurrency` | 16 | 1..256 |
| `project_eventing_concurrency` | 1 | 1..256 |
| `max_waiters` | 1024 | 0..4096 |

An omitted object or omitted field uses its default. Reject unknown fields, null,
booleans, strings, fractions and out-of-range values. Per-project limits greater
than a lane's server limit are valid; both limits apply. These are server limits,
not project overrides. Configuration-file location remains the sole hub restart
setting. Reductions apply to new grants; running requests retain their slots and
complete or fail through their original deadline/authorization rules. Never kill
accepted requests just to make a lowered limit appear satisfied.

Each lane uses FIFO order within each project and round-robin turns across
eligible projects. A project at its own active limit does not block another
eligible project. A project newly entering a lane joins behind projects already
waiting; multiple queued requests do not give it multiple turns. The maximum
retained waiting entries is `max_waiters` across all lanes. A free slot may be
granted despite a full waiting queue; a model backlog cannot reserve the free
slots of the eventing lane. Queue rejection is explicit backpressure, not a
negative semantic decision, a lost original or a successful delivery.

Bound admission before sending requests to the scheduler. Each lane may retain
at most its server concurrency plus `max_waiters` atomic ingress tickets. A ticket
contains only its request reference, project-independent slot, owning process and
deadline. Previously admitted tickets survive a hot reduction until their owners
finish or are fenced; the absolute ceiling is 4352 tickets per lane. A ticket
must be released after completion, error, queue timeout or caller
death. Garbage collection of a process killed between ticket allocation and
scheduler admission must prevent leaked capacity. Periodic cleanup must also
remove stale queue references; abandoned requests must not accumulate in a queue
behind a permanently occupied slot. Caller processes outside the hub are outside
this scheduler's memory guarantee; HTTP ingress retains its own admission bounds.

Measure one monotonic deadline before waiting. Queue residence consumes the same
request timeout budget as the eventual HTTP call. On a grant, pass only the
positive remaining milliseconds to the HTTP operation. The network adapter must
honor that remaining timeout for connection, response and cancellation; the
scheduler does not make arbitrary application callbacks preemptible. Do not
release a still-running request's slot merely because a diagnostic deadline has
elapsed. Release it after the bounded HTTP operation finishes or its owning
process exits. Monitor owners so exceptions and killed workers cannot strand
active or queued capacity. Register each asynchronous HTTP request ID with its
active resource ticket immediately after dispatch and before waiting for a
response. Allow only one outbound request ID per callback. If registration fails,
cancel that HTTP request and fail admission explicitly. Owner death cancels its
registered local HTTP request as well as releasing capacity. Cancellation stops
the local client request/connection; it cannot promise that a remote provider
aborts computation it has already accepted. Native unit calls before scheduler
startup may omit tracking; an already-started runtime may not silently omit it.

Fence queued requests against the current configuration revision and project
lifecycle immediately before execution. A changed revision invalidates prepared
old endpoints, credentials and membership assumptions: return `CONFIG_CHANGED`
without making the HTTP request. An archived project returns `PROJECT_ARCHIVED` for model and ordinary network
work; a removed or unknown project returns `PROJECT_NOT_FOUND`. The eventing lane
may continue transporting already accepted outbox/fan-out work for an archived
project, subject to the current revision fence. This narrow drain exception does
not authorize new publications, subscriptions or model work in an archived project. The caller preserves
its durable accepted work and retries or pauses using current policy. Requests
already executing retain the existing generation, ownership and authorization
checks before committing a result; a slot grant never grants data access.

A full or expired model admission returns `MODEL_BUSY`; corresponding ordinary
network and event-transport failures return `NETWORK_BUSY` and `EVENTING_BUSY`.
These stable errors are retryable admission failures. They must not become a
negative match. The model/backend ledgers may already have reserved a budget
before seeking a slot. A reservation or an uncertain attempt must not be described
as a completed/observed inference call. Distinguish scheduler grants from actual
HTTP calls and provider responses. Admission timeout before invocation makes no
HTTP request and consumes no provider token usage.

Expose only counts, effective limits and stable project IDs in Admin diagnostics:
active and queued entries per lane/project, grants, queued timeouts, full-queue
rejections, revision/lifecycle fences, caller-death cleanup and early ingress
rejections. Metrics must not contain URLs, request bodies, prompts, tokens or
user/provider credentials. Historical aggregate counters are process-local
operational metrics; durable query/publication accounting remains authoritative.
Readiness of the hub and raw publication/search does not require model capacity.

Qualification must saturate one project's slow/failing model and peer work while
another project's authorized work progresses. Test global and per-project caps,
FIFO and round-robin order, hot reductions, finite queues, deadline consumption,
queued revision and archival fences, exception/caller-death cleanup and raw
Kafka progress while model work is occupied. Record actual HTTP observations
separately from granted/reserved work and preserve accepted data through restart
and project lifecycle changes.

## Admin resource diagnostics

The read-only, server-scoped Admin command is exactly
`{"op":"resource_status"}` with no project selector. Require the Admin role;
Developers and Viewers must not receive a global project inventory through this
command. It returns `started`, effective `limits`, total `waiting`, total
`ingress_tickets`, and `lanes` keyed by `model`, `network`, `eventing`. Each lane
contains `active`, `queued`, `grants`, `queued_timeouts`, `queue_rejections`,
`fenced`, `caller_deaths`, `ingress_rejections` and `projects`; project entries
contain current `active` and `queued` counts. All counts are nonnegative integers.
When the admission service has not started, native CLI/unit diagnostics may return
`started:false` and effective limits without lane state. Once runtime admission
has started, unexpected scheduler loss fails subsequent admission closed; it must
not silently switch a live service to unlimited direct HTTP execution.
