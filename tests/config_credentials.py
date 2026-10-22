#!/usr/bin/env python3
"""Usable bearer credential bounds, namespace separation and hot reload rollback."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from foundation_acceptance import Runtime, Client, free_port


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True)
    p.add_argument('--report',default='verification/config-credentials.json');args=p.parse_args();command=json.loads(args.command)
    parent=Path('_build/roadmap/credential-tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));r=Runtime(root/'hub',command);seed=root/'seed'
    subprocess.run(['python3','scripts/configure_hub.py','--directory',str(seed),'--port',str(free_port()),
                    '--store-path',str(r.root/'hub.dets')],check=True,stdout=subprocess.DEVNULL)
    config=json.loads((seed/'hub.json').read_text());legacy='legacy credential with internal spaces';config['agents']['legacy-agent']=legacy
    r.file.write_text(json.dumps(config));r.file.chmod(0o600);cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def wait(fn):
        end=time.monotonic()+5
        while time.monotonic()<end:
            if fn():return
            time.sleep(.1)
        raise AssertionError('Configuration observation deadline')
    try:
        r.start();pid=r.pid;admin=Client(r);admin.login('admin',(seed/'initial-admin-password.txt').read_text().split('Password: ')[1].strip())
        assert Client(r).rpc({'op':'whoami'},legacy)['agent_id']=='legacy-agent'
        before=r.config
        for token in ('a'*4097,'unsafe header credential with spaces','unsafe-header\r\ncredential-0000001','λ'*32):
            admin.api({'op':'config_update','patch':{'admin_token':token}},expected=400,mutation=True)
            admin.api({'op':'create_agent','agent_id':'unsafe-agent','token':token},expected=400,mutation=True)
            assert r.config==before
        record('unsafe-or-oversized-new-bearer-values-rejected-before-activation')
        agent_token='a'*4096;admin_token='b'*4096
        admin.api({'op':'create_agent','agent_id':'long-credential-agent','token':agent_token},mutation=True)
        assert Client(r).rpc({'op':'whoami'},agent_token)['agent_id']=='long-credential-agent'
        admin.api({'op':'config_update','patch':{'admin_token':admin_token,'auth':{'allow_admin_token':True}}},mutation=True)
        Client(r,admin_token).api({'op':'overview'})
        assert Client(r).rpc({'op':'whoami'},legacy)['agent_id']=='legacy-agent'
        record('maximum-supported-bearer-values-authenticate-and-unchanged-legacy-value-remains-compatible')
        before=r.config
        for token in (admin_token,agent_token):
            peer={'project_id':'remote','url':'http://127.0.0.1:1','token':token,'inbound_token':'independent-inbound-credential-00001'}
            admin.api({'op':'config_update','patch':{'federation':{'description':'Credential test','peers':[peer]}}},expected=400,mutation=True)
            assert r.config==before
        record('outbound-peer-credentials-cannot-reuse-local-admin-or-agent-secrets')
        original=r.file.read_bytes();edited=json.loads(original);edited['admin_token']='unsafe changed credential\r\nwith header break'
        r.file.write_text(json.dumps(edited))
        wait(lambda:admin.api({'op':'config_get'})['reload_status']=='error')
        Client(r,admin_token).api({'op':'overview'})
        assert admin.api({'op':'config_get'})['config_revision']==before['config_revision']
        r.file.write_bytes(original)
        wait(lambda:admin.api({'op':'config_get'})['reload_status']=='ready')
        assert r.config==before and r.pid==pid and r.process.poll() is None
        assert (r.root/'hub.dets').stat().st_mode & 0o777==0o600
        record('invalid-external-credential-retains-live-key-and-restored-last-good-file-clears-error')
        Path(args.report).write_text(json.dumps({'schema':'adhd/config-credentials@1','passed':True,'cases':cases,
            'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()},indent=2)+'\n')
    finally:r.stop()


if __name__=='__main__':main()
