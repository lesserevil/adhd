#!/usr/bin/env python3
"""Actual owned backup rejection, stale review and ownership proof boundaries.

Corrupt input bundles are explicit adversarial copies, never accepted producers.
A healthy project's newer original is checked after every rejected plan. No model.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import secrets
import shutil
from uuid import uuid4
import zlib

from multi_support import Evidence, Fixture, arguments, scoped
from project_recovery_acceptance import BLUE, RED, Recovery
from project_recovery_restore import offline_bundle
from project_recovery_state import canonical, digest, exact, route


async def rejected(r, project, receipt):
    deadline = asyncio.get_running_loop().time() + r.f.args.deadline
    while asyncio.get_running_loop().time() < deadline:
        op = r.status(project, receipt['operation_id'])['operation']
        if op['state'] == 'failed':
            assert op['plan'] is None and op['result'] is None
            assert op['failure'] is not None and op['failure']['retryable'] is False
            return op
        assert op['state'] in {'queued', 'verifying'}, op['state']
        await asyncio.sleep(.05)
    raise AssertionError('Invalid backup did not reach bounded failed state')


def variant(f, base, name, transform):
    source = Path(f.config['recovery']['backup_root']) / base
    target = source.with_name(name)
    target.mkdir(mode=0o700)
    for path in source.iterdir():
        shutil.copy2(path, target / path.name)
    manifest = json.loads((target / 'manifest.json').read_text())
    raw = transform(target, manifest)
    if raw is None:
        raw = canonical(manifest)
    (target / 'manifest.json').write_bytes(raw)
    return digest(raw)


async def checks(f, r, evidence):
    await r.initialize(RED); await r.initialize(BLUE)
    bridge = await f.agent('bridge')
    saved = (await bridge.call(scoped(RED, 'send', recipient_id='red-b', text='Private owned reference for invalid-backup tests')))['delivery']
    f.hard_stop()
    manifest, sha, _ = offline_bundle(f, r, 'original')
    await f.start()
    # Populated is independently rejected before any route replacement.
    original_route = copy.deepcopy(r.status(RED)['route'])
    receipt = r.call(RED, 'project_restore_plan', mode='restore', backup_id='original', manifest_sha256=sha,
        expected_revision=r.revision(), message_id=uuid4().hex)
    failure = await rejected(r, RED, receipt)
    assert failure['failure']['reason'] == 'populated'
    assert r.status(RED)['route'] == original_route
    assert saved['id'] in json.dumps(f.admin().call(scoped(RED, 'deliveries')))
    evidence.record('populated-target-cannot-be-merged-or-replaced-by-restore')
    _, checkpoint = route(f.file, RED)
    f.hard_stop()
    held = f.root / 'held'; held.mkdir(mode=0o700)
    for path in (checkpoint, Path(str(checkpoint) + '.snapshot')):
        os.replace(path, held / path.name)
    await f.start()
    actor = await f.agent('bridge')
    blue = (await actor.call(scoped(BLUE, 'publish_record', text='Healthy newer original while invalid target plans are verified')))['record']['publication']
    unchanged_config = copy.deepcopy(f.admin().call({'op': 'config_get'})['config'])
    unchanged_red = copy.deepcopy(r.status(RED)['route'])
    unchanged_blue = copy.deepcopy(r.status(BLUE)['route'])
    def payload(target, m, change):
        path = target / 'project.snapshot'
        raw = change(path.read_bytes())
        path.write_bytes(raw)
        m['snapshot'].update(bytes=len(raw), sha256=digest(raw))
    cases = []
    cases.append(('wrong-hash', lambda t,m: (m['snapshot'].update(sha256='0'*64), None)[1], {'hash'}))
    cases.append(('wrong-length', lambda t,m: (m['snapshot'].update(bytes=m['snapshot']['bytes']+1), None)[1], {'hash', 'schema'}))
    cases.append(('unknown-manifest', lambda t,m: (m.update(schema='adhd/project-backup@99'), None)[1], {'schema'}))
    cases.append(('duplicate-json', lambda t,m: canonical(m)[:-1]+b',"schema":"adhd/project-backup@1"}', {'schema'}))
    def symlink(t,m):
        p=t/'project.snapshot'; p.unlink(); p.symlink_to((t.parent/'original/project.snapshot').resolve())
    cases.append(('symlink', symlink, {'path'}))
    def hardlink(t,m):
        p=t/'project.snapshot'; p.unlink(); os.link(t.parent/'original/project.snapshot',p)
    cases.append(('hardlink', hardlink, {'path'}))
    def compressed(t,m):
        def change(raw):
            # Valid, small compressed ETF is forbidden, independently of checksum.
            body=b'\x83\x50'+len(raw[43:]).to_bytes(4,'big')+zlib.compress(raw[43:])
            return raw[:10]+bytes.fromhex(digest(body))+body
        payload(t,m,change)
    cases.append(('compressed-etf', compressed, {'schema', 'limits'}))
    def unknown_snapshot(t,m):
        def change(raw):
            needle=b'\x77\x06schema\x61\x04'
            assert raw[42:].count(needle)==1, 'Fixture must target only root snapshot schema atom'
            body=raw[42:].replace(needle,needle[:-1]+b'\x63')
            return raw[:10]+bytes.fromhex(digest(body))+body
        payload(t,m,change)
    cases.append(('unknown-snapshot', unknown_snapshot, {'schema'}))
    for name, transform, reasons in cases:
        variant_sha = variant(f,'original',name,transform)
        receipt = r.call(RED,'project_restore_plan',mode='restore',backup_id=name,manifest_sha256=variant_sha,
            allow_missing=True,expected_revision=r.revision(),message_id=uuid4().hex)
        failed = await rejected(r,RED,receipt)
        assert failed['failure']['reason'] in reasons, (name, failed['failure'])
        assert f.admin().call({'op':'config_get'})['config']==unchanged_config
        assert r.status(RED)['route']==unchanged_red and r.status(RED)['availability']=='recovery_required'
        assert r.status(BLUE)['route']==unchanged_blue
        current = await f.agent('bridge')
        assert (await current.call(scoped(BLUE,'get',publication_id=blue['id'])))['publication']==blue
        assert not checkpoint.exists() and not Path(str(checkpoint)+'.snapshot').exists()
        assert not any(secret in json.dumps(failed) for secret in (str(f.root), 'Private owned reference', *f.tokens.values()))
        evidence.record('invalid-backup-'+name+'-fails-closed-without-target-writer-or-unrelated-project-change',reason=failed['failure']['reason'])
        if name == 'hardlink':
            (Path(f.config['recovery']['backup_root'])/name/'project.snapshot').unlink()
            assert (Path(f.config['recovery']['backup_root'])/'original/project.snapshot').stat().st_nlink == 1
    # A current unowned credential is identity evidence; rotating it cannot prove
    # that the retired private recipient is the same principal.
    original_token = f.tokens['red-b']
    tokens = {**f.tokens,'red-b':secrets.token_urlsafe(32)}
    f.admin().call({'op':'config_update','patch':{'agents':tokens}},mutation=True)
    receipt=r.call(RED,'project_restore_plan',mode='restore',backup_id='original',manifest_sha256=sha,
        allow_missing=True,expected_revision=r.revision(),message_id=uuid4().hex)
    failed=await rejected(r,RED,receipt)
    assert failed['failure']['reason'] in {'owner_changed','owner_unprovable'}
    evidence.record('rotated-unowned-agent-credential-cannot-inherit-retained-private-state',reason=failed['failure']['reason'])
    f.admin().call({'op':'config_update','patch':{'agents':{**tokens,'red-b':original_token}}},mutation=True)
    receipt=r.call(RED,'project_restore_plan',mode='restore',backup_id='original',manifest_sha256=sha,
        allow_missing=True,expected_revision=r.revision(),message_id=uuid4().hex)
    plan=(await r.settle(RED,receipt,{'ready'}))['plan']; r.assert_plan(plan,RED,'restore')
    f.admin().call({'op':'config_update','patch':{'threshold_ppm':500001}},mutation=True)
    assert r.call(RED,'project_restore_apply',expected=409,plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],
        expected_revision=r.revision(),confirm=True,message_id=uuid4().hex)['error']['code']=='RESTORE_STALE_PLAN'
    stale=r.status(RED,receipt['operation_id'])['operation']
    assert stale['state']=='stale' and exact(stale['plan'])==exact(plan)
    evidence.record('configuration-change-invalidates-reviewed-plan-without-rewriting-its-digest-or-opening-target')


async def main(args):
    assert not args.rest_url and not args.with_model
    f=Fixture(args,initialize_projects=False)
    f.config['recovery']={'backup_root':str(f.root/'offline-backups')}
    evidence=Evidence(args.report,'project-recovery-rejections')
    if args.hub: evidence.value['artifact_sha256']=digest(args.hub.read_bytes())
    evidence.value['harness_sha256']=digest(Path(__file__).read_bytes())
    try:
        await f.start(); r=Recovery(f,args.recovery_schema)
        await checks(f,r,evidence)
    except BaseException as error:
        evidence.finish(error); raise
    else: evidence.finish()
    finally:
        try: await f.close()
        finally: f.bind_evidence(evidence); evidence.write()


if __name__=='__main__':
    parser=arguments(__doc__);parser.add_argument('--recovery-schema',type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
