#!/usr/bin/env python3
"""Independent candidate retrieval, frozen input, protocol, fault and restart checks."""
import argparse,copy,hashlib,json,secrets,tempfile,time
from pathlib import Path
import jsonschema
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator
from retrieval_support import NoulFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image')
    p.add_argument('--report',default='verification/retrieval-lifecycle.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/retrieval-tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',command,args.image);model=NoulFixture();cases=[]
    config={'project_id':'retrieval-fixture','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{a:secrets.token_urlsafe(32) for a in ('alice','bob')},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':1000,'retry_ms':100},'retrieval':{'timeout_ms':1000}}
    h.file.write_text(json.dumps(config));h.file.chmod(0o600)
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def wait(fn,message='Retrieval deadline',seconds=25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.025)
        raise AssertionError(message)
    def rpc(body,actor='alice',mid=None):return Client(h).rpc(body,h.config['agents'][actor],mid=mid)
    def error(body,reason,actor='alice',mid=None):
        envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':mid or secrets.token_urlsafe(18),'role':'ROLE_USER','parts':[{'data':body}]}}}
        status,value,_=Client(h).request('/a2a',envelope,{'Authorization':'Bearer '+h.config['agents'][actor]})
        assert status==200 and 'error' in value,(status,value)
        if reason=='INVALID_PARAMS':assert value['error']['code']==-32602,value
        else:assert value['error']['data'][0]['reason']==reason,value
    def update(patch):return Client(h,h.config['admin_token']).api({'op':'config_update','patch':patch},mutation=True)
    def publish(tag,text='Unicode λ record',**extra):return rpc({'op':'publish_record','information_type':tag,'text':text,**extra})['record']
    def index():return rpc({'op':'retrieval_index'})['index']
    def ready():return wait(lambda:(v if (v:=index())['status'] in ('ready','partial') else None),'Index did not catch up')
    def submit(tag,**extra):return rpc({'op':'retrieve','question':'Which Unicode record was reported?','scope':{'information_type':tag},**extra})['query']
    def get(q,**extra):return rpc({'op':'get_retrieval','query_id':q['id'],**extra})['query']
    def finish(q,status='completed'):
        value=wait(lambda:(v if (v:=get(q))['status']!='pending' else None));assert value['status']==status,(value['status'],value['error']);return value
    try:
        h.start();admin=Client(h,h.config['admin_token']);schema=admin.get('/protocol/schema')[1];jsonschema.Draft202012Validator.check_schema(schema)
        def valid(name,value,expected=True):
            validator=ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker())
            errors=list(validator.iter_errors(value));assert bool(errors)!=expected,(name,[e.message for e in errors])
        zero=ready();valid('RetrievalIndexRead',zero);assert zero['active']['indexed']==0
        empty=finish(submit('empty'));assert empty['usage']['calls']==0 and empty['coverage']['total']==0 and not empty['coverage']['exhaustive']
        a=publish('basic',data={'key':'λ'});ready();cmd={'op':'retrieve','question':'Which Unicode record was reported?','scope':{'information_type':'basic'}}
        q=rpc(cmd,mid='stable-retrieve')['query'];assert rpc(cmd,mid='stable-retrieve')['query']==q
        error({**cmd,'question':'Changed question'},'IDEMPOTENCY_CONFLICT',mid='stable-retrieve')
        error({'op':'get_retrieval','query_id':q['id']},'NOT_FOUND','bob');error({'op':'cancel_retrieval','query_id':q['id']},'NOT_FOUND','bob')
        q=finish(q);valid('RetrievalQuery',q);assert q['candidates'][0]['publication_id']==a['publication']['id']
        assert q['coverage']['semantic_examined']==1 and q['usage']['records']==1 and not q['coverage']['exhaustive']
        record('empty-index-owned-idempotent-async-jobs-and-closed-wire-shapes')
        evaluation=q['evaluations'][0];valid('RetrievalEvaluation',evaluation)
        for path,value in [(['request','state','candidate','fragments',0,'text'],'forged'),(['fragment_truncated'],not evaluation['fragment_truncated']),(['response','model'],'wrong-model'),(['response','answers','useful','noul'],True),(['fragments',0,'end'],999)]:
            bad=copy.deepcopy(evaluation);target=bad
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value;valid('RetrievalEvaluation',bad,False)
        fragment=copy.deepcopy(evaluation['fragments'][0]);fragment.update(text='λ',start=7,end=9,sha256=hashlib.sha256('λ'.encode()).hexdigest());valid('RetrievalFragment',fragment)
        fragment['end']=8;valid('RetrievalFragment',fragment,False)
        # Both agent and administrator may request this safe command. Root convenience
        # union must accept commands shared by those otherwise closed schemas.
        assert ByteValidator(schema).is_valid({'op':'retrieval_index'})
        record('independent-utf8-span-model-pairing-and-fragment-projection-negatives')
        for bad in [{'op':'retrieve','question':' '},{'op':'retrieve','question':'x','limit':True},{'op':'retrieve','question':'x','scope':{'unknown':1}},{'op':'retrieval_index','extra':1},{'op':'get_retrieval','query_id':q['id'],'run':0}]:error(bad,'INVALID_PARAMS')
        for patch in [{'retrieval':{'recipe':{'lexical_weight':0,'semantic_weight':0}}},{'retrieval':{'recipe':{'tokenizer':'sql'}}},{'retrieval':{'model_fragments':True}}]:
            status,value,_=admin.request('/admin/api',{'op':'config_update','patch':patch,'expected_revision':h.config.get('config_revision',1),'confirm':True,'message_id':secrets.token_urlsafe(12)})
            assert status==400,(status,value)
        record('invalid-commands-recipes-and-config-types-fail-closed')
        publish('budget','First Unicode record');publish('budget','Second Unicode record');ready()
        limited=finish(submit('budget',budget={'records':1}),'partial');assert limited['error']['code']=='BUDGET_RECORDS' and limited['coverage']['semantic_target']==2 and limited['coverage']['semantic_examined']==1
        resumed=finish(rpc({'op':'continue_retrieval','query_id':limited['id'],'budget':{'records':1}})['query']);assert resumed['coverage']['semantic_examined']==2 and resumed['usage']['cumulative_records']==2
        old=get(resumed,run=1);assert old['status']=='partial' and old['coverage']['semantic_examined']==1
        first=get(resumed,limit=1);second=get(resumed,offset=first['next_offset'],limit=1);assert len(first['evaluations'])==len(second['evaluations'])==1 and second['next_offset'] is None
        byte_limited=finish(submit('basic',budget={'bytes':1024}),'partial');assert byte_limited['error']['code']=='BUDGET_BYTES' and byte_limited['usage']['calls']==0
        record('bounded-semantic-window-continuation-cumulative-cost-and-evidence-pagination')
        for mode in ('error','wrong-model','boolean','wrong-type','extra-answer','extra-field','missing','out-of-range','nonfinite','oversized','duplicate'):
            model.mode=mode;failed=finish(submit('basic'),'partial')
            assert failed['error']['code']=='MODEL_ERROR' and failed['coverage']['semantic_examined']==0 and failed['usage']['calls']==1,(mode,failed['error'])
        model.mode='normal';fixed=finish(rpc({'op':'continue_retrieval','query_id':failed['id']})['query']);assert fixed['usage']['cumulative_calls']==2
        record('provider-errors-malformed-typed-probabilities-size-and-duplicate-key-rejection')
        model.mode='slow';model.delay=.7;timed=finish(submit('basic',budget={'time_ms':100}),'partial');assert timed['error']['code']=='BUDGET_TIME' and timed['coverage']['semantic_examined']==0
        before=len(model.useful());cancelled=submit('basic');wait(lambda:len(model.useful())>before);cancelled=rpc({'op':'cancel_retrieval','query_id':cancelled['id']})['query'];time.sleep(.8)
        assert get(cancelled)['status']=='cancelled' and get(cancelled)['coverage']['semantic_examined']==0
        before=len(model.useful());drift=submit('basic');wait(lambda:len(model.useful())>before);pid=h.pid;update({'retrieval':{'operator_version':'next-version'}});assert h.pid==pid
        drift=finish(drift,'invalidated');assert drift['error']['code']=='CONFIG_CHANGED' and not drift['evaluations']
        model.mode='normal';drift=finish(rpc({'op':'continue_retrieval','query_id':drift['id'],'restart':True})['query']);assert drift['evaluator']['operator_version']=='next-version'
        record('active-time-limits-cancellation-and-hot-evaluator-drift-fence-late-results')
        # A new incoming correction must update old contextual rows, while an explicitly
        # frozen old snapshot reconstructs rows and document statistics without it.
        base=publish('frozen','Original Unicode statement',context={'subject':'scope-one'});ready();mark=index()['publication_watermark']
        old_q=finish(submit('frozen',scope={'information_type':'frozen','watermark':mark}));old_input=old_q['input_manifest_identity']
        correction=publish('correction','Corrected Unicode statement',context={'subject':'scope-one','links':[{'relation':'corrects','publication_id':base['publication']['id']}]});ready()
        now_q=finish(submit('frozen'));replay=finish(submit('frozen',scope={'information_type':'frozen','watermark':mark}))
        assert correction['publication']['id'] in now_q['coverage']['expanded_ids'] and now_q['input_manifest_identity']!=old_input
        assert replay['input_manifest_identity']==old_input and correction['publication']['id'] not in replay['coverage']['expanded_ids'] and replay['coverage']['reconstructed']
        assert replay['candidates'][0]['lexical_ppm']==old_q['candidates'][0]['lexical_ppm']
        record('incoming-corrections-reindex-old-context-and-frozen-replay-excludes-future-statistics')
        before_index=ready()['active'];cfg=admin.api({'op':'config_get'});rebuilt=admin.api({'op':'rebuild_index'},mutation=True)['index'];valid('RetrievalIndexRead',rebuilt)
        after=wait(lambda:(v if (v:=index())['active'] and v['active']['id']!=before_index['id'] and v['status']=='ready' else None))
        assert after['previous']['id']==before_index['id'] and h.config.get('config_revision',1)==cfg['config_revision']
        record('admin-rebuild-atomic-switch-previous-generation-and-unchanged-config-revision')
        model.mode='slow';model.delay=1.5;before=len(model.useful());crash=submit('basic');wait(lambda:len(model.useful())>before);h.stop(hard=True);model.mode='normal';h.start();ready();crash=finish(crash)
        assert crash['usage']['uncertain_calls']==1 and crash['usage']['calls']==2 and crash['usage']['records']==1
        assert get(resumed,run=1)['status']=='partial' and get(replay)['input_manifest_identity']==old_input
        record('real-hard-restart-conservatively-settles-leases-and-preserves-frozen-prior-runs')
        report={'passed':True,'command':command,'image':args.image,'cases':cases}
        if command and Path(command[-1]).is_file():report['artifact_sha256']=hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:h.stop();model.close()

if __name__=='__main__':main()
