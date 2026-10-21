#!/usr/bin/env python3
"""Retired agent identities cannot transfer retained private state to Developers.

Only public management/A2A interfaces create and inspect state. Admin recovery is
explicitly allowed. This suite owns its native process or verified image and
uses the same private data through an actual hard restart.
"""
import asyncio
import hashlib
import secrets
import time
from uuid import uuid4
from pathlib import Path

from archive_support import ArchiveFixture
from foundation_acceptance import Client
from multi_support import Admin, Evidence, Fixture, arguments, scoped

RED, BLUE = "project-red", "project-blue"


async def checks(f, evidence):
    admin = f.admin()
    users = []
    for name, projects in (("former-owner", [RED, BLUE]), ("replacement-owner", [RED])):
        password = secrets.token_urlsafe(32)
        user = admin.call({"op": "save_user", "user": {"username": name, "name": name,
            "email": name + "@example.invalid", "password": password,
            "role": "Developer", "project_ids": projects}}, mutation=True)["user"]
        users.append((user, password))
    login = Client(f)
    login.login("replacement-owner", users[1][1])
    developer = Admin(login, f, admin.client)
    sender_red, sender_blue = await f.agent("red-a"), await f.agent("blue-a")
    saved = []
    for kind, project in (("queued", RED), ("acked", RED), ("subscription", RED),
                          ("query", RED), ("receipt", RED), ("cross-project", BLUE),
                          ("legacy-unowned", BLUE)):
        name, token = "retired-" + kind, secrets.token_urlsafe(32)
        if kind == "legacy-unowned":
            admin.call({"op": "config_update", "patch": {"agents": {name: token},
                "agent_projects": {name: [project]}}}, mutation=True)
        else:
            admin.call({"op": "create_agent", "agent_id": name, "token": token,
                "owner_user_id": users[0][0]["id"], "project_ids": [project]}, mutation=True)
        f.tokens[name] = token
        agent = await f.agent(name)
        item = {"agent_id": name, "kind": kind, "project": project}
        if kind in ("queued", "acked", "cross-project", "legacy-unowned"):
            sender = sender_red if project == RED else sender_blue
            delivery = (await sender.call(scoped(project, "send", recipient_id=name,
                text="PRIVATE former owner " + kind)))["delivery"]
            assert (await agent.call(scoped(project, "poll")))["deliveries"] == [delivery]
            item["delivery"] = delivery
            if kind == "acked":
                await agent.call(scoped(project, "ack", delivery_ids=[delivery["id"]]))
                assert (await agent.call(scoped(project, "poll")))["deliveries"] == []
        elif kind == "subscription":
            item["subscription"] = (await agent.call(scoped(project, "subscribe", mode="raw")))["subscription"]
        elif kind == "query":
            query = (await agent.call(scoped(project, "query_history", question="What was explicitly reported?")))["query"]
            until = time.monotonic() + 15
            while time.monotonic() < until:
                query = (await agent.call(scoped(project, "get_history_query", query_id=query["id"])))["query"]
                if query["status"] != "pending":
                    break
                await asyncio.sleep(.05)
            assert query["status"] != "pending"
            item["query"] = query
        else:
            # Remove the resource publicly while retaining its original mutation
            # receipt. A retry must return the old ID without recreating it.
            item["receipt_command"] = scoped(project, "subscribe", mode="raw")
            item["receipt_mid"] = "former-owner-frozen-receipt"
            item["receipt"] = await agent.call(item["receipt_command"], item["receipt_mid"])
            await agent.call(scoped(project, "unsubscribe", subscription_id=item["receipt"]["subscription"]["id"]))
            assert (await agent.call(scoped(project, "list_subscriptions")))["subscriptions"] == []
        saved.append(item)
    evidence.record("independent-retained-private-ack-subscription-query-receipt-and-foreign-project-identities-created",
                    retained_kinds=[x["kind"] for x in saved])

    patch = {key: {x["agent_id"]: None for x in saved} for key in ("agents", "agent_owners", "agent_projects")}
    admin.call({"op": "config_update", "patch": patch}, mutation=True)
    for item in saved:
        assert (await f.raw(item["agent_id"], scoped(item["project"], "poll"))).status_code == 401
    evidence.record("all-retired-tokens-denied-after-atomic-credential-owner-admission-removal")

    observations = []
    for item in saved:
        name, new_token = item["agent_id"], secrets.token_urlsafe(32)
        before = admin.call({"op": "config_get"})
        config = before["config"]
        revision = config.get("config_revision", before.get("config_revision", before.get("revision")))
        command = {"op": "create_agent", "agent_id": name, "token": new_token,
            "project_ids": [RED], "expected_revision": revision, "confirm": True, "message_id": uuid4().hex}
        status, response, _ = login.request("/admin/api", command)
        after = admin.call({"op": "config_get"})
        row = {"kind": item["kind"], "http_status": status,
               "denied": status == 409, "configuration_unchanged": before == after}
        if status == 200:
            # Reproduce the actual confidentiality breach without copying text
            # or credentials into the durable report.
            f.tokens[name] = new_token
            replacement = await f.agent(name)
            if item["kind"] == "queued":
                rows = (await replacement.call(scoped(RED, "poll")))["deliveries"]
                row["replacement_received_former_private_delivery"] = any(d["id"] == item["delivery"]["id"] for d in rows)
            admin.call({"op": "config_update", "patch": {key: {name: None} for key in patch}}, mutation=True)
        else:
            f.tokens[name] = new_token
            row["replacement_token_denied"] = (await f.raw(name, scoped(RED, "poll"))).status_code == 401
            row["error_code"] = response.get("error", {}).get("code")
        observations.append(row)
    evidence.value["developer_reuse_attempts"] = observations
    evidence.write()

    # A fresh name is still available to a Developer on their own behalf.
    fresh, fresh_token = "legitimate-fresh-agent", secrets.token_urlsafe(32)
    created = developer.call({"op": "create_agent", "agent_id": fresh, "token": fresh_token,
                              "project_ids": [RED]}, mutation=True)
    assert created["owner_user_id"] == users[1][0]["id"]
    f.tokens[fresh] = fresh_token
    assert (await (await f.agent(fresh)).call(scoped(RED, "whoami")))["agent_id"] == fresh
    evidence.record("developer-can-still-create-fresh-owned-identity")

    for item in saved:
        token = secrets.token_urlsafe(32)
        admin.call({"op": "create_agent", "agent_id": item["agent_id"], "token": token,
            "owner_user_id": users[0][0]["id"], "project_ids": [item["project"]]}, mutation=True)
        f.tokens[item["agent_id"]] = token

    async def verify_recovery():
        for item in saved:
            agent, project = await f.agent(item["agent_id"]), item["project"]
            kind = item["kind"]
            if kind in ("queued", "cross-project", "legacy-unowned"):
                assert (await agent.call(scoped(project, "poll")))["deliveries"] == [item["delivery"]]
            elif kind == "acked":
                assert (await agent.call(scoped(project, "poll")))["deliveries"] == []
            elif kind == "subscription":
                assert (await agent.call(scoped(project, "list_subscriptions")))["subscriptions"] == [item["subscription"]]
            elif kind == "query":
                assert (await agent.call(scoped(project, "get_history_query", query_id=item["query"]["id"])))["query"] == item["query"]
            else:
                assert await agent.call(item["receipt_command"], item["receipt_mid"]) == item["receipt"]
                assert (await agent.call(scoped(project, "list_subscriptions")))["subscriptions"] == []
    await verify_recovery()
    evidence.record("explicit-admin-recovery-retains-all-identities-private-state-acknowledgements-and-owned-resources")
    f.hard_stop()
    await f.start()
    await verify_recovery()
    evidence.record("hard-restart-preserves-explicit-admin-recovery-without-acknowledged-redelivery")
    assert all(row["denied"] and row["configuration_unchanged"] and row.get("replacement_token_denied")
               and row.get("error_code") == "IDEMPOTENCY_CONFLICT"
               for row in observations), "Developer creation reused a retained identity or mutated state on rejection"
    evidence.record("developer-reuse-denied-for-every-retained-state-kind-across-all-project-snapshots")


async def main(args):
    assert not args.rest_url, "Hard-restart ownership is required"
    evidence = Evidence(args.report, "multi-agent-retirement")
    evidence.value["limitations"] = ["Controlled typed model fixture is not semantic model quality evidence."]
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.hub:
        evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest()
    fixture = Fixture(args)
    fixture.model = ArchiveFixture()
    fixture.config["matcher"] = {"url": fixture.model.url, "model": "Nemotron-Deciffusion-8B-v2.1", "timeout_ms": 1000, "retry_ms": 100}
    try:
        await fixture.start()
        fixture.bind_evidence(evidence)
        await checks(fixture, evidence)
    except BaseException as error:
        evidence.finish(error)
        raise
    else:
        evidence.finish()
    finally:
        await fixture.close()
        fixture.bind_evidence(evidence)
        evidence.write()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
