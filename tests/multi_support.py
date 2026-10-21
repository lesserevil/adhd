"""Independent public-interface fixture for project and Kafka acceptance.

No generated modules or internal store structures are imported. An external
server must use the separately supplied credential file; reports never copy it.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import tempfile
import time
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, create_client

from foundation_acceptance import Client
from hub_acceptance import Agent, ModelFixture, free_port


PROJECTS = [
    {"id": name, "name": "Shared project label", "description": "Acceptance isolation fixture",
     "status": "active", "settings": {}}
    for name in ("project-red", "project-blue", "project-hidden")
]
MEMBERSHIPS = {
    "red-a": ["project-red"], "red-b": ["project-red"],
    "blue-a": ["project-blue"], "blue-b": ["project-blue"],
    "bridge": ["project-red", "project-blue"], "hidden-a": ["project-hidden"],
}


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hub", type=Path, help="Generated standalone hub .exs")
    mode.add_argument("--command", help="JSON executable argv, before serve payload")
    mode.add_argument("--rest-url", help="An isolated already running hub's HTTP origin")
    parser.add_argument("--credentials", type=Path,
                        help="Private JSON {agents:{id:token}, admin:{username,password}, config_file?}")
    parser.add_argument("--eventing-rest-url", default="http://127.0.0.1:18082",
                        help="Real per-server Kafka REST bridge; never a broker success mock")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--keep-work", type=Path, help="Private persistent fixture directory")
    parser.add_argument("--deadline", type=float, default=20)
    parser.add_argument("--with-model", action="store_true", help="Controlled decision fault fixture")
    return parser


class Evidence:
    def __init__(self, path, suite):
        self.path = path
        self.value = {"suite": suite, "started_at": datetime.now(timezone.utc).isoformat(),
                      "passed": False, "checks": [], "limitations": [
                          "Controlled model responses prove transport/failure isolation, not semantic quality.",
                          "A single broker does not qualify replicated Kafka durability."]}

    def record(self, name, **details):
        self.value["checks"].append({"name": name, "passed": True, **details})
        self.write()

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.value, indent=2) + "\n")

    def finish(self, error=None):
        self.value["passed"] = error is None
        self.value["finished_at"] = datetime.now(timezone.utc).isoformat()
        if error is not None:
            # Exceptions may contain HTTP requests, so record only their type.
            self.value["failure_type"] = type(error).__name__
        self.write()


class Fixture:
    def __init__(self, args):
        self.args = args
        self.temp = None
        self.root = args.keep_work.resolve() if args.keep_work else None
        if self.root is None:
            self.temp = tempfile.TemporaryDirectory(prefix="adhd-multi-")
            self.root = Path(self.temp.name)
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.file = self.root / "hub.json"
        self.config_file = self.file
        self.process = None
        self.logs = []
        self.clients = []
        self.model = ModelFixture() if args.with_model else None
        self.admin_credentials = None
        if args.rest_url:
            if not args.credentials:
                raise ValueError("--rest-url requires a private --credentials file")
            cred = json.loads(args.credentials.read_text())
            self.base = args.rest_url.rstrip("/")
            self.tokens = cred["agents"]
            self.admin_credentials = cred.get("admin")
            self.config_file = Path(cred["config_file"]) if cred.get("config_file") else None
        else:
            self.tokens = {name: secrets.token_urlsafe(32) for name in MEMBERSHIPS}
            self.base = "http://127.0.0.1:" + str(free_port())
            self.config = {
                "project_id": "project-red", "projects": PROJECTS,
                "host": "127.0.0.1", "port": int(self.base.rsplit(":", 1)[1]),
                "store_path": str(self.root / "hub.dets"), "agents": self.tokens,
                "agent_projects": MEMBERSHIPS,
                "matcher": None if self.model is None else {
                    "url": self.model.url, "model": "Nemotron-Deciffusion-8B-v2.1",
                    "timeout_ms": 400, "retry_ms": 100},
                "eventing": {"enabled": True, "rest_url": args.eventing_rest_url,
                             "timeout_ms": 3000, "retry_ms": 100},
            }

    async def start(self):
        if not self.args.rest_url:
            if not self.file.exists():
                self.file.write_text(json.dumps(self.config))
                self.file.chmod(0o600)
            command = json.loads(self.args.command) if self.args.command else ["elixir", str(self.args.hub.resolve())]
            self.logs = [(self.root / name).open("ab") for name in ("stdout.log", "stderr.log")]
            self.process = subprocess.Popen(command + [json.dumps(["serve", str(self.file)])],
                                            stdout=self.logs[0], stderr=self.logs[1], start_new_session=True)
        deadline = time.monotonic() + 45
        async with httpx.AsyncClient() as http:
            while time.monotonic() < deadline:
                if self.process and self.process.poll() is not None:
                    raise AssertionError("Hub exited during startup; inspect private fixture logs")
                try:
                    response = await http.get(self.base + "/health", timeout=1)
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.1)
        raise AssertionError("Hub readiness deadline exceeded")

    async def agent(self, name):
        http = httpx.AsyncClient(headers={"Authorization": "Bearer " + self.tokens[name],
                                         "A2A-Version": "1.0"}, timeout=10)
        client = await create_client(agent=self.base, client_config=ClientConfig(
            streaming=False, httpx_client=http, supported_protocol_bindings=["JSONRPC"]))
        agent = Agent(client, http)
        self.clients.append(agent)
        return agent

    async def raw(self, name, command, mid=None):
        envelope = {"jsonrpc": "2.0", "id": uuid4().hex, "method": "SendMessage", "params": {
            "message": {"messageId": mid or uuid4().hex, "role": "ROLE_USER", "parts": [{"data": command}]}}}
        async with httpx.AsyncClient() as http:
            return await http.post(self.base + "/a2a", json=envelope, timeout=10,
                                   headers={"Authorization": "Bearer " + self.tokens[name], "A2A-Version": "1.0"})

    def admin(self):
        if self.admin_credentials:
            cred = self.admin_credentials
        else:
            text = (self.root / "initial-admin-password.txt").read_text()
            cred = {"username": "admin", "password": re.search(r"^Password: (.+)$", text, re.M)[1]}
        client = Client(self)
        client.login(cred["username"], cred["password"])
        return Admin(client, self)

    def hard_stop(self):
        if not self.process:
            raise ValueError("Process fault tests require a locally owned --hub or --command")
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=10)
        for log in self.logs:
            log.close()
        self.logs = []

    async def close(self):
        for client in self.clients:
            await client.close()
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.hard_stop()
        for log in self.logs:
            log.close()
        if self.model:
            self.model.close()
        if self.temp:
            self.temp.cleanup()


class Admin:
    def __init__(self, client, fixture, revision_source=None):
        self.client, self.fixture = client, fixture
        self.revision_source = revision_source or client

    def call(self, command, mutation=False, expected=200):
        if mutation:
            current = self.revision_source.api({"op": "config_get"})
            config = current["config"]
            revision = config.get("config_revision", current.get("config_revision", current.get("revision")))
            assert type(revision) is int, "config_get must report the current configuration revision"
            command = {**command, "expected_revision": revision, "confirm": True, "message_id": uuid4().hex}
        return self.client.api(command, expected=expected)


def scoped(project, op, **fields):
    return {"op": op, "project_id": project, **fields}


def reject(response, *, code=None):
    assert response.status_code in (200, 400, 401, 403, 404, 409), response.status_code
    value = response.json()
    assert "error" in value, "Unauthorized/invalid request succeeded"
    if code:
        metadata = value["error"].get("data", [])
        assert any(item.get("metadata", {}).get("code") == code for item in metadata), value["error"]
    return value["error"]


async def poll_until(agent, project, publications, deadline=20):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        deliveries = (await agent.call(scoped(project, "poll")))["deliveries"]
        if publications <= {d.get("publication_id") for d in deliveries}:
            return deliveries
        await asyncio.sleep(.1)
    raise AssertionError("Expected project deliveries did not arrive before deadline")


async def execute(args, suite, checks):
    evidence = Evidence(args.report, suite)
    fixture = Fixture(args)
    if args.hub:
        evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest()
    evidence.value["transport"] = "official-a2a-sdk-1.1.0-jsonrpc"
    try:
        await fixture.start()
        await checks(fixture, evidence)
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await fixture.close()
