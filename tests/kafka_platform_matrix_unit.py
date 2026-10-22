"""Pure platform driver custody/scheduling checks: every process boundary mocked."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import yaml
import kafka_platform_matrix as driver


def kube():
    return {'kind':'Config','apiVersion':'v1','current-context':'kind-adhd-test','clusters':[{'name':'kind-adhd-test','cluster':{'server':'https://127.0.0.1:12345','certificate-authority-data':'fixture-ca'}}],
        'contexts':[{'name':'kind-adhd-test','context':{'cluster':'kind-adhd-test','user':'fixture'}}],
        'users':[{'name':'fixture','user':{'client-certificate-data':'fixture-cert','client-key-data':'fixture-key'}}]}


def plan(work):
    value={'execution_allowed':True,'historical_binding_only':False,'image_config_identity':'sha256:'+'a'*64,
        'artifact_sha256':'b'*64,'driver_sha256':'c'*64,'runtime_cwd':str(work),'scope':'pure mocked fixture',
        'jobs':[{'name':name,'argv':['not-a-real-executable',name]} for name in ('compose','k8s')]}
    driver.dump(work/'plan.json',value)
    return value,driver.sha(work/'plan.json')


def execution(work,behavior):
    value,digest=plan(work);calls=[]
    def child(argv,**kwargs):
        name=argv[-1];calls.append(name)
        if behavior=='raise':raise OSError('Synthetic child creation failure')
        if behavior=='false':return SimpleNamespace(returncode=1)
        if behavior!='missing-report':
            driver.dump(work/(name+'.json'),{'passed':True,'artifact_sha256':value['artifact_sha256'],
                'image_config_digest':value['image_config_identity'],'selective_recovery_requested':True,
                'cleanup':{'resources_independently_absent':behavior!='unknown-cleanup','failures':[]}})
        return SimpleNamespace(returncode=0)
    def preflight(*a):
        if behavior=='preflight':raise AssertionError('Synthetic cluster binding failure')
    with patch.object(driver,'verify',return_value=True),patch.object(driver,'environment',return_value={}),patch.object(driver,'preflight',preflight),patch('subprocess.run',child),patch('subprocess.Popen',side_effect=AssertionError('No real process permitted')):
        try:result=driver.execute(work,digest)
        except (AssertionError,OSError):result=None
    output=json.loads((work/'matrix.json').read_text())
    assert (work/'execution-started.json').is_file()
    if behavior=='pass':assert result==0 and calls==['compose','k8s'] and output['passed'] and output['unrun_platforms']==[]
    elif behavior=='preflight':assert calls==[] and output['executed_platforms']==[] and output['unrun_platforms']==['compose','k8s']
    else:assert calls==['compose'] and output['executed_platforms']==['compose'] and output['unrun_platforms']==['k8s']
    assert output['passed']==(behavior=='pass')
    with patch.object(driver,'verify',return_value=True),patch.object(driver,'preflight',side_effect=AssertionError('No preflight on reentry')),patch('subprocess.Popen',side_effect=AssertionError('No process')):
        try:driver.execute(work,digest)
        except FileExistsError:pass
        else:raise AssertionError('Reentry admitted')


def main():
    checks=0
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary).resolve();cfg=root/'kubeconfig'
        cfg.write_text(yaml.safe_dump(kube()));assert driver.kube_endpoint(cfg,'adhd-test')['port']==12345;checks+=1
        for mode in ('exec','remote','path'):
            value=kube()
            if mode=='exec':value['users'][0]['user']={'exec':{'command':'not-permitted'}}
            if mode=='remote':value['clusters'][0]['cluster']['server']='https://example.invalid:12345'
            if mode=='path':value['clusters'][0]['cluster']['server']='https://127.0.0.1:12345/api'
            cfg.write_text(yaml.safe_dump(value))
            try:driver.kube_endpoint(cfg,'adhd-test')
            except AssertionError:pass
            else:raise AssertionError('Unsafe Kubeconfig accepted')
            checks+=1
        work=root/'baseline';work.mkdir();value,digest=plan(work);value['execution_allowed']=False;driver.dump(work/'plan.json',value)
        with patch('subprocess.Popen',side_effect=AssertionError('No process')),patch.object(driver,'preflight',side_effect=AssertionError('No preflight')):
            try:driver.execute(work,driver.sha(work/'plan.json'))
            except AssertionError:pass
            else:raise AssertionError('Historical binding plan executed')
        assert not (work/'execution-started.json').exists();checks+=1
        for behavior in ('pass','false','missing-report','unknown-cleanup','raise','preflight'):
            work=root/behavior;work.mkdir();execution(work,behavior);checks+=1
        tree=root/'tree';tree.mkdir();(tree/'known').write_text('fixture');inputs=driver.file_tree(tree)
        (tree/'shadow.py').write_text('unreviewed')
        try:driver.verify_frozen_inputs(tree,inputs)
        except AssertionError:pass
        else:raise AssertionError('Unlisted shadow file accepted')
        (tree/'shadow.py').unlink();(tree/'alias').symlink_to(tree/'known')
        try:driver.file_tree(tree)
        except AssertionError:pass
        else:raise AssertionError('Symlink accepted')
        checks+=1
    print('PASS platform matrix pure'+str(checks)+': Kubeconfig scope, binding-only deny, serial/fail-fast/actual-report/cleanup/attempt accounting, fsynced once-only reentry, exact set/symlink; real process attempts0')


if __name__=='__main__':main()
