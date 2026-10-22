"""Mocked Docker startup cleanup classification; zero processes or containers."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from image_eventing_runtime import EventingFaultImage
from image_filesystem_fault import RetainedImage

IMAGE='sha256:'+'a'*64
NAME='adhd-multi-accept-'+'c'*16
IDENTIFIER='f'*64


def reply(code=0,stdout=b'',stderr=b''):
    return SimpleNamespace(returncode=code,stdout=stdout,stderr=stderr)


def missing(identifier):
    return reply(1,stderr=('Error: No such object: '+identifier+'\n').encode())


def fixture(cls,transport):
    value=object.__new__(cls)
    value.name=NAME;value.container_id=None;value.image_id=IMAGE;value.armed=True
    value.events=[];value.last_exit_code=None;value.docker=transport
    return value


def fails(call):
    try:call()
    except (AssertionError,OSError):return
    raise AssertionError('Unknown Docker failure was reported as success')


def main():
    starts=[]
    def forbidden(*a,**k):starts.append('attempt');raise AssertionError('No process permitted')
    with patch('subprocess.Popen',forbidden),patch('subprocess.run',forbidden):
        for cls in (EventingFaultImage,RetainedImage):
            calls=[]
            def absent(*args,check=True):calls.append(args);return missing(args[1])
            target=fixture(cls,absent);target.stop()
            assert calls==[('inspect',NAME)] and target.name is target.container_id is None
            assert target.events[-1]['observed_absent'] and not target.cleanup_blocked
            calls=[]
            def transient(*args,check=True):
                calls.append(args)
                if args==('inspect',NAME) and len(calls)==1:return reply(1,stderr=b'Cannot connect to Docker daemon')
                if args[0]=='rm':return reply()
                return missing(args[1])
            target=fixture(cls,transient);fails(target.stop)
            assert ('rm','--force',NAME) in calls and len([a for a in calls if a[0]=='inspect'])==2
            assert target.name is target.container_id is None and target.events[-1]['observed_absent']
            calls=[]
            def daemon(*args,check=True):calls.append(args);return reply(1,stderr=b'Docker daemon is unavailable')
            target=fixture(cls,daemon);fails(target.stop)
            assert ('rm','--force',NAME) in calls and not target.events[-1]['observed_absent']
            assert target.cleanup_blocked and target.name is target.container_id is None
            # Refuse a replacement before the original unknown object is resolved.
            fails(lambda:target.argv(Path('/private/hub.json')))
            fails(target.stop)
            calls=[]
            def error(*args,check=True):
                calls.append(args)
                if len(calls)==1:raise OSError('Synthetic daemon socket failure')
                if args[0]=='rm':return reply()
                return missing(args[1])
            target=fixture(cls,error);fails(target.stop)
            assert ('rm','--force',NAME) in calls and target.events[-1]['observed_absent']
            calls=[]
            def foreign(*args,check=True):
                calls.append(args)
                return reply(stdout=json.dumps([{'Id':IDENTIFIER,'Image':'sha256:'+'b'*64}]).encode())
            target=fixture(cls,foreign);fails(target.stop)
            assert calls==[('inspect',NAME)] and target.cleanup_blocked
            assert not target.events[-1]['observed_absent']
            for malformed in (reply(1,stderr=('No such object: '+NAME.upper()).encode()),
                              reply(1,stdout=b'[{"Id":"contradictory"}]',stderr=('No such object: '+NAME).encode())):
                calls=[]
                def contradictory(*args,check=True):
                    calls.append(args)
                    return reply() if args[0]=='rm' else malformed
                target=fixture(cls,contradictory);fails(target.stop)
                assert calls==[('inspect',NAME),('rm','--force',NAME),('inspect',NAME)]
                assert target.cleanup_blocked and target.events[-1]['observed_absent'] is False
        assert EventingFaultImage.authoritative_absence(reply(1,stdout=b'[]',stderr=('error: no such object: '+NAME).encode()),NAME)
        assert not EventingFaultImage.authoritative_absence(reply(1,stderr=('No such object: '+IDENTIFIER.upper()).encode()),IDENTIFIER)
        for result in (reply(1,stderr=b'network: no such network'),reply(1,stderr=b'No such object: other'),reply(2),reply(0),reply(2,stderr=('No such object: '+NAME).encode()),reply(1,stderr=('Cannot connect to daemon\nNo such object: '+NAME).encode())):
            assert not EventingFaultImage.authoritative_absence(result,NAME)
    assert starts==[]
    print('PASS image startup cleanup15: five lifecycle cases on each helper plus strict classifier; before-create authoritative absence, transient original failure plus cleanup, daemon unknown failure, transport exception cleanup, foreign preservation, strict case-sensitive identifier/contradictory stdout denial plus retained/eventing unknown-cleanup lifecycle; process attempts0')


if __name__=='__main__':main()
