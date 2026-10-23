# Managed HTTPS wire extension

Application profile **2.2.0** adds server-wide TLS configuration and two global
Admin operations. The ACME component contract, `components/hub/acme/spec.md`,
and its [closed interface input](../../components/hub/acme/interface.schema.json)
own the behavior. The published [schema](schema.json), [OpenAPI](openapi.json)
and [scope inventory](scopes.json) are the client-facing profile. The
[actual protocol proof](../../verification/acme/protocol22-qualified-positive/manifest.json)
covers their accepted source and HTTP correspondence. The separate
[runtime composition](../../verification/acme/final-composition/manifest.json) covers
certificate lifecycle/recovery, all fifteen fault scenarios, browser review and
whole Compose and Kubernetes deployment checks. The [active queue](../roadmap/active-work.md)
records completion and the current-authority receipt boundary.

## Configuration and listeners

`tls` is server configuration, never a project override. TLS and ACME issuance
are separately enabled, both defaulting to false. Disabling issuance can retain
a valid managed certificate for HTTPS. The defaults are native HTTPS on 8443
and a separate HTTP-01 challenge listener on 8080; public HTTP-01 validation
requires routing public port 80 to that challenge listener. The existing private
HTTP bootstrap/repair listener remains separate. The challenge listener serves
only the exact active challenge token: it is not a redirector, Admin endpoint or
general application HTTP service.

The first profile supports HTTP-01 only. DNS-01, DNS credentials and external
account binding are unsupported. The ACME directory defaults to Let's Encrypt
staging. Enabling issuance requires explicit terms acceptance, contact email and
one to twenty normalized DNS names. The optional `ca_cert_file` configures
outbound directory trust only; it is not a certificate to serve. Account keys,
certificate generations and owner witnesses are private managed state, not API
fields. Rebinding a stopped full copy uses the existing explicit offline storage
rebind procedure; no reset or foreign state adoption is implied.

## Admin operations

Only the Admin role may use either operation. They accept no `project_id`.
The [examples](acme-examples.json) are illustrative schema vectors, not observed
issuance results or a complete production configuration.

- `{"op":"tls_status"}` returns the redacted server status and current
  `config_revision`. It reports HTTPS and issuance states separately, requested
  and active domain sets, optional certificate fingerprint/serial/validity,
  attempt timestamps and a closed public error. It exposes no private paths,
  keys, challenge authorization, raw client output or account credentials.
- `tls_renew` requires `expected_revision`, `confirm:true` and a stable
  `message_id`, using the existing mutation envelope and retry identity rules.
  `accepted:true` means the request was admitted, not that a certificate was
  issued. Poll status for the result. Concurrent requests coalesce with the
  current attempt, and manual requests do not bypass a persisted issuer retry
  floor.

Failed renewal keeps a still-valid prior certificate. HTTPS fails closed when
that certificate expires or is not yet valid; it does not silently downgrade to
HTTP. The separate private Admin repair path and redacted errors are distinct
from a ready public HTTPS listener. Port collisions during hot configuration
must preserve the prior committed listener/configuration.

A2A, Admin envelope version 1 and peer versions 1/2 remain unchanged. The
[archived 2.1 exports](v2.1/README.md) omit this additive surface; do not infer
2.2 support from an older artifact's profile.
