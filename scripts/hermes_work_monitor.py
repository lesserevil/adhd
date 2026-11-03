#!/usr/bin/env python3
"""Wake an explicitly authorized Hermes worker for durable local assignments."""
import json
import os
from pathlib import Path
import sys
import time


def snapshot(home, now):
    policy_path = home / "adhd-work-policy.json"
    if not policy_path.exists():
        return {"pending_work_ids": []}
    policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
    if not isinstance(policy, dict):
        raise ValueError("Invalid work policy")
    if policy.get("enabled") is not True:
        return {"pending_work_ids": []}
    if (not isinstance(policy.get("authorized_senders"), list)
            or not all(isinstance(value, str) and value for value in policy["authorized_senders"])
            or not isinstance(policy.get("project_id"), str) or not policy["project_id"]
            or not isinstance(policy.get("agent_id"), str) or not policy["agent_id"]):
        raise ValueError("Invalid work policy scope")
    pending = []
    for path in sorted((home / "hub-work/queue").glob("*.json")):
        task = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(task, dict):
            raise ValueError("Invalid queued task")
        if (task.get("project_id") != policy["project_id"]
                or task.get("sender_id") not in policy["authorized_senders"]
                or task.get("recipient_id") != policy["agent_id"]
                or task.get("task_id") != path.stem):
            continue
        state_path = home / "hub-work/state" / path.name
        state = json.loads(state_path.read_text(encoding="utf-8-sig")) if state_path.exists() else {}
        if not isinstance(state, dict) or state.get("status", "queued") not in ("queued", "running", "completed", "blocked"):
            raise ValueError("Invalid work state")
        if state.get("status", "queued") in ("queued", "running") or state.get("status_pending") is True:
            pending.append(path.stem)
    result = {"pending_work_ids": pending}
    if pending:
        result["retry_generation"] = int(now // 300)
    return result


def main():
    default = Path(os.environ["LOCALAPPDATA"]) / "hermes" if os.name == "nt" else Path.home() / ".hermes"
    home = Path(os.environ.get("HERMES_HOME") or default)
    try:
        result = snapshot(home, time.time())
    except (OSError, ValueError, KeyError, TypeError):
        print("ADHD work queue check failed; no work was dispatched.", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
