#!/usr/bin/env python3
"""Rendered desktop/mobile project, eventing, membership and role acceptance."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from playwright.async_api import async_playwright, expect

from multi_support import Evidence, Fixture, arguments, scoped


RED, BLUE = "project-red", "project-blue"


async def login(page, base, username, password, view="Overview"):
    await page.goto(base + "/admin")
    await page.get_by_label("Username", exact=True).fill(username)
    await page.get_by_label("Password", exact=True).fill(password)
    await page.get_by_role("button", name="Sign in", exact=True).click()
    await expect(page.get_by_role("heading", name=view, exact=True)).to_be_visible()
    if view == "Overview":
        await expect(page.get_by_label("Project", exact=True)).to_be_visible()


async def navigate(page, name):
    await page.get_by_role("button", name=name, exact=True).click()
    await expect(page.get_by_role("heading", name=name, exact=True)).to_be_visible()


async def save(page, button, op, same_view=True):
    async with page.expect_response(lambda response: response.url.endswith("/admin/api")
        and response.request.method == "POST" and response.request.post_data_json.get("op") == op) as event:
        await button.click()
    response = await event.value
    assert response.status == 200, "Rendered mutation failed: " + op
    await response.body()
    # Form values change immediately on fill/select; they are not evidence that
    # the request finished or that the server's new form has been installed.
    if same_view:
        await expect(button).to_be_enabled()


async def capture(page, root, name):
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Horizontal viewport overflow"
    await expect(page.get_by_text("NaN", exact=True)).to_have_count(0)
    await expect(page.get_by_text("Infinity", exact=True)).to_have_count(0)
    for link in await page.locator("a[href], img[src]").evaluate_all("nodes => nodes.map(n => n.getAttribute('href') || n.getAttribute('src'))"):
        assert link and not any(part in link for part in ("undefined", "NaN", "Infinity")), "Broken rendered resource URL"
    await page.screenshot(path=str(root / (name + ".png")), full_page=True)
    (root / (name + ".txt")).write_text(await page.locator("body").aria_snapshot())


def instrument(page, errors, http_errors):
    page.on("pageerror", lambda error: errors.append("page: " + str(error)))
    page.on("console", lambda message: errors.append("console: " + message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: errors.append("request: " + str(request.failure)))
    page.on("response", lambda response: http_errors.append(response.status) if response.status >= 400 else None)


async def create_user(page, name, role, project, username, password):
    await navigate(page, "Users")
    form = page.locator("#content > form")
    await form.get_by_label("Username", exact=True).fill(username)
    await form.get_by_label("Name", exact=True).fill(name)
    await form.get_by_label("Email", exact=True).fill(username + "@example.invalid")
    await form.get_by_label("Role", exact=True).select_option(role)
    await form.get_by_label("Password (blank retains current password)", exact=True).fill(password)
    if project:
        await form.get_by_label(re.compile(r"^Project access: .*\(" + re.escape(project) + r"\)$")).check()
    await save(page, form.get_by_role("button", name="Save user", exact=True), "save_user")
    await expect(page.get_by_role("heading", name=name, exact=True)).to_be_visible()


async def projects(page, f, suffix):
    await navigate(page, "Projects")
    section = page.locator("section.row").filter(has=page.get_by_role("heading", name="Create project", exact=True))
    project = "browser-project-" + suffix
    await section.get_by_label("Stable project ID", exact=True).fill(project)
    await section.get_by_label("Project name", exact=True).fill("Browser project " + suffix)
    await section.get_by_label("Project description", exact=True).fill("Created from rendered Admin controls")
    await save(page, section.get_by_role("button", name="Create project", exact=True), "config_update")
    row = page.locator("section.row").filter(has=page.get_by_text("Project ID: " + project, exact=True))
    await expect(row.get_by_label("Project name", exact=True)).to_have_value("Browser project " + suffix)
    renamed = "Renamed browser project " + suffix
    await row.get_by_label("Project name", exact=True).fill(renamed)
    await save(page, row.get_by_role("button", name="Save project", exact=True), "config_update")
    row = page.locator("section.row").filter(has=page.get_by_text("Project ID: " + project, exact=True))
    await expect(row.get_by_label("Project name", exact=True)).to_have_value(renamed)
    for state in ("archived", "active"):
        await row.get_by_label("Project state", exact=True).select_option(state)
        await save(page, row.get_by_role("button", name="Save project", exact=True), "config_update")
        row = page.locator("section.row").filter(has=page.get_by_text("Project ID: " + project, exact=True))
        await expect(row.get_by_label("Project state", exact=True)).to_have_value(state)
    registry = f.admin().call({"op": "config_get"})["config"]["projects"]
    saved = next(p for p in registry if p["id"] == project)
    assert saved["name"] == renamed and saved["status"] == "active"


async def event_settings(page, f, suffix):
    await navigate(page, "Events")
    await expect(page.get_by_role("heading", name="Event transport", exact=True)).to_be_visible()
    await expect(page.get_by_label("Kafka REST service URL", exact=True)).to_have_value(f.args.eventing_rest_url)
    value = "220" if suffix == "desktop" else "240"
    await page.get_by_label("Retry delay (ms)", exact=True).fill(value)
    await save(page, page.get_by_role("button", name="Save event settings", exact=True), "config_update")
    await expect(page.get_by_label("Retry delay (ms)", exact=True)).to_have_value(value)
    current = f.admin().call({"op": "config_get"})
    assert current["config"]["eventing"]["retry_ms"] == int(value)
    assert f.process is None or f.process.poll() is None


async def project_overrides(page, f, suffix):
    keys = ("matcher", "threshold_ppm", "federation", "history", "retrieval", "archive", "feedback", "optimization")
    original = f.admin().call({"op": "config_get"})["config"]
    defaults = {key: original.get(key) for key in keys}

    async def open_settings():
        await navigate(page, "Projects")
        row = page.locator("section.row").filter(has=page.get_by_text("Project ID: " + RED, exact=True))
        await row.get_by_role("button", name="Project settings", exact=True).click()
        await expect(page.get_by_role("button", name="Save project settings", exact=True)).to_be_visible()

    await open_settings()
    for key in keys:
        await page.get_by_label("Override " + key.replace("_", " "), exact=True).check()
    await page.get_by_label("threshold ppm", exact=True).fill("812345")
    await save(page, page.get_by_role("button", name="Save project settings", exact=True), "config_update", same_view=False)
    await expect(page.get_by_role("heading", name="Create project", exact=True)).to_be_visible()
    current = f.admin().call({"op": "config_get"})["config"]
    red = next(project for project in current["projects"] if project["id"] == RED)
    assert set(red["settings"]) == set(keys)
    assert red["settings"]["threshold_ppm"] == 812345
    assert {key: current.get(key) for key in keys} == defaults, "Project edits changed server defaults"
    assert not next(project for project in current["projects"] if project["id"] == BLUE)["settings"]
    await open_settings()
    for key in keys:
        await expect(page.get_by_label("Override " + key.replace("_", " "), exact=True)).to_be_checked()
    await capture(page, f.root, suffix + "-project-overrides")
    for key in keys:
        await page.get_by_label("Override " + key.replace("_", " "), exact=True).uncheck()
    await save(page, page.get_by_role("button", name="Save project settings", exact=True), "config_update", same_view=False)
    await expect(page.get_by_role("heading", name="Create project", exact=True)).to_be_visible()
    current = f.admin().call({"op": "config_get"})["config"]
    assert not next(project for project in current["projects"] if project["id"] == RED)["settings"]
    assert {key: current.get(key) for key in keys} == defaults


async def stream_forms(page, f, suffix):
    await page.get_by_label("Project", exact=True).select_option(RED)
    await navigate(page, "Subscriptions")
    await page.get_by_label("Owner agent", exact=True).select_option("red-b")
    await page.get_by_label("Subscription mode", exact=True).select_option("raw")
    criterion = page.get_by_label("Plain-text filter", exact=True)
    assert await criterion.is_disabled() or not await criterion.is_visible(), "Raw mode must not silently ignore editable filter text"
    await save(page, page.get_by_role("button", name="Create subscription", exact=True), "create_subscription")
    # Check through the public agent protocol; a visible form submission alone
    # cannot prove the stored raw mode, owner or correct project selection.
    b = await f.agent("red-b")
    subscriptions = (await b.call(scoped(RED, "list_subscriptions")))["subscriptions"]
    assert any(s["mode"] == "raw" for s in subscriptions)
    if f.model:
        await page.get_by_label("Owner agent", exact=True).select_option("red-b")
        await page.get_by_label("Subscription mode", exact=True).select_option("filtered")
        await expect(criterion).to_be_enabled()
        await page.get_by_label("Plain-text filter", exact=True).fill("Only API compatibility changes " + suffix)
        await save(page, page.get_by_role("button", name="Create subscription", exact=True), "create_subscription")
        subscriptions = (await b.call(scoped(RED, "list_subscriptions")))["subscriptions"]
        assert any(s["mode"] == "filtered" for s in subscriptions)


async def viewport_checks(browser, f, evidence, suffix, viewport, password):
    context = await browser.new_context(viewport=viewport)
    page = await context.new_page()
    errors = []
    normal_http_errors = []
    instrument(page, errors, normal_http_errors)
    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    await login(page, f.base, "admin", password)
    await navigate(page, "Information")
    await expect(page.get_by_text("RED-ONLY-FACT", exact=True)).to_be_visible()
    await expect(page.get_by_text("BLUE-ONLY-FACT", exact=True)).to_have_count(0)

    # Delay a real old-project response until after selecting another project.
    # The fulfilled bytes come from the server; only timing is changed.
    delayed = asyncio.Event()
    release = asyncio.Event()

    async def hold_old_project(route):
        body = route.request.post_data_json
        if body.get("op") == "publications" and body.get("project_id") == RED and not delayed.is_set():
            response = await route.fetch()
            delayed.set()
            await release.wait()
            await route.fulfill(response=response)
        else:
            await route.continue_()

    await page.route("**/admin/api", hold_old_project)
    await page.get_by_role("button", name="Refresh", exact=True).click()
    await asyncio.wait_for(delayed.wait(), timeout=10)
    await page.get_by_label("Project", exact=True).select_option(BLUE)
    await expect(page.get_by_text("BLUE-ONLY-FACT", exact=True)).to_be_visible()
    release.set()
    await page.wait_for_timeout(250)
    await expect(page.get_by_text("RED-ONLY-FACT", exact=True)).to_have_count(0)
    await expect(page.get_by_text("BLUE-ONLY-FACT", exact=True)).to_be_visible()
    await page.unroute("**/admin/api", hold_old_project)
    await capture(page, f.root, suffix + "-project-switch")
    evidence.record(suffix + "-project-switch-clears-previous-data-and-fences-late-response")

    pid = f.process.pid if f.process else None
    await projects(page, f, suffix)
    await capture(page, f.root, suffix + "-projects")
    await event_settings(page, f, suffix)
    await capture(page, f.root, suffix + "-events")
    assert f.process is None or f.process.pid == pid
    evidence.record(suffix + "-rendered-hot-project-create-rename-archive-resume-and-eventing-settings")
    await project_overrides(page, f, suffix)
    evidence.record(suffix + "-all-project-policy-overrides-save-and-reset-inheritance-without-changing-defaults")

    username = "browser-dev-" + suffix
    devpass = "Browser developer password " + uuid4().hex
    await create_user(page, "Browser Developer " + suffix, "Developer", RED, username, devpass)
    await capture(page, f.root, suffix + "-user-project-admission")
    dev_context = await browser.new_context(viewport=viewport)
    developer = await dev_context.new_page()
    instrument(developer, errors, normal_http_errors)
    await login(developer, f.base, username, devpass)
    await expect(developer.get_by_label("Project", exact=True).locator("option")).to_have_count(1)
    assert await developer.get_by_label("Project", exact=True).input_value() == RED
    for admin_view in ("Projects", "Events", "Settings"):
        await expect(developer.get_by_role("button", name=admin_view, exact=True)).to_have_count(0)
    await navigate(developer, "Agents")
    agent_id = "browser-agent-" + suffix
    await developer.get_by_label("Agent ID", exact=True).fill(agent_id)
    await developer.get_by_role("button", name="Generate token", exact=True).click()
    token = await developer.get_by_label("Agent token (save securely before submitting)", exact=True).input_value()
    await developer.get_by_label(re.compile(r"^Agent project: .*\(project-red\)$")).check()
    await save(developer, developer.get_by_role("button", name="Create agent", exact=True), "create_agent")
    await expect(developer.get_by_role("heading", name=agent_id, exact=True)).to_be_visible()
    assert token not in await developer.locator("body").inner_text()
    f.tokens[agent_id] = token
    assert "error" not in (await f.raw(agent_id, scoped(RED, "whoami"))).json()
    assert "error" in (await f.raw(agent_id, scoped(BLUE, "whoami"))).json()
    await capture(developer, f.root, suffix + "-developer-agent")
    evidence.record(suffix + "-rendered-user-admission-developer-agent-creation-and-project-denial")

    viewer_name, viewer_password = "browser-view-" + suffix, "Browser viewer password " + uuid4().hex
    await create_user(page, "Browser Viewer " + suffix, "Viewer", BLUE, viewer_name, viewer_password)
    viewer_context = await browser.new_context(viewport=viewport)
    viewer = await viewer_context.new_page()
    instrument(viewer, errors, normal_http_errors)
    await login(viewer, f.base, viewer_name, viewer_password)
    await navigate(viewer, "Agents")
    for action in ("Create agent", "Edit agent"):
        await expect(viewer.get_by_role("button", name=action, exact=True)).to_have_count(0)
    response = await viewer_context.request.post(f.base + "/admin/api", data={"op": "config_get"})
    assert response.status in (401, 403)
    await capture(viewer, f.root, suffix + "-viewer")
    evidence.record(suffix + "-viewer-cannot-mutate-and-admin-api-denies-direct-access")

    unassigned_name, unassigned_password = "browser-none-" + suffix, "Unassigned password " + uuid4().hex
    await create_user(page, "Browser Unassigned " + suffix, "Viewer", None, unassigned_name, unassigned_password)
    unassigned_context = await browser.new_context(viewport=viewport)
    unassigned = await unassigned_context.new_page()
    instrument(unassigned, errors, normal_http_errors)
    await login(unassigned, f.base, unassigned_name, unassigned_password, view="Users")
    await expect(unassigned.get_by_text("No projects assigned. Ask an Admin for project access.", exact=True)).to_be_visible()
    for name in ("Projects", "Events", "Settings", "Information", "Subscriptions", "Activity"):
        await expect(unassigned.get_by_role("button", name=name, exact=True)).to_have_count(0)
    assert "project-hidden" not in await unassigned.locator("body").inner_text()
    await capture(unassigned, f.root, suffix + "-unassigned")
    evidence.record(suffix + "-zero-admission-account-has-usable-profile-without-hidden-projects-or-forbidden-requests")

    # Deliberate security failures use the request client, keeping the normal
    # rendered path free of intentional HTTP error console noise.
    session = await (await context.request.get(f.base + "/admin/session")).json()
    response = await context.request.post(f.base + "/admin/api", data={"op": "config_update",
        "patch": {"threshold_ppm": 812300}, "expected_revision": session["config_revision"],
        "message_id": uuid4().hex, "confirm": True}, headers={"X-CSRF-Token": "incorrect", "Origin": f.base})
    assert response.status == 403
    response = await context.request.post(f.base + "/admin/api", data={"op": "config_update",
        "patch": {"threshold_ppm": 812300}, "expected_revision": session["config_revision"] - 1,
        "message_id": uuid4().hex, "confirm": True}, headers={"X-CSRF-Token": session["csrf"], "Origin": f.base})
    assert response.status == 409
    evidence.record(suffix + "-cookie-csrf-and-stale-admin-revision-rejected")

    await stream_forms(page, f, suffix)
    await capture(page, f.root, suffix + "-subscriptions")
    assert not errors, errors
    assert not normal_http_errors, normal_http_errors
    for private in (password, *f.tokens.values()):
        assert private not in await page.content()
    await page.get_by_role("button", name="Log out", exact=True).click()
    await expect(page.get_by_label("Username", exact=True)).to_be_visible()
    assert await page.evaluate("localStorage.length + sessionStorage.length") == 0
    evidence.record(suffix + "-raw-optional-filter-controls-no-script-errors-secret-leaks-or-browser-credential-storage")
    await viewer_context.close()
    await unassigned_context.close()
    await dev_context.close()
    await context.close()


async def main(args):
    f = Fixture(args)
    evidence = Evidence(args.report, "adhd/multi-eventing-browser@1")
    if args.hub:
        evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest()
    try:
        await f.start()
        bridge = await f.agent("bridge")
        await bridge.call(scoped(RED, "publish", text="RED-ONLY-FACT"))
        await bridge.call(scoped(BLUE, "publish", text="BLUE-ONLY-FACT"))
        password = re.search(r"^Password: (.+)$", (f.root / "initial-admin-password.txt").read_text(), re.M)[1]
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            for name, viewport in (("desktop", {"width": 1440, "height": 1000}),
                                   ("mobile", {"width": 390, "height": 844})):
                await viewport_checks(browser, f, evidence, name, viewport, password)
            await browser.close()
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
