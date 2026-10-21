#!/usr/bin/env python3
"""Cross-project evidence, feedback, paired replay and optimizer scope matrix.

Uses actual A2A/Kafka and an independently controlled typed evaluator. Equal
workflow ID strings are legitimate local names: identity includes explicit project.
"""
import asyncio
import copy
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time
import threading
from uuid import uuid4

import httpx

from archive_support import ArchiveFixture
from multi_support import Evidence, Fixture, MEMBERSHIPS, arguments, scoped


RED, BLUE = "project-red", "project-blue"
MARK = {RED: "RED-EVIDENCE-ONLY", BLUE: "BLUE-EVIDENCE-ONLY"}


def contextual_fixture():
    """Typed ArchiveFixture with explicit candidate-content relevance cases.

    This is authored deterministic routing evidence, not semantic model quality.
    The original endpoint records every exchange and authors the other typed decisions.
    """
    model = ArchiveFixture()
    upstream, original_close = model.url, model.close
    model.context_roots = set()
    questions = {"Was specimen " + value + " present?" for value in ("Quartz", "Obsidian", "Jade", "Opal")}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            self.respond(200, {"ready": True})
        def respond(self, status, value):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            response = httpx.post(upstream, json=body, timeout=5, trust_env=False)
            result = response.json()
            if response.status_code == 200 and "useful" in body["questions"] and body.get("state", {}).get("question") in questions:
                supplied = body["state"]["candidate"]["fragments"]
                relevant = any(f["origin_publication_id"] in model.context_roots for f in supplied)
                result["answers"]["useful"]["noul"] = .99 if relevant else .01
            if response.status_code == 200 and body.get("state", {}).get("question") == "Was specimen Opal present?":
                for key, choice in (("assessment", "no_evidence"), ("answer", "unknown")):
                    if key in body["questions"]:
                        result["answers"][key] = {"type": "choice", "choice": choice, "confidence": 1.0,
                            "probabilities": {label: float(label == choice) for label in body["questions"][key]["criteria"]}}
            self.respond(response.status_code, result)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    model.url = "http://127.0.0.1:" + str(server.server_port) + "/v1/systemone"
    def close():
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        original_close()
    model.close = close
    return model


async def wait(fn, message, seconds=35):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = fn()
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return value
        await asyncio.sleep(.05)
    raise AssertionError(message)


class Matrix:
    def __init__(self, f, model):
        self.f, self.model = f, model
        self.actor = None

    async def call(self, project, op, mid=None, **fields):
        return await self.actor.call(scoped(project, op, **fields), mid)

    def admin(self, project, op, mutation=False, mid=None, expected=200, **fields):
        # Official SDK Struct numbers are doubles. Only these declared revision
        # fields are converted when crossing back to raw Admin JSON; arbitrary
        # original payload numbers are never rewritten.
        for key in ("expected_label_revision", "expected_selection_revision"):
            if key in fields:
                fields[key] = int(fields[key])
        body = scoped(project, op, **fields)
        client = self.f.admin()
        if mutation:
            revision = client.call({"op": "config_get"})["config_revision"]
            body.update(expected_revision=revision, confirm=True, message_id=mid or uuid4().hex)
        return client.client.api(body, expected=expected)

    async def error(self, project, op, code="NOT_FOUND", actor="bridge", **fields):
        response = await self.f.raw(actor, scoped(project, op, **fields))
        value = response.json()
        assert "error" in value, "Crossed ownership/scope action unexpectedly succeeded"
        metadata = value["error"].get("data", [])
        assert any(item.get("reason") == code or item.get("metadata", {}).get("code") == code for item in metadata), value["error"]

    async def finish(self, project, op, query):
        async def observe():
            value = (await self.call(project, op, query_id=query["id"]))["query"]
            return value if value["status"] != "pending" else None
        value = await wait(observe, "Scoped evidence query did not settle")
        assert value["status"] == "completed", (op, value["status"], value.get("error"))
        assert value["project_id"] == project and value["owner_id"] == "bridge"
        return value

    async def ready(self, project):
        async def observe():
            index = (await self.call(project, "retrieval_index"))["index"]
            return index if index["status"] == "ready" else None
        return await wait(observe, "Project retrieval index did not catch up")

    async def record(self, project, text, tag="evidence", mid=None, **fields):
        return (await self.call(project, "publish_record", mid, text=text, information_type=tag, **fields))["record"]

    async def attempt(self, project, query):
        async def observe():
            rows = (await self.call(project, "list_retrieval_attempts", limit=64))["items"]
            return next((a for a in rows if a["archive_query_id"] == query["id"] and a["run"] == query["run"]), None)
        summary = await wait(observe, "Archive attempt did not capture")
        return (await self.call(project, "get_retrieval_attempt", attempt_id=summary["id"]))["attempt"]

    def label(self, project, attempt, ids, cohort, mid=None):
        return self.admin(project, "save_retrieval_label", True, mid, attempt_id=attempt["id"],
            expected_label_revision=attempt["label_revision"], label={"expectation": "supported", "support_ids": ids,
                "cohort": cohort, "tags": [], "note": "Independent project-scoped authored gold", "confirmed": True})


async def checks(m, evidence):
    f = m.f
    m.actor = await f.agent("bridge")
    records, private = {}, {}
    for project, recipient in ((RED, "red-b"), (BLUE, "blue-b")):
        private[project] = (await m.call(project, "send", "shared-private-mid", recipient_id=recipient,
            text="PRIVATE-ADDRESSED-SENTINEL-" + project))["delivery"]
        records[project] = await m.record(project, MARK[project] + " original capsule report", mid="same-source-message-id",
            source={"kind": "fixture", "id": "same-source", "item_id": "same-event"},
            context={"links": [{"relation": "related", "publication_id": private[project]["id"]}]})
        await m.ready(project)
        await wait(lambda: m.admin(project, "eventing_status")["pending_events"] == 0, "Original did not traverse real Kafka")
    async with httpx.AsyncClient(trust_env=False) as http:
        cluster = await http.get(f.args.eventing_rest_url.rstrip("/") + "/v3/clusters")
        cluster.raise_for_status()
        evidence.value["broker_cluster_id"] = cluster.json()["data"][0]["cluster_id"]
    assert records[RED]["publication"]["id"] != records[BLUE]["publication"]["id"]
    evidence.record("same-bridge-source-item-and-message-ids-retain-independent-project-originals-and-private-addressed-state")

    questions = {}
    question = "Which capsule report was explicitly recorded?"
    families = (("query_history", "get_history_query", "cancel_history_query", "continue_history_query"),
                ("retrieve", "get_retrieval", "cancel_retrieval", "continue_retrieval"),
                ("query_archive", "get_archive_query", "cancel_archive_query", "continue_archive_query"))
    for create, get, cancel, continuation in families:
        initial = {}
        for project in (RED, BLUE):
            command = {"question": question, "scope": {"information_type": "evidence"}}
            initial[project] = (await m.call(project, create, "same-" + create, **command))["query"]
            assert initial[project]["project_id"] == project
            assert (await m.call(project, create, "same-" + create, **command))["query"] == initial[project]
        if create == "query_history":
            frozen = {p: initial[p]["snapshot"]["watermark"] for p in (RED, BLUE)}
            later = await m.record(RED, MARK[RED] + " later outside frozen watermark")
            assert (await m.ready(RED))["publication_watermark"] > frozen[RED]
            assert (await m.ready(BLUE))["publication_watermark"] == frozen[BLUE]
        for project, other in ((RED, BLUE), (BLUE, RED)):
            q = await m.finish(project, get, initial[project])
            assert MARK[other] not in json.dumps(q) and "PRIVATE-ADDRESSED-SENTINEL" not in json.dumps(q)
            if create == "query_history" and project == RED:
                assert later["publication"]["id"] not in json.dumps(q)
            questions[project, create] = q
            for op in (get, cancel, continuation):
                await m.error(project, op, actor="red-b" if project == RED else "blue-b", query_id=q["id"])
            # A colliding string must resolve only the local query. Otherwise it
            # is a foreign resource and must be NOT_FOUND in this explicit scope.
            if initial[other]["id"] == q["id"]:
                own = (await m.call(project, get, query_id=initial[other]["id"]))["query"]
                assert own["project_id"] == project and MARK[other] not in json.dumps(own)
            else:
                for op in (get, cancel, continuation):
                    await m.error(project, op, query_id=initial[other]["id"])
        evidence.record(create + "-same-message-question-explicit-context-ownership-foreign-get-cancel-continue-and-frozen-evidence")

    attempts = {p: await m.attempt(p, questions[p, "query_archive"]) for p in (RED, BLUE)}
    assert attempts[RED]["id"] != attempts[BLUE]["id"]
    for project, other in ((RED, BLUE), (BLUE, RED)):
        await m.error(project, "get_retrieval_attempt", attempt_id=attempts[other]["id"])
        await m.error(project, "replay_retrieval", attempt_id=attempts[other]["id"], candidate_recipe={})
        bad = m.admin(project, "save_retrieval_label", True, expected=400,
            attempt_id=attempts[project]["id"], expected_label_revision=0,
            label={"expectation": "supported", "support_ids": [records[other]["publication"]["id"]],
                   "cohort": "training", "tags": [], "note": "Foreign original must be rejected", "confirmed": True})
        assert bad["error"]["code"] == "INVALID_PARAMS"
    m.label(RED, attempts[RED], [records[RED]["publication"]["id"]], "training", "same-label-mid")
    m.label(BLUE, attempts[BLUE], [records[BLUE]["publication"]["id"]], "held_out", "same-label-mid")
    red_clusters = m.admin(RED, "feedback_cohorts")["items"]
    blue_clusters = m.admin(BLUE, "feedback_cohorts")["items"]
    assert {x["cohort"] for x in red_clusters} == {"training"}
    assert {x["cohort"] for x in blue_clusters} == {"held_out"}
    assert all(attempts[BLUE]["id"] not in c["attempt_ids"] for c in red_clusters)
    assert all(attempts[RED]["id"] not in c["attempt_ids"] for c in blue_clusters)
    evidence.record("feedback-attempt-label-gold-and-same-question-cohort-keys-are-project-local-not-server-global")

    replays = {}
    for project in (RED, BLUE):
        command = {"attempt_id": attempts[project]["id"], "candidate_recipe": {"context_depth": 2}}
        started = (await m.call(project, "replay_retrieval", "same-replay-mid", **command))["query"]
        assert (await m.call(project, "replay_retrieval", "same-replay-mid", **command))["query"] == started
        replays[project] = await m.finish(project, "get_retrieval_replay", started)
        assert replays[project]["attempt_id"] == attempts[project]["id"]
        other = BLUE if project == RED else RED
        assert MARK[other] not in json.dumps(replays[project])
        for op in ("get_retrieval_replay", "cancel_retrieval_replay", "continue_retrieval_replay"):
            await m.error(project, op, actor="red-b" if project == RED else "blue-b", query_id=started["id"])
    await m.error(BLUE, "replay_retrieval", code="HELD_OUT_EXPOSED", attempt_id=attempts[BLUE]["id"], candidate_recipe={"context_depth": 3})
    # Blue's spent held-out cohort must not constrain another Red candidate.
    red_again = (await m.call(RED, "replay_retrieval", attempt_id=attempts[RED]["id"], candidate_recipe={"context_depth": 3}))["query"]
    await m.finish(RED, "get_retrieval_replay", red_again)
    evidence.record("paired-replay-same-mid-owner-and-project-namespaces-keep-held-out-exposure-and-model-evidence-independent")

    await optimizer(m, evidence)
    await evaluation_scope(m, evidence)
    durable = {p: (await m.call(p, "get_retrieval_replay", query_id=replays[p]["id"]))["query"] for p in (RED, BLUE)}
    f.hard_stop()
    f.admin_client = None
    await f.start()
    m.actor = await f.agent("bridge")
    for project in (RED, BLUE):
        assert (await m.call(project, "get_retrieval_replay", query_id=replays[project]["id"]))["query"] == durable[project]
        attempt = (await m.call(project, "get_retrieval_attempt", attempt_id=attempts[project]["id"]))["attempt"]
        assert attempt["label_revision"] == 1 and attempt["cohort"] == ("training" if project == RED else "held_out")
    evidence.record("hard-restart-preserves-two-project-originals-label-cohort-exposure-and-paired-evidence-without-crossed-receipts")
    await revoked_work(m, evidence)
    assert all("PRIVATE-ADDRESSED-SENTINEL" not in json.dumps(row["request"]) for row in m.model.requests)
    assert all(not (MARK[RED] in json.dumps(row["request"]) and MARK[BLUE] in json.dumps(row["request"])) for row in m.model.requests)
    evidence.record("actual-typed-model-requests-never-mix-project-originals-or-include-private-addressed-payloads")


async def optimizer(m, evidence):
    f = m.f
    training = {RED: [], BLUE: []}
    # Deliberately miss one independently labeled original, then let Archive's
    # real History fallback assess it. This is controlled recall-gap lifecycle
    # evidence, not a claim about a model's semantic quality.
    m.model.retrieval_noul = .01
    for project in (RED, BLUE):
        for case, specimen in (("one", "Alpha"), ("two", "Beta")):
            original = await m.record(project, MARK[project] + " Controlled original evidence " + case, "case-" + case,
                source={"kind": "fixture", "id": "same-training-source", "item_id": case + "-original"}, mid=case + "-original")
            await m.ready(project)
            query = (await m.call(project, "query_archive", "training-query-" + case,
                question="Was specimen " + specimen + " present?", scope={"information_type": "case-" + case}))["query"]
            q = await m.finish(project, "get_archive_query", query)
            attempt = await m.attempt(project, q)
            m.label(project, attempt, [original["publication"]["id"]], "training")
            labelled = (await m.call(project, "get_retrieval_attempt", attempt_id=attempt["id"]))["attempt"]
            assert labelled["adjudicated_diagnosis"] in ("confirmed_retrieval_gap", "confirmed_context_assembly_gap"), labelled["adjudicated_diagnosis"]
            training[project].append(attempt["id"])
    m.model.retrieval_noul = None
    # Foreign attempt IDs cannot satisfy local optimizer training gates.
    denied = m.admin(BLUE, "propose_index", True, expected=404, training_attempt_ids=training[RED])
    assert denied["error"]["code"] == "NOT_FOUND"
    m.model.mode = "error"
    proposals = {p: m.admin(p, "propose_index", True, "same-proposal-mid", training_attempt_ids=training[p])["proposal"] for p in (RED, BLUE)}
    for project, other in ((RED, BLUE), (BLUE, RED)):
        proposal = m.admin(project, "index_proposal", proposal_id=proposals[project]["id"])["proposal"]
        assert set(proposal["training_attempt_ids"]) == set(training[project])
        assert not set(proposal["training_attempt_ids"]) & set(training[other])
    m.admin(RED, "cancel_index_proposal", True, proposal_id=proposals[RED]["id"])
    assert m.admin(RED, "index_proposal", proposal_id=proposals[RED]["id"])["proposal"]["status"] == "cancelled"
    assert m.admin(BLUE, "index_proposal", proposal_id=proposals[BLUE]["id"])["proposal"]["status"] != "cancelled"
    m.admin(BLUE, "cancel_index_proposal", True, proposal_id=proposals[BLUE]["id"])
    m.model.mode = "normal"
    before = {p: (await m.call(p, "retrieval_index"))["index"]["selection"] for p in (RED, BLUE)}
    config = f.admin().call({"op": "config_get"})["config"]
    projects = copy.deepcopy(config["projects"])
    red = next(p for p in projects if p["id"] == RED)
    red["settings"]["retrieval"] = {"recipe": {"context_depth": 2}}
    f.admin().call({"op": "config_update", "patch": {"projects": projects}}, mutation=True)
    changed = {p: (await m.call(p, "retrieval_index"))["index"]["selection"] for p in (RED, BLUE)}
    assert changed[RED]["revision"] == before[RED]["revision"] + 1 and changed[RED]["base_recipe"]["context_depth"] == 2
    assert changed[BLUE] == before[BLUE]
    conflict = m.admin(RED, "reset_index_selection", True, expected=409, expected_selection_revision=before[RED]["revision"])
    assert conflict["error"]["code"] == "CONFIG_CONFLICT"
    m.admin(RED, "reset_index_selection", True, expected_selection_revision=changed[RED]["revision"])
    assert (await m.call(BLUE, "retrieval_index"))["index"]["selection"] == before[BLUE]
    evidence.record("optimizer-foreign-training-rejected-local-proposal-cancel-and-project-recipe-selection-reset-do-not-cross-projects")


async def evaluation_scope(m, evidence):
    """Execute real evaluation jobs; scope is distinct from full quality gates."""
    f = m.f
    config = f.admin().call({"op": "config_get"})["config"]
    projects = copy.deepcopy(config["projects"])
    for project in projects:
        if project["id"] in (RED, BLUE):
            project["settings"]["retrieval"] = {"recipe": {"context_depth": 1}}
    f.admin().call({"op": "config_update", "patch": {"projects": projects,
        "history": {"request_bytes": 65536}, "optimization": {
            "max_total_bytes_delta": 268435456, "max_total_calls_delta": 100000,
            "min_held_out_groups": 1, "min_regression_groups": 1}}}, mutation=True)
    m.model.retrieval_noul = None
    training = {RED: [], BLUE: []}
    async def make_case(project, case, cohort, negative=False):
        tag = "evaluation-" + case
        root = await m.record(project, MARK[project] + " Context original " + case, "context")
        m.model.context_roots.add(root["publication"]["id"])
        middle = await m.record(project, "Acknowledged", "context",
            context={"links": [{"relation": "reply", "publication_id": root["publication"]["id"]}]})
        leaf = await m.record(project, "Yes", tag,
            context={"links": [{"relation": "reply", "publication_id": middle["publication"]["id"]}]})
        await m.ready(project)
        m.model.assessment = "no_evidence" if negative else "direct"
        m.model.retrieval_noul = .01 if cohort == "training" else None
        started = (await m.call(project, "query_archive", "same-evaluation-query-" + case,
            question="Was specimen " + {"training-Gamma": "Quartz", "training-Delta": "Obsidian",
                "held-Epsilon": "Jade", "regression-Zeta": "Opal"}[case] + " present?",
            scope={"information_type": tag}))["query"]
        query = await m.finish(project, "get_archive_query", started)
        attempt = await m.attempt(project, query)
        label = {"expectation": "no_evidence" if negative else "supported",
            "support_ids": [] if negative else [root["publication"]["id"], leaf["publication"]["id"]],
            "cohort": cohort, "tags": ["negation", "correction"] if negative else [],
            "note": "Independent evaluation namespace assertion; not semantic-quality certification", "confirmed": True}
        m.admin(project, "save_retrieval_label", True, attempt_id=attempt["id"],
            expected_label_revision=attempt["label_revision"], label=label)
        m.model.assessment = "direct"
        m.model.retrieval_noul = None
        if cohort == "training":
            labelled = (await m.call(project, "get_retrieval_attempt", attempt_id=attempt["id"]))["attempt"]
            assert labelled["adjudicated_diagnosis"] in ("confirmed_retrieval_gap", "confirmed_context_assembly_gap"), labelled["adjudicated_diagnosis"]
        return attempt["id"]
    for project in (RED, BLUE):
        for case in ("training-Gamma", "training-Delta"):
            training[project].append(await make_case(project, case, "training"))
    proposals = {p: m.admin(p, "propose_index", True, "same-evaluation-proposal",
        training_attempt_ids=training[p])["proposal"] for p in (RED, BLUE)}
    def proposal(project):
        return m.admin(project, "index_proposal", proposal_id=proposals[project]["id"], limit=64)["proposal"]
    for project in (RED, BLUE):
        settled = await wait(lambda: (q if (q := proposal(project))["status"] != "pending" else None),
            "Real training did not freeze an evaluation winner", 90)
        assert settled["status"] == "awaiting_evaluation", (project, settled["status"], settled.get("error"), settled["variants"])
        proposals[project] = settled
    held, regression = {}, {}
    for project in (RED, BLUE):
        held[project] = [await make_case(project, "held-Epsilon", "held_out")]
        regression[project] = [await make_case(project, "regression-Zeta", "regression", negative=True)]
    for project, other in ((RED, BLUE), (BLUE, RED)):
        before = proposal(project)
        denied = m.admin(project, "evaluate_index", True, expected=404,
            proposal_id=proposals[project]["id"], held_out_attempt_ids=held[other], regression_attempt_ids=regression[project])
        assert denied["error"]["code"] == "NOT_FOUND" and proposal(project) == before
    m.model.mode, m.model.delay = "slow", .8
    blue_before = proposal(BLUE)
    red = m.admin(RED, "evaluate_index", True, "same-evaluate-mid", proposal_id=proposals[RED]["id"],
        held_out_attempt_ids=held[RED], regression_attempt_ids=regression[RED])["proposal"]
    assert red["phase"] == "evaluating" and red["held_out_attempt_ids"] == held[RED]
    assert proposal(BLUE) == blue_before
    blue = m.admin(BLUE, "evaluate_index", True, "same-evaluate-mid", proposal_id=proposals[BLUE]["id"],
        held_out_attempt_ids=held[BLUE], regression_attempt_ids=regression[BLUE])["proposal"]
    for project in (RED, BLUE):
        await wait(lambda: any(c["cohort"] != "training" for c in proposal(project)["children"]),
            "Local evaluate_index did not create a real final-case replay child")
        current = proposal(project)
        assert current["held_out_attempt_ids"] == held[project] and current["regression_attempt_ids"] == regression[project]
        permitted = set(training[project] + held[project] + regression[project])
        assert all(c["attempt_id"] in permitted for c in current["children"] + current["cases"])
        assert not set(training[BLUE if project == RED else RED]) & permitted
    m.admin(RED, "cancel_index_proposal", True, proposal_id=red["id"])
    assert proposal(RED)["status"] == "cancelled" and proposal(BLUE)["status"] != "cancelled"
    f.hard_stop()
    f.admin_client = None
    m.model.mode = "normal"
    await f.start()
    m.actor = await f.agent("bridge")
    assert proposal(RED)["status"] == "cancelled"
    resumed = await wait(lambda: q if (q := proposal(BLUE))["status"] != "pending" else None,
        "Blue evaluation did not settle independently after restart", 90)
    if resumed["status"] == "partial":
        m.admin(BLUE, "continue_index_proposal", True, proposal_id=blue["id"], retry_failed=True)
        resumed = await wait(lambda: q if (q := proposal(BLUE))["status"] != "pending" else None,
            "Explicit Blue evaluation recovery did not settle", 90)
    assert resumed["held_out_attempt_ids"] == held[BLUE] and resumed["regression_attempt_ids"] == regression[BLUE]
    assert resumed["phase"] != "training" and any(c["cohort"] != "training" for c in resumed["children"])
    permitted = set(training[BLUE] + held[BLUE] + regression[BLUE])
    assert all(c["attempt_id"] in permitted for c in resumed["children"] + resumed["cases"])
    assert proposal(RED)["status"] == "cancelled"
    assert resumed["evaluation"] is not None and len([c for c in resumed["cases"] if c["cohort"] != "training"]) == 2
    evidence.record("actual-evaluate-index-foreign-held-out-rejected-local-final-case-children-and-cancel-restart-remain-project-scoped",
        red_status=proposal(RED)["status"], blue_status=resumed["status"], blue_phase=resumed["phase"],
        local_final_cases=2, scope_policy="64KiB History requests and positive cost-delta limits; actual recall and answer gates unchanged")


async def revoked_work(m, evidence):
    f = m.f
    m.model.mode, m.model.delay = "slow", .8
    before = len(m.model.requests)
    red = (await m.call(RED, "query_history", "same-revocation-mid", question="What was reported before revocation?",
                        scope={"information_type": "evidence"}))["query"]
    await wait(lambda: any("What was reported before revocation?" in json.dumps(row["request"])
        and MARK[RED] in json.dumps(row["request"]) for row in m.model.requests[before:]), "Queued Red evaluator never started")
    blue = (await m.call(BLUE, "query_history", "same-revocation-mid", question="What was reported before revocation?",
                         scope={"information_type": "evidence"}))["query"]
    grants = copy.deepcopy(MEMBERSHIPS)
    grants["bridge"] = [BLUE]
    f.admin().call({"op": "config_update", "patch": {"agent_projects": grants}}, mutation=True)
    await m.error(RED, "get_history_query", code="PROJECT_NOT_FOUND", query_id=red["id"])
    await asyncio.sleep(1)
    m.model.mode = "normal"
    settled_blue = await m.finish(BLUE, "get_history_query", blue)
    red_view = m.admin(RED, "query_job", query_id=red["id"])["query"]
    assert red_view["status"] != "completed" and red_view["coverage"]["examined"] == 0
    f.hard_stop()
    f.admin_client = None
    await f.start()
    m.actor = await f.agent("bridge")
    await m.error(RED, "get_history_query", code="PROJECT_NOT_FOUND", query_id=red["id"])
    assert (await m.call(BLUE, "get_history_query", query_id=blue["id"]))["query"] == settled_blue
    f.admin().call({"op": "config_update", "patch": {"agent_projects": MEMBERSHIPS}}, mutation=True)
    resumed = await m.finish(RED, "get_history_query", red)
    assert MARK[BLUE] not in json.dumps(resumed)
    evidence.record("queued-model-result-is-fenced-by-live-admission-revocation-and-hard-restart-with-independent-blue-progress")


async def main(args):
    if args.rest_url:
        raise ValueError("This crash/revocation matrix requires an isolated owned --hub/--command")
    args.keep_work = args.keep_work.resolve()
    args.with_model = False
    f = Fixture(args)
    model = contextual_fixture()
    f.model = model
    f.config.update(matcher={"url": model.url, "model": "Nemotron-Deciffusion-8B-v2.1", "timeout_ms": 3000, "retry_ms": 100},
                    archive={"audit_rate_ppm": 0}, optimization={"enabled": True, "max_variants": 1})
    evidence = Evidence(args.report, "adhd/multi-project-evidence-isolation@1")
    evidence.value["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence.value["typed_fixture_sha256"] = hashlib.sha256(Path(__file__).with_name("archive_support.py").read_bytes()).hexdigest()
    evidence.value["transport"] = "official-a2a-sdk-1.1.0-jsonrpc-and-authenticated-admin-http"
    if args.hub:
        evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest()
    try:
        await f.start()
        await checks(Matrix(f, model), evidence)
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
