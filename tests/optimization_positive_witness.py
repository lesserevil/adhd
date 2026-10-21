#!/usr/bin/env python3
"""One manifest-bound live optimizer witness, with a hard provider I/O budget.

--check-plan performs no startup or network I/O. Running requires the separately
reviewed manifest digest. Rejected cohorts remain rejected; no substitutions,
retries, alternate identities, prompt changes or confidence changes are made.
"""
import asyncio
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time

import httpx

from multi_support import Evidence, Fixture, arguments, scoped
from protocol_acceptance import ByteValidator


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class BudgetRelay:
    def __init__(self, upstream, budget, log):
        self.upstream, self.budget, self.log = upstream, budget, log
        self.deadline = time.monotonic() + budget["maximum_wall_clock_seconds"]
        self.lock = threading.Condition()
        self.count = self.inflight = self.denied = 0
        self.closed = False
        self.exhausted = False
        relay = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                with relay.lock:
                    remaining = relay.deadline - time.monotonic()
                    if relay.closed or remaining <= 0 or relay.count >= budget["maximum_upstream_http_posts"]:
                        relay.denied += 1
                        relay.exhausted = True
                        self.reply(503, b'{"error":"predeclared provider budget exhausted"}')
                        return
                    relay.count += 1
                    sequence = relay.count
                    relay.inflight += 1
                row = {"sequence": sequence, "request_sha256": digest(raw), "request_json": raw.decode()}
                started = time.monotonic()
                try:
                    # A new client with no retry transport: exactly one upstream
                    # attempt per reserved unit, including failures/timeouts.
                    with httpx.Client(follow_redirects=False, trust_env=False,
                                      timeout=max(.001, min(10, remaining))) as http:
                        response = http.post(relay.upstream, content=raw, headers={"Content-Type": "application/json"})
                    body, status = response.content, response.status_code
                    row.update(http_status=status, response_sha256=digest(body), response_text=body.decode())
                except Exception as error:
                    body, status = b'{"error":"provider transport failed"}', 502
                    row.update(transport_error_type=type(error).__name__)
                finally:
                    row["elapsed_seconds"] = time.monotonic() - started
                    with relay.lock:
                        with relay.log.open("a") as output:
                            output.write(json.dumps(row) + "\n")
                        relay.inflight -= 1
                        relay.lock.notify_all()
                self.reply(status, body)
            def reply(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port) + "/v1/systemone"

    def check(self):
        assert not self.exhausted and time.monotonic() < self.deadline, "Frozen provider budget exhausted"

    def close(self):
        with self.lock:
            self.closed = True
            self.lock.wait_for(lambda: self.inflight == 0, timeout=12)
            assert self.inflight == 0, "Provider exchange did not settle within its reserved timeout"
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def verify_plan(args):
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    assert manifest["status"] == "FROZEN_FOR_HARNESS_REVIEW_NOT_EXECUTED"
    assert len(manifest["cases"]) == 7
    assert [c["cohort"] for c in manifest["cases"]] == ["training"]*2 + ["held_out"]*3 + ["regression"]*2
    assert [c["gold"]["expectation"] for c in manifest["cases"]] == ["supported"]*4 + ["no_evidence", "supported", "conflicting"]
    assert manifest["provider_budget"]["maximum_upstream_http_posts"] == 256
    assert manifest["provider_budget"]["maximum_wall_clock_seconds"] == 900
    assert manifest["provider_budget"]["relay_retries"] == 0
    assert manifest["configuration"]["history"] == {"request_bytes": 8192, "min_confidence_ppm": 500000}
    assert manifest["configuration"]["optimization"]["max_variants"] == 8
    actual_order = [case["id"]+":"+record["record_key"] for case in manifest["cases"] for record in case["records"]]
    assert actual_order == manifest["publication_order"] and len(set(actual_order)) == 21
    for case in manifest["cases"]:
        assert [record["record_key"] for record in case["records"]] == ["0", "1", "2"]
        assert case["gold"]["confirmed"] is True
        assert case["gold"]["support_record_keys"] == ([] if case["gold"]["expectation"] == "no_evidence" else ["0", "2"])
    if args.hub:
        assert digest(args.hub.read_bytes()) == manifest["target"]["artifact_sha256"]
    elif args.image:
        assert args.image == manifest["target"]["image_config_identity"]
    else:
        raise AssertionError("Witness requires an owned exact --hub or --image")
    return manifest, digest(raw)


async def checks(f, evidence, manifest, relay):
    project, actor = manifest["target"]["project_id"], manifest["target"]["agent_id"]
    agent, admin = await f.agent(actor), f.admin()
    schema = admin.client.get("/protocol/schema")[1]
    validator = ByteValidator({"$defs": schema["$defs"], "$ref": "#/$defs/OptimizationProposal"})
    def management(op, mutation=False, **fields):
        return admin.call(scoped(project, op, **fields), mutation=mutation)
    async def call(op, **fields):
        relay.check()
        return await agent.call(scoped(project, op, **fields))
    async def wait(fn):
        while True:
            relay.check()
            value = fn()
            if asyncio.iscoroutine(value):
                value = await value
            if value:
                return value
            await asyncio.sleep(.1)
    async def ready():
        async def observe():
            index = (await call("retrieval_index"))["index"]
            return index if index["status"] == "ready" else None
        return await wait(observe)
    captures = {}
    async def publish_case(case):
        resolved = {}
        for original in case["records"]:
            fields = copy.deepcopy(original)
            key = fields.pop("record_key")
            if fields["context"] is None:
                fields.pop("context")
            else:
                for link in fields["context"]["links"]:
                    link["publication_id"] = resolved[link.pop("target_record_key")]
            record = (await call("publish_record", **fields))["record"]
            resolved[key] = record["publication"]["id"]
            captures[case["id"]+":"+key] = {"record": record, "sha256": digest(canonical(record))}
        # This immutable capture precedes the first Archive/model use, including
        # server-assigned ingestion times and IDs. No metadata selection occurs.
        evidence.value["frozen_originals"] = captures
        evidence.write()
        await ready()
        return resolved
    async def attempt(case, resolved):
        query = (await call("query_archive", question=case["question"], scope=case["scope"], complete=case["complete"]))["query"]
        evidence.value.setdefault("owned_archive_query_ids", []).append(query["id"])
        evidence.write()
        async def finished():
            value = (await call("get_archive_query", query_id=query["id"]))["query"]
            return value if value["status"] != "pending" else None
        query = await wait(finished)
        assert query["status"] == "completed", (case["id"], query["status"], query.get("error"))
        async def captured():
            rows = (await call("list_retrieval_attempts", limit=64))["items"]
            return next((row for row in rows if row["archive_query_id"] == query["id"]), None)
        row = await wait(captured)
        label = copy.deepcopy(case["gold"])
        label["support_ids"] = [resolved[k] for k in label.pop("support_record_keys")]
        label["cohort"] = case["cohort"]
        management("save_retrieval_label", True, attempt_id=row["id"], expected_label_revision=0, label=label)
        evidence.value.setdefault("case_captures", []).append({"id": case["id"], "query": query,
            "attempt_id": row["id"], "independent_gold": label})
        evidence.write()
        return row["id"]
    async def proposal_settled(id):
        def observe():
            value = management("index_proposal", proposal_id=id, limit=64)["proposal"]
            return value if value["status"] != "pending" else None
        result = await wait(observe)
        validator.validate(result)
        evidence.value["latest_proposal"] = result
        evidence.write()
        return result

    base_index = await ready()
    training_sources = [await publish_case(case) for case in manifest["cases"][:2]]
    config = manifest["configuration"]
    admin.call({"op": "config_update", "patch": {"matcher": {"url": relay.url,
        "model": manifest["target"]["model"]}, "history": config["history"],
        "archive": config["archive"], "optimization": config["optimization"]}}, mutation=True)
    evidence.value["resolved_policies_before_inference"] = admin.call({"op": "config_get"})["config"]
    evidence.write()
    training = [await attempt(case, resolved) for case, resolved in zip(manifest["cases"][:2], training_sources)]
    proposal = management("propose_index", True, training_attempt_ids=training)["proposal"]
    evidence.value["proposal_id"] = proposal["id"]
    proposal = await proposal_settled(proposal["id"])
    assert proposal["status"] == "awaiting_evaluation", (proposal["status"], proposal.get("error"))
    assert proposal["held_out_attempt_ids"] == proposal["regression_attempt_ids"] == []
    evidence.value["training_freeze"] = copy.deepcopy(proposal)
    evidence.record("training-winner-frozen-before-any-final-original-publication")
    final_sources = [await publish_case(case) for case in manifest["cases"][2:]]
    final = [await attempt(case, resolved) for case, resolved in zip(manifest["cases"][2:], final_sources)]
    management("evaluate_index", True, proposal_id=proposal["id"], held_out_attempt_ids=final[:3], regression_attempt_ids=final[3:])
    proposal = await proposal_settled(proposal["id"])
    if proposal["status"] != "qualified":
        evidence.value["qualification"] = "not-qualified"
        raise AssertionError("Frozen independent cohort failed: " + str(proposal.get("error")))
    evaluation = proposal["evaluation"]
    assert evaluation["passed"] and evaluation["mean_recall_gain_ppm"] > 0
    assert evaluation["answer_failures"] == evaluation["answer_regressions"] == evaluation["false_supports"] == 0
    assert evaluation["total_calls_delta"] <= 0 and evaluation["total_bytes_delta"] <= 0
    finals = [row for row in proposal["cases"] if row["cohort"] != "training"]
    assert len(finals) == 5 and all(row["baseline"]["answer_pass"] and row["candidate"]["answer_pass"]
        and row["comparison"]["retrieval_gain_ppm"] >= 0 for row in finals)
    assert proposal["winner_identity"] == evidence.value["training_freeze"]["winner_identity"]
    assert proposal["build"]["status"] == "ready" and proposal["index_manifest"]["excluded"] == 0
    evidence.record("all-preregistered-final-strata-pass-unchanged-answer-recall-cost-and-completeness-gates")

    previous = await ready()
    management("promote_index", True, proposal_id=proposal["id"], expected_selection_revision=int(previous["selection"]["revision"]))
    selected = await ready()
    assert selected["selection"]["applied"] and selected["selection"]["qualification_current"]
    assert selected["active"]["recipe"] == selected["selection"]["effective_recipe"]
    assert selected["previous"]["recipe"] == previous["selection"]["effective_recipe"]
    later = manifest["ordinary_post_promotion"]
    subscription = (await call("subscribe", **later["subscription"]))["subscription"]
    record = (await call("publish_record", **later["record"]))["record"]
    async def delivered():
        return next((d for d in (await call("poll"))["deliveries"] if d.get("publication_id") == record["publication"]["id"]), None)
    delivery = await wait(delivered)
    assert any(match["subscription_id"] == subscription["id"] for match in delivery["matches"])
    await call("ack", delivery_ids=[delivery["id"]])
    caught = await ready()
    assert caught["selection"]["applied"] and caught["previous"]["recipe"] == previous["selection"]["effective_recipe"]
    evidence.record("actual-promotion-filtered-delivery-and-catchup-preserve-protected-rollback")
    admin.call({"op": "config_update", "patch": {"optimization": {"enabled": False}}}, mutation=True)
    rollback = management("rollback_index", True, expected_selection_revision=int(caught["selection"]["revision"]))["proposal"]
    rollback = await proposal_settled(rollback["id"])
    assert rollback["status"] == "promoted"
    restored = await ready()
    assert restored["selection"]["effective_recipe"] == base_index["selection"]["effective_recipe"]
    admin.call({"op": "config_update", "patch": {"retrieval": {"recipe": base_index["selection"]["base_recipe"]}}}, mutation=True)
    reset = await ready()
    assert not reset["selection"]["applied"]
    f.hard_stop()
    await f.start()
    restarted = await ready()
    assert restarted["selection"] == reset["selection"]
    assert not any(d["id"] == delivery["id"] for d in (await call("poll"))["deliveries"])
    for saved in captures.values():
        got = (await call("get_record", publication_id=saved["record"]["publication"]["id"]))["record"]
        assert got == saved["record"]
    evidence.value["qualification"] = "positive-scoped-witness"
    evidence.record("disabled-rollback-explicit-reset-and-hard-restart-preserve-originals-and-acknowledgements")


async def main(args):
    manifest, manifest_hash = verify_plan(args)
    if args.check_plan:
        print(json.dumps({"manifest_sha256": manifest_hash, "harness_sha256": digest(Path(__file__).read_bytes()),
                          "provider_calls": 0, "runtime_started": False, "valid": True}))
        return
    assert args.approved_manifest_sha256 == manifest_hash, "Explicit reviewed frozen manifest digest required"
    assert not args.with_model, "Use only the approved existing live provider through the budget relay"
    assert not args.report.exists(), "Never overwrite or resume a fixed witness"
    f = Fixture(args)
    assert not f.file.exists(), "Never reuse prior witness state"
    evidence = Evidence(args.report, "independent-positive-optimizer-witness")
    evidence.value.update(manifest_sha256=manifest_hash, harness_sha256=digest(Path(__file__).read_bytes()),
        artifact_sha256=manifest["target"]["artifact_sha256"], qualification="none", manifest=manifest,
        limitations=["Original capsule-R regression remains failed; this independent cohort does not replace its result."])
    relay = BudgetRelay(manifest["target"]["model_url"], manifest["provider_budget"], f.root/"provider-exchanges.jsonl")
    target = manifest["target"]
    f.tokens = {target["agent_id"]: secrets.token_urlsafe(32)}
    f.config.update(server_id=target["server_id"], project_id=target["project_id"], agents=f.tokens,
        projects=[{"id": target["project_id"], "name": "Frozen independent optimizer witness", "status": "active", "description": "Synthetic public acceptance sources", "settings": {}}],
        agent_projects={target["agent_id"]: [target["project_id"]]}, matcher=None)
    f.config["optimization"] = manifest["configuration"]["optimization"]
    error = None
    try:
        await f.start()
        f.bind_evidence(evidence)
        await asyncio.wait_for(checks(f, evidence, manifest, relay), timeout=max(.01, relay.deadline-time.monotonic()))
    except BaseException as caught:
        error = caught
        # Revoke further inference before public cancellation/cleanup. A failed
        # cohort is not silently resumed under a new proposal or budget.
        with relay.lock:
            relay.closed = True
        try:
            admin = f.admin()
            for query_id in evidence.value.get("owned_archive_query_ids", []):
                try:
                    admin.call(scoped(target["project_id"], "cancel_query_job", query_id=query_id), mutation=True)
                except Exception as cleanup_error:
                    evidence.value.setdefault("archive_cancellation_error_types", []).append(type(cleanup_error).__name__)
            pid = evidence.value.get("proposal_id")
            if pid:
                admin.call(scoped(target["project_id"], "cancel_index_proposal", proposal_id=pid), mutation=True)
            admin.call({"op": "config_update", "patch": {"matcher": None, "optimization": {"enabled": False}}}, mutation=True)
        except Exception as cleanup_error:
            evidence.value["cancellation_error_type"] = type(cleanup_error).__name__
    finally:
        relay.close()
        await f.close()
        f.bind_evidence(evidence)
        evidence.value["provider_budget_observed"] = {"upstream_http_posts": relay.count, "denied_requests": relay.denied,
            "exhausted": relay.exhausted, "exchange_log_sha256": digest(relay.log.read_bytes()) if relay.log.exists() else None}
        evidence.finish(error)
    if error:
        raise error


if __name__ == "__main__":
    parser = arguments(__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check-plan", action="store_true")
    parser.add_argument("--approved-manifest-sha256")
    asyncio.run(main(parser.parse_args()))
