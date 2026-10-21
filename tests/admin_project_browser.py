#!/usr/bin/env python3
"""Rendered subscription edits, model policy, project catalogs and OIDC admission."""
import asyncio
import hashlib
import json
from pathlib import Path
import re

from playwright.async_api import async_playwright, expect

from eventing_browser import mutation, until
from foundation_acceptance import Provider
from multi_browser import capture, instrument, login, navigate
from multi_support import Evidence, Fixture, arguments, poll_until, scoped


RED, BLUE = "project-red", "project-blue"


def row(page, sid):
    label = page.get_by_text(re.compile(r"^" + re.escape(sid) + r" · (raw|filtered) · (Paused|Active)$"))
    return page.locator("section.row").filter(has=label)


async def edit(page, sid):
    target = row(page, sid)
    await target.get_by_role("button", name="Edit subscription", exact=True).click()
    return target.locator("form")


async def update(page, form):
    result, command, _ = await mutation(page, form.get_by_role("button", name="Confirm subscription update", exact=True), "update_subscription")
    assert "agent_id" not in command and command["confirm"] is True
    await expect(page.get_by_role("button", name="Confirm subscription update", exact=True)).to_have_count(0)
    return result["subscription"]


async def publish(agent, text, **fields):
    return (await agent.call(scoped(RED, "publish", text=text, **fields)))["publication"]


async def acknowledge(agent, ids):
    await agent.call(scoped(RED, "ack", delivery_ids=ids))


async def subscription_flow(page, f, evidence, name):
    a, b, bridge = [await f.agent(agent) for agent in ("red-a", "red-b", "bridge")]
    await navigate(page, "Subscriptions")
    form = page.locator("#content > form")
    await form.get_by_label("Owner agent", exact=True).select_option("red-b")
    for label, value in (("Information types (one per line)", "status"), ("Source kinds (one per line)", "github"),
                         ("Source IDs (one per line)", "channel-x"), ("Publisher agent IDs (one per line)", "red-a")):
        await form.get_by_label(label, exact=True).fill(value)
    result, _, _ = await mutation(page, form.get_by_role("button", name="Create subscription", exact=True), "create_subscription")
    sid = result["subscription"]["id"]
    await expect(row(page, sid)).to_be_visible()
    fields = {"information_type": "status", "source": {"kind": "github", "id": "channel-x"}}
    positive = await publish(a, "Selected event " + name, **fields)
    rejected = []
    for fields_bad in ({**fields, "information_type": "message"},
                       {**fields, "source": {"kind": "jira", "id": "channel-x"}},
                       {**fields, "source": {"kind": "github", "id": "channel-y"}}):
        rejected.append(await publish(a, "Excluded selector event " + name, **fields_bad))
    rejected.append(await publish(bridge, "Excluded publisher " + name, **fields))
    rows = await poll_until(b, RED, {positive["id"]}, f.args.deadline)
    await until(lambda: f.admin().call({"op": "eventing_status", "project_id": RED})["pending_events"] == 0, "Selectors did not settle")
    assert {d["publication_id"] for d in (await b.call(scoped(RED, "poll")))["deliveries"]} == {positive["id"]}
    await acknowledge(b, [d["id"] for d in rows])
    # The selected subscription is genuinely outside the bounded first page.
    dummy = [(await a.call(scoped(RED, "subscribe", mode="raw")))["subscription"] for _ in range(100)]
    await page.get_by_role("button", name="Refresh", exact=True).click()
    await expect(page.get_by_role("button", name="Next subscriptions page", exact=True)).to_be_visible()
    await expect(row(page, sid)).to_have_count(0)
    await page.get_by_role("button", name="Next subscriptions page", exact=True).click()
    await expect(row(page, sid)).to_be_visible()
    cancelled = await edit(page, sid)
    await cancelled.get_by_label("Information types (one per line)", exact=True).fill("cancelled-unapplied-change")
    await cancelled.get_by_role("button", name="Cancel subscription edit", exact=True).click()
    assert next(s for s in (await b.call(scoped(RED, "list_subscriptions")))["subscriptions"] if s["id"] == sid)["revision"] == 1
    form = await edit(page, sid)
    await form.get_by_label("Pause subscription", exact=True).check()
    paused = await update(page, form)
    assert paused["paused"] and paused["revision"] == 2
    for item in dummy:
        await a.call(scoped(RED, "unsubscribe", subscription_id=item["id"]))
    await page.get_by_role("button", name="Previous subscriptions page", exact=True).click()
    await expect(row(page, sid)).to_be_visible()
    excluded_pause = await publish(a, "Published while paused " + name, **fields)
    await until(lambda: f.admin().call({"op": "eventing_status", "project_id": RED})["pending_events"] == 0, "Paused publication did not settle")
    assert not (await b.call(scoped(RED, "poll")))["deliveries"]
    form = await edit(page, sid)
    await form.get_by_label("Pause subscription", exact=True).uncheck()
    resumed = await update(page, form)
    assert not resumed["paused"] and resumed["revision"] == 3
    future = await publish(a, "Future after resume " + name, **fields)
    rows = await poll_until(b, RED, {future["id"]}, f.args.deadline)
    assert {d["publication_id"] for d in rows} == {future["id"]}
    await acknowledge(b, [d["id"] for d in rows])
    assert not (await b.call(scoped(RED, "poll")))["deliveries"]
    evidence.record(name + "-rendered-selector-fanout-beyond-100-edit-cancel-pause-resume-no-history-or-ack-resurrection")

    # Freeze a failed old-criterion job, edit+pause through Admin, then prove the
    # accepted backlog retains its prior revision while future work is paused.
    form = await edit(page, sid)
    await form.get_by_label("Subscription mode", exact=True).select_option("filtered")
    old_filter = "Frozen old criterion " + name
    await form.get_by_label("Plain-text filter", exact=True).fill(old_filter)
    filtered = await update(page, form)
    f.model.mode = "error"
    attempted = f.model.calls
    pending = await publish(a, "Old pending filter " + name, **fields)
    await until(lambda: f.model.calls > attempted, "Filtered job never attempted")
    form = await edit(page, sid)
    await form.get_by_label("Plain-text filter", exact=True).fill("New filter criterion " + name)
    await form.get_by_label("Pause subscription", exact=True).check()
    await update(page, form)
    await publish(a, "Filtered publication while paused " + name, **fields)
    f.model.mode = "match"
    rows = await poll_until(b, RED, {pending["id"]}, f.args.deadline)
    assert {d["publication_id"] for d in rows} == {pending["id"]}
    assert any(m["subscription_id"] == sid and m["subscription_revision"] == filtered["revision"] for m in rows[0]["matches"])
    assert any(old_filter in json.dumps(request) for request in f.model.requests)
    await acknowledge(b, [d["id"] for d in rows])
    form = await edit(page, sid)
    await form.get_by_label("Pause subscription", exact=True).uncheck()
    current = await update(page, form)
    future = await publish(a, "New pending filter " + name, **fields)
    rows = await poll_until(b, RED, {future["id"]}, f.args.deadline)
    assert {d["publication_id"] for d in rows} == {future["id"]}
    assert any(m["subscription_revision"] == current["revision"] for m in rows[0]["matches"])
    await acknowledge(b, [d["id"] for d in rows])
    await capture(page, f.root, name + "-edited-subscription")
    evidence.record(name + "-filtered-edit-and-pause-preserve-accepted-frozen-backlog-revision-and-future-criterion")
    return a, b, bridge, sid, positive, fields


async def model_transition(page, f, evidence, name, a, b, bridge, fields):
    f.model.mode = "error"
    initial = f.model.calls
    pending = await publish(a, "Before model disable " + name, **fields)
    await until(lambda: f.model.calls > initial, "Pending filter never attempted before disable")
    await navigate(page, "Settings")
    await page.get_by_role("button", name="Disable decision model", exact=True).click()
    await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
    await expect(page.get_by_role("button", name="Configure optional decision model", exact=True)).to_be_visible()
    assert f.admin().call({"op": "config_get"})["config"]["matcher"] is None
    f.model.mode = "match"
    await asyncio.sleep(.25)
    baseline = f.model.calls
    raw_sub = (await bridge.call(scoped(RED, "subscribe", mode="raw")))["subscription"]
    raw = await publish(a, "Raw progress while model disabled " + name, information_type="note")
    raw_rows = await poll_until(bridge, RED, {raw["id"]}, f.args.deadline)
    await acknowledge(bridge, [d["id"] for d in raw_rows])
    assert f.model.calls == baseline and not (await b.call(scoped(RED, "poll")))["deliveries"]
    await page.get_by_role("button", name="Configure optional decision model", exact=True).click()
    matcher = page.locator('fieldset:has(> legend:text-is("matcher"))')
    await matcher.get_by_label("url", exact=True).fill(f.model.url)
    await matcher.get_by_label("model", exact=True).fill(f.config["matcher"]["model"])
    await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
    rows = await poll_until(b, RED, {pending["id"]}, f.args.deadline)
    assert {d["publication_id"] for d in rows} == {pending["id"]}
    await acknowledge(b, [d["id"] for d in rows])
    await bridge.call(scoped(RED, "unsubscribe", subscription_id=raw_sub["id"]))
    evidence.record(name + "-rendered-model-disable-and-enable-preserve-filtered-backlog-while-raw-progresses-with-zero-inference")


async def concurrent_tabs(page, f, evidence, name, errors, http_errors, expected_http):
    other = await page.context.new_page()
    instrument(other, errors, http_errors)
    other.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    await other.goto(f.base + "/admin")
    await expect(other.get_by_role("heading", name="Overview", exact=True)).to_be_visible()
    await navigate(page, "Settings")
    await navigate(other, "Settings")
    await page.get_by_label("threshold ppm", exact=True).fill("812345")
    await other.get_by_label("threshold ppm", exact=True).fill("812346")
    await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
    expected_http.append(409)
    failed, _, _ = await mutation(other, other.get_by_role("button", name="Confirm and save settings", exact=True), "config_update", 409)
    assert failed["error"]["code"] == "CONFIG_CONFLICT"
    await expect(other.locator("#error")).to_contain_text("Settings changed")
    assert f.admin().call({"op": "config_get"})["config"]["threshold_ppm"] == 812345
    await other.get_by_role("button", name="Refresh", exact=True).click()
    await expect(other.get_by_label("threshold ppm", exact=True)).to_have_value("812345")
    await capture(other, f.root, name + "-concurrent-tab")
    await other.close()
    evidence.record(name + "-two-rendered-tabs-reject-stale-settings-save-without-overwriting-accepted-change")


async def project_catalog(page, f, evidence, name, original):
    await navigate(page, "Projects")
    target = page.locator("section.row").filter(has=page.get_by_text("Project ID: " + RED, exact=True))
    await target.get_by_role("button", name="Project settings", exact=True).click()
    await page.get_by_label("Override federation", exact=True).check()
    await page.get_by_role("button", name="Add source", exact=True).click()
    source = page.locator("fieldset.source-entry").last
    values = (("Source host", "github.com"), ("Source tenant", "browser-" + name), ("Source resource", "owned-repo"),
              ("Source description", "Project-owned browser source " + name), ("Approved publication IDs, one per line", original["id"]))
    for label, value in values:
        await source.get_by_label(label, exact=True).fill(value)
    await source.get_by_label("Canonical owner", exact=True).check()
    await mutation(page, page.get_by_role("button", name="Save project settings", exact=True), "config_update")
    await expect(page.get_by_role("heading", name="Create project", exact=True)).to_be_visible()
    config = f.admin().call({"op": "config_get"})["config"]
    red = next(p for p in config["projects"] if p["id"] == RED)
    entry = red["settings"]["federation"]["catalog"]["entries"][-1]
    assert entry["canonical"] and entry["export_publication_ids"] == [original["id"]]
    assert not config.get("federation") and not next(p for p in config["projects"] if p["id"] == BLUE)["settings"]
    agent = await f.agent("red-a")
    directory = await agent.call(scoped(RED, "federation_directory"))
    assert any(e["scope"]["tenant"] == "browser-" + name and e["canonical"] for e in directory["catalog"]["items"])
    evidence.record(name + "-rendered-project-canonical-source-and-approved-export-override-preserves-server-default-and-other-project")


async def oidc(page, browser, f, provider, evidence, name, size, errors, http_errors):
    await navigate(page, "Settings")
    await expect(page.get_by_role("button", name="Confirm and save settings", exact=True)).to_be_visible()
    setup = page.get_by_role("button", name="Configure OIDC provider", exact=True)
    if await setup.count():
        await setup.click()
        for label, value in (("provider id", "independent-provider"), ("issuer", provider.issuer),
                             ("client id", "independent-client"), ("client secret", "fixture-client-secret")):
            await page.get_by_label(label, exact=True).fill(value)
        await page.get_by_label("mode", exact=True).select_option("both")
    for role, groups in (("Admin", ""), ("Developer", "engineering"), ("Viewer", "readers")):
        await page.locator('fieldset:has(> legend:text-is("' + role + '"))').get_by_label("One value per line", exact=True).fill(groups)
    await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
    provider.subject = "multi-browser-" + name
    provider.groups = ["engineering", "readers"]
    context = await browser.new_context(viewport=size)
    op = await context.new_page()
    instrument(op, errors, http_errors)
    try:
        await op.goto(f.base + "/admin")
        await op.get_by_role("link", name="Sign in with identity provider", exact=True).click()
        await expect(op.get_by_role("heading", name="Users", exact=True)).to_be_visible()
        session = await op.evaluate("fetch('/admin/session').then(r=>r.json())")
        assert session["user"]["role"] == "Developer" and not session["user"].get("project_ids")
        await expect(op.get_by_text("No projects assigned. Ask an Admin for project access.", exact=True)).to_be_visible()
        await navigate(page, "Users")
        target = page.locator("section.row").filter(has_text="subject " + provider.subject)
        await target.get_by_role("button", name="Edit user", exact=True).click()
        await target.get_by_label(re.compile(r"^Project access: .*\(" + BLUE + r"\)$")).check()
        await mutation(page, target.get_by_role("button", name="Save user", exact=True), "save_user")
        await op.get_by_role("button", name="Refresh", exact=True).click()
        await expect(op.get_by_label("Project", exact=True).locator("option")).to_have_count(1)
        assert await op.get_by_label("Project", exact=True).input_value() == BLUE
        await navigate(page, "Settings")
        await page.locator('fieldset:has(> legend:text-is("Developer"))').get_by_label("One value per line", exact=True).fill("")
        await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
        await op.get_by_role("button", name="Refresh", exact=True).click()
        await navigate(op, "Agents")
        await expect(op.get_by_role("button", name="Create agent", exact=True)).to_have_count(0)
        session = await op.evaluate("fetch('/admin/session').then(r=>r.json())")
        assert session["user"]["role"] == "Viewer" and session["user"]["project_ids"] == [BLUE]
        await expect(op.get_by_role("button", name="Settings", exact=True)).to_have_count(0)
        await capture(op, f.root, name + "-oidc-admission")
        evidence.record(name + "-real-oidc-highest-role-and-hot-group-remap-keep-explicit-project-admission-independent")
    finally:
        await context.close()


async def late_awaits(page, f, evidence, name):
    for view, op in (("Subscriptions", "agents"), ("Activity", "jobs")):
        await page.get_by_label("Project", exact=True).select_option(RED)
        await navigate(page, view)
        awaited = page.get_by_role("button", name="Create subscription", exact=True) if view == "Subscriptions" else page.get_by_role("heading", name="Query jobs", exact=True)
        await expect(awaited).to_be_visible()
        delayed, release, delivered = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def hold(route):
            body = route.request.post_data_json
            if body.get("op") == op and not delayed.is_set():
                response = await route.fetch()
                delayed.set()
                await release.wait()
                await route.fulfill(response=response)
                delivered.set()
            else:
                await route.continue_()
        await page.route("**/admin/api", hold)
        await page.get_by_role("button", name="Refresh", exact=True).click()
        await asyncio.wait_for(delayed.wait(), 10)
        await page.get_by_label("Project", exact=True).select_option(BLUE)
        await expect(awaited).to_be_visible()
        release.set()
        await asyncio.wait_for(delivered.wait(), 10)
        await page.unroute("**/admin/api", hold)
        await asyncio.sleep(.1)
        if view == "Subscriptions":
            await expect(page.get_by_role("button", name="Create subscription", exact=True)).to_have_count(1)
            owners = await page.get_by_label("Owner agent", exact=True).locator("option").evaluate_all("nodes=>nodes.map(n=>n.value)")
            assert set(owners) == {"blue-a", "blue-b", "bridge"}
        else:
            await expect(page.get_by_role("heading", name="Matching jobs", exact=True)).to_have_count(1)
            await expect(page.get_by_role("heading", name="Query jobs", exact=True)).to_have_count(1)
    await page.get_by_label("Project", exact=True).select_option(RED)
    evidence.record(name + "-late-subscription-agents-and-activity-jobs-responses-cannot-append-after-project-switch")


async def viewport(browser, f, provider, evidence, name, size, password):
    context = await browser.new_context(viewport=size)
    page = await context.new_page()
    errors, http_errors, expected_http = [], [], []
    instrument(page, errors, http_errors)
    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    try:
        await login(page, f.base, "admin", password)
        a, b, bridge, sid, original, fields = await subscription_flow(page, f, evidence, name)
        await model_transition(page, f, evidence, name, a, b, bridge, fields)
        await b.call(scoped(RED, "unsubscribe", subscription_id=sid))
        await concurrent_tabs(page, f, evidence, name, errors, http_errors, expected_http)
        await late_awaits(page, f, evidence, name)
        await project_catalog(page, f, evidence, name, original)
        await oidc(page, browser, f, provider, evidence, name, size, errors, http_errors)
        anticipated = [e for e in errors if e.startswith("console: Failed to load resource:") and "409" in e]
        assert len(anticipated) <= len(expected_http)
        assert not [e for e in errors if e not in anticipated] and sorted(http_errors) == sorted(expected_http), (errors, http_errors)
        evidence.record(name + "-focused-admin-browser-flows-no-unexpected-console-request-http-errors")
    finally:
        await context.close()


async def main(args):
    if not args.with_model:
        raise ValueError("--with-model is required for the controlled filter transport fixture")
    args.keep_work = args.keep_work.resolve()
    f = Fixture(args)
    evidence = Evidence(args.report, "adhd/admin-project-browser@1")
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest()
    provider = None
    try:
        await f.start()
        provider = Provider(f.root)
        password = re.search(r"^Password: (.+)$", (f.root / "initial-admin-password.txt").read_text(), re.M)[1]
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            for name, size in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
                await viewport(browser, f, provider, evidence, name, size, password)
            await browser.close()
        assert provider.exchanges == 2
        evidence.value["real_oidc_exchanges"] = provider.exchanges
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()
        if provider:
            provider.close()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
