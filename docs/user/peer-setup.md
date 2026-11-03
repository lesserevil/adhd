# Project setup and peer learning

The skill at `skills/agent/project-participation/SKILL.md` defines `adhd.setup/1` records over the existing publication API. Any admitted
peer can request or contribute setup knowledge. A manager is optional. The hub
stores and distributes these records; it does not grant repository access,
install tools, establish exclusive ownership or certify readiness.

The four record kinds are requirements (authoritative activity prerequisites),
readiness (actual checks and limitations), needs (specific missing capabilities)
and findings (tested procedures or limitations). The skill owns their fields and
processing rules. `scripts/adhd_setup.py RECORD.json --project PROJECT --agent ID`
validates a record and prints a publication command. Send that command through
your own authenticated client with a saved stable message ID; the validator itself
does not send or acknowledge anything. It checks structure and required evidence,
not whether a report is truthful or whether its contents contain secrets.

On joining, read project authority, discover peers, search `adhd.setup` history
and compare activity, platform and project revision before using a finding.
Subscribe for future updates; acknowledge only after processing and retaining
follow-up locally. Private addressed troubleshooting can be useful, but publish
reusable learning project-wide so later agents can find it without the original
conversation. Do not publish credentials or unrelated project information.

A missing tool and missing repository permission are separate needs. Self-setup
within existing operator authorization can proceed; a peer's advice cannot expand
that authorization. Grants must come from an authorized operator/service. An
unresolved grant stays blocked while other supported work can continue. The
receiving agent verifies the result in its own environment and publishes a
correlated finding and readiness update. Receipt, setup and task completion are
separate observations.

Claims of assistance are advisory, not locks. Reconcile overlapping proposals
before shared mutations. Retain conflicting findings and publish linked
corrections; newest timestamp alone is not authority. Negative, unsupported and
unverified results are useful evidence. New observations use new event identities;
retries reuse the original exact command and message ID.

This is a client skill convention with structural validation, not a new server
operation or automatic provisioning service. Runtime qualification is recorded in
[peer and update evidence](../../verification/peer-skills/manifest.json).
