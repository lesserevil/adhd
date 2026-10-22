#!/usr/bin/env python3
"""Provider-neutral, explicitly bound OpenRig client for ADHD's existing A2A API."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict


def load_binding(path):
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("Binding file must be private (chmod 600)")
    config = json.loads(path.read_text())
    required = {"url", "server_id", "project_id", "agent_id", "token", "rig_id", "seat_id"}
    if set(config) != required or any(not isinstance(config[k], str) or not config[k].strip() for k in required):
        raise ValueError("Binding requires exactly url/server_id/project_id/agent_id/token/rig_id/seat_id")
    url = httpx.URL(config["url"])
    if url.scheme not in ("http", "https") or not url.host or url.username or url.password or url.query or url.fragment:
        raise ValueError("Binding URL must be an HTTP origin without credentials, query or fragment")
    if url.path not in ("", "/"):
        raise ValueError("Binding URL must be an HTTP origin")
    return config


def prepare(binding, command, message_id):
    if not isinstance(command, dict) or not isinstance(command.get("op"), str):
        raise ValueError("Command must be an object with an op")
    if "project_id" in command and command["project_id"] != binding["project_id"]:
        raise ValueError("Command project differs from the fixed binding")
    command = {**command, "project_id": binding["project_id"]}
    op = command["op"]
    observations = {"whoami", "list_projects", "list_subscriptions", "poll", "search", "get", "get_record",
                    "federation_directory", "identity_matches", "get_source_query", "get_federated_query",
                    "get_retrieval", "get_history_query", "get_archive_query", "get_retrieval_replay",
                    "get_retrieval_attempt", "list_retrieval_attempts"}
    if op not in observations and not message_id:
        raise ValueError("Mutation requires a stable --message-id; retain it with the identical command for retries")
    if op in {"publish", "publish_record", "send"}:
        identity = {key: binding[key] for key in ("server_id", "project_id", "rig_id", "seat_id", "agent_id")}
        provenance = {"version": 1, **identity}
        # An ordered JSON array is injective across delimiters and Unicode; do
        # not concatenate rig or seat names with ambiguous separators.
        canonical = json.dumps(["adhd-openrig-v1", *identity.values()], ensure_ascii=False, separators=(",", ":"))
        source_id = "openrig-v1-" + hashlib.sha256(canonical.encode()).hexdigest()
        command["data"] = {"openrig": provenance, "payload": command.get("data")}
        if op != "send":
            source = command.get("source", {})
            if not isinstance(source, dict) or set(source) - {"item_id", "uri"}:
                raise ValueError("OpenRig owns source.kind/id; caller may supply only item_id/uri")
            if not isinstance(source.get("item_id"), str) or not source["item_id"].strip():
                raise ValueError("Publication requires a stable source.item_id")
            command["source"] = {**source, "kind": "openrig", "id": source_id}
    return command


class WireResults:
    """Keep JSON number tokens intact after the official SDK validates a reply."""
    def __init__(self):
        self.values = []

    async def receive(self, response):
        await response.aread()
        try:
            value = json.loads(response.content)
            parts = value["result"]["message"]["parts"]
            if len(parts) == 1 and "data" in parts[0]:
                self.values.append(parts[0]["data"])
        except (ValueError, KeyError, TypeError):
            # Discovery and errors are parsed by the SDK; neither is an action
            # success. Never turn a transport/error response into a result.
            pass


async def exchange(client, wire, command, message_id=None):
    message = new_text_message(json.dumps(command, ensure_ascii=False), role=Role.ROLE_USER)
    message.message_id = message_id or str(uuid4())
    values = []
    before = len(wire.values)
    async for event in client.send_message(SendMessageRequest(message=message)):
        value = MessageToDict(event)
        values.append(value["message"]["parts"][0]["data"])
    if len(values) != 1 or len(wire.values) != before + 1:
        raise ValueError("Expected exactly one A2A response")
    # Protobuf Struct changes int tokens to doubles. Return the corresponding
    # raw HTTP JSON only after send_message has completed SDK validation; never
    # globally coerce floats because a user payload's 1.0 must remain a float.
    return wire.values[-1]


async def run(args):
    binding = load_binding(args.binding)
    command = json.loads(args.command_file.read_text() if args.command_file else args.command)
    command = prepare(binding, command, args.message_id)
    wire = WireResults()
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + binding["token"], "A2A-Version": "1.0"},
                                 event_hooks={"response": [wire.receive]}, timeout=15) as http:
        client = await create_client(agent=binding["url"], client_config=ClientConfig(
            streaming=False, httpx_client=http, supported_protocol_bindings=["JSONRPC"]))
        try:
            identity = await exchange(client, wire, {"op": "whoami", "project_id": binding["project_id"]})
            directory = await exchange(client, wire, {"op": "federation_directory", "project_id": binding["project_id"]})
            if identity.get("agent_id") != binding["agent_id"] or identity.get("project_id") != binding["project_id"]:
                raise ValueError("Authenticated identity differs from binding")
            if directory.get("server_id") != binding["server_id"] or directory.get("project_id") != binding["project_id"]:
                raise ValueError("Server/project identity differs from binding")
            result = await exchange(client, wire, command, args.message_id)
            print(json.dumps(result, ensure_ascii=False))
        finally:
            await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True, help="Private fixed rig/seat/project/credential binding")
    parser.add_argument("--message-id", help="Stable A2A retry identity, required for mutations")
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--command-file", type=Path, help="JSON command; keep event content off process argv")
    commands.add_argument("--command", help="JSON command (visible to local processes)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # SDK/HTTP exceptions may contain credentials or content. Keep those out
        # of stderr; transport acceptance retains private hub logs separately.
        print(json.dumps({"error": "OPENRIG_HUB_FAILED", "failure_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
