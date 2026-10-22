---
name: Managed ACME TLS
summary: Bounded HTTP-01 certificate acquisition, renewal and native HTTPS
kind: component
---
# Managed ACME TLS (ACME-001)

This additive authority targets application/OpenAPI 2.2.0 and schema
`urn:adhd:protocol:2.2`. It does not claim that admitted 2.1 artifacts implement
these operations. Wire major 2, envelope 1, A2A and federation envelopes are
unchanged. Discovery publishes the actual new schemas; old closed 2.1 validators
are not claimed to accept new settings, commands or errors.

## Scope and standards

Implement RFC 8555 ACME v2 using bundled, version/digest-bound Lego 5.5.2.
Lego performs signed ACME exchanges, nonce handling, account registration,
authorizations, orders and certificate requests. ADHD owns scheduling, bounded
process custody, private persistent account/client data, challenge exposure,
configuration fencing and validated certificate publication. Never implement a
second ad hoc ACME protocol or treat a successful client exit as a valid cert.
The certificate is for the hub's native HTTPS endpoint, not the separate model,
Kafka or federation peer's server certificate.

Only HTTP-01 is supported. DNS-01, TLS-ALPN-01, wildcard names, IP identifiers,
external-account binding, user-supplied shell/hooks and automatic revocation or
account-key rollover are unsupported in this cut. They require explicit future
contracts, not hidden client environment options. Replacing/renewing a certificate
does not revoke the previous one. Use the CA's documented operator process when
revocation is necessary. Do not promise issuance or production trust from staging.

RFC 8555 section 8.3 requires the CA to fetch TCP port **80**. The internal default
challenge port 8080 therefore requires operator-managed public 80-to-8080 routing
and DNS for every requested domain. Native HTTPS defaults to 8443; serving public
443 similarly requires routing. Neither config success nor local health proves
public reachability. Never alter host firewall, DNS or external infrastructure.

Primary sources: [RFC 8555](https://www.rfc-editor.org/rfc/rfc8555.html),
[Let's Encrypt HTTP-01 restrictions](https://letsencrypt.org/docs/challenge-types/),
[Lego 5.5.2 client command](https://github.com/go-acme/lego/blob/v5.5.2/cmd/cmd_run.go),
and [pinned webroot provider](https://github.com/go-acme/lego/blob/v5.5.2/providers/http/webroot/webroot.go).

## Closed configuration and defaults

`interface.schema.json` defines the exact new `tls` object. Missing `tls` expands
in memory to its defaults without rewriting an old config on startup. The existing
HTTP listener remains 127.0.0.1:8766 by default, with all prior configuration and
bootstrap behavior. This authority permits a public bind only for the two new
explicit TLS/challenge listeners; it does not broaden the existing HTTP host rule.

Defaults are:

```json
{"enabled":false,"host":"0.0.0.0","port":8443,"challenge_host":"0.0.0.0","challenge_port":8080,"acme":{"enabled":false,"directory_url":"https://acme-staging-v02.api.letsencrypt.org/directory","email":"","domains":[],"accept_terms":false,"renew_before_days":30,"retry_seconds":300,"order_timeout_ms":120000,"ca_cert_file":null}}
```

Config files may omit these members and use defaults. After normal default
expansion the closed schema applies; Admin Settings/config_get expose every
nonsecret field and hot config_update uses the existing expected_revision,
confirm, message_id and merge-patch rules. No TLS field is restart-only. Null
removes optional tls and restores disabled defaults; null is not a key/cert import.
Unknown fields, including DNS secrets, challenge-provider names and EAB fields,
are INVALID_PARAMS. No config secret contains an account or certificate key.

`acme.enabled:true` requires `tls.enabled:true`, nonempty email/domains and explicit
accept_terms:true. Directory URL is HTTPS with a hostname, no credentials/query/
fragment; TLS verification is mandatory, including hostname verification.
ca_cert_file optionally names a bounded readable regular PEM trust bundle for
that ACME client only; it does not weaken global HTTP/model/peer trust. The normal
hot-config preflight reads and binds its bytes. No shell/environment interpolation.
Email has no control characters and at most 254 UTF-8 bytes. Names are unique,
lowercase ASCII DNS A-labels, at most 253 bytes, each label 1..63 characters,
no trailing dot/wildcard/IP literal; operators convert Unicode via IDNA first.
At most 20 names. Sorting canonicalizes the domain set; order has no semantics.
Host is an explicit IPv4/IPv6 address, not a hostname requiring network lookup.
Resolve relative ca_cert_file paths against CONFIG_FILE's parent, never process
CWD; reject symlink/unsafe file input before any new network attempt.

TLS may remain enabled with ACME disabled to serve an already retained valid
certificate; no acquisition/renewal occurs. Without such a certificate HTTPS is
waiting and unavailable, while private HTTP remains usable for Admin/bootstrap.
Enabling ACME explicitly authorizes contacting the selected CA and agreeing its
terms for that account/directory; no implicit acceptance or production fallback.
Changing directory/account contact does not silently reuse a different CA account.

## Listeners and HTTP-01

HTTPS serves exactly the existing Server routing, authorization, size/framing,
CSRF, request/error and readiness rules through a transport wrapper; it is not
an alternate less-restricted Admin API. Support TLS 1.2/1.3, no client-certificate
requirement. Keep the original JSON serve argv, native CLI and private HTTP.
Never implicitly redirect to plaintext or expose private HTTP on a public bind.
public_url remains the existing explicit operator setting; enabling HTTPS does
not rewrite it or claim reverse-proxy configuration.

The separate challenge listener serves only GET
`/.well-known/acme-challenge/{token}` for the exact current pending HTTP-01 token.
The token is base64url without padding, 22..256 bytes; the response is the exact
key authorization produced for that active attempt, ASCII text/plain, at most
1024 bytes and Cache-Control:no-store. It is not generated from the request.
Unknown/stale tokens or other paths return empty 404; non-GET returns empty 405.
No directory listing, file serving, reflection, redirects, health, Admin, A2A or
private payloads exist on this listener. Enforce existing bounded HTTP framing.
No percent-decoded traversal or query aliases. Only explicitly configured domain
Host values (optional internal/public port) are eligible; do not trust forwarded
headers. Remove old tokens on success, failure, cancellation and startup recovery.

Use Lego's pinned HTTP webroot provider within the private attempt directory;
ADHD exposes only validated current attempt files, never an arbitrary path.
The provider's 0644 token files are acceptable inside an owned 0700 directory:
these public proof bytes are not account/private keys. Require owner-regular,
no-symlink/no-hardlink reads and bounded exact basename/content. No broad webroot
or propagation endpoint is enabled; no child process binds the challenge port.

## Hot transactions and fencing

Keep all existing config transaction durability/receipt semantics. Validate
settings and privately prebind each changed required listener before the durable
configuration decision; collision, invalid trust input or unusable listener
returns CONFIG_APPLY_FAILED without losing old listeners/config/revision.
Prebinding may reserve a socket before the first certificate exists; no invalid
TLS session is accepted while waiting. Do not wait for ACME/network issuance
inside Config's serialized transaction or mailbox. A successful config_update
means configuration committed, not certificate issued or externally reachable.

After config commit switch admissions to the prepared listeners and let the
saving request finish before draining displaced listeners. Failed acquisition
must not roll back unrelated committed configuration. On tls disable stop new
TLS admissions and challenge/renewal work; private HTTP remains governed by its
own settings. Endpoint/address changes do not silently open a second public API.

Each attempt binds current desired ACME directory/email/domain/trust bytes,
listener settings, accepted-terms policy and an opaque durable generation.
A committed relevant edit or disable retires that attempt, removes its challenge
entries, cancels its owned process and fences all late output. Current auth/config
is checked when admitting an Admin renewal. Publication rechecks the attempt's
fingerprint/generation under serialized local ownership. Unrelated config edits
need not cancel a matching attempt, but the recorded public config_revision always
reflects current config; it never authorizes a stale mutation submission.

## Private state, process ownership and publication

Managed state is the private `acme/` directory beside CONFIG_FILE, containing
`accounts/`, `attempts/`, `generations/` and `state.json`; no arbitrary state path
is configurable. Bind initialized state to the original server/configuration
identity. A second unrelated configuration sharing this directory must reject the
collision, not adopt another account. Retain an independent owner-only durable
initialization witness `CONFIG_FILE.acme-owner.json` beside CONFIG_FILE, binding
its configuration-path digest and opaque managed-state owner, so loss of an initialized managed
directory cannot be mistaken for first use. Include witness and managed directory
in stopped full-server backup/restore, preserving identity under the existing
explicit offline metadata rebind when paths change. Require owned 0700
directories, 0600 account keys, certificate keys and state, owner-regular nlink1
files, no redirected/symlink parents. Account material persists independently
from project stores; selective project recovery never rewinds it. Full-server
backup/restore includes it through the existing stopped-server procedure. Do not
mistake a missing initialized account/state directory for permission to reset it.
A fresh installation may create it when ACME is explicitly enabled.

One attempt per server, no concurrent client writers. Bundle a fixed executable
and build its argv from validated settings only; no shell, hooks, DNS plugin,
ambient provider credentials, custom executable or arbitrary flags. Bound one
attempt by order_timeout_ms including queue/spawn/CA polling/process cleanup,
with separately reserved bounded cleanup effort. Capture stdout/stderr bounded
64KiB each, never return them through API/logs. A POSIX guardian owns the whole
child process group and terminates descendants on timeout, parent EOF or parent
hard death. Do not claim process cleanup from a wait on the launcher alone.
Unknown process closure blocks further attempts, rather than overlapping writers.

Lego's working output is not the live certificate. In a new owned generation,
verify bounded PEM parsing (at most 1MiB complete chain and 64KiB private key),
exact requested DNS SAN set, supported signing/key
algorithms, key-pair agreement, valid leaf chain structure, not_before<=now<not_after,
serverAuth usage if present, and hostname coverage. Reject extra/unrequested SANs,
expired/not-yet-valid certificates, unrelated key or malformed chain. The custom
ca_cert_file trust setting applies only to ACME directory/server TLS. It is not an
additional public HTTPS trust anchor or a replacement for certificate/key/SAN
validation. Private-CA acceptance supplies independent controlled issuer trust;
public browser trust is not inferred from successful issuance. Never publish a
mismatched result merely because the client exited zero.

Fsync complete immutable certificate/key/metadata generation and its directory,
then atomically replace+fsync the active-generation pointer/state. TLS new
handshakes select a complete validated generation; never a mixed cert/key pair.
Keep the previous generation until active publication/load is known safe.
A failed renewal preserves the last usable certificate and reports a sanitized
failure/retry state. Recovery of an interrupted publish selects the last complete
validated generation or fails HTTPS closed; it never resets accounts or reads
partially written key/cert files. Private HTTP/Admin remains usable.

Do not serve a certificate for an uncovered SNI hostname. A still-valid previous
certificate may continue covering its own active_domains while a new desired
set is ordering; do not claim new domains ready. No-SNI connections may use the
validated active certificate. Recheck expiry for new handshakes and stop admissions
when expired; no expired certificate, temporary self-signed certificate or HTTP
downgrade. Existing accepted TLS connections follow bounded normal server drain.

## Scheduler, restart and public state

Renew when the active certificate reaches not_after-renew_before_days, and on
initial enable with no usable desired certificate. Perform bounded retry after
retry_seconds, respecting a valid later CA Retry-After without busy loops;
persist the next-attempt time and sanitized outcome. One accepted manual renewal
may schedule an immediate attempt even before the threshold. It does not bypass
CA limits, ownership, listener or process bounds. Clocks moving backward must not
cause unbounded retries; deadlines within an attempt use monotonic time.

On startup revalidate active generation/account metadata and desired config.
Previously running attempts are interrupted, not assumed successful; clear their
tokens and prove the old process dead before new admission. Reuse persisted Lego
account material and protocol-safe client reconciliation; do not invent order
continuation from a saved local success marker. Never repeat account creation or
issuance in a tight startup loop. Corrupt initialized state is an observable error,
not empty state. A valid active cert may continue while renewal is blocked.

The exact closed status/command shapes are in interface.schema.json. State is
metadata only: no paths, keys, PEM, challenge tokens, CA account/order URLs,
credentials, email, raw client output or arbitrary exception message. last_error
uses only a fixed code/message/retryable table. UTC timestamps are RFC3339 seconds
ending Z. Certificate sha256 hashes leaf DER; serial is lowercase hexadecimal.
Status is Admin-only global state, independent of selected project.

`tls_status` is read-only. `tls_renew` requires expected_revision, confirm:true and
message_id and uses existing durable Admin mutation receipt scope. Authenticate
and authorize before replay. A stale new submission returns CONFIG_CONFLICT.
A successful accepted reply is durable scheduling, not successful issuance.
Exact replay returns the original successful reply even after completion.
A different message_id during an active attempt coalesces into it, with its own
bounded existing mutation receipt, rather than spawning a second process.
Disabled ACME returns 409 TLS_RENEW_UNAVAILABLE, with no accepted mutation receipt.
No manual renewal bypasses disabled TLS, missing consent or invalid config.

State consistency: HTTPS disabled implies enabled:false and active_domains:[];
waiting has no certificate; ready has a currently valid certificate and its
covered active_domains; expired has a retained expired cert and active_domains:[];
error admits no TLS sessions and active_domains:[]. ACME disabled means no owned
attempt; ordering means exactly one admitted queued/running attempt; idle has no
attempt scheduled immediately; backoff has next_attempt_at; error denotes blocked
local custody/state requiring operator correction. A valid old certificate can
coexist with ordering/backoff/error. Config disable may retain redacted certificate
metadata for inspection. These are not CA protocol order statuses.

## Required qualification

Before publication require independent schema/unknown-field/state consistency,
Admin/CSRF/role/revision/idempotency/privacy, default-disabled legacy, first
bootstrap, HTTP01 token isolation/traversal/Host/stale token, actual controlled
ACME registration/order/renewal and current HTTPS wire tests. Exercise cert SAN/
expiry/keypair rejection, failed renewal preserving old cert, SNI/expiry failclosed,
hot domains/directory/bind/disable collision and late-worker fences. Kill the
app/client/guardian at durable boundaries and show owned descendants terminate,
restart account reuse and one complete generation, with no private material in
reports. Test private HTTP and existing agent/Admin/federation operations under
native HTTPS and the packaged bundled client. Use a local controlled CA/trust
fixture first; live Let's Encrypt issuance needs explicitly owned public DNS/80
reachability and must never be inferred from staging or self-signed fixtures.

### Exact wire examples

```json
{"op":"tls_status"}
{"op":"tls_renew","expected_revision":12,"confirm":true,"message_id":"renew-12-1"}
{"accepted":true,"config_revision":12}
{"error":{"code":"TLS_RENEW_UNAVAILABLE","message":"Managed ACME renewal is disabled."}}
```

The existing HTTP Admin success JSON envelope is unchanged: TLSStatus or
TLSRenewResult is the direct successful body. Unauthorized/CSRF/role failures use
the existing closed envelopes. TLS_RENEW_UNAVAILABLE maps to HTTP409; stale new
renewal maps to CONFIG_CONFLICT/409; malformed input to INVALID_PARAMS/400; durable
receipt write failure to CONFIG_WRITE_FAILED/503. Local custody/state admission
failure uses CONFIG_APPLY_FAILED/409, without a successful receipt.
