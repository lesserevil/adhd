#!/usr/bin/env python3
"""Target-only restore using complete actual snapshots and real per-server Kafka.

Owns its native/container lifecycle. No private state is fabricated or rewritten;
only complete stopped-runtime files are copied into a verified offline bundle.
"""
from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from archive_support import ArchiveFixture
from multi_support import Evidence, Fixture, arguments, poll_until, scoped
from project_recovery_acceptance import Recovery, RED, BLUE
from project_recovery_state import canonical, digest, exact, read_json, registry, route, snapshot

ALLOCATED = re.compile(r"[a-z][a-z0-9]{0,15}_([0-9a-f]{32})_([1-9a-z][0-9a-z]*)\Z")


def allocated(value):
    found = set()
    if isinstance(value, str) and ALLOCATED.fullmatch(value):
        found.add(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            found |= allocated(key) | allocated(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= allocated(item)
    return found


async def finish(agent, project, op, query, timeout=30):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        result = (await agent.call(scoped(project, op, query_id=query["id"])))["query"]
        if result["status"] != "pending":
            assert result["status"] == "completed", result.get("error")
            return result
        await asyncio.sleep(.05)
    raise AssertionError("Controlled workflow did not complete")


async def basic_families(f, phase):
    """Accept originals and durable/query state through real public interfaces."""
    actor, recipient = await f.agent("bridge"), await f.agent("red-b")
    sub = (await recipient.call(scoped(RED, "subscribe", mode="raw"), "raw-" + phase))["subscription"]
    record = (await actor.call(scoped(RED, "publish_record", text="Recovery " + phase + " original evidence",
        information_type="recovery-" + phase, data={"integer": 1, "float": 1.0, "boolean": True, "unicode": "λ"},
        source={"kind": "fixture", "id": "recovery", "item_id": phase}), "pub-" + phase))["record"]
    pub = record["publication"]
    deliveries = await poll_until(recipient, RED, {pub["id"]})
    public_delivery = next(d for d in deliveries if d.get("publication_id") == pub["id"])
    await recipient.call(scoped(RED, "ack", delivery_ids=[public_delivery["id"]]))
    private = (await actor.call(scoped(RED, "send", recipient_id="red-b", text="PRIVATE " + phase), "private-" + phase))["delivery"]
    queries = {}
    for create, get in (("query_history", "get_history_query"), ("retrieve", "get_retrieval"), ("query_archive", "get_archive_query")):
        start = (await actor.call(scoped(RED, create, question="Which recovery original was recorded?",
            scope={"information_type": "recovery-" + phase}), create + "-" + phase))["query"]
        queries[create] = await finish(actor, RED, get, start)
    archive_id = queries["query_archive"]["id"]
    deadline = asyncio.get_running_loop().time() + 20
    while True:
        rows = (await actor.call(scoped(RED, "list_retrieval_attempts", limit=64)))["items"]
        attempt = next((v for v in rows if v["archive_query_id"] == archive_id), None)
        if attempt:
            break
        assert asyncio.get_running_loop().time() < deadline, "Archive capture missing"
        await asyncio.sleep(.05)
    f.admin().call(scoped(RED, "save_retrieval_label", attempt_id=attempt["id"], expected_label_revision=int(attempt["label_revision"]),
        label={"expectation": "supported", "support_ids": [pub["id"]], "cohort": "training", "tags": [],
            "note": "Independent allocator/storage fixture; controlled model only", "confirmed": True}), mutation=True)
    replay = (await actor.call(scoped(RED, "replay_retrieval", attempt_id=attempt["id"], candidate_recipe={"context_depth": 2}), "replay-" + phase))["query"]
    replay = await finish(actor, RED, "get_retrieval_replay", replay)
    full_attempt = (await actor.call(scoped(RED, "get_retrieval_attempt", attempt_id=attempt["id"])))["attempt"]
    return {"subscription": sub, "record": record, "acknowledged_delivery": public_delivery,
        "private_delivery": private, "queries": queries, "attempt": full_attempt, "replay": replay}


def offline_bundle(f, r, backup_id, project=RED):
    assert f.process.poll() is not None, "Offline bundle requires a stopped actual owner"
    entry, checkpoint = route(f.file, project)
    source = Path(str(checkpoint) + ".snapshot")
    state = snapshot(source)
    # The fixture deliberately configures this explicit private root before
    # accepting any plan; it does not guess a runtime-selected filesystem route.
    backup_root = Path(f.config["recovery"]["backup_root"])
    backup_root.mkdir(mode=0o700, exist_ok=True)
    assert backup_root.stat().st_mode & 0o077 == 0
    directory = backup_root / backup_id
    directory.mkdir(mode=0o700)
    for name, body in (("project.snapshot", source.read_bytes()), ("server-config.json", f.file.read_bytes())):
        path = directory / name
        path.write_bytes(body)
        path.chmod(0o600)
    manifest = {"schema": "adhd/project-backup@1", "server_id": entry["server_id"], "project_id": project,
        "aliases": sorted(entry["aliases"]), "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {"route_generation": state["route_generation"], "project_epoch": state["project_epoch"],
            "allocation_epoch": state["allocation_epoch"], "storage_generation": state["storage_generation"], "sequence": state["seq"]},
        "principal_proof": {"kind": "configuration-v1"}}
    for key, name in (("snapshot", "project.snapshot"), ("configuration", "server-config.json")):
        raw = (directory / name).read_bytes()
        manifest[key] = {"name": name, "bytes": len(raw), "sha256": digest(raw)}
    r.validate("BackupManifest", manifest)
    raw = canonical(manifest)
    (directory / "manifest.json").write_bytes(raw)
    (directory / "manifest.json").chmod(0o600)
    return manifest, digest(raw), state


async def checks(f, r, evidence):
    from project_recovery_workflows import allocate, event_controls
    await r.initialize(RED)
    await r.initialize(BLUE)
    retained = await basic_families(f, "retained")
    retained["optimizer"] = await allocate(f, f.model, "retained")
    retained["eventing"] = await event_controls(f, "retained", retained["record"]["publication"]["id"])
    actor, blue_recipient = await f.agent("bridge"), await f.agent("blue-b")
    blue_sub = (await blue_recipient.call(scoped(BLUE, "subscribe", mode="raw")))["subscription"]
    before = (await actor.call(scoped(BLUE, "publish_record", text="Blue before target backup")))["record"]["publication"]
    rows = await poll_until(blue_recipient, BLUE, {before["id"]})
    await blue_recipient.call(scoped(BLUE, "ack", delivery_ids=[d["id"] for d in rows if d.get("publication_id") == before["id"]]))
    f.hard_stop()
    backup, manifest_sha, retained_state = offline_bundle(f, r, "target-backup")
    await f.start()
    lost = await basic_families(f, "lost")
    lost["optimizer"] = await allocate(f, f.model, "lost")
    lost["eventing"] = await event_controls(f, "lost", lost["record"]["publication"]["id"])
    actor, blue_recipient = await f.agent("bridge"), await f.agent("blue-b")
    newer = (await actor.call(scoped(BLUE, "publish_record", text="Blue newer than target backup")))["record"]["publication"]
    newer_deliveries = await poll_until(blue_recipient, BLUE, {newer["id"]})
    await blue_recipient.call(scoped(BLUE, "ack", delivery_ids=[d["id"] for d in newer_deliveries if d.get("publication_id") == newer["id"]]))
    # Current security changes must survive: they are not part of target restore.
    f.admin().call({"op": "save_user", "user": {"username": "current-viewer", "name": "Current security sentinel",
        "email": "current@example.invalid", "password": "private-current-password", "role": "Viewer", "project_ids": [BLUE]}}, mutation=True)
    current_config = copy.deepcopy(f.admin().call({"op": "config_get"})["config"])
    blue_status = r.status(BLUE)
    blue_before = f.admin().call(scoped(BLUE, "eventing_status"))
    old_target = r.status(RED)["route"]
    f.hard_stop()
    _, anchor = route(f.file, RED)
    for p in (anchor, Path(str(anchor) + ".snapshot")):
        assert p.is_file() and not p.is_symlink()
        os.replace(p, p.with_name(p.name + ".lost-post-backup"))
    await f.start()
    assert r.status(RED)["availability"] == "recovery_required"
    revision = r.revision()
    receipt = r.call(RED, "project_restore_plan", backup_id="target-backup", manifest_sha256=manifest_sha,
        expected_revision=revision, allow_missing=True, message_id="review-target-restore")
    plan = (await r.settle(RED, receipt, {"ready"}))["plan"]
    r.assert_plan(plan, RED, "restore")
    assert plan["selected"]["project_epoch"] != old_target["project_epoch"]
    assert plan["selected"]["allocation_epoch"] != old_target["allocation_epoch"]
    apply = dict(plan_id=plan["plan_id"], plan_sha256=plan["plan_sha256"], expected_revision=revision,
        confirm=True, message_id="apply-target-restore")
    accepted = r.call(RED, "project_restore_apply", **apply)
    done = await r.settle(RED, accepted, {"complete"})
    assert done["result"]["initialized"] is False and done["result"]["transport_discontinuity"] is True
    _, restored_anchor = route(f.file, RED)
    restored_state = snapshot(str(restored_anchor) + ".snapshot")
    stable_families = ("publications", "subscriptions", "deliveries", "contexts", "idempotency", "sources", "admin_idempotency",
        "history_queries", "retrieval_queries", "archive_queries", "feedback", "replay_queries")
    for family in stable_families:
        assert exact(restored_state[family]) == exact(retained_state[family]), "Complete backed-up accepted state changed in family " + family
    assert f.admin().call({"op": "config_get"})["config"] == current_config
    assert r.status(BLUE)["route"] == blue_status["route"]
    after_blue = f.admin().call(scoped(BLUE, "eventing_status"))
    assert after_blue["topic"] == blue_before["topic"] and after_blue["next_offset"] == blue_before["next_offset"]
    blue_actor, blue_recipient = await f.agent("bridge"), await f.agent("blue-b")
    assert (await blue_actor.call(scoped(BLUE, "get", publication_id=newer["id"])))["publication"] == newer
    assert (await blue_recipient.call(scoped(BLUE, "poll")))["deliveries"] == []
    actor, recipient = await f.agent("bridge"), await f.agent("red-b")
    assert (await actor.call(scoped(RED, "get_record", publication_id=retained["record"]["publication"]["id"])))["record"] == retained["record"]
    wire = await f.raw("bridge", scoped(RED, "get_record", publication_id=retained["record"]["publication"]["id"]))
    raw_data = wire.json()["result"]["message"]["parts"][0]["data"]["record"]["publication"]["data"]
    assert type(raw_data["integer"]) is int and type(raw_data["float"]) is float and type(raw_data["boolean"]) is bool
    assert raw_data["unicode"] == "λ"
    restored_deliveries = (await recipient.call(scoped(RED, "poll")))["deliveries"]
    assert retained["private_delivery"]["id"] in {d["id"] for d in restored_deliveries}
    assert retained["acknowledged_delivery"]["id"] not in {d["id"] for d in restored_deliveries}
    for create, get in (("query_history", "get_history_query"), ("retrieve", "get_retrieval"), ("query_archive", "get_archive_query")):
        original = retained["queries"][create]
        assert (await actor.call(scoped(RED, get, query_id=original["id"])))["query"] == original
    assert (await actor.call(scoped(RED, "get_retrieval_attempt", attempt_id=retained["attempt"]["id"])))["attempt"] == retained["attempt"]
    assert (await actor.call(scoped(RED, "get_retrieval_replay", query_id=retained["replay"]["id"])))["query"] == retained["replay"]
    previous_proposal = retained["optimizer"]["proposal"]
    restored_proposal = f.admin().call(scoped(RED, "index_proposal", proposal_id=previous_proposal["id"], limit=64))["proposal"]
    for field in ("id", "training_attempt_ids", "held_out_attempt_ids", "regression_attempt_ids", "winner_identity", "evaluation"):
        assert restored_proposal[field] == previous_proposal[field], "Backed-up optimizer provenance was discarded or invented"
    new = await basic_families(f, "lost")
    new["optimizer"] = await allocate(f, f.model, "recovered")
    new["eventing"] = await event_controls(f, "recovered", new["record"]["publication"]["id"])
    before_ids = allocated(retained_state)
    # New responses legitimately cite retained objects. Compare accepted ID
    # deltas instead of incorrectly demanding that preserved references change.
    lost_ids, new_ids = allocated(lost) - before_ids, allocated(new) - before_ids
    assert before_ids and lost_ids and new_ids
    assert not new_ids & (before_ids | lost_ids), "Post-restore allocator collided with retained or lost post-backup IDs"
    allocation_epoch = done["result"]["allocation_epoch"]
    assert all(ALLOCATED.fullmatch(value).group(1) == allocation_epoch for value in new_ids)
    evidence.record("target-only-restore-keeps-originals-private-acks-current-security-and-other-project-newer-position",
        retained_ids=len(before_ids), lost_post_backup_ids=len(lost_ids), new_ids=len(new_ids),
        families=["publication", "subscription", "delivery", "history", "retrieval", "archive", "feedback", "replay",
            "optimizer-proposal", "optimizer-child", "optimizer-evaluation", "selection-reset", "event-replay", "repair", "audit"],
        complete_accepted_subtrees_compared=list(stable_families),
        optimizer_quality_results={"retained": previous_proposal["status"], "lost": lost["optimizer"]["proposal"]["status"],
            "recovered": new["optimizer"]["proposal"]["status"]},
        transport_discontinuity=True)
    f.hard_stop()
    await f.start()
    assert r.call(RED, "project_restore_apply", **apply) == accepted
    assert r.status(RED)["route"]["allocation_epoch"] == allocation_epoch
    entry, checkpoint = route(f.file, RED)
    actual = snapshot(str(checkpoint) + ".snapshot")
    assert actual["allocation_epoch"] == allocation_epoch
    assert new_ids <= allocated(actual)
    assert not lost_ids & allocated(actual), "Cold recovery overwrote later activated writes or imported lost history"
    assert all(ALLOCATED.fullmatch(value).group(1) == allocation_epoch for value in allocated(actual) - before_ids), \
        "A newly accepted/internal ID used an old allocation namespace"
    evidence.record("apply-retry-and-cold-start-preserve-newer-activated-generation-without-reinstalling-older-backup")


async def main(args):
    from project_recovery_workflows import configure, model_fixture
    assert not args.rest_url, "Target restore requires an owned isolated backend"
    args.with_model = False
    f = Fixture(args, initialize_projects=False)
    model = model_fixture()
    f.model = model
    f.config.update(matcher={"url": model.url, "model": "controlled-recovery", "timeout_ms": 3000, "retry_ms": 100},
        archive={"audit_rate_ppm": 0}, history={"request_bytes": 65536},
        recovery={"backup_root": str(f.root / "offline-backups")})
    configure(f)
    evidence = Evidence(args.report, "target-only-project-restore")
    evidence.value["fixture_phase_wait_seconds"] = {"optimizer_training": 300, "optimizer_evaluation": 300, "kafka_replay_materialization": 300, "kafka_drain": 300}
    evidence.value["timing_scope"] = "Bounded complete-state lifecycle fixture, not throughput qualification; all original cases, gold and quality gates retained."
    if args.hub:
        evidence.value["artifact_sha256"] = digest(args.hub.read_bytes())
    try:
        await f.start()
        r = Recovery(f, args.recovery_schema)
        evidence.value["authored_recovery_schema_sha256"] = r.schema_sha256
        await checks(f, r, evidence)
        evidence.value["scope"] = "Target restore and public original/query/feedback/replay/optimizer/selection and actual Kafka repair/replay/audit allocator families using controlled typed replies. Deterministic lineage hashes remain stable. Federation and crash/browser gates remain separate; no live semantic model qualification."
    except BaseException as error:
        evidence.finish(error)
        raise
    else:
        evidence.finish()
    finally:
        try:
            await f.close()
        except BaseException as error:
            evidence.finish(error)
            raise
        f.bind_evidence(evidence)
        evidence.write()


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--recovery-schema", type=Path,
        default=Path(__file__).resolve().parents[1] / "components/hub/project-recovery/interface.schema.json")
    asyncio.run(main(parser.parse_args()))
