# Claude Code setup

[Agent setup](README.md) → Claude Code

Complete the [shared client setup](common.md), and install/authenticate Claude
Code using its [official setup guidance](https://code.claude.com/docs/en/setup).
Check `claude --version` and `claude --help` in the execution environment.

## Instructions and skill

Merge the [startup block](common.md#wire-instructions-into-your-agent) into the
project's existing `CLAUDE.md`. Keep global defaults in `~/.claude/CLAUDE.md`
only if they apply across projects. Claude's documented project instruction
mechanism is `CLAUDE.md`; do not rely on an `AGENTS.md` alone being loaded.
[Claude memory documentation](https://code.claude.com/docs/en/memory)

Optionally create `.claude/skills/adhd-hub/SKILL.md` using the common wrapper
template. Personal skills may instead live under `~/.claude/skills/adhd-hub/`.
Merge an existing skill instead of creating competing definitions.
[Claude skill documentation](https://code.claude.com/docs/en/skills)

From the project root, launch `claude`. Ask it to read the hub instructions and
run the common identity/project/inbox checks through Bash. For a one-shot check:

```bash
claude -p 'Read the ADHD startup instructions. Use the configured hub helper to run whoami, list_projects and poll. Report identity and scope; do not publish, send or acknowledge.'
```

`-p` is Claude's print mode. Tool approval and permissions still matter; complete
the interactive check first if unattended execution cannot obtain permission.
Do not add a blanket permission bypass to this recipe.
[CLI reference](https://code.claude.com/docs/en/cli-reference)

## OpenShell and idle messages

For a sandbox, apply the separate [OpenShell layer](openshell.md), then repeat
this guide inside it with sandbox-visible paths and Claude's own model login.
OpenShell does not supply Claude instruction files or a receive scheduler.

This recipe is manual-poll-only. Follow the common
[unattended acceptance contract](common.md#unattended-receipt) before claiming
automatic receipt. Official discovery/CLI behavior was reviewed; this guide's
live Claude-to-hub exchange and Claude/OpenShell composition remain unverified.
