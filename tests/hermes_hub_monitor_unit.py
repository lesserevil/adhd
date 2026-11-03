"""Receive-loop checks independent of a live hub or inference provider."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/hermes_hub_monitor.py"
spec = importlib.util.spec_from_file_location("monitor", SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_idle_stable_and_pending_retried(self):
        self.assertEqual(monitor.snapshot({"deliveries": []}, 0, 300),
                         monitor.snapshot({"deliveries": []}, 900, 300))
        pending = {"deliveries": [{"id": "b"}, {"id": "a"}]}
        self.assertEqual(monitor.snapshot(pending, 301, 300), monitor.snapshot(pending, 599, 300))
        self.assertNotEqual(monitor.snapshot(pending, 599, 300), monitor.snapshot(pending, 600, 300))

    def run_helper(self, source):
        with tempfile.TemporaryDirectory() as folder:
            helper = Path(folder) / "hub.py"
            helper.write_text(source)
            return subprocess.run([sys.executable, str(SCRIPT), "--helper", str(helper)],
                                  capture_output=True, text=True, timeout=10)

    def test_poll_only_and_no_content_leak(self):
        result = self.run_helper('import json,sys\nassert json.loads(sys.argv[1]) == {"op":"poll","limit":50}\nprint(json.dumps({"deliveries":[{"id":"d1","text":"private message"}]}))\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["pending_delivery_ids"], ["d1"])
        self.assertNotIn("private message", result.stdout)

    def test_update_failure_preserves_inbox_and_hides_output(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / "adhd-skills").mkdir()
            (home / "scripts").mkdir()
            (home / "adhd-skills/policy.json").write_text("{}")
            (home / "adhd-skills/state.json").write_text(json.dumps({"checked_at": "2000-01-01T00:00:00+00:00"}))
            (home / "scripts/adhd_skill_update.py").write_text('import sys\nprint("private update diagnostic")\nsys.exit(1)')
            helper = home / "hub.py"
            helper.write_text('print(\'{"deliveries":[{"id":"pending"}]}\')')
            result = subprocess.run([sys.executable, str(SCRIPT), "--helper", str(helper)],
                                    env=dict(os.environ, HERMES_HOME=str(home)), capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            value = json.loads(result.stdout)
            self.assertEqual(value["pending_delivery_ids"], ["pending"])
            self.assertEqual(value["skill_status"], "blocked")
            self.assertNotIn("private update", result.stdout + result.stderr)

    def test_failure_is_not_empty_or_secret_output(self):
        for source in ['import sys\nprint("secret-shaped diagnostic",file=sys.stderr)\nsys.exit(1)',
                       'print("{}")', 'print("not JSON")']:
            result = self.run_helper(source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("secret-shaped", result.stderr)


if __name__ == "__main__":
    unittest.main()
