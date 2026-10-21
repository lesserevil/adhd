---
name: Federation directory and canonical source routing
summary: Authenticated local catalogs, email correlation and owner-only asynchronous queries
kind: component
---
# Federated directory (FED-002, FED-003)

This contract explicitly extends federation/spec.md and protocol/spec.md. Keep the
unversioned submit/status protocol and existing query results compatible. New peer
operations use /federation/v1 only. This additive API profile is 1.1.0 under wire
major 1; inspect the published schema for operation capabilities. A peer missing
the new operations is unavailable for directory/source queries; never downgrade. No credentials, roles, group mappings or sessions
are transferable authority. Agents continue to use A2A.

## Stable identities and comparison

Persist an internal cryptographically random server_id (32 lowercase hex digits)
in the product store on creation/upgrade. It survives process/container replacement,
project_id renaming and live store moves. It is not operator configuration. Publish
server_id with the current project_id; configured peer project identity and bearer
credentials still authenticate each direct connection. Remember the first server_id
observed for each configured peer; unexpected replacement is an explicit identity
conflict, never silent adoption. Two configured peers advertising the same server_id
are also identity_conflict and cannot supply trusted directory entries until the
operator removes the duplicate. Removing/readding a peer explicitly resets its pin.
A copied backup must not run concurrently as a second server with the same identity.

A user is always locally identified by immutable user_id. Email correlation uses:
trim Unicode White_Space from both ends; require exactly one ASCII @ and nonempty
sides with no internal whitespace; ASCII-lowercase only the domain; preserve local
part case, dots and plus suffixes. Do not apply Unicode normalization, provider
aliases, plus removal or dot folding. Invalid/empty emails never correlate. Equal
comparison keys permit an identity match between trusted direct peers only; they do
not merge accounts, authenticate anybody, grant agent ownership or assign a role.
Never export or honor role/group/credential/session assertions through this exchange.

## Hot settings and bounded metadata

Extend federation settings with catalog and share_identities. Both are editable in
Admin Settings without JSON editing or restart. share_identities is boolean, default
false. catalog defaults {visible:true,entries:[]}. It has exactly visible (boolean)
and entries (array, at most 256). Each entry is exactly:
{scope:SCOPE,aliases:[TEXT...],description:TEXT,relationship:REL,canonical:BOOL,
 export_publication_ids:[ID...]}. aliases defaults [], up to 16 distinct nonblank
strings of 1..256 UTF-8 bytes; description is nonblank 1..4096 bytes; REL is
contained|derived|referenced; canonical is true only with relationship=contained.
export_publication_ids defaults [], at most 32 distinct IDs. They are an independent
Admin-approved export allowlist for that scope, not inherited permission to export
any linked or private information. Missing records are omitted; private deliveries
never qualify. Scope IDs are unique within a catalog. Encoded public catalog metadata is at most 128 KiB. visible=false returns an empty
withheld catalog and does not assert that this server has revoked previous claims.

SCOPE is exactly {provider,host,tenant,resource}. provider is github|slack|jira|other;
host is lowercase ASCII DNS name or IP, no scheme/port/path, 1..253 bytes; tenant and
resource are nonblank opaque case-sensitive strings 1..256 bytes. Tenant identifies
the provider workspace/site/organization, never the server's project display label.
Use provider-native stable resource IDs when available. A GitHub owner/name, Slack
channel name or Jira key may be an explicit alias for a stable resource. Equal names
on different providers/hosts/tenants are distinct. Scope identity is SHA-256 of the
canonical JSON object (UTF-8, sorted keys, compact JSON, no floats). No wildcard or
implicit parent scope exists: arrays represent sets of exact resources. Renames
preserve scope identity and update aliases; an alias must never replace a stable ID.
Aliases are case-insensitive ASCII for github, case-sensitive for other providers;
collisions remain explicit ambiguity. Do not guess an owner from display names.

A locally configured canonical claim is an operator assertion; it is not a signature
from GitHub/Slack/Jira and does not implement external-source ingestion. Preserve
contained/derived/referenced information separately from ownership. Only canonical
claims can authorize source-specific answer dispatch.

## Peer requests and pagination

Authenticate all directory requests exactly like existing peer requests before body
decoding. Each request has protocol_version:1 and origin_project_id equal to the
configured authenticated peer. Unknown keys are rejected. All peer results also
include protocol_version:1. Keep decoded response bound 256 KiB and no redirects.

catalog request: {protocol_version:1,op:"catalog",origin_project_id,cursor?}.
identities request: {protocol_version:1,op:"identities",origin_project_id,cursor?}.
Both return HTTP200 {protocol_version:1,server_id,project_id,revision,generated_at,
max_age_ms:10000,visible,items,next_cursor}. revision is lowercase SHA-256 of canonical JSON {visible,items}, over all pages. generated_at is current UTC milliseconds. items contains at most 64
entries. catalog item adds no fields to its configured public entry except omitting
export_publication_ids: publication bodies/IDs are not directory metadata. identity
item is exactly {user_id,name,email}, never roles or OIDC tokens/provider credentials.
Export only enabled profile-complete LOCAL records, not cached peer profiles; issuer
and subject remain server-local. Identical email may appear on multiple distinct
local accounts; correlation returns all such records without merging them.
share_identities=false returns visible:false, items:[], next_cursor:null. An empty
visible catalog/profile list still returns a complete valid snapshot. Snapshot
revision covers visibility too. No peer-supplied reply URL or network destination.

cursor is opaque to clients, 1..256 bytes, bound to request type, snapshot revision
and offset. The first request omits cursor. next_cursor is string or null. A changed
snapshot during pagination returns409 SNAPSHOT_CHANGED and the client restarts from
page one; an invalid cursor returns400 INVALID_PARAMS. A client verifies consistent
server/project identity, revision, generation/freshness and <=256 catalog or <=1000
identity entries, no duplicate scope/user IDs, no repeated cursor, and no extra keys.
Discard incomplete or conflicting snapshots. Expiry is generated_at+max_age_ms, never
extended by reception, restart or relaying. A future generated_at beyond 1s or already
expired snapshot is unusable. Persist local observations and absolute expiry.

Directory requests read local state only and never contact another server. Periodic
hub workers refresh configured direct peers asynchronously, at most four network
operations concurrently, sharing existing federation timeout/retry bounds. Persist
bounded caches (16 peers, 256 scopes and 1000 profiles per peer) with source server,
authenticated peer, revision and expiry. Network I/O stays outside the writer.
Never relay cached metadata as local ownership/profile claims. Disabled/removed peers
and configuration generations fence all in-flight work; discard stale completions.

## Local directory and identity APIs

A2A federation_directory {op} returns {server_id,project_id,catalog,peers}; local
catalog is the visible current snapshot, peers are configured-order observations
{project_id,server_id|null,status,revision|null,expires_at|null,catalog:ITEMS}.
status is pending|ready|unavailable|withheld|identity_conflict. Return only current,
visible, unexpired metadata; an outage is not an empty authoritative catalog.
An authenticated agent may read directory metadata. No secret endpoints/tokens.

A2A identity_matches {op} uses the authenticated agent's owner_user_id. No assigned
local user returns FORBIDDEN. Result {user_id,matches,coverage}; matches are
{server_id,project_id,user_id,name,email,observed_at,expires_at}, ordered by configured
peer then remote user_id. coverage is per-peer {project_id,status}; status also
allows identities_withheld. Match only a current valid local email against a current
validated peer snapshot. A local profile change applies immediately; remote changes
are bounded by the 10-second expiry and shown observation/expiry times. Never
transfer local roles through direct matches or through a three-server chain.

Admin-only federation_directory {op} adds cache diagnostics without secrets.
Admin-only identity_matches {op,user_id} permits selection of a local user.
Admin-only refresh_federation {op,message_id,expected_revision,confirm:true} persists
an asynchronous refresh request and returns {queued:true,config_revision}; no
network calls in the HTTP request. It uses configuration command authorization,
revision/conflict/idempotency rules; it does not rewrite peer credentials or pretend
refresh completion. Settings lists peer cache state and offers Refresh directory.
Users can inspect same-email matches; only Admin can select other users.


## Bootstrap identity invariant

The bootstrap user's server-owned built_in:true marker persists independently of
its username/name/email. Migrate an existing local username admin to this marker
before allowing edits. Never link a marked user to OIDC, including after rename;
clients cannot set/clear the marker. Keep it out of public profile/config results.
