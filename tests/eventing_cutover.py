#!/usr/bin/env python3
"""Hot transport cutover against real Kafka, including failed destination apply.

The forwarding gateway only injects transport failures. All successful broker
responses, records and offsets come from the supplied real Kafka REST service.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import time
from uuid import uuid4

from eventing_faults import LostReplyGateway
from multi_support import Evidence, Fixture, arguments, poll_until, scoped
from multi_migration import source_identities


async def interrupted_update(fixture, local, args, admin, command, prefix, evidence):
    """Observe a real durable decision, stop its writer, then SIGKILL it."""
    sentinel = fixture.root / "transition-fault.json"
    update = asyncio.create_task(asyncio.to_thread(admin.call, command, mutation=True))
    try:
        end = time.monotonic() + 30
        while time.monotonic() < end:
            if sentinel.exists():
                break
            if update.done():
                await update
                raise AssertionError("Hot transition completed without reaching requested real filesystem boundary")
            await asyncio.sleep(.01)
        else:
            raise AssertionError("Hot transition never reached requested filesystem boundary")
        trace = json.loads(sentinel.read_text())
        assert trace["stage"] == args.crash_at and trace["pid"] == fixture.process.pid
        end = time.monotonic() + 2
        while time.monotonic() < end:
            state = Path("/proc/" + str(trace["pid"]) + "/status").read_text()
            if re.search(r"^State:\s+T\b", state, re.M):
                break
            await asyncio.sleep(.01)
        else:
            raise AssertionError("Actual hot-transition writer was not stopped")
        decision = json.loads(Path(str(fixture.file) + ".transaction").read_text())
        assert decision["config"]["eventing"]["topic_prefix"] == prefix
        identity = decision["eventing_transition"]["id"]
        assert isinstance(identity, str) and identity
        installed = json.loads(fixture.file.read_text())["eventing"]["topic_prefix"] == prefix
        assert installed == (args.crash_at == "transition-project")
        fixture.hard_stop()
        assert fixture.process.returncode == -signal.SIGKILL
        try:
            await update
        except (AssertionError, OSError):
            pass
        else:
            raise AssertionError("Interrupted hot transition incorrectly returned a successful response")
        fixture.args = local
        fixture.admin_client = None
        await fixture.start()
        assert not Path(str(fixture.file) + ".transaction").exists()
        recovered = fixture.admin().call({"op": "config_get"})["config"]
        assert recovered["eventing"]["topic_prefix"] == prefix
        evidence.record("actual-hot-transition-kill-recovers-durable-config-decision-before-readiness",
                        stage=args.crash_at, transition_id=identity,
                        kernel_state_before_kill="stopped", signal="SIGKILL")
    finally:
        if not update.done():
            if fixture.process and fixture.process.poll() is None:
                fixture.hard_stop()
            try:
                await update
            except (AssertionError, OSError):
                pass


async def main(args):
    if args.rest_url:
        raise ValueError("Cutover faults require an owned disposable hub")
    gateway = LostReplyGateway(args.eventing_rest_url)
    local = copy.copy(args)
    local.eventing_rest_url = gateway.url
    fixture = Fixture(local)
    evidence = Evidence(args.report, "adhd/real-kafka-hot-cutover@1")
    evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest() if args.hub else None
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence.value["source_sha256"] = source_identities(args.hub) if args.hub else None
    if args.crash_at:
        if not args.hub:
            raise ValueError("Exact filesystem crash qualification requires --hub")
        source = Path(__file__).with_name("multi_fault.c")
        library = fixture.root / "transition-fault.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", "-O2",
                        "-o", str(library), str(source), "-ldl"], check=True)
        wrapped = copy.copy(local)
        wrapped.hub = None
        wrapped.command = json.dumps(["env", "LD_PRELOAD=" + str(library), "ADHD_CRASH_STAGE=" + args.crash_at,
            "ADHD_CRASH_CONFIG=" + str(fixture.file), "ADHD_CRASH_STORE=" + fixture.config["store_path"],
            "ADHD_CRASH_SENTINEL=" + str(fixture.root / "transition-fault.json"), "elixir", str(args.hub)])
        fixture.args = wrapped
        evidence.value["fault_source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        evidence.value["fault_library_sha256"] = hashlib.sha256(library.read_bytes()).hexdigest()
    try:
        await fixture.start()
        admin = fixture.admin()
        contexts = []
        for project, publisher, subscriber in (("project-red", "red-a", "red-b"),
                                              ("project-blue", "blue-a", "blue-b"),
                                              ("project-hidden", "hidden-a", "hidden-a")):
            a, b = await fixture.agent(publisher), await fixture.agent(subscriber)
            await b.call(scoped(project, "subscribe", mode="raw"))
            command = scoped(project, "publish", text="Before transport cutover " + project,
                source={"kind": "slack", "id": "same-channel", "item_id": "same-original"})
            mid = "same-original-message-id"
            result = await a.call(command, mid)
            original = result["publication"]
            deliveries = await poll_until(b, project, {original["id"]}, args.deadline)
            await b.call(scoped(project, "ack", delivery_ids=[d["id"] for d in deliveries]))
            contexts.append({"project": project, "a": a, "b": b, "original": original,
                             "original_result": result, "command": command, "message_id": mid})
        evidence.record("three-real-project-streams-materialized-and-acknowledged-before-transition")
        before = admin.call({"op": "config_get"})["config"]
        unavailable = "http://127.0.0.1:1"
        # A refused destination must not become the authoritative config.
        admin.call({"op": "config_update", "patch": {"eventing": {"rest_url": unavailable}}},
                   mutation=True, expected=409)
        after = admin.call({"op": "config_get"})["config"]
        assert after["eventing"]["rest_url"] == before["eventing"]["rest_url"]
        assert after["config_revision"] == before["config_revision"]
        for row in contexts:
            assert not (await row["b"].call(scoped(row["project"], "poll")))["deliveries"]
        evidence.record("failed-preflight-retains-config-revision-checkpoint-and-acknowledgements")

        gateway.blocked = True
        for row in contexts:
            row["pending"] = (await row["a"].call(scoped(row["project"], "publish", text="Accepted during old broker outage " + row["project"],
                source={"kind": "slack", "id": "same-channel", "item_id": "same-pending"})))["publication"]
        await asyncio.sleep(.5)
        for row in contexts:
            assert not (await row["b"].call(scoped(row["project"], "poll")))["deliveries"]
        old_pid = fixture.process.pid
        prefix = "cutover" + uuid4().hex[:12]
        command = {"op": "config_update", "patch": {"eventing": {
            "rest_url": args.eventing_rest_url, "topic_prefix": prefix}}}
        if args.crash_at:
            await interrupted_update(fixture, local, args, admin, command, prefix, evidence)
            admin = fixture.admin()
        else:
            admin.call(command, mutation=True)
            assert fixture.process.pid == old_pid and fixture.process.poll() is None
        for row in contexts:
            project, a, b, pending, original = (row[key] for key in ("project", "a", "b", "pending", "original"))
            rows = await poll_until(b, project, {pending["id"]}, args.deadline)
            assert [d["publication_id"] for d in rows] == [pending["id"]]
            assert (await b.call(scoped(project, "get", publication_id=original["id"])))["publication"] == original
            assert await a.call(row["command"], row["message_id"]) == row["original_result"]
            status = admin.call(scoped(project, "eventing_status"))
            status = status.get("eventing", status)
            assert status["topic"].startswith(prefix + ".")
            assert status["gap"]["reason"] == "TRANSPORT_CUTOVER" and status["gap"]["status"] == "reconciled"
            assert pending["id"] in status["gap"]["missing_event_ids"]
            assert original["id"] not in status["gap"]["missing_event_ids"]
            row["gap"] = status["gap"]
            row["delivery_ids"] = [d["id"] for d in rows]
        evidence.record("all-three-projects-reconstruct-only-pending-events-preserving-source-retries-originals-and-acks")
        fixture.hard_stop()
        fixture.args = local
        fixture.admin_client = None
        await fixture.start()
        admin = fixture.admin()
        for row in contexts:
            project, a, b, pending = (row[key] for key in ("project", "a", "b", "pending"))
            again = await poll_until(b, project, {pending["id"]}, args.deadline)
            assert [d["id"] for d in again] == row["delivery_ids"]
            status = admin.call(scoped(project, "eventing_status"))
            status = status.get("eventing", status)
            assert status["gap"] == row["gap"], "Recovery reapplied or replaced the completed transition"
            await b.call(scoped(project, "ack", delivery_ids=row["delivery_ids"]))
            newer = (await a.call(scoped(project, "publish", text="After hot transport cutover " + project)))["publication"]
            rows = await poll_until(b, project, {newer["id"]}, args.deadline)
            assert [d["publication_id"] for d in rows] == [newer["id"]]
        assert fixture.model is None or fixture.model.calls == 0
        evidence.record("restart-preserves-cutover-state-and-delivery-identities-with-zero-inference")
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await fixture.close()
        fixture.bind_evidence(evidence)
        evidence.write()
        gateway.close()


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--crash-at", choices=("transition-decision", "transition-project"))
    asyncio.run(main(parser.parse_args()))
