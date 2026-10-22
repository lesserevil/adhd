# Managed HTTPS and ACME

[Project guide](../README.md) → managed HTTPS

ACME-001 adds application-managed certificates and native HTTPS to application
profile 2.2. Implementation qualification is in progress; the accepted profile
2.1 artifacts do not provide these controls. See the
[roadmap evidence](../roadmap/active-work.md#acme-001-obtain-and-renew-tls-certificates-through-built-in-acme)
for the current qualification boundary.

The packaged ACME runtime targets Linux amd64. Other available language/OS
Flavors retain their existing disabled-TLS CLI scope; their ACME deployment is
not qualified by this feature’s Linux evidence.

An Admin configures **TLS** in the console. Domains, contact email, issuer,
HTTPS and challenge listeners, terms acceptance, renewal policy, retry delay,
order timeout and an optional private issuer CA file are hot settings. Developers
and Viewers cannot read certificate-management status or change its settings.
Certificates belong to the server, independently of project membership or stores.

## First setup

Keep the existing private HTTP Admin connection available during setup. Native
HTTPS and issuance are disabled by default. The initial issuer is Let's Encrypt
staging; its certificates are not trusted by public browsers. There is no automatic
switch to production.

1. Set DNS A/AAAA records for every intended hostname. Every published address must
   reach this server. HTTP-01 does not support wildcard names or IP certificates.
2. Route public TCP port **80** to the configured challenge listener (default
   **8080**). This listener serves only active HTTP-01 token proofs. It cannot serve
   Admin, A2A, health or project data. Merely opening external port 8080 is not enough:
   public ACME authorities validate HTTP-01 on port 80.
3. Route public TCP port **443** to the native HTTPS listener (default **8443**) if
   you want conventional HTTPS URLs. Keep the private HTTP listener (default 8766)
   behind its existing private access boundary. Do not publish private HTTP as a
   fallback when HTTPS is unavailable.
4. In **TLS**, enter the issuer directory URL, your contact email and explicit
   hostnames. Accept that issuer's account terms, enable native HTTPS and enable
   ACME issuance. Save the confirmed settings. No hostname or contact address is
   inferred from the machine, another project or a test fixture.
5. Refresh certificate status. Check active hostnames, certificate expiry and any
   actionable error. Before the first valid certificate, HTTPS connections fail
   closed; the app does not create a temporary self-signed certificate.
6. Once a client verifies the certificate and hostname, set the advertised
   `public_url` in **Settings**. Update OIDC redirect URI/provider registration to
   the exact HTTPS callback. HTTPS sessions use Secure cookies and the existing
   origin/CSRF checks. Native TLS does not weaken agent or peer authentication.

Production use requires an explicit issuer change and terms acceptance for the
production account. Issuer/contact/trust changes select isolated account state;
never copy a staging certificate into a production claim. HTTP-01 is the supported
challenge method. DNS-01, DNS provider credentials, external account binding and
operator-supplied arbitrary client flags/hooks are not supported in this profile.

## Renewal and failure behavior

The hub schedules renewal before expiry using the configured day window. For
short-lived certificates, the window is capped at one third of the certificate's
lifetime. **Request certificate renewal** schedules an asynchronous manual attempt.
A valid issuer `Retry-After` minimum still applies. Its durable private floor
survives a client timeout or restart, including when the client is interrupted
during its own backoff. An issuer minimum beyond the supported year-9999 status
range blocks automatic attempts with a storage/status error; it is never silently
replaced with an earlier local retry. Repeating the same mutation ID
replays its durable receipt; a separate request during an active attempt coalesces.
The console request returns promptly rather than waiting for the CA.

Each server runs at most one managed client attempt. Attempts have bounded
monotonic deadlines and owned process cleanup. Account keys survive successful
renewals; leaf keys rotate. The maintained, pinned Lego client performs ACME
account/order/challenge operations. The hub validates and publishes complete
certificate/key generations atomically. Existing TLS connections finish normally;
new handshakes select the current valid generation.

Failed renewal retains the previous usable certificate. A desired hostname edit
may leave an older certificate active for its covered hostnames while the new
order is pending; status distinguishes desired and active names. Uncovered SNI
names and expired certificates fail new handshakes. Disabling issuance retains a
valid certificate for HTTPS; disabling TLS closes new HTTPS admissions. Neither
case silently enables public HTTP.

An occupied replacement listener rejects the configuration change and preserves
the old settings and listener. A CA outage, rejected challenge or invalid issuance
is an asynchronous error, with sanitized status and retry timing. Private issuer
CA trust is frozen per attempt and applies only to the directory connection; it
does not grant browsers or federated peers trust in the issued certificate.

If a referenced CA file disappears or a native listener is occupied at startup,
private HTTP/Admin remains available and status reports the managed error. Issuance
is blocked until an Admin repairs the setting; a valid retained certificate may
continue serving if its listener remains available. Dry validation and hot saves
strictly check trust files and bind replacements before committing. After removing
a port conflict, saving the same listener settings can repair the failed bind.

## Private state and recovery

The only startup configuration location is `CONFIG_FILE`. Managed state lives in
its adjacent `acme/` directory, with accounts, transient attempts, immutable
certificate generations and a durable scheduler/publication pointer. The adjacent
`CONFIG_FILE.acme-owner.json` witness binds initialized state to that configuration.
Directories are owner-only (0700); private files are owner-only (0600). Symlink
or foreign-owner state is rejected. Keys, token proofs, account URLs and raw client
output never appear in public or Admin status.

A stopped full-server backup must include the configuration and its journals,
ACME owner witness and entire managed directory. Preserve ownership and file modes.
Project-only restore never rolls back server certificates or accounts. Do not delete
an initialized directory to recover from an error: losing state is reported rather
than silently registering replacement accounts. Restore the matching stopped
backup and follow the existing offline metadata-rebind procedure when moving the
installation. Keep backups confidential because they contain account and leaf keys.

Restart revalidates complete persisted generations, retires interrupted challenges
and reconciles client state. It never treats a client working file or saved success
message as a published certificate. The independent initialization witness detects
lost initialized state. External TLS termination remains available with managed TLS
disabled; configure its trust, certificates and network exposure separately.

## Interfaces and validation scope

The exact configuration, status, renewal envelopes and errors are specified in
`components/hub/acme/spec.md` and its
[closed schema](../../components/hub/acme/interface.schema.json). The application
profile adds `tls_status` and `tls_renew` to `/admin/api`; agent A2A and peer
protocol identities retain their existing authentication and project semantics.

A real isolated ACME CA can prove account registration, HTTP-01 validation,
issuance, renewal and recovery without publicly trusted issuance. Public issuer
staging additionally needs an owned configured domain and working external DNS,
port-80 routing and issuer connectivity. Those are separate evidence scopes;
fixture certificates do not prove public CA or production-domain readiness.
