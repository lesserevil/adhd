#!/usr/bin/env python3
"""Independent black-box hub acceptance using the official A2A SDK.

Run with the isolated test environment described in docs/user/getting-started.md.
This harness never imports generated hub code or reads its native test manifest.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ModelFixture:
    def __init__(self):
        self.mode = "match"
        self.calls = 0
        self.requests = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                data = json.dumps({'ready': fixture.mode != 'error'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.calls += 1
                fixture.requests.append(request)
                mode = fixture.mode
                if mode == "error":
                    self.send_response(503)
                    self.end_headers()
                    return
                if mode == "slow":
                    time.sleep(1)
                value = 0.99 if mode != "nonmatch" else 0.01
                if mode == "invalid":
                    value = 1.2
                response = {"model": request["model"], "answers": {
                    key: {"type": "noul", "noul": value}
                    for key in request["questions"]
                }}
                data = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except BrokenPipeError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/systemone"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class Hub:
    def __init__(self, command, root, matcher_url):
        self.command = command
        self.root = root
        self.root.mkdir(parents=True)
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.tokens = {name: secrets.token_urlsafe(32) for name in ("agent-a", "agent-b")}
        self.config = {
            "project_id": "acceptance-project", "host": "127.0.0.1", "port": self.port,
            "store_path": str(root / "hub.dets"), "agents": self.tokens,
            "threshold_ppm": 900000,
            "matcher": {"url": matcher_url, "model": "Nemotron-Deciffusion-8B-v2.1",
                        "timeout_ms": 2000, "retry_ms": 100},
        }
        self.config_file = root / "config.json"
        self.config_file.write_text(json.dumps(self.config))
        self.config_file.chmod(0o600)
        self.process = None
        self.logs = []

    def start(self):
        out = (self.root / "stdout.log").open("ab")
        err = (self.root / "stderr.log").open("ab")
        self.logs.extend((out, err))
        self.process = subprocess.Popen(
            self.command + [json.dumps(["serve", str(self.config_file)])],
            stdout=out, stderr=err, start_new_session=True,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                detail = (self.root / "stderr.log").read_text(errors="replace")[-4000:]
                for token in self.tokens.values():
                    detail = detail.replace(token, "<redacted>")
                raise AssertionError(f"Hub exited during startup: {detail}")
            try:
                response = httpx.get(self.base + "/health", timeout=1)
                if response.status_code == 200 and response.json() == {"status": "ready"}:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise AssertionError("Hub did not become ready")

    def stop(self, hard=False):
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL if hard else signal.SIGTERM)
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        for log in self.logs:
            log.close()
        self.logs.clear()

    async def agent(self, name):
        http = httpx.AsyncClient(headers={"Authorization": f"Bearer {self.tokens[name]}",
                                          "A2A-Version": "1.0"}, timeout=5)
        client = await create_client(agent=self.base, client_config=ClientConfig(
            streaming=False, httpx_client=http, supported_protocol_bindings=["JSONRPC"],
        ))
        return Agent(client, http)

    async def raw(self, name, command, message_id=None, **overrides):
        envelope = {"jsonrpc": "2.0", "id": str(uuid4()), "method": "SendMessage",
                    "params": {"message": {"messageId": message_id or str(uuid4()),
                        "role": "ROLE_USER", "parts": [{"data": command}]}}}
        envelope.update(overrides)
        async with httpx.AsyncClient() as http:
            return await http.post(self.base + "/a2a", json=envelope,
                headers={"Authorization": f"Bearer {self.tokens[name]}", "A2A-Version": "1.0"},
                timeout=5)


class Agent:
    def __init__(self, client, http):
        self.client, self.http = client, http

    async def call(self, command, message_id=None):
        message = new_text_message(json.dumps(command), role=Role.ROLE_USER)
        if message_id:
            message.message_id = message_id
        results = []
        async for event in self.client.send_message(SendMessageRequest(message=message)):
            document = MessageToDict(event)
            assert "message" in document, document
            parts = document["message"]["parts"]
            assert len(parts) == 1 and "data" in parts[0], document
            results.append(parts[0]["data"])
        assert len(results) == 1, results
        return results[0]

    async def close(self):
        await self.client.close()
        await self.http.aclose()


async def wait_deliveries(agent, predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        deliveries = (await agent.call({"op": "poll"}))["deliveries"]
        if predicate(deliveries):
            return deliveries
        await asyncio.sleep(0.1)
    raise AssertionError("Expected delivery did not arrive")


def domain_code(response):
    body = response.json()
    assert "error" in body, body
    return body["error"]["data"][0]["metadata"]["code"]


async def fixture_checks(command, root, record):
    fixture = ModelFixture()
    hub = Hub(command, root / "fixture", fixture.url)
    a = b = None
    try:
        hub.start()
        a, b = await hub.agent("agent-a"), await hub.agent("agent-b")
        assert (await a.call({"op": "whoami"}))["agent_id"] == "agent-a"
        assert (await b.call({"op": "whoami"}))["agent_id"] == "agent-b"
        record("official-sdk-agent-identity")

        response = httpx.post(hub.base + "/a2a", json={}, timeout=2)
        assert response.status_code == 401
        response = await hub.raw("agent-a", {"op": "whoami", "agent_id": "agent-b"})
        assert response.json()["error"]["code"] == -32602
        response = await hub.raw("agent-a", {"op": "whoami", "project_id": "foreign"})
        assert domain_code(response) == "PROJECT_MISMATCH"
        record("authentication-and-project-boundary")

        old = (await a.call({"op": "publish", "text": "Earlier information before subscription"}))["publication"]
        sub = (await b.call({"op": "subscribe", "description": "Information about project changes"}))["subscription"]
        duplicate = (await b.call({"op": "subscribe", "description": "Project work and progress"}))["subscription"]
        await asyncio.sleep(0.3)
        assert not (await b.call({"op": "poll"}))["deliveries"]
        assert (await b.call({"op": "search", "query": "earlier"}))["publications"][0]["id"] == old["id"]
        assert len((await b.call({"op": "list_subscriptions"}))["subscriptions"]) == 2
        assert not (await a.call({"op": "list_subscriptions"}))["subscriptions"]
        response = await hub.raw("agent-a", {"op": "unsubscribe", "subscription_id": sub["id"]})
        assert domain_code(response) == "FORBIDDEN"
        record("subscriptions-are-private-and-not-retroactive")

        mutation = {"op": "publish", "text": "A project schema change", "data": {"version": 2}}
        key = str(uuid4())
        published = await a.call(mutation, key)
        assert await a.call(dict(reversed(list(mutation.items()))), key) == published
        response = await hub.raw("agent-a", {"op": "publish", "text": "different"}, key)
        assert domain_code(response) == "IDEMPOTENCY_CONFLICT"
        deliveries = await wait_deliveries(b, lambda ds: len(ds) == 1 and len(ds[0].get("matches", [])) == 2)
        delivery = deliveries[0]
        assert delivery["publication_id"] == published["publication"]["id"]
        assert not (await a.call({"op": "poll"}))["deliveries"]
        assert (await b.call({"op": "poll"}))["deliveries"][0]["id"] == delivery["id"]
        record("idempotent-publish-and-per-recipient-deduplication")

        response = await hub.raw("agent-a", {"op": "ack", "delivery_ids": [delivery["id"]]})
        assert domain_code(response) == "FORBIDDEN"
        response = await hub.raw("agent-b", {"op": "ack", "delivery_ids": [delivery["id"], "missing-delivery"]})
        assert domain_code(response) == "NOT_FOUND"
        assert (await b.call({"op": "poll"}))["deliveries"][0]["id"] == delivery["id"]
        record("ack-ownership-and-batch-atomicity")

        hub.stop(hard=True)
        hub.start()
        assert (await b.call({"op": "poll"}))["deliveries"][0] == delivery
        assert await a.call(mutation, key) == published
        await b.call({"op": "ack", "delivery_ids": [delivery["id"]]})
        await b.call({"op": "ack", "delivery_ids": [delivery["id"]]})
        hub.stop(hard=True)
        hub.start()
        assert not (await b.call({"op": "poll"}))["deliveries"]
        record("hard-restart-preserves-delivery-idempotency-and-ack")

        direct_key = str(uuid4())
        direct = {"op": "send", "recipient_id": "agent-a", "text": "private coordination note"}
        sent = await b.call(direct, direct_key)
        assert await b.call(direct, direct_key) == sent
        assert (await a.call({"op": "poll"}))["deliveries"][0]["kind"] == "message"
        assert not (await a.call({"op": "search", "query": "private coordination note"}))["publications"]
        assert not (await b.call({"op": "poll"}))["deliveries"]
        record("addressed-message-privacy-and-idempotency")

        fixture.mode = "nonmatch"
        await a.call({"op": "publish", "text": "Unrelated update"})
        before = fixture.calls
        deadline = time.monotonic() + 5
        while fixture.calls < before + 1 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.4)
        assert not (await b.call({"op": "poll"}))["deliveries"]
        record("nonmatch-does-not-deliver")

        fixture.mode = "slow"
        slow_pub = (await a.call({"op": "publish", "text": "Update while inference is slow"}))["publication"]
        await asyncio.sleep(0.2)
        started = time.monotonic()
        await b.call({"op": "poll"})
        await a.call({"op": "search", "query": "inference is slow"})
        assert time.monotonic() - started < 0.8
        slow_deliveries = await wait_deliveries(b, lambda ds: any(d.get("publication_id") == slow_pub["id"] for d in ds))
        slow_item = next(d for d in slow_deliveries if d.get("publication_id") == slow_pub["id"])
        await b.call({"op": "ack", "delivery_ids": [slow_item["id"]]})
        await asyncio.sleep(2.2)
        assert not (await b.call({"op": "poll"}))["deliveries"]
        record("slow-inference-does-not-block-or-resurrect-acked-delivery")

        fixture.mode = "invalid"
        pending = (await a.call({"op": "publish", "text": "Pending while model output is invalid"}))["publication"]
        await asyncio.sleep(0.5)
        assert not (await b.call({"op": "poll"}))["deliveries"]
        fixture.mode = "error"
        hub.stop(hard=True)
        hub.start()
        started = time.monotonic()
        assert (await b.call({"op": "search", "query": "pending while"}))["publications"]
        assert not (await b.call({"op": "poll"}))["deliveries"]
        assert time.monotonic() - started < 2
        fixture.mode = "match"
        recovered = await wait_deliveries(b, lambda ds: any(d.get("publication_id") == pending["id"] for d in ds))
        assert sum(d.get("publication_id") == pending["id"] for d in recovered) == 1
        record("invalid-model-and-outage-recover-durably")

        await b.call({"op": "unsubscribe", "subscription_id": duplicate["id"]})
        assert len((await b.call({"op": "list_subscriptions"}))["subscriptions"]) == 1
        record("unsubscribe")

        async with httpx.AsyncClient() as http:
            response = await http.post(hub.base + "/a2a", content=b"{", headers={
                "Authorization": "Bearer " + hub.tokens["agent-a"], "Content-Type": "application/json"})
            assert response.json()["error"]["code"] == -32700
            response = await hub.raw("agent-a", {"op": "whoami"}, method="UnknownMethod")
            assert response.json()["error"]["code"] == -32601
            assert (await http.get(hub.base + "/health")).status_code == 200
        record("protocol-errors-leave-listener-alive")

        for header, expected_status in [
            (b"Content-Length: 0\r\nContent-Length: 0\r\n", b"400"),
            (b"Transfer-Encoding: chunked\r\n", b"400"),
            (b"Content-Length: 1048577\r\n", b"413"),
        ]:
            with socket.create_connection(("127.0.0.1", hub.port), timeout=3) as sock:
                sock.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n" + header + b"\r\n")
                assert sock.recv(4096).split(b" ", 2)[1] == expected_status
        assert httpx.get(hub.base + "/health", timeout=2).status_code == 200
        record("bounded-http-framing")
        state = (root / "fixture" / "hub.dets").read_bytes()
        assert all(token.encode() not in state for token in hub.tokens.values())
        record("no-bearer-tokens-in-product-store")

        corrupt = Hub(command, root / "corrupt", fixture.url)
        (corrupt.root / "hub.dets").write_bytes(b"not a valid persisted hub store\n")
        try:
            try:
                corrupt.start()
            except AssertionError:
                assert corrupt.process is not None and corrupt.process.poll() is not None
            else:
                raise AssertionError("Corrupt state was accepted as a fresh empty store")
        finally:
            corrupt.stop()
        record("corrupt-store-is-not-silently-reset")
    finally:
        if a:
            await a.close()
        if b:
            await b.close()
        hub.stop()
        fixture.close()


async def live_checks(command, root, matcher_url, record):
    hub = Hub(command, root / "live", matcher_url)
    a = b = None
    try:
        hub.start()
        a, b = await hub.agent("agent-a"), await hub.agent("agent-b")
        await b.call({"op": "subscribe", "description": "API request or response schema changes that require client code updates."})
        await a.call({"op": "subscribe", "description": "Client integration problems and requests for backend API changes."})
        pub = (await a.call({"op": "publish", "text": "I am changing the task API response to include a required status field. The client decoder must handle it."}))["publication"]
        received = await wait_deliveries(b, lambda ds: any(d.get("publication_id") == pub["id"] for d in ds), timeout=30)
        item = next(d for d in received if d.get("publication_id") == pub["id"])
        assert item["matches"][0]["model"] == "Nemotron-Deciffusion-8B-v2.1"
        await b.call({"op": "ack", "delivery_ids": [item["id"]]})
        unrelated = (await a.call({"op": "publish", "text": "The cafeteria lunch menu now includes tomato soup and fresh bread."}))["publication"]
        await asyncio.sleep(2)
        assert not any(d.get("publication_id") == unrelated["id"]
                       for d in (await b.call({"op": "poll"}))["deliveries"])
        response = (await b.call({"op": "publish", "text": "Client integration is blocked: please keep the old API status field optional until the client decoder is updated."}))["publication"]
        await wait_deliveries(a, lambda ds: any(d.get("publication_id") == response["id"] for d in ds), timeout=30)
        await b.call({"op": "send", "recipient_id": "agent-a", "text": "I am updating the client decoder now."})
        await wait_deliveries(a, lambda ds: any(d["kind"] == "message" for d in ds))
        assert (await a.call({"op": "search", "query": "client decoder"}))["publications"]
        record("live-nemotron-two-agent-coordination")
        return {"delivered_probability_ppm": item["matches"][0]["probability_ppm"],
                "threshold_ppm": 900000, "unrelated_publication_delivered": False}
    finally:
        if a:
            await a.close()
        if b:
            await b.close()
        hub.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", required=True, help="JSON argv for the built hub, excluding its JSON argument")
    parser.add_argument("--work-dir", default="_build/tests/hub001")
    parser.add_argument("--matcher-url", required=True, help="Reachable live Nemotron SystemOne URL")
    parser.add_argument("--report", default="verification/hub-acceptance.json")
    parser.add_argument("--legacy-command", help="Optional JSON argv for the original prototype, for store-upgrade verification")
    parser.add_argument("--previous-command", help="JSON argv for the schema-2 pre-console runtime")
    args = parser.parse_args()
    command = json.loads(args.command)
    assert isinstance(command, list) and command and all(isinstance(s, str) for s in command)
    parent = Path(args.work_dir).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    passed = []

    def record(name):
        passed.append({"case": name, "passed": True})
        print("PASS", name, flush=True)

    async def run():
        from information_cases import information_checks, legacy_upgrade_checks
        await fixture_checks(command, root, record)
        await information_checks(command, root, record)
        from admin_cases import admin_checks
        await admin_checks(command, root, record)
        if args.legacy_command:
            await legacy_upgrade_checks(json.loads(args.legacy_command), command, root, record)
        if args.previous_command:
            from upgrade_cases import schema_two_upgrade_checks
            await schema_two_upgrade_checks(json.loads(args.previous_command), command, root, record)
        return await live_checks(command, root, args.matcher_url, record)

    live = asyncio.run(run())
    artifact = next((Path(s) for s in command[1:] if Path(s).is_file()), None)
    report = {"schema": "adhd/hub-acceptance@1", "passed": True,
              "sdk_version": version("a2a-sdk"), "protocol_version": "1.0", "cases": passed,
              "live_model": live, "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact else None}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print("Acceptance report:", args.report, flush=True)


if __name__ == "__main__":
    main()
