#!/usr/bin/env python3
"""Desktop/mobile user, settings and real OIDC browser acceptance."""
import argparse,hashlib,json,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from foundation_acceptance import Client,Provider,free_port
from multi_workflow_upgrade import UpgradeRuntime


def main():
 p=argparse.ArgumentParser(description=__doc__);target=p.add_mutually_exclusive_group(required=True);target.add_argument('--command');target.add_argument('--image');p.add_argument('--image-manifest',type=Path);p.add_argument('--report',default='verification/foundation-browser.json');args=p.parse_args()
 parent=Path('_build/roadmap/browser').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
 command=json.loads(args.command) if args.command else [];runtime=UpgradeRuntime(root/'hub',command,args.image,args.image_manifest);provider=Provider(root);results=[]
 try:
  runtime.start();password=(runtime.root/'initial-admin-password.txt').read_text().split('Password: ')[1].strip()
  admin=Client(runtime);admin.login('admin',password)
  project=runtime.config['project_id']
  dev=admin.api({'op':'save_user','user':{'username':'browser-dev','name':'Browser Developer','email':'dev@example.invalid','role':'Developer','project_ids':[project],'password':'browser-developer-password'}},mutation=True)['user']
  admin.api({'op':'save_user','user':{'username':'browser-view','name':'Browser Viewer','email':'view@example.invalid','role':'Viewer','project_ids':[project],'password':'browser-viewer-password'}},mutation=True)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
   for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
    failures=[]
    def page_for(context):
     page=context.new_page();page.on('pageerror',lambda e:failures.append(str(e)));page.on('console',lambda m:failures.append(m.text) if m.type=='error' else None);page.on('requestfailed',lambda r:failures.append('requestfailed '+r.url));page.on('response',lambda r:failures.append('HTTP '+str(r.status)) if r.status>=400 else None);return page
    def login(page,username,password):
     page.goto(runtime.base+'/admin');page.get_by_label('Username',exact=True).fill(username);page.get_by_label('Password',exact=True).fill(password);page.get_by_role('button',name='Sign in',exact=True).click();expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
    def capture(page,suffix):
     assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
     assert not page.get_by_text('NaN',exact=True).count()
     page.screenshot(path=str(root/(name+'-'+suffix+'.png')),full_page=True)
     (root/(name+'-'+suffix+'.txt')).write_text(page.locator('body').aria_snapshot())
    context=browser.new_context(viewport=viewport);page=page_for(context);login(page,'admin',password)
    page.get_by_role('button',name='Users',exact=True).click()
    expect(page.get_by_role('heading',name='Add local user',exact=True)).to_be_visible()
    if name=='desktop':
     row=page.locator('section.row').filter(has=page.get_by_role('heading',name='admin',exact=True));row.get_by_role('button',name='Complete my profile',exact=True).click();row.get_by_label('Name',exact=True).fill('Browser Administrator');row.get_by_label('Email',exact=True).fill('admin@example.invalid');row.get_by_role('button',name='Save my profile',exact=True).click();expect(page.get_by_role('heading',name='Browser Administrator',exact=True)).to_be_visible()
    f=page.locator('#content > form');f.get_by_label('Username',exact=True).fill('new-'+name);f.get_by_label('Name',exact=True).fill('New '+name+' Viewer');f.get_by_label('Email',exact=True).fill(name+'@example.invalid');f.get_by_label('Role',exact=True).select_option('Viewer');f.get_by_label('Password (blank retains current password)',exact=True).fill('new-browser-viewer-password');f.get_by_label('Project access: '+next(p['name'] for p in runtime.config['projects'] if p['id']==project)+' ('+project+')',exact=True).check();f.get_by_role('button',name='Save user',exact=True).click();expect(page.get_by_role('heading',name='New '+name+' Viewer',exact=True)).to_be_visible();capture(page,'users')
    page.get_by_role('button',name='Settings',exact=True).click();threshold=812300 if name=='desktop' else 812400
    page.get_by_label('threshold ppm',exact=True).fill(str(threshold))
    if name=='desktop':
     page.get_by_role('button',name='Configure OIDC provider',exact=True).click()
     for label,value in [('provider id','independent-provider'),('issuer',provider.issuer),('client id','independent-client'),('client secret','fixture-client-secret')]:page.get_by_label(label,exact=True).fill(value)
     page.get_by_label('mode',exact=True).select_option('both')
     page.locator('fieldset:has(> legend:text-is("Admin"))').get_by_label('One value per line',exact=True).fill('admins')
     page.locator('fieldset:has(> legend:text-is("Developer"))').get_by_label('One value per line',exact=True).fill('engineering')
     page.get_by_role('button',name='Test OIDC connection',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Connected to')
    page.get_by_role('button',name='Validate settings',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Settings are valid')
    before=runtime.config['config_revision'];page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Confirm and save settings',exact=True).click();expect(page.get_by_text('Revision '+str(before+1)+' · reload ready',exact=True)).to_be_visible();expect(page.get_by_label('threshold ppm',exact=True)).to_have_value(str(threshold));assert runtime.config['threshold_ppm']==threshold;capture(page,'settings')
    if name=='desktop':
     page.get_by_role('button',name='Enable federation',exact=True).click();page.get_by_label('description',exact=True).fill('Browser-managed project catalog')
    page.get_by_label('Share user identities',exact=True).check();page.get_by_role('button',name='Add source',exact=True).click()
    source=page.locator('fieldset.source-entry').last
    source.get_by_label('Source provider',exact=True).select_option('github');source.get_by_label('Source host',exact=True).fill('github.com');source.get_by_label('Source tenant',exact=True).fill('browser-'+name);source.get_by_label('Source resource',exact=True).fill('stable-resource');source.get_by_label('Source description',exact=True).fill('Canonical browser fixtures for '+name);source.get_by_label('Canonical owner',exact=True).check();source.get_by_label('Source aliases, one per line',exact=True).fill('browser/'+name)
    page.get_by_role('button',name='Validate settings',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Settings are valid')
    before=runtime.config['config_revision'];page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Confirm and save settings',exact=True).click();expect(page.get_by_text('Revision '+str(before+1)+' · reload ready',exact=True)).to_be_visible()
    assert runtime.config['federation']['share_identities'] and runtime.config['federation']['catalog']['entries'][-1]['canonical']
    with page.expect_response(lambda r:r.url.endswith('/admin/api') and r.request.method=='POST' and r.request.post_data_json.get('op')=='config_get'):
     page.get_by_role('button',name='Refresh directory',exact=True).click()
    expect(page.get_by_role('heading',name='Federation directory',exact=True)).to_be_visible();capture(page,'catalog')
    page.reload();expect(page.get_by_role('button',name='Settings',exact=True)).to_be_visible()
    assert all(c.get('httpOnly') for c in context.cookies() if c['name']=='adhd_session')
    dctx=browser.new_context(viewport=viewport);dp=page_for(dctx);login(dp,'browser-dev','browser-developer-password');expect(dp.get_by_role('button',name='Settings',exact=True)).to_have_count(0);dp.get_by_role('button',name='Users',exact=True).click();expect(dp.get_by_role('button',name='Save user',exact=True)).to_have_count(0);dp.get_by_role('button',name='Agents',exact=True).click();dp.get_by_label('Agent ID',exact=True).fill('browser-'+name);dp.get_by_role('button',name='Generate token',exact=True).click();created_token=dp.get_by_label('Agent token (save securely before submitting)',exact=True).input_value();assert len(created_token)>=40;dp.get_by_role('button',name='Create agent',exact=True).click();expect(dp.get_by_role('heading',name='browser-'+name,exact=True)).to_be_visible();assert runtime.config['agent_owners']['browser-'+name]==dev['id'];capture(dp,'developer')
    admin.api({'op':'config_update','patch':{'federation':{'peers':[{'project_id':'unavailable-ui-peer','url':'http://127.0.0.1:'+str(free_port()),'token':'browser-peer-outbound-credential-00001','inbound_token':'browser-peer-inbound-credential-00001'}]}}},mutation=True)
    queued=Client(runtime).rpc({'op':'source_query','question':'Which project owns these UI fixtures?','sources':[{'provider':'github','host':'github.com','tenant':'unavailable-tenant','resource':'unknown-ui-source'}]},created_token)['query']
    page.get_by_role('button',name='Activity',exact=True).click();row=page.locator('section.row').filter(has=page.get_by_text('source · '+queued['id']+' · browser-'+name+' · pending',exact=True));expect(row.get_by_role('button',name='Cancel query',exact=True)).to_be_visible();page.once('dialog',lambda d:d.accept());row.get_by_role('button',name='Cancel query',exact=True).click();expect(page.get_by_text('source · '+queued['id']+' · browser-'+name+' · cancelled',exact=True)).to_be_visible();capture(page,'query-admin')
    assert Client(runtime).rpc({'op':'get_source_query','query_id':queued['id']},created_token)['query']['status']=='cancelled'
    admin.api({'op':'config_update','patch':{'federation':{'peers':[]}}},mutation=True)
    vctx=browser.new_context(viewport=viewport);vp=page_for(vctx);login(vp,'browser-view','browser-viewer-password');expect(vp.get_by_role('button',name='Settings',exact=True)).to_have_count(0);vp.get_by_role('button',name='Agents',exact=True).click();expect(vp.get_by_role('button',name='Create agent',exact=True)).to_have_count(0);expect(vp.get_by_role('button',name='Edit agent',exact=True)).to_have_count(0);capture(vp,'viewer')
    octx=browser.new_context(viewport=viewport);op=page_for(octx);op.goto(runtime.base+'/admin');op.get_by_role('link',name='Sign in with identity provider',exact=True).click();expect(op.get_by_role('heading',name='Overview',exact=True)).to_be_visible();expect(op.get_by_role('button',name='Settings',exact=True)).to_be_visible();capture(op,'oidc')
    admin.api({'op':'config_update','patch':{'auth':{'oidc':{'role_groups':{'Admin':[],'Developer':['engineering'],'Viewer':[]}}}}},mutation=True)
    op.get_by_role('button',name='Refresh',exact=True).click();expect(op.get_by_role('button',name='Settings',exact=True)).to_have_count(0)
    admin.api({'op':'config_update','patch':{'auth':{'oidc':{'role_groups':{'Admin':['admins'],'Developer':['engineering'],'Viewer':[]}}}}},mutation=True)
    op.get_by_role('button',name='Refresh',exact=True).click();expect(op.get_by_role('button',name='Settings',exact=True)).to_be_visible()
    target=next(u for u in runtime.config['users'] if u.get('username')=='new-'+name)
    provider.subject='browser-linked-'+name
    page.get_by_role('button',name='Users',exact=True).click();row=page.locator('section.row').filter(has=page.get_by_role('heading',name='New '+name+' Viewer',exact=True));page.once('dialog',lambda d:d.accept());row.get_by_role('button',name='Link OIDC identity',exact=True).click();expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Settings',exact=True)).to_have_count(0)
    session=page.evaluate("fetch('/admin/session').then(r=>r.json())");assert session['user']['id']==target['id'] and session['user']['role']=='Viewer' and session['user']['provider']=='oidc'
    provider.subject='fixture-person'
    page.get_by_role('button',name='Log out',exact=True).click();expect(page.get_by_label('Username',exact=True)).to_be_visible();page.reload();expect(page.get_by_label('Username',exact=True)).to_be_visible();assert page.evaluate('localStorage.length+sessionStorage.length')==0
    assert not failures,failures
    results.append({'viewport':viewport,'passed':True,'normal_path_errors':failures,'captures':str(root.relative_to(Path.cwd()))})
    for ctx in (context,dctx,vctx,octx):ctx.close()
   browser.close()
  assert provider.exchanges>=2
  result={'schema':'adhd/foundation-browser@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'viewports':results,'real_oidc_exchanges':provider.exchanges,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 finally:runtime.stop();provider.close()
 if runtime.owned_image:
  result['runtime']=runtime.owned_image.identity();result['artifact_sha256']=result['runtime']['artifact_sha256'];result['image_id']=result['runtime']['image_config_identity']
 Path(args.report).write_text(json.dumps(result,indent=2)+'\n');print('PASS desktop/mobile accounts, roles, live settings and real OIDC')

if __name__=='__main__':
    # Both bootstrap suites deliberately verify the documented default port.
    # Serialize that shared fixture when independent suites run concurrently.
    import fcntl
    lock_path=Path('_build/roadmap/foundation-port.lock');lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as port_lock:
        fcntl.flock(port_lock,fcntl.LOCK_EX)
        main()
