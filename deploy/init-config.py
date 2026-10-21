#!/usr/bin/env python3
"""Initialize a private, model-free hub seed. Never overwrite existing config."""
import argparse
import json
import os
import re
from pathlib import Path
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--server-id", default=None)
    p.add_argument("--project-id", default="default")
    args = p.parse_args()
    if args.server_id is not None and not re.fullmatch(r"[a-f0-9]{32}", args.server_id):
        p.error("--server-id must contain exactly 32 lowercase hexadecimal characters")
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = args.directory / "hub.json"
    config = {
        "server_id": args.server_id or uuid.uuid4().hex,
        "project_id": args.project_id,
        "projects": [{"id": args.project_id, "name": "Default", "status": "active",
                      "description": "Initial project", "settings": {}}],
        "host": "0.0.0.0", "port": 8766, "store_path": "/data/hub.dets",
        "agents": {}, "matcher": None,
        "eventing": {"enabled": True, "rest_url": "http://kafka-rest:8082",
                     "timeout_ms": 3000, "retry_ms": 1000},
    }
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    print(f"Initialized {target}; retain this server identity across replacements.")


if __name__ == "__main__":
    main()
