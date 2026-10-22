# Event recovery and historical replay, profile 2

This describes the target profile-2 wire contract in
`components/hub/eventing/spec.md`. Older accepted artifacts do not implement these
operations. Current implementation and recovery evidence remain subject to the
open KAFKA qualification gates in [active work](../roadmap/active-work.md).

All requests below use `POST /admin/api`, JSON, and an authenticated Admin
principal. Browser sessions require the existing origin and CSRF checks. An agent
A2A credential cannot administer recovery. Project scope follows the ordinary
profile-2 rules: supply `project_id` when more than one project can be selected.
The exact served schema is available through `GET /protocol/schema`; the owning
normative contract takes precedence over these explanatory examples.

| Operation | Required fields besides `op` and project scope | Result |
| --- | --- | --- |
| `eventing_status` | None | Transport watermarks, checkpoint, control revision, pending counts, quarantine descriptors, gap and last error. |
| `repair_eventing` | `message_id`, `confirm:true`, `reason`, `offset`, `expected_checkpoint`, `expected_digest`, `action` | `{audit_id,control_revision,next_offset}`. |
| `replay_events` | `message_id`, `confirm:true`, `reason`, `from_sequence`, `to_sequence`, `expected_watermark`, `subscriptions:[{id,revision}]` | `{replay:{id,status,event_ids,subscriptions,created_at}}`. |
| `eventing_replay` | `replay_id` | The same replay wrapper, with its current status. |
| `eventing_audit` | None; optional `offset` and `limit` | `{items,truncated}` in durable audit order. |

Every request and response has a closed schema. JSON integers must be integer
tokens; a fractional/exponent representation must not stand in for a checkpoint,
revision or sequence. `reason` is nonblank and at most 1024 UTF-8 bytes. Identical
actor/project/message-ID retries return their original accepted result before
checking preconditions that may now be stale. Reusing that ID for different
arguments fails `IDEMPOTENCY_CONFLICT`.

## Quarantine repair

First read `eventing_status`. Its `quarantines` array contains at most one blocking
record, with `offset`, `reason`, `digest` and `at`. Digest is the lowercase
64-character SHA-256 identity of the quarantined physical record; it is not a
publication ID. An unparseable physical offset is null.

```json
{
  "op": "repair_eventing",
  "project_id": "project-a",
  "message_id": "repair-request-1",
  "confirm": true,
  "reason": "Retry after repairing the broker record",
  "offset": 42,
  "expected_checkpoint": 42,
  "expected_digest": "0000000000000000000000000000000000000000000000000000000000000000",
  "action": "retry"
}
```

The digest and positions above are illustrative. A real request must copy the
observed digest and current checkpoint from the status response.

`retry` clears the matched quarantine, increments the control revision and
recreates the consumer at its unchanged checkpoint. If the bad record is still
present, it will quarantine again. For an unparseable offset, submit the current
checkpoint as `offset`; only retry is allowed.

`reconcile` requires a parseable quarantined offset equal to the current
checkpoint. It audits the physical skip, requeues any accepted pending original
whose producer acknowledgement names that offset, and advances to offset+1.
Unknown broker content never becomes an original, a recipient delivery or model
input. The audit's `missing_logical_proof` distinguishes a skip without a linked
accepted original. Repair remains available for archived projects so previously
accepted work can drain.

## Explicit historical replay

`replay_watermark` is the maximum retained publication ingestion sequence, or zero
when there are no publications. It is distinct from the Kafka accepted watermark:
retained pre-cutover originals can be replayed even if they have no prior outbox
entry. Read current subscriptions and select their exact revisions.

```json
{
  "op": "replay_events",
  "project_id": "project-a",
  "message_id": "replay-request-1",
  "confirm": true,
  "reason": "Provide the selected retained history to the new subscriber",
  "from_sequence": 1,
  "to_sequence": 100,
  "expected_watermark": 120,
  "subscriptions": [{"id": "subscription-a", "revision": 1}]
}
```

The inclusive range must contain retained originals, end at or below the observed
watermark, and select at most 1000 originals. Select 1..64 distinct active
subscriptions with admitted recipients. Filtered targets require a matcher.
Prospective additional event/target work is limited to 16 MiB and must also fit
the configured outstanding event/byte limits. Validation is atomic: a rejected
range admits no partial replay. Archived projects reject new replay work.

Replay preserves original IDs and immutable envelopes and uses Kafka transport.
It freezes its explicit targets separately from ordinary subscription activation
snapshots. A replay can append a match reason with `replay_id`; it preserves the
single logical recipient/publication delivery and its acknowledgement. It never
changes normal activation watermarks or silently adds other historical events.

| Replay state | Meaning |
| --- | --- |
| `pending` | Some selected targets still await durable materialization. |
| `materialized` | All selected targets have durable delivery/filter work. Model decisions and agent acknowledgements may still be pending. |

## Errors and recovery

| Code | Ordinary HTTP | Action |
| --- | --- | --- |
| `EVENTING_CONFLICT` | 409 | Refresh checkpoint/digest/watermark/subscription revisions, then submit a new intentional command. |
| `IDEMPOTENCY_CONFLICT` | 409 | Do not reuse a mutation ID for different arguments. |
| `RANGE_TOO_LARGE` | 413 | Select a smaller replay. |
| `BACKPRESSURE` | 503 | Accepted work is retained; retry unchanged after capacity recovers. |
| `EVENTING_DISABLED`, `MODEL_UNAVAILABLE` | 503 | Enable the required capability; do not retry indefinitely without a configuration change. |
| `CONFIG_APPLY_IN_PROGRESS` | 503, `Retry-After:1` | Retry the same command and mutation ID after bounded backoff. |
| `PROJECT_ARCHIVED` | 403 | Resume the project before starting replay; repair/audit remain available. |

Audit records retain actor, project, mutation ID, reason, time and exact control
arguments, without broker payloads or credentials. Audit, replay plan, outbox and
mutation result commit together. A lost response is uncertain: retry the original
command and ID before initiating another control. A restart must preserve those
identities and finish any separately decided transport or store transition.
