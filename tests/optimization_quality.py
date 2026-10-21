#!/usr/bin/env python3
"""Real typed-model training freeze, subsequently authored held-out evidence and atomic selection."""
import argparse,copy,hashlib,json,secrets,tempfile,time
from pathlib import Path
from contextlib import ExitStack
import jsonschema
from protocol_acceptance import ByteValidator,check_critical_annotations
from foundation_acceptance import Runtime,Client,free_port


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image');p.add_argument('--model-url',default='http://127.0.0.1:18770/v1/systemone');p.add_argument('--automatic',action='store_true');p.add_argument('--browser',action='store_true');p.add_argument('--report',default='verification/optimization-quality.json');args=p.parse_args()
    parent=Path('_build/roadmap/optimization-quality').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));command=json.loads(args.command) if args.command else [];h=Runtime(root/'hub',command,args.image);cases=[]
    cfg={'project_id':'optimization-quality','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':args.model_url,'model':'Nemotron-Deciffusion-8B-v2.1'},'history':{'request_bytes':8192},'archive':{'audit_rate_ppm':0},'optimization':{'enabled':True}}
    h.file.write_text(json.dumps(cfg));h.file.chmod(0o600);browser_stack=ExitStack();page=None;page_errors=[]
    assert not (args.automatic and args.browser),'Use separate automatic and browser quality witnesses'
    def rpc(c):return Client(h).rpc(c,h.config['agents']['alice'])
    def admin(c,mutation=False):return Client(h,h.config['admin_token']).api(c,mutation=mutation)
    def wait(fn,seconds=240):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if v:=fn():return v
            time.sleep(.1)
        raise AssertionError('Optimizer quality deadline '+str(root))
    def pub(text,tag,reply=None):return rpc({'op':'publish_record','text':text,'information_type':tag,**({'context':{'links':[{'relation':'reply','publication_id':reply}]}} if reply else {})})['record']['publication']['id']
    def record(name,**data):cases.append({'case':name,'passed':True,**data});print('PASS',name,flush=True)
    def create_case(tag,entity,cohort,reply='Yes',asked=None,tags=None):
        question=f'Was capsule {asked or entity} delivered to the collection bay?'
        first=pub(f'Did capsule {entity} reach the collection bay?','thread');middle=pub('Message acknowledgement.','thread',first);last=pub(reply,tag,middle)
        wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        q=rpc({'op':'query_archive','question':question,'scope':{'information_type':tag}})['query']
        q=wait(lambda:v if (v:=rpc({'op':'get_archive_query','query_id':q['id']})['query'])['status']!='pending' else None)
        assert q['status']=='completed',(q['status'],q['error'])
        a=wait(lambda:[v for v in rpc({'op':'list_retrieval_attempts','limit':64})['items'] if v['archive_query_id']==q['id']])[0]
        noev=asked is not None
        admin({'op':'save_retrieval_label','attempt_id':a['id'],'expected_label_revision':0,'label':{'expectation':'no_evidence' if noev else 'supported','support_ids':[] if noev else [first,last],'cohort':cohort,'tags':tags or [],'note':'Independent authored optimizer assertion; neutral acknowledgement is not gold.','confirmed':True}},True)
        (root/(tag+'-original.json')).write_text(json.dumps({'archive':q,'attempt':admin({'op':'feedback_attempt','attempt_id':a['id']})['attempt']},indent=2)+'\n')
        return a['id']
    def proposal(id):
        q=admin({'op':'index_proposal','proposal_id':id,'limit':64})['proposal'];(root/(id+'.json')).write_text(json.dumps(q,indent=2)+'\n');return q
    def settled(id):return wait(lambda:q if (q:=proposal(id))['status']!='pending' else None)
    def validate(name,v):ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker()).validate(v)
    try:
        h.start();pid=h.pid
        if args.browser:
            from playwright.sync_api import sync_playwright,expect
            pw=browser_stack.enter_context(sync_playwright());browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);browser_stack.callback(browser.close);context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();page.on('pageerror',lambda e:page_errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.goto(h.base+'/admin');page.get_by_label('Administrator token').fill(h.config['admin_token']);page.get_by_role('button',name='Sign in',exact=True).click();expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible()
        schema=Client(h).get('/protocol/schema')[1];jsonschema.Draft202012Validator.check_schema(schema);check_critical_annotations(schema)
        training=[create_case('context','Z','training'),create_case('contextother','M','training')]
        q=admin({'op':'propose_index','training_attempt_ids':training},True)['proposal'];id=q['id'];q=settled(id);validate('OptimizationProposal',q)
        assert q['status']=='awaiting_evaluation',(q['status'],q['error'],q['variants'])
        winner=q['winner_identity'];frozen_at=time.time_ns();frozen_watermark=rpc({'op':'retrieval_index'})['index']['publication_watermark']
        assert q['held_out_attempt_ids']==[] and q['regression_attempt_ids']==[]
        record('independent-training-freezes-one-winner-before-any-held-out-source-exists',winner=winner,training=training,freeze_watermark=frozen_watermark,usage=q['usage'])
        held=[create_case('freshfirst','T','held_out'),create_case('freshsecond','B','held_out'),create_case('freshthird','D','held_out'),create_case('freshother','J','held_out',asked='W')]
        regression=[create_case('negative','N','regression',reply='No',tags=['negation']),create_case('correction','R','regression',reply='Correction: No',tags=['correction'])]
        assert time.time_ns()>frozen_at
        before_promotion=rpc({'op':'retrieval_index'})['index']
        if args.automatic:
            admin({'op':'config_update','patch':{'optimization':{'mode':'automatic'}}},True)
            q=wait(lambda:q if (q:=proposal(id))['status'] not in ['pending','awaiting_evaluation'] else None)
        elif args.browser:
            page.get_by_role('button',name='Optimization',exact=True).click();expect(page.get_by_role('heading',name=id+' · awaiting_evaluation',exact=True)).to_be_visible();page.get_by_label('Fresh held-out attempt IDs',exact=True).fill('\n'.join(held));page.get_by_label('Regression attempt IDs',exact=True).fill('\n'.join(regression));page.get_by_role('button',name='Evaluate frozen winner',exact=True).click();q=settled(id)
        else:
            q=admin({'op':'evaluate_index','proposal_id':id,'held_out_attempt_ids':held,'regression_attempt_ids':regression},True)['proposal'];q=settled(id)
        validate('OptimizationProposal',q)
        assert q['status']==('promoted' if args.automatic else 'qualified') and q['winner_identity']==winner,(q['status'],q['error'],q['evaluation'])
        assert q['evaluation']['passed'] and q['evaluation']['mean_recall_gain_ppm']>0 and q['evaluation']['total_calls_delta']<=0 and q['evaluation']['total_bytes_delta']<=0
        assert q['evaluation']['answer_failures']==q['evaluation']['answer_regressions']==q['evaluation']['false_supports']==0
        final=[r for r in q['cases'] if r['cohort']!='training'];assert len(final)==6 and all(r['baseline']['answer_pass'] and r['candidate']['answer_pass'] for r in final)
        assert q['build']['status']=='ready' and q['index_manifest']['excluded']==0 and q['watermark']>frozen_watermark
        for forge in ['variant','base','child','gain','cost','eligibility','winner','watermark','masked-recall-loss']:
            bad=copy.deepcopy(q)
            if forge=='variant':bad['variants'][0]['recipe_identity']='0'*64
            if forge=='base':bad['base_recipe']['context_depth']=4
            if forge=='child':bad['children'][0]['run']+=1
            if forge=='gain':bad['cases'][0]['comparison']['retrieval_gain_ppm']+=1
            if forge=='cost':bad['usage']['calls']=bad['usage']['cumulative_calls']=0
            if forge=='eligibility':bad['evidence_available']=False;bad['status']='qualified'
            if forge=='winner':bad['winner_identity']='0'*64
            if forge=='watermark':bad['watermark']+=1
            if forge=='masked-recall-loss':
                row=next(r for r in bad['cases'] if r['cohort']=='regression' and r['candidate']['expected_gold']>0)
                gold=row['candidate']['expected_gold'];row['baseline'].update({'retrieved_gold':gold,'retrieval_recall_ppm':1000000});row['candidate'].update({'retrieved_gold':gold-1,'retrieval_recall_ppm':(gold-1)*1000000//gold});row['comparison']['retrieval_gain_ppm']=row['candidate']['retrieval_recall_ppm']-1000000;row['candidate'].update({'fallback':True,'full_scope':True});row['comparison']['fallback_delta']=int(row['candidate']['fallback'])-int(row['baseline']['fallback'])
                final=[r for r in bad['cases'] if r['cohort']!='training'];bad['evaluation']['mean_recall_gain_ppm']=sum(r['comparison']['retrieval_gain_ppm'] for r in final)//len(final)
                assert bad['evaluation']['mean_recall_gain_ppm']>0 and bad['evaluation']['answer_failures']==0
            errors=list(ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/OptimizationProposal'}).iter_errors(bad));assert errors,forge
        record('fresh-held-out-positives-nonempty-negative-and-negation-correction-controls-pass',evaluation=q['evaluation'],actual_usage=q['usage'],held_out=held,regression=regression)
        previous=before_promotion;old_recipe=previous['selection']['effective_recipe'];assert not previous['selection']['applied']
        if args.browser:
            page.get_by_role('button',name='Refresh',exact=True).click();expect(page.get_by_role('heading',name=id+' · qualified',exact=True)).to_be_visible();row=page.locator('section.row').filter(has=page.get_by_role('heading',name=id+' · qualified',exact=True));row.locator('summary').first.click();row.get_by_role('button',name='Inspect proposal evidence',exact=True).click()
            for name,viewport in [('qualified-desktop',{'width':1440,'height':1000}),('qualified-mobile',{'width':390,'height':844})]:
                page.set_viewport_size(viewport);assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');page.screenshot(path=str(root/(name+'.png')),full_page=True)
            row.get_by_role('button',name='Promote qualified recipe',exact=True).click();wait(lambda:rpc({'op':'retrieval_index'})['index']['selection']['applied']);q=proposal(id);assert not page_errors,page_errors
        elif not args.automatic:q=admin({'op':'promote_index','proposal_id':id,'expected_selection_revision':previous['selection']['revision']},True)['proposal']
        assert q['status']=='promoted'
        selected=rpc({'op':'retrieval_index'})['index'];validate('RetrievalIndexRead',selected)
        assert selected['status']=='ready' and selected['selection']['applied'] and selected['selection']['qualification_current']
        assert selected['active']['recipe']==selected['selection']['effective_recipe'] and selected['previous']['recipe']==old_recipe and selected['selection']['base_recipe']==old_recipe
        assert admin({'op':'config_get'})['config']['retrieval']['recipe']==old_recipe and h.pid==pid
        record('promotion-atomically-switches-complete-index-and-override-without-changing-operator-base',selection=selected['selection'])
        subscription=rpc({'op':'subscribe','description':'Capsule transport and delivery to the collection bay.'})['subscription']['id']
        publication=pub('Capsule T was delivered to the collection bay.','later')
        deliveries=wait(lambda:[d for d in rpc({'op':'poll'})['deliveries'] if d.get('publication_id')==publication],seconds=45)
        assert any(any(m['subscription_id']==subscription for m in d['matches']) for d in deliveries)
        wait(lambda:rpc({'op':'retrieval_index'})['index']['status']=='ready')
        caught=rpc({'op':'retrieval_index'})['index'];assert caught['previous']['recipe']==old_recipe and caught['selection']['previous']['recipe']==old_recipe
        record('ordinary-matching-and-publication-catchup-preserve-effective-selection-and-protected-rollback')
        # Rollback is recovery work and remains available with optimization disabled.
        admin({'op':'config_update','patch':{'optimization':{'enabled':False}}},True)
        q=admin({'op':'rollback_index','expected_selection_revision':caught['selection']['revision']},True)['proposal'];rollback=settled(q['id']);assert rollback['status']=='promoted',rollback['error']
        restored=rpc({'op':'retrieval_index'})['index'];assert restored['status']=='ready' and restored['selection']['effective_recipe']==old_recipe and restored['active']['source_watermark']==restored['publication_watermark']
        record('disabled-optimizer-allows-asynchronous-caught-up-atomic-rollback',selection=restored['selection'])
        report={'schema':'adhd-optimization-quality-report@1','passed':True,'model':cfg['matcher']['model'],'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest() if command else None,'image':args.image,'assessment_profile':{'history_request_bytes':8192,'min_confidence_ppm':500000},'automatic':args.automatic,'browser':args.browser,'workdir':str(root.relative_to(Path.cwd()))};Path(args.report).parent.mkdir(parents=True,exist_ok=True);Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:browser_stack.close();h.stop()

if __name__=='__main__':main()
