#!/usr/bin/env python3
"""Real password/session expiry, provider outage and bootstrap recovery checks."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
from foundation_acceptance import Client,Provider,free_port
from multi_workflow_upgrade import UpgradeRuntime


def main():
 p=argparse.ArgumentParser(description=__doc__);target=p.add_mutually_exclusive_group(required=True);target.add_argument('--command');target.add_argument('--image');p.add_argument('--image-manifest',type=Path);p.add_argument('--report',default='verification/auth-lifecycle.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
 parent=Path('_build/roadmap/auth-faults').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));cases=[];runtimes=[]
 def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
 def setup(name,stage=None):
  r=UpgradeRuntime(root/name,command,args.image,args.image_manifest);r.initialize_projects=False;runtimes.append(r);template=root/(name+'-seed');port=free_port()
  subprocess.run(['python3','scripts/configure_hub.py','--directory',str(template),'--port',str(port),'--store-path',str(r.root/'state.dets')],check=True,stdout=subprocess.DEVNULL)
  c=json.loads((template/'hub.json').read_text());initial=(template/'initial-admin-password.txt').read_text();r.base='http://127.0.0.1:'+str(port)
  if stage:
   side=r.file.with_name('hub.json.provision');side.write_text(json.dumps({'config':c}));side.chmod(0o600)
  else:r.file.write_text(json.dumps(c));r.file.chmod(0o600)
  if stage!='before-password':shutil.copy2(template/'initial-admin-password.txt',r.root/'initial-admin-password.txt')
  return r,c,initial
 provider=Provider(root)
 try:
  for stage in ('before-password','after-password'):
   r,c,initial=setup(stage,stage);r.start();text=(r.root/'initial-admin-password.txt').read_text();password=text.split('Password: ')[1].strip();client=Client(r);u=client.login('admin',password)
   assert u['id']==c['users'][0]['id']
   if stage=='after-password':assert text==initial
   else:assert text!=initial
   assert not Path(str(r.file)+'.provision').exists()
   r.stop();record('bootstrap-recovery-'+stage+'-stable-account-and-one-password-file')
  r,c,initial=setup('conflict','after-password');path=r.root/'initial-admin-password.txt';path.write_text('Username: admin\nPassword: intentionally-conflicting-password\n');saved=path.read_bytes()
  try:r.start()
  except AssertionError:pass
  else:raise AssertionError('Conflicting bootstrap credential was accepted')
  assert path.read_bytes()==saved and not r.file.exists();r.stop();record('bootstrap-conflicting-file-fails-closed-without-overwrite')
  r,c,initial=setup('journal-symlink');r.start();client=Client(r);client.login('admin',initial.split('Password: ')[1].strip())
  target=root/'untouched-journal.json';target.write_text('{}');side=Path(str(r.file)+'.journal');side.symlink_to(target);before=r.file.read_bytes()
  client.api({'op':'config_update','patch':{'threshold_ppm':765432}},expected=503,mutation=True)
  assert r.file.read_bytes()==before and target.read_text()=='{}' and not Path(str(r.file)+'.transaction').exists()
  r.stop()
  try:r.start()
  except AssertionError:pass
  else:raise AssertionError('Configuration journal symlink was followed on startup')
  r.stop();record('journal-symlink-rejected-before-mutation-and-on-startup')
  r,c,initial=setup('provision-symlink','after-password');side=Path(str(r.file)+'.provision');target=root/'untouched-provision.json';side.rename(target);side.symlink_to(target);before=target.read_bytes()
  try:r.start()
  except AssertionError:pass
  else:raise AssertionError('Provisioning symlink was followed')
  assert target.read_bytes()==before and not r.file.exists();r.stop();record('bootstrap-provisioning-symlink-rejected-without-overwrite')
  r,c,initial=setup('live');r.start();pid=r.pid;password=initial.split('Password: ')[1].strip();admin=Client(r);user=admin.login('admin',password);other=Client(r);other.login('admin',password)
  new_password='rotated-password-for-independent-lifecycle-test'
  admin.api({'op':'update_profile','name':'Lifecycle Administrator','email':'admin@example.invalid','password':new_password,'current_password':password},mutation=True)
  admin.api({'op':'overview'},expected=401);other.api({'op':'overview'},expected=401)
  bad=Client(r);status,_,_=bad.request('/admin/login',{'username':'admin','password':password});assert status==401
  current=Client(r);assert current.login('admin',new_password)['id']==user['id'];assert (r.root/'initial-admin-password.txt').read_text()==initial
  assert all(secret not in Path(str(r.file)+'.journal').read_text() for secret in (new_password,password));record('password-rotation-revokes-sessions-keeps-id-and-initial-file-and-safe-journal')
  o={'provider_id':'independent-provider','issuer':provider.issuer,'client_id':'independent-client','client_secret':'fixture-client-secret','redirect_uri':r.base+'/admin/oidc/callback','scopes':['openid','profile','email'],'groups_claim':'groups','role_groups':{'Admin':['admins'],'Developer':['engineering'],'Viewer':[]},'default_role':None,'timeout_ms':500}
  current.api({'op':'config_update','patch':{'auth':{'mode':'both','oidc':o,'session_ttl_ms':60000}}},mutation=True)
  oidc=Client(r);oidc.get('/admin/oidc/start');_,session,_=oidc.get('/admin/session');assert session['authenticated'] and session['user']['role']=='Admin';oidc.csrf=session['csrf']
  current.api({'op':'config_update','patch':{'auth':{'mode':'oidc'}}},mutation=True)
  provider.available=False
  anon=Client(r);status,body,_=anon.get('/admin/oidc/start');assert status==400
  status,_,_=anon.request('/admin/login',{'username':'admin','password':new_password});assert status==401
  _,session,_=anon.get('/admin/session');assert not session['methods']['local'] and not session['methods']['key']
  oidc.api({'op':'config_get'});oidc.api({'op':'config_update','patch':{'auth':{'mode':'both'}}},mutation=True);provider.available=True
  current=Client(r);current.login('admin',new_password);record('oidc-provider-outage-never-reactivates-local-or-key-fallback')
  before=r.config;old_revision=before['config_revision'];os.chmod(r.root,0o500)
  try:current.api({'op':'config_update','patch':{'threshold_ppm':765432}},expected=503,mutation=True)
  finally:os.chmod(r.root,0o700)
  assert r.config==before and current.api({'op':'config_get'})['config_revision']==old_revision and r.pid==pid
  record('failed-config-write-retains-last-good-revision-and-process')
  # Verify the real clock and a hot lifetime reduction; no product test clock.
  deadline=time.monotonic()+61
  while time.monotonic()<deadline:time.sleep(min(5,max(0,deadline-time.monotonic())))
  _,session,_=current.get('/admin/session');assert not session['authenticated'];current.api({'op':'overview'},expected=401)
  assert r.process.poll() is None and r.pid==pid;record('real-session-expiry-with-hot-sixty-second-lifetime-and-no-restart')
  result={'schema':'adhd/auth-lifecycle@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None}
 finally:
  for r in runtimes:r.stop()
  provider.close()
 if args.image:
  result['runtimes']=[r.owned_image.identity() for r in runtimes]
  result['artifact_sha256']=result['runtimes'][0]['artifact_sha256']
  result['image_id']=result['runtimes'][0]['image_config_identity']
 Path(args.report).write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
