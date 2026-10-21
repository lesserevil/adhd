#!/usr/bin/env python3
"""SIGKILL real all-project store moves at observed durable libc boundaries.

Linux native-runtime probe. LD_PRELOAD observes successful real filesystem calls;
it never substitutes product state or reports fabricated commit success.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from uuid import uuid4

from multi_support import Evidence, Fixture, arguments, poll_until, scoped


async def main(args):
    if not args.hub or args.rest_url:
        raise ValueError('Requires a locally owned --hub and native Linux Elixir on PATH')
    f = Fixture(args)
    if args.no_default:
        f.config.pop('project_id')
    target = f.root / 'moved' / 'hub.dets'
    target.parent.mkdir()
    source = Path(__file__).with_name('store_move_fault.c')
    library = f.root / 'move-fault.so'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-O2',
                    '-o', str(library), str(source), '-ldl'], check=True)
    sentinel = f.root / 'move-fault.json'
    injected = copy.copy(args)
    injected.hub = None
    injected.command = json.dumps(['env', 'LD_PRELOAD=' + str(library),
        'ADHD_MOVE_STAGE=' + args.crash_at, 'ADHD_MOVE_CONFIG=' + str(f.file),
        'ADHD_MOVE_TARGET=' + str(target), 'ADHD_MOVE_SENTINEL=' + str(sentinel), 'elixir', str(args.hub)])
    f.args = injected
    evidence = Evidence(args.report, 'adhd/multi-store-move-crash@1')
    evidence.value.update(artifact_sha256=hashlib.sha256(args.hub.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        fault_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        fault_library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
        crash_at=args.crash_at, no_default=args.no_default)
    pending = None
    try:
        await f.start()
        admin = f.admin()
        agents = {name: await f.agent(name) for name in ('red-a','red-b','blue-a','blue-b','hidden-a')}
        cases = [('project-red','red-a','red-b'),('project-blue','blue-a','blue-b')]
        originals, rows = {}, {}
        for project,sender,recipient in cases:
            await agents[recipient].call(scoped(project,'subscribe',mode='raw'))
            command=scoped(project,'publish',text='Crash recovery ' + project,
                           source={'kind':'slack','id':'crash-channel','item_id':'crash-item'})
            mid=uuid4().hex
            result=await agents[sender].call(command,mid)
            delivered=await poll_until(agents[recipient],project,{result['publication']['id']},args.deadline)
            await agents[recipient].call(scoped(project,'ack',delivery_ids=[delivered[0]['id']]))
            keep=(await agents[sender].call(scoped(project,'publish',text='Retained delivery ' + project)))['publication']
            rows[project]=await poll_until(agents[recipient],project,{keep['id']},args.deadline)
            originals[project]=(command,mid,result)
        hidden=(await agents['hidden-a'].call(scoped('project-hidden','publish',text='Hidden crash recovery')))['publication']
        before=admin.call({'op':'config_get'})['config']
        evidence.record('all-project-public-originals-and-acknowledgements-created-before-move')
        pending=asyncio.create_task(asyncio.to_thread(admin.call,
            {'op':'config_update','patch':{'store_path':str(target)}},mutation=True))
        end=time.monotonic()+25
        while time.monotonic()<end and not sentinel.exists():
            if pending.done():
                await pending
                raise AssertionError('Move completed without reaching requested syscall boundary')
            await asyncio.sleep(.01)
        assert sentinel.exists(),'Requested move boundary was not observed'
        observed=json.loads(sentinel.read_text())
        assert observed['pid']==f.process.pid and observed['stage']==args.crash_at
        end=time.monotonic()+2
        while time.monotonic()<end:
            state=Path('/proc/'+str(f.process.pid)+'/status').read_text()
            if re.search(r'^State:\s+T\b',state,re.M):
                break
            await asyncio.sleep(.01)
        else:
            raise AssertionError('Actual runtime was not stopped at the observed boundary')
        decision=Path(str(f.file)+'.transaction')
        assert decision.exists() == (args.crash_at!='before-decision')
        f.hard_stop()
        assert f.process.returncode == -signal.SIGKILL
        try:
            await pending
        except Exception:
            pass
        pending=None
        evidence.record('actual-runtime-stopped-and-sigkilled-at-requested-filesystem-boundary',
                        observed_stage=args.crash_at,kernel_state_before_kill='stopped',signal='SIGKILL')
        f.args=args
        await f.start()
        admin=f.admin()
        after=admin.call({'op':'config_get'})['config']
        assert after['server_id']==before['server_id']
        expected=before['store_path'] if args.crash_at=='before-decision' else str(target)
        assert after['store_path']==expected
        for project,sender,recipient in cases:
            command,mid,result=originals[project]
            assert await agents[sender].call(command,mid)==result
            assert await agents[sender].call(command)==result
            assert (await agents[recipient].call(scoped(project,'poll')))['deliveries']==rows[project]
        assert (await agents['hidden-a'].call(scoped('project-hidden','get',publication_id=hidden['id'])))['publication']==hidden
        assert not decision.exists()
        evidence.record('startup-recovers-one-complete-generation-with-every-project-original-retry-and-ack-state')
        post=(await agents['blue-a'].call(scoped('project-blue','publish',text='Accepted after crash recovery')))['publication']
        await poll_until(agents['blue-b'],'project-blue',{post['id']},args.deadline)
        evidence.record('recovered-project-writers-accept-new-publications-and-drain-real-kafka')
    except BaseException as exc:
        evidence.finish(exc)
        raise
    else:
        evidence.finish()
    finally:
        if pending and not pending.done():
            if f.process and f.process.poll() is None:
                f.hard_stop()
            try:
                await pending
            except Exception:
                pass
        f.args=args
        await f.close()


if __name__=='__main__':
    parser=arguments(__doc__)
    parser.add_argument('--no-default',action='store_true')
    parser.add_argument('--crash-at',required=True,choices=['before-decision','after-decision',
        'after-first-snapshot','after-first-checkpoint','before-config','after-config','before-cleanup'])
    asyncio.run(main(parser.parse_args()))
