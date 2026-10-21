# Retired agent ownership validation

An agent ID can retain private deliveries, acknowledgements, subscriptions,
owned queries and idempotency receipts after its credential, owner and project
grants are removed. Creating a credential under that same ID must therefore be
an explicit Admin recovery decision. A Developer can create a fresh identity;
they cannot acquire a retained identity, including one whose state belongs to a
project they cannot access.

The [evidence manifest](../validation/agent-retirement-manifest.json) binds the
following independent native runtime observations to exact artifact, harness and
report hashes:

- [Source31 negative witness](../validation/agent-retirement-31-negative.json):
  all seven Developer recreation attempts succeed, and the queued-message case
  exposes the former owner's private delivery to the replacement owner.
- [Source32 ownership regression](../validation/agent-retirement-32-native.json):
  all seven attempts return `409 IDEMPOTENCY_CONFLICT`, with unchanged
  configuration and unauthorized replacement credentials. The test restarts
  before recreation attempts to exercise cold retained snapshots. Explicit Admin
  recovery preserves saved resource IDs and acknowledgements across another
  hard restart; an acknowledged message is not delivered again.
- [Source32 snapshot faults](../validation/agent-retirement-32-faults-native.json):
  missing and corrupt atomic snapshot evidence both block fresh identity
  creation. Responses conform to the served protocol's error schema and declared
  status profile. Exact configuration remains unchanged, the proposed credential
  remains unauthorized, and healthy creation succeeds after restoring the exact
  original snapshot bytes.
- [Initial fault harness diagnostic](../validation/agent-retirement-32-harness-diagnostic.json):
  the application safely returned `503 CONFIG_WRITE_FAILED` for corruption, but
  the first test's arbitrary status whitelist omitted 503. This is retained as
  a harness failure, separately from the corrected qualification.

The fixture uses public management and official A2A SDK interfaces to create and
inspect retained state. Snapshot fault injection neither decodes nor fabricates
application records. Tests support a verified Docker image with actual container
replacement, but these reports make no source32 image qualification claim.
