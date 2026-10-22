"""Pure paused learned-image namespace plan; no app, compiler or socket starts."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from container_fixture import OwnedImage
from project_recovery_learned import IsolatedRecoveryImage
from workflow_provider_isolation import model_endpoints


def main():
    historical={'matcher':{'url':'http://127.0.0.1:18770/v1/systemone'},'projects':[{'id':'red','settings':{'history':{'url':'http://localhost:18770'}}}]}
    original=copy.deepcopy(historical)
    paused={'host':'0.0.0.0','port':32123,'public_url':'http://127.0.0.1:32123','matcher':None,'history':{'url':None},'optimization':{'enabled':False}}
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.Popen',side_effect=AssertionError('No process')),patch('subprocess.run',side_effect=AssertionError('No compiler or process')):
        root=Path(directory);manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'adhd/container-inputs@1','files':{'hub.exs':'a'*64}}))
        config=root/'hub.json';config.write_text(json.dumps(paused))
        target=IsolatedRecoveryImage('sha256:'+'b'*64,manifest,root,historical)
        assert target.isolation_endpoints(paused)==[('127.0.0.1',18770),('localhost',18770)]
        assert model_endpoints(paused,require_nonempty=False)==[] and historical==original
        base=['docker','run','--rm','--network','host','--read-only','sha256:'+'b'*64]
        with patch.object(OwnedImage,'argv',return_value=base):argv=target.argv(config)
        assert '--rm' not in argv and argv[argv.index('--network')+1]=='bridge'
        assert argv[-3:]==['--publish','127.0.0.1:32123:32123',base[-1]] and base[3]=='--network'
        assert json.loads(config.read_text())==paused
        target.cleanup_blocked=True
        with patch.object(OwnedImage,'argv',side_effect=AssertionError('Underlying argv must remain untouched')) as parent:
            try:target.argv(root/'missing-config-must-not-be-read.json')
            except AssertionError as error:assert str(error)=='Prior owned cleanup remains unconfirmed'
            else:raise AssertionError('Replacement admitted after unconfirmed cleanup')
            assert parent.call_count==0
        target.cleanup_blocked=False
        target.name='synthetic-owned-name';target.image_id='sha256:'+'b'*64
        row={'Id':'c'*64,'Image':target.image_id,'State':{'Running':True,'Pid':992999},
            'HostConfig':{'NetworkMode':'bridge','PidMode':'private','Privileged':False,
                'PortBindings':{'32123/tcp':[{'HostIp':'127.0.0.1','HostPort':'32123'}]}},
            'NetworkSettings':{'Networks':{'bridge':{}}}}
        def docker(*args,**kwargs):
            if args[0]=='inspect':raw=json.dumps([row]).encode()
            elif args[-1]=='/proc/1/ns/net':raw=b'net:[synthetic-private]'
            elif args[-1]=='/proc/1/exe':raw=b'/usr/lib/erlang/erts/bin/beam.smp'
            elif args[-1]=='/proc/1/cmdline':raw=b'/app/hub.exs\0'+json.dumps(['serve',str(config)]).encode()+b'\0'
            else:
                assert args[0]=='exec' and args[2]=='elixir' and args[-2] in ('127.0.0.1','localhost') and args[-1]=='18770'
                raw=b'isolated-model-port-refused\n'
            return SimpleNamespace(stdout=raw)
        target.docker=docker;target.observe()
        assert target.isolation_observations[-1]['effective_current_model_endpoints']==[]
        assert target.isolation_observations[-1]['historical_provider_route_proof'] is True
        historical['matcher']['url']='http://unexpected.invalid:18770'
        assert target.isolation_endpoints(paused)==[('127.0.0.1',18770),('localhost',18770)],'Historical custody input not copied'
        try:target.isolation_endpoints({**paused,'projects':[{'id':'hidden','settings':{'archive':{'url':'http://external.invalid:18770'}}}]})
        except AssertionError:pass
        else:raise AssertionError('Non-loopback effective target route admitted')
    print('PASS learned image preparation7: historical/effective endpoint union, paused config unchanged, private bridge/local mapping, retained lifecycle, VM namespace/cmdline/refusal evidence, unsafe route rejected, unknown-cleanup replacement denied; app/compiler/process attempts0')


if __name__=='__main__':main()
