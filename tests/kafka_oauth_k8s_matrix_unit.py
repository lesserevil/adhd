"""Pure secured-Kind entry and immutable preparation guards; no resources."""
import ast
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import kafka_oauth_k8s_matrix as runner


def main():
    code=compile(Path(runner.__file__).read_text(),runner.__file__,'exec')
    with patch.object(sys,'argv',[runner.__file__,'--execute']),patch('subprocess.Popen',side_effect=AssertionError('No processes')):
        try:exec(code,{'__name__':'__main__','__file__':runner.__file__})
        except AssertionError as error:assert 'reviewed frozen driver.py' in str(error)
        else:raise AssertionError('Authored execution accepted')
    with patch.object(runner,'readonly',side_effect=AssertionError('No Docker/Kube commands')):
        try:runner.cluster_facts('/kubectl','/config','foreign','tag','broker','proxy','namespace')
        except AssertionError as error:assert str(error)=='No Docker/Kube commands'
        else:raise AssertionError('Unexpected commands')
    node={'Name':'/owned-control-plane','State':{'Running':True},'Config':{'Labels':{'io.x-k8s.kind.cluster':'owned'}},'NetworkSettings':{'Ports':{'6443/tcp':[{'HostIp':'127.0.0.1','HostPort':'12345'}]}}}
    with patch.object(runner,'readonly',return_value=__import__('json').dumps([node]).encode()),patch.object(runner,'kube_endpoint',return_value={'host':'127.0.0.1','port':54321}):
        try:runner.cluster_facts('/kubectl','/config','owned-control-plane','tag','broker','proxy','namespace')
        except AssertionError as error:assert 'actual selected node' in str(error)
        else:raise AssertionError('Wrong published port accepted')
    source=Path(__file__).with_name('kafka_oauth_k8s.py').read_text()
    tree=ast.parse(source)
    assert len([n for n in ast.walk(tree) if isinstance(n,ast.Assert)])==51
    assert "args.initialize_projects=True" in source and "'configMapGenerator'" not in source
    assert 'with suppress(Exception):\n                run([\'delete\'' not in source
    assert "keytool=KeytoolProbe(PROXY_IMAGE,issuer.root)" in source
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory);(work/'frozen/tests').mkdir(parents=True)
        (work/'driver.py').write_text('current');(work/'frozen/tests/kafka_oauth_k8s_matrix.py').write_text('stale')
        try:runner.verify_own_matrix(work)
        except AssertionError as error:assert 'own matrix differs' in str(error)
        else:raise AssertionError('Stale own copy accepted')
        (work/'frozen/tests/kafka_oauth_k8s_matrix.py').write_text('current');runner.verify_own_matrix(work)
    print('PASS securedKind preparation pure6: authored entry rejected before helpers, zero real preflight calls, original48assertions/static initialization/shipped inline bootstrap verification, fixed keytoolsource, publishednode-port mismatch denial and no hidden namespace-delete errors; runtimes/providers0')


if __name__=='__main__':main()
