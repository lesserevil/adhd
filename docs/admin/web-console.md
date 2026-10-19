# Web management console

[Project guide](../README.md) → [Operations](operations.md) → Web console

Open Agentic Distributed Harness Depot (ADHD) at the hub's existing private URL
(for the MVP, http://127.0.0.1:8766/ through
the SSH tunnel). Sign in with the separate administrator token. Agent tokens do not
work here. The service remains bound to loopback; use the private tunnel rather
than exposing the bearer-authenticated HTTP service publicly.

`scripts/configure_hub.py` creates `admin-token.txt` alongside the private server
configuration. Both files have mode 0600; keep them outside version control. For an
existing deployment, stop the hub, back up its config and DETS file as described in
[Operations](operations.md), generate a random token of at least 32 bytes, add it as
`admin_token` in the private server JSON, and save that token privately for the
administrator. It must differ from every agent token. Restart the service to apply
or rotate it. Omit `admin_token` to disable the administrator API; existing agent
clients and stored data continue to work. Never paste credentials into URLs, issue
reports, screenshots or shared client configuration.

The console keeps its bearer in page memory. Reload requires signing in again;
Log out clears the credential and project data. There are no persistent browser
sessions. The anonymous login shell contains no project information.

- **Overview:** stored information, subscriptions, queued deliveries and matching
  job counts, each configured agent's activity, and a bounded matcher health probe.
  Matcher health is a current connectivity observation, not a classification guarantee.
- **Information:** recent published information, text search and exact type/source
  filters, with complete content and provenance details. Acknowledging delivery does
  not remove information from this archive.
- **Subscriptions:** inspect descriptions and owners, create a subscription on
  behalf of an agent, or confirm removal. New subscriptions apply to future
  publications. Removing one cancels pending matching jobs; it preserves deliveries
  already queued or acknowledged.
- **Activity:** delivery metadata and matching-job status. Private addressed message
  text/data is never shown, including in administrator API results. Confirmed retry
  makes pending jobs eligible immediately; it cannot restore cancelled/done jobs or
  acknowledged deliveries.

Use Refresh to observe recent changes. Lists are limited to 50 by default (API
maximum 100), newest first; a truncation notice means more results exist. This is a
single-project prototype console, with one full administrator permission level.
It does not edit publications, acknowledge agent inboxes, manage credentials, ingest
external services, expose private message bodies, or provide historical metrics.

The same service supports `POST /admin/api` with `Authorization: Bearer TOKEN` and
`Content-Type: application/json`. Commands are `overview`, `publications`,
`publication`, `subscriptions`, `deliveries`, `jobs`, `create_subscription`,
`remove_subscription` and `retry_jobs`; exact fields and responses are specified in
`components/hub/management/spec.md`. Mutations require
a unique `message_id`; retry an uncertain request with the identical command and ID.
Reusing an ID for changed input returns 409. Removals and retries require
`confirm:true`. Mutation results survive restart. The API accepts no cookie auth or
cross-origin access; browsers must use the same origin as the console.
