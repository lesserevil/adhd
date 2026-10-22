---
name: Live hub configuration
summary: Durable revisioned settings and atomic reconfiguration without hub restart
kind: component
---
# Live configuration (CONFIG-002)

This is an explicit extension of component.md and management/spec.md. Replace their
startup-only configuration and fixed admin-only API assumptions with this contract.
Only the absolute CONFIG_FILE startup location is fixed for a running process.
Internal entity IDs, revisions and derived statuses are not operator settings.
directory/spec.md extends hot federation catalog/identity-sharing settings; its
server-owned directory identities and observations are not configuration.
All actual settings, including project_id, store_path, port, public_url, agents,
matcher, threshold, federation, authentication and roles, are hot and editable from
the console. Preserve legacy configurations, exact CLI describe and existing A2A.

## Persistence and revisions

A configuration service owns the current validated snapshot and monotonic integer
`config_revision`, initially 1 when absent. Persist settings separately from DETS;
configuration credentials and password hashes must never enter the product store,
idempotency history, logs or diagnostics. Store the absolute configuration location
privately and resolve relative store paths against its directory. Read live config
for every authorization and worker dispatch; no worker/listener may retain startup
credentials, endpoints, thresholds or permissions indefinitely.

Validate the entire proposed snapshot before mutation. Newly set/rotated agent,
admin and peer HTTP bearer credentials use ASCII RFC6750 b64token characters
(A-Z a-z 0-9 - . _ ~ + / with optional trailing =), maximum 4096 bytes, and
their existing minimum lengths. Reject unsafe/unusable values before activation,
including through external file reload. Preserve unchanged legacy credentials;
only canonical header credentials count as a usable key when removing other
Admin sign-in paths. Passwords and OIDC client secrets retain their own contracts. Serialize updates with
expected_revision; stale writes return 409 CONFIG_CONFLICT with current_revision
and no submitted values. All settings commands use message_id (1..128 bytes),
confirm:true and a separate configuration idempotency journal beside CONFIG_FILE.
Persist only a command digest and redacted result, never submitted secret values.
Same ID/same command returns the original sanitized result; changed command is
409 IDEMPOTENCY_CONFLICT. Journal and configuration files are owner-only (0600),
with safe atomic replacement and fsync before success; never follow symlink targets.
A failed write or invalid destination must not activate any part of the proposal.

Poll CONFIG_FILE at most every 500ms for external edits. Apply a valid change
through the same transaction and advance the revision. Invalid edits retain the
last good running config and expose only a generic reload error/status to Admins.
A malformed file at cold startup fails closed. Own saves must not trigger a second
revision. Never silently overwrite a changed file with a stale in-memory version.
Use an atomic journal/recovery protocol for config and store changes: after hard
kill during a mutation, startup must recover one complete old or new transaction,
never a mixed config/store/listener identity. Never reset accepted product data.

The [hot backend relocation contract](../storage-relocation/spec.md) extends
store_path changes to every project, including installations without a default
project, and defines the durable all-writer decision and single-owner recovery
scope.

project-recovery/spec.md adds the hot Admin-editable root recovery settings and
external route/decision journal. Selective restore never installs a backed-up
configuration or advances its current revision. Recovery and configuration/route
decisions serialize; unknown or initialized-missing target availability must not
prevent global Admin authentication/control. All routes use the current registry.

## Project identity and independent model capability

The multiple-project contract preserves aliases created by earlier single-project
renames. A requested historical alias resolves to its current canonical project
only when the authenticated actor is admitted to that project. Unknown and
inaccessible aliases return PROJECT_NOT_FOUND identically. Resolve before resource
lookup, cache lookup or dispatch; an alias grants no membership. Preserve the
original command exactly for mutation idempotency, including its historical
project_id, so old cached results replay verbatim. Newly accepted results use the
canonical current project. Registry validation, configuration dry validation,
file reload and startup reject redefining any existing project's historical alias
as a different project, including an otherwise empty new project. A legacy rename
within the same logical project may return to one of that project's own aliases.

A subscription matcher is optional. Its absence rejects filtered subscription
creation but must not disable separately configured backend models. History uses
its effective history URL/model, retrieval its effective retrieval URL/model,
and archive its effective archive URL/model (including its established history
inheritance). Replay requires both effective retrieval and archive capabilities.
Return MODEL_UNAVAILABLE only for an absent required effective URL/model; retain
the owning feature's enabled, authorization, budget and lifecycle checks. Plain
publication, raw subscriptions, literal search, poll and acknowledgement do not
require any of these model capabilities.

A hot configuration update, dry validation or file reload MUST reject removing
an admitted project or collapsing a multiple-project installation to legacy
single-project mode, including deleting/nulling the project registry. Preserve the
stable server/default-project identities. Return CONFIG_APPLY_FAILED (HTTP409)
for these identity/registry transitions without changing configuration, revision,
memberships or retained project state. A downgrade requires the documented offline
restore of the matching pre-upgrade backup; deleting configuration fields is not
a downgrade procedure.

## Live effects and failure rollback

- Agent/admin token replacement or removal applies to the next request. Removing
  an agent keeps its historical publications, subscriptions and inbox; no other
  agent gains ownership. Disabled agents cannot authenticate or receive new work.
- Matcher URL/model, timeout/retry and threshold changes apply to future attempts.
  Tag network work by configuration generation; discard stale results after model,
  credentials, evidence-policy or ownership changes and retry under current policy.
  Do not lose accepted jobs or resurrect acknowledged/cancelled work.
- Federation disable/removal revokes inbound access and stops outbound dispatch
  immediately on commit. Existing owner query status/cancellation remains usable.
- Bind a new loopback listener before committing port changes. An occupied port
  returns 409 CONFIG_APPLY_FAILED without losing the old listener/config. Switch
  accepts to the new listener without restarting the CLI process/store, allow the
  saving request to finish, then drain old connections. Return the new admin URL.
  If public_url was the default loopback URL, a port-only edit updates it too.
  Custom proxy/tunnel URLs remain operator-managed; never claim to configure a proxy.
- Move store_path live by quiescing the serialized writer, copying the complete
  durable state to a new DETS file, flushing/validating it, switching the writer and
  committing config. Preserve IDs, jobs, idempotency, acknowledgements and sequence. Product store
  files are owner-only (0600), including existing files reopened after upgrade.
  Refuse an occupied/nonempty destination, same-file alias or invalid/unwritable
  parent without disturbing the current store. Never delete the old store on a
  successful move; it is an offline recovery copy, not another live writer.
- A project_id edit renames the same logical project, not an empty new project.
  Retain all IDs/text/data/timestamps, ownership, source dedup and replay results.
  Preserve original project identity as internal provenance; current record views
  may project the active project_id. Keep frozen query evidence and original replay
  results verbatim. Record the rename explicitly so startup validates historical
  records against known project aliases while still rejecting unrelated stores.
- Authentication, users, role mappings and sessions follow identity/spec.md. Live
  changes must not depend on a browser reload, token expiry or server restart.

The host setting continues to permit only 127.0.0.1; there is no new public bind.
Resource settings remain bounded by owning contracts. Invalid proposed settings
must fail with stable errors, not a restart-required success response.

## Configuration APIs

POST /admin/api accepts these operations in addition to existing management ops.
Cookie sessions need CSRF protection; legacy bearer Admin remains compatible.

- config_get: {op}; returns {config_revision,config,secrets,reload_status}.
  `config` is the full non-secret editable snapshot, including agent IDs and owner
  references, user profiles/roles, matcher, federation, auth and provider settings.
  Omit all credential/hash values; secrets is a JSON-pointer-to-boolean map for
  configured agent/admin/peer/client/password secrets. Never return placeholders
  that would be mistaken for actual values. Config reads are Admin-only.
- config_update: {op,expected_revision,patch,confirm:true,message_id}. `patch` is
  JSON Merge Patch (RFC 7396): absent fields retain values, arrays replace, null
  removes optional fields. Validate unknown fields and all bounds after merging.
  Server-owned revisions/IDs and user password hashes cannot be supplied. Do not
  use config_update to bypass identity/spec.md's role or agent-owner rules.
  Result {config_revision,applied:true,admin_url}. Admin-only, synchronous durable
  acknowledgment. Invalid: 400 INVALID_PARAMS, storage/bind:409 CONFIG_APPLY_FAILED,
  auth:403 FORBIDDEN, stale:409 CONFIG_CONFLICT, write:503 CONFIG_WRITE_FAILED.
- config_validate: {op,expected_revision,patch}; same full validation without
  mutation, persistence, new listeners or credential disclosure. Admin-only.
  Returns {valid:true,config_revision}. A dry run is not proof of later port access.

Legacy files without config_revision/auth/users remain valid, bearer-only and
unmodified on startup. A missing CONFIG_FILE is first installation: create a private
config with default port 8766, project_id shared-project, store_path hub.dets beside
config, zero agents, default local matcher, local authentication, and bootstrap
Admin as defined in identity/spec.md. Allow an empty agents map. Never truncate or
replace an existing unreadable file. The initial setup must be usable from the UI.

## Console and deployment

Add Settings, Users and Agents views alongside the four existing views. Admin
Settings has labeled usable forms for every setting, including adding/removing
peers, allowlisted publication IDs, tokens, matcher budgets, listener/data path,
provider selection and OIDC settings. No requirement to edit raw JSON or use a CLI
for routine configuration. An optional advanced JSON editor is supplemental only.
Passwords/tokens are write-only inputs; blank means retain, explicit Remove means
remove. Use Web Crypto to generate new agent/peer token inputs locally when desired;
never persist them in browser storage. Show revision/conflict/validation/save and
apply-error states, preserve edits on failure, and require confirmation for changes
that revoke access, rename the project or move the store. After listener changes
show the resulting URL and reconnect/navigate there after the saving response.

Viewers and Developers may inspect permitted project data but cannot access secret
settings or Admin mutation controls. Hiding controls does not replace API checks.
Every view/action works at desktop and 390px without overflow or runtime errors.

Deployments must mount a private writable configuration DIRECTORY, not a read-only
single file, so atomic saves, first-admin password and journal survive replacement.
Keep root filesystem read-only and credentials out of image/build context. Default
health reads the current file and active port. Store migration is limited to paths
writable inside the container's mounted volumes, not arbitrary host paths. Explain
that volume layout is infrastructure, while selecting a writable store path is hot.

## Acceptance

Use a process identity check across valid updates to every field. Include file
reload, token rotation, model recovery, peer revoke, local/OIDC role changes,
occupied port, config revision conflicts, response-loss replay, store move and
project rename with full accepted data intact. Kill during config transactions and
recover a complete state. Test read-only/failed writes and symlink rejection.
Run actual Docker runner with writable private config mount and replacement,
plus old schema-1/schema-2/native federation/SDK and real model regressions.

## Managed TLS / ACME extension (application2.2)

The new optional global `tls` setting is exactly defined in
[ACME authority](../acme/spec.md) and [closed schema](../acme/interface.schema.json).
Omission retains disabled TLS defaults; the existing HTTP binding, default
127.0.0.1:8766, bootstrap, auth and all project settings remain unchanged. The
new tls.host/challenge_host may explicitly bind wildcard IPv4/IPv6 addresses;
this is a narrow additional-listener exception, not a change to the existing
HTTP listener's owning host policy. TLS and ACME enablement are independent:
retained valid certificates may serve while issuance is disabled. No implicit
HTTP downgrade, reverse-proxy edit or public-reachability claim.

Expose every TLS/ACME field in Admin Settings and config_get; only Admin edits
them through the existing expected_revision/confirm/message_id transaction.
Accounts, private keys and certificate PEM never become editable config fields
or returned config/status secrets. ca_cert_file affects only ACME directory TLS.
Validate the complete defaulted post-merge configuration. Global tls is forbidden
in per-project overrides. Config_validate never creates state/listeners/accounts
or contacts the CA. Config_update preflights bounded local trust and prebinds
changed listeners before its normal durable decision. Failure preserves old
config/revision/listeners. Commit queues bounded asynchronous issuance instead of
waiting for network success; its reply certifies config, not a certificate.

A relevant committed edit retires and fences the old ACME attempt; discard late
client output rather than installing an old-policy certificate. Preserve unchanged
valid TLS generations until validated replacements are atomically published.
ACME status/renewal use the existing Admin route/authorization/CSRF/revision and
durable mutation-receipt policy; tls_renew's revision member is expected_revision,
and its successful scheduling reply returns config_revision. No project restore
may replace the global account/cert state. Full stopped-server backup includes
config-parent/acme and CONFIG_FILE.acme-owner.json; explicit portable config
location rebind must preserve their owner binding without importing old settings
or silently treating missing initialized state as first use.
