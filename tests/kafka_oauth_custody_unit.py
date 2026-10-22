"""Pure adversarial payload/cleanup/keytool closure checks, no Docker/Kube apps."""
import asyncio
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from unittest.mock import patch
from kafka_oauth_custody import KeytoolProbe,unpack_payload,cleanup_all,NamespaceLease,finish_primary_after_cleanup
from container_fixture import OwnedImage


def archive(rows):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as tar:
        for name,value,kind in rows:
            row=tarfile.TarInfo(name);row.type=kind;row.size=len(value) if kind==tarfile.REGTYPE else 0
            if kind==tarfile.SYMTYPE:row.linkname='/foreign'
            tar.addfile(row,io.BytesIO(value) if kind==tarfile.REGTYPE else None)
    return out.getvalue()


def denied(call):
    try:call()
    except (AssertionError,FileNotFoundError):return
    raise AssertionError('Unsafe payload accepted')


async def main():
    data=b'actual synthetic payload';digest=hashlib.sha256(data).hexdigest()
    manifest={'files':{'hub.exs':digest,'Dockerfile':'0'*64}}
    rows=[('./',b'',tarfile.DIRTYPE),('./hub.exs',data,tarfile.REGTYPE),('./manifest.json',json.dumps(manifest).encode(),tarfile.REGTYPE)]
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.run',side_effect=AssertionError('No processes')):
        root=Path(directory)
        unpack_payload(archive(rows),root/'valid',manifest)
        assert (root/'valid/hub.exs').read_bytes()==data
        bad=[rows+[('./hub.exs',data,tarfile.REGTYPE)],rows+[('../escape',data,tarfile.REGTYPE)],
            rows+[('/absolute',data,tarfile.REGTYPE)],rows+[('./foreign',data,tarfile.REGTYPE)],
            [rows[0],('./hub.exs',b'',tarfile.SYMTYPE),rows[2]],rows[:-1],
            [rows[0],('./hub.exs',b'changed',tarfile.REGTYPE),rows[2]]]
        for i,value in enumerate(bad):denied(lambda value=value,i=i:unpack_payload(archive(value),root/('bad'+str(i)),manifest))
        calls=[]
        async def broken():calls.append('hub');raise RuntimeError('primary cleanup')
        def namespace():calls.append('namespace')
        outcomes,errors=await cleanup_all([('hub',broken),('namespace',namespace)])
        assert calls==['hub','namespace'] and len(errors)==1 and str(errors[0])=='primary cleanup'
        assert outcomes==[{'resource':'hub','closed':False,'failure_type':'RuntimeError'},{'resource':'namespace','closed':True}]
        probe=KeytoolProbe.__new__(KeytoolProbe);probe.root=root
        with patch.object(OwnedImage,'docker',return_value=b'fixed') as docker:
            assert probe.docker('run','--rm','--name','adhd-owned','--network','none')==b'fixed'
            argv=docker.call_args.args;assert argv[0]=='run' and '--user' in argv and '--mount' in argv
            assert 'type=bind,src='+str(root)+',dst=/fixture' in argv and '--network' in argv and '--name' in argv
        with patch.object(probe,'probe',return_value=b'') as run:
            probe.import_truststore();args=run.call_args.args
            assert args[0]=='/usr/bin/keytool' and args[-2:]==('-storepass:file','/fixture/password.txt')
            assert args.count('-importcert')==1
    lease=NamespaceLease('adhd-oauth-owned','1'*32)
    document=lease.document();assert lease.issued and lease.uid is None
    current={'metadata':{**document['metadata'],'uid':'uid-original'}}
    assert lease.deletion(current)=={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':'uid-original'}}
    foreign={'metadata':{'name':lease.name,'uid':'uid-original','annotations':{'adhd.qa/owner':'2'*32}}}
    denied(lambda:lease.deletion(foreign))
    replaced={'metadata':{**document['metadata'],'uid':'uid-replaced'}}
    denied(lambda:lease.deletion(replaced))
    assert lease.uid=='uid-original'
    class Evidence:
        def __init__(self):self.value={};self.writes=[]
        def finish(self,error):self.writes.append((error,dict(self.value)))
    evidence=Evidence();primary=RuntimeError('original scenario failure')
    evidence.finish(primary);evidence.value['cleanup']=[{'closed':True}]
    assert finish_primary_after_cleanup(evidence,primary)
    assert evidence.writes[-1]==(primary,{'cleanup':[{'closed':True}]})
    assert not finish_primary_after_cleanup(evidence,None)
    print('PASS securedK8s custody pure15: safecompletepayload,7malformed/symlink/duplicate/escape/hash denials, independentcleanup preserved, fixedprivate keytool argv, issued-before-create recovery/foreign-nonce and replacedUID denial/atomicDeleteOptions; Docker/Kube/app/provider starts0')


if __name__=='__main__':asyncio.run(main())
