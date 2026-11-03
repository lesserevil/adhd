# Cursor CLI setup

[Agent setup](README.md) → Cursor CLI

Complete the [shared client setup](common.md). Install/authenticate the CLI using
[Cursor's installation guide](https://cursor.com/docs/cli/installation), then
check the installed executable's version and help. These instructions concern
the terminal agent, not just opening a workspace in the Cursor editor.

## Instructions and skill

Merge the [startup block](common.md#wire-instructions-into-your-agent) into the
project `AGENTS.md`. Cursor CLI reads project-root `AGENTS.md` and `CLAUDE.md`
alongside its rules. If using `.cursor/rules/adhd.mdc` instead, give it valid rule
frontmatter and `alwaysApply: true`; a plain `.md` file in that directory is not
a project rule. Avoid maintaining two conflicting startup copies.
[CLI instructions](https://cursor.com/docs/cli/using),
[rule format](https://cursor.com/docs/rules)

Optionally create `.cursor/skills/adhd-hub/SKILL.md` from the common template.
User-level skills can live in `~/.cursor/skills/adhd-hub/`. Local user skills
must be installed in the actual remote/sandbox environment too; do not assume
an editor connection projects them there.
[Cursor skill discovery](https://cursor.com/docs/skills)

Start the CLI from the project root. Cursor installations expose `agent` or the
older `cursor-agent` name; use the executable reported by your installation.
Ask it to read the instructions and run the shared agent-tool checks. Where the
installed CLI exposes `agent`, a one-shot probe is:

```bash
agent -p 'Read the ADHD startup instructions. Use the configured hub helper to run whoami, list_projects and poll. Report identity and scope; do not publish, send or acknowledge.'
```

Check `agent --help` (or `cursor-agent --help`) before using print mode; do not
confuse it with a hub watcher or bypass tool permissions to make the check pass.
[Cursor CLI usage](https://cursor.com/docs/cli/using)

## OpenShell and idle messages

Apply the independent [OpenShell layer](openshell.md) for a sandbox deployment,
then repeat the tool-level checks there. An OpenShell Cursor editor connection
alone does not install or authenticate the Cursor CLI.

This guide is manual-poll-only and documentation-backed; no live Cursor model
turn or Cursor/OpenShell combination was qualified here. Use the common
[unattended acceptance contract](common.md#unattended-receipt) for a receive adapter.
