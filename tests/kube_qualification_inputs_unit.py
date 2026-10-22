"""Pure semantic and malformed/foreign JSON kubeconfig guards; no APIs."""
import copy
import json
from pathlib import Path
import tempfile
from kube_qualification_inputs import validate_kube_endpoint,json_kube_endpoint


def denied(call):
    try:call()
    except (AssertionError,KeyError,TypeError):return
    raise AssertionError('Unsafe endpoint accepted')


def main():
    value={'kind':'Config','apiVersion':'v1','clusters':[{'name':'kind-owned','cluster':{'server':'https://127.0.0.1:34113','certificate-authority-data':'exactCA'}}],
        'contexts':[{'name':'owned-context','context':{'cluster':'kind-owned','user':'owned-user'}}],
        'users':[{'name':'owned-user','user':{'client-certificate-data':'exactCert','client-key-data':'exactKey'}}],'current-context':'owned-context'}
    endpoint=validate_kube_endpoint(value,'owned');assert endpoint=={'server':'https://127.0.0.1:34113','host':'127.0.0.1','port':34113,'cluster':'owned'}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'config';path.write_text(json.dumps(value));assert json_kube_endpoint(path,'owned')==endpoint
        path.write_text('{"kind":"Config","kind":"Other"}');denied(lambda:json_kube_endpoint(path,'owned'))
        path.unlink();path.symlink_to(Path(directory)/'missing');denied(lambda:json_kube_endpoint(path,'owned'))
    denied(lambda:validate_kube_endpoint(value,'foreign'))
    for server in ['http://127.0.0.1:34113','https://remote.invalid:34113','https://127.0.0.1:34113/path','https://user:pass@127.0.0.1:34113','https://127.0.0.1']:
        bad=copy.deepcopy(value);bad['clusters'][0]['cluster']['server']=server;denied(lambda bad=bad:validate_kube_endpoint(bad,'owned'))
    bad=copy.deepcopy(value);bad['users'][0]['user']['exec']={'command':'foreign'};denied(lambda:validate_kube_endpoint(bad,'owned'))
    print('PASS stdlib kubeconfig pure8: semanticclosedJSON equivalence, duplicate/symlink/foreigncluster/remote-or-credentialed-or-path endpoint/auth-exec denial; API/runtime calls0')


if __name__=='__main__':main()
