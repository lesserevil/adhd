#!/usr/bin/env python3
"""Real Kafka lost-produce-response and durable logical dedup qualification.

The gateway forwards actual requests to --eventing-rest-url and reads the real
response before selectively dropping it. It never invents a successful broker
reply, a consumed record or an offset. Only the disposable fixture uses it.
"""
import asyncio
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from multi_support import Evidence, Fixture, arguments, poll_until, scoped


class LostReplyGateway:
    def __init__(self, upstream):
        self.upstream = upstream.rstrip("/")
        self.produces = []
        self.dropped = 0
        self.blocked = False
        self.lock = threading.Lock()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_GET(self):
                self.forward()

            def do_POST(self):
                self.forward()

            def do_DELETE(self):
                self.forward()

            def forward(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if fixture.blocked:
                    self.send_error(503)
                    return
                headers = {key: value for key, value in self.headers.items()
                           if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}}
                with httpx.Client(follow_redirects=False, trust_env=False, timeout=10) as client:
                    try:
                        response = client.request(self.command, fixture.upstream + self.path,
                                                  content=body, headers=headers)
                    except httpx.HTTPError:
                        self.send_error(502)
                        return
                drop = False
                path = urlsplit(self.path).path
                if self.command == "POST" and path.startswith("/topics/") and response.is_success:
                    value, result = json.loads(body), response.json()
                    # This is observation of Kafka's actual acknowledgement,
                    # not treating HTTP200 alone as a successful produce.
                    assert result["offsets"] and all(
                        item.get("error_code") is None and item.get("error") is None
                        and type(item.get("offset")) is int and item["offset"] >= 0
                        for item in result["offsets"])
                    with fixture.lock:
                        fixture.produces.append({"path": path, "body": value, "ack": result})
                        if fixture.dropped == 0:
                            fixture.dropped += 1
                            drop = True
                if drop:
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.send_response(response.status_code)
                for key in ("Content-Type",):
                    if key in response.headers:
                        self.send_header(key, response.headers[key])
                self.send_header("Content-Length", str(len(response.content)))
                self.end_headers()
                try:
                    self.wfile.write(response.content)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


async def main(args):
    if args.rest_url:
        raise ValueError("Lost-reply qualification needs an owned --hub or --command to configure the forwarding gateway")
    gateway = LostReplyGateway(args.eventing_rest_url)
    local = copy.copy(args)
    local.eventing_rest_url = gateway.url
    f = Fixture(local)
    evidence = Evidence(args.report, "adhd/real-kafka-lost-reply@1")
    try:
        await f.start()
        a, b = await f.agent("red-a"), await f.agent("red-b")
        await b.call(scoped("project-red", "subscribe", mode="raw"))
        command = scoped("project-red", "publish", text="Real broker acknowledgement lost on transport",
                         source={"kind": "slack", "id": "fault-channel", "item_id": uuid4().hex})
        mid = uuid4().hex
        result = await a.call(command, mid)
        publication = result["publication"]
        rows = await poll_until(b, "project-red", {publication["id"]}, args.deadline + 10)
        assert sum(d.get("publication_id") == publication["id"] for d in rows) == 1
        deadline = time.monotonic() + args.deadline
        while len(gateway.produces) < 2 and time.monotonic() < deadline:
            await asyncio.sleep(.1)
        assert gateway.dropped == 1
        assert len(gateway.produces) >= 2, "Lost real broker reply never retried through durable outbox"
        observed = [row for row in gateway.produces
                    if row["body"]["records"][0]["value"]["publication_id"] == publication["id"]]
        assert len(observed) >= 2
        events = [row["body"]["records"][0]["value"] for row in observed]
        assert all(event == events[0] for event in events), "Broker retry mutated event identity or original"
        event = events[0]
        assert set(event) == {"schema_version", "event_id", "server_id", "project_id", "project_sequence",
                              "publication_id", "author_id", "created_at", "publication"}
        assert event["publication"] == publication
        assert event["project_id"] == "project-red"
        assert event["schema_version"] == 1 and type(event["project_sequence"]) is int
        assert event["project_sequence"] > 0
        for secret in f.tokens.values():
            assert secret not in json.dumps(event)
        assert f.model is None or f.model.calls == 0
        offsets = [row["ack"]["offsets"][0]["offset"] for row in observed]
        assert len(set(offsets)) >= 2, "The experiment did not actually create physical Kafka duplicates"
        evidence.record("real-produce-ack-lost-physical-duplicates-logically-deduplicated",
                        actual_produce_acks=len(observed), distinct_offsets=len(set(offsets)))

        assert await a.call(command, mid) == result
        await b.call(scoped("project-red", "ack", delivery_ids=[d["id"] for d in rows]))
        f.hard_stop()
        await f.start()
        assert await a.call(command, mid) == result
        assert (await b.call(scoped("project-red", "get", publication_id=publication["id"])))["publication"] == publication
        await asyncio.sleep(.5)
        assert not (await b.call(scoped("project-red", "poll")))["deliveries"]
        evidence.record("logical-delivery-and-source-retry-ack-survive-process-kill-and-broker-replay")
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()
        gateway.close()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
