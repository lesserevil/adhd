"""Pure real-entry unwind/ownership checks with all timers/transports mocked."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

import image_recovery_entry as entry


def case(root,name,body,error=None):
    script=root/(name+'.py');flag=root/(name+'.finally');report=root/(name+'.json')
    script.write_text('from pathlib import Path\nfrom image_recovery_entry import deadline_handler\ntry:\n'+''.join(' '+line+'\n' for line in body.splitlines())+'finally:\n Path('+repr(str(flag))+').write_text("closed")\n')
    events=[]
    def timer(kind,seconds,*args):events.append((seconds,flag.exists()));return (0.,0.)
    caught=None
    with patch('signal.getitimer',return_value=(0.,0.)),patch('signal.setitimer',timer),patch('signal.signal',return_value=None),patch('subprocess.Popen',side_effect=AssertionError('No actual process')),patch('subprocess.run',side_effect=AssertionError('No actual process')):
        try:entry.run_script(script,[],900,report)
        except BaseException as exc:caught=exc
    assert flag.read_text()=='closed' and json.loads(report.read_text())['passed']==(error is None)
    if error:assert isinstance(caught,error)
    else:assert caught is None
    assert events[0][0]==900 and events[-1][0]==0
    if 'deadline' in name:assert (0,False) in events,'Timer must disarm before scenario finally'
    return json.loads(report.read_text())


def fallback(root,foreign=False,primary=False):
    target=type('FakeOwned',(),{})();target.root=root;target.image_id='sha256:'+'a'*64;target.name=None;target.container_id=None;target.cleanup_blocked=True
    identifier='b'*64;target.events=[{'action':'failed-owned-cleanup','container_id':identifier,'owned_name':'adhd-owned-unit'}]
    calls=[]
    def stop():raise RuntimeError('Original failed owned cleanup')
    target.stop=stop
    def docker(*args,**kwargs):
        calls.append(args)
        if args[0]=='rm':return type('R',(),{'returncode':0})()
        if len(calls)>1:return type('R',(),{'returncode':1,'stdout':b'[]','stderr':('Error: No such object: '+identifier).encode()})()
        row={'Id':identifier,'Name':'/adhd-owned-unit','Image':('sha256:'+'c'*64) if foreign else target.image_id,'Mounts':[{'Type':'bind','Source':str(root),'Destination':str(root)}]}
        return type('R',(),{'returncode':0,'stdout':json.dumps([row]).encode()})()
    target.docker=docker
    try:entry.close_owned_image(target)
    except BaseException:pass
    else:raise AssertionError('Recovered cleanup turned earlier failure into success')
    if foreign:assert len(calls)==1 and target.cleanup_blocked
    else:assert len(calls)==3 and not target.cleanup_blocked and target.name is None


def owned_primary(root):
    manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'a'*64}}))
    script=root/'owned-primary.py';report=root/'owned-primary.json';identifier='b'*64;calls=[]
    script.write_text('from pathlib import Path\nfrom container_fixture import OwnedImage\n'
        +'o=OwnedImage("sha256:'+('a'*64)+'",Path('+repr(str(manifest))+'),Path('+repr(str(root))+'))\n'
        +'o.name="adhd-owned-unit";o.container_id="'+identifier+'";o.image_id="sha256:'+('a'*64)+'";o.cleanup_blocked=True\n'
        +'o.events=[{"action":"failed-owned-cleanup","container_id":"'+identifier+'","owned_name":"adhd-owned-unit"}]\n'
        +'raise RuntimeError("original-scenario-failure")\n')
    def stop(self,*a,**k):raise OSError('original-cleanup-failure')
    def docker(self,*args,**kwargs):
        calls.append(args)
        if args[0]=='rm':return SimpleNamespace(returncode=0)
        if len(calls)>1:return SimpleNamespace(returncode=1,stdout=b'[]',stderr=('Error: No such object: '+identifier).encode())
        return SimpleNamespace(returncode=0,stdout=json.dumps([{'Id':identifier,'Name':'/adhd-owned-unit','Image':'sha256:'+'a'*64,'Mounts':[{'Type':'bind','Source':str(root),'Destination':str(root)}]}]).encode())
    with patch('signal.getitimer',return_value=(0.,0.)),patch('signal.setitimer',return_value=(0.,0.)),patch('signal.signal',return_value=None),patch('container_fixture.OwnedImage.stop',stop),patch('container_fixture.OwnedImage.docker',docker),patch('subprocess.Popen',side_effect=AssertionError('No process')):
        try:entry.run_script(script,[],900,report)
        except RuntimeError as error:assert str(error)=='original-scenario-failure' and any('cleanup failures' in n for n in error.__notes__)
        else:raise AssertionError('Primary scenario failure lost')
    value=json.loads(report.read_text());assert value['passed'] is False and value['images'][0]['closed'] is True and value['cleanup_failure_types']==['OSError']


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve()
        case(root,'success','pass')
        case(root,'primary','raise RuntimeError("scenario failure")',RuntimeError)
        case(root,'deadline','deadline_handler()',entry.QualificationDeadline)
        case(root,'swallowed-deadline','try: deadline_handler()\nexcept BaseException: pass',entry.QualificationDeadline)
        case(root,'zero-exit','raise SystemExit(0)')
        fallback(root);fallback(root,foreign=True);owned_primary(root)
    print('PASS recovery entry pure8: actual runpy finally, original primary, deadline-before-cleanup, swallowed deadline denied, normal zeroexit, strict fallback/foreign denial, actual ledger/primary+cleanup preservation; real signals/processes0')


if __name__=='__main__':main()
