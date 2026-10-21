#!/usr/bin/env python3
"""Rendered structured optimizer policy, mode, selection reset and role boundaries."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--command');m.add_argument('--image');p.add_argument('--report',default='verification/optimization-browser.json');a=p.parse_args()
    parent=Path('_build/roadmap/optimization-browser').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',json.loads(a.command) if a.command else [],a.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'optimization-browser','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'}};h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def admin(c):return Client(h,h.config['admin_token']).api(c)
    def wait(fn):
        end=time.monotonic()+30
        while time.monotonic()<end:
            if fn():return
            time.sleep(.05)
        raise AssertionError('Browser fixture deadline '+str(root))
    try:
        h.start();pid=h.pid
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=viewport);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.goto(h.base+'/admin');page.get_by_label('Administrator token').fill(h.config['admin_token']);page.get_by_role('button',name='Sign in',exact=True).click();expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
                page.get_by_role('button',name='Settings',exact=True).click();group=page.get_by_role('group',name='Adaptive index optimization',exact=True);expect(group).to_be_visible();group.get_by_label('Enable adaptive index optimization',exact=True).check();group.get_by_label('Optimization mode',exact=True).select_option('automatic')
                for label,value in {'Maximum retained proposals':'12','Maximum active proposals':'2','Maximum recipe variants':'5','Candidate index build batch':'3','Required independent confirmed gaps':'3','Aggregate model calls':'256'}.items():group.get_by_label(label,exact=True).fill(value)
                page.get_by_role('button',name='Validate settings',exact=True).click();expect(page.locator('#status')).to_have_text('Settings are valid.');page.get_by_role('button',name='Confirm and save settings',exact=True).click();wait(lambda:admin({'op':'config_get'})['config']['optimization']['mode']=='automatic');expect(page.get_by_role('group',name='Adaptive index optimization',exact=True).get_by_label('Optimization mode',exact=True)).to_have_value('automatic')
                page.get_by_role('button',name='Optimization',exact=True).click();expect(page.get_by_role('heading',name='Optimization',exact=True)).to_be_visible();expect(page.get_by_role('heading',name='Index selection',exact=True)).to_be_visible();expect(page.get_by_text('No index proposals.',exact=True)).to_be_visible()
                before=admin({'op':'retrieval_index'})['index']['selection']['revision'];page.get_by_role('button',name='Reset to operator recipe',exact=True).click();wait(lambda:admin({'op':'retrieval_index'})['index']['selection']['revision']==before+1)
                page.get_by_role('button',name='Copy effective recipe to base',exact=True).click();wait(lambda:admin({'op':'retrieval_index'})['index']['selection']['revision']==before+2)
                expect(page.get_by_role('button',name='Build and restore previous recipe',exact=True)).to_have_count(0)
                assert h.pid==pid and not errors,errors;assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),name
                page.screenshot(path=str(root/(name+'.png')),full_page=True);cases.append({'case':name+'-hot-optimizer-mode-policy-and-durable-selection-controls','passed':True});print('PASS',cases[-1]['case'],flush=True);context.close()
            browser.close()
        report={'schema':'adhd-optimization-browser-report@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(h.command[-1]).read_bytes()).hexdigest() if h.command else None,'image':a.image,'workdir':str(root.relative_to(Path.cwd()))};Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
