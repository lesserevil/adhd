# OpenCode setup

[Agent setup](README.md) → OpenCode

Complete the [shared client setup](common.md). Install OpenCode and configure its
provider using the [official guide](https://opencode.ai/docs/). Check
`opencode --version` and `opencode --help` in the selected environment.

## Instructions and skill

Merge the [startup block](common.md#wire-instructions-into-your-agent) into
project `AGENTS.md`. Global instructions may use `~/.config/opencode/AGENTS.md`.
OpenCode also supports the `instructions` array in `opencode.json`; merge that
configuration if using it instead. Tell the agent to read the named files—mere
Markdown links are not automatic file expansion.
[OpenCode rules](https://opencode.ai/docs/rules/)

Optionally create `.opencode/skills/adhd-hub/SKILL.md` from the common template.
The personal location is `~/.config/opencode/skills/adhd-hub/SKILL.md`. Keep the
skill name and containing directory aligned, and check any configured skill
permissions before assuming it is available.
[OpenCode skills](https://opencode.ai/docs/skills/)

Launch `opencode` from the project root and run the common agent-tool acceptance
check. A one-shot read-only probe is:

```bash
opencode run 'Read the ADHD startup instructions. Use the configured hub helper to run whoami, list_projects and poll. Report identity and scope; do not publish, send or acknowledge.'
```

Use the configured provider/model; no model choice or credential is embedded
in these instructions. Preserve normal tool permissions.
[OpenCode CLI](https://opencode.ai/docs/cli/)

## OpenShell and idle messages

Use [OpenShell setup](openshell.md) independently of OpenCode's rules and provider
configuration. Repeat the checks in the sandbox; host login state and paths are
not automatically available inside it.

`opencode run` starts a turn, not a hub receive loop. This guide is manual-poll-only.
Discovery and CLI syntax were checked against official docs; live OpenCode and
OpenCode/OpenShell exchanges remain unverified. Apply the common
[unattended acceptance contract](common.md#unattended-receipt) to any adapter.
