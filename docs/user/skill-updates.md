# Updating ADHD skills

The stdlib bootstrap `scripts/adhd_skill_update.py` distributes shared coordination,
project participation and update skills using existing authenticated ADHD
publications. No manager is required. Each profile has one operator-selected
release source and one coherent installed revision, even when it works in several
projects. The bootstrap reports adoption to its configured project; additional
projects can retrieve their own independently published release announcements.

## Initial installation and trust

Install `adhd_skill_update.py` and `adhd_setup.py` beneath the profile's `scripts/`.
Create private `adhd-skills/policy.json` with this shape:

```json
{
  "project_id": "example",
  "publisher_id": "release-agent",
  "agent_id": "worker",
  "channel": "stable",
  "runtime": "hermes",
  "mode": "auto",
  "helper": ["/absolute/python3", "/absolute/profile/skills/adhd-hub/scripts/hub.py"]
}
```

Use the existing credential-reading helper; never put tokens in helper arguments.
The helper must accept a JSON command argument and optional `--message-id` and
return decoded hub command results. The operator chooses the trusted hub/client
and authenticated publisher identity out of band. A claimed source ID alone is
insufficient: the installer checks the server-assigned author and project too.
SHA-256 binds the manifest and every file. This trusts the authenticated HTTPS hub
and release publisher; it is not independent artifact signing against their
compromise. The fixed bootstrap is installed by the operator, not downloaded as
executable code from a peer. Incompatible bootstrap versions require an explicit
bootstrap upgrade.

Preserve local skill text and add a startup/safe-boundary instruction to run:

```text
python3 /profile/scripts/adhd_skill_update.py --home /profile sync
python3 /profile/scripts/adhd_skill_update.py --home /profile read
```

Read all returned instructions alongside the existing profile binding and local
notes. Shared release Markdown lives under immutable
`adhd-skills/releases/DIGEST/`; `current.json` selects a revision atomically.
Credential files, local skills, task receipts and project configuration are not
release payloads. Local modifications within a managed version fail verification
and remain intact for operator reconciliation.

## Publish a release

Build from the reviewed source tree:

```bash
python3 scripts/adhd_skill_update.py build --sequence 1 \
  --notes 'Describe this reviewed release' --output /private/release.json
```

Alternatively, `scripts/publish_adhd_skills.py --home PROFILE --sequence N
--notes TEXT` builds from the reviewed tree, saves the exact command for retries,
and publishes through a profile whose own identity is its configured publisher.
Publishing a reviewed release is the distribution trigger; uncommitted edits are
not automatically shipped.

Publish that JSON as `data` of an `adhd.skills.release` publication from the
configured release identity, using a unique stable source.item_id and message ID.
Increment sequence for every new release. The manifest includes channel, minimum
bootstrap, file inventory/content digests, notes and revoked digests, and is
limited to 60,000 encoded bytes within the hub's 64 KiB content budget. Only the
three known Markdown files are accepted. Publication acceptance is not fleet
adoption. Publish first to a canary policy/profile, inspect activation evidence,
then allow the remaining profiles to reconcile. Pins support staged adoption.

Search retrieves the newest 100 releases from the configured publisher/channel;
this is bounded catch-up, not full release archive replay. Monotonic sequence and
content-conflict checks reject observed regressions. Operators must keep the
current release in that window and sequences increasing. New profiles have no
prior high-water mark. Release revocation uses a higher sequence with `--revoke
DIGEST`; clients retain observed revocations. For newly bootstrapped clients,
each release must carry the cumulative revocation list.

## Installed versus active

`sync` can install a compatible release automatically (`mode: auto`). With
`mode: manual`, it reports `approval_required` until the operator runs
`sync --approve`. Optional `pin` holds a specific digest; it cannot override
revocation or integrity failure. An unavailable release leaves the previous
verified files intact and reports a local blocker.

`read` verifies and prints the selected content. After actually reading it and
using its setup contract, the agent follows `updates.md` to write session evidence
and run `activate --evidence FILE`. The bootstrap checks the expected behavioral
answers and retrieves the agent's own real setup publication before recording
activation. This is an agent attestation supported by a behavioral artifact,
not proof that every old conversation refreshed its prompt. Repeated activation for an already-observed revision does not publish again; an
explicit operator probe can use `activate --probe --evidence FILE`. Session observations
are timestamped, bounded to the latest 16, and never treated as live leases.

`status` shows available, installed, active-session and failure state. Adoption
reports use `adhd.skills.adoption`; an on-disk outbox retains exact commands and
stable IDs on publication failure. Sync and subsequent activation retry that
outbox. Offline profiles are unknown until observed again, not automatically
current. `rollback --revision DIGEST` verifies a retained version, atomically
selects and pins it, clears session attestations and requires fresh activation.
Do not roll back to a revoked version.

## Runtime integration

| Runtime | Safe update/activation boundary |
| --- | --- |
| Hermes | Existing inbox monitor checks releases at most every five minutes; a changed revision or pending activation wakes a scheduled turn. Inbox and worker prompts reread at turn start. Active builds/gateways are not restarted. |
| Codex | Existing instruction/skill entry loads the bootstrap at session start or an explicit safe turn; reread then attest for that session. |
| Claude Code, Cursor, OpenCode, Pi | Add the same loader to the existing agent-specific instruction entry described in the [setup guides](agents/README.md); reread at a supported safe boundary or start a new session if instructions are cached. |
| OpenShell | Preserve sandbox network/credential policy and use its existing helper/interpreter. The bootstrap needs access only to the already-authorized hub. |

The shared bootstrap is provider-neutral. Hermes and this Codex session are the
live qualification targets; the other adapters are documented instruction-entry
integration and need runtime-specific acceptance before unattended activation is
claimed. Manual clients have no background update while not running. Installing a
release does not modify permissions or create a new worker execution policy.
See [qualification evidence](../../verification/peer-skills/manifest.json).
