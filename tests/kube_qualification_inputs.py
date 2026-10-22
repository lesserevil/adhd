"""Standard-library validation of closed inline qualification kubeconfig inputs."""
import json
from pathlib import Path
from urllib.parse import urlsplit


def validate_kube_endpoint(value,cluster):
    assert value['kind']=='Config' and value['apiVersion']=='v1'
    assert all(len(value[key])==1 for key in ('clusters','contexts','users'))
    context=value['contexts'][0];selected=value['clusters'][0];user=value['users'][0]
    assert value['current-context']==context['name']
    assert context['context']['cluster']==selected['name']=='kind-'+cluster
    assert context['context']['user']==user['name']
    assert set(user['user'])=={'client-certificate-data','client-key-data'}, 'No external auth executors/files'
    assert all(isinstance(v,str) and v for v in user['user'].values())
    assert selected['cluster'].get('certificate-authority-data')
    assert set(selected['cluster'])=={'server','certificate-authority-data'}, 'No proxy, TLS override or external CA files'
    endpoint=urlsplit(selected['cluster']['server'])
    assert endpoint.scheme=='https' and endpoint.hostname in ('127.0.0.1','::1') and endpoint.port
    assert not endpoint.username and not endpoint.password and not endpoint.path and not endpoint.query and not endpoint.fragment
    return {'server':selected['cluster']['server'],'host':endpoint.hostname,'port':endpoint.port,'cluster':cluster}



def unique_pairs(pairs):
    value={}
    for key,item in pairs:
        assert key not in value, 'Duplicate JSON kubeconfig key'
        value[key]=item
    return value


def json_kube_endpoint(path,cluster):
    path=Path(path);assert not path.is_symlink() and path.stat().st_size<=1048576
    return validate_kube_endpoint(json.loads(path.read_text(),object_pairs_hook=unique_pairs),cluster)
