# Roadmap implementation and acceptance

[Project guide](../README.md) → roadmap implementation

The nine original pending entries were implemented together on `feat/roadmap`:
INFO-002 contextual evidence; QUERY-001 semantic scans; INFO-003 current answers;
SEARCH-001 retrieval; SEARCH-002 fallback/audits; SEARCH-003 attempts/replay;
INDEX-001 qualified adaptation; AUTH-001 optional OIDC; DOCS-002 documentation gates.
The dependency order keeps original evidence authoritative before adding derived
queries and indexes. [The historical design](../history/roadmap/adaptive-retrieval.md)
retains the initial rationale; named Component specifications own current behavior.

The implementation extends the previously accepted portable Elixir runtime and was
admitted through the acknowledged retained-source lifecycle. An earlier generated
candidate supplied only validators and was rejected as incomplete. The final
implementation, native test manifest, dependency inventory and qualification evidence
are retained in the [committed source entry](../../generated/committed-source-cache/entries/sha256/204e51b86ff75ebddea490e0f24d7960b167cf82f34b309dbdf01bafdd7fd23d.json).
Cache bytes are requalified before use. The [build helper](../../scripts/build_hub.py)
materializes matching content-checked source, invokes the normal retained-source
plan/authorization/build gates, and exports the accepted script. It avoids an
ordinary build silently starting another generation. No framework policy was weakened.

The accepted portable script SHA256 is
`b533b59f70b971dcbf44dd4e96e81b28972485246da99fcace40862a10749133`.
Fresh reports bind this artifact separately from historical MVP evidence:

| Evidence | Scope |
| --- | --- |
| [Compatibility and migrations](../../verification/roadmap-hub-acceptance.json) | 31 Linux SDK scenarios, real schema-1/schema-2 upgrades, hard restart, old retries, private visibility and live Nemotron subscriptions |
| [Queries and current facts](../../verification/roadmap-acceptance.json) | 7 protocol/failure/recovery scenarios plus real generative start/completion/late-event and contextual bird interpretation scenarios |
| [Real retrieval model](../../verification/roadmap-retrieval-model.json) | Paraphrased question ranked the independently expected publication first with actual Nemotron scoring; caller limit respected |
| [OIDC](../../verification/oidc-acceptance.json) | 6 independently signed provider scenarios, including thirteen invalid token/identity cases, PKCE, sessions, expiry, CSRF/origin, restart and confidential client authentication |
| [Adaptation](../../verification/adaptation-acceptance.json) | 10 scenarios: disjoint replay cohorts, improvement, insufficient evidence, quality/resource rejection, promotion/catch-up, rollback, retirement and automatic operation |
| [Rendered browser](../../verification/roadmap-browser.json) | Key and OIDC sign-in, Activity/index rebuild and logout at 1440px and 390px; no normal-path runtime errors or document overflow |
| [Container compatibility](../../verification/roadmap-container-baseline.json) | 33 hardened-container scenarios, including real matching, replacement, stopped-store backup/restore and rollback |
| [Container roadmap](../../verification/roadmap-container.json) | 23 new query, journal, OIDC and adaptation scenarios in hardened containers |
| [Reproducibility](../../verification/roadmap-container-reproducibility.json) | Two independent no-cache builds match, with pinned runtime and deterministic specification directories |
| [Lifecycle receipt](../../verification/current.json) | Current authority, six native cases with additional domain assertions, and eleven independent CLI vectors |

An actual hard-kill upgrade check exposed DETS repair requirements. The fix commits
a checksummed full-state journal by atomic rename before updating the working DETS
image. Acceptance recovers an unreadable working image and rejects a corrupted
authoritative journal. Offline backup/restore preserves the entire data directory.
These checks establish process-crash recovery, not a stronger power-loss guarantee.

Documentation review covered `PROJECT.md`, root and project READMEs, setup/API/usage/
stored-information/query guides, console/OIDC/retrieval/operations/troubleshooting/
Kubernetes guides, architecture traceability, coordination instructions, helper help
and the roadmap. Claims were checked against named specifications, the accepted
source and the fresh reports above. The documentation-update plan's `work` and
`config` command warnings are false positives: both command help paths succeed.
Source-intelligence and framework HTML gates are skipped by project configuration;
the frontend was inspected independently in Playwright. Documentation review
markers, full project verification and whitespace/link checks
are refreshed after the final queue update. Earlier deployment reports remain intact.

Linux was executed with Elixir 1.20.4/OTP 29.1.2 and the pinned Linux container.
The service also supports macOS using the same standard-runtime script; no matching
macOS worker was available for fresh execution. OIDC fixtures qualify the supported
protocol profile, not a live enterprise identity-provider deployment. Generative
model judgments remain fallible; full scan coverage does not guarantee truth.
Adaptation is disabled by default and uses declarative capability changes only.
DETS full-state writes, full-state journals and bounded scans remain prototype
scaling limits. Existing Docker/Kubernetes services, credentials and stores were
preserved; this branch has not been deployed or remotely published.

Local handoff review normalizes the protocol specification's trailing whitespace.
The runtime artifact remains byte-identical to the independently tested script.
Git attributes preserve immutable cache bytes; authored staged changes pass
`git diff --cached --check`. The refreshed source entry and lifecycle receipt
bind the normalized specification.
