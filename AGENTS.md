# Literate AI agent entry point

Read and follow `SKILL.md` before changing this framework or any project that uses its
canonical taxonomy. Treat that file as the provider-neutral onboarding authority.

For this project, read and follow [documentation consistency](docs/user/documentation-policy.md)
before changing behavior, configuration, interfaces, deployment, or documentation.
Documentation review is required before marking work complete.

When `literate.hub.local.json` exists, follow the
[hub coordination skill](skills/agent/coordinate-via-hub/SKILL.md) at session startup
and during work. Use the identity in that private client file with
`scripts/hub_agent.py`; verify it, reuse relevant subscriptions, search for prior
context, and poll before dependent decisions. Publish meaningful work updates and
acknowledge deliveries after processing them. Report connection failures; never
expose credentials or claim background synchronization.

After an agent is enrolled in ADHD, ADHD must not use SSH, SCP, or another remote
file-copy mechanism to deliver or repair that agent's files. Setup requests and
update notices travel through ADHD; the receiving agent retrieves authorized
artifacts and installs them within its own permissions. Enrollment must establish
that path. A missing post-enrollment delivery or bootstrap-upgrade capability is
an implementation gap, not permission to fall back to remote file copying.
