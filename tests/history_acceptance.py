#!/usr/bin/env python3
"""Black-box durable history jobs, precise scopes, privacy and evaluator failures."""
import argparse,hashlib,json,secrets,subprocess,tempfile,time
from pathlib import Path
import jsonschema
from foundation_acceptance import Runtime,Client,free_port
from protocol_acceptance import ByteValidator
from history_support import ChoiceFixture


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--command');mode.add_argument('--image')
    p.add_argument('--report',default='verification/history-acceptance.json');args=p.parse_args();command=json.loads(args.command) if args.command else []
    parent=Path('_build/roadmap/history-tests').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));model=ChoiceFixture();hubs=[];cases=[]
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    def wait(fn,message,seconds=25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.05)
        raise AssertionError(message)
    def runtime(name,history=None):
        r=Runtime(root/name,command,args.image);hubs.append(r)
        c={'project_id':'history-fixture','store_path':str(r.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32),'bob':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':500,'retry_ms':100}}
        if history is not None:c['history']=history
        r.file.write_text(json.dumps(c));r.file.chmod(0o600);r.start();return r
    def rpc(r,body,actor='alice',mid=None):return Client(r).rpc(body,r.config['agents'][actor],mid=mid)
    def error(r,body,reason,actor='alice',mid=None):
        envelope={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':mid or secrets.token_urlsafe(18),'role':'ROLE_USER','parts':[{'data':body}]}}}
        status,value,_=Client(r).request('/a2a',envelope,{'Authorization':'Bearer '+r.config['agents'][actor]})
        assert status==200 and 'error' in value,(status,value)
        if reason=='INVALID_PARAMS':assert value['error']['code']==-32602,value
        else:assert value['error']['data'][0]['reason']==reason,value
    def update(r,patch):return Client(r,r.config['admin_token']).api({'op':'config_update','patch':patch},mutation=True)
    def publish(r,tag,text='An archived original.',**extra):return rpc(r,{'op':'publish_record','text':text,'information_type':tag,**extra})['record']
    def submit(r,tag,**extra):return rpc(r,{'op':'query_history','question':'What was explicitly reported?','scope':{'information_type':tag},**extra})['query']
    def get(r,q,**extra):return rpc(r,{'op':'get_history_query','query_id':q['id'],**extra})['query']
    def finish(r,q,status='completed'):
        v=wait(lambda:(value if (value:=get(r,q))['status']!='pending' else None),'History job did not terminate')
        assert v['status']==status,(v['status'],v['error']);return v
    try:
        h=runtime('main');admin=Client(h,h.config['admin_token']);schema=admin.get('/protocol/schema')[1]
        def valid(name,value):ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker()).validate(value)
        initial=admin.api({'op':'config_get'});valid('admin_result_config_get',initial);assert initial['config']['history']['url'] is None
        pub=publish(h,'identity');cmd={'op':'query_history','question':'What was explicitly reported?','scope':{'information_type':'identity'}}
        q=rpc(h,cmd,mid='history-stable-create')['query'];assert q['status']=='pending';assert rpc(h,cmd,mid='history-stable-create')['query']==q
        error(h,{**cmd,'question':'Changed question'},'IDEMPOTENCY_CONFLICT',mid='history-stable-create')
        error(h,{'op':'get_history_query','query_id':q['id']},'NOT_FOUND','bob');error(h,{'op':'cancel_history_query','query_id':q['id']},'NOT_FOUND','bob')
        q=finish(h,q);valid('HistoryQuery',q);assert q['answer']['support_ids']==[pub['publication']['id']]
        record('owned-query-creation-idempotency-conflicts-and-independent-wire-result')
        invalid=[{'op':'query_history','question':' '},{'op':'query_history','question':'x','complete':1},{'op':'query_history','question':'x','budget':{'calls':True}},{'op':'query_history','question':'x','budget':{'bytes':1023}},{'op':'query_history','question':'x','scope':{'watermark':1.0}},{'op':'query_history','question':'x','scope':{'unexpected':'x'}},{'op':'query_history','question':'x','scope':{'occurred_from':'2026-10-20T00:00:00.000002Z','occurred_until':'2026-10-20T00:00:00.000001Z'}},{'op':'query_history','question':'x','scope':{'occurred_from':'2026-10-20T00:00:00.0000001Z'}},{'op':'get_history_query','query_id':q['id'],'limit':65},{'op':'get_history_query','query_id':q['id'],'offset':True},{'op':'continue_history_query','query_id':q['id'],'restart':1}]
        for body in invalid:error(h,body,'INVALID_PARAMS')
        error(h,{'op':'query_history','question':'x','scope':{'watermark':9007199254740991}},'INVALID_PARAMS')
        empty=finish(h,submit(h,'no-records'));assert empty['outcome']=='no_evidence' and empty['usage']['calls']==0 and empty['coverage']['total']==0
        record('strict-types-time-precision-unknown-fields-future-watermarks-and-empty-scope')
        a=publish(h,'scope','Root report.',source={'kind':'slack','id':'room-A'},occurred_at='2026-10-20T00:00:00.000001Z',context={'subject':'scope-referent'})
        b=publish(h,'scope','Context report.',source={'kind':'email','id':'mail-B'},occurred_at='2026-10-20T00:00:00.000002Z',context={'subject':'scope-referent'})
        scoped=rpc(h,{'op':'query_history','question':'What was reported?','scope':{'information_type':'scope','source_kind':'slack','source_id':'room-A','occurred_from':'2026-10-20T02:00:00.000001+02:00','occurred_until':'2026-10-20T00:00:00.000001Z'}})['query'];scoped=finish(h,scoped)
        assert scoped['coverage']['total']==1 and scoped['coverage']['expanded_ids']==[b['publication']['id']]
        assert set(scoped['answer']['support_ids'])=={a['publication']['id'],b['publication']['id']}
        precise=finish(h,rpc(h,{'op':'query_history','question':'What was reported?','scope':{'information_type':'scope','occurred_from':'2026-10-20T00:00:00.000002Z','occurred_until':'2026-10-20T00:00:00.000002Z'}})['query'])
        assert precise['coverage']['total']==1
        record('intersected-source-event-time-microsecond-scope-and-labeled-public-context-expansion')
        private=rpc(h,{'op':'send','recipient_id':'bob','text':'private-history-sentinel'})['delivery'];publish(h,'frozen','Original snapshot report.',context={'subject':'frozen-subject','links':[{'relation':'reply','publication_id':private['id']}]})
        model.mode='slow';before=len(model.choices());frozen=submit(h,'frozen');wait(lambda:len(model.choices())>before,'Model reservation not observed')
        started=time.monotonic();later=publish(h,'frozen','Later correction outside this snapshot.',occurred_at='2025-01-01T00:00:00Z',context={'subject':'frozen-subject'});assert time.monotonic()-started<1
        frozen=finish(h,frozen);assert frozen['coverage']['total']==1 and later['publication']['id'] not in frozen['answer']['support_ids']
        assert all('private-history-sentinel' not in json.dumps(e['request']) and later['publication']['id'] not in e['record_ids'] for e in frozen['evaluations'])
        assert any(x['reason']=='unresolved' for x in frozen['coverage']['gaps']);model.mode='normal'
        record('frozen-membership-future-corrections-private-isolation-gaps-and-responsive-ingestion')
        publish(h,'budget','First independent report.');publish(h,'budget','Second independent report.')
        limited=finish(h,submit(h,'budget',budget={'records':1}),'partial');assert limited['error']['code']=='BUDGET_RECORDS' and limited['coverage']['examined']==1
        resumed=rpc(h,{'op':'continue_history_query','query_id':limited['id'],'budget':{'records':1}})['query'];resumed=finish(h,resumed)
        assert resumed['coverage']['examined']==2 and resumed['usage']['cumulative_records']==2 and resumed['usage']['records']==1
        old=get(h,resumed,run=1);assert old['status']=='partial' and old['coverage']['examined']==1
        pages=[];offset=0
        while True:
            page=get(h,resumed,limit=1,offset=offset);pages+=page['evaluations']
            if page['next_offset'] is None:break
            assert page['next_offset']>offset;offset=page['next_offset']
        assert len(pages)==resumed['evaluation_count']==3
        for evaluation in pages:
            valid('HistoryEvaluation',evaluation);valid('HistoryModelExchange',{'request':evaluation['request'],'response':{'model':evaluation['request']['model'],'answers':evaluation['answers']}})
        one=publish(h,'call-budget');calls=finish(h,submit(h,'call-budget',budget={'calls':1}),'partial')
        assert calls['error']['code']=='BUDGET_CALLS' and calls['coverage']['primary_complete'] and not calls['coverage']['final_complete']
        calls=finish(h,rpc(h,{'op':'continue_history_query','query_id':calls['id']})['query']);assert calls['usage']['cumulative_calls']==2
        byte_limited=finish(h,submit(h,'call-budget',budget={'bytes':1024}),'partial');assert byte_limited['error']['code']=='BUDGET_BYTES' and byte_limited['usage']['calls']==0
        record('record-call-byte-budgets-continuation-cumulative-cost-prior-runs-and-evidence-pagination')
        model.mode='slow';model.delay=.4;timed=finish(h,submit(h,'call-budget',budget={'time_ms':100}),'partial')
        assert timed['outcome']=='unavailable' and timed['error']['code']=='BUDGET_TIME' and timed['coverage']['examined']==0;model.mode='normal';model.delay=1.2
        record('active-time-budget-bounds-network-wait-and-never-marks-failed-groups-examined')
        faults=['error','wrong-model','boolean','wrong-type','missing-choice','unknown-choice','missing-probability','extra-probability','sum','not-maximum','confidence','extra-answer','extra-field','oversized']
        for mode in faults:
            model.mode=mode;failed=finish(h,submit(h,'call-budget'),'partial')
            assert failed['outcome']=='unavailable' and failed['error']['code']=='MODEL_ERROR' and failed['coverage']['examined']==0 and not failed['answer']['support_ids'],(mode,failed)
        model.mode='normal';fixed=finish(h,rpc(h,{'op':'continue_history_query','query_id':failed['id']})['query']);assert fixed['usage']['cumulative_calls']==3
        model.mode='low-confidence';uncertain=finish(h,submit(h,'call-budget'));assert uncertain['outcome']=='insufficient' and 'low_confidence' in uncertain['answer']['uncertainty'] and not uncertain['answer']['support_ids'];model.mode='normal'
        record('http-outage-malformed-typed-choices-distribution-errors-size-bounds-and-low-confidence')
        pid=h.pid;model.mode='slow';before=len(model.choices());drift=submit(h,'call-budget');wait(lambda:len(model.choices())>before,'Drift call not reserved')
        update(h,{'history':{'operator_version':'operator-generation-two'}});drift=get(h,drift)
        assert h.pid==pid and drift['status']=='invalidated' and drift['error']['code']=='CONFIG_CHANGED'
        model.mode='normal';drift=finish(h,rpc(h,{'op':'continue_history_query','query_id':drift['id'],'restart':True})['query'])
        assert drift['run']==2 and get(h,drift,run=1)['status']=='invalidated' and drift['usage']['cumulative_uncertain_calls']>=1
        assert drift['evaluator']['operator_version']=='operator-generation-two'
        record('hot-evaluator-drift-discards-inflight-results-and-explicit-restart-preserves-prior-run')
        update(h,{'history':{'request_bytes':1024}});large=finish(h,submit(h,'call-budget'),'partial');assert large['error']['code']=='CONTEXT_LIMIT' and large['usage']['calls']==0
        error(h,{'op':'continue_history_query','query_id':large['id']},'INVALID_PARAMS')
        update(h,{'history':{'request_bytes':6144}});large=finish(h,rpc(h,{'op':'continue_history_query','query_id':large['id'],'restart':True})['query'])
        update(h,{'history':{'url':model.url,'model':'override-model'}});override=finish(h,submit(h,'call-budget'));assert override['evaluator']['model']=='override-model'
        update(h,{'history':{'url':None,'model':None}});inherited=finish(h,submit(h,'call-budget'));assert inherited['evaluator']['model']=='Nemotron-Deciffusion-8B-v2.1'
        assert h.pid==pid;update(h,{'history':{'enabled':False}});error(h,{'op':'query_history','question':'Disabled'},'UNAVAILABLE');update(h,{'history':{'enabled':True}})
        record('hot-request-bounds-url-model-inheritance-disable-and-explicit-resumption-without-hub-restart')
        model.mode='slow';before=len(model.choices());cancelled=submit(h,'call-budget');wait(lambda:len(model.choices())>before,'Cancellation call not reserved')
        listed=admin.api({'op':'query_jobs','kind':'history'});valid('admin_result_query_jobs',listed);assert any(x['query']['id']==cancelled['id'] for x in listed['items'])
        inspected=admin.api({'op':'query_job','query_id':cancelled['id']});valid('admin_result_query_job',inspected)
        cancel={'op':'cancel_query_job','query_id':cancelled['id'],'message_id':'history-admin-cancel','confirm':True}
        first=admin.api(cancel);assert admin.api(cancel)==first and first['query']['status']=='cancelled'
        time.sleep(1.4);cancelled=get(h,cancelled);assert cancelled['status']=='cancelled'
        error(h,{'op':'continue_history_query','query_id':cancelled['id']},'INVALID_PARAMS');model.mode='normal'
        restarted=finish(h,rpc(h,{'op':'continue_history_query','query_id':cancelled['id'],'restart':True})['query']);assert restarted['run']==2
        historical=admin.api({'op':'query_job','query_id':restarted['id'],'run':1});assert historical['query']['status']=='cancelled'
        record('admin-list-detail-run-pages-actor-scoped-cancel-retry-and-late-reply-isolation')
        # A query must survive a real process kill with an inference reservation.
        earlier_private=rpc(h,{'op':'poll'},actor='bob')['deliveries']
        rpc(h,{'op':'subscribe','description':'Keep all public originals'},actor='bob');baseline=publish(h,'kill-state','Original with a durable source receipt.',source={'kind':'email','id':'origin','item_id':'history-kill-event'})
        delivery=wait(lambda:next((item for item in rpc(h,{'op':'poll'},actor='bob')['deliveries'] if item.get('publication_id')==baseline['publication']['id']),None),'Matching publication delivery not queued')
        rpc(h,{'op':'ack','delivery_ids':[delivery['id']]},actor='bob');queued=rpc(h,{'op':'send','recipient_id':'bob','text':'hard-kill-private-sentinel'})['delivery']
        model.mode='slow';before=len(model.choices());durable=submit(h,'kill-state');wait(lambda:len(model.choices())>before,'Durable reservation not accepted')
        h.stop(hard=True);model.mode='normal';h.start();durable=finish(h,durable)
        assert durable['usage']['uncertain_calls']>=1 and durable['usage']['calls']>=3 and durable['coverage']['examined']==1
        assert rpc(h,{'op':'poll'},actor='bob')['deliveries']==earlier_private+[queued]
        again=publish(h,'kill-state','Original with a durable source receipt.',source={'kind':'email','id':'origin','item_id':'history-kill-event'});assert again==baseline
        assert rpc(h,{'op':'poll'},actor='bob')['deliveries']==earlier_private+[queued]
        assert len(rpc(h,{'op':'search','information_type':'kill-state'})['publications'])==1
        raw=''.join(json.dumps(x['request']) for x in model.choices());assert 'hard-kill-private-sentinel' not in raw and 'private-history-sentinel' not in raw
        for token in [h.config['admin_token'],*h.config['agents'].values()]:assert token not in raw
        record('real-hard-kill-recovers-reservation-originals-source-retries-private-queues-and-acknowledgements')
        # Completed results and exact historical evidence retain the creation label.
        before=durable
        registry=Client(h,h.config['admin_token']).api({'op':'config_get'})['config']['projects']
        legacy=next(project for project in registry if project['id']==h.config['project_id'])
        legacy['name']='Renamed History fixture'
        update(h,{'projects':registry});after=get(h,durable);assert after==before
        h.stop(hard=True);h.start();assert get(h,durable)==before
        record('project-rename-and-restart-preserve-frozen-query-label-snapshot-and-model-evidence')
        # A small independent runtime makes capacity limits deterministic.
        capacity=runtime('capacity',{'max_state_bytes':1048576,'request_bytes':8192});capacity_original=publish(capacity,'capacity')['publication']['id'];limited=None
        for i in range(40):
            body={'op':'query_history','question':'Question '+str(i)+' '+('q'*1800),'scope':{'information_type':'capacity'}}
            try:created=rpc(capacity,body)['query']
            except AssertionError:break
            result=wait(lambda:(x if (x:=get(capacity,created))['status']!='pending' else None),'Capacity job did not finish')
            if result['status']=='partial':limited=result;break
        assert limited and limited['error']['code']=='RESOURCE_LIMIT',limited
        original=rpc(capacity,{'op':'get_record','publication_id':capacity_original});update(capacity,{'history':{'max_state_bytes':2097152}})
        recovered=finish(capacity,rpc(capacity,{'op':'continue_history_query','query_id':limited['id']})['query']);assert recovered['coverage']['primary_complete']
        assert rpc(capacity,{'op':'get_record','publication_id':capacity_original})==original
        record('bounded-derived-history-state-raising-hot-limit-and-continuing-never-deletes-originals')
        flood=runtime('active-budget');publish(flood,'active-budget');model.mode='error';active=[submit(flood,'active-budget') for _ in range(64)]
        error(flood,{'op':'query_history','question':'Exceeds the active limit'},'RESOURCE_EXHAUSTED')
        for query in active:rpc(flood,{'op':'cancel_history_query','query_id':query['id']})
        model.mode='normal';assert all(get(flood,x)['status']=='cancelled' for x in active)
        run=active[0]
        for expected_run in range(2,17):
            rpc(flood,{'op':'cancel_history_query','query_id':run['id']});run=rpc(flood,{'op':'continue_history_query','query_id':run['id'],'restart':True})['query'];assert run['run']==expected_run
        rpc(flood,{'op':'cancel_history_query','query_id':run['id']});error(flood,{'op':'continue_history_query','query_id':run['id'],'restart':True},'RESOURCE_EXHAUSTED')
        flood.stop(hard=True);flood.start();archived=get(flood,run);assert archived['status']=='cancelled' and len(archived['prior_runs'])==15
        record('active-job-and-run-count-bounds-cancellation-and-archived-runs-survive-restart')
        for runtime_value in hubs:
            runtime_value.stop();data=Path(runtime_value.config['store_path'])
            if Path(str(runtime_value.file)+'.stores').exists():
                from project_recovery_state import route
                data=route(runtime_value.file,runtime_value.config['project_id'])[1]
            content=data.read_bytes()+Path(str(data)+'.snapshot').read_bytes()
            for token in [runtime_value.config['admin_token'],*runtime_value.config['agents'].values()]:assert token.encode() not in content
        binding=({'image_id':subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()} if args.image else {'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest()})
        Path(args.report).write_text(json.dumps({'schema':'adhd/history-acceptance@1','passed':True,'cases':cases,**binding},indent=2)+'\n')
    finally:
        for runtime_value in hubs:runtime_value.stop()
        model.close()

if __name__=='__main__':main()
