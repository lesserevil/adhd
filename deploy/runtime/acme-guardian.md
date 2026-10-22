# Managed ACME client process

ACME-001's guardian is an app-owned Linux helper, not a shell or external ACME
service. The application selects a fixed hash-verified sibling executable; no
operator-supplied executable, hooks or environment files are supported.

```
acme-guard --lock-file /private/acme/owner.lock --timeout-ms REMAINING --grace-ms 250 -- /fixed/lego ARGV...
acme-guard --probe-lock /private/acme/owner.lock
```

`REMAINING` is the remaining accepted order budget (1..3600000 milliseconds).
The guardian captures one absolute CLOCK_MONOTONIC deadline at entry; stdin data
never resets it. Raw BEAM monotonic timestamps have a different offset and must
not be passed as POSIX clock values. Closing stdin, loss of the parent, TERM/INT/HUP
or deadline expiry terminates the owned child process group, escalates to KILL,
and waits for owned/adopted descendants before releasing the lock. The direct
child PID remains unreaped until group signalling finishes, avoiding group-ID reuse.
No daemon mode or shell interpretation is used.

The lock's parent must be an owned private directory; paths are walked without
symlinks. The lock is owned, regular, non-hardlinked and private0600. Nonblocking
flock is held through child-group cleanup/waitpid and never unlinked. Probe mode
spawns no child, reports actual acquisition and releases on exit. Restart/worker
cleanup must wait for successful lock probe rather than guessing a cleanup delay.

Exit status: 64 invalid argv; 75 lock busy; 124 accepted order budget elapsed;
125 cancellation/private-path/guardian failure; 127 failed exec. Otherwise the
client's status is preserved. Successful client exit also cleans remaining group
members. Kernel-uninterruptible tasks and hostile children escaping their process
group are not a new security boundary: only the fixed maintained HTTP-01 client
with hooks disabled is eligible, not arbitrary untrusted programs.

The checked-in C source and local process tests qualify host behaviour only.
Packaged static-musl binary provenance, actual-image execution and client/CA flows
are separately required. Dependency pins retain original upstream release assets,
license and SPDX hashes; a patched-client build and its own dependency inventory
must be distinguished from stock upstream binary/SBOM evidence.

Compose/Kubernetes application settings and public TLS/challenge instructions are
owned by the [ACME operator guide](../../docs/admin/acme.md), when supplied by the
owning feature branch. Accounts/certificates/order state belong in the durable
private config mount; /runtime helpers remain immutable image content. AppHTTP8766
stays private, HTTP-01 serves only tokens on8080, and HTTPS uses8443 (alternate
isolated acceptance port18443 preserves existing host listeners).
