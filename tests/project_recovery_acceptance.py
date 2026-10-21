#!/usr/bin/env python3
"""Independent profile2.1 recovery admission, ownership and durable plan tests.

This is future acceptance, not an assertion that profile2.0 supports recovery.
Only public Admin/A2A APIs create accepted data; owned offline files are inspected
without opening DETS. Integration requires a real Kafka REST service.
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx
import jsonschema
from jsonschema import validators

from foundation_acceptance import Client
from multi_support import Evidence, Fixture, PROJECTS, arguments, scoped
from project_recovery_state import canonical, digest, read_json, registry, route, snapshot

RED, BLUE, HIDDEN = [p["id"] for p in PROJECTS]


def byte_bound(validator, limit, value, schema):
    if isinstance(value, str) and len(value.encode("utf-8")) > limit:
        yield jsonschema.ValidationError("Recovery UTF8 byte bound exceeded")


Strict = validators.extend(jsonschema.Draft202012Validator, {"x-maxBytes": byte_bound},
    type_checker=jsonschema.Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _, value: type(value) is int))


class Recovery:
    def __init__(self, fixture, schema):
        self.f = fixture
        self.definitions = read_json(schema)["$defs"]
        self.schema_sha256 = digest(Path(schema).read_bytes())

    def validate(self, name, value):
        Strict({"$defs": self.definitions, "$ref": "#/$defs/" + name},
            format_checker=jsonschema.FormatChecker()).validate(value)
        return value

    def call(self, project, op, expected=200, client=None, **fields):
        result = (client or self.f.admin().client).api(scoped(project, op, **fields), expected=expected)
        if expected != 200:
            self.validate("Error", result)
        else:
            self.validate("Status" if op == "project_restore_status" else "Accepted", result)
            assert result["project_id"] == project
            if op == "project_restore_status" and result["operation"] is not None:
                operation = result["operation"]
                assert operation["project_id"] == project
                if fields.get("operation_id"):
                    assert operation["operation_id"] == fields["operation_id"]
                progress = operation["progress"]
                assert progress["bytes_read"] <= progress["maximum_bytes"]
                assert progress["records_checked"] <= progress["maximum_records"]
        return result

    def revision(self):
        return self.f.admin().call({"op": "config_get"})["config_revision"]

    def status(self, project, operation_id=None):
        return self.call(project, "project_restore_status", **({"operation_id": operation_id} if operation_id else {}))

    async def settle(self, project, receipt, states):
        deadline = time.monotonic() + self.f.args.deadline
        while time.monotonic() < deadline:
            value = self.status(project, receipt["operation_id"])["operation"]
            assert value["kind"] == receipt["kind"]
            if value["state"] in states:
                return value
            assert value["state"] not in {"failed", "blocked", "stale", "expired"}, value["failure"]
            await asyncio.sleep(.05)
        raise AssertionError("Recovery job exceeded its declared acceptance deadline")

    def assert_plan(self, plan, project, mode):
        self.validate("Plan", plan)
        body = {k: v for k, v in plan.items() if k != "plan_sha256"}
        assert digest(canonical(body)) == plan["plan_sha256"], "Plan digest does not bind its canonical reviewed bytes"
        assert plan["project_id"] == project and plan["mode"] == mode
        assert plan["selected"]["project_epoch"] != plan["selected"]["allocation_epoch"]
        assert plan["selected"]["route_generation"] > plan["target"]["route_generation"]
        assert plan["aliases"] == sorted(plan["aliases"]) and project not in plan["aliases"]
        if plan["selected"]["transport_enabled"]:
            topic = plan["policy"]["topic_prefix"] + "." + digest(plan["server_id"].encode())[:16] + "." + digest(project.encode())[:16]
            assert plan["selected"]["topic"] == topic + ".r" + plan["selected"]["project_epoch"] + ".events.v1"
        return plan

    async def initialize(self, project, mid=None):
        revision = self.revision()
        command = dict(mode="initialize", expected_revision=revision, confirm=True, message_id=mid or uuid4().hex)
        receipt = self.call(project, "project_restore_plan", **command)
        plan = (await self.settle(project, receipt, {"ready"}))["plan"]
        self.assert_plan(plan, project, "initialize")
        assert plan["backup"] is None and plan["backup_id"] is None and plan["manifest_sha256"] is None
        assert plan["target"]["availability"] == "uninitialized" and plan["target"]["watermark"]["state_sha256"] is None
        apply = dict(plan_id=plan["plan_id"], plan_sha256=plan["plan_sha256"], expected_revision=revision,
            confirm=True, message_id=uuid4().hex)
        accepted = self.call(project, "project_restore_apply", **apply)
        complete = await self.settle(project, accepted, {"complete"})
        assert complete["result"]["initialized"] is True
        assert complete["result"]["transport_discontinuity"] is False
        assert self.revision() == revision
        assert self.call(project, "project_restore_apply", **apply) == accepted
        repeated = self.call(project, "project_restore_apply", **{**apply, "message_id": uuid4().hex})
        assert repeated["operation_id"] == accepted["operation_id"], "A decided plan installed twice"
        return command, receipt, apply, accepted, complete


def unavailable_rpc(response):
    """Valid A2A domain failures retain JSON-RPC HTTP200 (protocol/spec.md)."""
    assert response.status_code == 200
    body = response.json()
    assert 'result' not in body and body['jsonrpc'] == '2.0'
    error = body['error']
    assert error['code'] == -32000
    assert error['data'] == [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo',
        'domain': 'adhd.hub', 'metadata': {'code': 'RECOVERY_REQUIRED'}, 'reason': 'RECOVERY_REQUIRED'}]
    assert response.headers.get('retry-after') == '1'


async def admission(f, r, evidence):
    assert not f.args.rest_url, "Destructive recovery qualification requires owned native/container storage"
    async with httpx.AsyncClient(trust_env=False) as http:
        schema = (await http.get(f.base + "/protocol/schema")).json()
    assert schema["$id"] == "urn:adhd:protocol:2.1", "Target has not admitted the recovery profile"
    before = copy.deepcopy(f.admin().call({"op": "config_get"})["config"])
    for project in (RED, BLUE, HIDDEN):
        status = r.status(project)
        assert status["availability"] == "uninitialized" and status["operation"] is None
    actor = await f.agent("bridge")
    rejected = await f.raw("bridge", scoped(RED, "publish_record", text="Must not create an unknown target"), "unknown-publish-mid")
    unavailable_rpc(rejected)
    assert r.status(RED)["operation"] is None
    assert f.admin().call({"op": "config_get"})["config"] == before
    evidence.record("handwritten-config-global-auth-does-not-admit-unknown-project-stores")

    # Admission checks use current identities, including a real local session and
    # the distinct agent-token authority. They must not leave operation receipts.
    for role in ("Developer", "Viewer"):
        name = "recovery-" + role.lower()
        f.admin().call({"op": "save_user", "user": {"username": name, "password": "isolated-recovery-password",
            "name": "Recovery " + role, "email": name + "@example.invalid", "role": role, "project_ids": [RED]}}, mutation=True)
        client = Client(f)
        client.login(name, "isolated-recovery-password")
        value = r.call(RED, "project_restore_plan", client=client, expected=403, mode="initialize",
            expected_revision=r.revision(), confirm=True, message_id="denied-" + role)
        assert value["error"]["code"] == "FORBIDDEN"
    forbidden = r.call(RED, "project_restore_status", client=Client(f, f.tokens["bridge"]), expected=401)
    assert forbidden["error"]["code"] == "UNAUTHORIZED"
    assert r.status(RED)["operation"] is None
    evidence.record("developer-viewer-and-agent-cannot-obtain-or-create-server-owned-recovery-work")

    before = copy.deepcopy(f.admin().call({"op": "config_get"})["config"])
    saved = await r.initialize(RED, "initialize-red-once")
    assert f.admin().call({"op": "config_get"})["config"] == before
    assert r.status(BLUE)["availability"] == "uninitialized"
    entry, anchor = route(f.file, RED)
    state = snapshot(str(anchor) + ".snapshot")
    assert state["schema"] == 4 and state["project_epoch"] == entry["project_epoch"]
    assert state["allocation_epoch"] == entry["allocation_epoch"]
    assert state["route_generation"] == entry["generation"]
    assert r.status(RED)["route"]["project_epoch"] == state["project_epoch"]
    evidence.record("explicit-reviewed-admin-initialization-creates-one-verified-route-without-config-or-other-project-change")

    # A plan's operation ID is server-owned and cannot resolve through another
    # selected project; its receipt survives a real process/container replacement.
    absent = r.call(BLUE, "project_restore_status", expected=404, operation_id=saved[1]["operation_id"])
    assert absent["error"]["code"] == "NOT_FOUND"
    f.hard_stop()
    await f.start()
    assert r.call(RED, "project_restore_plan", **saved[0]) == saved[1]
    assert r.call(RED, "project_restore_apply", **saved[2]) == saved[3]
    altered = r.call(BLUE, "project_restore_plan", expected=409, **saved[0])
    assert altered["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # Denied publication earlier had no acceptance receipt and must now succeed
    # with its exact original message ID rather than replaying an invented row.
    current = await f.agent("bridge")
    published = await current.call(scoped(RED, "publish_record", text="Must not create an unknown target"), "unknown-publish-mid")
    assert published["record"]["publication"]["project_id"] == RED
    evidence.record("external-recovery-receipts-survive-hard-restart-and-cannot-cross-projects-or-invent-unauthorized-acceptance")
    return saved


async def known_missing(f, r, evidence):
    await r.initialize(BLUE)
    actor = await f.agent("bridge")
    blue = (await actor.call(scoped(BLUE, "publish_record", text="Unaffected project before target loss")))["record"]
    selected, checkpoint = route(f.file, RED)
    paths = [checkpoint, Path(str(checkpoint) + ".snapshot")]
    assert all(p.is_file() and not p.is_symlink() for p in paths), "Selected target lacks its complete accepted pair"
    original = {path: path.read_bytes() for path in paths}
    held = f.root / "missing-target-held"
    held.mkdir(mode=0o700)
    f.hard_stop()
    try:
        for path in paths:
            os.replace(path, held / path.name)
        await f.start()
        status = r.status(RED)
        assert status["availability"] == "recovery_required"
        before_config = copy.deepcopy(f.admin().call({"op": "config_get"})["config"])
        before_registry = registry(f.file)
        before_capacity = copy.deepcopy(status["capacity"])
        operation = copy.deepcopy(status["operation"])
        result = r.call(RED, "project_restore_plan", expected=409, mode="initialize", confirm=True,
            expected_revision=r.revision(), message_id="never-reinitialize-known-missing")
        assert result["error"]["code"] == "RESTORE_CONFLICT"
        after = r.status(RED)
        assert after["capacity"] == before_capacity and after["operation"] == operation
        assert f.admin().call({"op": "config_get"})["config"] == before_config
        assert registry(f.file) == before_registry
        assert not any(path.exists() for path in paths), "Missing target was recreated without a reviewed restore"
        denied = await f.raw("bridge", scoped(RED, "publish_record", text="Rejected while target missing"), "missing-publish-mid")
        unavailable_rpc(denied)
        current = await f.agent("bridge")
        healthy = await current.call(scoped(BLUE, "search", query="Unaffected project before target loss"))
        assert blue["publication"]["id"] in json.dumps(healthy)
        later = await current.call(scoped(BLUE, "publish_record", text="Unaffected project remains writable"))
        assert later["record"]["publication"]["project_id"] == BLUE
        evidence.record("cold-known-missing-target-never-reinitializes-or-accepts-data-and-other-project-remains-writable",
            target_route_generation=selected["generation"], original_pair_sha256={p.name: digest(raw) for p, raw in original.items()})
    finally:
        if f.process and f.process.poll() is None:
            f.hard_stop()
        for path in paths:
            offline = held / path.name
            if offline.exists():
                assert not path.exists(), "Runtime unexpectedly recreated an initialized missing target"
                os.replace(offline, path)
                assert path.read_bytes() == original[path]


async def main(args):
    evidence = Evidence(args.report, "project-recovery-admission")
    f = Fixture(args, initialize_projects=False)
    if args.hub:
        evidence.value["artifact_sha256"] = digest(args.hub.read_bytes())
    evidence.value["qualification"] = "pending-profile2.1-execution"
    try:
        await f.start()
        r = Recovery(f, args.recovery_schema)
        evidence.value["authored_recovery_schema_sha256"] = r.schema_sha256
        await admission(f, r, evidence)
        await known_missing(f, r, evidence)
        evidence.value["qualification"] = "admission-only; target-restore-and-allocator-matrix-separately-required"
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
