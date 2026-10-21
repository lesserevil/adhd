---
name: hub-management
summary: Authenticated observation and management of the private hub
kind: component
---
# Hub management

Extend the same portable artifact and HTTP server with an embedded web console.
Use Elixir standard runtime facilities for the server and dependency-free browser
HTML, CSS and JavaScript embedded in the artifact. No CDN, separate frontend build,
additional server, or external assets are required. Include an embedded data-URI
favicon so a normal browser session makes no missing favicon request. Preserve every existing A2A,
archive, persistence, CLI and matcher contract.

## Administrator boundary

configuration/spec.md and identity/spec.md explicitly extend this legacy contract
with Settings/Users/Agents views, live settings, local/OIDC human sessions, cookies,
CSRF and server-side per-user roles. The no-cookie rule below applies to the legacy
bearer-token login only. Their role matrix governs human access; this document
continues to govern unchanged metadata-only legacy list responses. The explicit
Admin-only private_delivery operation is the exception permitting requested full
Admin data access without adding private bodies to existing list responses.


Configuration optionally accepts admin_token: a nonblank string 32–65536 UTF-8
bytes, different from every agent token. Invalid values fail startup without
printing secrets. Absent admin_token leaves existing configurations valid and
makes /admin/api return 404. Agent credentials cannot authorize administrators;
the administrator credential cannot authorize A2A. Credentials never enter DETS,
HTML/assets, JSON responses, logs, exception diagnostics or process status output.

GET /, /admin and /admin/ serve the same anonymous HTML login shell. GET
/admin/assets/app.js and /admin/assets/app.css serve embedded assets with correct
JavaScript/CSS MIME types. No project data is embedded in the shell. Protect shell,
assets and admin responses with Cache-Control: no-store, X-Content-Type-Options:
nosniff, Referrer-Policy: no-referrer and Content-Security-Policy default-src 'none';
script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:;
frame-ancestors 'none'; base-uri 'none'; form-action 'self'. No inline handlers,
inline scripts/styles, eval, CORS, cookies or URL credentials. Render stored values
using textContent, never HTML interpolation. JSON and text details wrap safely.

POST /admin/api requires application/json and Authorization: Bearer ADMIN_TOKEN.
Absent/invalid credentials return 401 with WWW-Authenticate: Bearer. Authenticate
before decoding commands; compare tokens with constant-time comparison. If Origin
is supplied it must equal the request Host origin or configured public_url origin;
otherwise 403. Successful JSON responses are objects defined below. Errors have
shape {"error":{"code":CODE,"message":GENERIC_MESSAGE}}, with 400 INVALID_PARAMS,
404 NOT_FOUND and 409 IDEMPOTENCY_CONFLICT. Do not echo input or secrets in errors.
Unknown operations/fields, invalid types or bounds are invalid parameters. Existing
HTTP header/body bounds, loopback binding and request handling deadlines apply.

## API commands

All commands require op. Optional limit on list operations is integer 1–100,
default 50. Lists are newest first using existing durable sequence ordering and
respond with items plus truncated boolean (true iff further matching rows exist).
Read-only operations accept no message_id. Optional agent_id filters are validated
identifiers and, when supplied, must name a configured agent (otherwise NOT_FOUND).
No read operation mutates storage or consumes queued deliveries.

- overview: accepts only op. Returns project_id; counts containing agents,
  publications, subscriptions, queued_deliveries, pending_jobs, completed_jobs,
  cancelled_jobs; agents list containing agent_id, subscriptions and queued_deliveries;
  matcher containing status, checked_at and model. Agent totals include configured
  agents even when idle. Counts queued_deliveries exclude acknowledgements. No
  credential, matcher URL, file path, private text/data or raw error is returned.
- publications: optional query, information_type, source_kind, source_id, limit.
  Apply the existing search semantics and exact filters, but an empty command lists
  recent publications. Items are complete project-published envelopes. Query must
  be nonblank when supplied and follow existing query bounds. No private sends.
- publication: requires publication_id; returns {publication: ENVELOPE}; unknown or
  private delivery IDs return NOT_FOUND.
- subscriptions: optional agent_id and limit. Items contain the existing complete
  subscription records, including their owner agent_id and plain-text description.
- deliveries: optional agent_id and limit. Items contain only delivery_id,
  recipient_id, kind, created_at, acknowledged boolean, and publication_id when
  present. Include acknowledged and pending records for observation. Never include
  private body, text, data, or other private envelope fields, even for administrators.
- jobs: optional status (pending, done, cancelled) and limit. Items contain job_id,
  publication_id, subscription_id, recipient_id, status and retry_at (epoch ms).
  Never expose raw model requests/responses/errors or credential-bearing URLs.
- create_subscription: requires agent_id, description, message_id. Use existing
  subscription bounds, ownership, ID allocation and creation semantics; no replay
  of old publications. Returns the same subscription result as agent subscribe.
- remove_subscription: requires subscription_id, confirm:true, message_id. Remove
  the subscription regardless of owner and cancel pending associated matching jobs;
  leave queued/acknowledged deliveries intact. Returns {removed:true,
  subscription_id:ID}; missing ID returns NOT_FOUND.
- retry_jobs: requires confirm:true and message_id. Reset retry_at to zero for
  pending jobs only and return {retried:COUNT}. Never resurrect done/cancelled jobs,
  acknowledgements, or deliveries. Model worker continues normal retry policy.

Mutation message_id is a nonblank string 1–128 UTF-8 bytes. Persist successful
mutation command/result atomically in a separate administrator idempotency namespace.
An identical retry returns its original result across restart; reuse with a changed
command returns IDEMPOTENCY_CONFLICT. Concurrent mutations serialize through the
same durable writer as agent commands. No unpersisted successful result is allowed.
Backward-compatible schema-2 stores without administrator idempotency remain readable;
retain every publication, delivery, acknowledgement, subscription and pending job.

The accepted schema-2 DETS :state map already has an atom-keyed :sources index:
keys are {authenticated_actor, source_kind, source_id, source_item_id} tuples and
values are %{command: canonical_command, result: original_result}. Canonical command
omits string keys op and project_id. Continue using this existing :sources index
for schema 2; never silently replace it with a new empty index. Existing entries
must return their exact original results when the same event arrives under a new
A2A message ID; changed content must still raise SOURCE_CONFLICT. Preserve each
record's durable seq/value wrapper, delivery ack, job fields and idempotency map.
Add native coverage that upgrades an already populated original schema-2 sources
map and exercises same-event retry plus changed-event conflict. This management
extension does not require a new persistence schema. A schema-1 store gains sources
as an empty map when upgraded, as in the already accepted information extension.

Matcher status is a bounded health observation, not inferred from queue emptiness.
Probe GET /health at the configured matcher URL's origin, with at most 2000 ms
network timeout, outside the durable writer; ready:true means status ready, otherwise
unavailable. checked_at is UTC ISO8601 time. model is the configured model name.
Failure must not stall A2A, /health or durable writes. Do not report successful health
as proof that every relevance classification will succeed.

Add CLI ["validate-admin", COMMAND], performing the same pure command validation
without authentication/storage/network and returning exactly {"valid":true,"op":OP}
on success; invalid inputs exit nonzero with generic stderr diagnostics. Keep native
vectors independent of verifier-owned oracle vectors.

## Console interaction and design

Provide four working views: Overview, Information, Subscriptions and Activity.
Use a restrained operations-workspace layout: light slate canvas, dark navy text,
blue selection, teal healthy and amber pending states, local Avenir/Segoe UI sans
fonts, clear typography, tabular counts, separated rows rather than decorative card
grids. Desktop has a compact left navigation; narrow screens use a horizontal
navigation and stacked forms. No marketing hero, gradients or fabricated charts.

The password login input is labeled Administrator token. Keep the bearer only in a
JavaScript variable, clear the password field after submission, never localStorage,
sessionStorage, cookies, URL, history or console. Reload requires login. Logout
clears token and all project data from DOM. Unauthorized/expired requests return to
login without exposing stale data. Show useful generic network/API errors and allow
retry. Labels, keyboard focus, headings, status/error live regions and contrast must
support accessibility. Loading/empty/error states are explicit. Disable duplicate
mutation submissions. Preserve each mutation message_id when retrying an uncertain
network result. Avoid stale overlapping responses replacing newer navigation/search.

Overview shows counts, two-agent rows, service reachable state and actual matcher
health with observation time. Information provides recent information, text search,
exact type/source filters, results and a full detail panel for provenance/content.
Subscriptions shows owners/descriptions, creates a subscription for a selected agent,
and removes one only after a confirmation identifying its owner and description.
Cancellation must perform no mutation. Activity shows delivery metadata and matching
jobs with status and offers confirmed retry of pending jobs. Neither page nor detail
panels reveal private addressed content. Manual Refresh updates the active view and
shows last checked time. Refresh reloads current project admission and display names
before querying project data. If the selected project is no longer admitted, clear
its pending actions and select another admitted project explicitly in the selector,
or show the no-project state. A stale project response must not restore revoked
context. No automatic refresh is required. List truncation is visible.
At 390px mobile width no document overflow; wide tables can scroll within labeled
regions. Desktop and mobile all primary actions remain reachable. No page, console,
uncaught script, missing asset or unexpected network errors on normal paths.

## Acceptance

Test two distinct agent credentials plus separate administrator credential; missing,
wrong and agent credentials on admin, admin on A2A, disabled legacy config, wrong
Origin, unknown fields, invalid bounds, credential leakage and malicious stored text.
Exercise full published messages/status/search/details, subscription create and
cancel/remove, queue observation without private content, matcher ready/outage,
confirmed pending retry, persistence and exact mutation retry/conflict after restart.
Validate ordinary SDK behavior and container operations still pass. Inspect desktop
and 390px rendering in an instrumented browser, including login/logout/reload,
search/empty results, details, management confirmations, outage and overflow checks.
Document credential provisioning/rotation, access through the private tunnel, private
visibility boundary, actions and limits, troubleshooting and durable backup/upgrade.
