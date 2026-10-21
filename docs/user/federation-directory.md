# Source ownership and federated identities

Each hub remains a single-project server. Its persistent server ID identifies the
installation independently of its project display name. Configure direct peers in
Admin **Settings**; their separate inbound/outbound bearer credentials establish
trust. Metadata never introduces another network destination or inherits a role.

## Publish an information catalog

In Settings, enable federation and describe the project. Under **Information
catalog**, select **Publish information catalog**, then **Add source**. Specify:

- Provider, lowercase host, tenant/workspace/site identity, and stable resource ID.
- A description and optional aliases such as `foo/baz`, a Slack channel name, or
  a Jira key. Prefer provider-native stable IDs so display-name changes need only
  update aliases. Different hosts, tenants and providers remain distinct.
- Whether information is contained, derived or merely referenced. Select
  **Canonical owner** only for a contained source this server owns.
- Explicit approved project-public publication IDs if source questions may use
  evidence beyond the description. Private addressed messages cannot be exported.

Validate, then confirm and save. All of these settings are hot. Peers retrieve
bounded paginated metadata snapshots and may cache them for ten seconds. Catalogs
export source descriptions and ownership claims, never publication bodies,
allowlist IDs, credentials, user roles or private messages. A hidden catalog is
withheld information; it does not revoke an existing ownership claim.

Ownership is an operator assertion within the configured federation. It does not
prove control of GitHub/Slack/Jira or ingest those systems automatically. An empty
published catalog is valid. **Refresh directory** queues background refreshes;
it does not claim that remote servers have already answered.

## Ask the canonical server

Use `federated_query` for broad project discovery. Its matches describe projects
and do not establish canonical authority over an external source. Agents must use
`source_query` for questions about a known repository, channel or project. Read
`federation_directory` to discover approved scope identities and aliases first.
These are A2A DataPart commands, not new A2A RPC methods:

```json
{"op":"source_query","question":"Which work updates describe the API change?","aliases":[{"provider":"github","host":"github.com","tenant":"org-123","alias":"foo/baz"}]}
```

Alternatively supply `sources` with exact `{provider,host,tenant,resource}` objects.
Do not supply both selectors. Creation persists a pending owner-scoped job before
acknowledging. Poll `get_source_query` with its `query_id`; use
`cancel_source_query` to stop collection. Retrying a mutation with the same A2A
messageId and command does not create another job.

A source question goes only to its canonical direct peer, or is evaluated locally
when this hub owns it. Copies cannot answer authoritatively. Multi-source requests
split by source while sharing the question and deadline. Results preserve the
requested order and include stable owner/server and source provenance. Directory
coverage is reported separately: a known fresh owner can answer during an
unrelated peer outage without claiming complete federation coverage. The short
relevance model selects approved evidence; it does not synthesize an invented
answer. A completed nonmatch means the approved evidence did not support the
question, not that the server lacks the source.

Unknown or ambiguous scope, conflicting claims, revoked ownership, stale metadata
and unavailable owners remain explicit partial results. A failed owner is never
replaced with a convenient copy. Resolve a conflict by removing the incorrect
canonical claim on the server that published it. Transfer ownership by removing
the old claim, refreshing its visible catalog, then publishing one new claim.
Hiding an old catalog or advertising a newer competing claim is not a transfer.
An expired/unreachable established owner remains unavailable until authenticated
revocation or explicit peer removal permits re-resolution.

## Correlate users without copying access

**Share user identities** is off by default. Enabling it exports only enabled,
profile-complete local user IDs, names and emails to trusted direct peers. Both
local-password and OIDC-backed accounts qualify; tokens, provider assertions,
groups, roles and agent ownership never leave through this interface.

An agent's `identity_matches` command compares its assigned owner's current email
with fresh peer profiles. An unowned agent is denied. Admins can inspect a user's
matches from Users, using **Find federated identities**. Results include their
source server and observation/expiry times. Matching emails correlate people;
they never merge local accounts, authenticate a remote user or grant permissions.

Comparison trims surrounding Unicode whitespace and folds ASCII letters in the
domain only. The local part remains case-sensitive; dots and plus suffixes are
preserved. Empty/malformed addresses do not match. Remote changes are visible
through refresh/expiry; local profile changes apply immediately.

An Admin here can be a Viewer elsewhere. A third server does not acquire the
first server's profiles or roles through an intermediary. Each server enforces
its own users, OIDC groups and agent ownership. Unexpected replacement of a peer's
stable server ID, or duplicate server IDs, produces an identity conflict. To
accept a replacement, explicitly remove and save the peer, then add and save it
again. Do not run two live servers from copies of the same store backup.

The [protocol reference](../protocol/README.md) publishes exact schemas, bounds,
status/error mappings, pagination, durable state transitions and retry rules.
