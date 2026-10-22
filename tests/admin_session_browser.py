#!/usr/bin/env python3
"""Real delayed old-session responses cannot reset a replacement browser session."""
import argparse
import asyncio
import fcntl
import hashlib
import json
from pathlib import Path
import tempfile

from playwright.async_api import async_playwright, expect, Error as BrowserError
from multi_workflow_upgrade import UpgradeRuntime
from browser_observation import BrowserObservation, capture


async def viewport_check(pw, runtime, password, viewport, report):
    browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    context = await browser.new_context(viewport=viewport)
    page = await context.new_page()
    page.set_default_timeout(15000)
    held, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    first, replies = [], []
    observation=BrowserObservation(page,runtime.base)
    label="desktop" if viewport["width"]==1440 else "mobile"
    captures=[]

    async def intercept(route):
        request = route.request
        try:
            body = request.post_data_json
        except Exception:
            body = None
        if not isinstance(body, dict) or body.get("op") != "list_projects" or first:
            await route.continue_()
            return
        first.append(True)
        observation.allow(request,op="list_projects",status=401,aborted=True)
        headers = await request.all_headers()
        held.set()
        probe = None
        try:
            await asyncio.wait_for(release.wait(), 45)
            assert request.url == runtime.base + "/admin/api"
            # An independent local reader can still establish the old credential's
            # real status if the browser correctly aborted its intercepted fetch.
            probe = await pw.request.new_context(extra_http_headers=headers)
            response = await probe.post(request.url, data=body)
            replies.append({"op": "list_projects", "status": response.status})
            assert response.status == 401
            try:
                await route.fulfill(response=response)
            except BrowserError:
                assert "ERR_ABORTED" in str(request.failure), request.failure
        finally:
            if probe:
                await probe.dispose()
            finished.set()

    await page.route("**/admin/api", intercept)

    async def login():
        await page.get_by_label("Username", exact=True).fill("admin")
        await page.get_by_label("Password", exact=True).fill(password)
        await page.get_by_role("button", name="Sign in", exact=True).click()

    try:
        await page.goto(runtime.base + "/admin")
        await login()
        await asyncio.wait_for(held.wait(), 15)
        await page.get_by_role("button", name="Log out", exact=True).click()
        await expect(page.get_by_label("Username", exact=True)).to_be_visible()
        await login()
        await expect(page.get_by_role("button", name="Settings", exact=True)).to_be_visible()
        await expect(page.get_by_text("Service reachable", exact=True)).to_be_visible()
        release.set()
        await asyncio.wait_for(finished.wait(), 15)
        await page.wait_for_timeout(250)
        session = await (await context.request.get(runtime.base + "/admin/session")).json()
        row = {"viewport": viewport, "old_responses": replies,
               "server_session_authenticated": session.get("authenticated"),
               "workspace_visible": await page.locator("#workspace").is_visible(),
               "login_visible": await page.get_by_label("Username", exact=True).is_visible(),
               "browser_observation": observation.check(), "captures":captures}
        report["observations"].append(row)
        assert replies == [{"op": "list_projects", "status": 401}]
        assert row["server_session_authenticated"] and row["workspace_visible"]
        assert not row["login_visible"]
        captures.append(await capture(page,runtime.root,label+"-replacement-session"))

        # A current-session revocation must still take effect. The revoker owns
        # a separate cookie jar, so its Set-Cookie cannot clear browser cookies.
        await page.get_by_role("button", name="Settings", exact=True).click()
        validate = page.get_by_role("button", name="Validate settings", exact=True)
        await expect(validate).to_be_visible()
        cookies = await context.cookies(runtime.base + "/admin")
        assert any(c["name"] == "adhd_session" for c in cookies)
        cookie = "; ".join(c["name"] + "=" + c["value"] for c in cookies)
        revoker = await pw.request.new_context(extra_http_headers={
            "Origin": runtime.base, "Cookie": cookie, "X-CSRF-Token": session["csrf"]})
        try:
            revocation = await revoker.post(runtime.base + "/admin/logout", data={})
            row["revocation_http_status"] = revocation.status
            assert revocation.status == 200
        finally:
            await revoker.dispose()
        async with page.expect_response(lambda r: r.url == runtime.base + "/admin/api"
                                         and r.status == 401
                                         and r.request.method == "POST"
                                         and r.request.post_data_json.get("op") == "config_validate") as denied:
            await validate.click()
        response=await denied.value
        observation.allow(response.request,op="config_validate",status=401)
        await expect(page.get_by_label("Username", exact=True)).to_be_visible()
        captures.append(await capture(page,runtime.root,label+"-current-session-revoked"))
        row["browser_observation"]=observation.check()
        row["current_session_revocation_returns_to_login"] = True
        row["passed"] = True
    finally:
        release.set()
        try:
            if not page.is_closed():
                report.setdefault("final_browser_observations",[]).append(observation.check())
        finally:await browser.close()


async def run(runtime, password, report):
    async with async_playwright() as pw:
        for viewport in ({"width": 1440, "height": 1000}, {"width": 390, "height": 844}):
            await viewport_check(pw, runtime, password, viewport, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--command")
    mode.add_argument("--image")
    parser.add_argument("--image-manifest", type=Path)
    parser.add_argument("--port-lock", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    parent = Path("_build/roadmap/browser").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="auth-fence-", dir=parent))
    command = json.loads(args.command) if args.command else []
    runtime = UpgradeRuntime(root / "hub", command, args.image, args.image_manifest)
    report = {"schema": "adhd/browser-authentication-fence@1", "passed": False,
              "observations": [], "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if command:
        report["artifact_sha256"] = hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()
    args.port_lock.parent.mkdir(parents=True, exist_ok=True)
    with args.port_lock.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            runtime.start()
            password = (runtime.root / "initial-admin-password.txt").read_text().split("Password: ")[1].strip()
            asyncio.run(asyncio.wait_for(run(runtime, password, report), 120))
            report["passed"] = True
        finally:
            runtime.stop()
            if runtime.owned_image:
                report["runtime"] = runtime.owned_image.identity()
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
