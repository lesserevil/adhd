# Optional administrator OIDC

[Project guide](../README.md) → administrator OIDC

The default administrator authentication method remains the separate admin key.
OIDC is an explicit alternative for the web console and administrator API; agent
A2A bearer authentication is unchanged. An older deployed runtime needs upgrading
before these options are available.

## Configure the provider

Register an authorization-code client with S256 PKCE and RS256 ID tokens. Register
the callback as the configured `public_url` without a trailing slash plus
`/admin/callback`. Use an HTTPS public URL and issuer in normal operation. Configure
exact permitted provider subject IDs, rather than relying on email or display name:

```json
{
  "public_url": "https://hub.example.invalid",
  "admin_auth": "oidc",
  "oidc": {
    "issuer": "https://identity.example.invalid",
    "client_id": "adhd-console",
    "client_secret_env": "ADHD_OIDC_CLIENT_SECRET",
    "allowed_subjects": ["PROVIDER_SUBJECT_ID"],
    "session_seconds": 3600,
    "idle_seconds": 900
  }
}
```

Set the secret environment variable in the service process. Public clients can
omit `client_secret_env`; a configured variable must exist. Confidential clients
use `token_endpoint_auth_method: "client_secret_basic"` by default, or explicitly
select `"client_secret_post"` when required by the provider. Keep all server
configuration private. OIDC tokens and sessions are never stored in DETS or
returned to browser JavaScript. The browser receives only an opaque HttpOnly,
SameSite=Lax cookie, Secure on HTTPS, scoped to `/admin`.

In OIDC mode an existing `admin_token` can remain in private configuration for a
later deliberate mode switch, but it does not authorize requests. There is no
fallback to key authentication when the provider is unavailable. To return to
key mode, explicitly set `admin_auth: "key"` and restart with a valid admin token.
With `admin_auth` omitted, existing installations retain key mode.

## Sessions and access

Sign in starts discovery, browser-bound state/nonce validation, PKCE and one-time
authorization-code exchange. The server verifies the ID-token signature and
issuer, audience, authorized party, subject allowlist, nonce and time claims.
Administrator POST requests require a valid session, the configured public origin
and a CSRF token held in browser memory. Forwarded headers cannot grant access.

Sessions expire after the configured absolute or idle lifetime, and cannot outlive
the ID token. Refresh tokens are not requested. Restart invalidates local sessions.
Logout clears the local hub session; it does not sign the user out of the identity
provider globally. Provider failure prevents new sign-ins but does not invalidate
already valid local sessions. Discovery and signing keys are cached for up to
five minutes; an unknown key ID triggers one refresh.

The protocol follows [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
and [RFC 7636 S256 PKCE](https://www.rfc-editor.org/rfc/rfc7636).
The supported profile is authorization code with RS256; encrypted, unsigned and
HMAC-signed ID tokens are rejected. Independently signed provider fixtures verify
the flow; no live enterprise-provider deployment is implied by that evidence.

## Local testing and troubleshooting

`allow_insecure_loopback: true` is an explicit development option. It permits HTTP
only when public URL, issuer and discovered endpoint hosts are literally loopback
(`localhost`, `127.0.0.1` or `::1`). It does not permit private-network HTTP. For
remote access, terminate HTTPS at the private proxy and preserve the browser's
public Origin. The hub itself keeps its existing loopback listener.

For rejected sign-in, check the exact callback registration, issuer, RS256 signing
keys, client ID, subject allowlist and service clock. A different browser, expired
state, code reuse, wrong nonce or callback replay is rejected. A 503 indicates
provider discovery/exchange failure; check provider reachability without logging
codes, tokens or secrets. Missing session gives 401; wrong Origin/CSRF gives 403.
Sign in again after expiry/restart. Keep credentials out of URLs and screenshots.
