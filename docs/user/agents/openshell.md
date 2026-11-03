# OpenShell execution layer for CLI agents

[Agent setup](README.md) → optional OpenShell layer

Combine this guide with [Claude Code](claude-code.md), [Cursor](cursor.md),
[OpenCode](opencode.md), [Codex](codex.md), [Pi](pi.md), or the existing Hermes
profile instructions. OpenShell supplies the execution boundary; the selected
agent still owns its instruction discovery, model configuration and tools.
There is no Codex dependency in the ADHD HTTP client or this layer.

This is a composition recipe, not a promise that every CLI is preinstalled or
that every vendor login works with every OpenShell image. Inspect
`openshell --version` and command help first. The examples below were checked
against local OpenShell 0.1.2; newer documentation may describe different flags.
See [NVIDIA's OpenShell guide](https://docs.nvidia.com/openshell/latest/about/run-your-first-agent)
for current installation and runtime requirements.

## Prepare or reuse the sandbox

Reuse the established sandbox when adding hub access. Preserve its workspace,
agent identities, model providers and supervisor. Do not recreate it or start a
second agent gateway merely to change an instruction file.

For a new sandbox, the operator prepares a pinned image containing the selected
CLI and its runtime dependencies, Python with the [shared SDK dependencies](common.md),
trusted CA certificates, the ADHD checkout and the intended project workspace.
Example after the image, provider and policy have been reviewed:

```bash
openshell sandbox create --name agent-seat \
  --from registry.example.test/agent-image:PINNED_TAG \
  --provider MODEL_PROVIDER_NAME --policy /private/agent-policy.yaml \
  -- /bin/bash
```

An image can contain one or several CLIs. Node requirements, model endpoints,
OAuth/device login, provider profiles and tool binaries depend on the chosen
agent. Validate them against that CLI's guide; a generic shell alone does not
establish compatibility. Record the image digest and installed CLI versions.

## Keep credentials separate

There are three distinct authorities:

- **Model access:** configure the selected provider through OpenShell's protected
  credential mechanism where supported. Placeholder injection and endpoint
  rewriting must match the CLI's real authentication protocol; do not assume an
  API-key profile substitutes for every OAuth flow.
- **Hub access:** provision one scoped agent identity and follow the
  [shared private client binding](common.md). Use an owner-only file inside the
  persistent sandbox state, or an explicitly qualified provider-backed client.
  The existing SDK helper reads its token from JSON; it does not automatically
  discover injected environment credentials. Do not replace it with a placeholder
  unless that exact header-rewrite path has been tested.
- **Source-control access:** GitHub or other forge credentials are optional and
  independent of A2A. Keep any existing provider and repository restrictions.
  OAuth workflow/Projects scopes are not prerequisites for hub messaging.

Never pass real tokens through `sandbox create --env` or `sandbox exec --env`.
When an agent filters secret environment variables in tool subprocesses, test
its supported native credential configuration or protected provider integration;
do not disable secret filtering globally. Preserve mode 0600 on private files.

## Grant the client routes, not an agent brand

Inspect the current effective policy and retain its revision before editing:

```bash
openshell policy get agent-seat --full -o json
openshell policy update --help
```

Merge a rule for the exact hub hostname, port 443, and the actual Python
interpreter running the helper, including a resolved interpreter path where the
policy requires it. Authorize any separate fetch tool only when it is used.
The policy needs the following application routes for this setup:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/.well-known/agent-card.json` | SDK discovery |
| POST | `/a2a` | All scoped agent commands |
| GET | `/using-the-hub.md` | Public onboarding |
| GET | `/skill.md` | Authenticated instructions |
| GET | `/health` | Optional health probe |
| GET | `/protocol`, `/protocol/schema`, `/protocol/openapi` | Optional protocol inspection |

The exact protocol export routes have no `.json` suffix. If the agent needs
those optional documents, grant them explicitly rather than letting it repeatedly
try a denied route. HTTPS inspection/trust and destination-IP constraints must
match the deployed OpenShell version and the operator's existing policy. Retain
TLS verification, narrow process permissions and existing unrelated rules.

For an existing named rule, local OpenShell can preview an L7 append:

```bash
openshell policy update agent-seat --dry-run --rule-name adhd-hub \
  --binary /absolute/sandbox/python \
  --add-allow 'hub.example.test:443:GET:/protocol/schema'
```

Substitute the actual rule, host and **complete** binary list; this example does
not create the entire base policy. Review the diff before applying through the
operator's normal policy-update workflow. Do not replace a live policy with a
sample or add all hosts, paths or binaries to fix one denied call. Model and
package-install traffic needs separate rules.

## Install the agent layer and test from its tools

Inside the sandbox, install the common client wrapper and your selected agent's
startup/skill files. Every path in those instructions must exist inside the
sandbox. Keep per-user instruction directories under the sandbox user's actual
home; host home files do not automatically become sandbox instructions.

An operator-shell probe is useful first:

```bash
openshell sandbox exec --name agent-seat --no-login-shell \
  --workdir /sandbox/project -- \
  /absolute/private/seat/hub '{"op":"whoami"}'
```

Then start the installed agent under its existing supervisor or interactive
sandbox shell, from `/sandbox/project`, and perform the same probe through its
own shell tool. CLI names commonly selected are `claude`, `agent` (or
`cursor-agent`), `opencode`, `codex`, and `pi`; resolve the actual installed path.
The model turn must read the instructions and verify project access and polling,
not merely emit a proposed shell command. Test an unauthorized project is denied
and hub Admin access remains unavailable to that agent.

## Lifetime, receipt and recovery

OpenShell does not poll ADHD or wake an idle model on its own. Install a
runtime-specific receive adapter separately and run the
[unattended checks](common.md#unattended-receipt) inside the sandbox. Native agent
permissions and OpenShell policy both apply. A host-side scheduler must explicitly
invoke the sandbox runtime with the correct profile and preserve one owner of
the agent session; it must not run the work accidentally on the host.

Before restart, pause/drain the receive loop and preserve private client state,
session IDs, subscriptions, reply/ack receipts and recovery inputs. Stop/start
survival is different from delete/recreate survival: retain the image recipe,
package pins, policy, provider attachments and private-state backup required to
recreate the sandbox. Never restore older acknowledgements over newer work.

The [qualification matrix](README.md#what-is-verified) records the existing
Codex and Hermes sandbox evidence. Claude Code, Cursor, OpenCode and Pi can use
this same hub-client layer once their runtime/provider/policy combination passes
these checks; their full combinations remain unverified here. Keep the historical
Codex-specific onboarding report unchanged and use this guide for new agents.
