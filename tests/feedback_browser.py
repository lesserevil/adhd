#!/usr/bin/env python3
"""Rendered desktop/mobile adjudication, paired replay, retirement and hot settings."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from foundation_acceptance import Runtime,Client,free_port
from archive_support import ArchiveFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--report',default='verification/feedback-browser.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/feedback-browser').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=ArchiveFixture();cases=[]
    cfg={'project_id':'feedback-browser','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'},'archive':{'audit_rate_ppm':0}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(c):return Client(h).rpc(c,h.config['agents']['alice'])
    def wait(fn):
        end=time.monotonic()+30
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.05)
        raise AssertionError('Browser fixture deadline '+str(root))
    try:
        h.start();pid=h.pid;pub=rpc({'op':'publish_record','text':'Sample browser result λ.'})['record']['publication']['id'];wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        q=rpc({'op':'query_archive','question':'Which browser result was reported?'})['query'];wait(lambda:rpc({'op':'get_archive_query','query_id':q['id']})['query']['status']=='completed');a=wait(lambda:rpc({'op':'list_retrieval_attempts'})['items'])[0]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=viewport);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
                page.goto('http://127.0.0.1:'+str(h.config['port'])+'/admin');page.get_by_label('Administrator token').fill(h.config['admin_token']);page.get_by_role('button',name='Sign in',exact=True).click();expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
                page.get_by_role('button',name='Settings',exact=True).click();group=page.get_by_role('group',name='Feedback and replay',exact=True);expect(group).to_be_visible()
                values={'Maximum feedback and replay state (bytes)':'33554432','Maximum retained attempts':'1024','Maximum retained replays':'256','Maximum active replays':'16','Replay native build batch':'4','Replay work records per branch':'1024','Replay model calls per branch':'256','Replay request bytes per branch':'2097152','Replay active time per branch (ms)':'120000'}
                group.get_by_label('Capture terminal Archive attempts',exact=True).check()
                for label,value in values.items():group.get_by_label(label,exact=True).fill(value)
                page.get_by_role('button',name='Validate settings',exact=True).click();expect(page.locator('#status')).to_have_text('Settings are valid.');page.get_by_role('button',name='Confirm and save settings',exact=True).click();wait(lambda:Client(h,h.config['admin_token']).api({'op':'config_get'})['config']['feedback']['build_batch']==4);expect(page.get_by_role('group',name='Feedback and replay',exact=True).get_by_label('Replay native build batch',exact=True)).to_have_value('4')
                page.get_by_role('button',name='Feedback',exact=True).click();expect(page.get_by_role('heading',name='Which browser result was reported?',exact=True)).to_be_visible();page.get_by_role('button',name='Inspect attempt',exact=True).click()
                page.get_by_text('Confirm or revise label',exact=True).click();page.get_by_label('Supporting original IDs, one per line',exact=True).fill(pub);page.get_by_label('Adjudication note',exact=True).fill('Browser '+name+' independent assertion');page.get_by_label('I independently confirm this label',exact=True).check();page.get_by_role('button',name='Confirm label revision',exact=True).click();expect(page.get_by_text('Confirm or revise label',exact=True)).to_have_count(0)
                page.get_by_role('button',name='Inspect attempt',exact=True).click();page.get_by_text('Compare candidate recipe',exact=True).click();page.get_by_label('Candidate context depth',exact=True).fill('2');page.get_by_role('button',name='Start paired replay',exact=True).click();expect(page.locator('#status')).to_contain_text('Replay submitted')
                replays=wait(lambda:Client(h,h.config['admin_token']).api({'op':'query_jobs','kind':'replay'})['items']);id=replays[0]['query']['id'];wait(lambda:rpc({'op':'get_retrieval_replay','query_id':id})['query']['status']=='completed')
                page.get_by_role('button',name='Activity',exact=True).click();expect(page.get_by_text('replay · '+id+' · alice · completed',exact=True)).to_be_visible();row=page.locator('section.row').filter(has=page.get_by_text('replay · '+id+' · alice · completed',exact=True));row.get_by_role('button',name='View query evidence',exact=True).click();expect(row.get_by_role('heading',name='Replay evidence · run 1',exact=True)).to_be_visible();row.get_by_role('button',name='Retire replay evidence',exact=True).click();expect(row.get_by_role('button',name='Retire replay evidence',exact=True)).to_have_count(0)
                assert not rpc({'op':'get_retrieval_replay','query_id':id})['query']['evidence_available'];assert h.pid==pid
                page.screenshot(path=str(root/(name+'.png')),full_page=True);assert not errors,errors;cases.append({'case':name+'-hot-settings-label-replay-evidence-retirement','passed':True});print('PASS',cases[-1]['case'],flush=True);context.close()
            browser.close()
        result={'schema':'adhd/feedback-browser@1','passed':True,'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
