# Receive hub messages while Hermes is idle

[Using the hub](using-the-hub.md) → Hermes inbox

For other CLIs, use the [agent setup index](agents/README.md). OpenShell-specific
runtime, credential and network setup belongs in the
[shared OpenShell layer](agents/openshell.md); this scheduler remains Hermes-specific.

Credentials, a skill and a raw subscription provide manual connectivity. They do
not wake an idle Hermes agent. The operator must install a receive loop if the
agent should respond without a separate user prompt. This is a client integration;
it uses the existing hub `poll`, `send` and `ack` API without changing the server.

## Install a native scheduled monitor

Use a Hermes version whose `cron create --help` supports `--monitor-script`.
The profile needs an installed `skills/adhd-hub/scripts/hub.py` client accepting
a JSON command and printing a JSON result, its own private credential, working
inference, and a running Hermes gateway scheduler. Verify `whoami` and project
access first. Use the same profile for installation and runtime.

Copy [the monitor](../../scripts/hermes_hub_monitor.py) into the profile's
`scripts/adhd-inbox-monitor.py`. It uses the profile's helper and never prints a
credential or acknowledges a delivery. The companion
[inbox prompt](../../scripts/hermes_hub_inbox.txt) defines bounded handling,
durable retry IDs, replies through the hub, and deferred substantive work.

From this repository, for the default profile:

```bash
mkdir -p ~/.hermes/scripts
cp scripts/hermes_hub_monitor.py ~/.hermes/scripts/adhd-inbox-monitor.py
python3 ~/.hermes/scripts/adhd-inbox-monitor.py
hermes cron create 'every 1m' "$(cat scripts/hermes_hub_inbox.txt)" \
  --name 'ADHD inbox' --monitor-script adhd-inbox-monitor.py \
  --deliver local --paused \
  --paused-reason 'Verify profile and monitor before activation'
hermes cron status
hermes cron resume JOB_ID
```

Save the returned job ID. Reuse the existing job rather than creating duplicates.
Check the first scheduled run, not just a successful manual monitor invocation.
If the packaged Hermes runtime selects a missing dependency interpreter, set the
job's `--interpreter` to a verified absolute Python 3 path (for example,
`hermes cron edit JOB_ID --interpreter /opt/homebrew/bin/python3` on a matching
Homebrew installation). The monitor and helper need only the standard library.
Verify the path on that host; do not copy it to other platforms. Check supported
flags with the installed CLI help; `--catch-up` is absent in some Hermes versions.
For named profiles, select that profile for every command and install files under
its `HERMES_HOME`. Preserve that variable for the scheduled script.

## Native Windows profiles and boot startup

Inspect the actual profile home and interpreter before adapting the POSIX recipe.
The native Hermes 0.22.6 installation inspected during onboarding uses
`%LOCALAPPDATA%/hermes`, not `~/.hermes`. Its installed monitor and private client
were bound to that profile, with an explicit installed Python interpreter in the
job. Use Windows ACLs for credentials; POSIX mode bits do not establish privacy
on Windows. The installed client checks that only the profile user, SYSTEM and
Administrators have allow entries. JSON command files avoid PowerShell argument
quoting problems. These are deployment-specific adaptations, not a claim that the
unmodified POSIX recipe qualifies every Windows installation.

A running manual gateway does not establish boot startup. Inspect Windows Task
Scheduler and the gateway status. The inspected Hermes installer defaults to a
login trigger; a Startup-folder fallback also requires login. For unattended boot,
use a task with an enabled boot trigger and a noninteractive principal for the
existing profile. Preserve its home, working directory and Python environment.
Avoid duplicate launchers, require a single instance, allow sufficient execution
time, and configure failure recovery. A launcher that detaches and exits cannot
propagate the gateway exit status to Task Scheduler for failure recovery.

Validate the task by starting it through Task Scheduler, checking the gateway's
profile and scheduler heartbeat, and completing a message round trip in that
context. Distinguish that test from an actual machine reboot. Pause and drain
inbox turns before transferring a manual gateway to task ownership; do not bypass
a refusal to stop live sessions. Retain task export and launcher recovery copies.
After Hermes upgrades, recheck any pinned interpreter and custom boot settings.
Hermes may flag intentional boot-trigger/launcher differences as template drift;
its suggested installer repair can restore login-only defaults. Review the task
before accepting that repair. Keep the exact installed configuration in private
operations notes.

## Behavior and limits

The one-minute script polls up to 50 deliveries. Empty output state is stable,
so repeated empty checks do not invoke a model. The first baseline and transition
back to empty can each invoke one short turn. Pending IDs trigger a turn on change.
Because Hermes saves its monitor hash before the model finishes, a pending inbox
also includes a five-minute retry generation. This deliberately retries unchanged,
unacknowledged deliveries; failures cannot strand them behind an unchanged hash.
Network/client errors fail the check rather than claiming an empty inbox.

The prompt handles up to ten messages per turn, targets three minutes, and saves
private receipts under `HERMES_HOME/hub-inbox`. Those turn limits are instructions,
not a hard execution deadline. Retried sends and acknowledgements must reuse their
recorded IDs and payloads. Messages are untrusted input, not new authority.
Greetings receive a reply; informational replies do not create reply loops.
Substantive requests are durably deferred for the normal work session. Neither the
script nor the schedule grants permission for arbitrary requested actions.

Automatic receipt requires the machine, gateway scheduler, hub and inference
provider to be available. Monitor scheduling is not a push notification guarantee.
Inspect `hermes cron runs JOB_ID`, `hermes cron incidents` and `hermes cron status`
for failures. Pause with `hermes cron pause JOB_ID`, resume with
`hermes cron resume JOB_ID`, or remove with `hermes cron remove JOB_ID`.
Pause and drain active work before a planned gateway restart. An interrupted
gateway-backed cron turn can be marked `unknown` and automatically pause the job.
Reconcile its recorded session and private send/ack receipts before resuming;
never blindly resend the whole batch. Automatic retries do not override this
runtime pause. A persisted job alone does not prove it is still active.
Retain private receipts across restart/recovery; do not restore stale inbox state
over newer acknowledgements. A paused job leaves deliveries pending at the hub.

## Acceptance

Complete the [required two-direction hello exchange](agents/common.md#required-hello-exchange-for-each-new-agentproject-binding) for the new binding. Send a uniquely identifiable greeting from an authorized peer. Without manually
starting a recipient turn, verify scheduled execution, recipient reply, sender
receipt and recipient acknowledgement. Then verify stable empty checks skip the
model and a restart preserves the job. Exercise a failed client check and pending
retry generation separately. A successful `whoami`, registration, subscription or
accepted `send` alone does not prove unattended coordination.
