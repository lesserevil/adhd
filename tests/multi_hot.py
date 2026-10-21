#!/usr/bin/env python3
"""Public-interface hot configuration with no implicit/default project store."""
import asyncio
import hashlib

import httpx

from multi_support import Evidence, Fixture, arguments, poll_until, scoped


async def main(args):
    if args.rest_url:
        raise ValueError("No-default startup requires an owned disposable hub")
    fixture = Fixture(args)
    fixture.config.pop("project_id")
    evidence = Evidence(args.report, "adhd/no-default-hot-projects@1")
    evidence.value["artifact_sha256"] = hashlib.sha256(args.hub.read_bytes()).hexdigest() if args.hub else None
    try:
        await fixture.start()
        admin = fixture.admin()
        a, b = await fixture.agent("red-a"), await fixture.agent("red-b")
        assert "project_id" not in admin.call({"op": "config_get"})["config"]
        await b.call(scoped("project-red", "subscribe", mode="raw"))
        original = (await a.call(scoped("project-red", "publish", text="No default project required")))["publication"]
        await poll_until(b, "project-red", {original["id"]}, args.deadline)
        evidence.record("explicit-project-a2a-and-kafka-work-with-no-default-project")
        pid = fixture.process.pid
        for host in ("0.0.0.0", "127.0.0.1"):
            admin.call({"op": "config_update", "patch": {"host": host}}, mutation=True)
            assert fixture.process.pid == pid and fixture.process.poll() is None
            async with httpx.AsyncClient() as http:
                response = await http.get(fixture.base + "/health")
                assert response.status_code == 200
            assert admin.call({"op": "config_get"})["config"]["host"] == host
        evidence.record("host-binding-changes-at-the-same-port-without-hub-restart")
        before = {project: admin.call(scoped(project, "optimization_status"))["status"]["selection"]["revision"]
                  for project in ("project-red", "project-blue", "project-hidden")}
        admin.call({"op": "config_update", "patch": {"retrieval": {"recipe": {"context_depth": 2}}}}, mutation=True)
        after = {project: admin.call(scoped(project, "optimization_status"))["status"]["selection"]["revision"]
                 for project in before}
        assert all(after[project] == before[project] + 1 for project in before)
        evidence.record("operator-recipe-change-resets-selection-in-every-project-with-no-default-store")
        fixture.hard_stop()
        await fixture.start()
        after_restart = await poll_until(b, "project-red", {original["id"]}, args.deadline)
        assert len(after_restart) == 1
        assert (await a.call(scoped("project-red", "get", publication_id=original["id"])))["publication"] == original
        admin = fixture.admin()
        for project in before:
            assert admin.call(scoped(project, "optimization_status"))["status"]["selection"]["revision"] == after[project]
        evidence.record("no-default-project-config-and-all-project-state-survive-hard-restart")
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        try:
            await fixture.close()
        except BaseException as exc:
            evidence.finish(exc)
            raise
        fixture.bind_evidence(evidence)
        evidence.write()


if __name__ == "__main__":
    asyncio.run(main(arguments(__doc__).parse_args()))
