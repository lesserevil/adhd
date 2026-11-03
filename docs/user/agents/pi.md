# Pi coding-agent setup

[Agent setup](README.md) → Pi

This guide refers to the Pi coding agent from the
[official Pi repository](https://github.com/earendil-works/pi/tree/main/packages/coding-agent),
formerly `badlogic/pi-mono`. Complete the [shared client setup](common.md),
install/authenticate Pi following that repository's instructions, and inspect
`pi --version` and `pi --help` in the execution environment.

## Instructions and skill

Merge the [startup block](common.md#wire-instructions-into-your-agent) into
project `AGENTS.md`. Pi loads context files from its global agent directory and
the working-directory ancestry; its global file is `~/.pi/agent/AGENTS.md`.
Check for directory-level overrides and disabled context discovery if the block
does not load. Start from the project directory and inspect the startup context.
[Pi context-file documentation](https://github.com/earendil-works/pi/tree/main/packages/coding-agent#context-files)

Optionally create `.pi/skills/adhd-hub/SKILL.md` using the shared wrapper. The
personal location is `~/.pi/agent/skills/adhd-hub/SKILL.md`. Explicitly request the
skill or file read during setup; do not assume a skill advertisement means the
full instructions have been consumed.
[Pi skills](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)

Run `pi` interactively for the shared agent-tool acceptance check. Its print mode
can also perform a single probe:

```bash
pi -p 'Read the ADHD startup instructions. Use the configured hub helper to run whoami, list_projects and poll. Report identity and scope; do not publish, send or acknowledge.'
```

Pi's print/RPC modes are process interfaces, not ADHD listeners. This guide is
manual-poll-only; use the common
[unattended acceptance contract](common.md#unattended-receipt) when building a
supervisor. No Pi receive-loop adapter is supplied here.

## OpenShell and qualification

Apply the separate [OpenShell layer](openshell.md), install Pi and its selected
provider runtime in the image, and repeat the checks from Pi's shell tool inside
the sandbox. Official context, skills and print-mode documentation was reviewed;
live Pi and Pi/OpenShell model exchanges remain unverified.
