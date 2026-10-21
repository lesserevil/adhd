#!/usr/bin/env python3
"""Actual OpenRig CLI/daemon/tmux terminal seats driving ordinary ADHD A2A.

No provider process is launched. This proves deterministic infrastructure-seat
interoperability, not autonomous model behavior. Broker successes are real Kafka.
"""
import asyncio
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import secrets
import subprocess
import sys
import tarfile
import time
from uuid import uuid4

import httpx

from hub_acceptance import free_port
from multi_support import Fixture, PROJECTS, arguments, execute, scoped


REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "scripts/openrig_hub.py"
PIN = json.loads((Path(__file__).with_name("openrig_pin.json")).read_text())
RED, BLUE = "project-red", "project-blue"


def private(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


class Rigs:
    def __init__(self, root, executable):
        self.root = root / "rigs"
        self.root.mkdir(mode=0o700)
        self.home = self.root / "home"
        self.mux = self.root / "mux"
        self.home.mkdir(mode=0o700)
        self.mux.mkdir(mode=0o700)
        if len(str(self.mux / "tmux-999999/default")) >= 105:
            raise ValueError("Use a shorter --keep-work path for the real tmux Unix socket")
        self.cli = str(executable.resolve())
        self.port = free_port()
        self.env = {key: os.environ[key] for key in ("PATH", "HOME", "TERM", "LANG") if key in os.environ}
        self.env.update(OPENRIG_HOME=str(self.home), TMUX_TMPDIR=str(self.mux), TERM="xterm-256color")
        self.entries = []
        self.started = False
        self.sequence = 0

    def cli_call(self, *argv, check=True):
        value = subprocess.run([self.cli, *argv], env=self.env, cwd=self.root, capture_output=True, text=True, timeout=55)
        with (self.root / "cli.log").open("a") as log:
            log.write(json.dumps({"argv": argv, "code": value.returncode, "stdout": value.stdout, "stderr": value.stderr}) + "\n")
        if check:
            assert value.returncode == 0, "Actual OpenRig command failed; inspect private cli.log"
        return value

    def start_daemon(self):
        self.cli_call("daemon", "start", "--no-kernel", "--host", "127.0.0.1", "--port", str(self.port))
        self.started = True

    def inventory(self, name):
        return json.loads(self.cli_call("ps", "--nodes", "--rig", name, "--json").stdout)

    def launch(self):
        version = self.cli_call("--version").stdout.strip()
        assert version == PIN["version_output"], "Unqualified OpenRig version"
        self.start_daemon()
        for label in ("alpha", "beta"):
            name = "adhd-" + label + "-" + uuid4().hex[:8]
            spec = {"version": "0.2", "name": name, "pods": [{"id": "work", "label": "Work",
                "members": [{"id": "seat", "agent_ref": "builtin:terminal", "profile": "none", "runtime": "terminal",
                             "cwd": str(self.root)}], "edges": []}], "edges": []}
            path = private(self.root / (label + ".json"), spec)
            result = json.loads(self.cli_call("up", str(path), "--yes", "--json").stdout)
            assert result["status"] == "completed" and not result["errors"]
            rows = self.inventory(name)
            assert len(rows) == 1 and rows[0]["runtime"] == "terminal" and rows[0]["sessionStatus"] == "running"
            assert rows[0]["rigId"] == result["rigId"]
            self.entries.append(rows[0])
        return version

    def invoke(self, index, binding, command, mid=None, success=True):
        self.sequence += 1
        stem = self.root / ("invoke-" + str(self.sequence))
        inp = private(stem.with_suffix(".command.json"), command)
        out, err, done = [stem.with_suffix(suffix) for suffix in (".output", ".error", ".exit")]
        argv = [sys.executable, str(ADAPTER), "--binding", str(binding), "--command-file", str(inp)]
        if mid:
            argv += ["--message-id", mid]
        # Only nonsecret file paths occur in the shell command / pane history.
        shell = "umask 077; " + shlex.join(argv) + " >" + shlex.quote(str(out)) + " 2>" + shlex.quote(str(err))
        shell += "; code=$?; printf '%s' \"$code\" >" + shlex.quote(str(done))
        target = self.entries[index]["canonicalSessionName"]
        subprocess.run(["tmux", "send-keys", "-t", target, "-l", shell], env=self.env, check=True)
        subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], env=self.env, check=True)
        deadline = time.monotonic() + 45
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert done.exists(), "Actual seat did not complete adapter action"
        code = int(done.read_text())
        assert (code == 0) == success, "Adapter result differs from expectation; inspect private invoke files"
        if success:
            return json.loads(out.read_text())
        assert not out.read_text(), "A failed action emitted a success payload"
        assert json.loads(err.read_text())["error"] == "OPENRIG_HUB_FAILED"
        return None

    def close(self):
        if self.started:
            for entry in self.entries:
                self.cli_call("down", entry["rigName"], "--force", "--json", check=False)
            self.cli_call("daemon", "stop", check=False)
            subprocess.run(["tmux", "kill-server"], env=self.env, capture_output=True)


async def checks(f, evidence):
    rigs = Rigs(f.root, f.args.rig)
    bindings = []
    async def invoke(index, command, mid=None, success=True, binding=None):
        return await asyncio.to_thread(rigs.invoke, index, binding or bindings[index], command, mid, success)
    try:
        version = await asyncio.to_thread(rigs.launch)
        digest = hashlib.sha256(ADAPTER.read_bytes()).hexdigest()
        harness_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        evidence.value["adapter_sha256"] = digest
        evidence.value["harness_sha256"] = harness_digest
        evidence.value["openrig"] = {"version": version, "upstream_commit": PIN["commit"],
                                    "package_integrity": PIN["integrity"],
                                    "runtime": "terminal", "provider_processes_launched": 0}
        inspector = await f.agent("red-a")
        server = (await inspector.call(scoped(RED, "federation_directory")))["server_id"]
        for index, agent in enumerate(("red-a", "red-b")):
            bindings.append(private(rigs.root / (agent + ".binding.json"), {
                "url": f.base, "server_id": server, "project_id": RED,
                "agent_id": agent, "token": f.tokens[agent], "rig_id": rigs.entries[index]["rigId"],
                "seat_id": rigs.entries[index]["logicalId"]}))
        assert rigs.entries[0]["rigId"] != rigs.entries[1]["rigId"]
        for i in range(2):
            assert (await invoke(i, {"op": "whoami"}))["agent_id"] == ("red-a", "red-b")[i]
        evidence.record("two-actual-pinned-openrig-rigs-independent-a2a-credentials-and-terminal-panes")

        before = f.model.calls if f.model else 0
        sub = (await invoke(1, {"op": "subscribe", "mode": "raw"}, "rig-beta-raw-v1"))["subscription"]
        assert type(sub["revision"]) is int
        edited = (await invoke(1, {"op": "update_subscription", "subscription_id": sub["id"],
                                 "expected_revision": sub["revision"], "mode": "raw"}, "rig-beta-sub-edit-v1"))["subscription"]
        assert type(edited["revision"]) is int and edited["revision"] == sub["revision"] + 1
        command = {"op": "publish", "text": "Cross rig durable build status", "data": {"build": 42, "confidence": 1.0},
                   "source": {"item_id": "cross-rig-build-42-v1"}}
        result = await invoke(0, command, "cross-rig-build-42-v1")
        pub = result["publication"]
        assert pub["author_id"] == "red-a" and pub["project_id"] == RED
        expected = {"version": 1, "server_id": server, "project_id": RED, "rig_id": rigs.entries[0]["rigId"],
                    "seat_id": "work.seat", "agent_id": "red-a"}
        assert pub["data"] == {"openrig": expected, "payload": {"build": 42, "confidence": 1.0}}
        assert type(pub["data"]["payload"]["build"]) is int
        assert type(pub["data"]["payload"]["confidence"]) is float
        assert type(pub["data"]["openrig"]["version"]) is int
        canonical = json.dumps(["adhd-openrig-v1", server, RED, expected["rig_id"], "work.seat", "red-a"],
                               ensure_ascii=False, separators=(",", ":"))
        assert pub["source"]["id"] == "openrig-v1-" + hashlib.sha256(canonical.encode()).hexdigest()
        assert pub["source"]["kind"] == "openrig" and pub["source"]["item_id"] == "cross-rig-build-42-v1"
        deadline = time.monotonic() + f.args.deadline
        deliveries = []
        while time.monotonic() < deadline:
            deliveries = (await invoke(1, {"op": "poll"}))["deliveries"]
            if any(d.get("publication_id") == pub["id"] for d in deliveries):
                break
            await asyncio.sleep(.1)
        assert any(d.get("publication_id") == pub["id"] for d in deliveries)
        assert (f.model.calls if f.model else 0) == before
        assert (await invoke(1, {"op": "search", "source_kind": "openrig", "source_id": pub["source"]["id"]}))["publications"] == [pub]
        assert (await invoke(1, {"op": "get", "publication_id": pub["id"]}))["publication"] == pub
        evidence.record("cross-rig-raw-publication-source-provenance-zero-inference-and-backend-search")

        direct = (await invoke(0, {"op": "send", "recipient_id": "red-b", "text": "Private rig message"}, "rig-direct-v1"))["delivery"]
        assert direct["data"]["openrig"] == expected
        assert not (await invoke(1, {"op": "search", "query": "Private rig message"}))["publications"]
        queued = (await invoke(1, {"op": "poll"}))["deliveries"]
        assert any(d["id"] == direct["id"] for d in queued)
        await invoke(1, {"op": "ack", "delivery_ids": [d["id"] for d in queued]}, "rig-ack-v1")
        assert not (await invoke(1, {"op": "poll"}))["deliveries"]
        evidence.record("cross-rig-addressed-private-message-and-recipient-acknowledgements")

        await invoke(0, {"op": "search", "project_id": BLUE}, success=False)
        wrong = json.loads(bindings[0].read_text())
        for field, value in (("project_id", BLUE), ("server_id", "wrong-server"), ("agent_id", "red-b")):
            altered = private(rigs.root / (field + ".binding.json"), {**wrong, field: value})
            await invoke(0, {"op": "search", "query": "Must not run"}, success=False, binding=altered)
        for command_bad in ({"op": "publish", "text": "No item ID"},
                            {"op": "publish", "text": "Forged source", "source": {"kind": "agent", "item_id": "x"}}):
            await invoke(0, command_bad, "denied-v1", success=False)
        assert not (await invoke(0, {"op": "search", "query": "Forged source"}))["publications"]
        evidence.record("fixed-project-authorization-server-and-agent-binding-denials-without-access-grants")

        # Stop/restart the actual OpenRig daemon without replacing live panes.
        await asyncio.to_thread(rigs.cli_call, "daemon", "stop")
        await asyncio.to_thread(rigs.start_daemon)
        for i, entry in enumerate(rigs.entries):
            rows = await asyncio.to_thread(rigs.inventory, entry["rigName"])
            assert rows[0]["rigId"] == entry["rigId"] and rows[0]["canonicalSessionName"] == entry["canonicalSessionName"]
            assert (await invoke(i, {"op": "whoami"}))["agent_id"] == ("red-a", "red-b")[i]
        assert (await invoke(0, command, "cross-rig-build-42-v1"))["publication"] == pub
        assert not (await invoke(1, {"op": "poll"}))["deliveries"]
        evidence.record("actual-openrig-daemon-restart-preserves-seat-binding-source-retry-and-acknowledged-queue")

        if not f.args.rest_url:
            f.hard_stop()
            offline = {"op": "publish", "text": "Offline retained command", "source": {"item_id": "offline-retained-v1"}}
            await invoke(0, offline, "offline-retained-v1", success=False)
            await f.start()
            accepted = await invoke(0, offline, "offline-retained-v1")
            assert (await invoke(0, offline, "offline-retained-v1"))["publication"] == accepted["publication"]
            assert len((await invoke(1, {"op": "search", "query": "Offline retained command"}))["publications"]) == 1
            evidence.record("hub-offline-restart-identical-source-and-message-retry-without-duplicate-facts")
        if f.model:
            baseline = f.model.calls
            await invoke(1, {"op": "subscribe", "mode": "filtered", "filter": "Only build failures"}, "filtered-sub-v1")
            filtered = (await invoke(0, {"op": "publish", "text": "A build failed", "source": {"item_id": "failed-build-v1"}}, "failed-build-v1"))["publication"]
            deadline = time.monotonic() + f.args.deadline
            matches = []
            while time.monotonic() < deadline:
                matches = (await invoke(1, {"op": "poll"}))["deliveries"]
                if any(d.get("publication_id") == filtered["id"] and any(m.get("mode") == "filtered" for m in d.get("matches", [])) for d in matches):
                    break
                await asyncio.sleep(.1)
            assert f.model.calls > baseline
            assert any(d.get("publication_id") == filtered["id"] and any(m.get("mode") == "filtered" for m in d.get("matches", [])) for d in matches)
            evidence.record("optional-filtered-cross-rig-delivery-controlled-matcher-not-semantic-quality")
        if f.args.peer_eventing_rest_url:
            await federated(f, evidence, rigs, bindings, invoke)
        # Read the real terminal through the shipped CLI, not a fabricated pane.
        for entry in rigs.entries:
            capture = await asyncio.to_thread(rigs.cli_call, "capture", entry["canonicalSessionName"], "--lines", "100", "--json")
            assert "openrig_hub.py" in capture.stdout
            assert all(token not in capture.stdout for token in f.tokens.values())
        evidence.record("actual-openrig-cli-terminal-capture-has-adapter-path-without-bearer-secrets")
        assert hashlib.sha256(ADAPTER.read_bytes()).hexdigest() == digest
        assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == harness_digest
    finally:
        await asyncio.to_thread(rigs.close)


async def federated(f, evidence, rigs, bindings, invoke):
    args = copy.copy(f.args)
    args.keep_work = f.root / "peer"
    args.eventing_rest_url = args.peer_eventing_rest_url
    args.with_model = True
    peer = Fixture(args)
    try:
        # Require genuinely independent real brokers, not two aliases for one
        # service, before claiming per-server deployment interoperability.
        async with httpx.AsyncClient() as http:
            clusters = []
            for url in (f.args.eventing_rest_url, args.eventing_rest_url):
                response = await http.get(url.rstrip("/") + "/v3/clusters")
                response.raise_for_status()
                clusters.append(response.json()["data"][0]["cluster_id"])
            assert len(set(clusters)) == 2, "Federated hubs require distinct real Kafka clusters"
        await peer.start()
        peer.bind_evidence(evidence, "peer_runtime")
        pa = await peer.agent("red-b")
        sa = json.loads(bindings[0].read_text())["server_id"]
        sb = (await pa.call(scoped(RED, "federation_directory")))["server_id"]
        assert sa != sb and f.tokens["red-b"] != peer.tokens["red-b"]
        original = json.loads(bindings[1].read_text())
        remote_binding = private(rigs.root / "remote-red-b.binding.json", {
            **original, "url": peer.base, "server_id": sb, "token": peer.tokens["red-b"]})
        bindings[1] = remote_binding
        fact = (await invoke(1, {"op": "publish", "text": "Rig beta canonical build knowledge",
            "source": {"item_id": "beta-canonical-build-v1"}, "data": {"state": "passed"}},
            "beta-canonical-build-v1"))["publication"]
        assert fact["data"]["openrig"]["server_id"] == sb
        assert fact["data"]["openrig"]["rig_id"] == rigs.entries[1]["rigId"]
        a_to_b, b_to_a = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        scope = {"provider": "github", "host": "github.com", "tenant": "interop-fixture", "resource": "builds"}
        entry = {"scope": scope, "aliases": ["builds"], "description": "Rig beta canonical build knowledge",
                 "relationship": "contained", "canonical": True, "export_publication_ids": [fact["id"]]}
        def config(target, server_id, url, outbound, inbound):
            return {"description": "OpenRig interoperability scoped source exchange", "timeout_ms": 1000,
                    "retry_ms": 100, "catalog": {"visible": True, "entries": []},
                    "peers": [{"server_id": server_id, "url": url, "token": outbound, "inbound_token": inbound,
                               "project_pairs": [{"local_project_id": RED, "remote_project_id": RED}]}]}
        fa = config(f, sb, peer.base, a_to_b, b_to_a)
        fb = config(peer, sa, f.base, b_to_a, a_to_b)
        projects = copy.deepcopy(PROJECTS)
        projects[0]["settings"] = {"federation": {"catalog": {"visible": True, "entries": [entry]}}}
        f.admin().call({"op": "config_update", "patch": {"federation": fa}}, mutation=True)
        peer.admin().call({"op": "config_update", "patch": {"federation": fb, "projects": projects}}, mutation=True)
        deadline = time.monotonic() + f.args.deadline
        while time.monotonic() < deadline:
            directory = await invoke(0, {"op": "federation_directory"})
            if any(p["server_id"] == sb and p["project_id"] == RED and p["status"] == "ready"
                   and any(e["scope"] == scope for e in p["catalog"]) for p in directory["peers"]):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Actual peer canonical catalog was not observed")
        qcmd = {"op": "source_query", "sources": [scope], "question": "What is the canonical build knowledge?"}
        query = (await invoke(0, qcmd, "rig-canonical-query-v1"))["query"]
        deadline = time.monotonic() + f.args.deadline
        while time.monotonic() < deadline:
            result = (await invoke(0, {"op": "get_source_query", "query_id": query["id"]}))["query"]
            if result["status"] != "pending":
                break
            await asyncio.sleep(.1)
        assert result["status"] == "completed"
        answer = result["results"][0]
        assert answer["status"] == "answered" and answer["owner_server_id"] == sb and answer["owner_project_id"] == RED
        assert answer["response"]["server_id"] == sb and answer["response"]["project_id"] == RED
        assert answer["response"]["publications"] == [fact]
        assert (await invoke(0, qcmd, "rig-canonical-query-v1"))["query"] == query
        assert not (await invoke(0, {"op": "search", "query": "Rig beta canonical build knowledge"}))["publications"]
        assert peer.model.calls > 0
        evidence.record("two-rigs-separate-real-hubs-and-kafka-clusters-canonical-v2-routing-with-exact-source-provenance",
                        broker_cluster_ids=clusters)

        # Same rig/agent labels do not transfer an independently issued token or
        # grant Admin operations. No remote role is inferred from provenance.
        invalid = private(rigs.root / "foreign-token.binding.json", {
            **json.loads(remote_binding.read_text()), "token": f.tokens["red-b"]})
        await invoke(1, {"op": "whoami"}, success=False, binding=invalid)
        await invoke(1, {"op": "config_update", "patch": {"matcher": None}}, "forbidden-admin-v1", success=False)
        await invoke(1, {"op": "search", "project_id": BLUE}, success=False)
        evidence.record("federated-rigs-retain-local-authentication-and-project-admission-without-transferred-admin-roles")

        # Completed source evidence, source retry IDs and pending inboxes survive
        # the real remote hub restart; no local echo publication is introduced.
        peer.hard_stop()
        await invoke(1, {"op": "whoami"}, success=False)
        await peer.start()
        peer.bind_evidence(evidence, "peer_runtime")
        assert (await invoke(1, {"op": "get", "publication_id": fact["id"]}))["publication"] == fact
        assert (await invoke(1, {"op": "publish", "text": "Rig beta canonical build knowledge",
            "source": {"item_id": "beta-canonical-build-v1"}, "data": {"state": "passed"}},
            "beta-canonical-build-v1"))["publication"] == fact
        assert (await invoke(0, {"op": "get_source_query", "query_id": query["id"]}))["query"] == result
        assert not (await invoke(0, {"op": "search", "query": "Rig beta canonical build knowledge"}))["publications"]
        evidence.record("federated-rig-remote-offline-restart-preserves-source-identities-and-completed-evidence-without-echo")
    finally:
        await peer.close()


def main():
    parser = arguments(__doc__)
    parser.add_argument("--rig", type=Path, required=True, help="Explicit isolated @openrig/cli 0.6.14 executable")
    parser.add_argument("--peer-eventing-rest-url", help="Separate real Kafka cluster for optional two-hub federation")
    parser.add_argument("--openrig-tarball", type=Path, required=True,
                        help="Exact npm package archive; verifies the supported upstream integrity pin")
    args = parser.parse_args()
    if not args.keep_work:
        parser.error("--keep-work must explicitly place OpenRig state under an ignored _build directory")
    resolved = args.keep_work.resolve()
    if "_build" not in resolved.parts:
        parser.error("OpenRig test state must live beneath an ignored _build directory")
    args.keep_work = resolved
    if args.peer_eventing_rest_url and (args.rest_url or not args.with_model):
        parser.error("Federated fixture requires a locally owned --hub/--command and --with-model")
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(args.openrig_tarball.read_bytes()).digest()).decode()
    if integrity != PIN["integrity"]:
        parser.error("OpenRig npm package archive differs from the supported integrity pin")
    package = args.rig.resolve().parent.parent
    installed = json.loads((package / "package.json").read_text())
    if installed.get("name") != PIN["package"] or installed.get("version") != PIN["version"]:
        parser.error("--rig is not the supported installed npm package")
    # Verify the actual executed installation, not just a detached archive or a
    # version string. Never extract untrusted tar paths into the workspace.
    with tarfile.open(args.openrig_tarball, "r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if not parts or parts[0] != "package" or ".." in parts:
                parser.error("Unsupported package archive path")
            actual = package.joinpath(*parts[1:])
            if not actual.is_file() or actual.read_bytes() != archive.extractfile(member).read():
                parser.error("Installed OpenRig package differs from pinned archive: " + member.name)
    asyncio.run(execute(args, "openrig-a2a-terminal-seat-interop", checks))


if __name__ == "__main__":
    main()
