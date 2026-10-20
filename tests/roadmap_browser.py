#!/usr/bin/env python3
"""Rendered desktop/mobile management acceptance; requires Playwright and Chromium."""
import argparse, asyncio, json, secrets, sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
from hub_acceptance import Hub,ModelFixture
from oidc_acceptance import Provider
from playwright.async_api import async_playwright

async def checks(command,root):
    model=ModelFixture();provider=Provider();cases=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path='/snap/bin/chromium',args=['--no-sandbox'])
        try:
            for mode in ['key','oidc']:
                hub=Hub(command,root/mode,model.url);hub.config['admin_token']=secrets.token_urlsafe(32)
                if mode=='oidc':hub.config.update(admin_auth='oidc',public_url=hub.base,oidc={
                    'issuer':provider.base,'client_id':'acceptance-client','allowed_subjects':['admin-subject'],
                    'allow_insecure_loopback':True})
                hub.config_file.write_text(json.dumps(hub.config));hub.start()
                try:
                    for width in [1440,390]:
                        context=await browser.new_context(viewport={'width':width,'height':900});page=await context.new_page()
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.on('console',lambda e:errors.append(e.text) if e.type=='error' and '401' not in e.text else None)
                        page.on('requestfailed',lambda r:errors.append(r.url))
                        await page.goto(hub.base+'/admin')
                        if mode=='key':
                            await page.locator('#token').fill(hub.config['admin_token'])
                            await page.locator('#login-form button').click()
                        else:
                            await page.get_by_role('button',name='Sign in with identity provider').click()
                        await page.locator('#console').wait_for(state='visible')
                        await page.get_by_role('button',name='Activity',exact=True).click()
                        await page.get_by_role('heading',name='Indexes',exact=True).wait_for()
                        await page.get_by_role('heading',name='Query jobs',exact=True).wait_for()
                        page.once('dialog',lambda d:d.accept())
                        await page.get_by_role('button',name='Rebuild index',exact=True).click()
                        await page.wait_for_function("document.querySelector('#state').textContent.startsWith('Last checked')")
                        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                        assert await page.locator('#error').inner_text()==''
                        await page.screenshot(path=str(root/f'{mode}-{width}.png'),full_page=True)
                        (root/f'{mode}-{width}.aria.txt').write_text(await page.locator('body').aria_snapshot())
                        assert not errors,errors
                        await page.get_by_role('button',name='Log out',exact=True).click()
                        await page.locator('#login').wait_for(state='visible')
                        assert await page.locator('#console').is_hidden()
                        cases.append({'case':f'{mode}-{width}-sign-in-index-rebuild-no-errors-no-overflow-logout','passed':True})
                        await context.close()
                finally:hub.stop()
        finally:await browser.close();provider.close();model.close()
    return cases

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True);p.add_argument('--report',default='verification/roadmap-browser.json')
    args=p.parse_args();root=Path('_build/tests/browser')/str(uuid4());root.mkdir(parents=True)
    cases=asyncio.run(checks(json.loads(args.command),root))
    Path(args.report).write_text(json.dumps({'schema':'adhd/browser-acceptance@1','passed':True,'cases':cases,'captures':str(root)},indent=2)+'\n')
    print('PASS',len(cases),'rendered browser scenarios')
if __name__=='__main__':main()
