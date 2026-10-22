"""Mocked full model-gate entry and independent cleanup, no sockets/processes."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import patch
import kafka_deployed_model as gate


class HTTP:
    def __init__(self,**kwargs):assert kwargs=={'trust_env':False}
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def get(self,*args,**kwargs):return SimpleNamespace(status_code=200)


async def entry(root,mode):
    args=SimpleNamespace(model_only=True,model_relay_port=18960,model_url=None,gateway_report=None,
        model_window_file=None,image='sha256:'+'a'*64)
    admin=SimpleNamespace(call=lambda *_:{'config':{'matcher':None}})
    evidence=SimpleNamespace(value={},record=lambda *a,**k:None)
    vm={'container_id':'owned','vm_host_pid':1};seen=[]
    def popen(argv,**kwargs):
        seen.append('start-relay');(root/'model-relay.json').write_text('[]')
        assert argv.count('--max-calls')==1 and argv[argv.index('--max-calls')+1]=='12'
        return SimpleNamespace(pid=123,poll=lambda:None)
    def command(argv,**kwargs):
        seen.append('single-corpus');assert kwargs['timeout']==240
        assert '--with-backend-queries' in argv and '--privacy-canaries' in argv
        if mode=='primary':raise RuntimeError('original corpus failure')
        child={'passed':True,'artifact_sha256':None,'backend_query':{'positive_original_cited':True},
            'hot_model_enable_and_disable':True,'model_free_second_project_zero_inference':True,
            'foreign_and_private_canaries_absent_from_red_requests_and_answer':True,
            'relay_audit':{'upstream_attempts':6},'gateway_report_sha256':gate.sha(root/'model-relay.json')}
        (root/'optional-model.json').write_text(json.dumps(child))
    def close(*args):
        seen.append('stop-relay')
        if mode in ('cleanup','primary'):raise OSError('synthetic cleanup unknown')
        return {'process_exit_code':0,'listener_independently_absent':True}
    calls=0
    def identity():
        nonlocal calls
        calls+=1
        return {**vm,'container_id':'different' if mode=='restarted' and calls>1 else 'owned'}
    scope=gate.relay_scope('172.20.0.1',['172.20.0.2'],{'container_id':'owned'})
    with patch.object(gate.subprocess,'Popen',popen),patch.object(gate,'process_identity',return_value={'pid':123}),patch.object(gate,'stop_relay',close),patch.object(gate.httpx,'AsyncClient',HTTP):
        try:
            await gate.run(args,root=root,repo=Path(__file__).resolve().parents[1],base='http://127.0.0.1:1',credentials=root/'credentials',
                expected='b'*64,command=command,vm_identity=identity,scope=scope,admin=admin,evidence=evidence)
        except BaseException as error:
            assert mode!='success'
            if mode=='primary':assert isinstance(error,RuntimeError) and 'original corpus' in str(error) and error.__notes__
            if mode=='cleanup':assert isinstance(error,OSError)
            if mode=='restarted':assert isinstance(error,AssertionError)
        else:assert mode=='success' and evidence.value['optional_model']['same_packaged_vm_before_after_hot_changes']
    assert seen==['start-relay','single-corpus','stop-relay']
    assert ('optional_model' in evidence.value)==(mode=='success')


def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for mode in ('success','primary','cleanup','restarted'):
            work=root/mode;work.mkdir();asyncio.run(entry(work,mode))
        for bind,callers in [('0.0.0.0',['172.20.0.2']),('127.0.0.1',['172.20.0.2']),('172.20.0.1',['8.8.8.8'])]:
            try:gate.relay_scope(bind,callers,{'owned':True})
            except AssertionError:pass
            else:raise AssertionError('Foreign/wildcard relay scope admitted')
    print(json.dumps({'passed':True,'checks':7,'apps_models_sockets_started':False}))


if __name__=='__main__':main()
