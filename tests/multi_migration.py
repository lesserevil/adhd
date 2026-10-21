#!/usr/bin/env python3
"""Real legacy producer -> multi-project/Kafka migration across process kills.

Requires the actual previous qualified hub, not manually synthesized store data.
The old runtime creates credentials, originals, semantic jobs, delivery IDs and
acknowledgements through A2A; the candidate opens the same configuration/store.
"""
import asyncio
import copy
import hashlib
from pathlib import Path
import time
from uuid import uuid4

from multi_support import Evidence, Fixture, arguments, poll_until, scoped


P = "project-red"


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
    # The producer starts with the previous format, never a new registry seeded
    # into an old binary. All its agents belong to the migrated default project.
    f.config.pop("projects")
    f.config.pop("agent_projects")
    f.config.pop("eventing")
    try:
        await f.start()
        a, b = await f.agent("red-a"), await f.agent("red-b")
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
        # The candidate must migrate the persisted old configuration itself.
        # Kafka is enabled after that migration through the supported hot API.
        await f.start()
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
    asyncio.run(main(parser.parse_args()))
