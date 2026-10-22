"""Owned Docker lifecycle and exact staged-payload custody for integration tests."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4


class OwnedImage:
    def __init__(self, image, manifest, root):
        if manifest is None:
            raise ValueError("--image requires --image-manifest from the reviewed staging context")
        self.requested = image
        self.root = root
        self.manifest_path = Path(manifest).resolve()
        self.manifest_bytes = self.manifest_path.read_bytes()
        self.manifest = json.loads(self.manifest_bytes)
        assert self.manifest["schema"] == "adhd/container-inputs@1"
        assert "hub.exs" in self.manifest["files"]
        assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in self.manifest["files"].values())
        self.image_id = None
        self.name = None
        self.container_id = None
        self.events = []
        self.verified = False

    def docker(self, *args, check=True):
        return subprocess.run(["docker", *args], capture_output=True, check=check, timeout=30)

    def probe(self, entrypoint, *args):
        name = "adhd-accept-probe-" + uuid4().hex[:16]
        try:
            return self.docker("run", "--rm", "--name", name, "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", entrypoint,
                self.image_id, *args).stdout
        finally:
            self.docker("rm", "--force", name, check=False)

    def verify(self):
        if self.verified:
            return
        inspection = json.loads(self.docker("image", "inspect", self.requested).stdout)
        assert len(inspection) == 1 and re.fullmatch(r"sha256:[0-9a-f]{64}", inspection[0]["Id"])
        self.image_id = inspection[0]["Id"]
        actual_manifest = self.probe("cat", "/app/manifest.json")
        assert actual_manifest == self.manifest_bytes, "Image canonical manifest differs from reviewed staging input"
        actual_hash = self.probe("sha256sum", "/app/hub.exs").decode().split()[0]
        assert actual_hash == self.manifest["files"]["hub.exs"], "Image hub payload differs from its canonical manifest"
        self.verified = True

    def argv(self, config_file):
        self.verify()
        assert self.name is None
        self.name = "adhd-multi-accept-" + uuid4().hex[:16]
        return ["docker", "run", "--rm", "--name", self.name, "--network", "host",
            "--user", f"{os.getuid()}:{os.getgid()}", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "768m", "--cpus", "2",
            "--pids-limit", "256", "--tmpfs", "/tmp:rw,nosuid,noexec,size=128m",
            "--mount", f"type=bind,src={self.root},dst={self.root}",
            "--env", "ADHD_CONFIG_FILE=" + str(config_file), self.image_id]

    def observe(self):
        row = json.loads(self.docker("inspect", self.name).stdout)[0]
        assert row["Image"] == self.image_id and row["State"]["Running"] is True
        assert row["State"]["Pid"] > 0
        identifier = row["Id"]
        if self.container_id is None:
            self.container_id = identifier
            assert all(event.get("container_id") != identifier for event in self.events)
            self.events.append({"action": "started", "container_id": identifier, "image_config_identity": row["Image"]})
        else:
            assert identifier == self.container_id

    def absent(self):
        result = self.docker("inspect", self.name, check=False)
        if result.returncode == 0:
            return False
        assert b"no such" in result.stderr.lower(), "Docker inspection failed without proving owned container absence"
        return True

    def stop(self, hard=False):
        if self.name is None:
            return
        if self.container_id and self.absent():
            self.events.append({"action": "observed-exited", "container_id": self.container_id, "observed_absent": True})
            self.name = self.container_id = None
            if hard:
                raise AssertionError("Hard-stop test requires a currently running owned container")
            return
        if self.container_id is None:
            # A startup failure still owns its named container and must clean it.
            self.docker("rm", "--force", self.name, check=False)
        else:
            try:
                self.observe()
                if hard:
                    self.docker("kill", "--signal", "KILL", self.name)
                else:
                    self.docker("stop", "--time", "8", self.name)
            except BaseException:
                self.docker("rm", "--force", self.name, check=False)
                raise
        deadline = time.monotonic() + 15
        while not self.absent():
            if time.monotonic() >= deadline:
                raise AssertionError("Owned container did not stop and disappear")
            time.sleep(.05)
        if self.container_id:
            self.events.append({"action": "hard-killed" if hard else "stopped", "container_id": self.container_id,
                "observed_absent": True})
        self.name = self.container_id = None

    def identity(self):
        self.verify()
        return {"kind": "docker", "image_config_identity": self.image_id,
            "canonical_manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
            "container_helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "artifact_sha256": self.manifest["files"]["hub.exs"], "container_lifecycle": self.events}
