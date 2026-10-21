#!/usr/bin/env python3
"""Desktop/mobile structured archive settings, private evidence and cancellation."""
import argparse,hashlib,json,re,tempfile,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from federation_acceptance import Hub
from archive_support import ArchiveFixture

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--command',required=True);parser.add_argument('--report',default='verification/archive-browser.json');args=parser.parse_args();command=json.loads(args.command)
    parent=Path('_build/roadmap/archive-browser').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    model=ArchiveFixture();hub=Hub(command,root/'hub','archive-browser',model.url);hub.config.pop('federation');hub.config['archive']={'audit_rate_ppm':0};results=[]
    def query():return hub.call({'op':'query_archive','question':'Which sample reports the Unicode result?','mode':'search'})['query']
    def finish(q,state):
        end=time.monotonic()+25
        while time.monotonic()<end:
            value=hub.call({'op':'get_archive_query','query_id':q['id']})['query']
            if value['status']!='pending':assert value['status']==state,value['error'];return value
            time.sleep(.05)
        raise AssertionError('Archive browser fixture did not finish')
    try:
        hub.start();pid=hub.process.pid
        hub.call({'op':'publish_record','text':'Sample Unicode result λ.','data':{'literal':'<script>window.ARCHIVE_INJECTED=true</script>'}})
        hub.call({'op':'publish_record','text':'Second sample Unicode result.'})
        end=time.monotonic()+15
        while hub.call({'op':'retrieval_index'})['index']['status']!='ready':assert time.monotonic()<end;time.sleep(.05)
        hub.call({'op':'send','recipient_id':'bob','text':'PRIVATE_ARCHIVE_BROWSER_SENTINEL'});finish(query(),'completed')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=viewport);page=context.new_page();failures=[]
                page.on('dialog',lambda dialog:dialog.accept());page.on('pageerror',lambda error:failures.append(str(error)))
                page.on('console',lambda msg:failures.append(msg.text) if msg.type=='error' else None)
                page.on('requestfailed',lambda req:failures.append(req.url));page.on('response',lambda response:failures.append('HTTP '+str(response.status)) if response.status>=400 else None)
                page.goto(hub.base+'/admin');page.get_by_label('Administrator token').fill(hub.config['admin_token']);page.get_by_role('button',name='Sign in',exact=True).click()
                expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible();page.get_by_role('button',name='Settings',exact=True).click()
                group=page.get_by_role('group',name='Archive questions',exact=True);expect(group).to_be_visible()
                group.get_by_label('Enable archive questions',exact=True).check();group.get_by_label('Default archive mode',exact=True).select_option('search')
                group.get_by_label('Archive planner URL (blank uses history evaluator)',exact=True).fill(model.url)
                group.get_by_label('Archive planner model (blank uses history evaluator)',exact=True).fill('browser-model')
                group.get_by_label('Archive planner version',exact=True).fill('browser-'+name)
                for label,value in [('Archive planner timeout (ms)','1500'),('Archive planner request limit (bytes)','6144'),('Archive planner minimum confidence (ppm)','500000'),('Maximum archive workflow state (bytes)','33554432'),('Successful search audit rate (ppm)','0')]:group.get_by_label(label,exact=True).fill(value)
                stages=['Intent planning','Candidate retrieval','Original support assessment','Fallback full scan','Sampled full scan audit']
                for stage in stages:
                    budget=group.get_by_role('group',name=stage,exact=True)
                    for label in ['Record budget','Model call budget','Request byte budget','Active time budget (ms)']:expect(budget.get_by_label(label,exact=True)).to_be_visible()
                group.get_by_role('group',name='Original support assessment',exact=True).get_by_label('Record budget',exact=True).fill('1')
                with page.expect_response(lambda response:response.url.endswith('/admin/api') and response.request.post_data_json.get('op')=='config_update'):page.get_by_role('button',name='Confirm and save settings',exact=True).click()
                expect(page.get_by_label('Archive planner model (blank uses history evaluator)',exact=True)).to_have_value('browser-model')
                partial=finish(query(),'partial');assert partial['policy']['planner']['model']=='browser-model' and partial['error']['code']=='BUDGET_RECORDS';assert hub.process.pid==pid
                page.get_by_role('button',name='Activity',exact=True).click();expect(page.get_by_role('heading',name='Query jobs',exact=True)).to_be_visible()
                row=page.locator('section.row').filter(has_text=re.compile(r'\b'+re.escape(partial['id'])+r'\b'));row.get_by_role('button',name='View query evidence',exact=True).click()
                expect(row.get_by_role('heading',name='Archive evidence · run 1',exact=True)).to_be_visible();row.locator('details').last.locator('summary').click()
                expect(row.locator('details').last.locator('pre')).to_contain_text('Which sample reports the Unicode result?')
                assert not page.evaluate('window.ARCHIVE_INJECTED===true') and 'PRIVATE_ARCHIVE_BROWSER_SENTINEL' not in page.locator('body').inner_text()
                page.screenshot(path=str(root/(name+'-evidence.png')),full_page=True)
                row.get_by_role('button',name='Cancel query',exact=True).click();expect(page.get_by_role('heading',name='Query jobs',exact=True)).to_be_visible();assert hub.call({'op':'get_archive_query','query_id':partial['id']})['query']['status']=='cancelled'
                page.get_by_role('button',name='Settings',exact=True).click();group=page.get_by_role('group',name='Archive questions',exact=True)
                group.get_by_label('Archive planner URL (blank uses history evaluator)',exact=True).fill('');group.get_by_label('Archive planner model (blank uses history evaluator)',exact=True).fill('')
                group.get_by_label('Default archive mode',exact=True).select_option('search_then_scan');group.get_by_role('group',name='Original support assessment',exact=True).get_by_label('Record budget',exact=True).fill('128')
                with page.expect_response(lambda response:response.url.endswith('/admin/api') and response.request.post_data_json.get('op')=='config_update'):page.get_by_role('button',name='Confirm and save settings',exact=True).click()
                expect(page.get_by_label('Archive planner model (blank uses history evaluator)',exact=True)).to_have_value('')
                current=finish(query(),'completed');assert current['policy']['planner']['model']=='Nemotron-Deciffusion-8B-v2.1'
                assert hub.process.pid==pid and page.evaluate('document.documentElement.scrollWidth<=innerWidth') and not failures,failures
                page.screenshot(path=str(root/(name+'-settings.png')),full_page=True);(root/(name+'.txt')).write_text(page.locator('body').aria_snapshot())
                results.append({'viewport':viewport,'passed':True,'normal_path_errors':failures,'captures':str(root.relative_to(Path.cwd()))});context.close()
            browser.close()
        Path(args.report).write_text(json.dumps({'schema':'adhd/archive-browser@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'viewports':results},indent=2)+'\n');print('PASS desktop/mobile archive settings, exact evidence and cancellation')
    finally:hub.stop();model.close()

if __name__=='__main__':main()
