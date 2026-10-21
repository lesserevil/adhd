#!/usr/bin/env python3
"""Real legacy producer -> multi-project/Kafka migration across process kills.

Requires the actual previous qualified hub, not manually synthesized store data.
The old runtime creates credentials, originals, semantic jobs, delivery IDs and
acknowledgements through A2A; the candidate opens the same configuration/store.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4

from multi_support import Evidence, Fixture, arguments, poll_until, scoped


P = "project-red"


def source_identities(artifact):
    body = artifact.read_bytes()
    rows = {}
    for module in ("Migration", "Config", "Storage", "Store", "CLI"):
        match = re.search(rb"(?m)^defmodule ADHD\." + module.encode() + rb" do\n", body)
        assert match is not None, "Qualified artifact lacks migration authority module " + module
        following = re.search(rb"(?m)^defmodule ", body[match.end():])
        end = match.end() + following.start() if following else len(body)
        rows[module] = hashlib.sha256(body[match.start():end]).hexdigest()
    return rows


async def interrupt_upgrade(f, args, evidence):
    """Stop a real rename at an exact boundary, observe kernel stop, then kill."""
    assert sys.platform == "linux", "Precise filesystem crash fixture requires Linux"
    fixture_source = Path(__file__).with_name("multi_fault.c")
    library = f.root / "migration-fault.so"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", "-O2",
                    "-o", str(library), str(fixture_source), "-ldl"], check=True)
    sentinel = f.root / "migration-fault.json"
    assert not sentinel.exists(), "Crash fixture directory must be fresh"
    seed = json.loads(f.file.read_text())
    store = Path(seed["store_path"])
    sources = [f.file, Path(str(f.file) + ".journal"), store, Path(str(store) + ".snapshot")]
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources if path.exists()}
    injected = copy.copy(args)
    injected.hub = None
    injected.command = json.dumps(["env", "LD_PRELOAD=" + str(library),
        "ADHD_CRASH_STAGE=" + args.crash_at, "ADHD_CRASH_CONFIG=" + str(f.file),
        "ADHD_CRASH_STORE=" + str(store), "ADHD_CRASH_SENTINEL=" + str(sentinel), "elixir", str(args.hub)])
    f.args = injected
    startup = asyncio.create_task(f.start())
    try:
        end = time.monotonic() + 55
        while time.monotonic() < end:
            if sentinel.exists():
                break
            if startup.done():
                await startup
                raise AssertionError("Hub became ready without reaching the requested migration crash boundary")
            await asyncio.sleep(.02)
        else:
            raise AssertionError("Migration never reached the requested real filesystem boundary")
        trace = json.loads(sentinel.read_text())
        assert trace["stage"] == args.crash_at and trace["pid"] == f.process.pid
        end = time.monotonic() + 2
        while time.monotonic() < end:
            state = Path("/proc/" + str(trace["pid"]) + "/status").read_text()
            if re.search(r"^State:\s+T\b", state, re.M):
                break
            await asyncio.sleep(.01)
        else:
            raise AssertionError("Requested crash boundary did not stop the actual runtime process")
        f.hard_stop()
        assert f.process.returncode == -signal.SIGKILL
        try:
            await startup
        except AssertionError:
            pass
        else:
            raise AssertionError("Interrupted startup was incorrectly reported as successful")
        marker_path = Path(str(f.file) + ".project-upgrade")
        expected = {"before-prepared": None, "before-decided": "prepared", "before-config": "decided",
                    "after-snapshot": "decided", "before-completed": "decided"}[args.crash_at]
        marker = json.loads(marker_path.read_text()) if marker_path.exists() else None
        assert (marker["phase"] if marker else None) == expected
        for source, digest in originals.items():
            backup = Path(str(source) + ".before-projects")
            assert backup.is_file() and hashlib.sha256(backup.read_bytes()).hexdigest() == digest
        current = json.loads(f.file.read_text())
        assert isinstance(current.get("projects"), list) == (args.crash_at in ("after-snapshot", "before-completed"))
        evidence.record("actual-runtime-killed-at-observed-durable-migration-boundary",
                        stage=args.crash_at, marker_phase=expected, signal="SIGKILL",
                        kernel_state_before_kill="stopped",
                        preserved_backup_sha256={path.name: digest for path, digest in originals.items()},
                        fault_source_sha256=hashlib.sha256(fixture_source.read_bytes()).hexdigest(),
                        fault_library_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    finally:
        if not startup.done():
            if f.process and f.process.poll() is None:
                f.hard_stop()
            try:
                await startup
            except AssertionError:
                pass
        f.args = args


async def damaged_backup_refusal(f, args, evidence):
    """Corrupt a real prepared backup and require refusal before service opens."""
    config = json.loads(f.file.read_text())
    base = f.file if args.damage_backup == "config" else Path(config["store_path"])
    if args.damage_backup == "snapshot":
        base = Path(str(base) + ".snapshot")
    backup = Path(str(base) + ".before-projects")
    original = backup.read_bytes()
    damaged = b"Deliberately damaged migration backup\n"
    backup.write_bytes(damaged)
    refused = False
    try:
        try:
            await f.start()
        except AssertionError:
            assert f.process is not None and f.process.poll() is not None, "A timeout is not fail-closed startup refusal"
            refused = True
        assert refused, "A migration with a damaged prepared backup became publicly ready"
        evidence.record("damaged-prepared-backup-refused-before-public-readiness", backup=args.damage_backup,
                        original_sha256=hashlib.sha256(original).hexdigest(),
                        damaged_sha256=hashlib.sha256(damaged).hexdigest())
    finally:
        if f.process is not None and f.process.poll() is None:
            f.hard_stop()
        backup.write_bytes(original)
        backup.chmod(0o600)


async def main(args):
    if not args.with_model:
        raise ValueError("Legacy semantic migration requires --with-model for its controlled decision fixture")
    if not args.hub:
        raise ValueError("Migration requires locally owned --hub and --legacy-hub")
    current = args.hub
    legacy_args = copy.copy(args)
    legacy_args.hub = args.legacy_hub
    f = Fixture(legacy_args)
    evidence = Evidence(args.report, "adhd/multi-eventing-migration@1")
    evidence.value["artifact_sha256"] = hashlib.sha256(current.read_bytes()).hexdigest()
    evidence.value["legacy_artifact_sha256"] = hashlib.sha256(args.legacy_hub.read_bytes()).hexdigest()
    evidence.value["migration_source_sha256"] = source_identities(current)
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    # The producer starts with the previous format, never a new registry seeded
    # into an old binary. All its agents belong to the migrated default project.
    f.config.pop("projects")
    f.config.pop("agent_projects")
    f.config.pop("eventing")
    try:
        await f.start()
        a, b = await f.agent("red-a"), await f.agent("red-b")
        legacy_server_id = (await a.call({"op": "federation_directory"}))["server_id"]
        source = {"kind": "slack", "id": "legacy-channel", "item_id": "legacy-original"}
        command = {"op": "publish", "text": "Immutable legacy original with provenance", "source": source}
        retry_id = uuid4().hex
        original_result = await a.call(command, retry_id)
        original = original_result["publication"]
        old_sub = (await b.call({"op": "subscribe", "description": "Legacy API release changes"}))["subscription"]
        acknowledged = (await a.call({"op": "publish", "text": "Acknowledged before migration"}))["publication"]
        rows = await poll_until(b, P, {acknowledged["id"]}, args.deadline)
        ack_id = next(d["id"] for d in rows if d.get("publication_id") == acknowledged["id"])
        await b.call({"op": "ack", "delivery_ids": [ack_id]})
        pending_delivery = (await a.call({"op": "send", "recipient_id": "red-b", "text": "Durable private migration note"}))["delivery"]
        f.model.mode = "error"
        pending_model = (await a.call({"op": "publish", "text": "Pending legacy semantic decision"}))["publication"]
        # Ensure actual attempts happened before killing, rather than inferring
        # a pending job from an empty delivery poll immediately after publish.
        count = f.model.calls
        deadline = time.monotonic() + args.deadline
        while f.model.calls <= count and time.monotonic() < deadline:
            await asyncio.sleep(.1)
        assert f.model.calls > count
        evidence.record("actual-legacy-runtime-authored-originals-source-retries-acks-and-pending-work")

        f.hard_stop()
        f.args = args
        if args.crash_at:
            await interrupt_upgrade(f, args, evidence)
        if args.damage_backup:
            assert args.crash_at, "Backup damage test requires an actual interrupted migration"
            await damaged_backup_refusal(f, args, evidence)
        # The candidate must migrate the persisted old configuration itself.
        # Kafka is enabled after that migration through the supported hot API.
        await f.start()
        assert f.admin().call({"op": "config_get"})["config"]["server_id"] == legacy_server_id
        assert await a.call(command, retry_id) == original_result
        assert (await a.call(scoped(P, "get", publication_id=original["id"])))["publication"] == original
        assert (await a.call(scoped(P, "search", query="Immutable legacy original")))["publications"] == [original]
        subscriptions = (await b.call(scoped(P, "list_subscriptions")))["subscriptions"]
        sub = next(s for s in subscriptions if s["id"] == old_sub["id"])
        assert sub["mode"] == "filtered", "Migration silently broadened a legacy semantic subscription"
        assert sub["revision"] == 1
        rows = (await b.call(scoped(P, "poll")))["deliveries"]
        assert any(d["id"] == pending_delivery["id"] for d in rows)
        assert not any(d["id"] == ack_id for d in rows)
        assert not any(d.get("publication_id") == pending_model["id"] for d in rows)
        evidence.record("upgrade-preserves-credentials-originals-source-identities-private-deliveries-acks-and-filter-mode")

        admin = f.admin()
        admin.call({"op": "config_update", "patch": {"eventing": {
            "enabled": True, "rest_url": args.eventing_rest_url, "timeout_ms": 3000, "retry_ms": 100}}}, mutation=True)
        raw = await f.agent("bridge")
        await raw.call(scoped(P, "subscribe", mode="raw"))
        assert not (await raw.call(scoped(P, "poll")))["deliveries"]
        new = (await a.call(scoped(P, "publish", text="New Kafka event after migration cutover")))["publication"]
        raw_rows = await poll_until(raw, P, {new["id"]}, args.deadline)
        assert {d["publication_id"] for d in raw_rows} == {new["id"]}
        f.model.mode = "match"
        rows = await poll_until(b, P, {pending_model["id"], new["id"]}, args.deadline)
        assert sum(d.get("publication_id") == pending_model["id"] for d in rows) == 1
        assert not any(d.get("publication_id") == acknowledged["id"] for d in rows)
        evidence.record("hot-kafka-cutover-never-replays-history-to-new-raw-stream-and-resumes-legacy-filter-work")

        await raw.call(scoped(P, "ack", delivery_ids=[d["id"] for d in raw_rows]))
        await b.call(scoped(P, "ack", delivery_ids=[d["id"] for d in rows]))
        for _ in range(2):
            f.hard_stop()
            await f.start()
            assert await a.call(command, retry_id) == original_result
            assert not (await raw.call(scoped(P, "poll")))["deliveries"]
            assert not (await b.call(scoped(P, "poll")))["deliveries"]
            assert (await a.call(scoped(P, "get", publication_id=original["id"])))["publication"] == original
        evidence.record("repeated-kill-reopen-migration-is-idempotent-and-acknowledged-deliveries-never-resurrect")
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--legacy-hub", type=Path, required=True)
    parser.add_argument("--crash-at", choices=("before-prepared", "before-decided", "before-config", "after-snapshot", "before-completed"))
    parser.add_argument("--damage-backup", choices=("config", "backend", "snapshot"))
    asyncio.run(main(parser.parse_args()))
