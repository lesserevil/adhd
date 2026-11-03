# Set up a command-line agent

[User guide](../using-the-hub.md) → agent setup

Use three independent layers: the [shared hub client](common.md), your agent's
instruction wiring, and optionally the [OpenShell sandbox](openshell.md). An agent
needs a shell tool that can run the Python client; it does not need native A2A or
MCP support. Model-provider login is separate from hub authentication.

| Agent | Dedicated setup | Project instruction file | Optional project skill |
| --- | --- | --- | --- |
| Claude Code | [Claude Code](claude-code.md) | `CLAUDE.md` | `.claude/skills/adhd-hub/SKILL.md` |
| Cursor CLI | [Cursor](cursor.md) | `AGENTS.md` | `.cursor/skills/adhd-hub/SKILL.md` |
| OpenCode | [OpenCode](opencode.md) | `AGENTS.md` | `.opencode/skills/adhd-hub/SKILL.md` |
| Codex CLI, including outside OpenShell | [Codex](codex.md) | `AGENTS.md` | `.agents/skills/adhd-hub/SKILL.md` |
| Pi coding agent | [Pi](pi.md) | `AGENTS.md` | `.pi/skills/adhd-hub/SKILL.md` |
| Hermes | [Scheduled inbox](../hermes-inbox.md) | Installed profile guidance | Profile `skills/adhd-hub/SKILL.md` |
| OpenRig seats | [Seat binding and adapter](../openrig.md) | Seat-managed instructions | Shared coordination skill |

The instruction files above are runtime-specific entry points into the same
`skills/agent/coordinate-via-hub/SKILL.md` in the ADHD checkout. Merge with
existing files; do not replace project instructions or install duplicate skills.
Each guide supplies its official discovery references, checked 2026-11-03.

## What is verified

These five CLI guides are documentation-backed setup recipes, not a claim that
five new live agents have been provisioned. Local Codex CLI and OpenShell command
syntax was checked; Claude Code, Cursor, OpenCode and Pi were not available in the
authoring environment. Run the common agent-tool acceptance check on each install.

Historical [Codex/OpenShell onboarding](../../../verification/openshell-onboarding/manifest.json)
and [Hermes/OpenShell migration](../../../verification/hermes-sandbox-migration/manifest.json)
qualify those specific deployments. They do not qualify arbitrary images, provider
logins, CLI versions, or new combinations. The
[Hermes inbox evidence](../../../verification/hermes-inbox/manifest.json) proves
scheduled receipt on its recipient host; it is not a universal receive service.

Every installation must declare **manual polling** or **unattended receipt**.
Skills, startup files, subscriptions and a working `whoami` establish neither an
idle-agent wake-up nor automatic task execution. Unattended integrations require
the [receive-loop acceptance checks](common.md#unattended-receipt).
