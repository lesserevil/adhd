#!/usr/bin/env python3
"""Desktop/mobile hot evaluator settings and owner-safe Admin retrieval evidence."""
import argparse,hashlib,json,re,tempfile,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from federation_acceptance import Hub
from retrieval_support import NoulFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--command',required=True);p.add_argument('--report',default='verification/retrieval-browser.json');args=p.parse_args();command=json.loads(args.command)
    parent=Path('_build/roadmap/retrieval-browser').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=NoulFixture();hub=Hub(command,root/'hub','retrieval-browser',model.url);hub.config.pop('federation');results=[]
    def query():return hub.call({'op':'retrieve','question':'What original evidence is available?'})['query']
    def finish(q,state):
        end=time.monotonic()+20
        while time.monotonic()<end:
            value=hub.call({'op':'get_retrieval','query_id':q['id']})['query']
            if value['status']!='pending':assert value['status']==state,value;return value
            time.sleep(.05)
        raise AssertionError('Retrieval UI fixture did not finish')
    try:
        hub.start();pid=hub.process.pid
        hub.call({'op':'publish_record','text':'Original browser evidence.','context':{'question':'Was this observed?','subject':'browser-observation'},'data':{'literal':'<script>window.RETRIEVAL_INJECTED=true</script>'}})
        hub.call({'op':'publish_record','text':'Second original browser evidence.'})
        end=time.monotonic()+15
        while hub.call({'op':'retrieval_index'})['index']['status']!='ready':
            assert time.monotonic()<end;time.sleep(.05)
        hub.call({'op':'send','recipient_id':'bob','text':'PRIVATE_RETRIEVAL_BROWSER_SENTINEL'})
        completed=finish(query(),'completed')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=viewport);page=context.new_page();failures=[]
                page.on('dialog',lambda dialog:dialog.accept());page.on('pageerror',lambda e:failures.append(str(e)))
                page.on('console',lambda msg:failures.append(msg.text) if msg.type=='error' else None)
                page.on('requestfailed',lambda req:failures.append(req.url));page.on('response',lambda response:failures.append('HTTP '+str(response.status)) if response.status>=400 else None)
                page.goto(hub.base+'/admin');page.get_by_label('Administrator token').fill(hub.config['admin_token']);page.get_by_role('button',name='Sign in',exact=True).click()
                expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
                page.get_by_role('button',name='Settings',exact=True).click();expect(page.get_by_role('group',name='Retrieval indexes',exact=True)).to_be_visible()
                page.get_by_label('Retrieval evaluator URL (blank uses subscription matcher)',exact=True).fill(model.url)
                page.get_by_label('Retrieval evaluator model (blank uses subscription matcher)',exact=True).fill('browser-model')
                page.get_by_label('Retrieval evaluator version',exact=True).fill('browser-policy-'+name)
                page.get_by_label('Index tokenizer',exact=True).select_option('identifiers')
                page.get_by_label('Index fragment size (bytes)',exact=True).fill('512')
                page.get_by_label('Retrieval semantic record budget',exact=True).fill('1')
                with page.expect_response(lambda response:response.url.endswith('/admin/api') and response.request.post_data_json.get('op')=='config_update'):
                    page.get_by_role('button',name='Confirm and save settings',exact=True).click()
                expect(page.get_by_label('Retrieval evaluator model (blank uses subscription matcher)',exact=True)).to_have_value('browser-model')
                assert hub.process.pid==pid
                end=time.monotonic()+15
                while hub.call({'op':'retrieval_index'})['index']['status']!='ready':
                    assert time.monotonic()<end;time.sleep(.05)
                before=hub.call({'op':'retrieval_index'})['index']['active']['id']
                with page.expect_response(lambda response:response.url.endswith('/admin/api') and response.request.post_data_json.get('op')=='rebuild_index'):
                    page.get_by_role('button',name='Rebuild index',exact=True).click()
                end=time.monotonic()+15
                while not ((index:=hub.call({'op':'retrieval_index'})['index'])['status']=='ready' and index['active']['id']!=before):
                    assert time.monotonic()<end;time.sleep(.05)
                partial=finish(query(),'partial');assert partial['evaluator']['model']=='browser-model' and partial['error']['code']=='BUDGET_RECORDS'
                page.get_by_role('button',name='Activity',exact=True).click();expect(page.get_by_role('heading',name='Query jobs',exact=True)).to_be_visible()
                row=page.locator('section.row').filter(has_text=re.compile(r'\b'+re.escape(partial['id'])+r'\b'))
                row.get_by_role('button',name='View query evidence',exact=True).click();expect(row.get_by_role('heading',name='Retrieval evidence · run 1',exact=True)).to_be_visible()
                row.locator('details').last.locator('summary').click();expect(row.locator('details').last.locator('pre')).to_contain_text('browser evidence.')
                assert not page.evaluate('window.RETRIEVAL_INJECTED===true')
                assert 'PRIVATE_RETRIEVAL_BROWSER_SENTINEL' not in page.locator('body').inner_text()
                page.screenshot(path=str(root/(name+'-evidence.png')),full_page=True)
                row.get_by_role('button',name='Cancel query',exact=True).click()
                expect(page.get_by_role('heading',name='Query jobs',exact=True)).to_be_visible();assert hub.call({'op':'get_retrieval','query_id':partial['id']})['query']['status']=='cancelled'
                page.get_by_role('button',name='Settings',exact=True).click();expect(page.get_by_role('group',name='Retrieval indexes',exact=True)).to_be_visible()
                page.get_by_label('Retrieval evaluator URL (blank uses subscription matcher)',exact=True).fill('')
                page.get_by_label('Retrieval evaluator model (blank uses subscription matcher)',exact=True).fill('')
                page.get_by_label('Retrieval semantic record budget',exact=True).fill('64')
                with page.expect_response(lambda response:response.url.endswith('/admin/api') and response.request.post_data_json.get('op')=='config_update'):
                    page.get_by_role('button',name='Confirm and save settings',exact=True).click()
                expect(page.get_by_label('Retrieval evaluator model (blank uses subscription matcher)',exact=True)).to_have_value('')
                current=finish(query(),'completed');assert current['evaluator']['model']=='Nemotron-Deciffusion-8B-v2.1'
                assert hub.process.pid==pid and page.evaluate('document.documentElement.scrollWidth<=innerWidth') and not failures,failures
                page.screenshot(path=str(root/(name+'-settings.png')),full_page=True);(root/(name+'.txt')).write_text(page.locator('body').aria_snapshot())
                results.append({'viewport':viewport,'passed':True,'normal_path_errors':failures,'captures':str(root.relative_to(Path.cwd()))});context.close()
            browser.close()
        Path(args.report).write_text(json.dumps({'schema':'adhd/retrieval-browser@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'viewports':results},indent=2)+'\n');print('PASS desktop/mobile hot settings, inheritance, evidence and cancellation')
    finally:hub.stop();model.close()

if __name__=='__main__':main()
