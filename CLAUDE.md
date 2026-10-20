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
