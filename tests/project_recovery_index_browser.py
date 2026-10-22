#!/usr/bin/env python3
"""Actual asynchronous index panel replies respect project/view epochs.

Success bodies are captured unchanged from the real backend and delayed. The
current-context error case revokes a real Viewer grant before fetching its held
request, obtaining an actual non-disclosing denial instead of synthesizing an HTTP response.
"""
import asyncio
import copy
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect

from multi_support import Evidence, Fixture, arguments
from project_recovery_acceptance import BLUE, RED
from project_recovery_browser import login
from browser_observation import BrowserObservation, capture
from project_recovery_state import digest


async def viewport(args, browser, name, width, height, evidence):
    local=copy.copy(args);local.keep_work=args.keep_work/name;local.with_model=False
    f=Fixture(local);f.config['eventing']={'enabled':False}
    context=await browser.new_context(viewport={'width':width,'height':height})
    release=None
    page=await context.new_page()
    observation=BrowserObservation(page,f.base)
    try:
        await f.start()
        password=re.search(r'^Password: (.+)$',(f.root/'initial-admin-password.txt').read_text(),re.M)[1]
        await login(page,f.base,'admin',password)
        await expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
        await expect(page.get_by_role('heading',name='Retrieval index',exact=True).locator('..')).to_contain_text('archive watermark')
        captures=[]
        for phase,project in (('project-switch',RED),('view-switch',BLUE)):
            captured,release,fulfilled=asyncio.Event(),asyncio.Event(),asyncio.Event()
            async def delayed(route):
                body=route.request.post_data_json
                if body.get('op')=='retrieval_index' and body.get('project_id')==project and not captured.is_set():
                    response=await route.fetch()
                    assert response.status==200
                    observation.allow(route.request,op='retrieval_index',project=project,aborted=True)
                    captured.set();await release.wait()
                    await route.fulfill(response=response);fulfilled.set()
                else:await route.continue_()
            await page.route('**/admin/api',delayed)
            await page.get_by_role('button',name='Refresh',exact=True).click()
            await asyncio.wait_for(captured.wait(),10)
            if phase=='project-switch':
                await page.get_by_label('Project',exact=True).select_option(BLUE)
                await expect(page.get_by_role('heading',name=BLUE,exact=True)).to_be_visible()
                await expect(page.get_by_role('heading',name='Retrieval index',exact=True).locator('..')).to_contain_text('archive watermark')
            else:
                await page.get_by_role('button',name='Users',exact=True).click()
                await expect(page.get_by_role('heading',name='Users',exact=True)).to_be_visible()
            release.set();await asyncio.wait_for(fulfilled.wait(),10)
            # Allow the fulfilled fetch promise and its catch to run in-browser.
            await page.evaluate('()=>new Promise(resolve=>setTimeout(resolve,100))')
            alert=await page.get_by_role('alert').inner_text()
            observation={'viewport':name,'phase':phase,'project':await page.get_by_label('Project',exact=True).input_value(),'alert_text':alert}
            evidence.value.setdefault('observations',[]).append(observation)
            captures.append(await capture(page,f.root,phase));evidence.value.setdefault('captures',[]).append(captures[-1]);evidence.write()
            assert alert=='' and observation['project']==BLUE
            if phase=='view-switch':
                await expect(page.locator('#content').get_by_role('heading',name='Retrieval index',exact=True)).to_have_count(0)
            else:await expect(page.locator('#content').get_by_role('heading',name=RED,exact=True)).to_have_count(0)
            await page.unroute('**/admin/api',delayed)
            evidence.record(name+'-held-actual-index-'+phase+'-does-not-write-old-content-or-global-alert')
        evidence.value.setdefault("browser_observations",[]).append(observation.check())
        # A current-context failure must still be shown. Revoke the real Viewer's
        # admission after the overview succeeded, before its actual index request.
        user=f.admin().call({'op':'save_user','user':{'username':'index-viewer','name':'Index viewer',
            'email':'index-viewer@example.invalid','password':'private-index-viewer-password','role':'Viewer','project_ids':[BLUE]}},mutation=True)['user']
        viewer=await browser.new_context(viewport={'width':width,'height':height})
        try:
            child=await viewer.new_page();child_observation=BrowserObservation(child,f.base)
            await login(child,f.base,'index-viewer','private-index-viewer-password')
            await expect(child.get_by_role('heading',name='Retrieval index',exact=True).locator('..')).to_contain_text('archive watermark')
            captured,release,fulfilled=asyncio.Event(),asyncio.Event(),asyncio.Event()
            actual_status=[]
            async def current_error(route):
                body=route.request.post_data_json
                if body.get('op')=='retrieval_index' and not captured.is_set():
                    captured.set();await release.wait()
                    response=await route.fetch();body=await response.json();actual_status.append((response.status,body['error']['code']))
                    assert (response.status,body['error']['code']) in {(403,'FORBIDDEN'),(404,'PROJECT_NOT_FOUND')}
                    child_observation.allow(route.request,op='retrieval_index',status=response.status,project=BLUE)
                    await route.fulfill(response=response);fulfilled.set()
                else:await route.continue_()
            await child.route('**/admin/api',current_error)
            await child.get_by_role('button',name='Refresh',exact=True).click()
            await asyncio.wait_for(captured.wait(),10)
            f.admin().call({'op':'save_user','user':{'id':user['id'],'username':'index-viewer','name':'Index viewer',
                'email':'index-viewer@example.invalid','role':'Viewer','project_ids':[]}},mutation=True)
            release.set();await asyncio.wait_for(fulfilled.wait(),10)
            assert len(actual_status)==1 and actual_status[0] in {(403,'FORBIDDEN'),(404,'PROJECT_NOT_FOUND')}
            status,code=actual_status[0]
            evidence.value.setdefault('current_error_observations',[]).append({'viewport':name,'http_status':status,'error':code})
            evidence.write()
            await expect(child.get_by_role('alert')).to_have_text(code)
            await expect(child.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
            captures.append(await capture(child,f.root,'current-context-error'));evidence.value.setdefault('captures',[]).append(captures[-1])
            evidence.record(name+'-actual-current-context-index-denial-remains-visible',http_status=status,error=code)
        finally:
            try:evidence.value.setdefault("browser_observations",[]).append(child_observation.check())
            finally:await viewer.close()
        evidence.value.setdefault("browser_observations",[]).append(observation.check())
    finally:
        if release is not None:release.set()
        try:
            evidence.value.setdefault("browser_observations",[]).append(observation.check())
        finally:
            try:await context.close()
            finally:
                try:await f.close()
                finally:f.bind_evidence(evidence,key=name+'_runtime');evidence.write()


async def main(args):
    assert args.keep_work and not args.rest_url and not args.with_model
    evidence=Evidence(args.report,'recovery-index-browser-epochs')
    evidence.value['harness_sha256']=digest(Path(__file__).read_bytes())
    if args.hub:evidence.value['artifact_sha256']=digest(args.hub.read_bytes())
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,args=['--no-sandbox'])
            try:
                for name,width,height in (('desktop',1440,1000),('mobile',390,844)):
                    await viewport(args,browser,name,width,height,evidence)
            finally:await browser.close()
    except BaseException as error:evidence.finish(error);raise
    else:evidence.finish()


if __name__=='__main__':asyncio.run(main(arguments(__doc__).parse_args()))
