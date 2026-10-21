---
name: Users and access providers
summary: Local and OIDC user identity with per-server roles and agent ownership
kind: component
---
# User authentication and authorization (AUTH-001, ROLE-001)

Extend management/spec.md to authenticated human users without changing agent A2A
bearer authentication or allowing human sessions to act as agent tokens. Use only
standard Elixir/OTP crypto/public_key/ssl/inets; no hand-rolled crypto primitives.
Legacy admin-token login remains supported for existing files. Present Settings,
Users and Agents to human roles with the matrix below. The local and OIDC providers
share the same internal user model and session/authorization middleware.

## Identity and role configuration

Extend configuration with `users` (array <=1000), `agent_owners` (agent-ID to user-ID
or null), and `auth`. User fields: id (immutable opaque server ID), username
(local only, identifier unique case-sensitive), name (nonblank <=256 UTF-8 bytes),
email (<=320 bytes), role (Admin/Developer/Viewer), disabled (boolean default false),
provider (local/oidc), oidc (null for local, otherwise {issuer,subject,provider_id}),
password_hash (server-owned local PBKDF2 descriptor), and groups (server-owned
validated OIDC string array). Public users omit hashes/secrets; access_allowed reflects current policy.
Use stable internal ID for roles and agent ownership, never email or display name.
Match an OIDC account by exact issuer+subject; never auto-merge local accounts by
email. Federated email correlation in later contracts does not merge local accounts.
Only Admin may explicitly link a local user to an OIDC identity after proof of
control of that OIDC identity through the real callback; preserve internal ID.

`auth` has exactly mode (local/oidc/both), allow_admin_token (boolean),
session_ttl_ms (60000..86400000, default 3600000), oidc (optional object below).
Legacy absence means admin-token-only. For new installs mode=local and
allow_admin_token=false. Mode local enables local login; mode oidc enables only
OIDC (no silent password/key fallback); both explicitly enables both providers.
Legacy bearer is accepted only when allowed, with Admin role, and invalidated live
when removed/rotated/disabled. Require at least one usable authentication method;
reject deletion/disable/demotion of the last enabled Admin local recovery account
unless an enabled OIDC Admin has completed sign-in for this configuration.
The local account can remain stored while disabled as a login method.
A live proposal that would remove the last usable Admin recovery path returns
409 CONFIG_APPLY_FAILED and retains the complete previous configuration. Evaluate
OIDC recovery against the proposed live group mappings, not a stale stored role.

Role order is Admin > Developer > Viewer. Each user has exactly one effective role
per server. Admin: full access to server data, users, agents, roles and settings.
Developer: project read access and creation of agents owned by that same user;
no creation for others, configuration/role changes, or other mutations. Viewer:
read-only inspection; no product/settings mutations. Login/logout are session actions, not a grant of project mutation rights.
Profile/password edits require Admin; Developer and Viewer cannot change users.
Existing metadata-only deliveries operation remains unchanged for compatibility;
a new explicit Admin-only private_delivery operation may retrieve a full addressed
message for Admin's requested full-access capability. Other roles never see private
payloads, stored tokens/hashes, raw model errors or confidential settings. Reads
never consume/acknowledge agent deliveries. Agent credentials remain their own scope.

OIDC effective role is computed from current server role_groups and current trusted
groups on every authorized request; no stale role stored in a session. Highest match
wins, never a union of roles and never a role from another server. Manual users use
their configured role. An OIDC user may use Admin-configured default_role when no
mapping matches; default null denies login/access. An Admin may explicitly select
manual assignment for an OIDC user; changes are Admin-only. Provider group membership
refreshes at a new validated login, while local mappings apply immediately. Expire
sessions no later than the ID token expiry and configured lifetime; no refresh
or long-lived offline-access token is required.

## Bootstrap and local passwords

First installation creates built-in username admin, name admin, role Admin, random
opaque ID and 32 cryptographically random bytes encoded base64url as password.
Persist only PBKDF2-HMAC-SHA256 (>=600000 iterations, salt >=16 random bytes,
32-byte derived key); constant-time verification. The explicit bootstrap exception
is initial-admin-password.txt next to CONFIG_FILE, exclusive create, 0600 and
owner-only directory. The exact UTF-8 file format is `Username: admin\nPassword: PASSWORD\n`,
where PASSWORD is the generated base64url value. Never print
passwords or embed them in HTML/API/diagnostics. Report the filename only.
Persist provisioning atomically with config so a crash cannot lose the only password
or regenerate it. If an existing bootstrap file conflicts, fail closed rather than
overwrite it. Never regenerate on restart, upgrade or container replacement; do not
rewrite this file on later rotation. Document it as the INITIAL password only.
Initial email is empty with profile_complete:false; require the administrator to
supply a real email in the setup form, never fabricate an address. Ordinary users
must have name/email; a missing OIDC claim similarly prompts profile completion.

Rate-limit local login per server to 30 attempts/minute and each username to 5/minute,
return 429 with Retry-After; allow bounded maps/expiry, generic failure responses,
password bytes <=1024. Offload expensive hash checks so requests and store do not
stall; cap concurrent checks at four. Unknown user and wrong password have the same
response and use a dummy hash check. No plaintext password remains in durable state
except the explicitly requested initial-password file.

POST /admin/login {username,password} authenticates local mode and sets an opaque
random cookie `adhd_session`; JSON result contains user and csrf token, never the
cookie secret. Require same Origin as configured public_url or actual loopback
origin. Cookie HttpOnly, SameSite=Lax, Path=/admin, Secure on HTTPS. Tokens >=32
random bytes; memory-only bounded session store (<=1000), TTL and explicit revoke.
GET /admin/session returns {authenticated:true,user,csrf,config_revision} for
valid cookie sessions. Without a valid session return200 {authenticated:false,
methods:{local:BOOL,oidc:BOOL,key:BOOL}} with no project data. This allows normal
login rendering without generating an expected HTTP error. Other protected APIs
return401 when unauthenticated.
POST /admin/logout requires session CSRF and Origin, revokes and expires cookie.
POST /admin/api accepts cookie+X-CSRF-Token+Origin OR allowed legacy Admin bearer.
Do not accept OIDC access/ID tokens directly as local API bearer tokens.
Changing password/disabling user/provider revokes affected sessions and pending
logins; roles/group mappings are checked live. Restart clears all sessions safely.
Origin, cookie and CSRF checks apply server-side and cannot be bypassed by UI mode.
Cookies are a deliberate extension of management/spec.md's old no-cookie token UI;
legacy key remains JS-memory-only. Never store session credentials in browser storage.

## Browser authentication transitions

The Admin browser binds asynchronous requests to an authentication-context
generation. Starting logout, changing sign-in credentials, or starting an explicit
OIDC linking redirect invalidates the previous context before sending the new
authentication operation. Abort outstanding old-context fetches. Never interpret
their late success, HTTP401, transport failure or rejected body as a current
session result, and never let them clear or render over a newer authenticated
workspace. Current-context HTTP401 still requires sign-in; stale-response fencing
must not conceal real session expiry, revocation or authorization denial.

Await session installation, including project admission and initial view loading,
inside the initiating sign-in/boot error boundary. Intentional cancellation or
supersession must not produce an unhandled promise rejection or an error notice in
the replacement context. Cancellation is local presentation work: it does not undo
accepted server mutations, erase their durable receipts, or change their
message-ID recovery semantics. No new credentials, HTTP routes or wire fields are
introduced by this browser fencing.

Qualify a delayed real old-session response across logout and a successful new
login. The newer workspace and its valid server session must survive. Exercise
logout during installation and ordinary OIDC setup/link/logout on desktop/mobile;
also prove that a current-session revocation still returns the browser to sign-in.

## OIDC profile

Authorization Code Flow with PKCE S256 and server-side token exchange. Standards:
OpenID Connect Core 1.0 / Discovery 1.0 incorporating errata set 2; RFC7636 PKCE,
RFC7515/7517 JWS/JWK, RFC8725 JWT BCP. Supported ID token algorithm is RS256 only.
Never accept alg none, HS256 confusion, unknown alg, a token-supplied jku/x5u,
or an unverified decoded claim. Use standard public_key signature verification.

OIDC config fields: provider_id (identifier), issuer (absolute HTTPS URL; HTTP only
for 127.0.0.1/localhost test IdP), client_id (1..512 bytes), client_secret (optional
write-only <=4096), redirect_uri (absolute URL ending /admin/oidc/callback, HTTPS
or loopback HTTP only), scopes (<=16 nonblank strings, includes openid, profile,
email), groups_claim (claim name default groups, <=128), role_groups (object with
exact Admin/Developer/Viewer arrays, <=64 distinct <=256-byte groups each),
default_role (null or one of three roles, default null), timeout_ms (100..10000,
default3000). No unknown keys. Role-group edits and provider changes are Admin-only.
GET issuer/.well-known/openid-configuration; metadata issuer must match exactly.
Use advertised authorization_endpoint, token_endpoint and jwks_uri, with HTTPS or
loopback HTTP, no userinfo, no redirects, bounded responses <=256KiB and finite
network timeouts outside store writer. Require authorization-code and RS256 support.
No arbitrary discovery hosts from browser request inputs. Refresh JWKS once on an
unknown kid, then reject. Bound cached JWKS to configured issuer and revision.

GET /admin/oidc/start sets a separate HttpOnly SameSite=Lax state-binding cookie and
redirects to authorization endpoint with response_type=code, registered redirect,
client_id, scopes, >=32-byte state and nonce, PKCE challenge and method S256.
Pending flows are memory-only, single use, max five minutes and <=128 entries.
Callback GET /admin/oidc/callback requires exactly state and code (or provider error),
state cookie match, current provider generation and unused/nonexpired state. Consume
state before exchange to prevent replay, including error/failed exchange. Use
application/x-www-form-urlencoded token POST, grant_type authorization_code, code,
redirect_uri, code_verifier; client_secret_basic if secret set, otherwise public
client_id with PKCE. No request query/path parameters may choose redirect destinations.

Validate signature from configured issuer JWKS by unique kid, kty RSA, appropriate
use/key_ops and modulus >=2048 bits; reject duplicate kid ambiguity. Require exact
iss, aud containing client_id, azp=client_id when present (required for multiple
audiences), exp future,
iat not future (>30s skew) or unreasonably old (>1h), nbf when present, nonblank sub
and exact nonce. Limit JWT to64KiB, reject duplicate JSON keys and malformed
base64url. Extract name/email/groups only after verification; groups must be a
bounded string array (<=256 groups). Invalid groups cannot confer default Admin.
No access/refresh/ID token or auth code enters logs, cookie contents or product DETS.

Resolve existing account by issuer+sub or create a new OIDC user when a local
mapping/default_role explicitly admits it. Store profile and group data privately
beside config using the serialized config path, with stable ID and same role rules.
Denied user gets403, not a local session. Successful callback sets local opaque
session, clears flow cookie and redirects only to /admin. Provider error, invalid
claims or unavailable discovery/token/JWKS returns a generic login error. No silent
fallback when mode=oidc. Redact callback query strings from diagnostics.

## User and agent administration

POST /admin/api extends pure validate-admin for all operation shapes:
- users: {op}; any human role, public profiles only, returns {users:[...]}.
- agents: {op}; any human role, returns {agents:[{agent_id,owner_user_id,token_set}]}.
- save_user: {op,user,expected_revision,message_id,confirm:true}; Admin only.
  user is {id? (update),username?,name,email,role,disabled?,password?,provider?,
  role_source? (manual/groups)}. Reject password_hash, groups, oidc identity claims
  supplied by clients. Create ID server-side; require local username/password on
  create, keep password if absent on edit, never accept blank password as reset.
  Return sanitized user and config_revision. No role edit via profile operation.
- update_profile: {op,name,email,password?,current_password?,expected_revision,
  message_id,confirm:true}; Admin session user only. Never accept role/provider/id/groups.
  A local password change requires current password; revoke other sessions.
- create_agent: {op,agent_id,token,owner_user_id? (Admin only),expected_revision,
  message_id,confirm:true}; Admin or Developer. Developer owner is forcibly current
  user; supplying another owner's field is403. Refuse an existing agent ID. A Developer also
  MUST NOT recreate an absent agent ID with retained durable state in any project,
  including private delivery recipients/senders and mutation receipts. Return409
  IDEMPOTENCY_CONFLICT without changing configuration or exposing the retained
  project/data. Check all project stores, including projects not admitted to that
  Developer, without opening a live checkpoint for a second writer. Missing or
  unverifiable durable identity evidence fails closed. An Admin may explicitly
  restore/reassign that retained identity; its original private queues, receipts
  and acknowledgements remain intact. This is an Admin access grant, never an
  automatic claim by matching a formerly used identifier. Return
  {agent_id,owner_user_id,config_revision} without token. Apply live to A2A.
- private_delivery: {op,delivery_id}; Admin only; returns {delivery:DELIVERY}
  containing the full delivery envelope.
- test_oidc: {op,settings}; Admin only; validate proposed settings plus real
  discovery/JWKS reachability without saving, token echo or blocking the store.
  Return {valid:true,issuer,redirect_uri}; unreachable/invalid issuer=400 OIDC_ERROR.

Legacy bearer requests can administer new identities with principal legacy-admin;
this reserved ID is not impersonation of an agent. Pre-existing agents are unowned
until explicitly assigned by Admin; Developers cannot claim them by matching ID.
All persistent user/config mutations share revision/idempotency/atomic semantics.
User management, role assignment and group edits occur in normal labeled UI forms,
not raw JSON only. Use per-role group inputs and provider-mode controls; display
issuer and callback URL; test connection button performs actual discovery checks.
Login shell offers only enabled methods; OIDC start is a real redirect, not a stub.

## Explicit local-to-OIDC linking

Admin-only POST /admin/api {op:"link_oidc",user_id,expected_revision,confirm:true}
prepares a five-minute single-use proof flow and returns {authorization_url},
setting the ordinary OIDC state cookie. This prepares authentication, not a durable
config mutation; it has no message_id. Require OIDC enabled and the current revision.
The selected user must be enabled and local; keep built-in username admin local.
Refuse unsupported targets with409 CONFIG_APPLY_FAILED, unknown ID404 and stale
revision409 CONFIG_CONFLICT. Users UI offers confirmed "Link OIDC identity".
Redirect only to the configured provider. Bind flow to target ID, initiating Admin
credential/session, provider generation and approved config revision. Complete the existing
code/PKCE/state/nonce/signature checks before linking. At callback reauthenticate
that same Admin session (or unchanged legacy credential binding) against current configuration, require the approved revision,
and reject an issuer+subject already belonging to a different local account with
409 IDENTITY_CONFLICT. No email match, browser-supplied identity or role assertion
can satisfy proof. Other rejected flows use the existing OIDC errors.
Commit the linked identity and config revision atomically. Preserve target internal
ID, role and agent ownership; remove local username/password hash, set provider=oidc,
and manual role_source, using the proved issuer/subject/provider link. Retain actual
profile details when claims omit them; new claims may update name/email. Revoke old
local sessions, then issue the ordinary OIDC session and redirect to /admin. A
response loss leaves one durable account mapping; a subsequent real OIDC login
finds the same ID. Callback replay cannot create or relink an account. Test these
conditions independently, including successful linking and conflicting identities.

## Independent verification

Use an isolated local OIDC provider with a real RSA key, real code exchange, state,
nonce and PKCE checking; test good/denied/multi-group users, token tampering,
wrong issuer/audience/azp/nonce, expiration, unknown kid, callback replay/mismatched
cookie/state, changed provider mid-flow, provider outage, CSRF and cookie flags.
Verify default legacy key works, random bootstrap file ownership/restart, local
password login/logout/expiry/revocation, each role through direct API and UI,
Developer self-owned agents, attempted spoof/self-promotion and server independence.
Inspect desktop/mobile Users/Agents/Settings plus existing views with zero normal
runtime errors and no secrets in captures or logs. Use actual image and legacy
stores; a simulated login button alone never qualifies OIDC.

Admin query-job access is extended in directory/queries.md.
