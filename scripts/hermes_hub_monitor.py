#!/usr/bin/env python3
"""Cheap Hermes cron monitor for an installed profile-owned ADHD client.

Never acknowledges deliveries. Pending IDs change on arrival/removal and include
a bounded retry generation because Hermes saves monitor hashes before agent work.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def snapshot(result, now, retry_seconds):
    deliveries = result.get("deliveries")
    if not isinstance(deliveries, list):
        raise ValueError("Invalid poll response")
    ids = sorted({item["id"] for item in deliveries})
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("Invalid delivery ID")
    output = {"pending_delivery_ids": ids}
    if ids:
        output["retry_generation"] = int(now // retry_seconds)
    return output


def main():
    default = Path(os.environ["LOCALAPPDATA"]) / "hermes" if os.name == "nt" else Path.home() / ".hermes"
    home = Path(os.environ.get("HERMES_HOME") or default)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=Path, default=home / "skills/adhd-hub/scripts/hub.py")
    parser.add_argument("--retry-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.retry_seconds < 60:
        parser.error("retry-seconds must be at least 60")
    try:
        result = subprocess.run(
            [sys.executable, str(args.helper), '{"op":"poll","limit":50}'],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise RuntimeError("Hub poll failed")
        value = snapshot(json.loads(result.stdout), time.time(), args.retry_seconds)
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, RuntimeError):
        print("ADHD inbox poll failed; pending state was not acknowledged. Check client connectivity.", file=sys.stderr)
        return 1
    policy = home / "adhd-skills/policy.json"
    if policy.exists():
        state_path = home / "adhd-skills/state.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if not isinstance(state, dict):
                raise ValueError("Invalid update state")
            checked = datetime.datetime.fromisoformat(state["checked_at"]).timestamp() if state.get("checked_at") else 0
            if time.time() - checked >= 300:
                update = subprocess.run([sys.executable, str(home / "scripts/adhd_skill_update.py"),
                                         "--home", str(home), "sync"], capture_output=True, timeout=90)
                state = json.loads(state_path.read_text()) if state_path.exists() else {}
                if update.returncode:
                    state["status"] = "blocked"
            value["skill_revision"] = state.get("installed")
            value["skill_status"] = state.get("status", "activation_pending")
            if state.get("status") != "active_session_observed":
                value["skill_retry_generation"] = int(time.time() // 300)
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            value["skill_status"] = "blocked"
            value["skill_retry_generation"] = int(time.time() // 300)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
