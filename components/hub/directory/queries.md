---
name: Canonical source questions
summary: Durable owner-only query jobs and versioned peer source exchanges
kind: component
---
# Canonical source questions

This extends directory/spec.md and federation/spec.md.

## Canonical ownership and asynchronous source questions

New A2A source_query {op,question,sources?,aliases?,deadline_ms?}, one of sources or
aliases required. sources is 1..16 distinct SCOPEs; aliases is 1..16 distinct
{provider,host,tenant,alias} with corresponding SCOPE bounds. An alias selects a scope
only when all matching visible catalogs agree on its exact identity; zero matches
is unknown, multiple scopes is ambiguous. Question is 1..4096 bytes, deadline_ms
1000..120000 default30000. This is a source-qualified question; federated_query
remains broad project discovery and its answers must not claim canonical authority.
Agent documentation directs all questions ABOUT a known source through source_query.

Before ACK persist owner-scoped query ID, question, absolute deadline, selected source
or alias identities, peer-membership snapshot and pending status. Use ordinary A2A
actor/messageId deduplication. Max64 nonterminal source queries (separate from old
query budget). get_source_query {op,query_id} returns progressive current status;
cancel_source_query {op,query_id} durably cancels. Unknown404 domain NOT_FOUND, foreign
owner FORBIDDEN; get/cancel remain usable after federation is disabled. These jobs
never enter ordinary publication search, subscriptions, inboxes or feedback as facts.

SOURCE_QUERY is {id,project_id,owner_id,question,created_at,deadline_at,status,results,coverage}.
status pending|completed|partial|cancelled. results preserves requested scope/alias
order; each is {requested,scope|null,status,owner_server_id|null,owner_project_id|null,
response|null}. requested is exactly the input SCOPE or alias selector. Source status
pending|answered|unknown|ambiguous|conflict|unavailable|revoked. response is the existing
relevance RESPONSE plus server_id and scope; owner IDs accompany matches AND explicit
nonmatches. A nonmatch is absence of support in approved evidence, not denial that
this server owns the source. completed requires all requested scopes answered;
terminal unknown/conflict/ambiguous/revoked/unavailable yields partial, never completed.
coverage is configured-order {project_id,status} directory observations at the
last pending/result transition, using the directory status enum. Completed means
all requested scopes answered, not that every peer directory was available. An
established owner with a fresh canonical claim may answer despite unrelated
directory outages, with incomplete coverage reported explicitly. Unknown initial
ownership waits for complete visible directory observations before choosing an
owner. No late result after cancellation/deadline. Preserve old messageId replay results.
An already accepted and dispatched pending source job retains its pinned owner,
query ID and original deadline through restart and recovery. Cache expiry or a
transient lack of a fresh owner catalog alone MUST keep that result pending, with
unavailable directory coverage, until the original deadline or a fresh canonical
revalidation. Do not dispatch or accept answers through stale metadata. Once
revalidated, resume the original idempotent remote job; do not create a replacement
remote identity or extend its deadline. This retry rule requires the same owner
and retained admitted peer from the accepted membership snapshot. Explicit peer
removal, identity conflict, canonical revocation and expired deadlines retain
their terminal behavior. A new query without an already dispatched pinned result
still reports established-owner unavailability under the rules below.

Resolve canonical claims before any source-specific network question dispatch.
A replica, derived record or alias alone cannot be an owner. A unique currently
validated claimant can be pinned as owner; distinct simultaneous canonical server
claims produce conflict and no dispatch. Keep the established owner while its
catalog is unreachable/expired/withheld; return unavailable rather than choosing a
copy or accepting another unilateral claim. Remove an established claim only after
an authenticated fresh VISIBLE snapshot from that owner explicitly removes it, or
a local Admin explicitly removes that peer. Such revocation is recorded; a newer
competing claim cannot itself revoke an owner. A transfer consists of explicit old
claim removal then one unambiguous fresh new claim. When claims conflict, the UI
shows owners and asks operators to remove the incorrect claim on its owning server;
no last-write-wins override. Removing local claim is hot. Caches invalidate affected
source resolutions and in-flight answers immediately on observed revocation, peer
removal or local settings commit. Source metadata caches never confer ownership.

Send source questions only to the configured direct canonical peer, or evaluate
locally when this server is canonical. Do not forward through peers or discover new
network destinations from metadata. Split multi-source questions into independent
source jobs sharing the original question/deadline; never send the full set of
source identities to an unrelated owner. A remote owner sees only its own SCOPE.
Select/commit owner and catalog revisions, then recheck current ownership before
accepting or committing answers. Owner unavailability and incomplete directory
coverage remain explicit. Do not send the question to nonowners as a discovery step.

Versioned peer source_submit request exactly {protocol_version:1,op:"source_submit",
origin_project_id,origin_server_id,query_id,scope,question,deadline_at,owner_server_id,
catalog_revision}. Verify stable origin server against the pinned configured peer.
Verify owner_server_id is self and current visible catalog revision still claims
that exact scope canonical. Otherwise409 OWNERSHIP_CHANGED, no acceptance. A not-yet-learned origin server
pin returns503 DEPENDENCY_UNAVAILABLE; a known mismatched pin returns409
IDENTITY_CONFLICT. Retry the former within the original deadline; never adopt
an identity solely from a source_submit payload. Persist
incoming key (authenticated origin server,query_id,scope identity), exact command and
authorized scope evidence before202 {protocol_version:1,query_id,scope,status}.
Exact repeats return current status; changed commands conflict409. Snapshots contain
scope description and existing allowlisted project-public publication envelopes,
encoded total<=64KiB in configured order. Incoming source jobs share the existing
64 nonterminal incoming budget. No recursive dispatch.

source_status request {protocol_version:1,op:"source_status",origin_project_id,
origin_server_id,query_id,scope}. Return200 {protocol_version:1,query_id,scope,status}
and response only when completed. status pending|completed|expired|revoked. Check
own current canonical claim/generation again before evaluation completion and read;
revoked never returns old evidence. Use the existing short SystemOne typed relevance
evaluator on the scoped approved evidence; no generative response/model deployment.
Source questions include original question verbatim. The origin verifies exact
query/scope/server/project/model, all response shapes/bounds, and ownership freshness
before committing. Retry transport/429/5xx to the original deadline;401/403/404/409
mark unavailable/revoked as appropriate. No silent protocol downgrade. Retry-After
cannot extend deadlines. Restart preserves incoming/outgoing jobs, ownership pins,
cache freshness, replays and cancellation. Bound ownership pins to 4352 entries;
return RESOURCE_EXHAUSTED when a new pin would exceed that bound. Reject revoked evidence allowlists
before inference or response disclosure, including previously completed jobs. Never copy roles or ownership permissions.

## Independent acceptance

Use three real hubs and an independently written v1 peer client. Cover GitHub
foo/baz canonical owner and a copy, Slack workspace/channel and Jira tenant/project
scopes; exact provider/host/tenant collisions, aliases/renames, empty/large paginated
catalogs, invalid cursors/revisions/versions, and metadata privacy. Prove source
questions reach only the canonical owner; split multi-source requests, retain
provenance and explicit unknown/conflict/outage/deadline statuses. Exercise hot
claim revocation/transfer, stale caches and peer removal, cancellation/restart and
late replies without duplicate authoritative owners. Verify local and OIDC users
with equal/unequal emails correlate independently of IDs/providers while server
roles/agent ownership stay independent across a three-server chain. Include profile
updates and absent/malformed email, withheld profiles and remote role assertions.
Run published schema conformance, native SDK/legacy, Docker and browser regressions.


## Administrator access to query jobs

Admin full access includes discovery and source query records. Keep A2A owner
isolation for agents; expose separate Admin-only POST /admin/api operations:

- query_jobs {op,limit?,agent_id?,kind?}: limit1..100 default50, kind is
  discovery|source. Return {items:[{kind,query}],truncated}, newest created_at
  first with ID as deterministic tie-breaker. Include retained/removed agents'
  history; filters do not require an active agent. Expire pending jobs before read.
- query_job {op,query_id}: return {kind,query} or404 NOT_FOUND.
- cancel_query_job {op,query_id,message_id,confirm:true}: cancel a pending job
  durably and return {kind,query}; preserve other terminal states.

These are product mutations, not config edits: cancellation does not require or
advance config_revision. Product Admin mutation idempotency is scoped by immutable
authenticated Admin ID plus message_id, with exact decoded-command comparison.
Preserve old bearer-only global receipts for legacy-admin compatibility; other
users cannot collide with that namespace. Recheck current authorization inside
the serialized product writer before serving a cached mutation result. The
console Activity view lists these jobs and exposes confirmed cancellation only
to Admins. Developers/Viewers cannot inspect or cancel another agent's queries.
