"""Bounded payload/keytool custody and independent OAuth fixture cleanup."""
import hashlib
import inspect
import io
import json
import os
import re
from pathlib import Path
import stat
import tarfile
from container_fixture import OwnedImage


class KeytoolProbe(OwnedImage):
    """Reuse strict issued-name probe lifecycle for this one private keytool call."""
    def __init__(self,image,root):
        self.root=Path(root).resolve();self.requested=image
        row=json.loads(self.docker('image','inspect',image).stdout)
        assert len(row)==1 and re.fullmatch('sha256:[a-f0-9]{64}',row[0]['Id'])
        self.image_id=row[0]['Id'];self.probe_events=[]
        self.probe_active_name=self.probe_active_id=None;self.probe_cleanup_blocked=False
    def docker(self,*args,check=True):
        if args and args[0]=='run':
            args=(args[0],'--user',f'{os.getuid()}:{os.getgid()}','--memory','512m','--pids-limit','128',
                  '--mount',f'type=bind,src={self.root},dst=/fixture',*args[1:])
        return super().docker(*args,check=check)
    def import_truststore(self):
        return self.probe('/usr/bin/keytool','-importcert','-noprompt','-alias','issuer-ca','-file','/fixture/ca.pem',
            '-keystore','/fixture/issuer-trust.p12','-storetype','PKCS12','-storepass:file','/fixture/password.txt')


def unpack_payload(raw,destination,manifest):
    assert isinstance(raw,bytes) and len(raw)<=32*1024*1024
    expected=(set(manifest['files'])-{'Dockerfile'})|{'manifest.json'}
    values={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive:
            if member.name in ('.','./') and member.isdir():continue
            name=member.name.removeprefix('./')
            if member.isdir():name=name.rstrip('/')
            path=Path(name)
            assert not path.is_absolute() and '..' not in path.parts and str(path)==name
            if member.isdir():
                assert any(n.startswith(name.rstrip('/')+'/') for n in expected);continue
            assert member.isreg() and name in expected and name not in values and member.size<=8*1024*1024
            stream=archive.extractfile(member);assert stream is not None
            values[name]=stream.read(member.size+1);assert len(values[name])==member.size
    assert set(values)==expected
    assert json.loads(values['manifest.json'])==manifest
    for name,value in values.items():
        if name!='manifest.json':assert hashlib.sha256(value).hexdigest()==manifest['files'][name]
    destination=Path(destination);destination.mkdir(mode=0o700)
    for name,value in values.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with target.open('xb') as output:output.write(value)
        target.chmod(0o600)


async def cleanup_all(steps):
    """Attempt every independently owned closure; never suppress an unknown one."""
    outcomes=[];errors=[]
    for name,callback in steps:
        try:
            value=callback()
            if inspect.isawaitable(value):await value
            outcomes.append({'resource':name,'closed':True})
        except BaseException as error:
            errors.append(error);outcomes.append({'resource':name,'closed':False,'failure_type':type(error).__name__})
    return outcomes,errors
