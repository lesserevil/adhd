"""Pure recovery image boundary dispatch; never compile or start a process."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from project_recovery_crash import stopped, STAGES, UNDECIDED


async def checks(root):
    sentinel=root/'sentinel.json';pending=asyncio.get_running_loop().create_future();calls=[]
    sentinel.write_text(json.dumps({'stage':'after-install-snapshot','pid':1}))
    fake=SimpleNamespace(image_runtime=SimpleNamespace(stop_at_observed_boundary=lambda value:calls.append(value)),
        process=SimpleNamespace(pid=992999,poll=lambda:None))
    witness=await stopped(fake,sentinel,pending,1)
    assert witness=={'stage':'after-install-snapshot','pid':1} and calls==[witness]
    # A custody failure is fatal; it never falls back to the Docker client PID.
    def deny(_):raise AssertionError('Synthetic actual-BEAM custody rejection')
    fake.image_runtime.stop_at_observed_boundary=deny
    try:await stopped(fake,sentinel,pending,1)
    except AssertionError as error:assert str(error)=='Synthetic actual-BEAM custody rejection'
    else:raise AssertionError('Rejected custody silently accepted')
    # Preserve native semantics and actual kernel-T requirement, using synthetic
    # /proc bytes rather than inspecting or signaling any host process.
    fake.image_runtime=None;sentinel.write_text(json.dumps({'stage':'after-install-snapshot','pid':992999}))
    read=Path.read_text
    def text(path,*args,**kwargs):
        if str(path)=='/proc/992999/status':return 'Name: synthetic\nState:\tT (stopped)\n'
        return read(path,*args,**kwargs)
    with patch.object(Path,'read_text',text):assert (await stopped(fake,sentinel,pending,1))['pid']==992999
    assert len(STAGES)==12 and len(UNDECIDED)==3
    pending.cancel()


def main():
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.Popen',side_effect=AssertionError('No process permitted')),patch('subprocess.run',side_effect=AssertionError('No compiler/process permitted')):
        asyncio.run(checks(Path(directory)))
    print('PASS recovery crash image dispatch4: PID1 custody/denial/native kernel-T/unchanged12stage+3undecided; compiler/app/process attempts0')


if __name__=='__main__':main()
