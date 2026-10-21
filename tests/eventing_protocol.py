#!/usr/bin/env python3
"""Validate authored multi/eventing vectors independently against served schema.

Schema validation and runtime authorization are separate evidence. Valid vectors
are schema checks, not fabricated successful operations against nonexistent IDs.
Invalid agent vectors also reach the actual A2A boundary. The live SDK stream
round-trip validates its returned subscription/publication/delivery structures.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import httpx
import jsonschema
from openapi_spec_validator import validate as validate_openapi

from multi_support import arguments, execute, poll_until, reject, scoped
from protocol_acceptance import ByteValidator, strict_json


def vector_definition(vector):
    if "command" in vector:
        return "agent_" + vector["command"]["op"], vector["command"]
    if "request" in vector:
        return "PeerV2_" + vector["request"]["op"], vector["request"]
    return "Match", vector["record"]


async def checks(f, evidence):
    vectors_bytes = f.args.vectors.read_bytes()
    vectors = strict_json(vectors_bytes.decode())
    async with httpx.AsyncClient() as http:
        response = await http.get(f.base + "/protocol/schema")
        assert response.status_code == 200
        schema_bytes = response.content
        schema = strict_json(schema_bytes.decode())
        response = await http.get(f.base + "/protocol/openapi")
        assert response.status_code == 200
        openapi = strict_json(response.text)
    jsonschema.Draft202012Validator.check_schema(schema)
    validate_openapi(openapi)
    definitions = schema["$defs"]

    def validate(definition, value):
        assert definition in definitions, "Missing published definition " + definition
        ByteValidator({"$defs": definitions, "$ref": "#/$defs/" + definition}).validate(value)

    for kind, expected in (("valid", True), ("invalid", False)):
        for vector in vectors[kind]:
            definition, value = vector_definition(vector)
            assert definition in definitions, "Missing published definition " + definition
            try:
                validate(definition, value)
                accepted = True
            except jsonschema.ValidationError:
                accepted = False
            assert accepted == expected, "Published schema contradicts authored vector: " + vector["name"]
    evidence.record("authored-valid-invalid-agent-peer-v2-and-reason-vectors-independently-validated",
                    valid=len(vectors["valid"]), invalid=len(vectors["invalid"]),
                    vectors_sha256=hashlib.sha256(vectors_bytes).hexdigest(),
                    served_schema_sha256=hashlib.sha256(schema_bytes).hexdigest())

    for vector in vectors["invalid"]:
        if "command" not in vector:
            continue
        command = copy.deepcopy(vector["command"])
        command["project_id"] = "project-red"
        error = reject(await f.raw("red-a", command))
        assert error["code"] == -32602, "Malformed command must fail before resource lookup"
    evidence.record("invalid-agent-vectors-also-rejected-at-actual-a2a-runtime-boundary")

    a, b = await f.agent("red-a"), await f.agent("red-b")
    subscribe = scoped("project-red", "subscribe", mode="raw")
    validate("agent_subscribe", subscribe)
    result = await b.call(subscribe)
    validate("result_subscribe", result)
    sub = result["subscription"]
    publication = await a.call(scoped("project-red", "publish", text="Schema-qualified live broker event"))
    validate("result_publish", publication)
    rows = await poll_until(b, "project-red", {publication["publication"]["id"]}, f.args.deadline)
    result = await b.call(scoped("project-red", "poll"))
    validate("result_poll", result)
    for row in rows:
        for match in row["matches"]:
            validate("Match", match)
            assert set(match) == {"subscription_id", "subscription_revision", "mode"}
    edit = scoped("project-red", "update_subscription", subscription_id=sub["id"],
                  expected_revision=sub["revision"], mode="raw", paused=True)
    validate("agent_update_subscription", edit)
    result = await b.call(edit)
    validate("result_update_subscription", result)
    reject(await f.raw("red-b", edit))
    evidence.record("live-sdk-publication-subscription-raw-reason-poll-and-revisioned-edit-conformance")


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--vectors", type=Path, default=Path("docs/protocol/multi-eventing-examples.json"))
    asyncio.run(execute(parser.parse_args(), "adhd/multi-eventing-protocol@1", checks))
