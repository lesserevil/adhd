"""Zero-startup checks of the public fixture's explicitly bounded bootstrap."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from multi_support import Fixture


class SchemaClient:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    async def get(self, *_args, **_kwargs):
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"$id": "urn:adhd:protocol:2.1"})


class Admin:
    def __init__(self, states):
        self.states = states
        self.calls = []

    def call(self, command):
        self.calls.append(command)
        op = command["op"]
        if op == "list_projects": return {"projects": [{"id": p} for p in self.states]}
        if op == "project_restore_status": return {"availability": self.states[command["project_id"]]}
        if op == "config_get": return {"config_revision": 7}
        if op == "project_restore_plan": return {"operation_id": "plan"}
        if op == "project_restore_apply": return {"operation_id": "apply"}
        raise AssertionError(op)


def fixture(states):
    f = Fixture.__new__(Fixture)
    f.initialize_projects = True
    f.args = SimpleNamespace(rest_url=None)
    f.base = "http://127.0.0.1:1"
    f.bootstrap_project_ids = None
    f.initializations = []
    admin = Admin(states)
    f.admin = lambda: admin

    async def wait(project, operation, desired):
        if desired == {"ready"}:
            return {"plan": {"mode": "initialize", "project_id": project,
                             "plan_id": "p", "plan_sha256": "h"}}
        assert desired == {"complete"}
        admin.states[project] = "ready"
        return {"result": {"initialized": True}, "operation_id": operation}
    f.wait_recovery = wait
    return f, admin


class BootstrapScope(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, f):
        with patch("multi_support.httpx.AsyncClient", return_value=SchemaClient()):
            await f.initialize_unknown_projects()

    async def test_dynamic_project_excluded_after_initial_bootstrap(self):
        f, admin = fixture({"original": "uninitialized"})
        await self.invoke(f)
        self.assertEqual(len(f.initializations), 1)
        admin.calls.clear()
        admin.states["created-later"] = "uninitialized"
        await self.invoke(f)
        self.assertEqual(f.bootstrap_project_ids, frozenset({"original"}))
        self.assertFalse(any(c.get("project_id") == "created-later" for c in admin.calls))
        self.assertEqual(admin.states["created-later"], "uninitialized")
        self.assertEqual(len(f.initializations), 1)

    async def test_actual_alternate_canonical_inventory_not_fixed_constants(self):
        f, admin = fixture({"legacy-renamed-project": "uninitialized"})
        await self.invoke(f)
        self.assertEqual(f.bootstrap_project_ids, frozenset({"legacy-renamed-project"}))
        self.assertEqual(f.initializations[0]["project_id"], "legacy-renamed-project")
        self.assertEqual(admin.states["legacy-renamed-project"], "ready")

    async def test_known_missing_original_fails_closed_without_init(self):
        f, admin = fixture({"original": "ready"})
        await self.invoke(f)
        admin.calls.clear()
        admin.states["original"] = "recovery_required"
        with self.assertRaisesRegex(AssertionError, "existing unavailable"):
            await self.invoke(f)
        self.assertFalse(any(c["op"] in {"project_restore_plan", "project_restore_apply"}
                             for c in admin.calls))

    async def test_ready_original_preserved_without_mutation(self):
        f, admin = fixture({"original": "ready"})
        await self.invoke(f)
        await self.invoke(f)
        self.assertEqual(f.initializations, [])
        self.assertEqual({c["op"] for c in admin.calls}, {"list_projects", "project_restore_status"})


if __name__ == "__main__": unittest.main()
