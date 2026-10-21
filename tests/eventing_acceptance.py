#!/usr/bin/env python3
"""Independent A2A Kafka fan-out, model independence, selectors and fault checks.

Uses a real Kafka REST bridge configured by --eventing-rest-url. This test never
implements or substitutes a successful broker. --broker-container enables an
actual broker outage/restart in an explicitly supplied disposable deployment.
"""
import asyncio
import json
import subprocess
import time
from uuid import uuid4

from multi_support import arguments, execute, poll_until, reject, scoped


P = "project-red"


async def acknowledge(agent, deliveries):
    if deliveries:
        await agent.call(scoped(P, "ack", delivery_ids=[d["id"] for d in deliveries]))


async def checks(f, evidence):
    a, b, bridge = [await f.agent(name) for name in ("red-a", "red-b", "bridge")]
    before_calls = f.model.calls if f.model else 0
    old = (await a.call(scoped(P, "publish", text="Accepted before stream activation")))["publication"]
    sub = (await b.call(scoped(P, "subscribe", mode="raw")))["subscription"]
    overlap = (await b.call(scoped(P, "subscribe")))["subscription"]
    await a.call(scoped(P, "subscribe", mode="raw"))
    await bridge.call(scoped(P, "subscribe", mode="raw"))
    await asyncio.sleep(.4)
    assert not (await b.call(scoped(P, "poll")))["deliveries"]
    assert sub["mode"] == overlap["mode"] == "raw"
    evidence.record("raw-and-default-subscriptions-need-no-filter-or-model-and-start-after-activation")

    published = []
    for publisher, text in ((a, "Publisher A event"), (b, "Subscriber's own event"), (bridge, "Multi-project publisher event")):
        result = await publisher.call(scoped(P, "publish", text=text))
        published.append(result["publication"])
    ids = {p["id"] for p in published}
    for subscriber in (a, b, bridge):
        deliveries = await poll_until(subscriber, P, ids, f.args.deadline)
        public = [d for d in deliveries if d.get("publication_id") in ids]
        assert len(public) == len(ids), "Overlapping subscriptions duplicated recipient events"
        assert old["id"] not in {d.get("publication_id") for d in deliveries}
        assert {d["author_id"] for d in public} == {"red-a", "red-b", "bridge"}
        for delivery in public:
            publication = next(p for p in published if p["id"] == delivery["publication_id"])
            for key in ("project_id", "author_id", "source", "information_type", "text", "data"):
                assert delivery[key] == publication[key]
            assert delivery["matches"]
            for reason in delivery["matches"]:
                assert set(reason) == {"subscription_id", "subscription_revision", "mode"}
                assert reason["mode"] == "raw" and reason["subscription_revision"] >= 1
        # Protobuf Struct represents every SDK data number as a double. Check
        # integer wire tokens independently on raw HTTP, before SDK conversion.
        wire = (await f.raw(next(name for name, obj in (("red-a", a), ("red-b", b), ("bridge", bridge)) if obj is subscriber), scoped(P, "poll"))).json()
        wire_rows = wire["result"]["message"]["parts"][0]["data"]["deliveries"]
        assert all(type(r["subscription_revision"]) is int for d in wire_rows for r in d["matches"])
        assert (await subscriber.call(scoped(P, "poll")))["deliveries"] == deliveries
        await acknowledge(subscriber, deliveries)
        assert not (await subscriber.call(scoped(P, "poll")))["deliveries"]
    assert f.model is None or f.model.calls == before_calls
    evidence.record("all-publishers-including-self-independent-subscribers-and-overlap-dedup",
                    publications=len(published), subscribers=3, controlled_model_calls=0)

    # Backend originals survive broker-delivery acknowledgement and do not
    # require an extant subscription or a semantic decision endpoint.
    for publication in published + [old]:
        assert (await bridge.call(scoped(P, "get", publication_id=publication["id"])))["publication"] == publication
    found = (await bridge.call(scoped(P, "search", query="Publisher A event")))["publications"]
    assert found == [published[0]]
    assert f.model is None or f.model.calls == before_calls
    evidence.record("read-after-publish-and-post-ack-literal-search-retain-originals-with-zero-inference")

    direct = (await a.call(scoped(P, "send", recipient_id="red-b", text="Private message never on project stream")))["delivery"]
    await asyncio.sleep(.4)
    assert not (await bridge.call(scoped(P, "poll")))["deliveries"]
    assert not (await bridge.call(scoped(P, "search", query="Private message never")))["publications"]
    private = (await b.call(scoped(P, "poll")))["deliveries"]
    assert [d["id"] for d in private] == [direct["id"]]
    await acknowledge(b, private)
    evidence.record("private-addressed-messages-are-never-public-events-or-searchable-facts")

    for invalid in (
        {"mode": "filtered"}, {"mode": "filtered", "filter": ""},
        {"mode": "filtered", "filter": "   "}, {"mode": "raw", "filter": "Only release changes"},
        {"mode": "raw", "selectors": {"unknown": ["x"]}},
        {"mode": "raw", "selectors": {"author_id": "red-a"}},
        {"mode": "raw", "selectors": {"information_type": []}},
    ):
        reject(await f.raw("red-b", scoped(P, "subscribe", **invalid)))
    evidence.record("blank-conflicting-and-unknown-filter-selector-inputs-fail-closed")

    await b.call(scoped(P, "unsubscribe", subscription_id=sub["id"]))
    await b.call(scoped(P, "unsubscribe", subscription_id=overlap["id"]))
    selected = (await b.call(scoped(P, "subscribe", mode="raw", selectors={
        "information_type": ["status", "artifact"], "author_id": ["red-a"],
        "source_kind": ["slack"], "source_id": ["release-channel"]})))["subscription"]
    candidates = [
        (a, {"information_type": "status", "source": {"kind": "slack", "id": "release-channel"}}),
        (a, {"information_type": "artifact", "source": {"kind": "slack", "id": "release-channel"}}),
        (a, {"information_type": "message", "source": {"kind": "slack", "id": "release-channel"}}),
        (b, {"information_type": "status", "source": {"kind": "slack", "id": "release-channel"}}),
        (a, {"information_type": "status", "source": {"kind": "email", "id": "release-channel"}}),
        (a, {"information_type": "status", "source": {"kind": "slack", "id": "other-channel"}}),
    ]
    expected = []
    all_events = []
    for index, (publisher, fields) in enumerate(candidates):
        publication = (await publisher.call(scoped(P, "publish", text="Selector matrix " + str(index), **fields)))["publication"]
        all_events.append(publication)
        if index < 2:
            expected.append(publication["id"])
    rows = await poll_until(b, P, set(expected), f.args.deadline)
    # Wait for all events to pass through an independent raw subscriber before
    # asserting exclusions: a quick empty poll alone cannot prove selection.
    await poll_until(bridge, P, {p["id"] for p in all_events}, f.args.deadline)
    await asyncio.sleep(.2)
    rows = (await b.call(scoped(P, "poll")))["deliveries"]
    assert {d["publication_id"] for d in rows} == set(expected)
    assert f.model is None or f.model.calls == before_calls
    await acknowledge(b, rows)
    await b.call(scoped(P, "unsubscribe", subscription_id=selected["id"]))
    evidence.record("deterministic-selector-fields-intersect-values-union-without-inference", cases=len(candidates))

    if f.model:
        await filtered_faults(f, evidence, a, b, bridge)
    else:
        evidence.value["limitations"].append("Optional semantic filter fault phase requires a separate --with-model run.")

    if f.args.broker_container:
        await broker_faults(f, evidence, a, bridge)
    else:
        evidence.value["limitations"].append("Actual broker process faults require --broker-container; this run covers healthy real broker handoff.")


async def filtered_faults(f, evidence, publisher, filtered, raw):
    f.model.mode = "error"
    subscription = (await filtered.call(scoped(P, "subscribe", mode="filtered", filter="Only API compatibility changes")))["subscription"]
    calls = f.model.calls
    publication = (await publisher.call(scoped(P, "publish", text="API compatibility breaking change")))["publication"]
    await poll_until(raw, P, {publication["id"]}, f.args.deadline)
    assert (await filtered.call(scoped(P, "search", query="API compatibility breaking change")))["publications"] == [publication]
    deadline = time.monotonic() + f.args.deadline
    while f.model.calls <= calls and time.monotonic() < deadline:
        await asyncio.sleep(.1)
    assert f.model.calls > calls, "Filtered stream never attempted its explicit decision"
    assert not (await filtered.call(scoped(P, "poll")))["deliveries"]
    f.model.mode = "invalid"
    await asyncio.sleep(.6)
    assert not (await filtered.call(scoped(P, "poll")))["deliveries"]
    f.model.mode = "match"
    rows = await poll_until(filtered, P, {publication["id"]}, f.args.deadline)
    assert sum(d.get("publication_id") == publication["id"] for d in rows) == 1
    await acknowledge(filtered, rows)
    await asyncio.sleep(.4)
    assert not (await filtered.call(scoped(P, "poll")))["deliveries"]
    evidence.record("optional-filter-error-and-invalid-result-preserve-raw-progress-and-search-retry-once")
    await filtered.call(scoped(P, "unsubscribe", subscription_id=subscription["id"]))
    await subscription_revisions(f, evidence, publisher, filtered, raw)


async def subscription_revisions(f, evidence, publisher, subscriber, raw):
    f.model.mode = "error"
    subscription = (await subscriber.call(scoped(P, "subscribe", mode="filtered", filter="Criterion before editing")))["subscription"]
    old = (await publisher.call(scoped(P, "publish", text="Accepted under old filtered revision")))["publication"]
    await poll_until(raw, P, {old["id"]}, f.args.deadline)
    edit = scoped(P, "update_subscription", subscription_id=subscription["id"],
                  expected_revision=int(subscription["revision"]), mode="raw")
    subscription = (await subscriber.call(edit))["subscription"]
    reject(await f.raw("red-b", edit))
    new = (await publisher.call(scoped(P, "publish", text="Accepted under new raw revision")))["publication"]
    rows = await poll_until(subscriber, P, {new["id"]}, f.args.deadline)
    assert not any(d.get("publication_id") == old["id"] for d in rows)
    assert all(r["mode"] == "raw" and r["subscription_revision"] == subscription["revision"]
               for d in rows for r in d["matches"])
    await acknowledge(subscriber, rows)
    f.model.mode = "nonmatch"
    # Fence inference completion with an observed typed request for the frozen
    # old event. A raw stream reaching newer data alone cannot prove its fate.
    deadline = time.monotonic() + f.args.deadline
    while time.monotonic() < deadline:
        if any(r.get("state", {}).get("publication", {}).get("id") == old["id"] for r in f.model.requests):
            break
        await asyncio.sleep(.1)
    else:
        raise AssertionError("Old revision event never reached its explicitly configured decision queue")
    await asyncio.sleep(.5)
    assert not (await subscriber.call(scoped(P, "poll")))["deliveries"]
    subscription = (await subscriber.call(scoped(P, "update_subscription", subscription_id=subscription["id"],
        expected_revision=int(subscription["revision"]), mode="raw", paused=True)))["subscription"]
    paused = (await publisher.call(scoped(P, "publish", text="Accepted while stream paused")))["publication"]
    await poll_until(raw, P, {paused["id"]}, f.args.deadline)
    assert not (await subscriber.call(scoped(P, "poll")))["deliveries"]
    subscription = (await subscriber.call(scoped(P, "update_subscription", subscription_id=subscription["id"],
        expected_revision=int(subscription["revision"]), mode="raw", paused=False)))["subscription"]
    resumed = (await publisher.call(scoped(P, "publish", text="Accepted after explicit stream resume")))["publication"]
    rows = await poll_until(subscriber, P, {resumed["id"]}, f.args.deadline)
    assert {d["publication_id"] for d in rows} == {resumed["id"]}
    await acknowledge(subscriber, rows)
    await subscriber.call(scoped(P, "unsubscribe", subscription_id=subscription["id"]))
    f.model.mode = "match"
    evidence.record("revision-conflicts-frozen-filter-work-hot-raw-switch-and-pause-resume-watermarks")


async def broker_faults(f, evidence, publisher, raw):
    name = f.args.broker_container
    inspection = subprocess.run(["docker", "inspect", "--format", "{{.Id}} {{.State.Running}}", name],
                                text=True, capture_output=True, check=True).stdout.strip()
    assert inspection.endswith(" true"), "Explicit disposable broker is not running"
    subprocess.run(["docker", "stop", "--time", "5", name], check=True, capture_output=True)
    accepted = []
    try:
        for i in range(3):
            # The durability contract accepts originals/outbox while Kafka is
            # unavailable; no synchronous delivery success is inferred.
            result = await publisher.call(scoped(P, "publish", text="Broker offline durable fact " + str(i)), "outage-" + str(i))
            accepted.append(result["publication"])
            assert result["event"]["state"] == "pending"
            assert (await publisher.call(scoped(P, "get", publication_id=accepted[-1]["id"])))["publication"] == accepted[-1]
        ids = {p["id"] for p in accepted}
        assert not ids.intersection(d.get("publication_id") for d in (await raw.call(scoped(P, "poll")))["deliveries"])
        if f.process:
            f.hard_stop()
            await f.start()
            assert (await publisher.call(scoped(P, "search", query="Broker offline durable fact")))["publications"]
    finally:
        subprocess.run(["docker", "start", name], check=True, capture_output=True)
    rows = await poll_until(raw, P, {p["id"] for p in accepted}, f.args.deadline + 30)
    for publication in accepted:
        assert sum(d.get("publication_id") == publication["id"] for d in rows) == 1
    await acknowledge(raw, rows)
    if f.process:
        f.hard_stop()
        await f.start()
    await asyncio.sleep(.5)
    assert not {p["id"] for p in accepted}.intersection(
        d.get("publication_id") for d in (await raw.call(scoped(P, "poll")))["deliveries"])
    evidence.record("real-broker-outage-outbox-hub-kill-recovery-and-acked-replay-dedup", events=len(accepted))


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--broker-container", help="Explicit disposable Kafka broker to stop/start during qualification")
    args = parser.parse_args()
    asyncio.run(execute(args, "adhd/eventing-acceptance@1", checks))
