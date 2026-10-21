#!/usr/bin/env python3
"""Actual prior-binary history template migration, preserved evidence and lease fencing."""
import argparse,hashlib,json,secrets,tempfile,time
from pathlib import Path
import jsonschema
from foundation_acceptance import Runtime,Client,free_port
from history_support import ChoiceFixture
from protocol_acceptance import ByteValidator

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--command',required=True);parser.add_argument('--producer-command',required=True);parser.add_argument('--image');parser.add_argument('--report',required=True);args=parser.parse_args();command=json.loads(args.command);producer=json.loads(args.producer_command)
    parent=Path('_build/roadmap/template-upgrade').resolve();parent.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));h=Runtime(root/'hub',producer);model=ChoiceFixture()
    cfg={'project_id':'template-upgrade','store_path':str(h.root/'hub.dets'),'port':free_port(),'agents':{'alice':secrets.token_urlsafe(32)},'admin_token':secrets.token_urlsafe(32),'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1'}};h.file.write_text(json.dumps(cfg));h.file.chmod(0o600)
    def rpc(cmd):return Client(h).rpc(cmd,h.config['agents']['alice'])
    def get(q,**kw):return rpc({'op':'get_history_query','query_id':q['id'],**kw})['query']
    def wait(fn):
        end=time.monotonic()+25
        while time.monotonic()<end:
            if value:=fn():return value
            time.sleep(.04)
        raise AssertionError('Template upgrade deadline')
    def finish(q):
        q=wait(lambda:v if (v:=get(q))['status']!='pending' else None);assert q['status']=='completed',q['error'];return q
    try:
        h.start();rpc({'op':'publish_record','text':'The original template upgrade evidence was retained.'})
        before=finish(rpc({'op':'query_history','question':'Which original evidence was retained?'})['query'])
        model.mode='slow';model.delay=2;pending=rpc({'op':'query_history','question':'Which evidence is still present?'})['query'];wait(lambda:get(pending)['usage']['calls']==1)
        h.stop(hard=True);model.mode='normal';h.command=command;h.image=args.image;h.start()
        after=get(before);assert after==before
        schema=Client(h).get('/protocol/schema')[1]
        def validator(name):return ByteValidator({'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=jsonschema.FormatChecker())
        validator('HistoryQuery').validate(after)
        request=after['evaluations'][0]['request'];validator('HistoryRecordedModelRequest').validate(request);assert not validator('HistoryModelRequest').is_valid(request)
        invalid=wait(lambda:v if (v:=get(pending))['status']=='invalidated' else None)
        assert invalid['error']['code']=='CONFIG_CHANGED' and invalid['usage']['uncertain_calls']==1 and invalid['usage']['time_ms']>=3000
        current=finish(rpc({'op':'continue_history_query','query_id':before['id'],'restart':True})['query'])
        assert current['evaluator']['template_sha256']!=before['evaluator']['template_sha256'] and current['snapshot']==before['snapshot']
        assert get(current,run=1)==before;validator('HistoryModelRequest').validate(current['evaluations'][0]['request'])
        h.stop(hard=True);h.start();assert get(current)==current and get(current,run=1)==before
        report={'schema':'adhd/model-template-upgrade@1','passed':True,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'producer_sha256':hashlib.sha256(Path(producer[-1]).read_bytes()).hexdigest(),'image':args.image,'cases':[{'case':name,'passed':True} for name in ['preserve-actual-old-choices-and-recorded-template','reject-old-request-as-current-template','invalidate-old-inflight-and-settle-reservation','restart-on-identical-frozen-corpus','retain-old-and-new-runs-across-hard-restart']]}
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n');print('PASS prior-template original evidence, current-vs-recorded choices, inflight fencing and restart')
    finally:h.stop();model.close()

if __name__=='__main__':main()
