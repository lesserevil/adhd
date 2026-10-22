#!/usr/bin/env python3
"""Black-box SDK project isolation, admission, lifecycle and restart acceptance."""
import asyncio
import copy
import json
from uuid import uuid4

from foundation_acceptance import Client
from multi_support import PROJECTS, arguments, execute, poll_until, reject, scoped


RED, BLUE, HIDDEN = "project-red", "project-blue", "project-hidden"


async def checks(f, evidence):
    a, b, c, d, bridge = [await f.agent(name) for name in ("red-a", "red-b", "blue-a", "blue-b", "bridge")]
    for agent, project in ((a, RED), (b, RED), (c, BLUE), (d, BLUE), (bridge, RED), (bridge, BLUE)):
        value = await agent.call(scoped(project, "whoami"))
        assert value["project_id"] == project
    reject(await f.raw("red-a", scoped(BLUE, "whoami")))
    reject(await f.raw("bridge", scoped(HIDDEN, "whoami")))
    reject(await f.raw("bridge", {"op": "search", "query": "Ambiguous project context"}))
    assert set((await bridge.call({"op": "whoami"}))["project_ids"]) == {RED, BLUE}
    assert set((await a.call({"op": "whoami"}))["project_ids"]) == {RED}
    assert not (await a.call({"op": "search", "query": "Singleton omission is unambiguous"}))["publications"]
    visible = await bridge.call({"op": "list_projects"})
    assert {p["id"] for p in visible["projects"]} == {RED, BLUE}
    assert HIDDEN not in json.dumps(visible)
    evidence.record("explicit-context-singleton-omission-and-authorized-project-inventory")

    # Same idempotency and source item values are intentionally reused. Neither
    # deduplication nor response caching may cross the explicit project boundary.
    command = {"op": "publish", "text": "Same immutable fact across projects",
               "source": {"kind": "slack", "id": "shared-channel", "item_id": "same-source-event"}}
    mid = uuid4().hex
    red = await bridge.call({**command, "project_id": RED}, mid)
    blue = await bridge.call({**command, "project_id": BLUE}, mid)
    assert red["publication"]["project_id"] == RED
    assert blue["publication"]["project_id"] == BLUE
    assert red != blue
    assert await bridge.call({**command, "project_id": RED}, mid) == red
    assert await bridge.call({**command, "project_id": BLUE}, mid) == blue
    rp, bp = red["publication"], blue["publication"]
    for agent, project, own in ((a, RED, rp), (c, BLUE, bp)):
        got = (await agent.call(scoped(project, "search", query="Same immutable fact")))["publications"]
        assert got == [own]
        assert (await agent.call(scoped(project, "get", publication_id=own["id"])))["publication"] == own
    reject(await f.raw("red-a", scoped(BLUE, "get", publication_id=bp["id"])))
    reject(await f.raw("bridge", scoped(RED, "get", publication_id=bp["id"])))
    reject(await f.raw("bridge", scoped(BLUE, "get", publication_id=rp["id"])))
    evidence.record("source-id-idempotency-cache-get-and-search-project-isolation")

    # A context link into another admitted project is still outside this
    # operation's scope. It may be rejected or retained only as unresolved.
    response = await f.raw("bridge", scoped(RED, "publish_record", text="Reference to another project",
        context={"links": [{"relation": "related", "publication_id": bp["id"]}]}))
    value = response.json()
    if "error" not in value:
        record = value["result"]["message"]["parts"][0]["data"]["record"]
        view = await bridge.call(scoped(RED, "get_record", publication_id=record["publication"]["id"]))
        assert not any(r["publication"] == bp for r in view["related"])
        assert all(link["target_identity"] is None for link in record["links"])
    evidence.record("cross-project-context-links-never-expand-foreign-evidence")

    red_sub = (await b.call(scoped(RED, "subscribe", mode="raw")))["subscription"]
    blue_sub = (await d.call(scoped(BLUE, "subscribe", mode="raw")))["subscription"]
    bridge_sub = (await bridge.call(scoped(RED, "subscribe", mode="raw")))["subscription"]
    assert not (await bridge.call(scoped(BLUE, "list_subscriptions")))["subscriptions"]
    reject(await f.raw("bridge", scoped(BLUE, "unsubscribe", subscription_id=bridge_sub["id"])))
    reject(await f.raw("red-a", scoped(RED, "unsubscribe", subscription_id=red_sub["id"])))
    event_r = (await a.call(scoped(RED, "publish", text="Independent red stream")))["publication"]
    event_b = (await c.call(scoped(BLUE, "publish", text="Independent blue stream")))["publication"]
    rd = await poll_until(b, RED, {event_r["id"]}, f.args.deadline)
    bd = await poll_until(d, BLUE, {event_b["id"]}, f.args.deadline)
    both = await poll_until(bridge, RED, {event_r["id"]}, f.args.deadline)
    assert all(item["project_id"] == RED for item in rd + both)
    assert all(item["project_id"] == BLUE for item in bd)
    assert not (await bridge.call(scoped(BLUE, "poll")))["deliveries"]
    assert not any(item.get("publication_id") == event_b["id"] for item in rd)
    reject(await f.raw("bridge", scoped(BLUE, "ack", delivery_ids=[both[0]["id"]])))
    reject(await f.raw("red-a", scoped(RED, "ack", delivery_ids=[rd[0]["id"]])))
    assert (await b.call(scoped(RED, "poll")))["deliveries"] == rd
    await b.call(scoped(RED, "ack", delivery_ids=[item["id"] for item in rd]))
    assert not (await b.call(scoped(RED, "poll")))["deliveries"]
    assert (await d.call(scoped(BLUE, "poll")))["deliveries"] == bd
    evidence.record("project-private-subscriptions-recipient-deliveries-and-acknowledgements")

    reject(await f.raw("red-a", scoped(RED, "send", recipient_id="blue-a", text="Must not cross admission")))
    direct = (await bridge.call(scoped(RED, "send", recipient_id="red-b", text="Private red only")))["delivery"]
    assert direct["project_id"] == RED
    assert not (await d.call(scoped(BLUE, "search", query="Private red only")))["publications"]
    assert not (await b.call(scoped(RED, "search", query="Private red only")))["publications"]
    evidence.record("direct-messages-require-shared-project-and-remain-out-of-fact-search")

    admin = f.admin()
    initial_pid = f.process.pid if f.process else None
    projects = copy.deepcopy(PROJECTS)
    projects[0]["name"] = "Renamed without changing identity"
    admin.call({"op": "config_update", "patch": {"projects": projects}}, mutation=True)
    assert (await a.call(scoped(RED, "get", publication_id=rp["id"])))["publication"] == rp
    projects.append({"id": "project-new", "name": "Created live", "description": "", "status": "active", "settings": {}})
    admin.call({"op": "config_update", "patch": {"projects": projects}}, mutation=True)
    assert "project-new" in json.dumps(admin.call({"op": "config_get"}))
    reject(await f.raw("bridge", scoped("project-new", "whoami")))
    projects[0]["status"] = "archived"
    admin.call({"op": "config_update", "patch": {"projects": projects}}, mutation=True)
    reject(await f.raw("red-a", scoped(RED, "publish", text="Must not commit into archive")))
    assert (await c.call(scoped(BLUE, "get", publication_id=bp["id"])))["publication"] == bp
    projects[0]["status"] = "active"
    admin.call({"op": "config_update", "patch": {"projects": projects}}, mutation=True)
    assert (await a.call(scoped(RED, "get", publication_id=rp["id"])))["publication"] == rp
    assert f.process is None or f.process.pid == initial_pid
    evidence.record("hot-create-rename-archive-resume-preserve-stable-identity-and-other-projects")

    password = "Acceptance-password-" + uuid4().hex
    user = admin.call({"op": "save_user", "user": {
        "username": "developer-" + uuid4().hex[:10], "name": "Project Developer",
        "email": "project-developer@example.invalid", "role": "Developer", "password": password,
        "project_ids": [RED]}}, mutation=True)["user"]
    developer = Client(f)
    developer.login(user["username"], password)
    from multi_support import Admin
    dev = Admin(developer, f, revision_source=admin.client)
    token = uuid4().hex + uuid4().hex
    agent_id = "developer-" + uuid4().hex[:10]
    dev.call({"op": "create_agent", "agent_id": agent_id, "token": token,
              "project_ids": [BLUE]}, mutation=True, expected=403)
    dev.call({"op": "create_agent", "agent_id": agent_id, "token": token,
              "project_ids": [RED]}, mutation=True)
    f.tokens[agent_id] = token
    assert (await f.raw(agent_id, scoped(RED, "whoami"))).json().get("error") is None
    reject(await f.raw(agent_id, scoped(BLUE, "whoami")))
    dev.call({"op": "config_update", "patch": {"projects": projects}}, mutation=True, expected=403)
    # No login refresh: admitted agents inherit the current owner admission.
    admin.call({"op": "save_user", "user": {"id": user["id"], "name": "Project Developer",
        "email": "project-developer@example.invalid", "role": "Developer", "project_ids": []}}, mutation=True)
    reject(await f.raw(agent_id, scoped(RED, "publish", text="Revoked owner's agent")))
    evidence.record("developer-cannot-self-admit-agent-grants-bounded-by-live-owner-admission")

    # A token already in use must be fenced by membership changes, including
    # requests from an existing SDK session rather than a fresh login only.
    grants = copy.deepcopy(f.config["agent_projects"] if hasattr(f, "config") else {
        "red-a": [RED], "red-b": [RED], "blue-a": [BLUE], "blue-b": [BLUE], "bridge": [RED, BLUE], "hidden-a": [HIDDEN]})
    grants["bridge"] = [BLUE]
    admin.call({"op": "config_update", "patch": {"agent_projects": grants}}, mutation=True)
    reject(await f.raw("bridge", scoped(RED, "get", publication_id=rp["id"])))
    reject(await f.raw("bridge", scoped(RED, "poll")))
    reject(await f.raw("bridge", scoped(RED, "publish", text="Stale membership must fail")))
    assert (await bridge.call(scoped(BLUE, "get", publication_id=bp["id"])))["publication"] == bp
    evidence.record("membership-revocation-fences-live-token-background-delivery-and-project-access")

    if f.process:
        f.hard_stop()
        await f.start()
        assert (await a.call(scoped(RED, "get", publication_id=rp["id"])))["publication"] == rp
        assert (await c.call(scoped(BLUE, "get", publication_id=bp["id"])))["publication"] == bp
        reject(await f.raw("bridge", scoped(RED, "poll")))
        assert (await b.call(scoped(RED, "list_subscriptions")))["subscriptions"]
        evidence.record("hard-restart-preserves-projects-originals-membership-and-subscriptions")


if __name__ == "__main__":
    args = arguments(__doc__).parse_args()
    asyncio.run(execute(args, "adhd/multi-project-acceptance@1", checks))
