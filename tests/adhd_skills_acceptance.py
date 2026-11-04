#!/usr/bin/env python3
"""Real A2A shared-profile release source and independent project adoption reports."""
import asyncio
import json
import hashlib
import subprocess
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import adhd_skill_update as skills
from multi_support import arguments, execute, scoped


async def checks(f, evidence):
    async def call(cmd, mid=None):
        response = await f.raw('bridge', cmd, mid)
        result = response.json()
        assert 'error' not in result, 'A2A command failed'
        return result['result']['message']['parts'][0]['data']
    red, blue = 'project-red', 'project-blue'
    release = skills.build(1, Path(__file__).resolve().parents[1], 'isolated acceptance')
    publication = await call(scoped(red, 'publish', information_type='adhd.skills.release',
        text='Trusted fixture release', data=release,
        source={'kind':'agent','id':'bridge','item_id':'fixture-release'}))
    assert publication['publication']['author_id'] == 'bridge'
    loop = asyncio.get_running_loop()
    fail_blue = [True]
    def transport(cmd, mid=None):
        if fail_blue[0] and cmd['op'] == 'publish' and cmd['project_id'] == blue:
            raise RuntimeError('controlled second project outage')
        return asyncio.run_coroutine_threadsafe(call(cmd, mid), loop).result(30)
    with tempfile.TemporaryDirectory(prefix='adhd-profile-') as tmp:
        home = Path(tmp)
        skills.atomic(home/'adhd-skills/policy.json', dict(project_id=red, publisher_id='bridge',
            agent_id='bridge', channel='stable', runtime='acceptance', mode='auto',
            report_projects=[red,blue], helper=['not-used-in-raw-A2A-fixture']))
        updater = skills.Updater(home, transport)
        try:
            await asyncio.to_thread(updater.sync)
        except RuntimeError:
            pass
        else:
            raise AssertionError('second-project outage was not exercised')
        assert updater.read()['revision'] == release['revision']
        pending = list((updater.root/'outbox').glob('*.json'))
        assert len(pending) == 1
        retry = skills.read_json(pending[0])
        assert retry['command']['project_id'] == blue
        red_reports = (await call(scoped(red,'search',information_type='adhd.skills.adoption')))['publications']
        assert len(red_reports) == 1
        fail_blue[0] = False
        await asyncio.to_thread(updater.flush)
        await asyncio.to_thread(updater.sync)
        for project in (red,blue):
            reports = (await call(scoped(project,'search',information_type='adhd.skills.adoption')))['publications']
            assert len(reports) == 1 and reports[0]['project_id'] == project
            assert reports[0]['data']['installed'] == release['revision']
        assert not list((updater.root/'outbox').glob('*.json'))
        assert (updater.root/'current.json').is_file()
        assert len(list((updater.root/'releases').iterdir())) == 1
        evidence.record('one-profile-one-release-two-project-reports-independent-outage-and-retry')
        # A release in the reporting-only project cannot control the shared profile.
        evil = skills.build(99, Path(__file__).resolve().parents[1], 'wrong source project')
        await call(scoped(blue,'publish',information_type='adhd.skills.release',
            text='Reporting project cannot select release',data=evil,
            source={'kind':'agent','id':'bridge','item_id':'wrong-project-release'}))
        await asyncio.to_thread(updater.sync)
        assert updater.read()['revision'] == release['revision']
        evidence.record('reporting-project-cannot-race-or-replace-configured-release-source')
        # Initial trust is established locally once. Every subsequent executable
        # and Markdown payload is retrieved by this profile through authenticated A2A.
        import install_adhd_bootstrap as seed
        helper = home/'hub.py'
        helper.write_text("""import json,sys,uuid
from pathlib import Path
from urllib.request import Request,urlopen
p=json.loads(Path(__file__).with_name('client.json').read_text())
args=sys.argv[1:];mid=args[1] if args[0]=='--message-id' else uuid.uuid4().hex
cmd=json.loads(args[-1])
envelope={'jsonrpc':'2.0','id':mid,'method':'SendMessage','params':{'message':{'messageId':mid,'role':'ROLE_USER','parts':[{'text':json.dumps(cmd)}]}}}
r=json.load(urlopen(Request(p['base']+'/a2a',data=json.dumps(envelope).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+p['token'],'A2A-Version':'1.0'}),timeout=15))
if 'error' in r: raise SystemExit('A2A fixture error')
print(json.dumps(r['result']['message']['parts'][0]['data']))
""")
        skills.atomic(home/'client.json', {'base':f.base,'token':f.tokens['bridge']})
        policy = skills.read_json(updater.root/'policy.json')
        policy['helper'] = [sys.executable,str(helper)]
        skills.atomic(updater.root/'policy.json',policy)
        source = Path(skills.__file__).read_bytes()
        initial = source + b'\n# initial enrollment fixture revision\n'
        target = home/'scripts/adhd_skill_update.py'
        skills.write_bytes(target, initial)
        old_hash = hashlib.sha256(initial).hexdigest()
        def manifest(sequence, payload, predecessor):
            m = dict(schema='adhd.bootstrap/1', sequence=sequence, version=skills.BOOTSTRAP,
                     channel='stable', text=payload.decode(), sha256=hashlib.sha256(payload).hexdigest(),
                     predecessors=[predecessor])
            m['revision'] = skills.digest(m)
            return m
        m = manifest(1,source,old_hash)
        pub = await call(scoped(red,'publish',information_type='adhd.bootstrap.release',
            text='Executable upgrade',data=m,source={'kind':'agent','id':'bridge','item_id':'bootstrap-1'}))
        await asyncio.to_thread(seed.install, home, pub['publication']['id'])
        assert hashlib.sha256(target.read_bytes()).hexdigest() == m['sha256']
        # Use the actual installed executable and credential-reading helper.
        result = await asyncio.to_thread(subprocess.run,
            [sys.executable,str(target),'--home',str(home),'sync'],capture_output=True,text=True,timeout=40)
        assert result.returncode == 0
        assert skills.read_json(updater.root/'current.json')['revision'] == release['revision']
        bad = manifest(2,b'raise SystemExit(7)\n',m['sha256'])
        await call(scoped(red,'publish',information_type='adhd.bootstrap.release',
            text='Controlled failed update probe',data=bad,
            source={'kind':'agent','id':'bridge','item_id':'bootstrap-2'}))
        result = await asyncio.to_thread(subprocess.run,
            [sys.executable,str(target),'--home',str(home),'bootstrap-sync','--approve'],
            capture_output=True,text=True,timeout=40)
        assert result.returncode != 0
        assert hashlib.sha256(target.read_bytes()).hexdigest() == m['sha256']
        await asyncio.to_thread(seed.recover,home,old_hash)
        assert target.read_bytes() == initial
        assert skills.read_json(updater.root/'current.json')['revision'] == release['revision']
        evidence.record('enrollment-bootstrap-upgrade-skill-sync-failed-update-and-independent-recovery-over-authenticated-A2A')
    evidence.value['transport'] = 'raw-a2a-jsonrpc-integer-preserving'
    evidence.value['limitations'] = ['Isolated native accepted hub; controlled reporting outage; no claim about unprovisioned live projects.']

if __name__ == '__main__':
    asyncio.run(execute(arguments(__doc__).parse_args(), 'adhd/skills-multi-project@1', checks))
