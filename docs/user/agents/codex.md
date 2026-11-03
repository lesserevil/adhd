# Codex CLI setup

[Agent setup](README.md) → Codex CLI

This guide works outside OpenShell. Complete the [shared client setup](common.md)
in Codex's actual execution environment. Install/authenticate Codex through the
[official CLI guide](https://developers.openai.com/codex/cli/), then check
`codex --version` and `codex --help`.

## Instructions and skill

Merge the [startup block](common.md#wire-instructions-into-your-agent) into the
project `AGENTS.md`. User defaults live in `~/.codex/AGENTS.md` unless Codex home
is configured elsewhere. Check for an `AGENTS.override.md` that takes precedence
in the same directory and for more-specific instructions beneath the root.
[Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

Optionally create `.agents/skills/adhd-hub/SKILL.md` from the shared wrapper
template. A user-level install belongs in `~/.agents/skills/adhd-hub/SKILL.md`.
Keep the startup instruction to explicitly read the workflow; skill discovery
alone does not require a hub check on every turn.
[Codex skills](https://learn.chatgpt.com/docs/build-skills)

Launch `codex` from the project root. Ask it to run the common agent-tool checks.
An optional one-shot probe uses the installed CLI's `exec` command:

```bash
codex exec 'Read the ADHD startup instructions. Use the configured hub helper to run whoami, list_projects and poll. Report identity and scope; do not publish, send or acknowledge.'
```

The chosen Codex profile must permit reading the client binding and executing its
helper with HTTPS access. Diagnose filesystem, network and approval failures
separately; do not disable sandboxing globally as an onboarding workaround.
The local CLI's `--help` and `exec --help` were inspected at version 0.164.0;
that is syntax evidence, not a new live standalone-agent qualification.

## Optional OpenShell and idle messages

To run Codex in OpenShell, combine this guide with the
[agent-independent OpenShell layer](openshell.md). Earlier
[Codex/OpenShell evidence](../../../verification/openshell-onboarding/manifest.json)
remains historical evidence for that deployment, not a prerequisite for Codex.

This recipe is manual-poll-only. `codex exec` does not subscribe a running model
to the hub. A supervisor must satisfy the common
[unattended acceptance contract](common.md#unattended-receipt) before automatic
receipt is claimed. Existing Codex sessions need an explicit instruction refresh
or a fresh session when adding this binding.
