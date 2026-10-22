"""Model-only matrix admission/cleanup/identity guards; no Docker, sockets or provider."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import kafka_deployed_model_matrix as runner


def child():
    return {'passed':True,'model_only_requested':True,'artifact_sha256':'a'*64,'image_config_digest':'sha256:'+'b'*64,
        'runtime_hub_image_config_digest':'sha256:'+'b'*64,'compiled_vm_custody':[{'image':'sha256:'+'b'*64,'process':{'actual_compiled_boot_and_app_arguments':True}}]*2,'cleanup':{'resources_independently_absent':True,'failures':[]},
        'optional_model':{'passed':True,'same_packaged_vm_before_after_hot_changes':True,'image_config_digest':'sha256:'+'b'*64,'artifact_sha256':'a'*64,
            'budget':{'upstream_attempts':6},'cleanup':{'listener_independently_absent':True}},'model_relay_cleanup':{'confirmed':True}}


def scenario(root,mode):
    work=root/mode;work.mkdir();(work/'results').mkdir()
    plan={'image':'sha256:'+'b'*64,'artifact_sha256':'a'*64,'driver_sha256':'c'*64,'lease_path':'/owned/cooperative.lock',
        'expected_model':{},'tools':{'docker':{'path':'/docker'}},'jobs':[{'name':name,'argv':[name]} for name in ('compose','k8s')],'env':{},'scope':'diagnostic unit'}
    if mode=='baseline':plan['baseline']=True
    runner.dump(work/'plan.json',plan);events=[]
    def acquire(path):
        events.append('lease')
        if mode=='busy':raise BlockingIOError('busy')
        return 123,(1,2)
    def inspect(*args):events.append('inspect');return {'container_id':'original','metadata_client':{'reaped':True}}
    def popen(argv,**kwargs):
        name=argv[0];events.append(name)
        if mode=='creation':raise OSError('original create failure')
        value=child()
        if mode=='baseline':
            value.update(model_only_requested=False,selective_recovery_requested=True);value.pop('optional_model');value.pop('model_relay_cleanup')
        if mode=='invalid':value['optional_model']['budget']['upstream_attempts']=13
        runner.dump(work/(name+'.json'),value)
        return SimpleNamespace(pid=42)
    def close(fd):
        events.append('release')
        if mode=='cleanup':raise OSError('lease close failure')
    module=SimpleNamespace(acquire=acquire,inspect_model=inspect,regular=lambda *a:SimpleNamespace(st_dev=1,st_ino=2))
    failure=None
    with patch.dict(sys.modules,{'model_service_lease':module}),patch.object(runner,'verify',return_value=True),patch.object(runner,'claim_execution',side_effect=lambda *a:events.append('once')),patch.object(runner.subprocess,'Popen',side_effect=popen),patch.object(runner,'wait_owned_child',return_value=0),patch.object(runner.os,'close',side_effect=close):
        try:runner.execute(work,runner.sha(work/'plan.json'))
        except BaseException as error:failure=error
    report=json.loads((work/'matrix.json').read_text())
    assert report['passed']==(mode in ('success','baseline'))
    if mode=='success':assert events==['lease','inspect','once','compose','k8s','inspect','release'] and not report['unrun_platforms']
    elif mode=='baseline':assert events==['once','compose','k8s'] and not report['lease_acquired'] and report['model_before'] is None
    elif mode=='busy':assert isinstance(failure,BlockingIOError) and events==['lease'] and report['unrun_platforms']==['compose','k8s']
    elif mode=='creation':assert isinstance(failure,OSError) and report['rows'][0]['attempted'] and not report['rows'][0]['started'] and report['unrun_platforms']==['compose','k8s']
    elif mode=='invalid':assert isinstance(failure,AssertionError) and report['rows'][0]['started'] and report['rows'][0]['exit_code']==0 and report['unrun_platforms']==['k8s']
    else:assert failure is not None and report['cleanup_failures'] and not report['passed']
    return report


def main():
    plan={'image':'sha256:'+'b'*64,'artifact_sha256':'a'*64};assert runner.qualified(child(),plan)
    for path,value in [(('passed',),False),(('runtime_hub_image_config_digest',),'foreign'),(('model_only_requested',),False),
        (('optional_model','budget','upstream_attempts'),13),(('model_relay_cleanup','confirmed'),False),
        (('cleanup','resources_independently_absent'),False),(('optional_model','same_packaged_vm_before_after_hot_changes'),False)]:
        bad=child();target=bad
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
        try:runner.qualified(bad,plan)
        except AssertionError:pass
        else:raise AssertionError('Invalid child passed')
    code=compile(Path(runner.__file__).read_text(),runner.__file__,'exec')
    with patch.object(sys,'argv',[runner.__file__,'--execute']),patch('subprocess.Popen',side_effect=AssertionError('No processes')):
        try:exec(code,{'__name__':'__main__','__file__':runner.__file__})
        except AssertionError as error:assert 'reviewed frozen driver.py' in str(error)
        else:raise AssertionError('Authored execute admitted')
    with tempfile.TemporaryDirectory() as temp:
        for mode in ('success','baseline','busy','creation','invalid','cleanup'):scenario(Path(temp),mode)
    print(json.dumps({'passed':True,'checks':15,'apps_models_compilers_sockets_started':False}))


if __name__=='__main__':main()
