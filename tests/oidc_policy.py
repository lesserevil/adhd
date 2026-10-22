#!/usr/bin/env python3
"""Independent OIDC profile, email separation and group admission checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from foundation_acceptance import Client, Provider, free_port
from multi_workflow_upgrade import UpgradeRuntime


def main():
    p=argparse.ArgumentParser(description=__doc__)
    target=p.add_mutually_exclusive_group(required=True)
    target.add_argument('--command')
    target.add_argument('--image')
    p.add_argument('--image-manifest',type=Path)
    p.add_argument('--report',default='verification/oidc-policy.json')
    args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/oidc-policy').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));r=UpgradeRuntime(root/'hub',command,args.image,args.image_manifest)
    seed=root/'seed'
    subprocess.run([sys.executable,'scripts/configure_hub.py','--directory',str(seed),
        '--port',str(free_port()),'--store-path',str(r.root/'hub.dets')],check=True,stdout=subprocess.DEVNULL)
    r.file.write_bytes((seed/'hub.json').read_bytes());r.file.chmod(0o600)
    shutil.copy2(seed/'initial-admin-password.txt',r.root/'initial-admin-password.txt')
    password=(seed/'initial-admin-password.txt').read_text().split('Password: ')[1].strip()
    provider=Provider(root);cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def signin():
        client=Client(r);client.get('/admin/oidc/start');_,session,_=client.get('/admin/session')
        if session['authenticated']:client.csrf=session['csrf']
        return client,session
    try:
        r.start();pid=r.pid;admin=Client(r);admin.login('admin',password)
        local=admin.api({'op':'save_user','user':{'username':'local-person','name':'Local Person',
            'email':'person@example.invalid','role':'Developer','password':'local-person-password'}},mutation=True)['user']
        oidc={'provider_id':'independent-provider','issuer':provider.issuer,'client_id':'independent-client',
            'client_secret':'fixture-client-secret','redirect_uri':r.base+'/admin/oidc/callback',
            'scopes':['openid','profile','email'],'groups_claim':'groups',
            'role_groups':{'Admin':['admins','operators'],'Developer':['engineering','writers'],'Viewer':['readers']},
            'default_role':None,'timeout_ms':3000}
        admin.api({'op':'config_update','patch':{'auth':{'mode':'both','oidc':oidc}}},mutation=True)
        original,session=signin();first=session['user'];assert first['role']=='Admin' and first['id']!=local['id']
        provider.subject='another-subject';second,session=signin();assert session['user']['id'] not in (first['id'],local['id'])
        assert session['user']['email']==first['email']==local['email']
        record('matching-email-never-auto-merges-local-or-distinct-oidc-subjects')
        provider.subject='fixture-person';provider.claim_overrides={'name':'Renamed Person','email':'changed@example.invalid'}
        original.api({'op':'create_agent','agent_id':'profile-owned','owner_user_id':first['id'],
                      'token':'profile-owned-agent-credential-0001'},mutation=True)
        current,session=signin();assert session['user']['id']==first['id'] and session['user']['role']=='Admin'
        assert session['user']['name']=='Renamed Person' and session['user']['email']=='changed@example.invalid'
        assert r.config['agent_owners']['profile-owned']==first['id']
        record('proved-profile-updates-retain-internal-id-role-and-agent-ownership')
        for groups in (None,{'Admin':True},['unknown-group'],[]):
            provider.subject='denied-'+str(len(cases))+'-'+str(type(groups).__name__);provider.groups=groups
            denied,session=signin();assert session['authenticated'] is False
            denied.api({'op':'config_get'},expected=401)
        provider.groups=['operators','writers','readers'];provider.subject='multi-group'
        multi,session=signin();assert session['user']['role']=='Admin';multi_id=session['user']['id']
        admin.api({'op':'config_update','patch':{'auth':{'oidc':{'role_groups':{
            'Admin':['admins'],'Developer':['engineering','writers'],'Viewer':['readers']}}}}},mutation=True)
        _,session,_=multi.get('/admin/session');assert session['user']['role']=='Developer'
        multi.api({'op':'save_user','user':{'id':multi_id,'name':'Renamed Person','email':'changed@example.invalid','role':'Admin'},
                   'expected_revision':r.config['config_revision'],'message_id':'forged-role','confirm':True},expected=403)
        record('invalid-and-unmapped-groups-denied-multiple-mappings-highest-role-hot-demotion')
        admin.api({'op':'config_update','patch':{'auth':{'oidc':{'default_role':'Viewer'}}}},mutation=True)
        provider.subject='missing-profile';provider.groups=[];provider.omit_claims={'name','email'};provider.claim_overrides={}
        missing,session=signin();user=session['user'];assert user['role']=='Viewer'
        assert user['name']=='' and user['email']=='' and user['profile_complete'] is False
        admin.api({'op':'save_user','user':{'id':user['id'],'name':'Collected Name',
            'email':'collected@example.invalid','role':'Viewer'}},mutation=True)
        _,session,_=missing.get('/admin/session');assert session['user']['id']==user['id']
        assert session['user']['profile_complete'] and session['user']['email']=='collected@example.invalid'
        assert r.pid==pid and r.process.poll() is None
        record('explicit-default-viewer-and-admin-profile-completion-without-fabricated-claims')
        initial_admin=next(u for u in r.config['users'] if u.get('username')=='admin')
        admin.api({'op':'save_user','user':{'id':initial_admin['id'],'username':'renamed-admin',
            'name':'Renamed Administrator','email':'admin@example.invalid','role':'Admin'}},mutation=True)
        admin.api({'op':'link_oidc','user_id':initial_admin['id'],'expected_revision':r.config['config_revision'],'confirm':True},expected=409)
        assert next(u for u in r.config['users'] if u['id']==initial_admin['id'])['built_in'] is True
        r.stop(hard=True);r.start();admin=Client(r);u=admin.login('renamed-admin',password)
        assert u['id']==initial_admin['id'] and u['provider']=='local' and 'built_in' not in u
        admin.api({'op':'link_oidc','user_id':u['id'],'expected_revision':r.config['config_revision'],'confirm':True},expected=409)
        record('renamed-bootstrap-account-remains-local-and-unlinkable-after-hard-restart')
        result={'schema':'adhd/oidc-policy@1','passed':True,'cases':cases,
                'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None}
    finally:
        try:r.stop()
        finally:provider.close()
    if args.image:
        result['runtime']=r.owned_image.identity()
        result['artifact_sha256']=result['runtime']['artifact_sha256']
        result['image_id']=result['runtime']['image_config_identity']
    Path(args.report).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
