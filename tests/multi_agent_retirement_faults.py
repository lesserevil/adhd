#!/usr/bin/env python3
"""Developer identity creation fails closed on unavailable ownership evidence.

Public APIs establish the fixture and inspect outcomes. File fault injection
temporarily removes or corrupts one atomic snapshot without decoding its state.
The exact original bytes are restored before the healthy recovery attempt.
"""
import asyncio
import hashlib
import os
from pathlib import Path
import secrets
from uuid import uuid4
from protocol_acceptance import ByteValidator

from foundation_acceptance import Client
from multi_support import Admin, arguments, execute, scoped


async def checks(f, evidence):
    assert not f.args.rest_url and f.config_file, "Requires an owned runtime and private snapshot"
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence.value["limitations"] = ["File faults qualify ownership evidence unavailability, not semantic model quality or replicated Kafka durability."]
    schema = Client(f).get("/protocol/schema")[1]
    assert isinstance(schema, dict)
    validator = ByteValidator({"$defs": schema["$defs"], "$ref": "#/$defs/Error"})
    statuses = Client(f).get("/protocol/openapi")[1]["paths"]["/admin/api"]["post"]["responses"]
    admin = f.admin()
    password = secrets.token_urlsafe(32)
    user = admin.call({"op": "save_user", "user": {"username": "snapshot-developer",
        "name": "Snapshot developer", "email": "snapshot-developer@example.invalid",
        "password": password, "role": "Developer", "project_ids": ["project-red"]}}, mutation=True)["user"]
    client = Client(f)
    client.login("snapshot-developer", password)
    developer = Admin(client, f, admin.client)
    developer.call({"op": "create_agent", "agent_id": "healthy-before-fault",
                    "token": secrets.token_urlsafe(32), "project_ids": ["project-red"]}, mutation=True)
    evidence.record("fresh-developer-creation-succeeds-with-complete-snapshot-evidence")

    if schema.get("$id") == "urn:adhd:protocol:2.1":
        from project_recovery_state import route
        entry, anchor = route(f.config_file, "project-red")
        assert entry["initialized"] and entry["availability"] == "ready"
        snapshot = Path(str(anchor) + ".snapshot")
    else:
        snapshot = Path(f.config["store_path"] + ".snapshot")
    held = snapshot.with_name(snapshot.name + ".ownership-fault-held")
    assert snapshot.is_file() and not held.exists()
    observations = []
    blue = await f.agent("blue-a")
    blue_original = (await blue.call(scoped("project-blue", "publish", text="Healthy Blue ownership-fault control")))["publication"]
    live_process = f.process
    for mode in ("missing", "corrupt"):
        agent_id, token = "fresh-during-" + mode, secrets.token_urlsafe(32)
        before = admin.call({"op": "config_get"})
        revision = before["config"].get("config_revision", before.get("config_revision", before.get("revision")))
        command = {"op": "create_agent", "agent_id": agent_id, "token": token,
            "project_ids": ["project-red"], "expected_revision": revision, "confirm": True, "message_id": uuid4().hex}
        original = snapshot.read_bytes()
        os.replace(snapshot, held)
        try:
            if mode == "corrupt":
                snapshot.write_bytes(b"deliberate ownership-evidence corruption")
                snapshot.chmod(0o600)
            status, response, _ = client.request("/admin/api", command)
            # A concurrent rewrite would invalidate the fault, not count as a
            # passing fail-closed observation.
            assert not snapshot.exists() if mode == "missing" else snapshot.read_bytes() == b"deliberate ownership-evidence corruption"
            after = admin.call({"op": "config_get"})
            assert f.process is live_process and f.process.poll() is None
            if f.image_runtime:
                f.image_runtime.observe()
            assert (await blue.call(scoped("project-blue", "get", publication_id=blue_original["id"])))['publication'] == blue_original
            blue_progress = (await blue.call(scoped("project-blue", "publish", text="Healthy Blue during " + mode + " ownership evidence fault")))["publication"]
            assert (await blue.call(scoped("project-blue", "get", publication_id=blue_progress["id"])))['publication'] == blue_progress
            f.tokens[agent_id] = token
            unauthorized = (await f.raw(agent_id, scoped("project-red", "whoami"))).status_code == 401
            row = {"fault": mode, "http_status": status,
                "error_code": response.get("error", {}).get("code"),
                "configuration_unchanged": before == after, "new_token_denied": unauthorized,
                "shared_runtime_unchanged": True, "unrelated_blue_original_and_progress_preserved": True,
                "original_snapshot_sha256": hashlib.sha256(original).hexdigest()}
            observations.append(row)
            evidence.value["fault_observations"] = observations
            evidence.write()
            assert 400 <= status < 600 and str(status) in statuses
            validator.validate(response)
            assert row["configuration_unchanged"] and unauthorized
        finally:
            os.replace(held, snapshot)
            assert snapshot.read_bytes() == original
        restored = developer.call({"op": "create_agent", "agent_id": agent_id, "token": token,
                                   "project_ids": ["project-red"]}, mutation=True)
        assert restored["owner_user_id"] == user["id"]
        assert (await (await f.agent(agent_id)).call(scoped("project-red", "whoami")))["agent_id"] == agent_id
        evidence.record("identity-creation-fails-closed-and-recovers-after-" + mode + "-snapshot-restoration")


if __name__ == "__main__":
    args = arguments(__doc__).parse_args()
    asyncio.run(execute(args, "multi-agent-retirement-snapshot-faults", checks))
