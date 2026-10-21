#!/usr/bin/env python3
"""Real desktop/mobile Admin initialization and target-only recovery console.

All successful replies come from the actual backend and Kafka. One captured real
status reply is delayed across a project switch to test UI epoch isolation.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from playwright.async_api import async_playwright, expect

from foundation_acceptance import Client
from multi_support import Evidence, Fixture, arguments, poll_until, scoped
from project_recovery_acceptance import Recovery, RED, BLUE
from project_recovery_restore import offline_bundle
from project_recovery_state import digest, route


async def login(page, base, username, password):
    await page.goto(base + "/admin")
    await page.get_by_label("Username", exact=True).fill(username)
    await page.get_by_label("Password", exact=True).fill(password)
    await page.get_by_role("button", name="Sign in", exact=True).click()


async def capture(page, directory, label):
    assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not await page.get_by_text("NaN", exact=True).count()
    png = directory / (label + ".png")
    text = directory / (label + ".txt")
    await page.screenshot(path=str(png), full_page=True)
    text.write_text(await page.locator("body").aria_snapshot())
    return {"name": label, "png_sha256": digest(png.read_bytes()), "structure_sha256": digest(text.read_bytes()),
        "path": str(png)}


async def viewport(args, browser, name, width, height, evidence):
    local = copy.copy(args)
    local.keep_work = args.keep_work / name
    local.with_model = False
    f = Fixture(local, initialize_projects=False)
    f.config["recovery"] = {"backup_root": str(f.root / "offline-backups")}
    errors, captures = [], []
    release = None
    context = await browser.new_context(viewport={"width": width, "height": height})
    page = await context.new_page()
    def observe(target):
        target.on("pageerror", lambda e: errors.append("pageerror " + str(e)))
        target.on("console", lambda m: errors.append("console " + m.text) if m.type == "error" else None)
        target.on("requestfailed", lambda q: errors.append("requestfailed " + q.method + " " + q.url.split("?")[0]))
        target.on("response", lambda r: errors.append("HTTP " + str(r.status) + " " + r.url.split("?")[0]) if r.status >= 400 else None)
    observe(page)
    page.on("dialog", lambda d: asyncio.create_task(d.accept()))
    try:
        await f.start()
        r = Recovery(f, args.recovery_schema)
        password = re.search(r"^Password: (.+)$", (f.root / "initial-admin-password.txt").read_text(), re.M)[1]
        await login(page, f.base, "admin", password)
        await expect(page.get_by_role("heading", name="Recovery", exact=True)).to_be_visible()
        await expect(page.get_by_text("Target " + RED + " · uninitialized", exact=True)).to_be_visible()
        await expect(page.get_by_role("button", name="Apply reviewed plan", exact=True)).to_have_count(0)
        captures.append(await capture(page, f.root, "uninitialized"))
        before = r.revision()
        await page.get_by_role("button", name="Review empty initialization", exact=True).click()
        await expect(page.get_by_role("button", name="Apply reviewed plan", exact=True)).to_be_visible()
        plan = r.status(RED)["operation"]["plan"]
        r.assert_plan(plan, RED, "initialize")
        await page.get_by_role("heading", name="Recovery status", exact=True).locator("..").locator("details").last.locator("summary").click()
        assert plan["plan_sha256"] in await page.locator("#content").inner_text()
        captures.append(await capture(page, f.root, "review-initialization"))
        await page.get_by_role("button", name="Apply reviewed plan", exact=True).click()
        await expect(page.get_by_text("apply · complete", exact=True)).to_be_visible(timeout=30000)
        assert r.status(RED)["availability"] == "ready" and r.revision() == before
        assert r.status(RED)["operation"]["result"]["initialized"] is True
        await page.get_by_role("button", name="Refresh", exact=True).click()
        await expect(page.get_by_text("Target " + RED + " · ready", exact=True)).to_be_visible()
        await expect(page.get_by_role("button", name="Review empty initialization", exact=True)).to_have_count(0)
        # The defaults come from status, while an absent root object stays absent
        # in config_get. Both save and reset must work without a hub restart.
        pid = f.process.pid
        await page.get_by_text("Recovery settings", exact=True).click()
        await page.get_by_label("scan batch records", exact=True).fill("17")
        await page.get_by_label("timeout ms", exact=True).fill("280000")
        async with page.expect_response(lambda response: response.url.endswith("/admin/api") and response.request.post_data_json.get("op") == "config_update") as saved:
            await page.get_by_role("button", name="Save recovery settings", exact=True).click()
        assert (await saved.value).status == 200
        await expect(page.get_by_text("Target " + RED + " · ready", exact=True)).to_be_visible()
        assert f.process.pid == pid
        assert r.status(RED)["settings"]["scan_batch_records"] == 17
        await page.get_by_text("Recovery settings", exact=True).click()
        async with page.expect_response(lambda response: response.url.endswith("/admin/api") and response.request.post_data_json.get("op") == "config_update") as reset:
            await page.get_by_role("button", name="Restore default recovery settings", exact=True).click()
        assert (await reset.value).status == 200
        await expect(page.get_by_text("Target " + RED + " · ready", exact=True)).to_be_visible()
        assert r.status(RED)["settings"]["timeout_ms"] == 300000
        assert "recovery" not in f.admin().call({"op": "config_get"})["config"]
        assert f.process.pid == pid
        # Restore the fixture's explicit offline bundle prerequisite through the
        # same hot configuration API, then refresh its reviewed revision in UI.
        f.admin().call({"op": "config_update", "patch": {"recovery": f.config["recovery"]}}, mutation=True)
        await page.get_by_role("button", name="Refresh", exact=True).click()
        await expect(page.get_by_text("Target " + RED + " · ready", exact=True)).to_be_visible()
        await r.initialize(BLUE)
        actor, recipient = await f.agent("bridge"), await f.agent("red-b")
        await recipient.call(scoped(RED, "subscribe", mode="raw"))
        original = (await actor.call(scoped(RED, "publish_record", text="Retained browser recovery original")))["record"]["publication"]
        rows = await poll_until(recipient, RED, {original["id"]})
        await recipient.call(scoped(RED, "ack", delivery_ids=[d["id"] for d in rows if d.get("publication_id") == original["id"]]))
        private = (await actor.call(scoped(RED, "send", recipient_id="red-b", text="PRIVATE_RECOVERY_BROWSER_SENTINEL")))["delivery"]
        await page.goto("about:blank")
        f.hard_stop()
        _, manifest_sha, _ = offline_bundle(f, r, "browser-backup")
        await f.start()
        actor, recipient = await f.agent("bridge"), await f.agent("red-b")
        lost = (await actor.call(scoped(RED, "publish_record", text="Lost post-backup browser fact")))["record"]["publication"]
        await poll_until(recipient, RED, {lost["id"]})  # proves actual old-topic tail exists
        newer = (await actor.call(scoped(BLUE, "publish_record", text="Blue keeps its newer browser fact")))["record"]["publication"]
        config = copy.deepcopy(f.admin().call({"op": "config_get"})["config"])
        blue_route = r.status(BLUE)["route"]
        old_red_route = r.status(RED)["route"]
        f.hard_stop()
        _, anchor = route(f.file, RED)
        for path in (anchor, Path(str(anchor) + ".snapshot")):
            assert path.is_file() and not path.is_symlink()
            os.replace(path, path.with_name(path.name + ".browser-lost"))
        await f.start()
        await login(page, f.base, "admin", password)
        await expect(page.get_by_role("heading", name="Recovery", exact=True)).to_be_visible()
        await expect(page.get_by_text("Target " + RED + " · recovery_required", exact=True)).to_be_visible()
        await expect(page.get_by_role("button", name="Review empty initialization", exact=True)).to_have_count(0)
        await page.get_by_label("Backup ID", exact=True).fill("browser-backup")
        await page.get_by_label("Manifest SHA256", exact=True).fill(manifest_sha)
        await page.get_by_label("Allow restore when initialized target files are missing", exact=True).check()
        await page.get_by_role("button", name="Review restore plan", exact=True).click()
        await expect(page.get_by_role("button", name="Apply reviewed plan", exact=True)).to_be_visible(timeout=30000)
        plan = r.status(RED)["operation"]["plan"]
        r.assert_plan(plan, RED, "restore")
        assert plan["manifest_sha256"] == manifest_sha
        await page.get_by_role("heading", name="Recovery status", exact=True).locator("..").locator("details").last.locator("summary").click()
        assert plan["plan_sha256"] in await page.locator("#content").inner_text()
        captures.append(await capture(page, f.root, "review-restore"))
        await page.get_by_role("button", name="Apply reviewed plan", exact=True).click()
        await expect(page.get_by_text("apply · complete", exact=True)).to_be_visible(timeout=30000)
        actual = r.status(RED)
        assert actual["operation"]["result"]["transport_discontinuity"] is True
        assert actual["route"]["project_epoch"] != old_red_route["project_epoch"]
        assert actual["route"]["topic"] != old_red_route["topic"]
        assert r.status(BLUE)["route"] == blue_route
        assert f.admin().call({"op": "config_get"})["config"] == config
        actor, recipient = await f.agent("bridge"), await f.agent("red-b")
        assert (await actor.call(scoped(RED, "get", publication_id=original["id"])))["publication"] == original
        assert (await actor.call(scoped(BLUE, "get", publication_id=newer["id"])))["publication"] == newer
        queued = (await recipient.call(scoped(RED, "poll")))["deliveries"]
        assert [d["id"] for d in queued] == [private["id"]]
        assert lost["id"] not in json.dumps(await actor.call(scoped(RED, "search", query="Lost post-backup browser fact")))
        html = await page.content()
        assert "PRIVATE_RECOVERY_BROWSER_SENTINEL" not in html
        assert password not in html and not any(token in html for token in f.tokens.values())
        captures.append(await capture(page, f.root, "restored"))
        # Delay one actual response, then switch context. No synthetic success
        # or altered server data is served; only timing changes.
        captured, release = asyncio.Event(), asyncio.Event()
        async def delayed(route_request):
            body = route_request.request.post_data_json
            if body.get("op") == "project_restore_status" and body.get("project_id") == RED and not captured.is_set():
                response = await route_request.fetch()
                captured.set()
                await release.wait()
                await route_request.fulfill(response=response)
            else:
                await route_request.continue_()
        await page.route("**/admin/api", delayed)
        await page.get_by_role("button", name="Refresh recovery status", exact=True).click()
        await asyncio.wait_for(captured.wait(), 10)
        await page.get_by_label("Project", exact=True).select_option(BLUE)
        await expect(page.get_by_text("Target " + BLUE + " · ready", exact=True)).to_be_visible()
        release.set()
        await asyncio.sleep(.2)
        assert "Target " + RED not in await page.locator("#content").inner_text()
        alert_text = await page.get_by_role("alert").inner_text()
        evidence.value["late_response_observation"] = {"viewport": name,
            "selected_project": await page.get_by_label("Project", exact=True).input_value(),
            "alert_text": alert_text, "old_target_visible": "Target " + RED in await page.locator("#content").inner_text()}
        if alert_text:
            captures.append(await capture(page, f.root, "late-response-failure"))
            evidence.value["failure_captures"] = captures
        evidence.write()
        assert alert_text == ""
        await page.unroute("**/admin/api", delayed)
        # Real lower-role browser sessions see only their explicit healthy grant.
        for role in ("Developer", "Viewer"):
            username = name + "-recovery-" + role.lower()
            f.admin().call({"op": "save_user", "user": {"username": username, "name": "Recovery " + role,
                "email": username + "@example.invalid", "password": "private-role-password", "role": role,
                "project_ids": [BLUE]}}, mutation=True)
            lower = await browser.new_context(viewport={"width": width, "height": height})
            child = await lower.new_page()
            observe(child)
            await login(child, f.base, username, "private-role-password")
            await expect(child.get_by_role("heading", name="Overview", exact=True)).to_be_visible()
            await expect(child.get_by_role("button", name="Recovery", exact=True)).to_have_count(0)
            await expect(child.get_by_role("button", name="Review restore plan", exact=True)).to_have_count(0)
            assert await child.get_by_label("Project", exact=True).locator("option").evaluate_all("xs=>xs.map(x=>x.value)") == [BLUE]
            await lower.close()
        assert not errors, errors
        evidence.record(name + "-rendered-init-hot-settings-missing-target-restore-current-security-and-project-epoch",
            viewport={"width": width, "height": height}, captures=captures, normal_path_errors=errors,
            delay_scope="One unmodified actual status response released after project switch")
    finally:
        if release is not None:
            release.set()
        try:
            await context.close()
        finally:
            try:
                await f.close()
            finally:
                f.bind_evidence(evidence, key=name + "_runtime")
                evidence.write()


async def main(args):
    assert not args.rest_url and args.keep_work, "Browser recovery requires an owned private --keep-work directory"
    evidence = Evidence(args.report, "project-recovery-browser")
    evidence.value["harness_sha256"] = digest(Path(__file__).read_bytes())
    if args.hub:
        evidence.value["artifact_sha256"] = digest(args.hub.read_bytes())
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
                    await viewport(args, browser, name, width, height, evidence)
            finally:
                await browser.close()
    except BaseException as error:
        evidence.finish(error)
        raise
    else:
        evidence.finish()


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--recovery-schema", type=Path,
        default=Path(__file__).resolve().parents[1] / "components/hub/project-recovery/interface.schema.json")
    asyncio.run(main(parser.parse_args()))
