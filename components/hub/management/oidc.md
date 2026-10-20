---
name: Optional administrator OIDC
summary: Authorization-code sign-in with explicit administrator authorization
kind: component
---
# Optional administrator OIDC (AUTH-001)

Extend configuration with admin_auth: `key` (default) or `oidc`, and optional
`oidc` object. Existing configs, admin_token behavior, separate agent bearer
authentication and disabled legacy admin API remain compatible in key mode.
Explicit OIDC mode uses sessions only: neither admin_token nor agent tokens can
authorize admin requests, and provider failure never falls back to a key. It is
valid to retain an old admin_token in private config for future deliberate rollback;
ignore it for authorization while OIDC is selected. OIDC is not required by default.

OIDC configuration requires issuer (absolute HTTPS URL without query/fragment),
client_id (nonblank <=256 bytes), and allowed_subjects (1..100 distinct nonblank
subject strings <=256 bytes). Optional client_secret_env names a required nonblank
environment value; read it at startup and never persist/log/return it. Optional
session_seconds (60..86400 default 3600), idle_seconds (30..86400 default 900,
not above session_seconds), and allow_insecure_loopback (boolean default false).
Reject unknown keys. Require public_url HTTPS in OIDC mode; explicit loopback
development mode permits HTTP only when issuer, public_url and discovered endpoint
hosts are literally localhost/127.0.0.1/::1. Do not accept private nonloopback HTTP.
The redirect URI is exactly public_url without trailing slash + `/admin/callback`.
Authorize by exact issuer + sub allowlist, never email/display name alone.

Use OpenID Connect discovery at issuer + `/.well-known/openid-configuration`.
Require exact returned issuer, HTTPS authorization_endpoint, token_endpoint and
jwks_uri (or the explicit loopback exception), authorization-code flow, and RS256
ID-token signing capability. Reject insecure endpoints and invalid discovery.
Verified TLS, bounded 1 MiB responses, 5 second network deadlines, no redirects
to unvalidated endpoints. Discovery/JWKS cache up to 300 seconds; refresh once
on an unknown signing kid. A provider outage makes sign-in unavailable (503)
without disabling valid unexpired local sessions or A2A. Network work must not
block the product store writer.

## Routes and flow

GET `/admin/auth` anonymously returns only `{mode:"key"}` or `{mode:"oidc"}`.
In key mode retain the existing anonymous shell and in-memory token login; OIDC
routes otherwise return 404. In OIDC mode the shell shows “Sign in” linking to
`/admin/login`, not a key input. No provider or project secret enters HTML.

GET `/admin/login` creates crypto-random state, nonce, browser transaction binding
and 43..128-character PKCE verifier (at least 256 bits entropy each). Save only
short-lived server-memory transaction state, expiring after 300 seconds. Set a
browser binding cookie HttpOnly, SameSite=Lax, Path=/admin, Max-Age=300 and Secure
for HTTPS. Redirect to the discovered authorization endpoint with response_type=code,
client_id, exact redirect_uri, scope=openid, state, nonce, code_challenge_method=S256
and URL-safe base64 SHA256 code_challenge. No open redirect parameter is accepted.

GET `/admin/callback` validates bounded unique code/state query parameters and
browser binding, compares state in constant time, and consumes the transaction
once before exchanging code. Reject missing/duplicate/wrong/expired/replayed state
or provider errors with generic 401. POST form-urlencoded authorization_code,
code, redirect_uri, client_id, code_verifier and optional client_secret to token
endpoint. Never expose tokens or provider diagnostic bodies. Require id_token.

Validate JWT strictly: three base64url components, bounded decoded size, alg
exactly RS256 (never none/HS256 or header-supplied jku/x5u), kid selecting a
matching RSA signing JWK, RSA modulus >=2048 bits, `use` sig/absent, alg RS256/absent
and key_ops verify/absent. Verify SHA256 RSA signature with OTP public_key using
decoded unsigned n/e. Require exact iss, nonblank allowed sub, matching aud
(string or array containing client_id), azp=client_id when multiple audiences,
integer unexpired exp, integer iat not in the future beyond 60 seconds, optional
nbf not beyond 60 seconds, and exact nonce. Reject duplicate JSON claim/header
keys, malformed encoding, encryption and unsupported algorithms. Session expiry
cannot exceed token exp or configured lifetime. Access tokens are not ID tokens.
No refresh token/offline access is requested or persisted.

Successful callback creates a random opaque session and CSRF secret in memory,
clears transaction cookie, sets HttpOnly SameSite=Lax Path=/admin session cookie
with Secure on HTTPS and Max-Age matching expiry, then redirects only to /admin/.
Browser never receives provider tokens. Bound outstanding transactions/sessions
to 1000 each; expire old entries and reject excess safely. Restart logs out
sessions; credentials and tokens never enter DETS or status output.

GET `/admin/session` with a valid cookie returns `{authenticated:true,csrf:SECRET}`;
otherwise 401. Browser keeps CSRF in memory only. In OIDC mode POST /admin/api
requires valid unexpired, non-idle session, exact configured public_url Origin
and `X-CSRF-Token` in constant-time comparison for every operation. Missing/bad
session is 401; bad Origin/CSRF is 403. Never trust forwarded headers to establish
identity or an allowed origin. Key-mode origin/bearer policy is unchanged.
POST `/admin/logout` uses the same session/Origin/CSRF checks, destroys session,
clears cookie and returns `{logged_out:true}`. Logout is local; no provider-wide
logout is claimed. Browser clears all project data and CSRF, returns to sign-in,
and handles expired sessions/503/network errors without displaying stale data.

Existing Cache-Control, CSP and XSS rules apply. The original “no cookies” rule
continues in key mode; only these secure OIDC cookies are the explicit exception.
Cookie-auth admin requests cannot authorize A2A and session IDs are not agent
bearer tokens. Preserve existing administrator/private-payload boundaries.

## Acceptance and documentation

Use an independent local OIDC provider fixture with real RSA signatures and
authorization-code/PKCE verification. Exercise unchanged key-default and legacy
disabled API, OIDC allow/deny, wrong signature/kid/issuer/audience/azp/nonce,
expired/future tokens, malformed/duplicate claims, alg confusion, code/state
replay, missing browser binding, CSRF/Origin, idle/absolute expiry, logout,
restart, discovery/JWKS failure and key rotation. Verify key/agent credentials
cannot bypass explicitly selected OIDC and no tokens leak to HTML, APIs/logs/store.
Run browser sign-in/callback/actions/logout on desktop/mobile, network failure and
expiry recovery. The controlled signed provider is protocol integration evidence;
do not claim a live enterprise provider unless configured and tested separately.

Document configuration/environment secrets, exact callback registration, RS256
provider requirement, issuer/sub allowlist, HTTPS and proxy requirements, explicit
loopback-only testing, session/CSRF behavior, local logout, restart invalidation,
provider outages, deliberate mode switch and rollback. Follow the primary
OpenID Connect Core ID-token validation and RFC 7636 S256 protocol contracts;
no provider SDK or nonstandard runtime dependency is needed.

Confidential clients use client_secret_basic by default; explicit
`token_endpoint_auth_method: "client_secret_post"` selects form authentication.
Reject unsupported methods. Discovery must support the selected method when it
advertises token endpoint authentication methods. Public clients omit secrets.
