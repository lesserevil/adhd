#!/usr/bin/env python3
"""Two-phase public API durability probe across real deployment replacement.

Run before and after the operator replaces a Compose/Kubernetes hub and broker.
This tool performs no orchestration and makes no replication/HA claim. The same
private credential file and --snapshot must be retained between the two phases.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from multi_support import Evidence, Fixture, arguments, poll_until, reject, scoped


P = "project-red"


async def main(args):
    if not args.rest_url:
        raise ValueError("Deployment replacement requires --rest-url for the orchestrated server")
    f = Fixture(args)
    evidence = Evidence(args.report, "adhd/eventing-deployment-replacement@1")
    evidence.value["phase"] = args.phase
    try:
        await f.start()
        a, b = await f.agent("red-a"), await f.agent("red-b")
        server_id = f.admin().call({"op": "config_get"})["config"]["server_id"]
        if args.phase == "before":
            await b.call(scoped(P, "subscribe", mode="raw"))
            mid = uuid4().hex
            command = scoped(P, "publish", text="Durable deployment replacement fact " + mid,
                source={"kind": "slack", "id": "deployment-fixture", "item_id": mid})
            result = await a.call(command, mid)
            publication = result["publication"]
            rows = await poll_until(b, P, {publication["id"]}, args.deadline)
            own = [d for d in rows if d.get("publication_id") == publication["id"]]
            assert len(own) == 1
            snapshot = {"server_id": server_id, "command": command, "message_id": mid,
                        "publication_result": result, "delivery": own[0]}
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot.write_text(json.dumps(snapshot, indent=2) + "\n")
            args.snapshot.chmod(0o600)
            evidence.record("real-deployment-accepted-original-source-retry-and-unacknowledged-delivery")
        else:
            raw = args.snapshot.read_bytes()
            snapshot = json.loads(raw)
            assert server_id == snapshot["server_id"], "Replacement created a different logical server"
            result = snapshot["publication_result"]
            original, delivery = result["publication"], snapshot["delivery"]
            assert await a.call(snapshot["command"], snapshot["message_id"]) == result
            assert (await a.call(scoped(P, "get", publication_id=original["id"])))["publication"] == original
            assert (await a.call(scoped(P, "search", query=original["text"])))["publications"] == [original]
            rows = await poll_until(b, P, {original["id"]}, args.deadline)
            assert [d for d in rows if d.get("publication_id") == original["id"]] == [delivery]
            await b.call(scoped(P, "ack", delivery_ids=[delivery["id"]]))
            await b.call(scoped(P, "ack", delivery_ids=[delivery["id"]]))
            assert not any(d.get("publication_id") == original["id"]
                           for d in (await b.call(scoped(P, "poll")))["deliveries"])
            reject(await f.raw("blue-a", scoped(P, "get", publication_id=original["id"])))
            evidence.record("replacement-preserves-server-original-source-retry-and-delivery-identities",
                            snapshot_sha256=hashlib.sha256(raw).hexdigest())
            evidence.record("idempotent-ack-and-project-denial-remain-enforced-after-replacement")
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
