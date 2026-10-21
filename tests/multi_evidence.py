#!/usr/bin/env python3
"""Cross-project evidence, feedback, paired replay and optimizer scope matrix.

Uses actual A2A/Kafka and an independently controlled typed evaluator. Equal
workflow ID strings are legitimate local names: identity includes explicit project.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx

from archive_support import ArchiveFixture
from multi_support import Evidence, Fixture, MEMBERSHIPS, arguments, scoped


RED, BLUE = "project-red", "project-blue"
MARK = {RED: "RED-EVIDENCE-ONLY", BLUE: "BLUE-EVIDENCE-ONLY"}


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
    model = ArchiveFixture()
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
