# Web management console

[Project guide](../README.md) → [Operations](operations.md) → Web console

Open the hub's private URL at `/admin`. On first installation, sign in as `admin`
using the randomly generated password in `initial-admin-password.txt` beside the
configuration file. The file is owner-readable only. Configure local accounts or
OIDC through Settings; the built-in admin remains available through local login.
Never put passwords, tokens or client secrets in URLs, issue reports or screenshots.
Use a private tunnel or an authenticated TLS deployment boundary for remote access.

Local login and OIDC establish protected, server-side sessions. Cookies are
HttpOnly/SameSite; browser mutations require same-origin and CSRF checks. Log out
revokes the session. Agent credentials do not grant console access. A separately
configured administrator token works only when explicitly allowed by auth policy;
the console keeps that bearer in page memory and requires sign-in after reload.
The anonymous shell discloses no project information.

Each user has one server-local role. Admin can inspect and manage all server
resources. Developer can inspect public server state and create agents on their
own behalf. Viewer can inspect and cannot change state. Only Admin assigns roles
or group mappings. OIDC users receive the highest role mapped from their groups;
remote same-email identity matches never transfer permissions. Sessions recheck
current policy after hot role/configuration changes.

- **Overview:** publication, subscription, delivery and job counts, configured
  agents, matcher connectivity and safe retrieval-index status. Connectivity is
  an observation, never a classification-quality guarantee.
- **Information:** public original records, literal text and exact source/type
  filters, communication context, immutable identity and provenance. Incoming
  corrections remain separate originals. Acknowledgement does not remove records.
- **Subscriptions:** descriptions and owners. Admin can create or confirm removal
  on behalf of agents. New subscriptions affect future publications; removal
  cancels pending matching work and retains accepted deliveries.
- **Activity:** delivery metadata and matching jobs; Admin can retry pending
  matching work and inspect/cancel discovery, source, history and retrieval jobs.
  History/retrieval evidence exposes coverage, versions, costs, exact model inputs,
  original provenance, prior runs and bounded pages. Private addressed contents
  require the explicit Admin-only private-delivery API; they never join public
  information or retrieval.
- **Users:** Admin-managed local name/email/password, one role, disabled state and
  explicit OIDC linking. Users can complete their own profile through the provided
  controls. OIDC profile links retain provider, issuer and subject.
- **Agents:** Admin credential/ownership management; Developer creates only an
  agent owned by their own authenticated account. Agent tokens are separate from
  human sessions. Save generated credentials before applying changes.
- **Settings:** all operational configuration, including OIDC setup and connection
  verification, role-group mappings, listener/store changes, matcher, federation
  peers, canonical catalogs and evaluator/index policies. Only the configuration
  file location is selected at startup. Blank secret fields retain secrets;
  explicit removal controls revoke them. Blank history/retrieval URL/model fields
  restore subscription-matcher inheritance.

Settings changes are revision checked and confirmed. Invalid or failed changes
retain the previous active configuration. Changes apply without restarting the hub
and persist across restarts. A conflict requires refreshing before resubmission.
Back up the whole storage directory, including its durable snapshot, before moving
or restoring accepted data; see [operations](operations.md).

Retrieval indexes in Settings exposes model inheritance, confidence, timeouts,
budgets, storage bounds and primitive recipes. The index panel shows active,
previous and building generations, coverage, watermarks, progress and errors.
Confirmed Rebuild index retains originals and switches atomically after catch-up;
resource failures preserve the active index and allow ingestion. Overview exposes
safe status to read-only users. Candidate scores express relevance and never
establish truth or exhaustiveness; see [candidate retrieval](../user/retrieval.md).

Use Refresh to observe changes. General lists are bounded and disclose truncation;
query evidence has explicit pages. Product mutations use actor-scoped message IDs:
identical retries return the original result, changed retries conflict. The console
uses the same-origin `/admin/api`; direct API callers must satisfy the same role,
confirmation, revision and authentication requirements. Exact operations, response
shapes and errors are in the [wire profile](../protocol/README.md) and
`components/hub/management/spec.md`.


Archive questions in Settings exposes enablement/default mode, planner URL/model
inheritance from History, asserted version, timeout, request bound, confidence,
state cap, audit rate and all five stage budgets. Changes are hot. Activity includes
archive paths, coverage, sampling populations, provisional comparisons and exact
parent/child references. Admin can inspect paged original-model exchanges and prior
runs or cancel a pending/partial workflow. Human sessions remain separate from
agent ownership. See [archive questions](../user/archive-queries.md).

Admins have a **Feedback** page for captured Archive attempts, independent labels,
cohort/exposure summaries and paired recipe replays. **Activity** provides replay
stages, costs, evidence pages and explicit terminal-evidence retirement. **Settings →
Feedback and replay** controls all capture, replay and resource bounds without a
restart. See the [replay guide](../user/retrieval-replay.md) for ownership, exposure,
continuation accounting and the difference between retrieval recall and answers.

Admins use **Optimization** to propose bounded recipe variants from confirmed
independent training misses. A winner freezes before attaching fresh held-out and
regression attempts. Inspect per-case evidence, answer correctness and actual model
costs before explicit promotion. Review is the default mode; automatic selection
and promotion require enabled, explicit automatic mode and every current gate.
**Settings → Adaptive index optimization** exposes all thresholds, native/storage
limits, mode and aggregate budgets as hot structured controls.

The page distinguishes operator base from the effective learned recipe, previous
recipe and qualification runtime. **Reset to operator recipe** clears the override.
**Copy effective recipe to base** saves it as operator configuration and clears the
override, including when recipe values are unchanged. **Build and restore previous
recipe** catches up current sources before atomically switching; it remains a
recovery action when optimization is disabled. Retirement removes inactive derived
proofs without deleting publications, labels, exposure or selected generations.
Qualification covers the displayed cases and runtime; model interpretations and
human labels remain fallible. Exact messages are in `optimization/interface.md`
under `components/hub/`.
