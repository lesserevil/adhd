#!/usr/bin/env python3
"""Render original communication context at desktop and narrow mobile widths."""
import argparse,hashlib,json,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from federation_acceptance import Hub
from hub_acceptance import ModelFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True);p.add_argument('--report',default='verification/context-browser.json');args=p.parse_args()
    parent=Path('_build/roadmap/context-browser').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));command=json.loads(args.command)
    model=ModelFixture();hub=Hub(command,root/'hub','context-browser',model.url);hub.config.pop('federation');results=[]
    try:
        hub.start();hub.call({'op':'publish_record','text':'Yes','context':{'question':'Is there a bird in that tree?','subject':'tree-1','links':[{'relation':'reply','publication_id':'missing-question'}]},'data':{'literal':'<script>throw 1</script>'}})
        hub.call({'op':'send','recipient_id':'bob','text':'PRIVATE_CONTEXT_BROWSER_SENTINEL'})
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=viewport);page=context.new_page();failures=[]
                page.on('pageerror',lambda e:failures.append(str(e)));page.on('console',lambda m:failures.append(m.text) if m.type=='error' else None)
                page.on('requestfailed',lambda r:failures.append(r.url));page.on('response',lambda r:failures.append('HTTP '+str(r.status)) if r.status>=400 else None)
                page.goto(hub.base+'/admin');page.get_by_label('Administrator token').fill(hub.config['admin_token']);page.get_by_role('button',name='Sign in',exact=True).click()
                expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible();page.get_by_role('button',name='Information',exact=True).click()
                page.get_by_role('button',name='View details',exact=True).click();expect(page.get_by_role('heading',name='Communication context',exact=True)).to_be_visible()
                details=page.locator('details').last;details.locator('summary').click();expect(details.locator('pre')).to_be_visible()
                expect(details.locator('pre')).to_contain_text('Is there a bird in that tree?');expect(details.locator('pre')).to_contain_text('unresolved');expect(details.locator('pre')).to_contain_text('<script>throw 1</script>')
                assert 'PRIVATE_CONTEXT_BROWSER_SENTINEL' not in page.locator('body').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth') and not failures,failures
                screenshot=root/(name+'.png');page.screenshot(path=str(screenshot),full_page=True);(root/(name+'.txt')).write_text(page.locator('body').aria_snapshot())
                results.append({'viewport':viewport,'passed':True,'normal_path_errors':failures,'screenshot':str(screenshot.relative_to(Path.cwd()))});context.close()
            browser.close()
        Path(args.report).write_text(json.dumps({'schema':'adhd/context-browser@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'viewports':results},indent=2)+'\n')
        print('PASS desktop/mobile original context, provenance and private isolation')
    finally:hub.stop();model.close()


if __name__=='__main__':main()
