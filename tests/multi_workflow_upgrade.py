#!/usr/bin/env python3
"""Upgrade actual accepted legacy workflow evidence and a real learned selection.

Only public APIs create or inspect application state. Store files are copied
byte-for-byte while closed; no DETS terms or private state are manufactured.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time

from foundation_acceptance import Runtime, Client, free_port
from container_fixture import OwnedImage
from workflow_provider_isolation import NativeProviderFence, IsolatedWorkflowImage, stop_independently


class UpgradeRuntime(Runtime):
    """Own the actual container, keeping native legacy producers independent."""
    def __init__(self, root, command, image=None, manifest=None, *, isolate_provider=False):
        super().__init__(root, command)
        image_class = IsolatedWorkflowImage if isolate_provider else OwnedImage
        self.owned_image = image_class(image, manifest, self.root) if image else None

    def start(self):
        if self.owned_image:
            self.command = self.owned_image.argv(self.file)
        try:
            super().start()
            if self.owned_image:
                self.owned_image.observe()
        except BaseException:
            self.stop()
            raise

    def stop(self, hard=False):
        try:
            if self.owned_image:
                self.owned_image.stop(hard)
        finally:
            super().stop(hard)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def wait(fn, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError("Actual legacy workflow upgrade did not settle")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hub", type=Path)
    mode.add_argument("--image")
    parser.add_argument("--image-manifest", type=Path)
    parser.add_argument("--producer-report", type=Path, required=True)
    parser.add_argument("--producer-root", type=Path, required=True)
    parser.add_argument("--producer-command", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    accepted = json.loads(args.producer_report.read_text())
    assert accepted["passed"] and not accepted.get("image")
    producer_command = json.loads(args.producer_command)
    producer_hash = hashlib.sha256(Path(producer_command[-1]).read_bytes()).hexdigest()
    assert accepted["artifact_sha256"] == producer_hash
    original_root = (args.producer_root / accepted["workdir"] / "hub").resolve()
    config = json.loads((original_root / "hub.json").read_text())
    original_store = Path(config["store_path"])
    assert original_store.is_relative_to(original_root)
    original_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in original_root.iterdir()
                      if p.is_file() and p.name.startswith(original_store.name)}
    assert original_store.name in original_files
    args.work_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="workflow-", dir=args.work_root.resolve()))
    producer = Runtime(root / "producer", producer_command)
    provider_fence = NativeProviderFence(producer.root, config)
    fence_prefix = provider_fence.prepare()
    producer.command = fence_prefix + producer.command
    target = UpgradeRuntime(root / "target", fence_prefix + ["elixir", str(args.hub.resolve())] if args.hub else [], args.image, args.image_manifest, isolate_provider=bool(args.image))
    for name in original_files:
        shutil.copy2(original_root / name, producer.root / name)
    config.update(store_path=str(producer.root / original_store.name), port=free_port())
    config["public_url"] = "http://127.0.0.1:" + str(config["port"])
    producer.file.write_text(json.dumps(config))
    producer.file.chmod(0o600)
    checks = []
    def api(runtime, command, mutation=False):
        return Client(runtime, runtime.config["admin_token"]).api(command, mutation=mutation)
    def capture(runtime):
        jobs = {}
        counts = {}
        for kind in ("history", "retrieval", "archive", "replay", "optimization"):
            rows = api(runtime, {"op": "query_jobs", "kind": kind, "limit": 100})["items"]
            # The accepted producer must really contain every advertised family.
            assert rows and len(rows) < 100, (kind, len(rows))
            counts[kind] = len(rows)
            for row in rows:
                assert row["kind"] == kind
                query = row["query"]
                assert query["status"] != "pending", (kind, query["status"])
                jobs[kind, query["id"]] = api(runtime, {"op": "query_job", "query_id": query["id"], "limit": 64})
        attempts = api(runtime, {"op": "feedback_attempts", "offset": 0, "limit": 64})["items"]
        assert attempts and len(attempts) < 64
        labels = {a["id"]: api(runtime, {"op": "feedback_attempt", "attempt_id": a["id"]}) for a in attempts}
        assert all(a["attempt"]["label_revision"] > 0 for a in labels.values())
        return {"jobs": jobs, "labels": labels, "cohorts": api(runtime, {"op": "feedback_cohorts", "limit": 64}),
            "deliveries": api(runtime, {"op": "deliveries"}), "publications": api(runtime, {"op": "overview"})["counts"]["publications"],
            "counts": counts}
    def compare(runtime, expected, allow_generation_retirement=False):
        unavailable = []
        if allow_generation_retirement:
            current = api(runtime, {"op": "retrieval_index"})["index"]
            generations = {current[key]["id"] for key in ("active", "previous") if current[key] is not None}
        for (kind, identifier), value in expected["jobs"].items():
            actual = api(runtime, {"op": "query_job", "query_id": identifier, "limit": 64})
            retained_value = copy.deepcopy(value)
            if (allow_generation_retirement and kind == "optimization"
                    and value["query"].get("global_evidence_available") is True
                    and actual["query"].get("global_evidence_available") is False):
                # Independently verify that the saved isolated generation is no
                # longer either publicly retained current global generation.
                assert value["query"]["index_manifest"]["id"] not in generations, identifier
                retained_value["query"]["global_evidence_available"] = False
                unavailable.append(identifier)
            assert actual == retained_value, (kind, identifier)
        for identifier, value in expected["labels"].items():
            assert api(runtime, {"op": "feedback_attempt", "attempt_id": identifier}) == value
        assert api(runtime, {"op": "feedback_cohorts", "limit": 64}) == expected["cohorts"]
        assert api(runtime, {"op": "deliveries"}) == expected["deliveries"]
        assert api(runtime, {"op": "overview"})["counts"]["publications"] == expected["publications"]
        return unavailable
    def record(name, **details):
        checks.append({"name": name, "passed": True, **details})
        print("PASS", name, flush=True)
    primary_error = None
    try:
        producer.start()
        provider_fence.observe(producer.process)
        before = api(producer, {"op": "retrieval_index"})["index"]
        assert before["selection"]["rollback_available"]
        rollback = api(producer, {"op": "rollback_index", "expected_selection_revision": before["selection"]["revision"]}, True)["proposal"]
        settled = wait(lambda: q if (q := api(producer, {"op": "index_proposal", "proposal_id": rollback["id"]})["proposal"])["status"] != "pending" else None)
        assert settled["status"] == "promoted" and settled["usage"]["calls"] == 0
        index = api(producer, {"op": "retrieval_index"})["index"]
        selection = index["selection"]
        assert index["status"] == "ready" and selection["applied"] and selection["qualification_current"]
        assert selection["effective_recipe"] != selection["base_recipe"]
        expected = capture(producer)
        record("genuine-accepted-producer-has-all-five-workflow-families-labeled-feedback-and-selected-learned-recipe", counts=expected["counts"], labels=len(expected["labels"]))
        offline = Path(producer.config["store_path"])
        api(producer, {"op": "config_update", "patch": {"store_path": str(producer.root / "moved.dets")}}, True)
        compare(producer, expected)
        assert api(producer, {"op": "retrieval_index"})["index"]["selection"] == selection
        producer.stop()
        # Copy the actual closed source from the successful hot store move.
        for path in producer.root.iterdir():
            if path.is_file() and path.name.startswith(offline.name):
                shutil.copy2(path, target.root / path.name)
        target_config = dict(producer.config)
        target_config.update(store_path=str(target.root / offline.name), port=free_port())
        target_config["public_url"] = "http://127.0.0.1:" + str(target_config["port"])
        if args.image:
            target_config["host"] = "0.0.0.0"
        target.file.write_text(json.dumps(target_config))
        target.file.chmod(0o600)
        target.start()
        if not args.image:
            provider_fence.observe(target.process)
        ready = wait(lambda: value if (value := api(target, {"op": "retrieval_index"})["index"])["status"] == "ready" else None)
        retained = ready["selection"]
        for key in ("revision", "applied", "base_identity", "base_recipe", "effective_recipe", "selected", "previous"):
            assert retained[key] == selection[key], key
        assert retained["qualification_current"] == (retained["current_runtime"] == selection["current_runtime"])
        assert ready["active"]["server_id"] == index["active"]["server_id"]
        changed_runtime = retained["current_runtime"] != selection["current_runtime"]
        retired = compare(target, expected, allow_generation_retirement=bool(args.image and changed_runtime))
        # A different native runtime can rebuild derived active index generations.
        # Freeze that truthful availability projection for exact restart checks;
        # immutable paired evidence and all other fields remain byte-equivalent.
        expected = copy.deepcopy(expected)
        for identifier in retired:
            expected["jobs"]["optimization", identifier]["query"]["global_evidence_available"] = False
        record("legacy-upgrade-preserves-exact-history-retrieval-archive-replay-optimizer-evidence-labels-cohorts-deliveries-and-selection", changed_runtime=changed_runtime, retired_global_generation_ids=retired)
        target.stop(hard=True)
        target.start()
        if not args.image:
            provider_fence.observe(target.process)
        compare(target, expected)
        assert api(target, {"op": "retrieval_index"})["index"]["selection"] == retained
        record("hard-restart-preserves-migrated-workflows-selected-control-and-unacknowledged-deliveries")
        api(target, {"op": "config_update", "patch": {"retrieval": {"recipe": retained["base_recipe"]}}}, True)
        reset = api(target, {"op": "retrieval_index"})["index"]["selection"]
        assert reset["revision"] == retained["revision"] + 1 and not reset["applied"]
        assert reset["selected"] is None and reset["previous"] is None
        wait(lambda: api(target, {"op": "retrieval_index"})["index"]["status"] == "ready")
        # Current isolated global-index availability is separate from immutable
        # paired raw evidence. Explicit reset drops that old generation; all
        # other historical projection fields must remain identical.
        unavailable = compare(target, expected, allow_generation_retirement=True)
        assert unavailable, "The accepted producer must contain a retained global generation"
        record("operator-reset-after-migration-preserves-originals-and-historical-evidence", unavailable_global_generation_ids=unavailable)
        assert original_files == {name: hashlib.sha256((original_root / name).read_bytes()).hexdigest() for name in original_files}
        result = {"suite": "adhd/multi-workflow-upgrade@1", "passed": True, "checks": checks,
            "producer_artifact_sha256": producer_hash, "producer_report_sha256": hashlib.sha256(args.producer_report.read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "legacy_store_sha256": original_files,
            "provider_export_fence": provider_fence.report(),
            "provider_isolation_helper_sha256": hashlib.sha256(Path(__file__).with_name("workflow_provider_isolation.py").read_bytes()).hexdigest(),
            "image": args.image, "artifact_sha256": hashlib.sha256(args.hub.read_bytes()).hexdigest() if args.hub else None,
            "evidence_projection_digest": digest({"jobs": [{"kind": k, "id": i, "value": value} for (k, i), value in expected["jobs"].items()], "labels": expected["labels"]})}
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_errors = stop_independently((('target', target), ('producer', producer)))
        if primary_error is not None or cleanup_errors:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({'suite': 'adhd/multi-workflow-upgrade@1', 'passed': False,
                'checks': checks, 'failure_type': type(primary_error).__name__ if primary_error else None,
                'cleanup_failures': [{'runtime': name, 'error_type': type(error).__name__}
                                     for name, error in cleanup_errors],
                'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'image': args.image,
                'retained_private_work': str(root)}, indent=2) + "\n")
        if cleanup_errors:
            if primary_error is not None:
                primary_error.add_note('Independent runtime cleanup failures: ' +
                    ', '.join(name + ':' + type(error).__name__ for name, error in cleanup_errors))
            else:
                raise cleanup_errors[0][1]
    result['provider_export_fence'] = provider_fence.report()
    if target.owned_image:
        result["runtime"] = target.owned_image.identity()
        result["artifact_sha256"] = result["runtime"]["artifact_sha256"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
