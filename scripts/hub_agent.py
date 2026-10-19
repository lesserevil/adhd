#!/usr/bin/env python3
"""Send a command to Agentic Distributed Harness Depot (ADHD) using the official A2A client SDK."""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict


async def run(args):
    config = json.loads(Path(args.config).read_text())
    token = config["agents"].get(args.agent)
    if not token:
        raise SystemExit("Agent is not present in the selected private configuration")
    command = json.loads(args.command)
    if not isinstance(command, dict):
        raise SystemExit("Command must be a JSON object")
    url = args.url or config.get("public_url") or f"http://{config.get('host', '127.0.0.1')}:{config.get('port', 8766)}"
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token,
                                          "A2A-Version": "1.0"}, timeout=10) as http:
        client = await create_client(agent=url, client_config=ClientConfig(
            streaming=False, httpx_client=http, supported_protocol_bindings=["JSONRPC"]))
        try:
            # JSON text keeps integer-valued command fields intact through protobuf.
            message = new_text_message(json.dumps(command), role=Role.ROLE_USER)
            message.message_id = args.message_id or str(uuid4())
            async for event in client.send_message(SendMessageRequest(message=message)):
                response = MessageToDict(event)
                print(json.dumps(response["message"]["parts"][0]["data"], indent=2))
        finally:
            await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="literate.hub.local.json")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--url")
    parser.add_argument("--message-id", help="Reuse for a retry of the same mutation")
    parser.add_argument("command", help="Hub command as a JSON object")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
