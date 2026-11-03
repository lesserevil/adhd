import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("work_monitor", Path(__file__).parents[1] / "scripts/hermes_work_monitor.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class WorkMonitorTest(unittest.TestCase):
    def test_policy_scope_and_terminal_states(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(monitor.snapshot(home, 0), {"pending_work_ids": []})
            policy = {"enabled": True, "project_id": "p", "agent_id": "worker", "authorized_senders": ["manager"]}
            (home / "adhd-work-policy.json").write_text(json.dumps(policy))
            queue = home / "hub-work/queue"
            state = home / "hub-work/state"
            queue.mkdir(parents=True)
            state.mkdir()
            for name, sender in [("accepted", "manager"), ("wrong_sender", "peer"), ("done", "manager"), ("blocked", "manager")]:
                (queue / (name + ".json")).write_text(json.dumps({"task_id": name, "project_id": "p", "recipient_id": "worker", "sender_id": sender, "text": "private task text"}))
            for name, project, recipient in [("wrong_project", "other", "worker"), ("wrong_recipient", "p", "peer")]:
                (queue / (name + ".json")).write_text(json.dumps({"task_id": name, "project_id": project, "recipient_id": recipient, "sender_id": "manager"}))
            for name, status in [("done", "completed"), ("blocked", "blocked")]:
                (state / (name + ".json")).write_text(json.dumps({"status": status}))
            self.assertEqual(monitor.snapshot(home, 299), {"pending_work_ids": ["accepted"], "retry_generation": 0})
            self.assertEqual(monitor.snapshot(home, 300)["retry_generation"], 1)
            (state / "done.json").write_text(json.dumps({"status": "completed", "status_pending": True}))
            self.assertEqual(monitor.snapshot(home, 300)["pending_work_ids"], ["accepted", "done"])
            policy["enabled"] = False
            (home / "adhd-work-policy.json").write_text(json.dumps(policy))
            self.assertEqual(monitor.snapshot(home, 300), {"pending_work_ids": []})

    def test_malformed_state_is_not_empty_success(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "adhd-work-policy.json").write_text("{")
            with self.assertRaises(ValueError):
                monitor.snapshot(home, 0)
            (home / "adhd-work-policy.json").write_text(json.dumps({"enabled": True, "project_id": "p", "agent_id": "worker", "authorized_senders": "manager"}))
            with self.assertRaises(ValueError):
                monitor.snapshot(home, 0)


if __name__ == "__main__":
    unittest.main()
