"""Public controlled optimizer allocations for before/lost/after restore epochs.

This typed endpoint authors deterministic transport/lifecycle outcomes. It makes
no live-model semantic-quality claim and never contacts a provider.
"""
import asyncio
import copy
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from uuid import uuid4

import httpx

from archive_support import ArchiveFixture
from multi_support import scoped
from project_recovery_restore import RED, finish
from multi_support import poll_until

PHASES = ("retained", "lost", "recovered")
COHORTS = ("training", "held_out", "regression")


def configure(f):
    f.config["agent_projects"] = copy.deepcopy(f.config["agent_projects"])
    for phase in PHASES:
        for cohort in COHORTS:
            name = "alloc-" + phase + "-" + cohort
            f.tokens[name] = secrets.token_urlsafe(32)
            f.config["agent_projects"][name] = [RED]
    f.config["optimization"] = {"enabled": True, "max_variants": 1, "min_held_out_groups": 2,
        "min_regression_groups": 2, "max_total_bytes_delta": 268435456, "max_total_calls_delta": 100000}
    f.config["retrieval"] = {"recipe": {"context_depth": 1}}


def model_fixture():
    model = ArchiveFixture()
    original_url, original_close = model.url, model.close
    model.recovery_roots = set()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def send(self, status, body):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_GET(self):
            self.send(200, {"ready": True})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            response = httpx.post(original_url, json=body, trust_env=False, timeout=10)
            value = response.json()
            if response.status_code == 200:
                state, questions = body.get("state", {}), body["questions"]
                question = state.get("question", "")
                if "useful" in questions:
                    fragments = state["candidate"]["fragments"]
                    relevant = any(v["origin_publication_id"] in model.recovery_roots for v in fragments)
                    value["answers"]["useful"]["noul"] = .99 if relevant else .01
                if question.endswith("unreported result?"):
                    choices = {"assessment": "no_evidence", "answer": "unknown"}
                elif question.startswith("What were the conflicting reports"):
                    choices = {"assessment": "conflicting", "answer": "conflict"}
                else:
                    choices = {}
                for key, choice in choices.items():
                    if key in questions:
                        value["answers"][key] = {"type": "choice", "choice": choice, "confidence": 1.0,
                            "probabilities": {label: float(label == choice) for label in questions[key]["criteria"]}}
            self.send(response.status_code, value)
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


async def wait(fn, explanation, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return value
        await asyncio.sleep(.05)
    raise AssertionError(explanation)


async def allocate(f, model, phase):
    assert phase in PHASES
    actors = {cohort: await f.agent("alloc-" + phase + "-" + cohort) for cohort in COHORTS}
    captured = {}
    async def case(cohort, variant):
        actor = actors[cohort]
        tag = "allocator-" + phase + "-" + cohort + "-" + variant
        # Opaque identity metadata deliberately shares no entity token with the
        # question. Every phase/cohort has independently fixed question wording;
        # this avoids reusing spent cohort identities and the prior no-miss setup.
        base = {"retained": 0, "lost": 1, "recovered": 2}[phase] * 20 + COHORTS.index(cohort) * 5
        nouns = ("Quartz", "Obsidian", "Flint", "Garnet", "Moonstone", "Jasper", "Peridot", "Tourmaline", "Agate", "Opal",
            "Beryl", "Zircon", "Spinel", "Onyx", "Lazurite", "Apatite", "Iolite", "Kyanite", "Olivine", "Rutile",
            "Emerald", "Amber", "Corundum", "Jadeite", "Sunstone", "Azurite", "Malachite", "Celestite", "Chalcedony", "Sodalite",
            "Carnelian", "Fluorite", "Hematite", "Pyrite", "Aragonite", "Anhydrite", "Labradorite", "Nepheline", "Orthoclase", "Selenite",
            "Sapphire", "Topaz", "Calcite", "Amethyst", "Andalusite", "Aquamarine", "Chrysoprase", "Citrine", "Diopside", "Enstatite",
            "Fuchsite", "Gypsum", "Howlite", "Idocrase", "Kunzite", "Larimar", "Moldavite", "Natrolite", "Okenite", "Prehnite")
        subject = nouns[base + {"first": 0, "second": 1, "negation": 2, "correction": 3, "no-evidence": 4}[variant]]
        question = ("What were the conflicting reports about specimen " + subject + "?" if variant == "correction" else
            "What is specimen " + subject + "'s unreported result?" if variant == "no-evidence" else "Was specimen " + subject + " observed?")
        text = ("Specimen " + subject + " was observed at station R." if variant == "correction" else
            "Was specimen unrelated-marker observed?" if variant == "no-evidence" else question)
        root = (await actor.call(scoped(RED, "publish_record", text=text, information_type="context")))["record"]["publication"]
        model.recovery_roots.add(root["id"])
        middle = (await actor.call(scoped(RED, "publish_record", text="Recorded acknowledgement.", information_type="context",
            context={"links": [{"relation": "reply", "publication_id": root["id"]}]})))["record"]["publication"]
        leaf = (await actor.call(scoped(RED, "publish_record", text="Correction: specimen " + subject + " was not observed at station R." if variant == "correction" else "No" if variant == "negation" else "Yes",
            information_type=tag, context={"links": [{"relation": "reply", "publication_id": middle["id"]}]})))["record"]["publication"]
        async def ready():
            value = (await actor.call(scoped(RED, "retrieval_index")))["index"]
            return value if value["status"] == "ready" else None
        await wait(ready, "Optimizer source indexing did not settle")
        q = (await actor.call(scoped(RED, "query_archive", question=question, scope={"information_type": tag})))["query"]
        q = await finish(actor, RED, "get_archive_query", q)
        async def attempt():
            rows = (await actor.call(scoped(RED, "list_retrieval_attempts", limit=64)))["items"]
            return next((v for v in rows if v["archive_query_id"] == q["id"]), None)
        item = await wait(attempt, "Optimizer case capture missing")
        f.admin().call(scoped(RED, "save_retrieval_label", attempt_id=item["id"], expected_label_revision=int(item["label_revision"]),
            label={"expectation": "no_evidence" if variant == "no-evidence" else "supported",
                "support_ids": [] if variant == "no-evidence" else [root["id"], leaf["id"]], "cohort": cohort,
                "tags": [variant] if variant in ("negation", "correction") else [],
                "note": "Independent controlled allocator lifecycle; no semantic qualification claim", "confirmed": True}), mutation=True)
        detail = (await actor.call(scoped(RED, "get_retrieval_attempt", attempt_id=item["id"])))["attempt"]
        if cohort == "training":
            assert detail["adjudicated_diagnosis"] in {"confirmed_retrieval_gap", "confirmed_context_assembly_gap"}, \
                "Training did not establish an actual captured recurrence gap"
        captured[cohort, variant] = {"root": root, "middle": middle, "leaf": leaf, "query": q, "attempt": detail}
        return item["id"]
    training = [await case("training", variant) for variant in ("first", "second")]
    proposal = f.admin().call(scoped(RED, "propose_index", training_attempt_ids=training), mutation=True)["proposal"]
    def current():
        return f.admin().call(scoped(RED, "index_proposal", proposal_id=proposal["id"], limit=64))["proposal"]
    frozen = await wait(lambda: value if (value := current())["status"] != "pending" else None,
        "Real bounded optimizer training did not freeze")
    assert frozen["status"] == "awaiting_evaluation", (frozen["status"], frozen.get("error"))
    held = [await case("held_out", variant) for variant in ("negation", "correction", "no-evidence")]
    regression = [await case("regression", variant) for variant in ("negation", "correction", "no-evidence")]
    evaluated = f.admin().call(scoped(RED, "evaluate_index", proposal_id=proposal["id"],
        held_out_attempt_ids=held, regression_attempt_ids=regression), mutation=True)["proposal"]
    final = await wait(lambda: value if (value := current())["status"] != "pending" else None,
        "Real optimizer evaluation did not settle")
    assert final["evaluation"] is not None
    assert {c["cohort"] for c in final["cases"]} >= {"training", "held_out", "regression"}
    assert any(v["cohort"] != "training" for v in final["children"])
    # Allocation qualification does not convert a rejected quality result into a
    # pass or force a winner. A reset is an independently permitted durable
    # selection action even when this controlled proposal is rejected.
    selection = (await actors["training"].call(scoped(RED, "retrieval_index")))["index"]["selection"]
    reset = f.admin().call(scoped(RED, "reset_index_selection", expected_selection_revision=int(selection["revision"])), mutation=True)
    return {"captured": list(captured.values()), "proposal": final, "evaluation_acceptance": evaluated,
        "selection_before_reset": selection, "selection_reset": reset}


async def event_controls(f, phase, publication_id):
    """Allocate real replay/repair/audit state without synthesizing broker success."""
    admin = f.admin().client
    def api(op, **fields):
        return admin.api(scoped(RED, op, **fields))
    def status():
        return api("eventing_status")
    subscriber = await f.agent("red-a")
    subscription = (await subscriber.call(scoped(RED, "subscribe", mode="raw",
        selectors={"information_type": ["recovery-" + ("lost" if phase == "recovered" else phase)]}), "late-" + phase))["subscription"]
    assert publication_id not in json.dumps(await subscriber.call(scoped(RED, "poll"))), "A new subscription replayed history implicitly"
    before = status()
    command = scoped(RED, "replay_events", from_sequence=1, to_sequence=before["replay_watermark"],
        expected_watermark=before["replay_watermark"], subscriptions=[{"id": subscription["id"], "revision": int(subscription["revision"])}],
        reason="Independent recovery allocation replay " + phase, confirm=True, message_id="event-replay-" + phase)
    replay = admin.api(command)
    assert admin.api(command) == replay
    rows = await poll_until(subscriber, RED, {publication_id}, 30)
    await subscriber.call(scoped(RED, "ack", delivery_ids=[row["id"] for row in rows]))
    materialized = await wait(lambda: value if (value := api("eventing_replay", replay_id=replay["replay"]["id"]))["replay"]["status"] == "materialized" else None,
        "Actual replay did not reach Kafka materialization")
    await wait(lambda: status()["pending_events"] == 0, "Pending logical events did not drain before foreign-row injection")
    before = status()
    async with httpx.AsyncClient(trust_env=False) as http:
        response = await http.post(f.args.eventing_rest_url.rstrip("/") + "/topics/" + before["topic"],
            headers={"Content-Type": "application/vnd.kafka.json.v2+json", "Accept": "application/vnd.kafka.v2+json"},
            json={"records": [{"partition": 0, "key": RED, "value": {"foreign_recovery_fixture": phase}}]})
        response.raise_for_status()
        offset = response.json()["offsets"][0]["offset"]
    quarantined = await wait(lambda: value if (value := status())["quarantined"] else None,
        "Foreign actual Kafka row was not quarantined")
    item = next(row for row in quarantined["quarantines"] if row["offset"] == offset)
    repair = scoped(RED, "repair_eventing", offset=offset, expected_checkpoint=quarantined["next_offset"],
        expected_digest=item["digest"], action="retry", reason="Retry real foreign recovery row " + phase,
        confirm=True, message_id="repair-retry-" + phase)
    retried = admin.api(repair)
    await wait(lambda: status()["quarantined"] == 1, "Retry silently accepted foreign data")
    assert admin.api(repair) == retried
    repaired = admin.api({**repair, "message_id": "repair-reconcile-" + phase,
        "action": "reconcile", "reason": "Explicit physical skip for recovery allocator " + phase})
    assert repaired["next_offset"] == offset + 1
    assert status()["quarantined"] == 0
    audit = api("eventing_audit", offset=0, limit=100)
    assert repaired["audit_id"] in json.dumps(audit) and retried["audit_id"] in json.dumps(audit)
    return {"subscription": subscription, "replay": materialized, "repair_retry": retried,
        "repair_reconcile": repaired, "audit": audit, "actual_foreign_offset": offset}
