#!/usr/bin/env python3
"""Rendered Admin recovery/replay and CA forms against actual Kafka records."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

import httpx
from playwright.async_api import async_playwright, expect

from multi_browser import capture, create_user, instrument, login, navigate
from multi_support import Evidence, Fixture, arguments, poll_until, scoped


RED, BLUE = "project-red", "project-blue"


async def until(fn, message, seconds=25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = fn()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        await asyncio.sleep(.1)
    raise AssertionError(message)


async def mutation(page, button, op, expected=200):
    async with page.expect_response(lambda r: r.url.endswith("/admin/api") and r.request.method == "POST"
        and r.request.post_data_json.get("op") == op) as event:
        await button.click()
    response = await event.value
    value = await response.json()
    assert response.status == expected, (op, response.status, value.get("error", {}).get("code"))
    return value, response.request.post_data_json, response.request.headers


async def refresh(page):
    await page.get_by_role("button", name="Refresh", exact=True).click()
    await expect(page.get_by_role("heading", name="Event recovery", exact=True)).to_be_visible()
    await expect(page.get_by_role("button", name="Confirm event replay", exact=True)).to_be_enabled()


def certs(root):
    values = {}
    for name, ca in (("ca", "TRUE"), ("leaf", "FALSE")):
        key, cert = root / (name + ".key"), root / (name + ".pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=ADHD-browser-fixture-" + name, "-addext", "basicConstraints=critical,CA:" + ca,
            "-keyout", str(key), "-out", str(cert)], capture_output=True, check=True)
        key.chmod(0o600)
        values[name] = cert.read_text()
        values[name + "_key"] = key.read_text()
    return values


async def ca_forms(page, f, evidence, name, expected_http, certificates):
    await navigate(page, "Settings")
    enabled = page.get_by_label("Use custom Kafka REST CA certificates", exact=True)
    textarea = page.get_by_label("Kafka REST CA certificates (PEM)", exact=True)
    await expect(enabled).not_to_be_checked()
    await expect(textarea).to_be_disabled()
    current = f.admin().call({"op": "config_get"})["config_revision"]
    await enabled.check()
    await expect(textarea).to_be_enabled()
    for invalid in (certificates["leaf"], certificates["ca_key"], certificates["ca"] + "unrecognized text"):
        await textarea.fill(invalid)
        await textarea.blur()
        expected_http.append(400)
        await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update", 400)
        await expect(page.locator("#error")).not_to_be_empty()
        state = f.admin().call({"op": "config_get"})
        assert state["config_revision"] == current and not state["config"]["eventing"].get("tls_ca_pem")
    await textarea.fill(certificates["ca"])
    await textarea.blur()
    await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
    await expect(page.get_by_label("Use custom Kafka REST CA certificates", exact=True)).to_be_checked()
    await expect(page.get_by_label("Kafka REST CA certificates (PEM)", exact=True)).to_have_value(certificates["ca"])
    assert f.admin().call({"op": "config_get"})["config"]["eventing"]["tls_ca_pem"] == certificates["ca"]
    await capture(page, f.root, name + "-custom-ca")
    await page.get_by_label("Use custom Kafka REST CA certificates", exact=True).uncheck()
    await mutation(page, page.get_by_role("button", name="Confirm and save settings", exact=True), "config_update")
    await expect(page.get_by_label("Kafka REST CA certificates (PEM)", exact=True)).to_be_disabled()
    assert not f.admin().call({"op": "config_get"})["config"]["eventing"].get("tls_ca_pem")
    evidence.record(name + "-rendered-custom-ca-hot-save-remove-and-leaf-private-key-junk-rejection")


async def replay(page, f, evidence, name):
    a, b = await f.agent("red-a"), await f.agent("red-b")
    publication = (await a.call(scoped(RED, "publish", text="Browser retained original " + name,
        source={"kind": "fixture", "id": name, "item_id": uuid4().hex})))["publication"]
    status = lambda: f.admin().call({"op": "eventing_status", "project_id": RED})
    await until(lambda: status()["pending_events"] == 0, "Original not materialized")
    watermark = status()["replay_watermark"]
    sub = (await b.call(scoped(RED, "subscribe", mode="raw")))["subscription"]
    dummy = [(await a.call(scoped(RED, "subscribe", mode="raw")))["subscription"] for _ in range(100)]
    await asyncio.sleep(.3)
    assert not (await b.call(scoped(RED, "poll")))["deliveries"]
    await navigate(page, "Events")
    await expect(page.get_by_role("heading", name="Replay retained events", exact=True)).to_be_visible()
    await expect(page.get_by_text("Only the first 100 subscriptions are shown.", exact=False)).to_be_visible()
    await expect(page.locator('[data-replay-subscription][value="' + sub["id"] + '"]')).to_have_count(0)
    await page.get_by_label("Replay from sequence", exact=True).fill(str(watermark))
    await page.get_by_label("Replay through sequence", exact=True).fill(str(watermark))
    await page.get_by_label("Replay reason", exact=True).fill("Explicit browser replay " + name)
    await page.get_by_role("button", name="Add replay target", exact=True).click()
    await page.get_by_label("Replay target subscription ID", exact=True).fill(sub["id"])
    await page.get_by_label("Replay target revision", exact=True).fill(str(int(sub["revision"])))
    accepted, command, headers = await mutation(page, page.get_by_role("button", name="Confirm event replay", exact=True), "replay_events")
    rid = accepted["replay"]["id"]
    assert command["project_id"] == RED and command["subscriptions"] == [{"id": sub["id"], "revision": int(sub["revision"])}]
    rows = await poll_until(b, RED, {publication["id"]}, f.args.deadline)
    assert len(rows) == 1 and any(m.get("replay_id") == rid for m in rows[0]["matches"])
    assert not (await a.call(scoped(RED, "poll")))["deliveries"]
    await b.call(scoped(RED, "ack", delivery_ids=[rows[0]["id"]]))
    repeat = await page.context.request.post(f.base + "/admin/api", data=command,
        headers={"X-CSRF-Token": headers["x-csrf-token"], "Origin": f.base})
    repeated = await repeat.json()
    assert repeat.status == 200 and repeated == accepted, (repeat.status, repeated.get("error", {}).get("code"))
    await page.get_by_label("Replay ID", exact=True).fill(rid)
    await page.get_by_role("button", name="Refresh replay status", exact=True).click()
    await expect(page.get_by_text("Replay " + rid + " · materialized · 1 events", exact=True)).to_be_visible()
    await page.get_by_role("button", name="Refresh recovery audit", exact=True).click()
    await expect(page.get_by_text("Explicit browser replay " + name, exact=True)).to_be_visible()
    await capture(page, f.root, name + "-replay")
    # New explicit replay must append proof without resurrecting an old ack.
    await page.get_by_label("Replay reason", exact=True).fill("Repeat acknowledged history " + name)
    second, _, _ = await mutation(page, page.get_by_role("button", name="Confirm event replay", exact=True), "replay_events")
    await until(lambda: f.admin().call({"op": "eventing_replay", "project_id": RED,
        "replay_id": second["replay"]["id"]})["replay"]["status"] == "materialized", "Repeat replay stalled")
    assert not (await b.call(scoped(RED, "poll")))["deliveries"]
    for item in dummy:
        await a.call(scoped(RED, "unsubscribe", subscription_id=item["id"]))
    evidence.record(name + "-beyond-100-exact-target-real-kafka-replay-only-selected-recipient-idempotency-and-ack-preserved")
    return a, b, sub, publication


async def recovery(page, f, evidence, name, a, b):
    status = lambda: f.admin().call({"op": "eventing_status", "project_id": RED})
    state = status()
    async with httpx.AsyncClient(trust_env=False) as http:
        reply = await http.post(f.args.eventing_rest_url.rstrip("/") + "/topics/" + state["topic"],
            headers={"Content-Type": "application/vnd.kafka.json.v2+json", "Accept": "application/vnd.kafka.v2+json"},
            json={"records": [{"key": RED, "partition": 0, "value": {"foreign": "browser-poison-" + name}}]})
        reply.raise_for_status()
        offset = reply.json()["offsets"][0]["offset"]
    blocked = await until(lambda: (v if (v := status())["quarantined"] else None), "Real foreign row did not quarantine")
    digest = blocked["quarantines"][0]["digest"]
    assert blocked["quarantines"][0]["offset"] == offset
    await refresh(page)
    await expect(page.get_by_role("heading", name="Quarantined offset " + str(offset), exact=True)).to_be_visible()
    await page.get_by_label("Recovery reason", exact=True).fill("Browser retry foreign row " + name)
    retry, retry_command, _ = await mutation(page, page.get_by_role("button", name="Confirm event repair", exact=True), "repair_eventing")
    assert retry_command["expected_digest"] == digest and retry_command["action"] == "retry"
    again = await until(lambda: (v if (v := status())["quarantined"] else None), "Retry silently discarded poison")
    assert again["quarantines"][0]["digest"] == digest and retry["next_offset"] == blocked["next_offset"]
    original = (await a.call(scoped(RED, "publish", text="Accepted behind browser poison " + name)))["publication"]
    await refresh(page)
    await page.get_by_label("Recovery action", exact=True).select_option("reconcile")
    await page.get_by_label("Recovery reason", exact=True).fill("Browser reconcile foreign row " + name)
    accepted, command, headers = await mutation(page, page.get_by_role("button", name="Confirm event repair", exact=True), "repair_eventing")
    assert command["expected_digest"] == digest and command["offset"] == offset
    await until(lambda: status()["quarantined"] == 0, "Explicit reconcile failed to resume actual Kafka")
    deliveries = await poll_until(b, RED, {original["id"]}, f.args.deadline)
    assert all("browser-poison" not in json.dumps(d) for d in deliveries)
    await b.call(scoped(RED, "ack", delivery_ids=[d["id"] for d in deliveries]))
    repeat = await page.context.request.post(f.base + "/admin/api", data=command,
        headers={"X-CSRF-Token": headers["x-csrf-token"], "Origin": f.base})
    assert repeat.status == 200 and await repeat.json() == accepted
    await refresh(page)
    await page.get_by_role("button", name="Refresh recovery audit", exact=True).click()
    await expect(page.get_by_text("Browser reconcile foreign row " + name, exact=True)).to_be_visible()
    audit = f.admin().call({"op": "eventing_audit", "project_id": RED})
    assert any(i["reason"] == "Browser reconcile foreign row " + name and i["details"]["missing_logical_proof"] for i in audit["items"])
    assert not (await a.call(scoped(RED, "search", query="browser-poison-" + name)))["publications"]
    await capture(page, f.root, name + "-recovery")
    evidence.record(name + "-actual-foreign-kafka-row-retry-requarantine-audited-reconcile-and-original-drain")


async def epochs(page, f, evidence, name):
    delayed, release, delivered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def hold(route):
        body = route.request.post_data_json
        if body.get("op") == "eventing_audit" and body.get("project_id") == RED and not delayed.is_set():
            response = await route.fetch()
            delayed.set()
            await release.wait()
            await route.fulfill(response=response)
            delivered.set()
        else:
            await route.continue_()
    await page.route("**/admin/api", hold)
    await page.get_by_role("button", name="Refresh recovery audit", exact=True).click()
    await asyncio.wait_for(delayed.wait(), 10)
    await page.get_by_label("Project", exact=True).select_option(BLUE)
    await expect(page.get_by_text("No recovery actions recorded.", exact=True)).to_be_visible()
    release.set()
    await asyncio.wait_for(delivered.wait(), 10)
    await page.unroute("**/admin/api", hold)
    await asyncio.sleep(.15)
    await expect(page.get_by_text("Browser reconcile foreign row " + name, exact=True)).to_have_count(0)
    await expect(page.get_by_label("Recovery action", exact=True)).to_have_count(0)
    evidence.record(name + "-delayed-old-project-audit-cannot-render-controls-or-evidence-in-new-project")


async def viewport(browser, f, evidence, name, size, password, certificates):
    context = await browser.new_context(viewport=size)
    page = await context.new_page()
    errors, http_errors, expected_http = [], [], []
    instrument(page, errors, http_errors)
    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    try:
        await login(page, f.base, "admin", password)
        await ca_forms(page, f, evidence, name, expected_http, certificates)
        a, b, sub, publication = await replay(page, f, evidence, name)
        await recovery(page, f, evidence, name, a, b)
        await b.call(scoped(RED, "unsubscribe", subscription_id=sub["id"]))
        await epochs(page, f, evidence, name)
        username, user_password = "events-view-" + name, "Browser events viewer " + uuid4().hex
        await create_user(page, "Events Viewer " + name, "Viewer", BLUE, username, user_password)
        viewer_context = await browser.new_context(viewport=size)
        viewer = await viewer_context.new_page()
        instrument(viewer, errors, http_errors)
        await login(viewer, f.base, username, user_password)
        await expect(viewer.get_by_role("button", name="Events", exact=True)).to_have_count(0)
        # Revoke active admission outside this page; normal Refresh must update
        # the selector and navigate to Users without a routine403 flow.
        user = next(u for u in f.admin().call({"op": "users"})["users"] if u["username"] == username)
        f.admin().call({"op": "save_user", "user": {**{k: user[k] for k in ("id", "username", "name", "email", "role")},
            "project_ids": [], "disabled": False}}, mutation=True)
        await viewer.get_by_role("button", name="Refresh", exact=True).click()
        await expect(viewer.get_by_role("heading", name="Users", exact=True)).to_be_visible()
        await expect(viewer.get_by_text("No projects assigned. Ask an Admin for project access.", exact=True)).to_be_visible()
        assert not await viewer.get_by_label("Project", exact=True).locator("option").count()
        for op in ("eventing_status", "eventing_audit", "replay_events", "repair_eventing"):
            response = await viewer_context.request.post(f.base + "/admin/api", data={"op": op, "project_id": RED}, headers={"Origin": f.base})
            assert response.status in (401, 403)
        await capture(viewer, f.root, name + "-revoked-viewer")
        await viewer_context.close()
        evidence.record(name + "-viewer-controls-absent-direct-admin-denial-and-refresh-after-external-admission-revocation")
        expected_console = [e for e in errors if e.startswith("console: Failed to load resource:") and "400" in e]
        assert len(expected_console) <= len(expected_http)
        assert not [e for e in errors if e not in expected_console], errors
        assert sorted(http_errors) == sorted(expected_http), http_errors
        html = await page.content()
        assert all(token not in html for token in f.tokens.values())
        evidence.record(name + "-desktop-mobile-no-runtime-failures-unexpected-http-or-bearer-html-leaks")
    finally:
        await context.close()


async def main(args):
    if args.keep_work:
        args.keep_work = args.keep_work.resolve()
    f = Fixture(args)
    evidence = Evidence(args.report, "adhd/eventing-recovery-browser@1")
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence.value["limitations"].append("CA form tests validate certificate policy; HTTP broker fixture does not prove a TLS handshake.")
    if args.hub:
        evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest()
    try:
        await f.start()
        f.bind_evidence(evidence)
        password = re.search(r"^Password: (.+)$", (f.root / "initial-admin-password.txt").read_text(), re.M)[1]
        certificates = certs(f.root)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            for name, size in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
                await viewport(browser, f, evidence, name, size, password, certificates)
            await browser.close()
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        try:
            await f.close()
        except BaseException as exc:
            evidence.finish(exc)
            raise
        f.bind_evidence(evidence)
        evidence.write()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
